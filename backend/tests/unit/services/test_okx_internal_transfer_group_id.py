"""Deterministic synthetic group id for OKX internal transfers."""
from decimal import Decimal

from services.importer import _okx_internal_transfer_group_id


def test_sign_and_case_invariant_within_same_minute():
    funding_leg = _okx_internal_transfer_group_id("BTC", Decimal("0.458495"), 1750600000000)
    trading_leg = _okx_internal_transfer_group_id("btc", Decimal("-0.458495"), 1750600000500)
    assert funding_leg == trading_leg
    assert funding_leg == f"okx_xfer:btc:0.458495:{1750600000000 // 60000}"


def test_canonical_amount_strips_trailing_zeros():
    key = _okx_internal_transfer_group_id("USDT", "300.00389139000000", 1750600000000)
    assert "300.003891" in key  # 6dp quantize + normalize collapse the residue


def test_one_second_skew_still_matches():
    """Real-data regression: OKX stamps the funding leg ~1s after the trading
    leg (e.g. ts ...420 trading vs ...421 funding). Second-granularity keys
    never matched, so the basis carry was lost (the TRUMP +11.21 bug)."""
    trading_leg = _okx_internal_transfer_group_id("TRUMP", Decimal("-0.679620"), 1737288420000)
    funding_leg = _okx_internal_transfer_group_id("TRUMP", Decimal("0.679620"), 1737288421000)
    assert trading_leg == funding_leg


def test_amount_precision_mismatch_still_matches():
    """Real-data regression: the trading CSV rounds to 7dp while the funding
    CSV carries full precision (0.6798604 vs 0.67986039864375). Quantizing to
    6dp unifies them."""
    trading_leg = _okx_internal_transfer_group_id("TRUMP", Decimal("0.6798604"), 1739121318000)
    funding_leg = _okx_internal_transfer_group_id("TRUMP", Decimal("0.67986039864375"), 1739121318000)
    assert trading_leg == funding_leg


def test_different_minute_does_not_collide():
    a = _okx_internal_transfer_group_id("BTC", Decimal("1"), 1750600000000)
    b = _okx_internal_transfer_group_id("BTC", Decimal("1"), 1750600060000)  # +60s
    assert a != b


def test_different_ccy_does_not_collide():
    a = _okx_internal_transfer_group_id("BTC", Decimal("1"), 1750600000000)
    b = _okx_internal_transfer_group_id("TRUMP", Decimal("1"), 1750600000000)
    assert a != b


def test_different_amount_does_not_collide():
    a = _okx_internal_transfer_group_id("BTC", Decimal("1.000001"), 1750600000000)
    b = _okx_internal_transfer_group_id("BTC", Decimal("1.000002"), 1750600000000)
    assert a != b
