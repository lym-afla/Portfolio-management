"""Test duplicate detection for transactions and FX transactions."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from common.models import Accounts, Brokers, FXTransaction, Transactions
from core.import_utils import fx_transaction_exists, transaction_exists

CustomUser = get_user_model()


@pytest.fixture
def user():
    """Create a test user."""
    return CustomUser.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )


@pytest.fixture
def broker():
    """Create a test broker."""
    return Brokers.objects.create(name="Test Broker", currency="RUB")


@pytest.fixture
def account(user, broker):
    """Create a test account."""
    return Accounts.objects.create(
        name="Test Account", broker=broker, investor=user, currency="RUB"
    )


@pytest.fixture
def sample_transaction(user, account):
    """Create a sample transaction for testing."""
    return Transactions.objects.create(
        investor=user,
        account=account,
        date=datetime(2023, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        type="Buy",
        currency="RUB",
        cash_flow=Decimal("1000.00"),
        comment="Test transaction",
    )


@pytest.fixture
def sample_fx_transaction(user, account):
    """Create a sample FX transaction for testing."""
    return FXTransaction.objects.create(
        investor=user,
        account=account,
        date=datetime(2023, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        from_currency="RUB",
        to_currency="USD",
        exchange_rate=Decimal("75.50"),
        from_amount=Decimal("7550.00"),
        to_amount=Decimal("100.00"),
    )


@pytest.mark.asyncio
async def test_transaction_exists_exact_match(user, account, sample_transaction):
    """Test transaction_exists with exact matching data."""
    transaction_data = {
        "investor": user,
        "account": account,
        "date": sample_transaction.date,
        "type": "Buy",
        "currency": "RUB",
        "cash_flow": Decimal("1000.00"),
        "comment": "Test transaction",
        "security": None,
        "quantity": None,
        "price": None,
        "commission": None,
        "aci": None,
        "is_fx": False,
    }

    result = await transaction_exists(transaction_data)
    assert result is not None
    assert result.id == sample_transaction.id


@pytest.mark.asyncio
async def test_transaction_exists_time_window(user, account, sample_transaction):
    """
    Test transaction_exists.

    With time window matching (microsecond precision handling).
    """
    # Test with slightly different timestamp (within 1 second window)
    offset_date = sample_transaction.date + timedelta(microseconds=500)

    transaction_data = {
        "investor": user,
        "account": account,
        "date": offset_date,
        "type": "Buy",
        "currency": "RUB",
        "cash_flow": Decimal("1000.00"),
        "comment": "Test transaction",
        "security": None,
        "quantity": None,
        "price": None,
        "commission": None,
        "aci": None,
        "is_fx": False,
    }

    result = await transaction_exists(transaction_data)
    assert result is not None
    assert result.id == sample_transaction.id


@pytest.mark.asyncio
async def test_transaction_exists_no_match(user, account):
    """Test transaction_exists with non-matching data."""
    transaction_data = {
        "investor": user,
        "account": account,
        "date": datetime(2023, 1, 16, 10, 30, 0, tzinfo=timezone.utc),
        "type": "Buy",
        "currency": "RUB",
        "cash_flow": Decimal("1000.00"),
        "comment": "Different transaction",
        "security": None,
        "quantity": None,
        "price": None,
        "commission": None,
        "aci": None,
        "is_fx": False,
    }

    result = await transaction_exists(transaction_data)
    assert result is None


@pytest.mark.asyncio
async def test_transaction_exists_outside_time_window(
    user, account, sample_transaction
):
    """Test transaction_exists with timestamp outside 1-second window."""
    # Test with timestamp outside 1-second window
    offset_date = sample_transaction.date + timedelta(seconds=2)

    transaction_data = {
        "investor": user,
        "account": account,
        "date": offset_date,
        "type": "Buy",
        "currency": "RUB",
        "cash_flow": Decimal("1000.00"),
        "comment": "Test transaction",
        "security": None,
        "quantity": None,
        "price": None,
        "commission": None,
        "aci": None,
        "is_fx": False,
    }

    result = await transaction_exists(transaction_data)
    assert result is None


@pytest.mark.asyncio
async def test_fx_transaction_exists_exact_match(user, account, sample_fx_transaction):
    """Test fx_transaction_exists with exact matching data."""
    fx_transaction_data = {
        "investor": user,
        "account": account,
        "date": sample_fx_transaction.date,
        "from_currency": "RUB",
        "to_currency": "USD",
        "exchange_rate": Decimal("75.50"),
        "from_amount": Decimal("7550.00"),
        "to_amount": Decimal("100.00"),
        "commission": None,
        "commission_currency": None,
        "is_fx": True,
    }

    result = await fx_transaction_exists(fx_transaction_data)
    assert result is not None
    assert result.id == sample_fx_transaction.id


@pytest.mark.asyncio
async def test_fx_transaction_exists_time_window(user, account, sample_fx_transaction):
    """Test fx_transaction_exists with time window matching."""
    # Test with slightly different timestamp (within 1 second window)
    offset_date = sample_fx_transaction.date + timedelta(microseconds=300)

    fx_transaction_data = {
        "investor": user,
        "account": account,
        "date": offset_date,
        "from_currency": "RUB",
        "to_currency": "USD",
        "exchange_rate": Decimal("75.50"),
        "from_amount": Decimal("7550.00"),
        "to_amount": Decimal("100.00"),
        "commission": None,
        "commission_currency": None,
        "is_fx": True,
    }

    result = await fx_transaction_exists(fx_transaction_data)
    assert result is not None
    assert result.id == sample_fx_transaction.id


@pytest.mark.asyncio
async def test_fx_transaction_exists_no_match(user, account):
    """Test fx_transaction_exists with non-matching data."""
    fx_transaction_data = {
        "investor": user,
        "account": account,
        "date": datetime(2023, 1, 16, 10, 30, 0, tzinfo=timezone.utc),
        "from_currency": "RUB",
        "to_currency": "EUR",
        "exchange_rate": Decimal("85.50"),
        "from_amount": Decimal("8550.00"),
        "to_amount": Decimal("100.00"),
        "commission": None,
        "commission_currency": None,
        "is_fx": True,
    }

    result = await fx_transaction_exists(fx_transaction_data)
    assert result is None


@pytest.mark.asyncio
async def test_transaction_exists_missing_required_field(user, account):
    """Test transaction_exists raises error for missing required fields."""
    transaction_data = {
        "investor": user,
        "account": account,
        # Missing 'date' field
        "type": "Buy",
        "currency": "RUB",
        "cash_flow": Decimal("1000.00"),
        "is_fx": False,
    }

    with pytest.raises(
        ValueError, match="Required field 'date' is missing from transaction_data"
    ):
        await transaction_exists(transaction_data)


@pytest.mark.asyncio
async def test_fx_transaction_exists_missing_required_field(user, account):
    """Test fx_transaction_exists raises error for missing required fields."""
    fx_transaction_data = {
        "investor": user,
        "account": account,
        "date": datetime(2023, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        "from_currency": "RUB",
        # Missing 'to_currency' field
        "exchange_rate": Decimal("75.50"),
        "is_fx": True,
    }

    with pytest.raises(
        ValueError,
        match="Required field 'to_currency' is missing from FX transaction_data",
    ):
        await fx_transaction_exists(fx_transaction_data)


@pytest.mark.asyncio
async def test_transaction_multiple_duplicates(user, account, sample_transaction):
    """Test transaction_exists when multiple duplicates exist."""
    # Create another transaction with similar but slightly different data
    Transactions.objects.create(
        investor=user,
        account=account,
        date=sample_transaction.date + timedelta(microseconds=100),
        type="Buy",
        currency="RUB",
        cash_flow=Decimal("1000.00"),
        comment="Similar transaction",
    )

    transaction_data = {
        "investor": user,
        "account": account,
        "date": sample_transaction.date,
        "type": "Buy",
        "currency": "RUB",
        "cash_flow": Decimal("1000.00"),
        "comment": "Test transaction",
        "security": None,
        "quantity": None,
        "price": None,
        "commission": None,
        "aci": None,
        "is_fx": False,
    }

    # Should return the first matching transaction
    result = await transaction_exists(transaction_data)
    assert result is not None
    assert result.id in [
        sample_transaction.id
    ]  # Should return one of the matching transactions


@pytest.mark.asyncio
async def test_fx_transaction_multiple_duplicates(user, account, sample_fx_transaction):
    """Test fx_transaction_exists when multiple duplicates exist."""
    # Create another FX transaction with similar but slightly different data
    FXTransaction.objects.create(
        investor=user,
        account=account,
        date=sample_fx_transaction.date + timedelta(microseconds=200),
        from_currency="RUB",
        to_currency="USD",
        exchange_rate=Decimal("75.50"),
        from_amount=Decimal("7550.00"),
        to_amount=Decimal("100.00"),
    )

    fx_transaction_data = {
        "investor": user,
        "account": account,
        "date": sample_fx_transaction.date,
        "from_currency": "RUB",
        "to_currency": "USD",
        "exchange_rate": Decimal("75.50"),
        "from_amount": Decimal("7550.00"),
        "to_amount": Decimal("100.00"),
        "commission": None,
        "commission_currency": None,
        "is_fx": True,
    }

    # Should return the first matching transaction
    result = await fx_transaction_exists(fx_transaction_data)
    assert result is not None
    assert result.id in [
        sample_fx_transaction.id
    ]  # Should return one of the matching transactions
