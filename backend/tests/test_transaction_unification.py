"""
Tests for the unified transaction processing implementation.

This test suite verifies that:
1. Centralized cash flow calculation works correctly
2. Serializers produce consistent output
3. Balance tracking functions properly
4. Bond price formatting is correct
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from common.models import Accounts, Assets, Brokers, FXTransaction, Transactions
from constants import (
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_SELL,
)
from core.balance_tracker import BalanceTracker
from database.serializers import FXTransactionSerializer, TransactionSerializer

User = get_user_model()


@pytest.mark.django_db
class TestCashFlowCalculation:
    """Test the centralized get_calculated_cash_flow() method."""

    def test_buy_transaction_cash_flow(self, user, account, stock):
        """Test cash flow calculation for a buy transaction."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=stock,
            type=TRANSACTION_TYPE_BUY,
            date=date(2024, 1, 1),
            quantity=100,  # Positive for buy
            price=Decimal("150.00"),
            commission=Decimal("-9.95"),
            currency="USD",
        )

        # Expected: -100 * 150.00 - 9.95 = -15,009.95
        cash_flow = transaction.get_calculated_cash_flow()
        assert cash_flow == Decimal("-15009.95")

    def test_sell_transaction_cash_flow(self, user, account, stock):
        """Test cash flow calculation for a sell transaction."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=stock,
            type=TRANSACTION_TYPE_SELL,
            date=date(2024, 1, 1),
            quantity=-100,  # Negative for sell
            price=Decimal("160.00"),
            commission=Decimal("-9.95"),
            currency="USD",
        )

        # Expected: -100 * 160.00 - 9.95 = 15,990.05
        cash_flow = transaction.get_calculated_cash_flow()
        assert cash_flow == Decimal("15990.05")

    def test_bond_buy_with_aci(self, user, account, bond):
        """Test cash flow calculation for a bond with ACI."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            type=TRANSACTION_TYPE_BUY,
            date=date(2024, 1, 1),
            quantity=10,  # Positive for buy
            price=Decimal("98.5"),  # Stored as percentage
            notional=Decimal("1000"),  # Par value per bond
            aci=Decimal("-25.50"),  # Negative for buy (we pay it)
            commission=Decimal("-15.00"),
            currency="USD",
        )

        # Effective price: 98.5% * 1000 / 100 = 985.00 per bond
        # Expected: -(-10) * 985.00 + (-25.50) - 15.00 = -9,890.50
        cash_flow = transaction.get_calculated_cash_flow()
        assert cash_flow == Decimal("-9890.50")

    def test_cash_in_transaction(self, user, account):
        """Test cash flow for cash in transaction."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            type=TRANSACTION_TYPE_CASH_IN,
            date=date(2024, 1, 1),
            cash_flow=Decimal("10000.00"),
            currency="USD",
        )

        cash_flow = transaction.get_calculated_cash_flow()
        assert cash_flow == Decimal("10000.00")

    def test_dividend_transaction(self, user, account, stock):
        """Test cash flow for dividend transaction."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=stock,
            type=TRANSACTION_TYPE_DIVIDEND,
            date=date(2024, 1, 1),
            cash_flow=Decimal("150.00"),
            currency="USD",
        )

        cash_flow = transaction.get_calculated_cash_flow()
        assert cash_flow == Decimal("150.00")


@pytest.mark.django_db
class TestTransactionSerializer:
    """Test the enhanced TransactionSerializer."""

    def test_serializer_includes_instrument_type(self, user, account, stock):
        """Verify instrument_type field is included."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=stock,
            type=TRANSACTION_TYPE_BUY,
            date=date(2024, 1, 1),
            quantity=100,
            price=Decimal("150.00"),
            currency="USD",
        )

        serializer = TransactionSerializer(transaction, context={"digits": 2})
        data = serializer.data

        assert data["instrument_type"] == "Stock"
        assert data["transaction_type"] == "regular"
        assert data["id"] == f"regular_{transaction.id}"

    def test_bond_price_formatted_as_percentage(self, user, account, bond):
        """Verify bonds show price as percentage."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=bond,
            type=TRANSACTION_TYPE_BUY,
            date=date(2024, 1, 1),
            quantity=10,
            price=Decimal("98.5"),
            notional=Decimal("1000"),
            currency="USD",
        )

        serializer = TransactionSerializer(transaction, context={"digits": 2})
        data = serializer.data

        # Price should be formatted as percentage
        assert "%" in data["price"]
        assert "98.5" in data["price"]


@pytest.mark.django_db
class TestBalanceTracker:
    """Test the BalanceTracker helper class."""

    def test_balance_tracking_single_currency(self, user, account, stock):
        """Test balance tracking with single currency."""
        tracker = BalanceTracker(number_of_digits=2)
        tracker.set_initial_balances({"USD": Decimal("10000.00")})

        # Create a buy transaction
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=stock,
            type=TRANSACTION_TYPE_BUY,
            date=date(2024, 1, 1),
            quantity=100,
            price=Decimal("150.00"),
            commission=Decimal("-9.95"),
            currency="USD",
        )

        tracker.update(transaction)
        balances = tracker.get_balances_for_transaction(transaction.id)

        # Balance should be 10,000 - 15,009.95 = -5,009.95
        assert "USD" in balances
        # Check that the formatted balance contains a negative 'bracket'
        assert "(" in balances["USD"]

    def test_balance_tracking_with_fx(self, user, account):
        """Test balance tracking with FX transaction."""
        tracker = BalanceTracker(number_of_digits=2)
        tracker.set_initial_balances({"USD": Decimal("10000.00"), "EUR": Decimal("0")})

        # Create an FX transaction
        fx_transaction = FXTransaction.objects.create(
            investor=user,
            account=account,
            date=date(2024, 1, 1),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000.00"),
            to_amount=Decimal("920.50"),
            exchange_rate=Decimal("0.9205"),
        )

        tracker.update(fx_transaction)
        balances = tracker.get_balances_for_transaction(fx_transaction.id)

        assert "USD" in balances
        assert "EUR" in balances
        # USD should be reduced, EUR should be increased


@pytest.mark.django_db
class TestFXTransactionSerializer:
    """Test the FXTransactionSerializer."""

    def test_fx_serializer_structure(self, user, account):
        """Verify FX transaction serializer produces correct structure."""
        fx_transaction = FXTransaction.objects.create(
            investor=user,
            account=account,
            date=date(2024, 1, 1),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000.00"),
            to_amount=Decimal("920.50"),
            exchange_rate=Decimal("0.9205"),
        )

        serializer = FXTransactionSerializer(fx_transaction, context={"digits": 2})
        data = serializer.data

        assert data["transaction_type"] == "fx"
        assert data["type"] == "FX"
        assert data["id"] == f"fx_{fx_transaction.id}"
        assert data["from_cur"] == "USD"
        assert data["to_cur"] == "EUR"


# Fixtures
@pytest.fixture
def user():
    """Create test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
        default_currency="USD",
        digits=2,
    )


@pytest.fixture
def broker(user):
    """Create test broker."""
    return Brokers.objects.create(investor=user, name="Test Broker", country="US")


@pytest.fixture
def account(broker):
    """Create test account."""
    return Accounts.objects.create(broker=broker, name="Test Account")


@pytest.fixture
def stock(user):
    """Create test stock asset."""
    asset = Assets.objects.create(
        name="Apple Inc.", ticker="AAPL", type="Stock", currency="USD"
    )
    asset.investors.add(user)
    return asset


@pytest.fixture
def bond(user):
    """Create test bond asset."""
    asset = Assets.objects.create(
        name="US Treasury Bond", ticker="UST", type="Bond", currency="USD"
    )
    asset.investors.add(user)
    return asset
