#!/usr/bin/env python3
"""
Memory Usage Profiler

Profiles memory usage for portfolio management operations.
"""

import os
import sys
import time
from pathlib import Path

from memory_profiler import profile

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portfolio_management.settings.test")

import django

django.setup()

from portfolio_management.models import Assets, Portfolios, Transactions
from portfolio_management.portfolio.calculator import (
    calculate_buy_in_price,
    calculate_nav,
)
from tests.fixtures.factories.asset_factory import AssetFactory
from tests.fixtures.factories.transaction_factory import TransactionFactory


@profile
def profile_portfolio_creation():
    """Profile memory usage during portfolio creation."""
    print("📊 Profiling portfolio creation...")

    portfolios = []
    for i in range(10):
        portfolio = Portfolios.objects.create(
            name=f"Memory Test Portfolio {i}", base_currency="USD"
        )
        portfolios.append(portfolio)

    return portfolios


@profile
def profile_asset_creation():
    """Profile memory usage during asset creation."""
    print("📊 Profiling asset creation...")

    assets = []
    for i in range(100):
        asset = AssetFactory.create(ticker=f"MEM{i:03d}", name=f"Memory Test Asset {i}")
        assets.append(asset)

    return assets


@profile
def profile_transaction_creation():
    """Profile memory usage during transaction creation."""
    print("📊 Profiling transaction creation...")

    assets = AssetFactory.create_batch(20)
    portfolio = Portfolios.objects.create(name="Memory Test", base_currency="USD")

    transactions = []
    for asset in assets:
        for i in range(10):
            tx = TransactionFactory.create(
                portfolio=portfolio,
                asset=asset,
                type="Buy",
                quantity=100,
                price=50.00 + i,
            )
            transactions.append(tx)

    return transactions


@profile
def profile_calculation_performance():
    """Profile memory usage during financial calculations."""
    print("📊 Profiling calculation performance...")

    # Create test data
    assets = AssetFactory.create_batch(50)
    portfolio = Portfolios.objects.create(name="Calc Test", base_currency="USD")
    transactions = []

    for asset in assets:
        transactions.extend(
            TransactionFactory.create_batch(
                20,
                portfolio=portfolio,
                asset=asset,
                type="Buy",
                quantity=100,
                price=50.00,
            )
        )

    # Profile calculations
    start_time = time.time()

    # Calculate buy-in prices for each asset
    for asset in assets:
        asset_transactions = [tx for tx in transactions if tx.asset == asset]
        buy_in_price = calculate_buy_in_price(asset_transactions)

    # Calculate portfolio NAV
    nav = calculate_nav(portfolio)

    end_time = time.time()
    calculation_time = end_time - start_time

    print(f"✅ Calculations completed in {calculation_time:.2f} seconds")
    print(f"   - Assets processed: {len(assets)}")
    print(f"   - Transactions processed: {len(transactions)}")
    print(f"   - Portfolio NAV: {nav}")

    return {"calculation_time": calculation_time, "transactions": len(transactions)}


@profile
def profile_bulk_operations():
    """Profile memory usage during bulk database operations."""
    print("📊 Profiling bulk operations...")

    # Bulk create assets
    assets_data = []
    for i in range(1000):
        asset = AssetFactory.build(ticker=f"BULK{i:04d}", name=f"Bulk Asset {i}")
        assets_data.append(asset)

    start_time = time.time()
    created_assets = Assets.objects.bulk_create(assets_data)
    bulk_create_time = time.time() - start_time

    print(
        f"✅ Bulk created {len(created_assets)} assets in {bulk_create_time:.2f} seconds"
    )

    # Bulk create transactions
    transactions_data = []
    for asset in created_assets[:100]:  # Use first 100 assets
        for i in range(10):
            tx = TransactionFactory.build(
                asset=asset, type="Buy", quantity=100, price=50.00 + i
            )
            transactions_data.append(tx)

    start_time = time.time()
    created_transactions = Transactions.objects.bulk_create(transactions_data)
    bulk_tx_time = time.time() - start_time

    print(
        f"✅ Bulk created {len(created_transactions)} transactions in {bulk_tx_time:.2f} seconds"
    )

    return {
        "assets_created": len(created_assets),
        "transactions_created": len(created_transactions),
        "asset_time": bulk_create_time,
        "transaction_time": bulk_tx_time,
    }


@profile
def profile_query_performance():
    """Profile memory usage during database queries."""
    print("📊 Profiling query performance...")

    # Create test data
    assets = AssetFactory.create_batch(100)
    transactions = []

    for asset in assets:
        transactions.extend(
            TransactionFactory.create_batch(
                20, asset=asset, type="Buy", quantity=100, price=50.00
            )
        )

    # Profile different query types
    queries = {
        "simple_select": lambda: list(Assets.objects.all()),
        "select_related": lambda: list(
            Transactions.objects.select_related("asset", "portfolio").all()
        ),
        "prefetch_related": lambda: list(
            Portfolios.objects.prefetch_related("transactions").all()
        ),
        "filter_queryset": lambda: list(Transactions.objects.filter(type="Buy")),
        "complex_filter": lambda: list(
            Transactions.objects.filter(
                type="Buy", price__gte=50.00, quantity__gte=50
            ).select_related("asset")
        ),
    }

    results = {}
    for query_name, query_func in queries.items():
        start_time = time.time()
        query_results = query_func()
        end_time = time.time()
        query_time = end_time - start_time

        results[query_name] = {"time": query_time, "count": len(query_results)}

        print(f"   - {query_name}: {query_time:.3f}s ({len(query_results)} results)")

    return results


def main():
    """Main profiling function."""
    print("🔍 Starting Memory Usage Profiling")
    print("=" * 50)

    # Run profiling functions
    profile_results = {}

    try:
        print("\n1. Portfolio Creation")
        profile_results["portfolios"] = profile_portfolio_creation()

        print("\n2. Asset Creation")
        profile_results["assets"] = profile_asset_creation()

        print("\n3. Transaction Creation")
        profile_results["transactions"] = profile_transaction_creation()

        print("\n4. Calculation Performance")
        profile_results["calculations"] = profile_calculation_performance()

        print("\n5. Bulk Operations")
        profile_results["bulk_ops"] = profile_bulk_operations()

        print("\n6. Query Performance")
        profile_results["queries"] = profile_query_performance()

    except Exception as e:
        print(f"❌ Profiling error: {e}")
        return 1

    print("\n✅ Memory profiling completed!")
    print("📄 Check the generated profile output above for memory usage details.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
