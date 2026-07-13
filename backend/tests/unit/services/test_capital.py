"""Unit tests for ``services/capital.py``.

These tests target the previously-uncovered branches in
``get_capital_distribution`` (FX-converted crypto rewards, ACI
account/date filtering, tax aggregation in both currency modes) and the
entire ``get_commission`` function (no-currency aggregate, FX-converted
sum, account/date filtering, and the empty-transaction early return).

All money values use ``Decimal``.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from common.models import Accounts, Assets, Brokers, FX, Transactions
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_COUPON,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_TAX,
)
from services.capital import get_capital_distribution, get_commission


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def usd_account(user, broker):
    """A USD-denominated unrestricted account."""
    return Accounts.objects.create(broker=broker, name="USD Account")


@pytest.fixture
def rub_account(user):
    """A second account under a RUB-style broker, for filter tests."""
    rub_broker = Brokers.objects.create(investor=user, name="RUB Broker", country="RU")
    return Accounts.objects.create(broker=rub_broker, name="RUB Account")


@pytest.fixture
def stock_asset(user):
    """A plain USD stock."""
    asset = Assets.objects.create(
        type="Stock",
        ISIN="USCAPITAL001",
        name="Capital Test Stock",
        currency="USD",
        exposure="Equity",
    )
    asset.investors.add(user)
    return asset


@pytest.fixture
def bond_asset_capital(user):
    """A RUB-denominated bond."""
    asset = Assets.objects.create(
        type="Bond",
        ISIN="RUCAPBOND001",
        name="Capital Test Bond",
        currency="RUB",
        exposure="Fixed Income",
    )
    asset.investors.add(user)
    return asset


@pytest.fixture
def crypto_asset_capital(user):
    """A USD-denominated crypto asset."""
    asset = Assets.objects.create(
        type=ASSET_TYPE_CRYPTO,
        ISIN="CRYPTO:CAPETH",
        name="Capital Test ETH",
        ticker="ETH",
        currency="USD",
        exposure="Commodity",
    )
    asset.investors.add(user)
    return asset


@pytest.fixture
def rub_usd_fx(user):
    """A single RUBUSD FX row (75 RUB per 1 USD)."""
    fx = FX.objects.create(date=date(2024, 6, 1), RUBUSD=Decimal("75"))
    fx.investors.add(user)
    return fx


# ===========================================================================
# get_capital_distribution
# ===========================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestGetCapitalDistributionCryptoFx:
    """Cover FX-conversion branch of crypto rewards (lines 102-108)."""

    def test_crypto_reward_fx_converted_into_target_currency(
        self, user, crypto_asset_capital, usd_account, rub_usd_fx
    ):
        """A USD crypto reward converted into RUB uses the FX rate."""
        # Crypto reward denominated in USD; ask for RUB result.
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=crypto_asset_capital,
            currency="USD",
            type=TRANSACTION_TYPE_CRYPTO_REWARD,
            date=datetime(2024, 6, 1, 12, 0),
            quantity=Decimal("2.000000000"),
            price=Decimal("50.000000000"),  # reward value = 100 USD
        )

        result = get_capital_distribution(
            crypto_asset_capital,
            date(2024, 6, 2),
            user,
            currency="RUB",
            account_ids=[usd_account.id],
        )

        # 100 USD * 75 RUB/USD = 7500 RUB
        assert result == Decimal("7500.00")

    def test_crypto_reward_skipped_when_fx_rate_is_none(
        self, user, crypto_asset_capital, usd_account
    ):
        """If ``get_rate`` returns a falsy FX, the reward is skipped (line 107)."""
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=crypto_asset_capital,
            currency="USD",
            type=TRANSACTION_TYPE_CRYPTO_REWARD,
            date=datetime(2024, 6, 1, 12, 0),
            quantity=Decimal("2.000000000"),
            price=Decimal("50.000000000"),
        )

        with patch("services.capital._fx_get_rate", return_value={"FX": None}):
            result = get_capital_distribution(
                crypto_asset_capital,
                date(2024, 6, 2),
                user,
                currency="RUB",
                account_ids=[usd_account.id],
            )

        # No distributions because the only reward was skipped.
        assert result == Decimal("0.00")


@pytest.mark.unit
@pytest.mark.django_db
class TestGetCapitalDistributionBondAciFilters:
    """Cover the account_ids / start_date filter lines for ACI (120, 123)."""

    def test_aci_filter_by_account_ids_excludes_other_account(
        self, user, bond_asset_capital, rub_usd_fx, broker
    ):
        """ACI on a transaction in a non-selected account is excluded."""
        included = Accounts.objects.create(broker=broker, name="Bond Acct A")
        excluded = Accounts.objects.create(broker=broker, name="Bond Acct B")

        # Buy in the *included* account with negative ACI (-40 RUB).
        Transactions.objects.create(
            investor=user,
            account=included,
            security=bond_asset_capital,
            currency="RUB",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 2, 1, 12, 0),
            quantity=Decimal("10"),
            price=Decimal("100.0"),
            aci=Decimal("-40.00"),
        )
        # Buy in the *excluded* account with negative ACI (-1000 RUB) — must be ignored.
        Transactions.objects.create(
            investor=user,
            account=excluded,
            security=bond_asset_capital,
            currency="RUB",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 2, 1, 12, 0),
            quantity=Decimal("10"),
            price=Decimal("100.0"),
            aci=Decimal("-1000.00"),
        )

        result = get_capital_distribution(
            bond_asset_capital,
            date(2024, 6, 2),
            user,
            account_ids=[included.id],
        )

        # Only the included account's ACI (-40) contributes.
        assert result == Decimal("-40.00")

    def test_aci_filter_by_start_date_excludes_earlier_transactions(
        self, user, bond_asset_capital, rub_usd_fx, broker
    ):
        """ACI before ``start_date`` is excluded (line 123 path)."""
        account = Accounts.objects.create(broker=broker, name="Bond Acct Date")

        # Buy before the start_date window with negative ACI.
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_capital,
            currency="RUB",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 1, 5, 12, 0),
            quantity=Decimal("10"),
            price=Decimal("100.0"),
            aci=Decimal("-25.00"),
        )
        # Sell inside the window with positive ACI.
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_capital,
            currency="RUB",
            type=TRANSACTION_TYPE_SELL,
            date=datetime(2024, 5, 10, 12, 0),
            quantity=Decimal("-5"),
            price=Decimal("101.0"),
            aci=Decimal("15.00"),
        )

        result = get_capital_distribution(
            bond_asset_capital,
            date(2024, 6, 2),
            user,
            start_date=date(2024, 3, 1),
        )

        # Only the within-window sell ACI (+15) counts.
        assert result == Decimal("15.00")

    def test_aci_fx_converted_when_target_currency_given(
        self, user, bond_asset_capital, rub_usd_fx, broker
    ):
        """ACI legs are FX-converted when a target currency is requested (lines 132-137)."""  # noqa: E501
        account = Accounts.objects.create(broker=broker, name="Bond FX Acct")

        # Buy with negative ACI (-75 RUB) and sell with positive ACI (+150 RUB).
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_capital,
            currency="RUB",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 6, 1, 12, 0),
            quantity=Decimal("10"),
            price=Decimal("100.0"),
            aci=Decimal("-75.00"),
        )
        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_capital,
            currency="RUB",
            type=TRANSACTION_TYPE_SELL,
            date=datetime(2024, 6, 1, 12, 0),
            quantity=Decimal("-5"),
            price=Decimal("101.0"),
            aci=Decimal("150.00"),
        )

        # Net ACI in RUB = -75 + 150 = 75 RUB -> 75 / 75 = 1.00 USD
        result = get_capital_distribution(
            bond_asset_capital, date(2024, 6, 2), user, currency="USD"
        )
        assert result == Decimal("1.00")


@pytest.mark.unit
@pytest.mark.django_db
class TestGetCapitalDistributionTax:
    """Cover tax aggregation in both currency modes (lines 150-160)."""

    def test_tax_aggregated_in_native_currency_no_conversion(
        self, user, stock_asset, usd_account
    ):
        """Taxes subtract from distributions when currency is None (aggregate path)."""
        # Dividend pays +200.
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type="Dividend",
            date=datetime(2024, 4, 1, 12, 0),
            cash_flow=Decimal("200.00"),
        )
        # Tax of -30 (reduces net distribution).
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_TAX,
            date=datetime(2024, 4, 2, 12, 0),
            cash_flow=Decimal("-30.00"),
        )

        result = get_capital_distribution(stock_asset, date(2024, 6, 2), user)

        # 200 (dividend) + (-30) (tax) = 170
        assert result == Decimal("170.00")

    def test_tax_fx_converted_when_target_currency_given(
        self, user, stock_asset, usd_account, rub_usd_fx
    ):
        """Taxes are FX-converted when a target currency is supplied (line 158-160)."""
        # Dividend 200 USD.
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type="Dividend",
            date=datetime(2024, 6, 1, 12, 0),
            cash_flow=Decimal("200.00"),
        )
        # Tax -30 USD.
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_TAX,
            date=datetime(2024, 6, 1, 12, 0),
            cash_flow=Decimal("-30.00"),
        )

        result = get_capital_distribution(
            stock_asset, date(2024, 6, 2), user, currency="RUB"
        )

        # Net USD = 170 -> * 75 = 12750 RUB
        assert result == Decimal("12750.00")

    def test_tax_filter_by_account_and_start_date(
        self, user, stock_asset, rub_usd_fx, broker
    ):
        """Tax filtering by account_ids and start_date both apply."""
        included = Accounts.objects.create(broker=broker, name="Tax Acct In")
        excluded = Accounts.objects.create(broker=broker, name="Tax Acct Out")

        # Dividend in included account.
        Transactions.objects.create(
            investor=user,
            account=included,
            security=stock_asset,
            currency="USD",
            type="Dividend",
            date=datetime(2024, 5, 15, 12, 0),
            cash_flow=Decimal("100.00"),
        )
        # Tax in included account, within window.
        Transactions.objects.create(
            investor=user,
            account=included,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_TAX,
            date=datetime(2024, 5, 16, 12, 0),
            cash_flow=Decimal("-10.00"),
        )
        # Tax in *excluded* account — must not be counted.
        Transactions.objects.create(
            investor=user,
            account=excluded,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_TAX,
            date=datetime(2024, 5, 16, 12, 0),
            cash_flow=Decimal("-999.00"),
        )
        # Tax in included account but *before* the window — must not be counted.
        Transactions.objects.create(
            investor=user,
            account=included,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_TAX,
            date=datetime(2024, 1, 1, 12, 0),
            cash_flow=Decimal("-888.00"),
        )

        result = get_capital_distribution(
            stock_asset,
            date(2024, 6, 2),
            user,
            account_ids=[included.id],
            start_date=date(2024, 3, 1),
        )

        # 100 dividend + (-10) tax = 90
        assert result == Decimal("90.00")


@pytest.mark.unit
@pytest.mark.django_db
class TestGetCapitalDistributionDividendFxAndFilters:
    """Cover dividend/coupon FX conversion + filter branches (lines 82-86)."""

    def test_dividend_fx_converted(self, user, stock_asset, usd_account, rub_usd_fx):
        """Dividends are FX-converted when a target currency is requested."""
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type="Dividend",
            date=datetime(2024, 6, 1, 12, 0),
            cash_flow=Decimal("4.00"),
        )

        result = get_capital_distribution(
            stock_asset, date(2024, 6, 2), user, currency="RUB"
        )

        # 4 USD * 75 = 300 RUB
        assert result == Decimal("300.00")

    def test_coupon_fx_converted_for_bond(
        self, user, bond_asset_capital, rub_usd_fx, broker
    ):
        """Coupons on bonds FX-convert correctly (uses transaction.date for rate)."""
        account = Accounts.objects.create(broker=broker, name="Coupon Acct")

        Transactions.objects.create(
            investor=user,
            account=account,
            security=bond_asset_capital,
            currency="RUB",
            type=TRANSACTION_TYPE_COUPON,
            date=datetime(2024, 6, 1, 12, 0),
            cash_flow=Decimal("150.00"),
        )

        # Convert RUB -> USD: 150 / 75 = 2.00
        result = get_capital_distribution(
            bond_asset_capital, date(2024, 6, 2), user, currency="USD"
        )
        assert result == Decimal("2.00")


# ===========================================================================
# get_commission
# ===========================================================================


@pytest.mark.unit
@pytest.mark.django_db
class TestGetCommission:
    """Cover the entire ``get_commission`` function (lines 170-199)."""

    def test_no_transactions_returns_zero(self, user, stock_asset):
        """Empty transaction set returns Decimal(0) (the else branch, line 199)."""
        result = get_commission(stock_asset, date(2024, 6, 2), user)
        assert result == Decimal("0")

    def test_commission_aggregated_no_currency_conversion(
        self, user, stock_asset, usd_account
    ):
        """Commissions sum directly when currency is None (line 188-191)."""
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 3, 1, 12, 0),
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("-5.00"),
        )
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_SELL,
            date=datetime(2024, 4, 1, 12, 0),
            quantity=Decimal("-10"),
            price=Decimal("110"),
            commission=Decimal("-7.00"),
        )

        result = get_commission(stock_asset, date(2024, 6, 2), user)
        assert result == Decimal("-12.00")

    def test_commission_fx_converted(
        self, user, stock_asset, usd_account, rub_usd_fx
    ):
        """Commissions are FX-converted when target currency supplied (line 193-196)."""
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 6, 1, 12, 0),
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("-2.00"),
        )

        result = get_commission(stock_asset, date(2024, 6, 2), user, currency="RUB")
        # -2 USD * 75 RUB/USD = -150 RUB
        assert result == Decimal("-150.00")

    def test_commission_filtered_by_account_ids(
        self, user, stock_asset, rub_usd_fx, broker
    ):
        """Only commissions in selected accounts are summed (line 178-179)."""
        included = Accounts.objects.create(broker=broker, name="Comm In")
        excluded = Accounts.objects.create(broker=broker, name="Comm Out")

        Transactions.objects.create(
            investor=user,
            account=included,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 6, 1, 12, 0),
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("-3.00"),
        )
        Transactions.objects.create(
            investor=user,
            account=excluded,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 6, 1, 12, 0),
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("-999.00"),
        )

        result = get_commission(
            stock_asset, date(2024, 6, 2), user, account_ids=[included.id]
        )
        assert result == Decimal("-3.00")

    def test_commission_filtered_by_start_date(
        self, user, stock_asset, rub_usd_fx, usd_account
    ):
        """Commissions before ``start_date`` are excluded (line 181-185)."""
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 1, 5, 12, 0),  # before window
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("-100.00"),
        )
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 5, 1, 12, 0),  # inside window
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("-8.00"),
        )

        result = get_commission(
            stock_asset, date(2024, 6, 2), user, start_date=date(2024, 3, 1)
        )
        assert result == Decimal("-8.00")

    def test_commission_skips_null_commission_transactions(
        self, user, stock_asset, rub_usd_fx, usd_account
    ):
        """Transactions with commission=NULL are excluded via the isnull filter."""
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 6, 1, 12, 0),
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=None,  # should be excluded
        )
        Transactions.objects.create(
            investor=user,
            account=usd_account,
            security=stock_asset,
            currency="USD",
            type=TRANSACTION_TYPE_BUY,
            date=datetime(2024, 6, 1, 12, 0),
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("-4.00"),
        )

        result = get_commission(stock_asset, date(2024, 6, 2), user)
        assert result == Decimal("-4.00")
