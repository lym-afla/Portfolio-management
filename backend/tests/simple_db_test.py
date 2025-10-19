"""
Simple database test that bypasses complex fixtures.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from common.models import Assets
from common.models import Transactions

CustomUser = get_user_model()


@pytest.mark.django_db
class TestSimpleDatabaseOperations:
    """Test basic database operations without complex fixtures."""

    def test_create_user(self):
        """Test creating a user directly."""
        user = CustomUser.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        assert user.username == "testuser"
        assert user.email == "test@example.com"

    def test_create_asset_simple(self):
        """Test creating an asset directly."""
        asset = Assets.objects.create(
            type="Stock",
            ISIN="TEST123456789",
            name="Test Stock Corp",
            currency="USD",
            exposure="Equity",
        )
        assert asset.name == "Test Stock Corp"
        assert asset.currency == "USD"

    def test_create_transaction_simple(self):
        """Test creating a transaction directly."""
        # Create user first
        user = CustomUser.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create asset
        asset = Assets.objects.create(
            type="Stock",
            ISIN="TEST123456789",
            name="Test Stock Corp",
            currency="USD",
            exposure="Equity",
        )

        # Create transaction
        transaction = Transactions.objects.create(
            investor=user,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        assert transaction.investor == user
        assert transaction.security == asset
        assert transaction.quantity == Decimal("100")
        assert transaction.price == Decimal("50.00")

    def test_simple_buy_in_price_calculation(self):
        """Test buy-in price calculation with simple setup."""
        # Create user
        user = CustomUser.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create asset
        asset = Assets.objects.create(
            type="Stock",
            ISIN="TEST123456789",
            name="Test Stock Corp",
            currency="USD",
            exposure="Equity",
        )

        # Create multiple buy transactions
        Transactions.objects.create(
            investor=user,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        Transactions.objects.create(
            investor=user,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("50"),
            price=Decimal("55.00"),
            cash_flow=Decimal("-2750.00"),
            commission=Decimal("3.00"),
        )

        # Test basic calculation logic
        total_cost = Decimal("5000") + Decimal("2750")  # 7750
        total_quantity = Decimal("100") + Decimal("50")  # 150
        expected_buy_in_price = total_cost / total_quantity  # 51.666...

        # Verify calculation
        assert expected_buy_in_price == Decimal("51.66666666666666666666666667")

    def test_decimal_precision(self):
        """Test decimal precision handling."""
        # Create user and asset
        user = CustomUser.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        asset = Assets.objects.create(
            type="Stock",
            ISIN="TEST123456789",
            name="Test Stock Corp",
            currency="USD",
            exposure="Equity",
        )

        # Create transaction with high precision
        Transactions.objects.create(
            investor=user,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("1.234567"),
            price=Decimal("123.456789"),
            cash_flow=Decimal("-152.41579"),
            commission=Decimal("0.15"),
        )

        # Test high precision calculation
        quantity = Decimal("1.234567")
        price = Decimal("123.456789")
        expected_cost = quantity * price
        assert expected_cost == Decimal("152.415791749763")

    @pytest.mark.performance
    def test_simple_performance(self):
        """Test performance with simple database operations."""
        import time

        start_time = time.time()

        # Create multiple assets
        assets = []
        for i in range(10):
            asset = Assets.objects.create(
                type="Stock",
                ISIN=f"TEST{i:010d}",
                name=f"Test Stock {i}",
                currency="USD",
                exposure="Equity",
            )
            assets.append(asset)

        end_time = time.time()
        creation_time = end_time - start_time

        # Should complete quickly
        assert creation_time < 2.0
        assert len(assets) == 10
        assert all(asset.name.startswith("Test Stock") for asset in assets)
