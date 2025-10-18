"""
FX Integration Tests

Integration tests for FX rate functionality, including:
- FX rate API integration
- Cross-currency transaction processing
- FX rate caching and performance
- Historical FX rate accuracy
- Real-time FX rate updates
- Error handling in FX operations

Author: Portfolio Management Test Framework
Created: 2025-10-18
Purpose: Validate FX rate integration across the system
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status

from common.models import FX, Assets
from portfolio_management.common.models import (
    fx_cache,
    get_exchange_rate,
    update_fx_rate,
)
from tests.fixtures.factories.fx_factory import FXRateFactory


@pytest.mark.integration
class TestFXRateAPIIntegration:
    """Test FX rate API integration functionality."""

    def test_fx_rate_endpoint_success(self, api_client, fx_rates):
        """Test successful FX rate API endpoint call."""
        url = reverse("fx-rates")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "results" in data
        assert len(data["results"]) >= len(fx_rates)

        # Check structure of returned data
        for fx_data in data["results"]:
            assert "date" in fx_data
            assert "from_currency" in fx_data
            assert "to_currency" in fx_data
            assert "rate" in fx_data

    def test_fx_rate_endpoint_filtering(self, api_client, fx_rates):
        """Test FX rate endpoint with filtering parameters."""
        url = reverse("fx-rates")

        # Test currency pair filtering
        response = api_client.get(url, {"from_currency": "USD", "to_currency": "EUR"})
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "results" in data
        for fx_data in data["results"]:
            assert fx_data["from_currency"] == "USD"
            assert fx_data["to_currency"] == "EUR"

    def test_fx_rate_endpoint_date_range(self, api_client, fx_rates):
        """Test FX rate endpoint with date range filtering."""
        url = reverse("fx-rates")

        # Test date range filtering
        start_date = (date.today() - timedelta(days=10)).isoformat()
        end_date = date.today().isoformat()

        response = api_client.get(url, {"start_date": start_date, "end_date": end_date})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "results" in data

    def test_fx_rate_endpoint_cross_currency(self, api_client, fx_rates):
        """Test FX rate endpoint for cross-currency calculations."""
        url = reverse("fx-rates-cross")

        response = api_client.get(
            url,
            {
                "from_currency": "GBP",
                "to_currency": "JPY",
                "date": date.today().isoformat(),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "rate" in data
        assert "from_currency" in data
        assert "to_currency" in data
        assert isinstance(Decimal(data["rate"]), Decimal)

    def test_fx_rate_bulk_update(self, admin_client, fx_rates):
        """Test bulk FX rate update functionality."""
        url = reverse("fx-rates-bulk-update")

        bulk_data = [
            {
                "date": date.today().isoformat(),
                "from_currency": "USD",
                "to_currency": "EUR",
                "rate": "0.8500",
            },
            {
                "date": date.today().isoformat(),
                "from_currency": "EUR",
                "to_currency": "GBP",
                "rate": "0.8700",
            },
        ]

        response = admin_client.post(url, bulk_data, format="json")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "updated_count" in data
        assert data["updated_count"] == 2

    def test_fx_rate_validation_errors(self, api_client):
        """Test FX rate endpoint validation errors."""
        url = reverse("fx-rates")

        # Test invalid currency code
        response = api_client.get(url, {"from_currency": "INVALID"})
        assert response.status_code == status.HTTP_400_BAD_ERROR

        # Test invalid date format
        response = api_client.get(url, {"start_date": "2025-13-45"})
        assert response.status_code == status.HTTP_400_BAD_ERROR

    def test_fx_rate_performance(self, api_client, fx_rates):
        """Test FX rate endpoint performance with large datasets."""
        url = reverse("fx-rates")

        import time

        start_time = time.time()

        response = api_client.get(url)

        end_time = time.time()
        response_time = end_time - start_time

        assert response.status_code == status.HTTP_200_OK
        # Should respond within 2 seconds even with large datasets
        assert response_time < 2.0


@pytest.mark.integration
class TestFXRateCalculationIntegration:
    """Test FX rate calculations in real-world scenarios."""

    def test_get_exchange_rate_direct(self, fx_rates):
        """Test direct FX rate retrieval."""
        rate = get_exchange_rate("USD", "EUR", date.today())

        assert rate is not None
        assert isinstance(rate, Decimal)
        assert rate > 0

        # Compare with database rate
        fx_rate = FX.objects.get(
            from_currency="USD", to_currency="EUR", date=date.today()
        )
        assert rate == fx_rate.rate

    def test_get_exchange_rate_cross(self, fx_rates):
        """Test cross-currency FX rate calculation."""
        rate = get_exchange_rate("GBP", "JPY", date.today())

        assert rate is not None
        assert isinstance(rate, Decimal)
        assert rate > 0

        # Verify cross-currency calculation
        # GBP -> USD -> JPY
        gbp_to_usd = get_exchange_rate("GBP", "USD", date.today())
        usd_to_jpy = get_exchange_rate("USD", "JPY", date.today())
        expected_rate = gbp_to_usd * usd_to_jpy

        # Allow for small rounding differences
        assert abs(rate - expected_rate) < Decimal("0.0001")

    def test_get_exchange_rate_historical(self, fx_rates):
        """Test historical FX rate retrieval."""
        historical_date = date.today() - timedelta(days=5)
        rate = get_exchange_rate("USD", "EUR", historical_date)

        assert rate is not None
        assert isinstance(rate, Decimal)
        assert rate > 0

    def test_get_exchange_rate_interpolation(self, fx_rates):
        """Test FX rate interpolation for missing dates."""
        # Request rate for a date that might not exist
        target_date = date.today() - timedelta(days=3)
        rate = get_exchange_rate("USD", "EUR", target_date)

        assert rate is not None
        assert isinstance(rate, Decimal)
        assert rate > 0

    def test_get_exchange_rate_cache_efficiency(self, fx_rates):
        """Test FX rate caching functionality."""
        # Clear cache
        fx_cache.clear()

        # First call should hit database
        rate1 = get_exchange_rate("USD", "EUR", date.today())
        assert rate1 is not None

        # Second call should use cache
        rate2 = get_exchange_rate("USD", "EUR", date.today())
        assert rate2 == rate1

        # Verify cache contains the rate
        cache_key = f"USD_EUR_{date.today()}"
        assert cache_key in fx_cache

    def test_update_fx_rate_new(self, fx_rates):
        """Test updating a new FX rate."""
        new_rate = Decimal("1.2500")
        success = update_fx_rate("CHF", "USD", date.today(), new_rate)

        assert success is True

        # Verify rate was saved
        fx_obj = FX.objects.get(
            from_currency="CHF", to_currency="USD", date=date.today()
        )
        assert fx_obj.rate == new_rate

    def test_update_fx_rate_existing(self, fx_rates):
        """Test updating an existing FX rate."""
        updated_rate = Decimal("0.9000")
        success = update_fx_rate("USD", "EUR", date.today(), updated_rate)

        assert success is True

        # Verify rate was updated
        fx_obj = FX.objects.get(
            from_currency="USD", to_currency="EUR", date=date.today()
        )
        assert fx_obj.rate == updated_rate

    def test_fx_rate_precision_validation(self, fx_rates):
        """Test FX rate precision and validation."""
        # Test high precision rate
        high_precision_rate = Decimal("1.23456789")
        success = update_fx_rate("USD", "EUR", date.today(), high_precision_rate)

        assert success is True

        # Verify rate is stored with proper precision
        fx_obj = FX.objects.get(
            from_currency="USD", to_currency="EUR", date=date.today()
        )
        assert fx_obj.rate == high_precision_rate

    def test_fx_rate_error_handling(self, fx_rates):
        """Test FX rate error handling."""
        # Test invalid currency code
        rate = get_exchange_rate("INVALID", "EUR", date.today())
        assert rate is None

        # Test zero rate
        success = update_fx_rate("USD", "EUR", date.today(), Decimal("0"))
        assert success is False

        # Test negative rate
        success = update_fx_rate("USD", "EUR", date.today(), Decimal("-1.0"))
        assert success is False


@pytest.mark.integration
class TestTransactionFXIntegration:
    """Test FX rate integration with transaction processing."""

    def test_multi_currency_transaction_flow(
        self, multi_currency_portfolio, fx_rates, api_client
    ):
        """Test transaction flow across multiple currencies."""
        portfolio = multi_currency_portfolio

        # Create transactions in different currencies
        transactions_data = [
            {
                "portfolio": portfolio.id,
                "asset": Assets.objects.get(ticker="AAPL").id,
                "type": "Buy",
                "quantity": 10,
                "price": "150.00",
                "currency": "USD",
                "date": date.today().isoformat(),
            },
            {
                "portfolio": portfolio.id,
                "asset": Assets.objects.get(ticker="VOD").id,
                "type": "Buy",
                "quantity": 100,
                "price": "2.50",
                "currency": "GBP",
                "date": date.today().isoformat(),
            },
        ]

        # Process transactions
        url = reverse("transaction-list")
        for tx_data in transactions_data:
            response = api_client.post(url, tx_data, format="json")
            assert response.status_code == status.HTTP_201_CREATED

        # Verify portfolio valuation includes FX conversion
        url = reverse("portfolio-detail", kwargs={"pk": portfolio.id})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "total_value" in data
        assert "currency" in data
        assert data["total_value"] > 0

    def test_fx_gain_loss_calculation(
        self, multi_currency_portfolio, fx_rates, api_client
    ):
        """Test FX gain/loss calculation in portfolio."""
        portfolio = multi_currency_portfolio

        # Create initial position in foreign currency
        asset = Assets.objects.get(ticker="AAPL")

        # Initial buy transaction
        initial_tx_data = {
            "portfolio": portfolio.id,
            "asset": asset.id,
            "type": "Buy",
            "quantity": 10,
            "price": "150.00",
            "currency": "USD",
            "date": (date.today() - timedelta(days=30)).isoformat(),
        }

        response = api_client.post(
            reverse("transaction-list"), initial_tx_data, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Simulate FX rate change and sell transaction
        new_fx_rate = Decimal("0.9000")
        update_fx_rate("USD", "EUR", date.today(), new_fx_rate)

        sell_tx_data = {
            "portfolio": portfolio.id,
            "asset": asset.id,
            "type": "Sell",
            "quantity": 10,
            "price": "160.00",
            "currency": "USD",
            "date": date.today().isoformat(),
        }

        response = api_client.post(
            reverse("transaction-list"), sell_tx_data, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Check portfolio performance includes FX effect
        url = reverse("portfolio-performance", kwargs={"pk": portfolio.id})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "fx_gain_loss" in data
        assert "total_gain_loss" in data

    def test_dividend_fx_conversion(
        self, multi_currency_portfolio, fx_rates, api_client
    ):
        """Test dividend payment with FX conversion."""
        portfolio = multi_currency_portfolio

        # Create asset that pays dividend in foreign currency
        asset = Assets.objects.get(ticker="AAPL")

        # Create position
        position_tx_data = {
            "portfolio": portfolio.id,
            "asset": asset.id,
            "type": "Buy",
            "quantity": 10,
            "price": "150.00",
            "currency": "USD",
            "date": (date.today() - timedelta(days=10)).isoformat(),
        }

        response = api_client.post(
            reverse("transaction-list"), position_tx_data, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Create dividend transaction
        dividend_tx_data = {
            "portfolio": portfolio.id,
            "asset": asset.id,
            "type": "Dividend",
            "quantity": 0,
            "price": "10.00",  # $1 per share dividend
            "currency": "USD",
            "date": date.today().isoformat(),
        }

        response = api_client.post(
            reverse("transaction-list"), dividend_tx_data, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Verify dividend is converted to portfolio currency
        portfolio_url = reverse("portfolio-detail", kwargs={"pk": portfolio.id})
        response = api_client.get(portfolio_url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "cash_balance" in data

        # Dividend should be converted from USD to EUR at current rate
        expected_dividend_eur = Decimal("10.00") * get_exchange_rate(
            "USD", "EUR", date.today()
        )
        assert data["cash_balance"] >= expected_dividend_eur * Decimal(
            "0.9"
        )  # Allow for rounding

    def test_corporate_action_fx_handling(
        self, multi_currency_portfolio, fx_rates, api_client
    ):
        """Test corporate actions with FX implications."""
        portfolio = multi_currency_portfolio

        # Create position in foreign stock
        asset = Assets.objects.get(ticker="AAPL")

        # Initial position
        tx_data = {
            "portfolio": portfolio.id,
            "asset": asset.id,
            "type": "Buy",
            "quantity": 100,
            "price": "150.00",
            "currency": "USD",
            "date": (date.today() - timedelta(days=20)).isoformat(),
        }

        response = api_client.post(reverse("transaction-list"), tx_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED

        # Simulate stock split (2:1)
        split_tx_data = {
            "portfolio": portfolio.id,
            "asset": asset.id,
            "type": "Split",
            "quantity": 100,  # Additional shares from split
            "price": "0.00",
            "currency": "USD",
            "date": date.today().isoformat(),
        }

        response = api_client.post(
            reverse("transaction-list"), split_tx_data, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Verify position quantity is updated correctly
        url = reverse("portfolio-positions", kwargs={"pk": portfolio.id})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        aapl_position = next(
            (pos for pos in data if pos["asset"]["ticker"] == "AAPL"), None
        )
        assert aapl_position is not None
        assert aapl_position["quantity"] == 200  # Original 100 + 100 from split

    def test_currency_reporting_integration(
        self, multi_currency_portfolio, fx_rates, api_client
    ):
        """Test currency-specific reporting with FX conversion."""
        portfolio = multi_currency_portfolio

        # Create transactions in multiple currencies
        transactions = [
            {"ticker": "AAPL", "currency": "USD", "quantity": 10, "price": "150.00"},
            {"ticker": "VOD", "currency": "GBP", "quantity": 100, "price": "2.50"},
            {"ticker": "SIE", "currency": "EUR", "quantity": 50, "price": "120.00"},
        ]

        for tx in transactions:
            asset = Assets.objects.get(ticker=tx["ticker"])
            tx_data = {
                "portfolio": portfolio.id,
                "asset": asset.id,
                "type": "Buy",
                "quantity": tx["quantity"],
                "price": tx["price"],
                "currency": tx["currency"],
                "date": date.today().isoformat(),
            }

            response = api_client.post(
                reverse("transaction-list"), tx_data, format="json"
            )
            assert response.status_code == status.HTTP_201_CREATED

        # Test currency breakdown report
        url = reverse("portfolio-currency-breakdown", kwargs={"pk": portfolio.id})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "currency_allocation" in data
        assert "total_value_usd" in data
        assert "total_value_eur" in data
        assert "total_value_gbp" in data

        # Verify currency conversion accuracy
        total_usd = Decimal(str(data["total_value_usd"]))
        total_eur = Decimal(str(data["total_value_eur"]))

        # Check conversion consistency
        if total_usd > 0:
            calculated_eur = total_usd * get_exchange_rate("USD", "EUR", date.today())
            assert abs(total_eur - calculated_eur) < total_eur * Decimal(
                "0.01"
            )  # 1% tolerance


@pytest.mark.integration
class TestFXRateDataManagement:
    """Test FX rate data management and maintenance."""

    def test_fx_rate_bulk_import(self, admin_client, fx_rates):
        """Test bulk import of FX rate data."""
        url = reverse("fx-rates-bulk-import")

        # Create CSV data for import
        csv_data = """date,from_currency,to_currency,rate
2025-10-18,USD,EUR,0.8500
2025-10-18,EUR,GBP,0.8700
2025-10-18,USD,JPY,110.50
2025-10-18,GBP,USD,1.1500
"""

        response = admin_client.post(
            url, {"file": ("fx_rates.csv", csv_data, "text/csv")}, format="multipart"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "imported_count" in data
        assert data["imported_count"] == 4

    def test_fx_rate_data_validation(self, admin_client):
        """Test FX rate data validation."""
        url = reverse("fx-rates-bulk-import")

        # Create invalid CSV data
        invalid_csv_data = """date,from_currency,to_currency,rate
2025-10-18,USD,EUR,0.8500
2025-10-18,EUR,INVALID,0.8700
2025-10-18,USD,JPY,-110.50
2025-13-45,GBP,USD,1.1500
"""

        response = admin_client.post(
            url,
            {"file": ("invalid_fx_rates.csv", invalid_csv_data, "text/csv")},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "errors" in data
        assert len(data["errors"]) > 0

    def test_fx_rate_historical_sync(self, admin_client, fx_rates):
        """Test historical FX rate synchronization."""
        url = reverse("fx-rates-sync-historical")

        sync_data = {
            "start_date": (date.today() - timedelta(days=30)).isoformat(),
            "end_date": date.today().isoformat(),
            "currency_pairs": [
                {"from_currency": "USD", "to_currency": "EUR"},
                {"from_currency": "EUR", "to_currency": "GBP"},
                {"from_currency": "USD", "to_currency": "JPY"},
            ],
        }

        response = admin_client.post(url, sync_data, format="json")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "synced_count" in data
        assert "errors" in data
        assert data["synced_count"] >= 0

    @patch("portfolio_management.common.models.requests.get")
    def test_fx_rate_external_api_integration(self, mock_get, admin_client):
        """Test integration with external FX rate APIs."""
        # Mock external API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "rates": {"EUR": 0.8500, "GBP": 0.8700, "JPY": 110.50},
            "base": "USD",
            "date": date.today().isoformat(),
        }
        mock_get.return_value = mock_response

        url = reverse("fx-rates-sync-external")

        response = admin_client.post(
            url,
            {
                "api_provider": "example_api",
                "base_currency": "USD",
                "target_currencies": ["EUR", "GBP", "JPY"],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "updated_rates" in data
        assert data["updated_rates"] >= 0

    def test_fx_rate_data_cleanup(self, admin_client, fx_rates):
        """Test FX rate data cleanup and maintenance."""
        url = reverse("fx-rates-cleanup")

        # Create some old FX rates for cleanup testing
        old_date = date.today() - timedelta(days=400)
        FXRateFactory.create_batch(
            5, from_currency="USD", to_currency="EUR", date=old_date
        )

        cleanup_params = {
            "older_than_days": 365,
            "keep_weekly": True,
            "keep_monthly": True,
        }

        response = admin_client.post(url, cleanup_params, format="json")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "deleted_count" in data
        assert data["deleted_count"] >= 0

    def test_fx_rate_export_functionality(self, admin_client, fx_rates):
        """Test FX rate data export functionality."""
        url = reverse("fx-rates-export")

        export_params = {
            "format": "csv",
            "start_date": (date.today() - timedelta(days=7)).isoformat(),
            "end_date": date.today().isoformat(),
            "currency_pairs": [
                {"from_currency": "USD", "to_currency": "EUR"},
                {"from_currency": "EUR", "to_currency": "GBP"},
            ],
        }

        response = admin_client.post(url, export_params, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Verify CSV content
        content = response.content.decode("utf-8")
        assert "date,from_currency,to_currency,rate" in content
        assert "USD,EUR" in content
        assert "EUR,GBP" in content

    def test_fx_rate_analytics(self, admin_client, fx_rates):
        """Test FX rate analytics and reporting."""
        url = reverse("fx-rates-analytics")

        analytics_params = {
            "currency_pair": "USD/EUR",
            "period": "30d",
            "metrics": ["volatility", "trend", "correlation"],
        }

        response = admin_client.get(url, analytics_params)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "volatility" in data
        assert "trend" in data
        assert "statistics" in data

        # Verify statistical calculations
        stats = data["statistics"]
        assert "min_rate" in stats
        assert "max_rate" in stats
        assert "avg_rate" in stats
        assert "std_dev" in stats


@pytest.mark.integration
class TestFXRatePerformance:
    """Test FX rate performance and optimization."""

    def test_bulk_fx_rate_lookup_performance(self, fx_rates):
        """Test performance of bulk FX rate lookups."""
        import time

        # Test bulk lookup of many rates
        currency_pairs = [
            ("USD", "EUR"),
            ("EUR", "GBP"),
            ("USD", "JPY"),
            ("GBP", "JPY"),
            ("EUR", "JPY"),
        ]

        start_time = time.time()

        for from_curr, to_curr in currency_pairs:
            for i in range(10):  # 10 lookups per pair
                rate = get_exchange_rate(
                    from_curr, to_curr, date.today() - timedelta(days=i)
                )
                assert rate is not None

        end_time = time.time()
        lookup_time = end_time - start_time

        # Should complete all lookups within 1 second
        assert lookup_time < 1.0

    def test_fx_rate_cache_performance(self, fx_rates):
        """Test FX rate cache performance."""
        import time

        # Clear cache
        fx_cache.clear()

        # First lookup (cache miss)
        start_time = time.time()
        rate1 = get_exchange_rate("USD", "EUR", date.today())
        first_lookup_time = time.time() - start_time

        # Second lookup (cache hit)
        start_time = time.time()
        rate2 = get_exchange_rate("USD", "EUR", date.today())
        second_lookup_time = time.time() - start_time

        assert rate1 == rate2
        # Cache hit should be significantly faster
        assert second_lookup_time < first_lookup_time * 0.1

    def test_concurrent_fx_rate_access(self, fx_rates):
        """Test concurrent access to FX rate data."""
        import threading
        import time

        results = []
        errors = []

        def lookup_rate(currency_pair, date):
            try:
                rate = get_exchange_rate(currency_pair[0], currency_pair[1], date)
                results.append((currency_pair, date, rate))
            except Exception as e:
                errors.append(e)

        # Create multiple threads for concurrent lookups
        threads = []
        currency_pairs = [("USD", "EUR"), ("EUR", "GBP"), ("USD", "JPY")]
        dates = [date.today() - timedelta(days=i) for i in range(5)]

        start_time = time.time()

        for pair in currency_pairs:
            for d in dates:
                thread = threading.Thread(target=lookup_rate, args=(pair, d))
                threads.append(thread)
                thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        end_time = time.time()
        total_time = end_time - start_time

        # Verify results
        assert len(errors) == 0
        assert len(results) == len(currency_pairs) * len(dates)

        # All results should have valid rates
        for pair, d, rate in results:
            assert rate is not None
            assert rate > 0

        # Should complete within reasonable time
        assert total_time < 2.0

    def test_memory_usage_large_dataset(self, fx_rates):
        """Test memory usage with large FX rate datasets."""
        import os

        import psutil

        # Get current process
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Create large dataset
        large_dataset = FXRateFactory.create_batch(
            1000,
            from_currency="USD",
            to_currency="EUR",
            date=date.today() - timedelta(days=1),
        )

        # Perform operations on large dataset
        for fx_rate in large_dataset:
            rate = get_exchange_rate("USD", "EUR", fx_rate.date)
            assert rate is not None

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (< 100MB)
        assert memory_increase < 100 * 1024 * 1024  # 100MB

        # Clean up
        FX.objects.filter(id__in=[fx.id for fx in large_dataset]).delete()


@pytest.mark.integration
class TestFXRateErrorRecovery:
    """Test FX rate error handling and recovery mechanisms."""

    @patch("portfolio_management.common.models.requests.get")
    def test_external_api_failure_recovery(self, mock_get, admin_client, fx_rates):
        """Test recovery from external API failures."""
        # Mock API failure
        mock_get.side_effect = Exception("API connection failed")

        url = reverse("fx-rates-sync-external")

        response = admin_client.post(
            url,
            {
                "api_provider": "example_api",
                "base_currency": "USD",
                "target_currencies": ["EUR", "GBP"],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "error" in data
        assert "fallback_used" in data

        # System should fall back to cached/internal rates
        assert data["fallback_used"] is True

    def test_database_connection_recovery(self, fx_rates):
        """Test FX rate operations with database connection issues."""
        with patch("django.db.connection") as mock_connection:
            # Simulate database connection failure
            mock_connection.cursor.side_effect = Exception("Database connection lost")

            # Operations should handle connection errors gracefully
            rate = get_exchange_rate("USD", "EUR", date.today())

            # Should return None or raise appropriate error
            assert rate is None or isinstance(rate, Exception)

    def test_fx_rate_data_integrity(self, fx_rates, admin_client):
        """Test FX rate data integrity validation."""
        # Create inconsistent FX rate data
        inconsistent_rate = Decimal("5.0")  # Unrealistic USD/EUR rate
        update_fx_rate("USD", "EUR", date.today(), inconsistent_rate)

        # Run integrity check
        url = reverse("fx-rates-integrity-check")
        response = admin_client.post(url, format="json")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "issues_found" in data
        assert data["issues_found"] > 0

        # Should detect unrealistic rates
        issues = data["issues"]
        rate_issues = [issue for issue in issues if "unrealistic_rate" in issue["type"]]
        assert len(rate_issues) > 0

    def test_fx_rate_backup_and_restore(self, admin_client, fx_rates):
        """Test FX rate backup and restore functionality."""
        # Create backup
        url = reverse("fx-rates-backup")
        response = admin_client.post(url, format="json")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "backup_id" in data
        assert "backed_up_count" in data

        backup_id = data["backup_id"]

        # Modify some rates
        update_fx_rate("USD", "EUR", date.today(), Decimal("999.999"))

        # Restore from backup
        restore_url = reverse("fx-rates-restore")
        restore_response = admin_client.post(
            restore_url, {"backup_id": backup_id}, format="json"
        )

        assert restore_response.status_code == status.HTTP_200_OK
        restore_data = restore_response.json()
        assert "restored_count" in restore_data

        # Verify rates were restored
        restored_rate = get_exchange_rate("USD", "EUR", date.today())
        assert restored_rate != Decimal("999.999")

    def test_fx_rate_rate_limiting(self, admin_client):
        """Test FX rate API rate limiting."""
        url = reverse("fx-rates")

        # Make many rapid requests
        responses = []
        for i in range(100):
            response = admin_client.get(url)
            responses.append(response.status_code)

        # Should receive rate limiting responses after threshold
        rate_limited_responses = [
            code for code in responses if code == status.HTTP_429_TOO_MANY_REQUESTS
        ]
        assert len(rate_limited_responses) > 0
