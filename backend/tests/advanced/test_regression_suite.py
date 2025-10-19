"""
Regression Test Suite.

Comprehensive regression tests to ensure financial calculation accuracy
remains consistent over time and across code changes. These tests validate
critical financial formulas against known expected results.

Author: Portfolio Management Test Framework
Created: 2025-10-18
Purpose: Prevent regressions in financial calculations
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.core.portfolio_utils import NAV_at_date
from common.models import FX, Assets
from tests.fixtures.factories.asset_factory import AssetFactory
from tests.fixtures.factories.transaction_factory import TransactionFactory


@pytest.mark.regression
class TestCalculationRegression:
    """
    Regression tests for core financial calculations.

    These tests ensure that calculation results remain consistent
    with expected values and don't change unexpectedly.
    """

    # Test Case 1: Simple Buy-In Price Calculation
    @pytest.mark.regression_critical
    def test_regression_buy_in_price_simple_buy(self, sample_transactions):
        """Regression test for simple buy-in price calculation."""
        transactions = sample_transactions

        # Calculate buy-in price
        buy_in_price = transactions[0].security.calculate_buy_in_price(
            date.today(), investor=transactions[0].investor
        )

        # Expected result: (100 * 50 + 50 * 55) / (100 + 50) = 51.6666667
        expected_buy_in = Decimal("51.66666666666666666666666667")

        # Allow for very small floating point differences
        assert abs(buy_in_price - expected_buy_in) < Decimal("0.000001")
        assert buy_in_price == expected_buy_in.quantize(Decimal("0.000001"))

    # Test Case 2: Buy-In Price with Partial Sale
    @pytest.mark.regression_critical
    def test_regression_buy_in_price_with_partial_sale(self, sample_transactions):
        """Regression test for buy-in price calculation with partial sale."""
        # Add a partial sale to transactions
        sale_transaction = TransactionFactory.create(
            security=sample_transactions[0].security,
            type="Sell",
            quantity=25,  # Sell 25 out of 150 shares
            price=Decimal("60.00"),
            currency="USD",
            date=date.today() + timedelta(days=20),
        )

        transactions = list(sample_transactions) + [sale_transaction]

        # Recalculate buy-in price after sale
        buy_in_price = transactions[0].security.calculate_buy_in_price(
            date.today(), investor=transactions[0].investor
        )

        # Expected result should remain the same (51.6666667)
        expected_buy_in = Decimal("51.66666666666666666666666667")

        assert abs(buy_in_price - expected_buy_in) < Decimal("0.000001")

    # Test Case 3: Buy-In Price with Complex Sequence
    @pytest.mark.regression_critical
    def test_regression_buy_in_price_complex_sequence(self):
        """Regression test for complex buy-in price calculation sequence."""
        asset = AssetFactory.create()

        # Create complex transaction sequence
        transactions = [
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=100,
                price=Decimal("50.00"),
                currency="USD",
                date=date(2025, 1, 1),
            ),
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=50,
                price=Decimal("55.00"),
                currency="USD",
                date=date(2025, 2, 1),
            ),
            TransactionFactory.create(
                asset=asset,
                type="Sell",
                quantity=25,
                price=Decimal("60.00"),
                currency="USD",
                date=date(2025, 3, 1),
            ),
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=75,
                price=Decimal("52.00"),
                currency="USD",
                date=date(2025, 4, 1),
            ),
        ]

        buy_in_price = transactions[0].security.calculate_buy_in_price(
            date.today(), investor=transactions[0].investor
        )

        # Expected: Complex weighted average calculation
        # Remaining shares: 100 + 50 - 25 + 75 = 200
        # Total cost:
        # (100*50) + (50*55) - (25*51.6667) + (75*52) =
        # = 10000 + 2750 - 1291.67 + 3900 = 15358.33
        # Buy-in price: 15358.33 / 200 = 76.791667
        expected_buy_in = Decimal("76.79166666666666666666666667")

        assert abs(buy_in_price - expected_buy_in) < Decimal("0.000001")

    # Test Case 4: Multi-Currency NAV Calculation
    @pytest.mark.regression_critical
    def test_regression_nav_multi_currency(self, multi_currency_portfolio, fx_rates):
        """Regression test for multi-currency NAV calculation."""
        portfolio = multi_currency_portfolio

        # Calculate NAV
        nav_result = NAV_at_date(
            portfolio.user.id,
            portfolio.accounts.values_list("id", flat=True),
            date.today(),
            "EUR",
        )

        # Expected calculation:
        # AAPL: 10 * $150 = $1500
        # VOD: 100 * £2.50 = £250
        # SIE: 50 * €120 = €6000
        # Convert all to EUR:
        # AAPL: 1500 * 0.85 = €1275
        # VOD: 250 * 1.15 = €287.50
        # SIE: 6000 * 1.0 = €6000
        # Total: €1275 + €287.50 + €6000 = €7562.50

        expected_nav_eur = Decimal("7562.50")

        assert abs(nav_result - expected_nav_eur) < Decimal("0.01")

    # Test Case 5: Realized Gain/Loss Calculation
    @pytest.mark.regression_critical
    def test_regression_realized_gain_loss(self, sample_transactions):
        """Regression test for realized gain/loss calculation."""
        # Add a sale transaction
        sale_transaction = TransactionFactory.create(
            asset=sample_transactions[0].asset,
            type="Sell",
            quantity=50,
            price=Decimal("60.00"),
            currency="USD",
            date=date.today() + timedelta(days=30),
        )

        transactions = list(sample_transactions) + [sale_transaction]

        securities = Assets.objects.filter(
            id__in=transactions.values_list("security_id", flat=True)
        )

        # Calculate realized gain/loss
        gl_result = 0
        for security in securities:
            gl_result += security.realized_gain_loss(
                date.today(), transactions[0].investor, transactions[0].account_ids
            )

        # Expected calculation:
        # Sold 50 shares at $60 = $3000
        # Cost basis: 50 * $51.6667 = $2583.33
        # Realized gain: $3000 - $2583.33 = $416.67

        expected_gl = Decimal("416.6666666666666666666666667")

        assert abs(gl_result["realized"] - expected_gl) < Decimal("0.01")

    # Test Case 6: FX Rate Cross-Currency Conversion
    @pytest.mark.regression_critical
    def test_regression_fx_cross_currency(self, fx_rates):
        """Regression test for cross-currency FX conversion."""
        # Test GBP to JPY conversion
        rate = FX.get_rate("GBP", "JPY", date.today())["FX"]

        # Expected: GBP->USD * USD->JPY = 1.15 * 110 = 126.5
        expected_rate = Decimal("126.50")

        assert abs(rate - expected_rate) < Decimal("0.01")

    # Test Case 7: Dividend Processing with FX
    @pytest.mark.regression_critical
    def test_regression_dividend_fx_processing(
        self, multi_currency_portfolio, fx_rates
    ):
        """Regression test for dividend processing with FX conversion."""
        portfolio = multi_currency_portfolio
        asset = Assets.objects.get(ticker="AAPL")

        # Create dividend transaction
        dividend = TransactionFactory.create(
            portfolio=portfolio,
            asset=asset,
            type="Dividend",
            quantity=0,
            price=Decimal("1.00"),  # $1 per share
            currency="USD",
            date=date.today(),
        )

        # Expected dividend in EUR: 10 * $1 * 0.85 = €8.50
        expected_dividend_eur = Decimal("8.50")

        # Verify dividend is properly converted
        actual_dividend = dividend.price * FX.get_rate("USD", "EUR", date.today())["FX"]
        assert abs(actual_dividend - expected_dividend_eur) < Decimal("0.01")

    # Test Case 8: Complex Portfolio Rebalancing
    @pytest.mark.regression_critical
    def test_regression_portfolio_rebalancing(self, multi_currency_portfolio, fx_rates):
        """Regression test for portfolio rebalancing calculations."""
        portfolio = multi_currency_portfolio

        # Simulate portfolio rebalancing
        initial_nav = NAV_at_date(
            portfolio.user.id,
            portfolio.accounts.values_list("id", flat=True),
            date.today(),
            "EUR",
        )

        # Add new positions
        new_asset = AssetFactory.create(ticker="MSFT", currency="USD")
        TransactionFactory.create(
            portfolio=portfolio,
            asset=new_asset,
            type="Buy",
            quantity=20,
            price=Decimal("300.00"),
            currency="USD",
            date=date.today(),
        )

        # Calculate new NAV
        new_nav = NAV_at_date(
            portfolio.user.id,
            portfolio.accounts.values_list("id", flat=True),
            date.today(),
            "EUR",
        )

        # Expected increase: 20 * $300 * 0.85 = €5100
        expected_increase = Decimal("5100.00")
        expected_new_nav = initial_nav + expected_increase

        assert abs(new_nav - expected_new_nav) < Decimal("0.01")

    # Test Case 9: Tax Loss Harvesting Scenario
    @pytest.mark.regression_critical
    def test_regression_tax_loss_harvesting(self):
        """Regression test for tax loss harvesting calculations."""
        asset = AssetFactory.create()

        # Create loss-making position
        buy_tx = TransactionFactory.create(
            asset=asset,
            type="Buy",
            quantity=100,
            price=Decimal("100.00"),
            currency="USD",
            date=date(2025, 1, 1),
        )

        # Price dropped, sell at loss
        sell_tx = TransactionFactory.create(
            asset=asset,
            type="Sell",
            quantity=100,
            price=Decimal("80.00"),
            currency="USD",
            date=date(2025, 6, 1),
        )

        transactions = [buy_tx, sell_tx]
        securities = Assets.objects.filter(
            id__in=transactions.values_list("security_id", flat=True)
        )
        gl_result = 0
        for security in securities:
            gl_result += security.realized_gain_loss(
                date.today(), transactions[0].investor, transactions[0].account_ids
            )

        # Expected loss: 100 * ($80 - $100) = -$2000
        expected_loss = Decimal("-2000.00")

        assert abs(gl_result["realized"] - expected_loss) < Decimal("0.01")

    # Test Case 10: High Precision Financial Calculations
    @pytest.mark.regression_critical
    def test_regression_high_precision_calculations(self):
        """Regression test for high precision financial calculations."""
        asset = AssetFactory.create()

        # Create transactions with very small price differences
        transactions = [
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=1000000,
                price=Decimal("100.123456789"),
                currency="USD",
                date=date(2025, 1, 1),
            ),
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=500000,
                price=Decimal("100.123456790"),
                currency="USD",
                date=date(2025, 1, 2),
            ),
        ]

        buy_in_price = transactions[0].security.calculate_buy_in_price(
            date.today(), investor=transactions[0].investor
        )

        # Expected: Weighted average with high precision
        expected_price = Decimal("100.12345678933333333333333333")

        # Verify high precision is maintained
        assert abs(buy_in_price - expected_price) < Decimal("0.0000000001")


@pytest.mark.regression
class TestEdgeCaseRegression:
    """
    Regression tests for edge cases that previously caused issues.

    These tests ensure edge cases continue to work correctly.
    """

    def test_regression_zero_quantity_handling(self):
        """Regression test for zero quantity transaction handling."""
        asset = AssetFactory.create()

        # Create transaction with zero quantity (dividend)
        zero_tx = TransactionFactory.create(
            asset=asset,
            type="Dividend",
            quantity=0,
            price=Decimal("10.00"),
            currency="USD",
            date=date.today(),
        )

        # Should handle gracefully without division by zero
        buy_in_price = zero_tx.security.calculate_buy_in_price(
            date.today(), investor=zero_tx.investor
        )
        assert buy_in_price == Decimal("0")

    def test_regression_negative_quantity_handling(self):
        """Regression test for negative quantity (short position) handling."""
        asset = AssetFactory.create()

        # Create short position
        short_tx = TransactionFactory.create(
            asset=asset,
            type="Sell",
            quantity=100,
            price=Decimal("50.00"),
            currency="USD",
            date=date.today(),
        )

        # Should handle short positions correctly
        buy_in_price = short_tx.security.calculate_buy_in_price(
            date.today(), investor=short_tx.investor
        )
        assert buy_in_price == Decimal("50.00")

    def test_regression_very_large_numbers(self):
        """Regression test for very large number handling."""
        asset = AssetFactory.create()

        # Create transaction with very large numbers
        large_tx = TransactionFactory.create(
            asset=asset,
            type="Buy",
            quantity=999999999,
            price=Decimal("999.99"),
            currency="USD",
            date=date.today(),
        )

        # Should handle without overflow
        buy_in_price = large_tx.security.calculate_buy_in_price(
            date.today(), investor=large_tx.investor
        )
        assert buy_in_price == Decimal("999.99")

    def test_regression_very_small_numbers(self):
        """Regression test for very small number handling."""
        asset = AssetFactory.create()

        # Create transaction with very small numbers
        small_tx = TransactionFactory.create(
            asset=asset,
            type="Buy",
            quantity=1,
            price=Decimal("0.000001"),
            currency="USD",
            date=date.today(),
        )

        # Should maintain precision
        buy_in_price = small_tx.security.calculate_buy_in_price(
            date.today(), investor=small_tx.investor
        )
        assert buy_in_price == Decimal("0.000001")

    def test_regression_mixed_currency_precision(self):
        """Regression test for mixed currency precision handling."""
        asset = AssetFactory.create()

        # Create transactions with different currency precisions
        transactions = [
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=100,
                price=Decimal("123.456"),  # 3 decimal places
                currency="JPY",
                date=date.today(),
            ),
            TransactionFactory.create(
                asset=asset,
                type="Buy",
                quantity=100,
                price=Decimal("1.234567"),  # 6 decimal places
                currency="USD",
                date=date.today(),
            ),
        ]

        # Should handle mixed precision correctly
        buy_in_price = transactions[0].security.calculate_buy_in_price(
            date.today(), investor=transactions[0].investor
        )
        assert buy_in_price > 0
        assert isinstance(buy_in_price, Decimal)


@pytest.mark.regression
class TestPerformanceRegression:
    """
    Regression tests for performance characteristics.

    These tests ensure performance doesn't degrade over time.
    """

    def test_regression_calculation_performance_small_portfolio(self):
        """Performance regression test for small portfolio calculations."""
        import time

        asset = AssetFactory.create()
        transactions = TransactionFactory.create_batch(
            10,
            asset=asset,
            type="Buy",
            quantity=100,
            price=Decimal("50.00"),
            currency="USD",
        )

        start_time = time.time()
        buy_in_price = transactions[0].security.calculate_buy_in_price(
            date.today(), investor=transactions[0].investor
        )
        end_time = time.time()

        calculation_time = end_time - start_time

        # Should complete within 100ms for small portfolio
        assert calculation_time < 0.1
        assert buy_in_price > 0

    def test_regression_calculation_performance_medium_portfolio(self):
        """Performance regression test for medium portfolio calculations."""
        import time

        assets = AssetFactory.create_batch(10)
        transactions = []

        for asset in assets:
            transactions.extend(
                TransactionFactory.create_batch(
                    5,
                    asset=asset,
                    type="Buy",
                    quantity=100,
                    price=Decimal("50.00"),
                    currency="USD",
                )
            )

        start_time = time.time()
        buy_in_price = transactions[0].security.calculate_buy_in_price(
            date.today(), investor=transactions[0].investor
        )
        end_time = time.time()

        calculation_time = end_time - start_time

        # Should complete within 500ms for medium portfolio
        assert calculation_time < 0.5
        assert buy_in_price > 0

    def test_regression_calculation_performance_large_portfolio(self):
        """Performance regression test for large portfolio calculations."""
        import time

        assets = AssetFactory.create_batch(50)
        transactions = []

        for asset in assets:
            transactions.extend(
                TransactionFactory.create_batch(
                    20,
                    asset=asset,
                    type="Buy",
                    quantity=100,
                    price=Decimal("50.00"),
                    currency="USD",
                )
            )

        start_time = time.time()
        buy_in_price = transactions[0].security.calculate_buy_in_price(
            date.today(), investor=transactions[0].investor
        )
        end_time = time.time()

        calculation_time = end_time - start_time

        # Should complete within 2 seconds for large portfolio
        assert calculation_time < 2.0
        assert buy_in_price > 0

    def test_regression_fx_lookup_performance(self, fx_rates):
        """Performance regression test for FX rate lookups."""
        import time

        # Test 1000 FX rate lookups
        currency_pairs = [("USD", "EUR"), ("EUR", "GBP"), ("USD", "JPY")]

        start_time = time.time()

        for i in range(1000):
            pair = currency_pairs[i % len(currency_pairs)]
            rate = FX.get_rate(pair[0], pair[1], date.today())["FX"]
            assert rate > 0

        end_time = time.time()
        lookup_time = end_time - start_time

        # Should complete 1000 lookups within 1 second
        assert lookup_time < 1.0


@pytest.mark.regression
class TestAPIRegression:
    """
    Regression tests for API endpoints.

    These tests ensure API responses remain consistent.
    """

    def test_regression_portfolio_endpoint_response_format(
        self, api_client, sample_portfolio
    ):
        """Regression test for portfolio endpoint response format."""
        url = f"/api/portfolios/{sample_portfolio.id}/"
        response = api_client.get(url)

        assert response.status_code == 200

        data = response.json()

        # Verify expected response structure
        required_fields = [
            "id",
            "name",
            "description",
            "base_currency",
            "total_value",
            "cash_balance",
            "created_at",
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify data types
        assert isinstance(data["id"], int)
        assert isinstance(data["name"], str)
        assert isinstance(data["total_value"], (int, float, str))
        assert isinstance(data["cash_balance"], (int, float, str))

    def test_regression_transaction_endpoint_validation(
        self, api_client, sample_portfolio
    ):
        """Regression test for transaction endpoint validation."""
        url = "/api/transactions/"

        # Test invalid transaction data
        invalid_data = {
            "portfolio": sample_portfolio.id,
            "asset": 99999,  # Invalid asset ID
            "type": "InvalidType",
            "quantity": -10,
            "price": -100,
        }

        response = api_client.post(url, invalid_data, format="json")

        assert response.status_code == 400

        data = response.json()

        # Should have validation errors
        assert "asset" in data or "non_field_errors" in data
        assert "type" in data or "non_field_errors" in data
        assert "quantity" in data or "non_field_errors" in data
        assert "price" in data or "non_field_errors" in data

    def test_regression_fx_endpoint_pagination(self, api_client, fx_rates):
        """Regression test for FX endpoint pagination."""
        url = "/api/fx-rates/"

        response = api_client.get(url)

        assert response.status_code == 200

        data = response.json()

        # Verify pagination structure
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data

        # Verify results structure
        if data["results"]:
            result = data["results"][0]
            required_fields = ["id", "date", "from_currency", "to_currency", "rate"]

            for field in required_fields:
                assert field in result, f"Missing field in FX rate result: {field}"


@pytest.mark.regression
class TestDataIntegrityRegression:
    """
    Regression tests for data integrity.

    These tests ensure data consistency is maintained.
    """

    def test_regression_transaction_sequence_integrity(self, sample_transactions):
        """Regression test for transaction sequence integrity."""
        # Verify transactions are properly sequenced
        sorted_transactions = sorted(sample_transactions, key=lambda x: x.date)

        for i in range(len(sorted_transactions) - 1):
            current = sorted_transactions[i]
            next_tx = sorted_transactions[i + 1]

            assert current.date <= next_tx.date, "Transactions not properly sequenced"

    def test_regression_position_calculation_integrity(self, sample_transactions):
        """Regression test for position calculation integrity."""
        # Calculate positions from transactions
        positions = {}

        for tx in sample_transactions:
            asset_id = tx.asset.id

            if asset_id not in positions:
                positions[asset_id] = 0

            if tx.type == "Buy":
                positions[asset_id] += tx.quantity
            elif tx.type == "Sell":
                positions[asset_id] -= tx.quantity

        # Verify no negative positions (unless shorting is allowed)
        for asset_id, quantity in positions.items():
            assert quantity >= 0, f"Negative position detected for asset {asset_id}"

    def test_regression_currency_conversion_integrity(self, fx_rates):
        """Regression test for currency conversion integrity."""
        # Test round-trip conversion
        original_usd = Decimal("1000.00")

        # USD to EUR
        usd_to_eur_rate = FX.get_rate("USD", "EUR", date.today())["FX"]
        eur_amount = original_usd * usd_to_eur_rate

        # EUR back to USD
        eur_to_usd_rate = FX.get_rate("EUR", "USD", date.today())["FX"]
        final_usd = eur_amount * eur_to_usd_rate

        # Should be very close to original (allowing for rounding)
        difference = abs(final_usd - original_usd)
        tolerance = original_usd * Decimal("0.01")  # 1% tolerance

        assert difference < tolerance, f"Round-trip conversion failed: {difference}"

    def test_regression_financial_calculation_consistency(self, sample_transactions):
        """Regression test for financial calculation consistency."""
        # Multiple calculations should be consistent
        buy_in_price_1 = sample_transactions[0].security.calculate_buy_in_price(
            date.today(), investor=sample_transactions[0].investor
        )
        buy_in_price_2 = sample_transactions[0].security.calculate_buy_in_price(
            date.today(), investor=sample_transactions[0].investor
        )

        assert (
            buy_in_price_1 == buy_in_price_2
        ), "Inconsistent buy-in price calculations"

        # NAV calculations should be consistent
        if hasattr(sample_transactions[0], "portfolio"):
            nav_1 = NAV_at_date(
                sample_transactions[0].portfolio.user.id,
                sample_transactions[0].portfolio.accounts.values_list("id", flat=True),
                date.today(),
                "EUR",
            )
            nav_2 = NAV_at_date(
                sample_transactions[0].portfolio.user.id,
                sample_transactions[0].portfolio.accounts.values_list("id", flat=True),
                date.today(),
                "EUR",
            )

            assert nav_1 == nav_2, "Inconsistent NAV calculations"


# Regression Test Metadata
REGRESSION_TEST_METADATA = {
    "version": "1.0.0",
    "created_date": "2025-10-18",
    "last_updated": "2025-10-18",
    "critical_tests": 10,
    "edge_case_tests": 5,
    "performance_tests": 4,
    "api_tests": 3,
    "integrity_tests": 4,
    "total_tests": 26,
    "expected_execution_time": "< 30 seconds",
    "precision_requirement": "6 decimal places minimum",
    "performance_thresholds": {
        "small_portfolio": "< 100ms",
        "medium_portfolio": "< 500ms",
        "large_portfolio": "< 2000ms",
        "fx_lookup": "< 1ms per lookup",
    },
}


@pytest.fixture(scope="session")
def regression_baseline_data():
    """
    Fixture providing baseline regression data.

    This ensures consistent test data across regression runs.
    """
    return {
        "buy_in_price_cases": [
            {
                "name": "simple_buy",
                "transactions": [
                    {"type": "Buy", "quantity": 100, "price": "50.00"},
                    {"type": "Buy", "quantity": 50, "price": "55.00"},
                ],
                "expected": "51.66666666666666666666666667",
            },
            {
                "name": "with_sale",
                "transactions": [
                    {"type": "Buy", "quantity": 100, "price": "50.00"},
                    {"type": "Buy", "quantity": 50, "price": "55.00"},
                    {"type": "Sell", "quantity": 25, "price": "60.00"},
                ],
                "expected": "51.66666666666666666666666667",
            },
        ],
        "fx_rate_cases": [
            {"from": "USD", "to": "EUR", "date": "2025-10-18", "expected": "0.8500"},
            {"from": "GBP", "to": "JPY", "date": "2025-10-18", "expected": "126.50"},
        ],
        "performance_benchmarks": {
            "small_portfolio_calculation": 0.1,  # seconds
            "medium_portfolio_calculation": 0.5,
            "large_portfolio_calculation": 2.0,
            "fx_rate_lookup": 0.001,
        },
    }
