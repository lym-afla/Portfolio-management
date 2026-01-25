"""Test save and update broker performance using httpx (SSE testing without daphne)."""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from common.models import FX, Accounts, Assets, Brokers, Transactions
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
async def user():
    """Create test user."""
    return await sync_to_async(User.objects.create_user)(
        username="testuser", password="testpass"
    )


@pytest.fixture
async def broker(user):
    """Create test broker."""
    return await sync_to_async(Brokers.objects.create)(
        investor=user, name="Test Broker", country="US"
    )


@pytest.fixture
async def account(broker):
    """Create test broker account."""
    return await sync_to_async(Accounts.objects.create)(
        broker=broker,
        name="Test Account",
        native_id="TEST001",
        restricted=False,
        is_active=True,
    )


@pytest.fixture
async def transactions(user, account):
    """Create test transactions."""
    asset = await sync_to_async(Assets.objects.create)(
        type="Stock",
        ISIN="US0378331005",
        name="Generic Security",
        currency="USD",
        exposure="Equity",
        restricted=False,
    )
    await sync_to_async(asset.investors.add)(user)

    await sync_to_async(Transactions.objects.create)(
        investor=user,
        account=account,
        date=date(2022, 1, 1),
        type=TRANSACTION_TYPE_CASH_IN,
        cash_flow=Decimal("1500"),
        currency="USD",
    )
    await sync_to_async(Transactions.objects.create)(
        investor=user,
        account=account,
        date=date(2022, 1, 2),
        type=TRANSACTION_TYPE_BUY,
        quantity=Decimal("10"),
        price=Decimal("100"),
        currency="USD",
        security=asset,
    )
    await sync_to_async(Transactions.objects.create)(
        investor=user,
        account=account,
        date=date(2022, 8, 31),
        type=TRANSACTION_TYPE_SELL,
        quantity=Decimal("-10"),
        price=Decimal("120"),
        currency="USD",
        security=asset,
    )
    await sync_to_async(Transactions.objects.create)(
        investor=user,
        account=account,
        date=date(2022, 9, 1),
        type=TRANSACTION_TYPE_CASH_OUT,
        cash_flow=Decimal("-1200"),
        currency="USD",
    )


@pytest.fixture
async def fx_rates(user):
    """Create FX rates for the test period."""
    start_date = date(2010, 1, 1)
    fx = await sync_to_async(FX.objects.create)(date=start_date)
    await sync_to_async(fx.investors.add)(user)
    fx.USDEUR = Decimal("1.15")
    fx.USDGBP = Decimal("1.25")
    fx.CHFGBP = Decimal("1.14")
    fx.RUBUSD = Decimal("65")
    fx.PLNUSD = Decimal("4")
    await sync_to_async(fx.save)()


def get_asgi_application():
    """Get the ASGI application."""
    from portfolio_management.asgi import application

    return application


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_broker_performance_unauthorized():
    """Test unauthorized access to SSE endpoint."""
    user = await sync_to_async(User.objects.create_user)(
        username="testuser", password="testpass"
    )
    broker = await sync_to_async(Brokers.objects.create)(
        investor=user, name="Test Broker", country="US"
    )

    session_id = "test_session_123"
    update_data = {
        "user_id": user.id + 1,  # Different user ID
        "selection_account_type": "broker",
        "selection_account_id": broker.id,
        "currency": "USD",
        "is_restricted": "False",
        "skip_existing_years": False,
        "effective_current_date": "2023-01-01",
    }

    await sync_to_async(cache.set)(
        f"account_performance_update_{session_id}", update_data
    )

    # Generate JWT token for authentication
    token = await sync_to_async(str)(AccessToken.for_user(user))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=get_asgi_application()),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/database/api/update-account-performance/sse/?session_id={session_id}&token={token}"
        )

        # The response should be 403 (user mismatch) since we're using wrong user_id
        assert response.status_code in [401, 403]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_broker_performance_missing_session():
    """Test missing session ID."""
    user = await sync_to_async(User.objects.create_user)(
        username="testuser", password="testpass"
    )
    # Generate JWT token for authentication
    token = await sync_to_async(str)(AccessToken.for_user(user))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=get_asgi_application()),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/database/api/update-account-performance/sse/?token={token}"  # No session_id but with token
        )

        assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_broker_performance_invalid_data():
    """Test broker performance calculation with invalid data."""
    user = await sync_to_async(User.objects.create_user)(
        username="testuser", password="testpass"
    )

    # Use DRF's APIClient for validation endpoint
    client = APIClient()
    await sync_to_async(client.force_authenticate)(user=user)

    # Test validation endpoint
    invalid_data = {
        "selection_account_type": "invalid",
        "selection_account_id": "INVALID",
        "currency": "INVALID",
        "is_restricted": "INVALID",
        "skip_existing_years": "not_a_boolean",
        "effective_current_date": "2023-01-01",
    }

    response = await sync_to_async(client.post)(
        "/database/api/update-account-performance/validate/",
        invalid_data,
        format="json",
    )

    assert response.status_code == 400
    response_data = response.json()
    assert response_data["valid"] is False
    assert response_data["type"] == "validation"
    assert "errors" in response_data


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_broker_performance_no_transactions():
    """Test broker performance calculation with no transactions."""
    user = await sync_to_async(User.objects.create_user)(
        username="testuser", password="testpass"
    )
    broker = await sync_to_async(Brokers.objects.create)(
        investor=user, name="Test Broker", country="US"
    )

    session_id = "test_session_invalid"
    update_data = {
        "user_id": user.id,
        "selection_account_type": "broker",
        "selection_account_id": broker.id,
        "currency": "USD",
        "is_restricted": "False",
        "skip_existing_years": False,
        "effective_current_date": "2023-01-01",
    }

    await sync_to_async(cache.set)(
        f"account_performance_update_{session_id}", update_data
    )

    # Generate JWT token for authentication
    token = await sync_to_async(str)(AccessToken.for_user(user))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=get_asgi_application()),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/database/api/update-account-performance/sse/?session_id={session_id}&token={token}"
        )

        assert response.status_code == 200

        # Parse SSE messages
        response_text = response.text
        events = [
            json.loads(line.replace("data: ", ""))
            for line in response_text.strip().split("\n\n")
            if line.startswith("data: ")
        ]

        error_events = [event for event in events if event["status"] == "error"]
        assert len(error_events) >= 1
        assert any(
            "No transactions found" in event.get("message", "")
            for event in error_events
        )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_accounts_table_api():
    """Test the accounts table API functionality."""
    user = await sync_to_async(User.objects.create_user)(
        username="testuser", password="testpass"
    )
    broker = await sync_to_async(Brokers.objects.create)(
        investor=user, name="Test Broker", country="US"
    )
    _ = await sync_to_async(Accounts.objects.create)(
        broker=broker,
        name="Test Account",
        native_id="TEST001",
        restricted=False,
        is_active=True,
    )

    # Create FX rates
    start_date = date(2010, 1, 1)
    fx = await sync_to_async(FX.objects.create)(date=start_date)
    await sync_to_async(fx.investors.add)(user)
    fx.USDEUR = Decimal("1.15")
    fx.USDGBP = Decimal("1.25")
    await sync_to_async(fx.save)()

    # Create mock request with user default settings
    class MockRequest:
        def __init__(self, user, data):
            self.user = user
            self.data = data
            self.session = {
                "effective_current_date": datetime.now().strftime("%Y-%m-%d")
            }
            user.default_currency = "USD"
            user.digits = 2

    # Test basic functionality
    request = MockRequest(
        user, {"page": 1, "itemsPerPage": 10, "search": "", "sortBy": {}}
    )

    response = await sync_to_async(get_accounts_table_api)(request)

    # Verify response structure
    assert "accounts" in response
    assert "totals" in response
    assert "total_items" in response
    assert "current_page" in response
    assert "total_pages" in response

    # Verify accounts data
    accounts = response["accounts"]
    assert len(accounts) >= 1  # Should have at least one test account


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_last_exit_date_for_brokers():
    """Test get last exit date for brokers."""
    user = await sync_to_async(User.objects.create_user)(
        username="testuser", password="testpass"
    )
    broker = await sync_to_async(Brokers.objects.create)(
        investor=user, name="Test Broker", country="US"
    )
    account = await sync_to_async(Accounts.objects.create)(
        broker=broker,
        name="Test Account",
        native_id="TEST001",
        restricted=False,
        is_active=True,
    )

    asset = await sync_to_async(Assets.objects.create)(
        type="Stock",
        ISIN="US1234567890",
        name="Test Stock",
        currency="USD",
        exposure="Equity",
        restricted=False,
    )
    await sync_to_async(asset.investors.add)(user)

    transaction_date = datetime.now().date() - timedelta(days=30)
    await sync_to_async(Transactions.objects.create)(
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
    last_exit_date = await sync_to_async(get_last_exit_date_for_accounts)(
        [account.id], current_date
    )

    assert last_exit_date == current_date

    # Close the position
    await sync_to_async(Transactions.objects.create)(
        investor=user,
        account=account,
        security=asset,
        date=current_date - timedelta(days=1),
        type=TRANSACTION_TYPE_SELL,
        quantity=-100,
        price=15,
        currency="USD",
    )

    last_exit_date = await sync_to_async(get_last_exit_date_for_accounts)(
        [account.id], current_date
    )
    # Convert to date if it's a datetime for comparison
    if isinstance(last_exit_date, datetime):
        last_exit_date = last_exit_date.date()
    assert last_exit_date == current_date - timedelta(days=1)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_calculate_performance():
    """Test calculate performance."""
    user = await sync_to_async(User.objects.create_user)(
        username="testuser", password="testpass"
    )
    broker = await sync_to_async(Brokers.objects.create)(
        investor=user, name="Test Broker", country="US"
    )
    account = await sync_to_async(Accounts.objects.create)(
        broker=broker,
        name="Test Account",
        native_id="TEST001",
        restricted=False,
        is_active=True,
    )

    asset = await sync_to_async(Assets.objects.create)(
        type="Stock",
        ISIN="US1234567890",
        name="Test Stock",
        currency="USD",
        exposure="Equity",
        restricted=False,
    )
    await sync_to_async(asset.investors.add)(user)

    start_date = datetime(2022, 1, 1).date()
    end_date = datetime(2022, 12, 31).date()

    await sync_to_async(Transactions.objects.create)(
        investor=user,
        account=account,
        date=start_date,
        type=TRANSACTION_TYPE_CASH_IN,
        cash_flow=Decimal("1000"),
        currency="USD",
    )
    await sync_to_async(Transactions.objects.create)(
        investor=user,
        account=account,
        security=asset,
        date=start_date + timedelta(days=30),
        type=TRANSACTION_TYPE_BUY,
        quantity=100,
        price=10,
        currency="USD",
    )
    await sync_to_async(Transactions.objects.create)(
        investor=user,
        account=account,
        security=asset,
        date=end_date - timedelta(days=30),
        type=TRANSACTION_TYPE_SELL,
        quantity=-100,
        price=15,
        currency="USD",
    )
    await sync_to_async(Transactions.objects.create)(
        investor=user,
        account=account,
        date=end_date,
        type=TRANSACTION_TYPE_CASH_OUT,
        cash_flow=Decimal("-1200"),
        currency="USD",
    )

    performance_data = await sync_to_async(calculate_performance)(
        user, start_date, end_date, "account", account.id, "USD"
    )

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

    assert performance_data["invested"] == Decimal("1000")
    assert performance_data["cash_out"] == Decimal("-1200")
    assert performance_data["price_change"] == Decimal("500")  # (15 - 10) * 100
