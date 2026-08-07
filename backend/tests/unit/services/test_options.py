"""Unit tests for services/options.py — option economics helpers.

All money/price math uses Decimal (per AGENTS.md)."""
import logging
from decimal import Decimal

import pytest

from services import options


# ---------------------------------------------------------------------------
# contract_size_for_underlying
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestContractSize:
    def test_btc(self):
        assert options.contract_size_for_underlying("BTC") == Decimal("0.01")

    def test_eth(self):
        assert options.contract_size_for_underlying("ETH") == Decimal("0.1")

    def test_case_insensitive(self):
        assert options.contract_size_for_underlying("btc") == Decimal("0.01")
        assert options.contract_size_for_underlying("Eth") == Decimal("0.1")

    def test_unknown_coin_defaults_to_one_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert options.contract_size_for_underlying("SOL") == Decimal("1")
        assert any("SOL" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# gross_premium
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGrossPremium:
    def test_canonical_btc_option_sell(self):
        # 7 contracts × 0.0022 BTC × 0.01 = 0.000154 BTC (the user's CSV case).
        assert options.gross_premium(
            Decimal("7"), Decimal("0.0022"), Decimal("0.01")
        ) == Decimal("0.000154")

    def test_zero_quantity(self):
        assert options.gross_premium(Decimal("0"), Decimal("100"), Decimal("1")) == Decimal("0")


# ---------------------------------------------------------------------------
# intrinsic_price  (USD-strike / coin-settled, OKX/Bybit style)
# ---------------------------------------------------------------------------

class _FakeMeta:
    """Minimal stand-in for OptionMetadata to avoid DB setup in pure-math tests."""
    def __init__(self, option_type, strike_price):
        self.option_type = option_type
        self.strike_price = strike_price


@pytest.mark.unit
class TestIntrinsicPrice:
    def test_call_otm(self):
        # spot below strike -> 0
        meta = _FakeMeta("CALL", Decimal("80000"))
        assert options.intrinsic_price(meta, Decimal("70000"), Decimal("0.01")) == Decimal("0")

    def test_call_itm(self):
        # spot 85000, strike 80000, size 0.01:
        # USD intrinsic per contract = 0.01 * (85000-80000) = 50 USD
        # BTC intrinsic = 50 / 85000 = 0.0005882352...  -> quantize 8dp
        meta = _FakeMeta("CALL", Decimal("80000"))
        result = options.intrinsic_price(meta, Decimal("85000"), Decimal("0.01"))
        assert result == Decimal("0.00058824")  # 8 dp

    def test_put_itm(self):
        # spot 75000, strike 80000, size 0.01:
        # USD intrinsic = 0.01 * (80000-75000) = 50 USD; BTC = 50/75000 = 0.0006666666...
        meta = _FakeMeta("PUT", Decimal("80000"))
        result = options.intrinsic_price(meta, Decimal("75000"), Decimal("0.01"))
        assert result == Decimal("0.00066667")  # 8 dp

    def test_put_otm(self):
        meta = _FakeMeta("PUT", Decimal("80000"))
        assert options.intrinsic_price(meta, Decimal("85000"), Decimal("0.01")) == Decimal("0")

    def test_at_strike_is_zero(self):
        meta = _FakeMeta("CALL", Decimal("80000"))
        assert options.intrinsic_price(meta, Decimal("80000"), Decimal("0.01")) == Decimal("0")


# ---------------------------------------------------------------------------
# derive_collateral
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDeriveCollateral:
    """derive_collateral is a SELL-only concept.

    Option writers post collateral; option buyers pay premium and post none.
    Task 4's decompose_option_fill will call derive_collateral only for sells
    (collateral = 0 for buys is handled there).
    """

    def test_canonical_sell(self):
        # BC = -0.00701889, premium = +0.000154, fee_signed = -0.00001078
        # BC_sell = +premium + fee_signed - collateral
        #        -> collateral = premium + fee_signed - BC_signed
        #        = 0.000154 + (-0.00001078) - (-0.00701889)
        #        = 0.000154 - 0.00001078 + 0.00701889 = 0.00716211
        # Matches the CSV settlement row's collateral release exactly.
        collateral = options.derive_collateral(
            balance_change_signed=Decimal("-0.00701889"),
            premium=Decimal("0.000154"),
            fee_signed=Decimal("-0.00001078"),
        )
        assert collateral == Decimal("0.00716211")   # matches CSV + settlement release
