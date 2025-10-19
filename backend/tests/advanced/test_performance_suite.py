"""
Performance Test Suite

Comprehensive performance testing framework for the portfolio management system.
These tests ensure the system performs adequately under various load conditions
and identify performance bottlenecks.

Author: Portfolio Management Test Framework
Created: 2025-10-18
Purpose: Monitor and validate system performance characteristics
"""

import concurrent.futures
import time
from datetime import date, timedelta
from decimal import Decimal

import psutil
import pytest
from django.db import transaction
from django.urls import reverse
from rest_framework.test import APIClient

from portfolio_management.common.models import fx_cache, get_exchange_rate
from portfolio_management.models import Assets, Portfolios, Transactions
from portfolio_management.portfolio.calculator import calculate_buy_in_price, calculate_nav
from tests.fixtures.factories.asset_factory import AssetFactory
from tests.fixtures.factories.transaction_factory import TransactionFactory


@pytest.mark.performance
class TestCalculationPerformance:
    """Performance tests for financial calculations."""

    def test_performance_buy_in_price_small_dataset(self):
        """Test buy-in price calculation performance with small dataset."""
        asset = AssetFactory.create()
        transactions = TransactionFactory.create_batch(
            10, asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
        )

        # Warm up
        calculate_buy_in_price(transactions)

        # Performance test
        start_time = time.time()
        for _ in range(100):  # 100 iterations
            result = calculate_buy_in_price(transactions)
        end_time = time.time()

        avg_time = (end_time - start_time) / 100
        max_time_per_calc = 0.01  # 10ms max per calculation

        assert (
            avg_time < max_time_per_calc
        ), f"Average time {avg_time:.4f}s exceeds threshold {max_time_per_calc}s"
        assert result > 0

    def test_performance_buy_in_price_medium_dataset(self):
        """Test buy-in price calculation performance with medium dataset."""
        assets = AssetFactory.create_batch(20)
        transactions = []

        for asset in assets:
            transactions.extend(
                TransactionFactory.create_batch(
                    25, asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
                )
            )

        # Warm up
        calculate_buy_in_price(transactions)

        # Performance test
        start_time = time.time()
        for _ in range(50):  # 50 iterations
            result = calculate_buy_in_price(transactions)
        end_time = time.time()

        avg_time = (end_time - start_time) / 50
        max_time_per_calc = 0.05  # 50ms max per calculation

        assert (
            avg_time < max_time_per_calc
        ), f"Average time {avg_time:.4f}s exceeds threshold {max_time_per_calc}s"
        assert result > 0

    def test_performance_buy_in_price_large_dataset(self):
        """Test buy-in price calculation performance with large dataset."""
        assets = AssetFactory.create_batch(100)
        transactions = []

        for asset in assets:
            transactions.extend(
                TransactionFactory.create_batch(
                    50, asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
                )
            )

        # Warm up
        calculate_buy_in_price(transactions)

        # Performance test
        start_time = time.time()
        for _ in range(10):  # 10 iterations
            result = calculate_buy_in_price(transactions)
        end_time = time.time()

        avg_time = (end_time - start_time) / 10
        max_time_per_calc = 0.5  # 500ms max per calculation

        assert (
            avg_time < max_time_per_calc
        ), f"Average time {avg_time:.4f}s exceeds threshold {max_time_per_calc}s"
        assert result > 0

    def test_performance_nav_calculation_scaling(self):
        """Test NAV calculation performance scaling."""
        # Test with different portfolio sizes
        portfolio_sizes = [10, 50, 100, 500]
        performance_data = []

        for size in portfolio_sizes:
            # Create portfolio with specified number of assets
            portfolio = Portfolios.objects.create(
                name=f"Test Portfolio {size}", base_currency="USD"
            )

            assets = AssetFactory.create_batch(size)
            transactions = []

            for asset in assets:
                transactions.extend(
                    TransactionFactory.create_batch(
                        5,
                        portfolio=portfolio,
                        asset=asset,
                        type="Buy",
                        quantity=100,
                        price=Decimal("50.00"),
                    )
                )

            # Performance test
            start_time = time.time()
            nav = calculate_nav(portfolio)
            end_time = time.time()

            calc_time = end_time - start_time
            performance_data.append((size, calc_time))

            # Verify linear or better scaling
            if len(performance_data) > 1:
                prev_size, prev_time = performance_data[-2]
                scaling_factor = (calc_time / prev_time) / (size / prev_size)
                assert scaling_factor < 2.0, f"Super-linear scaling detected: {scaling_factor:.2f}x"

            assert nav > 0
            assert calc_time < 1.0, f"NAV calculation took {calc_time:.2f}s for {size} assets"

    def test_performance_concurrent_calculations(self):
        """Test performance under concurrent calculation load."""
        assets = AssetFactory.create_batch(50)
        transactions_by_asset = {}

        for asset in assets:
            transactions_by_asset[asset.id] = TransactionFactory.create_batch(
                20, asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
            )

        def calculate_asset_buy_in(asset_id):
            transactions = transactions_by_asset[asset_id]
            return calculate_buy_in_price(transactions)

        # Concurrent calculation test
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(calculate_asset_buy_in, asset.id) for asset in assets]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        end_time = time.time()
        total_time = end_time - start_time

        # Should complete faster than sequential execution
        avg_time_per_asset = total_time / len(assets)
        assert (
            avg_time_per_asset < 0.1
        ), f"Concurrent calculation too slow: {avg_time_per_asset:.4f}s per asset"
        assert len(results) == len(assets)
        assert all(result > 0 for result in results)


@pytest.mark.performance
class TestDatabasePerformance:
    """Performance tests for database operations."""

    def test_database_query_performance(self):
        """Test database query performance for common operations."""
        # Create test data
        assets = AssetFactory.create_batch(100)
        transactions = []

        for asset in assets:
            transactions.extend(
                TransactionFactory.create_batch(
                    10, asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
                )
            )

        # Test asset query performance
        start_time = time.time()
        queried_assets = Assets.objects.all()
        list(queried_assets)  # Force evaluation
        asset_query_time = time.time() - start_time

        assert asset_query_time < 0.1, f"Asset query took {asset_query_time:.4f}s"

        # Test transaction query performance
        start_time = time.time()
        queried_transactions = Transactions.objects.select_related("asset", "portfolio").all()
        list(queried_transactions)  # Force evaluation
        transaction_query_time = time.time() - start_time

        assert transaction_query_time < 0.5, f"Transaction query took {transaction_query_time:.4f}s"

    def test_database_bulk_operations_performance(self):
        """Test performance of bulk database operations."""
        # Test bulk asset creation
        start_time = time.time()
        assets_data = [AssetFactory.build() for _ in range(1000)]
        Assets.objects.bulk_create(assets_data)
        bulk_create_time = time.time() - start_time

        assert bulk_create_time < 1.0, f"Bulk create took {bulk_create_time:.4f}s"

        # Test bulk transaction creation
        assets = Assets.objects.all()[:100]
        transactions_data = []

        for asset in assets:
            transactions_data.extend(
                [
                    TransactionFactory.build(
                        asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
                    )
                    for _ in range(10)
                ]
            )

        start_time = time.time()
        Transactions.objects.bulk_create(transactions_data)
        bulk_tx_create_time = time.time() - start_time

        assert bulk_tx_create_time < 2.0, f"Bulk transaction create took {bulk_tx_create_time:.4f}s"

    def test_database_index_performance(self):
        """Test database index performance for indexed queries."""
        # Create test data with various query patterns
        assets = AssetFactory.create_batch(500)
        transactions = []

        for asset in assets:
            transactions.extend(
                TransactionFactory.create_batch(
                    20, asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
                )
            )

        # Test indexed queries
        test_queries = [
            # Query by asset (should be indexed)
            lambda: list(Transactions.objects.filter(asset__ticker="AAPL")),
            # Query by date range (should be indexed)
            lambda: list(Transactions.objects.filter(date__gte=date.today() - timedelta(days=30))),
            # Query by type (should be indexed)
            lambda: list(Transactions.objects.filter(type="Buy")),
            # Complex query with multiple conditions
            lambda: list(
                Transactions.objects.filter(
                    type="Buy", date__gte=date.today() - timedelta(days=30)
                ).select_related("asset")
            ),
        ]

        for i, query_func in enumerate(test_queries):
            start_time = time.time()
            # results = query_func()
            query_time = time.time() - start_time

            assert query_time < 0.5, f"Query {i + 1} took {query_time:.4f}s"

    def test_database_connection_pooling(self):
        """Test database connection pooling performance."""

        def db_operation():
            # Simulate database operation
            with transaction.atomic():
                asset = AssetFactory.create()
                tx = TransactionFactory.create(asset=asset)
                return asset.id, tx.id

        # Test concurrent database operations
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(db_operation) for _ in range(50)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle concurrent operations efficiently
        avg_time_per_operation = total_time / 50
        assert (
            avg_time_per_operation < 0.1
        ), f"Concurrent DB operations too slow: {avg_time_per_operation:.4f}s"
        assert len(results) == 50


@pytest.mark.performance
class TestAPIPerformance:
    """Performance tests for API endpoints."""

    def test_api_endpoint_performance(self, api_client):
        """Test API endpoint response times."""

        endpoints = [
            reverse("portfolio-list"),
            reverse("asset-list"),
            reverse("transaction-list"),
            reverse("fx-rates"),
        ]

        for endpoint in endpoints:
            # Warm up
            api_client.get(endpoint)

            # Performance test
            start_time = time.time()
            response = api_client.get(endpoint)
            response_time = time.time() - start_time

            assert response.status_code == 200
            assert response_time < 0.5, f"Endpoint {endpoint} took {response_time:.4f}s"

    def test_api_pagination_performance(self, api_client):
        """Test API pagination performance."""
        # Create large dataset
        AssetFactory.create_batch(1000)

        url = reverse("asset-list")

        # Test pagination performance
        # start_time = time.time()

        page = 1
        total_time = 0

        while True:
            response = api_client.get(url, {"page": page})
            page_start = time.time()

            assert response.status_code == 200

            data = response.json()
            if not data.get("next"):
                break

            page += 1
            page_time = time.time() - page_start
            total_time += page_time

            # Each page should load quickly
            assert page_time < 0.2, f"Page {page} took {page_time:.4f}s"

            # Limit pagination test to first 10 pages
            if page > 10:
                break

        # total_pagination_time = time.time() - start_time
        avg_time_per_page = total_time / min(page, 10)

        assert avg_time_per_page < 0.1, f"Average page time {avg_time_per_page:.4f}s too slow"

    def test_api_concurrent_requests(self, api_client):
        """Test API performance under concurrent requests."""
        # Create test data
        portfolios = [
            Portfolios.objects.create(name=f"Portfolio {i}", base_currency="USD") for i in range(5)
        ]

        def make_request(portfolio_id):
            url = reverse("portfolio-detail", kwargs={"pk": portfolio_id})
            start = time.time()
            response = api_client.get(url)
            end = time.time()
            return response.status_code, end - start

        # Concurrent request test
        # start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(make_request, portfolio.id)
                for portfolio in portfolios
                for _ in range(10)
            ]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        # end_time = time.time()
        # total_time = end_time - start_time

        # Analyze results
        successful_requests = [r for r in results if r[0] == 200]
        response_times = [r[1] for r in successful_requests]

        assert (
            len(successful_requests) == 50
        ), f"Only {len(successful_requests)}/50 requests successful"
        assert len(response_times) == 50

        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)

        assert avg_response_time < 0.5, f"Average response time {avg_response_time:.4f}s too slow"
        assert max_response_time < 2.0, f"Max response time {max_response_time:.4f}s too slow"

    def test_api_filtering_performance(self, api_client):
        """Test API filtering performance."""
        # Create diverse test data
        assets = AssetFactory.create_batch(500)

        for asset in assets:
            TransactionFactory.create_batch(
                10, asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
            )

        # Test various filters
        filter_tests = [
            {"type": "Buy"},
            {"date__gte": (date.today() - timedelta(days=30)).isoformat()},
            {"asset__ticker": "AAPL"},
            {"quantity__gte": 50},
            {"price__gte": "40.00"},
        ]

        url = reverse("transaction-list")

        for filters in filter_tests:
            # Warm up
            api_client.get(url, filters)

            # Performance test
            start_time = time.time()
            response = api_client.get(url, filters)
            response_time = time.time() - start_time

            assert response.status_code == 200
            assert response_time < 0.3, f"Filter {filters} took {response_time:.4f}s"


@pytest.mark.performance
class TestFXRatePerformance:
    """Performance tests for FX rate operations."""

    def test_fx_rate_lookup_performance(self, fx_rates):
        """Test FX rate lookup performance."""
        # Clear cache for fair testing
        fx_cache.clear()

        # Test direct rate lookups
        currency_pairs = [("USD", "EUR"), ("EUR", "GBP"), ("USD", "JPY")]

        start_time = time.time()

        for _ in range(1000):
            pair = currency_pairs[_ % len(currency_pairs)]
            rate = get_exchange_rate(pair[0], pair[1], date.today())
            assert rate > 0

        end_time = time.time()
        avg_lookup_time = (end_time - start_time) / 1000

        assert avg_lookup_time < 0.001, f"Average lookup time {avg_lookup_time:.6f}s too slow"

    def test_fx_rate_cross_currency_performance(self, fx_rates):
        """Test cross-currency FX rate calculation performance."""
        cross_pairs = [("GBP", "JPY"), ("EUR", "JPY"), ("GBP", "CHF")]

        start_time = time.time()

        for _ in range(500):
            pair = cross_pairs[_ % len(cross_pairs)]
            rate = get_exchange_rate(pair[0], pair[1], date.today())
            assert rate > 0

        end_time = time.time()
        avg_calc_time = (end_time - start_time) / 500

        assert (
            avg_calc_time < 0.002
        ), f"Average cross-currency calculation time {avg_calc_time:.6f}s too slow"

    def test_fx_rate_bulk_operations_performance(self, fx_rates):
        """Test FX rate bulk operations performance."""
        # Test bulk rate retrieval
        currency_pairs = [
            ("USD", "EUR"),
            ("EUR", "GBP"),
            ("USD", "JPY"),
            ("GBP", "JPY"),
            ("EUR", "JPY"),
            ("USD", "CHF"),
        ]

        start_time = time.time()

        # Retrieve all rates in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(get_exchange_rate, pair[0], pair[1], date.today())
                for pair in currency_pairs
                for _ in range(100)
            ]
            rates = [future.result() for future in concurrent.futures.as_completed(futures)]

        end_time = time.time()
        total_time = end_time - start_time
        avg_time_per_lookup = total_time / len(rates)

        assert len(rates) == 600  # 6 pairs * 100 lookups each
        assert (
            avg_time_per_lookup < 0.001
        ), f"Bulk lookup average time {avg_time_per_lookup:.6f}s too slow"
        assert all(rate > 0 for rate in rates)

    def test_fx_rate_cache_performance(self, fx_rates):
        """Test FX rate caching performance."""
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
        assert (
            second_lookup_time < first_lookup_time * 0.1
        ), "Cache not providing sufficient speedup"

        # Test cache hit performance over many lookups
        start_time = time.time()

        for _ in range(1000):
            rate = get_exchange_rate("USD", "EUR", date.today())
            assert rate == rate1

        end_time = time.time()
        avg_cache_hit_time = (end_time - start_time) / 1000

        assert (
            avg_cache_hit_time < 0.0001
        ), f"Cache hit average time {avg_cache_hit_time:.6f}s too slow"


@pytest.mark.performance
class TestMemoryUsage:
    """Performance tests for memory usage."""

    def test_memory_usage_calculation_scaling(self):
        """Test memory usage scaling with calculation complexity."""
        process = psutil.Process()
        initial_memory = process.memory_info().rss

        # Test with increasing dataset sizes
        dataset_sizes = [100, 500, 1000, 5000]

        for size in dataset_sizes:
            # Create test data
            assets = AssetFactory.create_batch(size)
            transactions = []

            for asset in assets:
                transactions.extend(
                    TransactionFactory.create_batch(
                        10,
                        asset=asset,
                        type="Buy",
                        quantity=100,
                        price=Decimal("50.00"),
                    )
                )

            # Measure memory before calculations
            before_memory = process.memory_info().rss

            # Perform calculations
            for tx_batch in [transactions[i : i + 100] for i in range(0, len(transactions), 100)]:
                calculate_buy_in_price(tx_batch)

            # Measure memory after calculations
            after_memory = process.memory_info().rss
            memory_increase = after_memory - before_memory

            # Memory increase should be reasonable
            memory_per_transaction = memory_increase / len(transactions)
            assert (
                memory_per_transaction < 1024
            ), f"Memory usage too high: {memory_per_transaction} bytes per transaction"

            # Clean up
            Transactions.objects.filter(id__in=[tx.id for tx in transactions]).delete()
            Assets.objects.filter(id__in=[asset.id for asset in assets]).delete()

        final_memory = process.memory_info().rss
        total_memory_increase = final_memory - initial_memory

        # Total memory increase should be manageable
        assert (
            total_memory_increase < 100 * 1024 * 1024
        ), f"Total memory increase {total_memory_increase} bytes too high"

    def test_memory_usage_fx_operations(self, fx_rates):
        """Test memory usage during FX operations."""
        process = psutil.Process()
        initial_memory = process.memory_info().rss

        # Perform many FX rate lookups
        currency_pairs = [("USD", "EUR"), ("EUR", "GBP"), ("USD", "JPY")]

        for _ in range(10000):
            pair = currency_pairs[_ % len(currency_pairs)]
            rate = get_exchange_rate(pair[0], pair[1], date.today())
            assert rate > 0

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be minimal due to caching
        assert (
            memory_increase < 10 * 1024 * 1024
        ), f"FX operations memory increase {memory_increase} bytes too high"

    def test_memory_leak_detection(self):
        """Test for memory leaks in long-running operations."""
        process = psutil.Process()
        memory_samples = []

        # Perform repeated operations and monitor memory
        for iteration in range(10):
            # Create and process data
            assets = AssetFactory.create_batch(100)
            transactions = []

            for asset in assets:
                transactions.extend(
                    TransactionFactory.create_batch(
                        10,
                        asset=asset,
                        type="Buy",
                        quantity=100,
                        price=Decimal("50.00"),
                    )
                )

            # Perform calculations
            calculate_buy_in_price(transactions)

            # Measure memory
            memory_sample = process.memory_info().rss
            memory_samples.append(memory_sample)

            # Clean up
            Transactions.objects.filter(id__in=[tx.id for tx in transactions]).delete()
            Assets.objects.filter(id__in=[asset.id for asset in assets]).delete()

        # Analyze memory trend
        if len(memory_samples) > 1:
            # Calculate memory trend (slope)
            memory_trend = (memory_samples[-1] - memory_samples[0]) / len(memory_samples)

            # Memory should not be consistently increasing
            assert (
                memory_trend < 1024 * 1024
            ), f"Potential memory leak detected: trend {memory_trend} bytes per iteration"


@pytest.mark.performance
class TestStressTesting:
    """Stress tests for system under heavy load."""

    def test_stress_concurrent_users(self, api_client):
        """Test system performance under concurrent user load."""
        # Create test data
        portfolios = [
            Portfolios.objects.create(name=f"Stress Portfolio {i}", base_currency="USD")
            for i in range(20)
        ]

        def simulate_user_activity(portfolio_id):
            """Simulate a user making various API calls."""
            client = APIClient()

            operations = [
                # View portfolio
                lambda: client.get(reverse("portfolio-detail", kwargs={"pk": portfolio_id})),
                # List assets
                lambda: client.get(reverse("asset-list")),
                # List transactions
                lambda: client.get(reverse("transaction-list"), {"portfolio": portfolio_id}),
                # Get FX rates
                lambda: client.get(reverse("fx-rates")),
            ]

            results = []
            for operation in operations:
                start = time.time()
                response = operation()
                end = time.time()
                results.append((response.status_code, end - start))

            return results

        # Stress test with concurrent users
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = [
                executor.submit(simulate_user_activity, portfolio.id)
                for portfolio in portfolios
                for _ in range(5)
            ]
            all_results = [future.result() for future in concurrent.futures.as_completed(futures)]

        end_time = time.time()
        total_time = end_time - start_time

        # Analyze results
        flat_results = [result for user_results in all_results for result in user_results]
        successful_operations = [r for r in flat_results if r[0] == 200]
        response_times = [r[1] for r in successful_operations]

        success_rate = len(successful_operations) / len(flat_results)
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        assert success_rate > 0.95, f"Success rate too low: {success_rate:.2%}"
        assert (
            avg_response_time < 1.0
        ), f"Average response time under stress: {avg_response_time:.4f}s"
        assert total_time < 30, f"Stress test took too long: {total_time:.2f}s"

    def test_stress_large_dataset_processing(self):
        """Test performance with very large datasets."""
        # Create large dataset
        assets = AssetFactory.create_batch(1000)
        transactions = []

        for asset in assets:
            transactions.extend(
                TransactionFactory.create_batch(
                    50, asset=asset, type="Buy", quantity=100, price=Decimal("50.00")
                )
            )

        # Stress test calculations
        start_time = time.time()

        # Process transactions in batches
        batch_size = 1000
        total_processed = 0

        for i in range(0, len(transactions), batch_size):
            batch = transactions[i : i + batch_size]
            # result = calculate_buy_in_price(batch)
            total_processed += len(batch)

            # Should process batches quickly
            batch_time = time.time() - start_time
            if total_processed % 5000 == 0:
                rate = total_processed / batch_time
                assert rate > 1000, f"Processing rate too slow: {rate:.2f} transactions/second"

        end_time = time.time()
        total_time = end_time - start_time
        processing_rate = len(transactions) / total_time

        assert (
            processing_rate > 5000
        ), f"Large dataset processing too slow: {processing_rate:.2f} transactions/second"
        assert total_time < 60, f"Large dataset processing took too long: {total_time:.2f}s"

    def test_stress_api_rate_limiting(self, api_client):
        """Test API rate limiting under stress."""
        url = reverse("asset-list")

        # Make rapid requests
        start_time = time.time()
        responses = []

        for i in range(200):  # 200 rapid requests
            response = api_client.get(url)
            responses.append(response.status_code)

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle rapid requests gracefully
        successful_requests = [code for code in responses if code == 200]
        rate_limited_requests = [code for code in responses if code == 429]

        success_rate = len(successful_requests) / len(responses)

        assert success_rate > 0.8, f"Success rate under stress too low: {success_rate:.2%}"
        assert total_time < 10, f"Rapid requests took too long: {total_time:.2f}s"

        # Should have some rate limiting if implemented
        if rate_limited_requests:
            rate_limiting_rate = len(rate_limited_requests) / len(responses)
            assert (
                rate_limiting_rate < 0.2
            ), f"Rate limiting too aggressive: {rate_limiting_rate:.2%}"


# Performance Test Configuration
PERFORMANCE_CONFIG = {
    "thresholds": {
        "calculation_times": {
            "small_dataset": 0.01,  # seconds
            "medium_dataset": 0.05,
            "large_dataset": 0.5,
        },
        "api_response_times": {
            "simple_endpoints": 0.1,
            "complex_endpoints": 0.5,
            "paginated_endpoints": 0.2,
        },
        "database_queries": {
            "simple_select": 0.1,
            "complex_select": 0.5,
            "bulk_operations": 2.0,
        },
        "fx_operations": {
            "direct_lookup": 0.001,
            "cross_currency": 0.002,
            "bulk_operations": 0.01,
        },
        "memory_usage": {
            "per_transaction": 1024,  # bytes
            "total_increase": 100 * 1024 * 1024,  # 100MB
        },
        "stress_tests": {
            "success_rate": 0.95,
            "avg_response_time": 1.0,
            "processing_rate": 5000,  # transactions/second
        },
    },
    "test_datasets": {
        "small": {"assets": 10, "transactions_per_asset": 10},
        "medium": {"assets": 50, "transactions_per_asset": 25},
        "large": {"assets": 100, "transactions_per_asset": 50},
        "stress": {"assets": 1000, "transactions_per_asset": 50},
    },
    "monitoring": {
        "track_memory": True,
        "track_cpu": True,
        "track_db_connections": True,
        "track_response_times": True,
    },
}


@pytest.fixture(scope="session")
def performance_monitor():
    """Fixture for performance monitoring during tests."""
    monitor = {
        "start_time": None,
        "memory_samples": [],
        "cpu_samples": [],
        "response_times": [],
    }

    def start_monitoring():
        monitor["start_time"] = time.time()
        process = psutil.Process()
        monitor["memory_samples"].append(process.memory_info().rss)
        monitor["cpu_samples"].append(process.cpu_percent())

    def stop_monitoring():
        if monitor["start_time"]:
            end_time = time.time()
            duration = end_time - monitor["start_time"]
            process = psutil.Process()
            monitor["memory_samples"].append(process.memory_info().rss)
            monitor["cpu_samples"].append(process.cpu_percent())
            return duration
        return 0

    monitor["start"] = start_monitoring
    monitor["stop"] = stop_monitoring

    return monitor
