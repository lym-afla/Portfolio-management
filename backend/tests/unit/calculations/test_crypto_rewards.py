"""Crypto reward calculation regression tests."""

from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Prices, Transactions
from services.positions import position as get_position
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
)
from core.portfolio_utils import IRR, _calculate_cash_flow

from services.realized import (
    calculate_buy_in_price,
    get_economic_basis,
    realized_gain_loss,
    unrealized_gain_loss,
)
from services.capital import get_capital_distribution
from services.accounts import balance as account_balance


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


@pytest.mark.django_db
def test_crypto_reward_increases_position_and_capital_distribution(user, crypto_account, btc):
    """Rewards increase crypto position and distributions without cash balance."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 10, 12, 0),
        quantity=Decimal("0.010000000"),
        price=Decimal("50000.000000000"),
    )

    assert get_position(btc, datetime(2026, 1, 11).date(), user, [crypto_account.id]) == Decimal(
        "0.010000000"
    )
    assert get_capital_distribution(
        btc, datetime(2026, 1, 11).date(), user, "USD", [crypto_account.id]
    ) == Decimal("500.00")
    assert account_balance(crypto_account, datetime(2026, 1, 11).date()) == {}


@pytest.mark.django_db
def test_crypto_reward_does_not_distort_paid_entry_price(user, crypto_account, btc):
    """Rewards affect economic basis but not paid entry price."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("0.100000000"),
        price=Decimal("200.000000000"),
    )

    assert calculate_buy_in_price(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [crypto_account.id]
    ) == Decimal("100.000000")
    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [crypto_account.id]
    ) == Decimal("120.00")


@pytest.mark.django_db
def test_crypto_transfer_out_reduces_economic_basis_for_remaining_lots(user, crypto_account, btc):
    """Transfer out removes proportional basis from current crypto lots."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("0.100000000"),
        price=Decimal("200.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 3, 12, 0),
        quantity=Decimal("-0.250000000"),
        price=Decimal("150.000000000"),
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 4).date(), user, "USD", [crypto_account.id]
    ) == Decimal("92.73")


@pytest.mark.django_db
def test_rewarded_crypto_lot_unrealized_gain_uses_economic_basis(user, crypto_account, btc):
    """Reward value is distribution, not zero-cost unrealized appreciation."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("0.100000000"),
        price=Decimal("200.000000000"),
    )
    Prices.objects.create(
        security=btc,
        date=datetime(2026, 1, 3).date(),
        price=Decimal("200.000000"),
    )

    assert calculate_buy_in_price(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [crypto_account.id]
    ) == Decimal("100.000000")
    assert get_capital_distribution(
        btc, datetime(2026, 1, 3).date(), user, "USD", [crypto_account.id]
    ) == Decimal("20.00")
    unrealized = unrealized_gain_loss(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [crypto_account.id]
    )
    assert unrealized["total"] == Decimal("100.00")


@pytest.mark.django_db
def test_crypto_unrealized_gain_uses_unrounded_current_position(user, crypto_account, btc):
    """Unrealized G/L preserves sub-1e-6 crypto current quantity."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("0.000000500"),
        price=Decimal("100000000.000000000"),
    )
    Prices.objects.create(
        security=btc,
        date=datetime(2026, 1, 2).date(),
        price=Decimal("120000000.000000"),
    )

    unrealized = unrealized_gain_loss(btc, 
        datetime(2026, 1, 2).date(), user, "USD", [crypto_account.id]
    )
    assert unrealized["total"] == Decimal("10.00")


@pytest.mark.django_db
def test_rewarded_crypto_lot_realized_gain_uses_economic_basis(user, crypto_account, btc):
    """Full rewarded crypto disposal realizes proceeds over economic basis."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("0.100000000"),
        price=Decimal("200.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 3, 12, 0),
        quantity=Decimal("-1.100000000"),
        price=Decimal("200.000000000"),
    )

    realized = realized_gain_loss(btc, datetime(2026, 1, 4).date(), user, "USD", [crypto_account.id])
    assert realized["all_time"]["total"] == Decimal("100.00")
    assert get_capital_distribution(
        btc, datetime(2026, 1, 4).date(), user, "USD", [crypto_account.id]
    ) == Decimal("20.00")


@pytest.mark.django_db
def test_crypto_realized_gain_uses_basis_only_up_to_disposal_time(user, crypto_account, btc):
    """Same-day later crypto rows do not affect basis before an earlier sale."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 10, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 1, 11, 0),
        quantity=Decimal("-0.500000000"),
        price=Decimal("200.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("0.500000000"),
        price=Decimal("1000.000000000"),
    )

    realized = realized_gain_loss(btc, datetime(2026, 1, 2).date(), user, "USD", [crypto_account.id])
    assert realized["all_time"]["total"] == Decimal("50.00")


@pytest.mark.django_db
def test_crypto_realized_gain_separates_same_day_round_trips(user, crypto_account, btc):
    """Closed same-day segments do not include later same-day round trips."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 10, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 1, 11, 0),
        quantity=Decimal("-1.000000000"),
        price=Decimal("200.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("1000.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 1, 13, 0),
        quantity=Decimal("-1.000000000"),
        price=Decimal("1100.000000000"),
    )

    realized = realized_gain_loss(btc, datetime(2026, 1, 2).date(), user, "USD", [crypto_account.id])
    assert realized["all_time"]["total"] == Decimal("200.00")


@pytest.mark.django_db
def test_crypto_unrealized_gain_with_start_date_uses_opening_basis(user, crypto_account, btc):
    """Period unrealized G/L keeps basis from lots opened before start_date."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("0.100000000"),
        price=Decimal("200.000000000"),
    )
    Prices.objects.create(
        security=btc,
        date=datetime(2026, 1, 10).date(),
        price=Decimal("200.000000"),
    )

    unrealized = unrealized_gain_loss(btc, 
        datetime(2026, 1, 10).date(),
        user,
        "USD",
        [crypto_account.id],
        start_date=datetime(2026, 1, 5).date(),
    )
    assert unrealized["total"] == Decimal("100.00")


@pytest.mark.django_db
def test_crypto_realized_gain_with_start_date_uses_opening_basis(user, crypto_account, btc):
    """Period realized G/L keeps basis from lots opened before start_date."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("0.100000000"),
        price=Decimal("200.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 10, 12, 0),
        quantity=Decimal("-1.100000000"),
        price=Decimal("200.000000000"),
    )

    realized = realized_gain_loss(btc, 
        datetime(2026, 1, 11).date(),
        user,
        "USD",
        [crypto_account.id],
        start_date=datetime(2026, 1, 5).date(),
    )
    assert realized["all_time"]["total"] == Decimal("100.00")


@pytest.mark.django_db
def test_crypto_realized_gain_start_date_disposal_is_not_current_position(
    user, crypto_account, btc
):
    """A disposal on start_date closes the period position instead of staying current."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 5, 12, 0),
        quantity=Decimal("-1.000000000"),
        price=Decimal("200.000000000"),
    )

    realized = realized_gain_loss(btc, 
        datetime(2026, 1, 6).date(),
        user,
        "USD",
        [crypto_account.id],
        start_date=datetime(2026, 1, 5).date(),
    )
    assert realized["all_time"]["total"] == Decimal("100.00")
    assert realized["current_position"]["total"] == Decimal("0")


@pytest.mark.django_db
def test_crypto_realized_gain_with_start_date_uses_unrounded_opening_position(
    user, crypto_account, btc
):
    """Period realized G/L recognizes sub-1e-6 opening crypto quantity."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("0.000000500"),
        price=Decimal("100000000.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 10, 12, 0),
        quantity=Decimal("-0.000000500"),
        price=Decimal("120000000.000000000"),
    )

    realized = realized_gain_loss(btc, 
        datetime(2026, 1, 11).date(),
        user,
        "USD",
        [crypto_account.id],
        start_date=datetime(2026, 1, 5).date(),
    )
    assert realized["all_time"]["total"] == Decimal("10.00")


@pytest.mark.django_db
def test_crypto_realized_gain_uses_unrounded_economic_basis(user, crypto_account, btc):
    """Internal basis precision avoids losing a cent in realized G/L."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.015000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-1.000000000"),
        price=Decimal("100.021000000"),
    )

    realized = realized_gain_loss(btc, datetime(2026, 1, 3).date(), user, "USD", [crypto_account.id])
    assert get_economic_basis(btc, 
        datetime(2026, 1, 1).date(), user, "USD", [crypto_account.id]
    ) == Decimal("100.02")
    assert realized["all_time"]["total"] == Decimal("0.01")


@pytest.mark.django_db
def test_grouped_internal_transfer_carries_economic_basis(user, crypto_account, btc):
    """Grouped internal transfer-in carries proportional basis from transfer-out."""
    account_b = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    transfer_group = "internal-transfer-1"
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 1),
        quantity=Decimal("0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(),
        user,
        "USD",
        [crypto_account.id, account_b.id],
    ) == Decimal("100.00")
    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [crypto_account.id]
    ) == Decimal("60.00")
    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id]
    ) == Decimal("40.00")


@pytest.mark.django_db
def test_chained_grouped_transfers_preserve_economic_basis(user, crypto_account, btc):
    """Basis carries through chained internal transfer groups."""
    account_b = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    account_c = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Earn",
        native_id="bybit-earn",
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id="g1",
        import_provider="bybit",
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 1),
        quantity=Decimal("0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id="g1",
        import_provider="bybit",
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 3, 12, 0),
        quantity=Decimal("-0.250000000"),
        price=Decimal("100.000000000"),
        import_group_id="g2",
        import_provider="bybit",
    )
    Transactions.objects.create(
        investor=user,
        account=account_c,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 3, 12, 1),
        quantity=Decimal("0.250000000"),
        price=Decimal("100.000000000"),
        import_group_id="g2",
        import_provider="bybit",
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 4).date(),
        user,
        "USD",
        [crypto_account.id, account_b.id, account_c.id],
    ) == Decimal("100.00")
    assert get_economic_basis(btc, 
        datetime(2026, 1, 4).date(), user, "USD", [account_b.id]
    ) == Decimal("15.00")
    assert get_economic_basis(btc, 
        datetime(2026, 1, 4).date(), user, "USD", [account_c.id]
    ) == Decimal("25.00")


@pytest.mark.django_db
def test_grouped_transfer_preserves_sub_micro_crypto_basis(user, crypto_account, btc):
    """Internal transfer source quantity uses 9-decimal precision."""
    account_b = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    transfer_group = "sub-micro-transfer"
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("0.000000500"),
        price=Decimal("100000000.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.000000500"),
        price=Decimal("100000000.000000000"),
        import_group_id=transfer_group,
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 1),
        quantity=Decimal("0.000000500"),
        price=Decimal("100000000.000000000"),
        import_group_id=transfer_group,
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id]
    ) == Decimal("50.00")


@pytest.mark.django_db
def test_grouped_transfer_basis_ignores_other_asset_transactions(user, crypto_account, btc):
    """Internal transfer basis lookup is scoped to the transferred security."""
    eth = Assets.objects.create(
        type=ASSET_TYPE_CRYPTO,
        ISIN="CRYPTO:ETH",
        name="Ethereum",
        ticker="ETH",
        currency="USD",
        exposure="Commodity",
    )
    eth.investors.add(user)
    account_b = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    transfer_group = "btc-transfer-with-other-asset"

    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=eth,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 9, 0),
        quantity=Decimal("10.000000000"),
        price=Decimal("1000.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 1),
        quantity=Decimal("0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id]
    ) == Decimal("40.00")


@pytest.mark.django_db
def test_grouped_transfer_basis_does_not_cross_import_provider(user, crypto_account, btc):
    """Grouped transfer basis is not carried across provider collisions."""
    account_b = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    transfer_group = "shared-provider-collision-group"
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 1),
        quantity=Decimal("0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="okx",
        import_account_id="okx-funding",
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id]
    ) == Decimal("0.00")


@pytest.mark.django_db
def test_grouped_transfer_basis_requires_unambiguous_source_account(user, crypto_account, btc):
    """Ambiguous same-provider/group/account flows do not steal first source basis."""
    account_b = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    account_x = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Subaccount X",
        native_id="bybit-x",
    )
    account_y = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Subaccount Y",
        native_id="bybit-y",
    )
    transfer_group = "shared-account-collision-group"
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 10, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=account_x,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 10, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("1000.000000000"),
        import_provider="bybit",
        import_account_id="bybit-x",
    )
    Transactions.objects.create(
        investor=user,
        account=account_x,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 10, 0),
        quantity=Decimal("-0.400000000"),
        price=Decimal("1000.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-x",
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 11, 0),
        quantity=Decimal("-0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-funding",
    )
    Transactions.objects.create(
        investor=user,
        account=account_y,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 1),
        quantity=Decimal("0.400000000"),
        price=Decimal("1000.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-y",
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id]
    ) == Decimal("0.00")


@pytest.mark.django_db
def test_split_grouped_transfer_allocates_basis_proportionally(user, crypto_account, btc):
    """Split transfer-ins share one source transfer-out basis by quantity."""
    account_b = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    account_c = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Earn",
        native_id="bybit-earn",
    )
    transfer_group = "split-transfer-group"
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-1.000000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 1),
        quantity=Decimal("0.500000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-funding",
    )
    Transactions.objects.create(
        investor=user,
        account=account_c,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 2),
        quantity=Decimal("0.500000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-earn",
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id]
    ) == Decimal("50.00")
    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_c.id]
    ) == Decimal("50.00")
    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id, account_c.id]
    ) == Decimal("100.00")


@pytest.mark.django_db
def test_split_grouped_transfer_outs_from_same_source_allocate_basis(user, crypto_account, btc):
    """Multiple same-source transfer-outs can fund later grouped transfer-ins."""
    account_b = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    account_c = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Earn",
        native_id="bybit-earn",
    )
    transfer_group = "split-transfer-outs-group"
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 10, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 10, 0),
        quantity=Decimal("-0.300000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 2, 11, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("200.000000000"),
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.500000000"),
        price=Decimal("200.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 13, 0),
        quantity=Decimal("0.400000000"),
        price=Decimal("150.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-funding",
    )
    Transactions.objects.create(
        investor=user,
        account=account_c,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 14, 0),
        quantity=Decimal("0.400000000"),
        price=Decimal("150.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-earn",
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id]
    ) == Decimal("54.71")
    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_c.id]
    ) == Decimal("54.71")
    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id, account_c.id]
    ) == Decimal("109.41")


@pytest.mark.django_db
def test_grouped_transfer_basis_does_not_use_future_transfer_out(user, crypto_account, btc):
    """Grouped transfer-in does not receive basis from a later transfer-out."""
    account_b = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    transfer_group = "future-transfer-out-group"
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-funding",
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 13, 0),
        quantity=Decimal("-0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-main",
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id]
    ) == Decimal("0.00")


@pytest.mark.django_db
def test_blank_provider_transfer_in_does_not_match_provider_transfer_out(user, crypto_account, btc):
    """Blank-provider transfer-in only matches blank-provider transfer-out."""
    account_b = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    transfer_group = "blank-provider-collision-group"
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="bybit",
        import_account_id="bybit-main",
    )
    Transactions.objects.create(
        investor=user,
        account=account_b,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 2, 12, 1),
        quantity=Decimal("0.400000000"),
        price=Decimal("100.000000000"),
        import_group_id=transfer_group,
        import_provider="",
        import_account_id="manual-funding",
    )

    assert get_economic_basis(btc, 
        datetime(2026, 1, 3).date(), user, "USD", [account_b.id]
    ) == Decimal("0.00")


@pytest.mark.django_db
def test_crypto_trade_cash_flow_for_irr_without_account_cash(user, crypto_account, btc):
    """Crypto trades expose asset cash flows for IRR but not account cash."""
    trade_in = Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    trade_out = Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.500000000"),
        price=Decimal("120.000000000"),
    )

    assert _calculate_cash_flow(trade_in) == Decimal("-100.000000000000000000")
    assert _calculate_cash_flow(trade_out) == Decimal("60.000000000000000000")
    assert account_balance(crypto_account, datetime(2026, 1, 3).date()) == {}


@pytest.mark.django_db
def test_external_crypto_transfer_cash_flow_for_irr_without_account_cash(user, crypto_account, btc):
    """External crypto transfers are IRR flows but not account cash."""
    transfer_in = Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("0.250000000"),
        price=Decimal("40000.000000000"),
    )
    transfer_out = Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.100000000"),
        price=Decimal("45000.000000000"),
    )

    assert _calculate_cash_flow(transfer_in) == Decimal("-10000.000000000000000000")
    assert _calculate_cash_flow(transfer_out) == Decimal("4500.000000000000000000")
    assert account_balance(crypto_account, datetime(2026, 1, 3).date()) == {}


@pytest.mark.django_db
def test_portfolio_irr_includes_external_crypto_transfer_flow(
    monkeypatch, user, crypto_account, btc
):
    """Portfolio IRR treats unpaired crypto transfer-in as an external contribution."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("0.250000000"),
        price=Decimal("40000.000000000"),
    )
    captured = {}

    def capture_xirr(dates, cash_flows):
        captured["dates"] = dates
        captured["cash_flows"] = cash_flows
        return Decimal("0.10")

    monkeypatch.setattr("core.portfolio_utils.xirr", capture_xirr)

    result = IRR(
        user.id,
        datetime(2026, 1, 2).date(),
        "USD",
        account_ids=[crypto_account.id],
        cached_nav=Decimal("11000.00"),
    )

    assert result == Decimal("0.1000")
    assert captured["cash_flows"] == [
        Decimal("-10000.00"),
        Decimal("11000.00"),
    ]


@pytest.mark.django_db
def test_internal_crypto_transfer_is_account_flow_but_portfolio_neutral(
    monkeypatch, user, crypto_account, btc
):
    """Paired internal transfers cancel for combined scope and flow for each account."""
    destination = Accounts.objects.create(
        broker=crypto_account.broker,
        name="Funding",
        native_id="bybit-funding",
    )
    transfer_group = "internal-transfer-for-irr"
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("-0.400000000"),
        price=Decimal("25000.000000000"),
        import_group_id=transfer_group,
    )
    Transactions.objects.create(
        investor=user,
        account=destination,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=datetime(2026, 1, 1, 12, 1),
        quantity=Decimal("0.400000000"),
        price=Decimal("25000.000000000"),
        import_group_id=transfer_group,
    )
    captured = []

    def capture_xirr(dates, cash_flows):
        captured.append(cash_flows)
        return Decimal("0.10")

    monkeypatch.setattr("core.portfolio_utils.xirr", capture_xirr)

    IRR(
        user.id,
        datetime(2026, 1, 2).date(),
        "USD",
        account_ids=[crypto_account.id, destination.id],
        cached_nav=Decimal("0.00"),
    )
    IRR(
        user.id,
        datetime(2026, 1, 2).date(),
        "USD",
        account_ids=[crypto_account.id],
        cached_nav=Decimal("0.00"),
    )
    IRR(
        user.id,
        datetime(2026, 1, 2).date(),
        "USD",
        account_ids=[destination.id],
        cached_nav=Decimal("0.00"),
    )

    assert captured[0] == [
        Decimal("10000.00"),
        Decimal("-10000.00"),
        Decimal("0.00"),
    ]
    assert captured[1] == [Decimal("10000.00"), Decimal("0.00")]
    assert captured[2] == [Decimal("-10000.00"), Decimal("0.00")]


@pytest.mark.django_db
def test_crypto_trade_out_realizes_gain_but_transfer_out_is_neutral(user, crypto_account, btc):
    """Crypto trade out realizes gain while transfer out only moves principal."""
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        date=datetime(2026, 1, 1, 12, 0),
        quantity=Decimal("1.000000000"),
        price=Decimal("100.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        date=datetime(2026, 1, 2, 12, 0),
        quantity=Decimal("-0.250000000"),
        price=Decimal("150.000000000"),
    )
    Transactions.objects.create(
        investor=user,
        account=crypto_account,
        security=btc,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        date=datetime(2026, 1, 3, 12, 0),
        quantity=Decimal("-0.250000000"),
        price=Decimal("200.000000000"),
    )

    realized = realized_gain_loss(btc, datetime(2026, 1, 4).date(), user, "USD", [crypto_account.id])
    assert realized["all_time"]["total"] == Decimal("25.000000000000000000")
