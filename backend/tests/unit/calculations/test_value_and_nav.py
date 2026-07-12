"""
Characterization tests for Assets.calculate_value_at_date and core.portfolio_utils.NAV_at_date.

These tests document CURRENT (pre-extraction) behavior of the value/NAV
calculation paths so that the upcoming service-layer extraction has a
regression contract. They assert exactly what the code returns today,
including any surprising edge-case behavior (e.g. returning Decimal(0)
where one might expect None), which is called out in inline comments.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from common.models import (
    FX,
    Accounts,
    Assets,
    BondMetadata,
    Brokers,
    Prices,
    Transactions,
)
from core.portfolio_utils import NAV_at_date


# ===========================================================================
# calculate_value_at_date
# ===========================================================================


@pytest.mark.nav
@pytest.mark.unit
class TestCalculateValueAtDate:
    """Characterization tests for Assets.calculate_value_at_date."""

    def test_simple_position_value(self, user, account, asset):
        """100 shares at price $55 -> value $5500."""
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("55.00"),
            commission=Decimal("0"),
        )
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("55.00")
        )

        value = asset.calculate_value_at_date(date(2023, 6, 15), investor=user)

        assert value == Decimal("5500.00")

    def test_zero_position_no_transactions_returns_zero(self, user, account, asset):
        """Asset with NO transactions has position 0 -> value Decimal(0).

        Note: calculate_value_at_date short-circuits on position==0 BEFORE
        ever querying a price, so it returns Decimal(0) rather than None.
        """
        # No transactions, no prices - still returns Decimal(0)
        value = asset.calculate_value_at_date(date(2023, 6, 15), investor=user)

        assert value == Decimal(0)

    def test_zero_position_closed_returns_zero(self, user, account, asset):
        """Position fully closed (buy then sell) -> value Decimal(0)."""
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("0"),
        )
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 2, 15),
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            commission=Decimal("0"),
        )
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("55.00")
        )

        value = asset.calculate_value_at_date(date(2023, 6, 15), investor=user)

        assert value == Decimal(0)

    def test_missing_price_falls_back_to_transaction_price(
        self, user, account, asset
    ):
        """No Prices row, but a Buy transaction exists -> value uses tx price.

        Characterization: price_at_date falls back to the last transaction's
        price when no Prices quote is found, so calculate_value_at_date returns
        position * transaction_price (NOT Decimal(0)).
        """
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("0"),
        )
        # Deliberately create NO Prices row

        value = asset.calculate_value_at_date(date(2023, 6, 15), investor=user)

        # Falls back to the Buy transaction price of 50.00
        assert value == Decimal("5000.000000000000000")

    def test_bond_value_position_price_notional(self, user, account, bond_asset):
        """Bond: 5 bonds, price 99%, notional 1000 -> 5 * 99 * 1000 / 100 = 4950.

        Bond value formula: position * price% * notional / 100.
        """
        BondMetadata.objects.create(
            asset=bond_asset,
            initial_notional=Decimal("1000"),
            nominal_currency="USD",
            coupon_rate=Decimal("5"),
            coupon_frequency=1,
            issue_date=date(2023, 1, 1),
            maturity_date=date(2030, 1, 1),
            bond_type="FIXED",
        )
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("5"),
            price=Decimal("99"),
            commission=Decimal("0"),
        )
        Prices.objects.create(
            date=date(2023, 6, 15), security=bond_asset, price=Decimal("99")
        )

        value = bond_asset.calculate_value_at_date(date(2023, 6, 15), investor=user)

        # 5 * 99 * 1000 / 100 = 4950
        assert value == Decimal("4950.000")

    def test_multi_currency_fx_conversion(
        self, user, account, asset_eur, fx_rates_multi_currency
    ):
        """EUR asset valued in USD: position * price * FX(EUR->USD).

        Uses fx_rates_multi_currency fixture: first monthly entry at
        2023-01-01 has USDEUR=1.1 (1.1 USD per 1 EUR). price_at_date looks
        up the latest FX on/before the date, so we use a date within that
        rate grid.
        """
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset_eur,
            currency="EUR",
            type="Buy",
            date=date(2023, 1, 2),
            quantity=Decimal("100"),
            price=Decimal("40.00"),
            commission=Decimal("0"),
        )
        Prices.objects.create(
            date=date(2023, 1, 2), security=asset_eur, price=Decimal("40.00")
        )

        # Value in USD: 100 * 40 * FX(EUR->USD on 2023-01-02)
        expected_fx = FX.get_rate("EUR", "USD", date(2023, 1, 2))["FX"]
        expected = Decimal("100") * Decimal("40.00") * expected_fx

        value = asset_eur.calculate_value_at_date(
            date(2023, 1, 2), investor=user, currency="USD"
        )

        assert value == expected

    def test_account_ids_filter(self, user, broker, asset):
        """account_ids restricts which transactions contribute to position."""
        acct_a = Accounts.objects.create(broker=broker, name="Acct A")
        acct_b = Accounts.objects.create(broker=broker, name="Acct B")

        Transactions.objects.create(
            investor=user,
            account=acct_a,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("55.00"),
            commission=Decimal("0"),
        )
        Transactions.objects.create(
            investor=user,
            account=acct_b,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("50"),
            price=Decimal("55.00"),
            commission=Decimal("0"),
        )
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("55.00")
        )

        value_a = asset.calculate_value_at_date(
            date(2023, 6, 15), investor=user, account_ids=[acct_a.id]
        )
        value_b = asset.calculate_value_at_date(
            date(2023, 6, 15), investor=user, account_ids=[acct_b.id]
        )

        assert value_a == Decimal("5500.00")  # 100 * 55
        assert value_b == Decimal("2750.00")  # 50 * 55


# ===========================================================================
# NAV_at_date
# ===========================================================================


@pytest.mark.nav
@pytest.mark.unit
class TestNAVAtDate:
    """Characterization tests for core.portfolio_utils.NAV_at_date."""

    def test_empty_portfolio_returns_zero(self, user, broker):
        """No assets, no accounts with transactions -> NAV Decimal(0)."""
        account = Accounts.objects.create(broker=broker, name="Empty Account")
        result = NAV_at_date(
            user_id=user.id,
            account_ids=(account.id,),
            date=date(2023, 6, 15),
            target_currency="USD",
        )

        assert result["Total NAV"] == Decimal(0)

    def test_single_asset_with_cash(self, user, broker, asset):
        """Single asset + cash balance: NAV = asset value + cash."""
        account = Accounts.objects.create(broker=broker, name="NAV Account")

        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("55.00"),
            cash_flow=Decimal("-5500.00"),
            commission=Decimal("0"),
        )
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("60.00")
        )

        result = NAV_at_date(
            user_id=user.id,
            account_ids=(account.id,),
            date=date(2023, 6, 15),
            target_currency="USD",
        )

        # Asset value: 100 * 60 = 6000; Cash: -5500 -> NAV = 500
        asset_value = Decimal("100") * Decimal("60.00")
        cash = Decimal("-5500.00")
        expected = asset_value + cash

        assert result["Total NAV"] == expected

    def test_multi_currency_nav(
        self, multi_currency_user, broker, asset_eur, asset_gbp, fx_rates_multi_currency
    ):
        """Multi-currency NAV: EUR + GBP assets valued in USD via FX.

        Purchase price equals current price, so asset value is exactly offset
        by the inferred cash outflow and Total NAV nets to ~0. We assert the
        per-asset-class breakdown to verify the FX conversion itself.

        Note: NAV_at_date filters portfolio by investors__id, so the acting
        user must be added to each asset's investors (the asset_eur/asset_gbp
        fixtures only add the default ``user``).
        """
        asset_eur.investors.add(multi_currency_user)
        asset_gbp.investors.add(multi_currency_user)
        # Broker must belong to multi_currency_user for NAV_at_date's
        # Accounts.objects.filter(broker__investor__id=user_id) to match.
        broker = Brokers.objects.create(
            investor=multi_currency_user, name="MC Broker", country="US"
        )
        account = Accounts.objects.create(broker=broker, name="Multi Account")

        Transactions.objects.create(
            investor=multi_currency_user,
            account=account,
            security=asset_eur,
            currency="EUR",
            type="Buy",
            date=date(2023, 1, 2),
            quantity=Decimal("100"),
            price=Decimal("40.00"),
            commission=Decimal("0"),
        )
        Transactions.objects.create(
            investor=multi_currency_user,
            account=account,
            security=asset_gbp,
            currency="GBP",
            type="Buy",
            date=date(2023, 1, 2),
            quantity=Decimal("100"),
            price=Decimal("30.00"),
            commission=Decimal("0"),
        )
        Prices.objects.create(
            date=date(2023, 1, 2), security=asset_eur, price=Decimal("40.00")
        )
        Prices.objects.create(
            date=date(2023, 1, 2), security=asset_gbp, price=Decimal("30.00")
        )

        valuation_date = date(2023, 1, 2)
        result = NAV_at_date(
            user_id=multi_currency_user.id,
            account_ids=(account.id,),
            date=valuation_date,
            target_currency="USD",
            breakdown=("asset_type",),
        )

        # Asset values converted to USD: 100*40*1.1 + 100*30*1.22 = 8060
        eur_value_usd = (
            Decimal("100") * Decimal("40.00") * FX.get_rate("EUR", "USD", valuation_date)["FX"]
        )
        gbp_value_usd = (
            Decimal("100") * Decimal("30.00") * FX.get_rate("GBP", "USD", valuation_date)["FX"]
        )

        assert result["asset_type"]["Stock"] == eur_value_usd + gbp_value_usd
        # Cash outflow in USD offsets asset value -> NAV ~ 0
        assert abs(result["Total NAV"]) < Decimal("0.01")

    def test_multi_currency_nav_price_appreciation(
        self, multi_currency_user, broker, asset_eur, asset_gbp, fx_rates_multi_currency
    ):
        """Multi-currency NAV with price gain: NAV = (asset - cost) converted.

        Buy at one price, value at a higher price; the unrealized gain shows
        up as positive Total NAV (cash outflow is at cost, asset valued at
        market).

        Note: NAV_at_date filters portfolio by investors__id, so the acting
        user must be added to each asset's investors.
        """
        asset_eur.investors.add(multi_currency_user)
        # Broker must belong to multi_currency_user for NAV_at_date's
        # Accounts.objects.filter(broker__investor__id=user_id) to match.
        broker = Brokers.objects.create(
            investor=multi_currency_user, name="MC Broker", country="US"
        )
        account = Accounts.objects.create(broker=broker, name="Gain Account")

        Transactions.objects.create(
            investor=multi_currency_user,
            account=account,
            security=asset_eur,
            currency="EUR",
            type="Buy",
            date=date(2023, 1, 2),
            quantity=Decimal("100"),
            price=Decimal("40.00"),
            commission=Decimal("0"),
        )
        # Current price higher than cost
        Prices.objects.create(
            date=date(2023, 1, 2), security=asset_eur, price=Decimal("50.00")
        )

        valuation_date = date(2023, 1, 2)
        result = NAV_at_date(
            user_id=multi_currency_user.id,
            account_ids=(account.id,),
            date=valuation_date,
            target_currency="USD",
        )

        # Asset: 100 * 50 * FX(EUR->USD); Cash: -(100 * 40) * FX(EUR->USD)
        fx = FX.get_rate("EUR", "USD", valuation_date)["FX"]
        asset_value = Decimal("100") * Decimal("50.00") * fx
        cash = Decimal("-100") * Decimal("40.00") * fx
        expected = asset_value + cash

        assert result["Total NAV"] == expected

    def test_nav_breakdown_by_asset_type(self, user, broker, asset):
        """breakdown=('asset_type',) produces a per-type dict keyed by asset.type.

        Characterization: Total NAV nets to ~0 because the inferred cash
        outflow offsets the asset value (purchase price == current price).
        The asset_type breakdown separately reports Stock and Cash.
        """
        account = Accounts.objects.create(broker=broker, name="BD Account")

        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("55.00"),
            commission=Decimal("0"),
        )
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("55.00")
        )

        result = NAV_at_date(
            user_id=user.id,
            account_ids=(account.id,),
            date=date(2023, 6, 15),
            target_currency="USD",
            breakdown=("asset_type",),
        )

        assert result["asset_type"]["Stock"] == Decimal("5500.000000000000")
        assert result["asset_type"]["Cash"] == Decimal("-5500.00")
        # Stock + Cash nets to ~0
        assert abs(result["Total NAV"]) < Decimal("0.01")
