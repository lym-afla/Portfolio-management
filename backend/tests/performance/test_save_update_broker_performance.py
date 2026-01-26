"""Test save and update broker performance (non-SSE tests only)."""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from common.models import Accounts, Assets, Brokers, Transactions
from constants import (
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_SELL,
)
from core.accounts_utils import get_accounts_table_api
from core.portfolio_utils import calculate_performance, get_last_exit_date_for_accounts

User = get_user_model()


@pytest.fixture
def user():
    """Create test user."""
    return User.objects.create_user(username="testuser", password="testpass")


@pytest.fixture
def broker(user):
    """Create test broker."""
    return Brokers.objects.create(investor=user, name="Test Broker", country="US")


@pytest.fixture
def account(broker):
    """Create test broker account."""
    return Accounts.objects.create(
        broker=broker,
        name="Test Account",
        native_id="TEST001",
        restricted=False,
        is_active=True,
    )


@pytest.fixture
def transactions(user, account):
    """Create test transactions."""
    asset = Assets.objects.create(
        type="Stock",
        ISIN="US0378331005",
        name="Generic Security",
        currency="USD",
        exposure="Equity",
        restricted=False,
    )
    asset.investors.add(user)

    Transactions.objects.create(
        investor=user,
        account=account,
        date=date(2022, 1, 1),
        type=TRANSACTION_TYPE_CASH_IN,
        cash_flow=Decimal("1500"),
        currency="USD",
    )
    Transactions.objects.create(
        investor=user,
        account=account,
        date=date(2022, 1, 2),
        type=TRANSACTION_TYPE_BUY,
        quantity=Decimal("10"),
        price=Decimal("100"),
        currency="USD",
        security=asset,
    )
    Transactions.objects.create(
        investor=user,
        account=account,
        date=date(2022, 8, 31),
        type=TRANSACTION_TYPE_SELL,
        quantity=Decimal("-10"),
        price=Decimal("120"),
        currency="USD",
        security=asset,
    )
    Transactions.objects.create(
        investor=user,
        account=account,
        date=date(2022, 9, 1),
        type=TRANSACTION_TYPE_CASH_OUT,
        cash_flow=Decimal("-1200"),
        currency="USD",
    )


@pytest.fixture
def fx_rates(user):
    """Create FX rates for the test period."""
    from common.models import FX

    # Create FX rates for the test period
    start_date = date(2010, 1, 1)
    fx = FX.objects.create(date=start_date)
    fx.investors.add(user)
    fx.USDEUR = Decimal("1.15")
    fx.USDGBP = Decimal("1.25")
    fx.CHFGBP = Decimal("1.14")
    fx.RUBUSD = Decimal("65")
    fx.PLNUSD = Decimal("4")
    fx.save()


@pytest.mark.django_db
def test_get_last_exit_date_for_brokers(user, account):
    """Test get last exit date for brokers."""
    asset = Assets.objects.create(
        type="Stock",
        ISIN="US1234567890",
        name="Test Stock",
        currency="USD",
        exposure="Equity",
        restricted=False,
    )
    asset.investors.add(user)

    transaction_date = datetime.now().date() - timedelta(days=30)
    Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        date=transaction_date,
        type=TRANSACTION_TYPE_BUY,
        quantity=100,
        price=10,
        currency="USD",
    )

    current_date = datetime.now().date()
    last_exit_date = get_last_exit_date_for_accounts([account.id], current_date)

    assert last_exit_date == current_date

    # Close the position
    Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        date=current_date - timedelta(days=1),
        type=TRANSACTION_TYPE_SELL,
        quantity=-100,
        price=15,
        currency="USD",
    )

    last_exit_date = get_last_exit_date_for_accounts([account.id], current_date)
    # Convert to date if it's a datetime for comparison
    if isinstance(last_exit_date, datetime):
        last_exit_date = last_exit_date.date()
    assert last_exit_date == current_date - timedelta(days=1)


@pytest.mark.django_db
def test_calculate_performance(user, account, caplog):
    """Test calculate performance."""
    caplog.set_level(logging.DEBUG)

    asset = Assets.objects.create(
        type="Stock",
        ISIN="US1234567890",
        name="Test Stock",
        currency="USD",
        exposure="Equity",
        restricted=False,
    )
    asset.investors.add(user)

    start_date = datetime(2022, 1, 1).date()
    end_date = datetime(2022, 12, 31).date()

    Transactions.objects.create(
        investor=user,
        account=account,
        date=start_date,
        type=TRANSACTION_TYPE_CASH_IN,
        cash_flow=Decimal("1000"),
        currency="USD",
    )
    Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        date=start_date + timedelta(days=30),
        type=TRANSACTION_TYPE_BUY,
        quantity=100,
        price=10,
        currency="USD",
    )
    Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        date=end_date - timedelta(days=30),
        type=TRANSACTION_TYPE_SELL,
        quantity=-100,
        price=15,
        currency="USD",
    )
    Transactions.objects.create(
        investor=user,
        account=account,
        date=end_date,
        type=TRANSACTION_TYPE_CASH_OUT,
        cash_flow=Decimal("-1200"),
        currency="USD",
    )

    performance_data = calculate_performance(
        user, start_date, end_date, "account", account.id, "USD"
    )

    for t in Transactions.objects.filter(investor=user, account=account):
        print(f"Transaction: {t.date} {t.type} {t.quantity} {t.price} {t.currency}")

    # Get the realized gain/loss value first
    realized_gain = asset.realized_gain_loss(
        end_date, user, "USD", account_ids=[account.id], start_date=start_date
    )
    print(f"Price change: {realized_gain}")

    assert "bop_nav" in performance_data
    assert "eop_nav" in performance_data
    assert "invested" in performance_data
    assert "cash_out" in performance_data
    assert "price_change" in performance_data
    assert "capital_distribution" in performance_data
    assert "commission" in performance_data
    assert "tax" in performance_data
    assert "fx" in performance_data
    assert "tsr" in performance_data

    assert performance_data["invested"] == Decimal("1000")  # No cash inflows
    assert performance_data["cash_out"] == Decimal("-1200")  # No cash outflows
    assert performance_data["price_change"] == Decimal("500")  # (15 - 10) * 100


@pytest.mark.django_db
def test_get_accounts_table_api(user, broker, account, transactions, fx_rates):
    """Test the accounts table API functionality."""
    # Create a second broker and account
    second_broker = Brokers.objects.create(investor=user, name="Second Test Broker", country="US")
    second_account = Accounts.objects.create(
        name="Second Test Account", broker=second_broker, restricted=True
    )

    # Create asset for second account (using USD to avoid FX conversion issues)
    asset = Assets.objects.create(
        type="Stock",
        ISIN="US1234567891",
        name="Second Test Stock",
        currency="USD",
        exposure="Equity",
        restricted=False,
    )
    asset.investors.add(user)

    # Create additional transaction for second account
    current_date = datetime.now().date()
    Transactions.objects.create(
        investor=user,
        account=second_account,
        security=asset,
        date=current_date - timedelta(days=30),
        type=TRANSACTION_TYPE_BUY,
        quantity=50,
        price=15,
        currency="USD",
    )

    # Create mock request with user default settings
    class MockRequest:
        def __init__(self, user, data):
            self.user = user
            self.data = data
            self.session = {"effective_current_date": current_date.strftime("%Y-%m-%d")}
            user.default_currency = "USD"
            user.digits = 2

    # Test basic functionality
    request = MockRequest(user, {"page": 1, "itemsPerPage": 10, "search": "", "sortBy": {}})

    response = get_accounts_table_api(request)

    # Verify response structure
    assert "accounts" in response
    assert "totals" in response
    assert "total_items" in response
    assert "current_page" in response
    assert "total_pages" in response

    # Verify accounts data
    accounts = response["accounts"]
    assert len(accounts) >= 1  # Should have at least one test account

    # Verify first account data
    first_account = next(acc for acc in accounts if acc["id"] == account.id)
    assert first_account["name"] == account.name
    assert first_account["broker_name"] == broker.name
    assert isinstance(first_account["nav"], str)
    assert any(
        [
            first_account["nav"].startswith("$"),  # Positive value
            first_account["nav"].startswith("($"),  # Negative value
        ]
    )
    assert isinstance(first_account["cash"], dict)
    assert isinstance(first_account["irr"], str)  # IRR is formatted as percentage

    # Test totals calculation
    totals = response["totals"]
    assert "nav" in totals
    assert "irr" in totals
    assert isinstance(totals["nav"], str)
    assert any(
        [
            totals["nav"].startswith("$"),  # Positive value
            totals["nav"].startswith("($"),  # Negative value
        ]
    )
    assert isinstance(totals["irr"], str)


@pytest.mark.django_db
def test_update_broker_performance_validation(user):
    """Test broker performance calculation validation."""
    # Use DRF's APIClient for validation endpoint
    client = APIClient()
    client.force_authenticate(user=user)

    # Test validation endpoint
    invalid_data = {
        "selection_account_type": "invalid",
        "selection_account_id": "INVALID",
        "currency": "INVALID",
        "is_restricted": "INVALID",
        "skip_existing_years": "not_a_boolean",
        "effective_current_date": "2023-01-01",
    }

    # First, test the validation endpoint
    response = client.post(
        "/database/api/update-account-performance/validate/",
        invalid_data,
        format="json",  # Use format='json' instead of content_type
    )

    assert response.status_code == 400
    response_data = response.json()
    assert response_data["valid"] is False
    assert response_data["type"] == "validation"
    assert "errors" in response_data

    # Verify specific validation errors
    errors = response_data["errors"]
    assert "selection_account_type" in errors  # Invalid account type
    assert "currency" in errors  # Invalid currency
    assert "is_restricted" in errors  # Invalid restriction value

    # Step 2: Test that invalid data can't start the process
    response = client.post(
        "/database/api/update-account-performance/start/", invalid_data, format="json"
    )

    assert response.status_code == 400
    response_data = response.json()
    assert response_data["valid"] is False
    assert response_data["type"] == "validation"
