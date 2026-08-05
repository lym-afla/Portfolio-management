"""Tests for the crypto branch of services.fx.get_rate (spec §4.5)."""
from datetime import date
from decimal import Decimal

import pytest

from common.models import Assets, FX, Prices
from services.fx import get_rate


@pytest.fixture
def btc_asset(user):
    asset = Assets.objects.create(
        type="Crypto", ISIN="CRYPTO:BTC", name="BTC",
        currency="USD", exposure="Commodity", yahoo_symbol="BTC-USD",
    )
    asset.investors.add(user)
    return asset


@pytest.fixture
def usd_eur_fx(user):
    fx = FX.objects.create(
        date=date(2026, 1, 1), from_currency="USD", to_currency="EUR", rate=Decimal("1.1"),
    )
    fx.investors.add(user)
    return fx


@pytest.mark.django_db
def test_get_rate_btc_to_usd_uses_price(btc_asset):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    result = get_rate("BTC", "USD", date(2026, 1, 1))
    assert result["FX"] == Decimal("60000")


@pytest.mark.django_db
def test_get_rate_btc_to_eur_chains_through_usd(btc_asset, usd_eur_fx, user):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    result = get_rate("BTC", "EUR", date(2026, 1, 1), investor=user)
    # crypto_fx_rate("BTC","EUR") = 60000 * get_rate("USD","EUR")["FX"]
    # get_rate("USD","EUR") walks the FX graph and returns the reciprocal-of-1.1
    # rounded to 6 dp = 0.909091. The final result is then rounded to 6 dp.
    expected = (Decimal("60000") * Decimal("0.909091")).quantize(Decimal("0.000001"))
    assert result["FX"] == expected


@pytest.mark.django_db
def test_get_rate_usd_to_btc_inverts(btc_asset):
    Prices.objects.create(security=btc_asset, date=date(2026, 1, 1), price=Decimal("60000"))
    result = get_rate("USD", "BTC", date(2026, 1, 1))
    # USD -> BTC = 1 / 60000, rounded to 6 dp
    expected = (Decimal("1") / Decimal("60000")).quantize(Decimal("0.000001"))
    assert result["FX"] == expected


@pytest.mark.django_db
def test_get_rate_btc_missing_price_raises(btc_asset):
    with pytest.raises(ValueError):
        get_rate("BTC", "USD", date(2026, 1, 1))


@pytest.mark.django_db
def test_get_rate_stablecoin_peg_unchanged():
    """The USD<->USDT 1.0 peg short-circuit must still work."""
    result = get_rate("USD", "USDT", date(2026, 1, 1))
    assert result["FX"] == Decimal("1.000000")
