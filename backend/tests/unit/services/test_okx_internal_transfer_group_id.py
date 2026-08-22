"""Deterministic synthetic group id for OKX internal transfers."""
from decimal import Decimal

from services.importer import _okx_internal_transfer_group_id


def test_sign_and_case_invariant_within_same_second():
    funding_leg = _okx_internal_transfer_group_id("BTC", Decimal("0.45849457"), 1750600000000)
    trading_leg = _okx_internal_transfer_group_id("btc", Decimal("-0.45849457"), 1750600000500)
    assert funding_leg == trading_leg
    assert funding_leg == "okx_xfer:btc:0.45849457:1750600000"


def test_canonical_amount_strips_trailing_zeros():
    key = _okx_internal_transfer_group_id("USDT", "300.00389139000000", 1750600000000)
    assert "300.00389139" in key  # Decimal.normalize() collapses trailing zeros


def test_different_second_does_not_collide():
    a = _okx_internal_transfer_group_id("BTC", Decimal("1"), 1750600000000)
    b = _okx_internal_transfer_group_id("BTC", Decimal("1"), 1750600001000)
    assert a != b


def test_different_ccy_does_not_collide():
    a = _okx_internal_transfer_group_id("BTC", Decimal("1"), 1750600000000)
    b = _okx_internal_transfer_group_id("TRUMP", Decimal("1"), 1750600000000)
    assert a != b
