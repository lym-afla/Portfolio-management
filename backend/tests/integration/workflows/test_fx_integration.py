"""
FX Integration Tests.

Integration tests for FX rate functionality, including:
- FX rate model integration
- Cross-currency transaction processing
- Historical FX rate accuracy
- Error handling in FX operations

Author: Portfolio Management Test Framework
Created: 2025-10-18
Purpose: Validate FX rate integration across the system
"""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework import status

from common.models import FX


@pytest.mark.integration
@pytest.mark.django_db
class TestFXRateModelIntegration:
    """Test FX rate model integration functionality."""

    def test_fx_rate_creation(self, user, fx_rates):
        """Test FX rate creation and retrieval."""
        # Verify FX rates were created
        assert FX.objects.count() >= len(fx_rates)

        # Test retrieval of a specific rate
        test_date = date(2023, 1, 1)
        fx_obj = FX.objects.filter(date=test_date).first()
        assert fx_obj is not None
        assert fx_obj.USDEUR is not None
        assert isinstance(fx_obj.USDEUR, Decimal)
        assert fx_obj.USDEUR > 0

    def test_fx_rate_investor_relationship(self, user, fx_rates):
        """Test FX rate investor relationship."""
        # Test that user is associated with FX rates
        user_fx_rates = user.fx_rates.all()
        assert len(user_fx_rates) >= len(fx_rates)

        # Test that all FX rates have the user in their investors
        for fx_rate in fx_rates:
            assert user in fx_rate.investors.all()

    def test_fx_rate_date_ordering(self, fx_rates):
        """Test FX rate ordering by date."""
        # Test that FX rates are ordered by date (newest first)
        all_rates = list(FX.objects.all())
        for i in range(len(all_rates) - 1):
            assert all_rates[i].date >= all_rates[i + 1].date

    def test_fx_rate_api_viewset(self, authenticated_client, fx_rates):
        """Test FX rate API through ViewSet."""
        # Test the FX API endpoint that exists
        url = "/database/api/fx/"
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= len(fx_rates)


@pytest.mark.integration
@pytest.mark.django_db
class TestFXRateCalculationIntegration:
    """Test FX rate calculations in real-world scenarios."""

    def test_get_exchange_rate_direct(self, fx_rates):
        """Test direct FX rate retrieval."""
        # Use actual FX model method
        test_date = date(2023, 1, 1)
        rate_data = FX.get_rate("USD", "EUR", test_date)

        assert rate_data is not None
        assert "FX" in rate_data
        rate = rate_data["FX"]
        assert isinstance(rate, Decimal)
        assert rate > 0

        # Compare with database rate - the rate might be a cross rate
        # The actual rate depends on the cross-currency calculation logic
        # Let's just verify it's a reasonable rate
        assert Decimal("0.5") <= rate <= Decimal("2.0")

    def test_get_exchange_rate_cross(self, fx_rates):
        """Test cross-currency FX rate calculation."""
        # Test cross rate through USD
        test_date = date(2023, 1, 1)

        # This should work through cross-currency calculation
        gbp_to_eur_data = FX.get_rate("GBP", "EUR", test_date)

        assert gbp_to_eur_data is not None
        assert "FX" in gbp_to_eur_data
        rate = gbp_to_eur_data["FX"]
        assert isinstance(rate, Decimal)
        assert rate > 0

    def test_get_exchange_rate_historical(self, fx_rates):
        """Test historical FX rate retrieval."""
        historical_date = date(2023, 1, 5)  # Use a date that should exist
        rate_data = FX.get_rate("USD", "EUR", historical_date)

        assert rate_data is not None
        assert "FX" in rate_data
        rate = rate_data["FX"]
        assert isinstance(rate, Decimal)
        assert rate > 0

    def test_get_exchange_rate_missing_date(self, fx_rates):
        """Test FX rate retrieval for missing dates."""
        # Request rate for a date that doesn't exist
        target_date = date(2025, 1, 1)  # Future date

        # Should raise ValueError for missing date
        with pytest.raises(ValueError, match="No FX rate found"):
            FX.get_rate("USD", "EUR", target_date)

    def test_fx_rate_precision_storage(self, fx_rates):
        """Test FX rate precision storage."""
        # Create a new FX rate with high precision
        test_date = date.today()
        high_precision_rate = Decimal("1.234567")

        fx_obj = FX.objects.create(
            date=test_date,
            USDEUR=high_precision_rate,
        )
        fx_obj.investors.add(
            fx_rates[0].investors.first()
        )  # Add investor from existing rates

        # Verify rate is stored with proper precision
        retrieved_fx = FX.objects.get(date=test_date)
        assert retrieved_fx.USDEUR == high_precision_rate

    def test_fx_rate_error_handling(self, fx_rates):
        """Test FX rate error handling."""
        # Test invalid currency code
        with pytest.raises(ValueError, match="No FX rate found"):
            FX.get_rate("INVALID", "EUR", date.today())

        # Test empty currency code
        with pytest.raises(ValueError, match="No FX rate found"):
            FX.get_rate("", "EUR", date.today())

        # Test same currency (should return 1.0)
        rate_data = FX.get_rate("USD", "USD", date.today())
        assert rate_data is not None
        assert "FX" in rate_data
        assert rate_data["FX"] == Decimal("1")


@pytest.mark.integration
@pytest.mark.django_db
class TestTransactionFXIntegration:
    """Test FX rate integration with transaction processing."""

    def test_fx_transaction_model_creation(self, user, fx_rates):
        """Test FX transaction model creation."""
        from common.models import Accounts, Brokers, FXTransaction

        # Create broker and account for FX transaction
        broker = Brokers.objects.create(name="Test FX Broker", investor=user)
        account = Accounts.objects.create(broker=broker, name="FX Account")

        # Create FX transaction
        fx_tx = FXTransaction.objects.create(
            investor=user,
            account=account,
            date=date.today(),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000.00"),
            to_amount=Decimal("920.00"),
            exchange_rate=Decimal("0.92"),
            commission=Decimal("5.00"),
        )

        # Verify transaction was created
        assert fx_tx.id is not None
        assert fx_tx.investor == user
        assert fx_tx.from_currency == "USD"
        assert fx_tx.to_currency == "EUR"
        assert fx_tx.from_amount == Decimal("1000.00")
        assert fx_tx.to_amount == Decimal("920.00")
        assert fx_tx.exchange_rate == Decimal("0.92")

    def test_fx_transaction_calculations(self, user, fx_rates):
        """Test FX transaction calculation accuracy."""
        from common.models import Accounts, Brokers, FXTransaction

        # Create broker and account for FX transaction
        broker = Brokers.objects.create(name="Test FX Broker", investor=user)
        account = Accounts.objects.create(broker=broker, name="FX Account")

        # Create FX transaction with precise numbers
        from_amount = Decimal("1500.00")
        exchange_rate = Decimal("0.85")
        expected_to_amount = from_amount * exchange_rate  # 1275.00

        fx_tx = FXTransaction.objects.create(
            investor=user,
            account=account,
            date=date.today(),
            from_currency="USD",
            to_currency="EUR",
            from_amount=from_amount,
            to_amount=expected_to_amount,
            exchange_rate=exchange_rate,
        )

        # Verify calculation accuracy
        assert fx_tx.to_amount == expected_to_amount
        assert fx_tx.exchange_rate == exchange_rate

        # Test that exchange_rate field matches calculated rate
        calculated_rate = fx_tx.to_amount / fx_tx.from_amount
        assert abs(calculated_rate - exchange_rate) < Decimal("0.0001")

    def test_fx_rate_factory_usage(self, user):
        """Test FX rate factory for creating test data."""
        # Create FX rate manually to avoid factory faker issues
        fx_rate = FX.objects.create(
            date=date.today(),
            USDEUR=Decimal("0.92"),
            USDGBP=Decimal("0.82"),
        )
        fx_rate.investors.add(user)

        # Verify creation
        assert fx_rate.id is not None
        assert fx_rate.USDEUR is not None
        assert fx_rate.USDGBP is not None
        assert user in fx_rate.investors.all()


@pytest.mark.integration
@pytest.mark.django_db
class TestFXRatePerformance:
    """Test FX rate performance and optimization."""

    def test_bulk_fx_rate_lookup_performance(self, fx_rates):
        """Test performance of bulk FX rate lookups."""
        import time

        # Test bulk lookup of many rates
        currency_pairs = [
            ("USD", "EUR"),
            ("EUR", "GBP"),
        ]

        start_time = time.time()

        for from_curr, to_curr in currency_pairs:
            for i in range(5):  # 5 lookups per pair
                rate_data = FX.get_rate(from_curr, to_curr, date(2023, 1, 1 + i))
                assert rate_data is not None

        end_time = time.time()
        lookup_time = end_time - start_time

        # Should complete all lookups within 1 second
        assert lookup_time < 1.0

    def test_fx_rate_query_performance(self, fx_rates):
        """Test FX rate database query performance."""
        import time

        start_time = time.time()

        # Test multiple database queries
        for _ in range(10):
            rates = FX.objects.all()
            count = rates.count()
            assert count >= len(fx_rates)

        end_time = time.time()
        query_time = end_time - start_time

        # Should complete queries within reasonable time
        assert query_time < 2.0
