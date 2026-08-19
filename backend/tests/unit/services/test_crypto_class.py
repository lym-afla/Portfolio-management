"""Tests for services/crypto.py — Crypto-class helpers."""
from datetime import date
from decimal import Decimal

import pytest

from common.models import Assets, FX, Prices
from services.crypto import (
    crypto_fx_rate,
    crypto_usd_price,
    is_crypto,
    is_crypto_code,
)


@pytest.fixture
def btc_asset(user):
    asset = Assets.objects.create(
        type="Crypto",
        ISIN="CRYPTO:BTC",
        name="BTC",
        currency="USD",
        exposure="Commodity",
        yahoo_symbol="BTC-USD",
    )
    asset.investors.add(user)
    return asset


@pytest.fixture
def usd_eur_fx(user):
    fx = FX.objects.create(
        date=date(2026, 1, 1),
        from_currency="USD",
        to_currency="EUR",
        rate=Decimal("1.1"),
    )
    fx.investors.add(user)
    return fx


@pytest.mark.django_db
def test_is_crypto_true_for_crypto_asset(btc_asset):
    assert is_crypto(btc_asset) is True


@pytest.mark.django_db
def test_is_crypto_false_for_stock(asset):
    assert is_crypto(asset) is False


@pytest.mark.django_db
def test_is_crypto_code_recognizes_btc(btc_asset):
    assert is_crypto_code("BTC") is True
    assert is_crypto_code("btc") is True  # case-insensitive


@pytest.mark.django_db
def test_is_crypto_code_false_for_fiat_and_stablecoin():
    assert is_crypto_code("USD") is False
    assert is_crypto_code("USDT") is False
    assert is_crypto_code("EUR") is False
    assert is_crypto_code("UNKNOWN") is False


@pytest.mark.django_db
def test_crypto_usd_price_from_prices(btc_asset):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    price = crypto_usd_price("BTC", date(2026, 1, 1))
    assert price == Decimal("60000")


@pytest.mark.django_db
def test_crypto_usd_price_missing_raises(btc_asset):
    with pytest.raises(ValueError):
        crypto_usd_price("BTC", date(2026, 1, 1))


@pytest.mark.django_db
def test_crypto_fx_rate_btc_to_eur(btc_asset, usd_eur_fx, user):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    # BTC -> EUR chains BTC->USD (the coin's USD price, 60000) with the fiat
    # graph's USD->EUR rate. The stored FX row is quote-per-base
    # (from=USD, to=EUR, rate=1.1 means "1.1 USD per 1 EUR"), so get_rate's
    # path-walk computes USD->EUR as 1/1.1 and rounds to 6 dp (0.909091)
    # before returning. crypto_fx_rate then multiplies and re-quantizes.
    rate = crypto_fx_rate("BTC", "EUR", date(2026, 1, 1), investor=user)
    # 60000 (BTC->USD) * 0.909091 (USD->EUR, 6-dp rounded by get_rate) = 54545.46
    expected = (Decimal("60000") * Decimal("0.909091")).quantize(Decimal("0.000001"))
    assert rate == expected


@pytest.mark.django_db
def test_crypto_fx_rate_same_currency_is_one(btc_asset, user):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    rate = crypto_fx_rate("BTC", "USD", date(2026, 1, 1), investor=user)
    assert rate == Decimal("60000")  # BTC->USD = the price itself


@pytest.mark.django_db
def test_resolve_crypto_asset_sets_yahoo_symbol(user):
    """Task 8: resolve_crypto_asset must set yahoo_symbol="<SYMBOL>-USD" on the
    Assets row for every coin it creates (or backfills the value on an existing
    row whose yahoo_symbol is blank, via resolve_or_create_asset's silent-mode
    empty-field fill)."""
    from services.crypto_exchange import resolve_crypto_asset

    for symbol, expected_yahoo in [
        ("BTC", "BTC-USD"),
        ("ETH", "ETH-USD"),
        ("TRUMP", "TRUMP-USD"),
    ]:
        asset = resolve_crypto_asset(symbol, user)
        assert asset.yahoo_symbol == expected_yahoo, f"{symbol} -> {asset.yahoo_symbol}"


@pytest.mark.django_db
class TestCryptoUsdPriceWithFallback:
    """Three-tier price resolver: market price -> last-trade price -> None."""

    def test_tier1_market_price(self, user):
        """When a Prices row exists, return it (tier 1)."""
        from datetime import datetime, timezone
        from common.models import Transactions
        from services.crypto import crypto_usd_price_with_fallback
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:FB1", name="FB1",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        Prices.objects.create(security=coin, date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                              price=Decimal("100"))
        result = crypto_usd_price_with_fallback("FB1", date(2026, 6, 1), investor=user)
        assert result == Decimal("100")

    def test_tier2_last_trade_price(self, user):
        """When no Prices row but a trade exists, return last-trade price."""
        from datetime import datetime, timezone
        from common.models import Accounts, Brokers, Transactions
        from services.crypto import crypto_usd_price_with_fallback
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:FB2", name="FB2",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        broker = Brokers.objects.create(investor=user, name="FB2B", country="X")
        acct = Accounts.objects.create(broker=broker, name="A")
        Transactions.objects.create(
            investor=user, account=acct, security=coin, currency="USDT",
            type="Crypto trade out",
            date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            quantity=Decimal("-1"), price=Decimal("16.557"),
        )
        result = crypto_usd_price_with_fallback("FB2", date(2026, 6, 1), investor=user)
        assert result == Decimal("16.557")

    def test_tier3_none_when_no_price_no_trade(self, user):
        """When no Prices row AND no trade, return None."""
        from services.crypto import crypto_usd_price_with_fallback
        Assets.objects.create(type="Crypto", ISIN="CRYPTO:FB3", name="FB3",
                              currency="USD", exposure="Commodity").investors.add(user)
        result = crypto_usd_price_with_fallback("FB3", date(2026, 6, 1), investor=user)
        assert result is None


@pytest.mark.django_db
class TestSafeCryptoFxRate:
    """safe_crypto_fx_rate returns None+warning instead of raising."""

    def test_priced_returns_rate(self, user):
        from datetime import datetime, timezone
        from services.crypto import safe_crypto_fx_rate
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:SF1", name="SF1",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        Prices.objects.create(security=coin, date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                              price=Decimal("50000"))
        result = safe_crypto_fx_rate("SF1", "USD", date(2026, 6, 1), investor=user)
        assert result == Decimal("50000")

    def test_unpriced_no_trade_returns_none(self, user):
        from services.crypto import safe_crypto_fx_rate
        Assets.objects.create(type="Crypto", ISIN="CRYPTO:SF2", name="SF2",
                              currency="USD", exposure="Commodity").investors.add(user)
        result = safe_crypto_fx_rate("SF2", "USD", date(2026, 6, 1), investor=user)
        assert result is None

    def test_unpriced_with_trade_returns_last_trade(self, user):
        from datetime import datetime, timezone
        from common.models import Accounts, Brokers, Transactions
        from services.crypto import safe_crypto_fx_rate
        coin = Assets.objects.create(type="Crypto", ISIN="CRYPTO:SF3", name="SF3",
                                     currency="USD", exposure="Commodity")
        coin.investors.add(user)
        broker = Brokers.objects.create(investor=user, name="SF3B", country="X")
        acct = Accounts.objects.create(broker=broker, name="A")
        Transactions.objects.create(
            investor=user, account=acct, security=coin, currency="USDT",
            type="Crypto trade out",
            date=datetime(2026, 1, 15, tzinfo=timezone.utc),
            quantity=Decimal("-1"), price=Decimal("42"),
        )
        result = safe_crypto_fx_rate("SF3", "USD", date(2026, 6, 1), investor=user)
        assert result == Decimal("42")
