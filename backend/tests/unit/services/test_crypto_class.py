"""Tests for services/crypto.py — Crypto-class helpers."""
from datetime import date
from decimal import Decimal

import pytest

from common.models import Assets, Prices
from common.models import FX
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
