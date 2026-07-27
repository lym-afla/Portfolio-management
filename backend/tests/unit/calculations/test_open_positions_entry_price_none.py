"""Regression tests for open-positions table output when entry_price is None.

Positions built entirely from crypto deposits/transfers/rewards have no
Buy-type transactions, so ``services.realized.calculate_buy_in_price``
correctly returns ``None`` for them. The table-output code in
``core.tables_utils`` must handle that without crashing and must surface
``entry_value=None`` plus ``"N/R"`` for the dependent ratios.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Transactions
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
)
from core.tables_utils import calculate_positions_table_output


@pytest.fixture
def crypto_account(user):
    """Create a crypto broker account."""
    broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    return Accounts.objects.create(broker=broker, name="Unified", native_id="bybit-main")


@pytest.fixture
def btc(user):
    """Create a BTC crypto asset."""
    asset = Assets.objects.create(
        type=ASSET_TYPE_CRYPTO,
        ISIN="CRYPTO:BTC",
        name="Bitcoin",
        ticker="BTC",
        currency="USD",
        exposure="Commodity",
    )
    asset.investors.add(user)
    return asset


@pytest.mark.regression
@pytest.mark.unit
@pytest.mark.django_db
def test_open_positions_table_handles_crypto_position_with_no_cost_basis(
    user, crypto_account, btc
):
    """Crypto held from deposit/reward only must not crash the open-positions table.

    Regression for the TypeError at tables_utils entry_value calculation:
    ``None * Decimal`` when entry_price (buy-in price) is None because the
    position was built entirely from deposits/rewards with no Buy trades.
    """
    # Deposit (external transfer in) -- no cost basis established.
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("0.500000000"),
        price=Decimal("40000.000000000"),
    )
    # Reward -- also no cost basis (reward value is a capital distribution).
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("0.100000000"),
        price=Decimal("45000.000000000"),
    )

    end_date = datetime(2026, 1, 3).date()
    categories = [
        "entry_value",
        "current_value",
        "realized_gl",
        "unrealized_gl",
        "capital_distribution",
        "commission",
    ]

    # Must not raise (the original regression).
    positions, totals = calculate_positions_table_output(
        user_id=user.id,
        assets=[btc],
        end_date=end_date,
        categories=categories,
        use_default_currency=True,
        currency_target="USD",
        selected_account_ids=[crypto_account.id],
        start_date=None,
        is_closed=False,
    )

    assert len(positions) == 1
    position = positions[0]

    # No Buy transactions => no derivable cost basis => None.
    assert position["entry_price"] is None
    assert position["entry_value"] is None

    # Position is the sum of the deposit + reward quantities.
    assert position["current_position"] == Decimal("0.600000000")

    # Ratios that depend on entry_value are not meaningful ("N/R").
    assert position["price_change_percentage"] == "N/R"
    assert position["capital_distribution_percentage"] == "N/R"
    assert position["commission_percentage"] == "N/R"
    assert position["total_return_percentage"] == "N/R"

    # Totals aggregation must not crash on the None entry_value; the position
    # contributes zero to the portfolio entry-value total.
    assert totals.get("entry_value", Decimal(0)) == Decimal(0)
