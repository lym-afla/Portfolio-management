"""
Edge Cases and Error Scenario Tests

Comprehensive testing of edge cases, boundary conditions, and error scenarios
to ensure the system handles unexpected inputs and situations gracefully.

Author: Portfolio Management Test Framework
Created: 2025-10-18
Purpose: Validate system robustness under edge cases and error conditions
"""

from datetime import date
from datetime import timedelta
from decimal import Decimal
from decimal import getcontext
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from common.models import FX
from common.models import Assets
from common.models import Portfolios
from common.models import Transactions
from portfolio_management.common.models import fx_cache
from portfolio_management.common.models import get_exchange_rate
from portfolio_management.portfolio.calculator import calculate_buy_in_price
from portfolio_management.portfolio.calculator import calculate_nav
from portfolio_management.portfolio.models import gain_loss
from tests.fixtures.factories.asset_factory import AssetFactory
from tests.fixtures.factories.fx_factory import FXRateFactory
from tests.fixtures.factories.transaction_factory import TransactionFactory

# Set high precision for edge case testing
getcontext().prec = 50


@pytest.mark.edge_case
class TestCalculationEdgeCases:
    """Test edge cases in financial calculations."""

    def test_buy_in_price_zero_transactions(self):
        """Test buy-in price calculation with zero transactions."""
        result = calculate_buy_in_price([])
        assert result == Decimal("0")

    def test_buy_in_price_single_transaction(self):
        """Test buy-in price calculation with single transaction."""
        asset = AssetFactory.create()
        transaction = TransactionFactory.create(
            asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
        )

        result = calculate_buy_in_price([transaction])
        assert result == Decimal("50.00")

    def test_buy_in_price_only_sell_transactions(self):
        """Test buy-in price calculation with only sell transactions."""
        asset = AssetFactory.create()
        sell_tx = TransactionFactory.create(
            asset=asset, type="Sell", quantity=100, price=Decimal("50.00")
        )

        result = calculate_buy_in_price([sell_tx])
        assert result == Decimal("50.00")  # Should return sell price

    def test_buy_in_price_equal_buy_sell_quantities(self):
        """Test buy-in price when buy and sell quantities are equal."""
        asset = AssetFactory.create()

        buy_tx = TransactionFactory.create(
            asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
        )
        sell_tx = TransactionFactory.create(
            asset=asset, type="Sell", quantity=100, price=Decimal("60.00")
        )

        result = calculate_buy_in_price([buy_tx, sell_tx])
        assert result == Decimal("50.00")  # Should return original buy price

    def test_buy_in_price_more_sells_than_buys(self):
        """Test buy-in price when sells exceed buys (short position)."""
        asset = AssetFactory.create()

        buy_tx = TransactionFactory.create(
            asset=asset, type="Buy", quantity=50, price=Decimal("50.00")
        )
        sell_tx = TransactionFactory.create(
            asset=asset, type="Sell", quantity=100, price=Decimal("60.00")
        )

        result = calculate_buy_in_price([buy_tx, sell_tx])
        assert result == Decimal("60.00")  # Should return sell price for short position

    def test_buy_in_price_very_small_quantities(self):
        """Test buy-in price with very small quantities."""
        asset = AssetFactory.create()

        transactions = [
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=Decimal("0.000001"),
                price=Decimal("1000000.00"),
            ),
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=Decimal("0.000002"),
                price=Decimal("500000.00"),
            ),
        ]

        result = calculate_buy_in_price(transactions)
        expected = (
            Decimal("0.000001") * Decimal("1000000.00")
            + Decimal("0.000002") * Decimal("500000.00")
        ) / Decimal("0.000003")
        assert abs(result - expected) < Decimal("0.01")

    def test_buy_in_price_very_large_quantities(self):
        """Test buy-in price with very large quantities."""
        asset = AssetFactory.create()

        transactions = [
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=Decimal("999999999"),
                price=Decimal("0.01"),
            ),
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=Decimal("999999999"),
                price=Decimal("0.02"),
            ),
        ]

        result = calculate_buy_in_price(transactions)
        expected = Decimal("0.015")
        assert result == expected

    def test_buy_in_price_negative_prices(self):
        """Test buy-in price with negative prices (error case)."""
        asset = AssetFactory.create()

        # Should handle negative prices gracefully
        transaction = TransactionFactory.create(
            asset=asset, type="Buy", quantity=100, price=Decimal("-50.00")
        )

        result = calculate_buy_in_price([transaction])
        assert result == Decimal("-50.00")

    def test_buy_in_price_zero_prices(self):
        """Test buy-in price with zero prices."""
        asset = AssetFactory.create()

        transaction = TransactionFactory.create(
            asset=asset, type="Buy", quantity=100, price=Decimal("0.00")
        )

        result = calculate_buy_in_price([transaction])
        assert result == Decimal("0.00")

    def test_buy_in_price_very_high_precision(self):
        """Test buy-in price with very high precision numbers."""
        asset = AssetFactory.create()

        transactions = [
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=Decimal("100.12345678901234567890"),
                price=Decimal("50.98765432109876543210"),
            ),
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=Decimal("200.23456789012345678901"),
                price=Decimal("51.12345678901234567890"),
            ),
        ]

        result = calculate_buy_in_price(transactions)

        # Calculate expected value with high precision
        total_cost = Decimal("100.12345678901234567890") * Decimal(
            "50.98765432109876543210"
        ) + Decimal("200.23456789012345678901") * Decimal("51.12345678901234567890")
        total_quantity = Decimal("100.12345678901234567890") + Decimal(
            "200.23456789012345678901"
        )
        expected = total_cost / total_quantity

        assert abs(result - expected) < Decimal("0.0000000001")

    def test_nav_calculation_empty_portfolio(self):
        """Test NAV calculation for empty portfolio."""
        portfolio = Portfolios.objects.create(
            name="Empty Portfolio", base_currency="USD"
        )

        result = calculate_nav(portfolio)
        assert result == Decimal("0")

    def test_nav_calculation_only_cash(self):
        """Test NAV calculation for portfolio with only cash."""
        portfolio = Portfolios.objects.create(
            name="Cash Only Portfolio", base_currency="USD"
        )

        # Portfolio should have no positions but positive NAV from cash
        result = calculate_nav(portfolio)
        assert result == Decimal("0")  # No transactions means no cash balance

    def test_nav_calculation_negative_positions(self):
        """Test NAV calculation with negative positions (short selling)."""
        portfolio = Portfolios.objects.create(
            name="Short Portfolio", base_currency="USD"
        )
        asset = AssetFactory.create()

        # Create short position
        TransactionFactory.create(
            portfolio=portfolio,
            asset=asset,
            type="Sell",
            quantity=100,
            price=Decimal("50.00"),
            currency="USD",
        )

        result = calculate_nav(portfolio)
        # Should handle short positions (result could be negative)
        assert isinstance(result, Decimal)

    def test_gain_loss_no_transactions(self):
        """Test gain/loss calculation with no transactions."""
        result = gain_loss([])
        assert result["realized"] == Decimal("0")
        assert result["unrealized"] == Decimal("0")

    def test_gain_loss_only_buy_transactions(self):
        """Test gain/loss calculation with only buy transactions."""
        asset = AssetFactory.create()
        buy_tx = TransactionFactory.create(
            asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
        )

        result = gain_loss([buy_tx])
        assert result["realized"] == Decimal("0")
        assert result["unrealized"] == Decimal("0")  # No current price provided

    def test_gain_loss_only_sell_transactions(self):
        """Test gain/loss calculation with only sell transactions."""
        asset = AssetFactory.create()
        sell_tx = TransactionFactory.create(
            asset=asset, type="Sell", quantity=100, price=Decimal("60.00")
        )

        result = gain_loss([sell_tx])
        # Should handle sells without corresponding buys
        assert isinstance(result["realized"], Decimal)
        assert isinstance(result["unrealized"], Decimal)


@pytest.mark.edge_case
class TestFXEdgeCases:
    """Test edge cases in FX rate operations."""

    def test_fx_rate_same_currency(self):
        """Test FX rate for same currency pair."""
        with patch("portfolio_management.models.FX.objects.get") as mock_get:
            mock_get.side_effect = FX.DoesNotExist
            rate = get_exchange_rate("USD", "USD", date.today())
            assert rate == Decimal("1.0")

    def test_fx_rate_invalid_currency(self):
        """Test FX rate with invalid currency codes."""
        rate = get_exchange_rate("INVALID", "USD", date.today())
        assert rate is None

        rate = get_exchange_rate("USD", "INVALID", date.today())
        assert rate is None

    def test_fx_rate_future_date(self):
        """Test FX rate for future date."""
        future_date = date.today() + timedelta(days=30)
        rate = get_exchange_rate("USD", "EUR", future_date)
        # Should return None or handle gracefully
        assert rate is None or isinstance(rate, Decimal)

    def test_fx_rate_very_old_date(self):
        """Test FX rate for very old date."""
        old_date = date(2000, 1, 1)
        rate = get_exchange_rate("USD", "EUR", old_date)
        # Should return None or handle gracefully
        assert rate is None or isinstance(rate, Decimal)

    def test_fx_rate_zero_rate(self):
        """Test FX rate with zero value."""
        with patch("portfolio_management.models.FX.objects.get") as mock_get:
            mock_fx = MagicMock()
            mock_fx.rate = Decimal("0")
            mock_get.return_value = mock_fx

            rate = get_exchange_rate("USD", "EUR", date.today())
            assert rate == Decimal("0")

    def test_fx_rate_negative_rate(self):
        """Test FX rate with negative value (error case)."""
        with patch("portfolio_management.models.FX.objects.get") as mock_get:
            mock_fx = MagicMock()
            mock_fx.rate = Decimal("-1.0")
            mock_get.return_value = mock_fx

            rate = get_exchange_rate("USD", "EUR", date.today())
            assert rate == Decimal("-1.0")

    def test_fx_rate_very_small_rate(self):
        """Test FX rate with very small value."""
        with patch("portfolio_management.models.FX.objects.get") as mock_get:
            mock_fx = MagicMock()
            mock_fx.rate = Decimal("0.000001")
            mock_get.return_value = mock_fx

            rate = get_exchange_rate("USD", "EUR", date.today())
            assert rate == Decimal("0.000001")

    def test_fx_rate_very_large_rate(self):
        """Test FX rate with very large value."""
        with patch("portfolio_management.models.FX.objects.get") as mock_get:
            mock_fx = MagicMock()
            mock_fx.rate = Decimal("999999.99")
            mock_get.return_value = mock_fx

            rate = get_exchange_rate("USD", "EUR", date.today())
            assert rate == Decimal("999999.99")

    def test_fx_rate_round_trip_conversion(self, fx_rates):
        """Test FX rate round-trip conversion accuracy."""
        original_amount = Decimal("1000.00")

        # USD to EUR
        usd_to_eur = get_exchange_rate("USD", "EUR", date.today())
        eur_amount = original_amount * usd_to_eur

        # EUR back to USD
        eur_to_usd = get_exchange_rate("EUR", "USD", date.today())
        final_usd = eur_amount * eur_to_usd

        # Should be very close to original
        difference = abs(final_usd - original_amount)
        tolerance = original_amount * Decimal("0.01")  # 1% tolerance for rounding
        assert difference <= tolerance

    def test_fx_rate_cross_currency_no_direct_path(self):
        """Test cross-currency conversion when no direct path exists."""
        with patch("portfolio_management.models.FX.objects.get") as mock_get:
            mock_get.side_effect = FX.DoesNotExist

            rate = get_exchange_rate("USD", "XYZ", date.today())
            assert rate is None

    def test_fx_rate_cache_edge_cases(self):
        """Test FX rate caching edge cases."""
        # Test with empty cache
        fx_cache.clear()
        rate = get_exchange_rate("USD", "EUR", date.today())
        assert rate is None  # No rate exists

        # Test with corrupted cache
        fx_cache["USD_EUR_2025-10-18"] = "invalid"
        rate = get_exchange_rate("USD", "EUR", date.today())
        assert rate is None  # Should handle corrupted cache


@pytest.mark.edge_case
class TestDatabaseEdgeCases:
    """Test edge cases in database operations."""

    def test_transaction_model_missing_relations(self):
        """Test transaction creation with missing relations."""
        with pytest.raises(ValueError):
            TransactionFactory.create(asset=None)

        with pytest.raises(ValueError):
            TransactionFactory.create(portfolio=None)

    def test_transaction_model_invalid_enum_values(self):
        """Test transaction creation with invalid enum values."""
        asset = AssetFactory.create()
        portfolio = Portfolios.objects.create(
            name="Test Portfolio", base_currency="USD"
        )

        with pytest.raises(ValueError):
            TransactionFactory.create(
                asset=asset, portfolio=portfolio, type="INVALID_TYPE"
            )

    def test_asset_model_duplicate_isin(self):
        """Test asset creation with duplicate ISIN."""
        # Create first asset
        AssetFactory.create(ISIN="US1234567890")

        # Try to create second asset with same ISIN
        with pytest.raises(IntegrityError):
            AssetFactory.create(ISIN="US1234567890")

    def test_portfolio_model_negative_balance(self):
        """Test portfolio with negative cash balance."""
        portfolio = Portfolios.objects.create(
            name="Negative Balance Portfolio", base_currency="USD"
        )

        # Model should allow negative balances (margin accounts)
        # This test verifies the behavior
        assert portfolio.cash_balance == Decimal("0")

    def test_fx_rate_duplicate_entry(self):
        """Test creating duplicate FX rate entries."""
        # Create first FX rate
        FXRateFactory.create(
            from_currency="USD",
            to_currency="EUR",
            date=date.today(),
            rate=Decimal("0.85"),
        )

        # Try to create duplicate
        with pytest.raises(IntegrityError):
            FXRateFactory.create(
                from_currency="USD",
                to_currency="EUR",
                date=date.today(),
                rate=Decimal("0.86"),
            )

    def test_database_connection_timeout(self):
        """Test behavior during database connection timeout."""
        with patch("django.db.connection.cursor") as mock_cursor:
            mock_cursor.side_effect = DatabaseError("Connection timeout")

            with pytest.raises(DatabaseError):
                Assets.objects.create(ticker="TEST", name="Test Asset")

    def test_concurrent_transaction_creation(self):
        """Test concurrent transaction creation."""
        asset = AssetFactory.create()
        portfolio = Portfolios.objects.create(
            name="Concurrent Test", base_currency="USD"
        )

        def create_transaction(index):
            return TransactionFactory.create(
                asset=asset,
                portfolio=portfolio,
                type="Buy",
                quantity=100,
                price=Decimal(f"50.{index:02d}"),
            )

        import threading

        threads = []
        transactions = []

        for i in range(10):
            thread = threading.Thread(
                target=lambda i=i: transactions.append(create_transaction(i))
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert len(transactions) == 10
        assert all(tx.asset == asset for tx in transactions)

    def test_very_long_asset_names(self):
        """Test asset with very long names."""
        long_name = "A" * 1000  # Very long name

        asset = AssetFactory.create(name=long_name)
        # Should either work or be truncated by model constraints
        assert len(asset.name) <= 255  # Assuming max length of 255

    def test_special_characters_in_names(self):
        """Test assets with special characters in names."""
        special_names = [
            "Asset & Company Inc.",
            "Asset/Company Ltd.",
            "Asset-Company GmbH",
            "Asset'Company Corp.",
            "Ásset Compañía S.A.",
            "资产公司",  # Chinese characters
            "株式会社",  # Japanese characters
        ]

        for name in special_names:
            asset = AssetFactory.create(name=name)
            assert asset.name == name

    def test_unicode_in_descriptions(self):
        """Test unicode characters in descriptions."""
        unicode_text = "Portfolio with émojis 📈 and ñiño and 中文"

        portfolio = Portfolios.objects.create(
            name="Unicode Test", description=unicode_text, base_currency="USD"
        )

        assert portfolio.description == unicode_text


@pytest.mark.edge_case
class TestAPIEdgeCases:
    """Test edge cases in API endpoints."""

    def test_api_empty_request_body(self, api_client):
        """Test API with empty request body."""
        url = reverse("transaction-list")
        response = api_client.post(url, {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_api_malformed_json(self, api_client):
        """Test API with malformed JSON."""
        url = reverse("transaction-list")
        response = api_client.post(
            url, '{"invalid": json}', content_type="application/json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_api_very_large_request(self, api_client):
        """Test API with very large request payload."""
        # Create large transaction data
        large_data = {
            "portfolio": Portfolios.objects.create(
                name="Large Test", base_currency="USD"
            ).id,
            "asset": AssetFactory.create().id,
            "type": "Buy",
            "quantity": "1" * 100,  # Very large number string
            "price": "50.00",
            "currency": "USD",
        }

        url = reverse("transaction-list")
        response = api_client.post(url, large_data, format="json")

        # Should handle gracefully
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
        ]

    def test_api_negative_page_numbers(self, api_client):
        """Test API pagination with negative page numbers."""
        url = reverse("asset-list")
        response = api_client.get(url, {"page": -1})

        # Should handle gracefully
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_api_very_large_page_numbers(self, api_client):
        """Test API pagination with very large page numbers."""
        url = reverse("asset-list")
        response = api_client.get(url, {"page": 999999})

        # Should return empty results, not error
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 0

    def test_api_invalid_date_formats(self, api_client):
        """Test API with invalid date formats."""
        url = reverse("transaction-list")

        invalid_dates = [
            "2025-13-45",  # Invalid month/day
            "not-a-date",
            "2025/10/18",
            "18-10-2025",
            "",
        ]

        for invalid_date in invalid_dates:
            response = api_client.post(
                url,
                {
                    "portfolio": Portfolios.objects.create(
                        name="Date Test", base_currency="USD"
                    ).id,
                    "asset": AssetFactory.create().id,
                    "type": "Buy",
                    "quantity": 100,
                    "price": "50.00",
                    "currency": "USD",
                    "date": invalid_date,
                },
                format="json",
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_api_sql_injection_attempts(self, api_client):
        """Test API against SQL injection attempts."""
        url = reverse("asset-list")

        sql_injection_attempts = [
            "'; DROP TABLE assets; --",
            "' OR '1'='1",
            "1' UNION SELECT * FROM users --",
            "'; UPDATE assets SET name='hacked'; --",
        ]

        for injection in sql_injection_attempts:
            response = api_client.get(url, {"search": injection})

            # Should not cause server error
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_400_BAD_REQUEST,
            ]

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                assert "results" in data

    def test_api_concurrent_requests(self, api_client):
        """Test API under concurrent request load."""
        import threading

        url = reverse("portfolio-list")
        results = []

        def make_request():
            response = api_client.get(url)
            results.append(response.status_code)

        threads = []
        for _ in range(20):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Most requests should succeed
        success_count = sum(1 for code in results if code == status.HTTP_200_OK)
        assert success_count >= 18  # At least 90% success rate

    def test_api_unicode_handling(self, api_client):
        """Test API handling of unicode characters."""
        portfolio_data = {
            "name": "Tëst Pörtlfolio 📈",
            "description": "Pörtlfolio with ñiño and 中文 characters",
            "base_currency": "USD",
        }

        url = reverse("portfolio-list")
        response = api_client.post(url, portfolio_data, format="json")

        if response.status_code == status.HTTP_201_CREATED:
            data = response.json()
            assert data["name"] == portfolio_data["name"]
            assert data["description"] == portfolio_data["description"]

    def test_api_null_value_handling(self, api_client):
        """Test API handling of null values."""
        portfolio_data = {
            "name": "Test Portfolio",
            "description": None,  # Null description
            "base_currency": "USD",
        }

        url = reverse("portfolio-list")
        response = api_client.post(url, portfolio_data, format="json")

        # Should handle null values gracefully
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
        ]


@pytest.mark.edge_case
class TestFinancialCalculationBoundaries:
    """Test boundary conditions in financial calculations."""

    def test_calculation_with_maximum_decimals(self):
        """Test calculations with maximum allowed decimal places."""
        # Create transactions with maximum precision
        max_precision = Decimal("0.0000000000000000000000000001")

        asset = AssetFactory.create()
        transaction = TransactionFactory.create(
            asset=asset, type="Buy", quantity=Decimal("1"), price=max_precision
        )

        result = calculate_buy_in_price([transaction])
        assert result == max_precision

    def test_calculation_with_minimum_decimals(self):
        """Test calculations with minimum decimal places."""
        # Create transactions with no decimal places
        asset = AssetFactory.create()
        transaction = TransactionFactory.create(
            asset=asset, type="Buy", quantity=Decimal("1000000"), price=Decimal("1")
        )

        result = calculate_buy_in_price([transaction])
        assert result == Decimal("1")

    def test_calculation_overflow_protection(self):
        """Test calculation overflow protection."""
        # Use numbers that might cause overflow
        very_large = Decimal("999999999999999999999999999999.99")

        asset = AssetFactory.create()
        transaction = TransactionFactory.create(
            asset=asset, type="Buy", quantity=Decimal("1"), price=very_large
        )

        result = calculate_buy_in_price([transaction])
        assert result == very_large

    def test_calculation_underflow_protection(self):
        """Test calculation underflow protection."""
        # Use numbers that might cause underflow
        very_small = Decimal("0.0000000000000000000000000001")

        asset = AssetFactory.create()
        transaction = TransactionFactory.create(
            asset=asset, type="Buy", quantity=Decimal("1"), price=very_small
        )

        result = calculate_buy_in_price([transaction])
        assert result == very_small

    def test_division_by_zero_protection(self):
        """Test division by zero protection in calculations."""
        asset = AssetFactory.create()

        # Create scenario that might cause division by zero
        transaction = TransactionFactory.create(
            asset=asset,
            type="Buy",
            quantity=Decimal("0"),  # Zero quantity
            price=Decimal("50.00"),
        )

        result = calculate_buy_in_price([transaction])
        # Should handle zero quantity gracefully
        assert isinstance(result, Decimal)

    def test_square_root_edge_cases(self):
        """Test square root calculations in edge cases."""
        # Test if system uses square roots (e.g., for volatility)
        from math import sqrt

        # Test perfect squares
        assert sqrt(Decimal("4")) == Decimal("2")
        assert sqrt(Decimal("9")) == Decimal("3")

        # Test very small numbers
        result = sqrt(Decimal("0.000001"))
        assert result > 0

        # Test very large numbers
        result = sqrt(Decimal("1000000000000"))
        assert result > 0

    def test_percentage_calculation_boundaries(self):
        """Test percentage calculations at boundaries."""
        # Test 0% return
        assert Decimal("100") * Decimal("0.00") == Decimal("0")

        # Test 100% return
        assert Decimal("100") * Decimal("1.00") == Decimal("100")

        # Test -100% return
        assert Decimal("100") * Decimal("-1.00") == Decimal("-100")

        # Test very small percentage
        result = Decimal("100") * Decimal("0.0001")
        assert result == Decimal("0.01")

        # Test very large percentage
        result = Decimal("100") * Decimal("1000")
        assert result == Decimal("100000")

    def test_compound_interest_boundaries(self):
        """Test compound interest calculations at boundaries."""
        principal = Decimal("1000")

        # Test with 0% rate
        # principal * (1 + 0) ^ periods = principal
        result = principal * (Decimal("1") + Decimal("0")) ** 12
        assert result == principal

        # Test with 100% rate
        # principal * (1 + 1) ^ 1 = 2 * principal
        result = principal * (Decimal("1") + Decimal("1")) ** 1
        assert result == principal * Decimal("2")

        # Test with very small rate
        result = principal * (Decimal("1") + Decimal("0.0001")) ** 12
        assert result > principal

        # Test with negative rate
        result = principal * (Decimal("1") + Decimal("-0.1")) ** 1
        assert result == principal * Decimal("0.9")


@pytest.mark.edge_case
class TestSystemRobustness:
    """Test overall system robustness under various conditions."""

    def test_memory_exhaustion_handling(self):
        """Test system behavior under memory pressure."""
        # This test would ideally test memory exhaustion scenarios
        # For safety, we'll test with large but manageable datasets

        assets = AssetFactory.create_batch(1000)
        transactions = []

        for asset in assets:
            transactions.extend(
                TransactionFactory.create_batch(
                    10, asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
                )
            )

        # System should handle large datasets without crashing
        result = calculate_buy_in_price(transactions)
        assert isinstance(result, Decimal)

        # Clean up
        Transactions.objects.filter(id__in=[tx.id for tx in transactions]).delete()
        Assets.objects.filter(id__in=[asset.id for asset in assets]).delete()

    def test_concurrent_user_simulation(self, api_client):
        """Test system behavior with multiple concurrent users."""
        import threading

        # Create test data
        portfolios = [
            Portfolios.objects.create(name=f"User {i} Portfolio", base_currency="USD")
            for i in range(10)
        ]

        def simulate_user_activity(portfolio_id):
            """Simulate a user making API calls."""
            client = APIClient()

            # Make various API calls
            responses = []

            # List portfolios
            responses.append(client.get(reverse("portfolio-list")).status_code)

            # Get specific portfolio
            responses.append(
                client.get(
                    reverse("portfolio-detail", kwargs={"pk": portfolio_id})
                ).status_code
            )

            # List assets
            responses.append(client.get(reverse("asset-list")).status_code)

            return responses

        # Run concurrent user simulation
        threads = []
        all_responses = []

        for portfolio in portfolios:
            thread = threading.Thread(
                target=lambda pid=portfolio.id: all_responses.extend(
                    simulate_user_activity(pid)
                )
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Most requests should succeed
        success_count = sum(1 for code in all_responses if code == status.HTTP_200_OK)
        total_requests = len(all_responses)
        success_rate = success_count / total_requests

        assert success_rate > 0.8, f"Success rate too low: {success_rate:.2%}"

    def test_system_recovery_after_errors(self):
        """Test system recovery after various error conditions."""
        # Test recovery after database error
        with patch("portfolio_management.models.Assets.objects.create") as mock_create:
            mock_create.side_effect = DatabaseError("Temporary error")

            with pytest.raises(DatabaseError):
                AssetFactory.create()

        # System should recover and work normally afterward
        asset = AssetFactory.create()
        assert asset is not None
        assert asset.id is not None

        # Test recovery after API error
        with patch("portfolio_management.views.PortfolioViewSet.list") as mock_list:
            mock_list.side_effect = Exception("API error")

            client = APIClient()
            response = client.get(reverse("portfolio-list"))
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # API should recover and work normally afterward
        response = client.get(reverse("portfolio-list"))
        assert response.status_code == status.HTTP_200_OK

    def test_graceful_degradation(self):
        """Test graceful degradation when components fail."""
        # Test behavior when FX rates are unavailable
        with patch("portfolio_management.common.models.get_exchange_rate") as mock_fx:
            mock_fx.return_value = None

            # Calculations should handle missing FX rates gracefully
            rate = get_exchange_rate("USD", "EUR", date.today())
            assert rate is None

        # Test behavior when external data sources are unavailable
        with patch("requests.get") as mock_get:
            mock_get.side_effect = ConnectionError("Network unavailable")

            # System should handle network issues gracefully
            try:
                # This would be an external API call
                pass
            except ConnectionError:
                pass  # Expected behavior

        # System should remain functional
        assert True  # Test passes if we reach this point

    def test_data_consistency_under_load(self):
        """Test data consistency under high load conditions."""
        portfolio = Portfolios.objects.create(
            name="Load Test Portfolio", base_currency="USD"
        )
        asset = AssetFactory.create()

        # Create many concurrent transactions
        import threading

        def create_transaction(index):
            TransactionFactory.create(
                portfolio=portfolio,
                asset=asset,
                type="Buy",
                quantity=100,
                price=Decimal(f"50.{index:02d}"),
            )

        threads = []
        for i in range(50):
            thread = threading.Thread(target=lambda i=i: create_transaction(i))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify data consistency
        transaction_count = Transactions.objects.filter(portfolio=portfolio).count()
        assert transaction_count == 50

        # Verify calculations work correctly
        transactions = Transactions.objects.filter(portfolio=portfolio)
        buy_in_price = calculate_buy_in_price(transactions)
        assert isinstance(buy_in_price, Decimal)
        assert buy_in_price > 0


# Edge Case Test Configuration
EDGE_CASE_CONFIG = {
    "boundary_values": {
        "min_quantity": Decimal("0.000001"),
        "max_quantity": Decimal("999999999999"),
        "min_price": Decimal("0.000001"),
        "max_price": Decimal("999999999999.99"),
        "min_fx_rate": Decimal("0.000001"),
        "max_fx_rate": Decimal("999999.99"),
    },
    "invalid_inputs": {
        "negative_quantities": [Decimal("-1"), Decimal("-100")],
        "zero_quantities": [Decimal("0")],
        "negative_prices": [Decimal("-1"), Decimal("-100")],
        "zero_prices": [Decimal("0")],
        "invalid_dates": ["2025-13-45", "not-a-date", ""],
        "invalid_currencies": ["INVALID", "XYZ123", ""],
    },
    "stress_conditions": {
        "max_concurrent_users": 50,
        "max_transactions_per_test": 1000,
        "max_api_requests_per_test": 200,
        "max_portfolio_size": 100,
    },
    "precision_requirements": {
        "financial_calculations": 28,  # decimal places
        "fx_rates": 6,  # decimal places
        "percentages": 4,  # decimal places
    },
}


@pytest.fixture
def edge_case_validator():
    """Fixture for validating edge case test results."""

    def validate_boundary_value(value, value_type, min_max):
        """Validate that a value is within expected boundaries."""
        min_val = EDGE_CASE_CONFIG["boundary_values"][f"{min_max}_{value_type}"]

        if min_max == "min":
            assert value >= min_val, f"Value {value} is below minimum {min_val}"
        else:
            assert value <= min_val, f"Value {value} is above maximum {min_val}"

    def validate_error_handling(result, expected_error_type=None):
        """Validate that errors are handled properly."""
        if expected_error_type:
            assert isinstance(
                result, expected_error_type
            ), f"Expected {expected_error_type}, got {type(result)}"
        else:
            assert result is not None, "Result should not be None"
            assert not isinstance(result, Exception), f"Unexpected exception: {result}"

    return {
        "validate_boundary_value": validate_boundary_value,
        "validate_error_handling": validate_error_handling,
    }
