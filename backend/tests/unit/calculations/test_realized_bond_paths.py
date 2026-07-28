"""Tests for bond redemption and bond sell G/L paths in services/realized.py.

Covers two previously-uncovered code blocks in ``realized_gain_loss``:

1. Bond redemption G/L branch (``services/realized.py`` lines ~670-742), hit
   when a transaction has ``type`` of "Bond redemption" or "Bond maturity" and
   a non-null ``notional_change``. Gain is computed from ``cash_flow``,
   ``notional_change`` and the buy-in price:

       notional_redeemed       = notional_change * position_at_txn_date
       price_appreciation_lcl  = cash_received - notional_redeemed * buy_in_price_lcl / 100
       gl_target_currency      = cash_received * fx_rate_exit
                                 - notional_redeemed * buy_in_price_target / 100

2. Bond sell G/L branch (``services/realized.py`` lines ~884-900), hit when a
   bond (``asset.is_bond``) is disposed via a Sell that reduces an open long.
   Requires ``BondMetadata`` because it calls ``asset.get_effective_notional``:

       price_appreciation_lcl = notional_at_sell * (price - buy_in_price_lcl)
                                * (-quantity) / 100
       gl_target_currency     = notional_at_sell * (price * fx_rate_exit
                                - buy_in_price_target) * (-quantity) / 100

All numeric values are ``Decimal`` and every assertion is an explicit expected
value (these assertions are the regression contract).

Note on the redemption fixture: ``realized_gain_loss`` only iterates
transactions with ``quantity__isnull=False``, so the redemption transaction
must carry a non-null quantity (``Decimal("0")`` = "no position change", the
documented partial-redemption shape). ``calculate_buy_in_price`` walks the
same queryset and dereferences ``transaction.price`` without a null guard, so
the redemption must also carry a non-null price (``Decimal("100")`` = par).
With ``quantity == 0`` neither field affects the weighted-average basis.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from common.models import Assets, BondMetadata, FX, Transactions
from constants import (
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_BOND_REDEMPTION,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_SELL,
)
from services.realized import realized_gain_loss


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_bond(user, currency="USD", isin="USBONDTEST1", name="Test Bond"):
    """Create a bond Asset of the given currency and link it to the investor."""
    bond = Assets.objects.create(
        type="Bond",
        ISIN=isin,
        name=name,
        currency=currency,
        exposure="Fixed Income",
    )
    bond.investors.add(user)
    return bond


def _make_bond_metadata(bond, initial_notional=Decimal("1000"), nominal_currency=None):
    """Create BondMetadata. Non-amortizing, so get_effective_notional is a flat par."""
    return BondMetadata.objects.create(
        asset=bond,
        initial_notional=initial_notional,
        nominal_currency=nominal_currency or bond.currency,
        is_amortizing=False,
    )


# ---------------------------------------------------------------------------
# Bond redemption G/L (services/realized.py ~lines 670-742)
# ---------------------------------------------------------------------------


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestBondRedemptionGainLoss:
    """Cover the bond redemption branch of realized_gain_loss."""

    def test_redemption_at_par_after_buy_at_par_is_zero(self, user, account):
        """Bond bought at 100% and redeemed at par realizes zero gain."""
        bond = _make_bond(user)
        _make_bond_metadata(bond, initial_notional=Decimal("1000"))

        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2023, 1, 15, 12, 0, 0),
            quantity=Decimal("100"),
            price=Decimal("100"),  # bought at par
        )
        # Full redemption at par: 100 bonds * 1000 notional = 100,000 cash
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="USD",
            type=TRANSACTION_TYPE_BOND_MATURITY,
            date=datetime(2023, 6, 15, 12, 0, 0),
            quantity=Decimal("0"),
            price=Decimal("100"),  # par; quantity 0 => no effect on basis
            cash_flow=Decimal("100000"),
            notional_change=Decimal("1000"),
        )

        result = realized_gain_loss(bond, date(2023, 7, 16), investor=user)

        assert result["all_time"]["total"] == Decimal("0")
        assert result["all_time"]["price_appreciation"] == Decimal("0")
        assert result["all_time"]["fx_effect"] == Decimal("0")

    def test_redemption_at_par_after_buy_at_discount(self, user, account):
        """Bond bought at 95%, redeemed at par: gain = notional*(100-95)/100*position."""
        bond = _make_bond(user)
        _make_bond_metadata(bond, initial_notional=Decimal("1000"))

        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2023, 1, 15, 12, 0, 0),
            quantity=Decimal("100"),
            price=Decimal("95"),
        )
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="USD",
            type=TRANSACTION_TYPE_BOND_REDEMPTION,
            date=datetime(2023, 6, 15, 12, 0, 0),
            quantity=Decimal("0"),
            price=Decimal("100"),
            cash_flow=Decimal("100000"),
            notional_change=Decimal("1000"),
        )

        result = realized_gain_loss(bond, date(2023, 7, 16), investor=user)

        # notional_redeemed = 1000 * 100 = 100,000
        # price_appreciation_lcl = 100,000 - 100,000 * 95/100 = 5,000
        expected_gain = (
            Decimal("1000")
            * (Decimal("100") - Decimal("95"))
            / Decimal("100")
            * Decimal("100")
        )
        assert result["all_time"]["total"] == expected_gain
        assert result["all_time"]["price_appreciation"] == expected_gain
        assert result["all_time"]["fx_effect"] == Decimal("0")

    def test_redemption_at_par_after_buy_at_premium(self, user, account):
        """Bond bought at 105%, redeemed at par: loss = notional*(100-105)/100*position."""
        bond = _make_bond(user)
        _make_bond_metadata(bond, initial_notional=Decimal("1000"))

        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2023, 1, 15, 12, 0, 0),
            quantity=Decimal("100"),
            price=Decimal("105"),
        )
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="USD",
            type=TRANSACTION_TYPE_BOND_REDEMPTION,
            date=datetime(2023, 6, 15, 12, 0, 0),
            quantity=Decimal("0"),
            price=Decimal("100"),
            cash_flow=Decimal("100000"),
            notional_change=Decimal("1000"),
        )

        result = realized_gain_loss(bond, date(2023, 7, 16), investor=user)

        expected_loss = (
            Decimal("1000")
            * (Decimal("100") - Decimal("105"))
            / Decimal("100")
            * Decimal("100")
        )
        assert result["all_time"]["total"] == expected_loss
        assert result["all_time"]["price_appreciation"] == expected_loss
        assert result["all_time"]["fx_effect"] == Decimal("0")

    def test_redemption_with_fx_conversion(self, user, account):
        """EUR bond redeemed at par, reported in USD: explicit non-zero FX effect.

        FX convention: ``USDEUR=x`` means x USD per 1 EUR, so
        ``get_rate("EUR", "USD")`` returns x.
        """
        # 1.1 USD per EUR at the buy date, 1.2 USD per EUR at the redemption date
        FX.objects.create(date=date(2023, 1, 1), from_currency="USD", to_currency="EUR", rate=Decimal("1.1"))
        FX.objects.create(date=date(2023, 6, 1), from_currency="USD", to_currency="EUR", rate=Decimal("1.2"))

        bond = _make_bond(user, currency="EUR", isin="EUBONDTEST1", name="EUR Bond")
        _make_bond_metadata(
            bond, initial_notional=Decimal("1000"), nominal_currency="EUR"
        )

        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="EUR",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2023, 1, 15, 12, 0, 0),
            quantity=Decimal("100"),
            price=Decimal("95"),
        )
        # Redemption at par: 100 bonds * 1000 = 100,000 EUR cash
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="EUR",
            type=TRANSACTION_TYPE_BOND_MATURITY,
            date=datetime(2023, 6, 15, 12, 0, 0),
            quantity=Decimal("0"),
            price=Decimal("100"),
            cash_flow=Decimal("100000"),
            notional_change=Decimal("1000"),
        )

        result = realized_gain_loss(
            bond, date(2023, 7, 16), investor=user, currency="USD"
        )

        # notional_redeemed        = 1000 * 100 = 100,000 EUR
        # buy_in_price_lcl (EUR)   = 95
        # buy_in_price_tgt (USD)   = 95 * 1.1 = 104.5  (FX-converted at buy date)
        # fx_rate_exit (EUR->USD)  = 1.2              (at redemption date)
        # price_appreciation_lcl   = 100,000 - 100,000 * 95/100 = 5,000 EUR
        # price_appreciation       = 5,000 * 1.2 = 6,000 USD
        # gl_target_currency       = 100,000 * 1.2 - 100,000 * 104.5/100
        #                            = 120,000 - 104,500 = 15,500 USD
        # fx_effect                = 15,500 - 6,000 = 9,500 USD
        assert result["all_time"]["total"] == Decimal("15500")
        assert result["all_time"]["price_appreciation"] == Decimal("6000")
        assert result["all_time"]["fx_effect"] == Decimal("9500")


# ---------------------------------------------------------------------------
# Bond sell G/L (services/realized.py ~lines 884-900)
# ---------------------------------------------------------------------------


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.gain_loss
class TestBondSellGainLoss:
    """Cover the bond sell branch of realized_gain_loss."""

    def test_bond_sell_profit(self, user, account):
        """Bond bought at 95%, sold at 98%: gain = notional*(98-95)/100*quantity."""
        bond = _make_bond(user)
        _make_bond_metadata(bond, initial_notional=Decimal("1000"))

        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2023, 1, 15, 12, 0, 0),
            quantity=Decimal("100"),
            price=Decimal("95"),
        )
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="USD",
            type=TRANSACTION_TYPE_SELL,
            date=datetime(2023, 6, 15, 12, 0, 0),
            quantity=Decimal("-100"),
            price=Decimal("98"),
        )

        result = realized_gain_loss(bond, date(2023, 7, 16), investor=user)

        # notional_at_sell = 1000
        # price_appreciation_lcl = 1000 * (98 - 95) * (-(-100)) / 100 = 3,000
        expected_gain = (
            Decimal("1000")
            * (Decimal("98") - Decimal("95"))
            / Decimal("100")
            * Decimal("100")
        )
        assert result["all_time"]["total"] == expected_gain
        assert result["all_time"]["price_appreciation"] == expected_gain
        assert result["all_time"]["fx_effect"] == Decimal("0")

    def test_bond_sell_with_fx_conversion(self, user, account):
        """EUR bond sold, reported in USD: explicit non-zero FX effect."""
        FX.objects.create(date=date(2023, 1, 1), from_currency="USD", to_currency="EUR", rate=Decimal("1.1"))
        FX.objects.create(date=date(2023, 6, 1), from_currency="USD", to_currency="EUR", rate=Decimal("1.2"))

        bond = _make_bond(
            user, currency="EUR", isin="EUBONDTEST2", name="EUR Bond Sell"
        )
        _make_bond_metadata(
            bond, initial_notional=Decimal("1000"), nominal_currency="EUR"
        )

        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="EUR",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2023, 1, 15, 12, 0, 0),
            quantity=Decimal("100"),
            price=Decimal("95"),
        )
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            currency="EUR",
            type=TRANSACTION_TYPE_SELL,
            date=datetime(2023, 6, 15, 12, 0, 0),
            quantity=Decimal("-100"),
            price=Decimal("98"),
        )

        result = realized_gain_loss(
            bond, date(2023, 7, 16), investor=user, currency="USD"
        )

        # notional_at_sell (EUR)    = 1000
        # buy_in_price_lcl (EUR)    = 95
        # buy_in_price_tgt (USD)    = 95 * 1.1 = 104.5
        # fx_rate_exit (EUR->USD)   = 1.2
        # price_appreciation_lcl    = 1000 * (98-95) * 100/100 = 3,000 EUR
        # price_appreciation        = 3,000 * 1.2 = 3,600 USD
        # gl_target_currency        = 1000 * (98*1.2 - 104.5) * 100/100
        #                             = 1000 * (117.6 - 104.5) = 13,100 USD
        # fx_effect                 = 13,100 - 3,600 = 9,500 USD
        assert result["all_time"]["total"] == Decimal("13100")
        assert result["all_time"]["price_appreciation"] == Decimal("3600")
        assert result["all_time"]["fx_effect"] == Decimal("9500")
