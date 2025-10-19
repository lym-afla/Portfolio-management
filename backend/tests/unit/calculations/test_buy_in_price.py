"""
Test cases for buy-in price calculation algorithms.

This module tests the core buy-in price calculation logic including:
- Average buy-in price for long positions
- Average buy-in price for short positions
- Partial sales and position adjustments
- Multi-currency buy-in price calculations
- Edge cases and error handling
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from common.models import Assets, Transactions


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.django_db
class TestBuyInPriceCalculation:
    """Test buy-in price calculation functionality."""

    def test_buy_in_price_single_purchase(self, user, broker, asset):
        """Test buy-in price calculation with single purchase."""
        # Create purchase transaction
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 1, 16))

        assert buy_in_price == Decimal("50.00")

    def test_buy_in_price_multiple_purchases(self, user, broker, asset):
        """Test buy-in price calculation with multiple purchases."""
        # Create multiple purchase transactions
        Transactions.objects.create(
            investor=user,
            broker=broker,
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
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("50"),
            price=Decimal("55.00"),
            cash_flow=Decimal("-2750.00"),
            commission=Decimal("3.00"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 2, 16))

        # Weighted average: (100*50 + 50*55) / 150 = 51.666...
        expected_price = (Decimal("5000") + Decimal("2750")) / Decimal("150")
        assert buy_in_price == expected_price.quantize(Decimal("0.000001"))

    def test_buy_in_price_with_partial_sale(self, user, broker, asset):
        """Test buy-in price calculation after partial sale."""
        # Create initial purchases
        Transactions.objects.create(
            investor=user,
            broker=broker,
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
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("50"),
            price=Decimal("55.00"),
            cash_flow=Decimal("-2750.00"),
            commission=Decimal("3.00"),
        )

        # Partial sale
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 3, 15),
            quantity=Decimal("-30"),
            price=Decimal("60.00"),
            cash_flow=Decimal("1800.00"),
            commission=Decimal("3.00"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 3, 16))

        # Buy-in price should remain the same as it's based on remaining position
        expected_price = (Decimal("5000") + Decimal("2750")) / Decimal("150")
        assert buy_in_price == expected_price.quantize(Decimal("0.000001"))

    def test_buy_in_price_after_full_sale(self, user, broker, asset):
        """Test buy-in price calculation after position is closed."""
        # Create purchase
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Full sale
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 2, 15),
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            cash_flow=Decimal("5500.00"),
            commission=Decimal("5.00"),
        )

        # Buy new position
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 3, 15),
            quantity=Decimal("75"),
            price=Decimal("52.00"),
            cash_flow=Decimal("-3900.00"),
            commission=Decimal("4.00"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 3, 16))

        # Should be based on new position only
        assert buy_in_price == Decimal("52.00")

    def test_buy_in_price_short_position(self, user, broker, asset):
        """Test buy-in price calculation for short positions."""
        # Create short sale
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 1, 15),
            quantity=Decimal("-100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("5000.00"),
            commission=Decimal("5.00"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 1, 16))

        # For short positions, buy-in price should be the sale price
        assert buy_in_price == Decimal("50.00")

    def test_buy_in_price_short_position_cover(self, user, broker, asset):
        """Test buy-in price calculation when covering short position."""
        # Create short sale
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 1, 15),
            quantity=Decimal("-100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("5000.00"),
            commission=Decimal("5.00"),
        )

        # Cover part of short position
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("50"),
            price=Decimal("45.00"),
            cash_flow=Decimal("-2250.00"),
            commission=Decimal("3.00"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 2, 16))

        # For remaining short position, buy-in price should still be original sale price
        assert buy_in_price == Decimal("50.00")

    def test_buy_in_price_multi_currency(
        self, multi_currency_user, broker, asset_eur, fx_rates_multi_currency
    ):
        """Test buy-in price calculation with multi-currency conversion."""
        # Create EUR purchase
        Transactions.objects.create(
            investor=multi_currency_user,
            broker=broker,
            security=asset_eur,
            currency="EUR",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("40.00"),
            cash_flow=Decimal("-4000.00"),
            commission=Decimal("4.00"),
        )

        # Calculate buy-in price in EUR (local currency)
        buy_in_price_eur = asset_eur.calculate_buy_in_price(date(2023, 1, 16))
        assert buy_in_price_eur == Decimal("40.00")

        # Calculate buy-in price in USD (converted)
        buy_in_price_usd = asset_eur.calculate_buy_in_price(
            date(2023, 1, 16), currency="USD"
        )
        assert buy_in_price_usd > Decimal("40.00")  # EUR converted to USD
        assert buy_in_price_usd < Decimal("50.00")  # Reasonable conversion rate

    def test_buy_in_price_with_start_date(self, user, broker, asset):
        """Test buy-in price calculation with start date constraint."""
        # Create old transaction
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2022, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("30.00"),
            cash_flow=Decimal("-3000.00"),
            commission=Decimal("3.00"),
        )

        # Create new transaction
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Calculate with start date (should ignore old transaction)
        start_date = date(2023, 1, 1)
        buy_in_price = asset.calculate_buy_in_price(
            date(2023, 1, 16), start_date=start_date
        )

        # Should only consider new transaction
        assert buy_in_price == Decimal("50.00")

        # Calculate without start date (should include both)
        buy_in_price_all = asset.calculate_buy_in_price(date(2023, 1, 16))
        expected_all = (Decimal("3000") + Decimal("5000")) / Decimal("200")
        assert buy_in_price_all == expected_all.quantize(Decimal("0.000001"))

    def test_buy_in_price_no_transactions(self, user, broker, asset):
        """Test buy-in price calculation with no transactions."""
        buy_in_price = asset.calculate_buy_in_price(date(2023, 1, 16))
        assert buy_in_price is None

    def test_buy_in_price_zero_position(self, user, broker, asset):
        """Test buy-in price calculation when position is zero."""
        # Create purchase
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create equal sale
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 2, 15),
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            cash_flow=Decimal("5500.00"),
            commission=Decimal("5.00"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 2, 16))
        assert buy_in_price is None

    def test_buy_in_price_broker_filter(self, user, broker, broker_uk, asset):
        """Test buy-in price calculation with broker filter."""
        # Create transaction with first broker
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create transaction with second broker
        Transactions.objects.create(
            investor=user,
            broker=broker_uk,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("100"),
            price=Decimal("60.00"),
            cash_flow=Decimal("-6000.00"),
            commission=Decimal("6.00"),
        )

        # Calculate for first broker only
        buy_in_price_broker1 = asset.calculate_buy_in_price(
            date(2023, 2, 16), broker_id_list=[broker.id]
        )
        assert buy_in_price_broker1 == Decimal("50.00")

        # Calculate for second broker only
        buy_in_price_broker2 = asset.calculate_buy_in_price(
            date(2023, 2, 16), broker_id_list=[broker_uk.id]
        )
        assert buy_in_price_broker2 == Decimal("60.00")

        # Calculate for both brokers
        buy_in_price_both = asset.calculate_buy_in_price(
            date(2023, 2, 16), broker_id_list=[broker.id, broker_uk.id]
        )
        expected_both = (Decimal("5000") + Decimal("6000")) / Decimal("200")
        assert buy_in_price_both == expected_both.quantize(Decimal("0.000001"))


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.django_db
class TestBuyInPriceEdgeCases:
    """Test edge cases and complex scenarios in buy-in price calculations."""

    def test_buy_in_price_dividend_transactions(self, user, broker, asset):
        """Test that dividend transactions don't affect buy-in price."""
        # Create purchase
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create dividend
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Dividend",
            date=date(2023, 3, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("200.00"),
            commission=None,
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 3, 16))
        assert buy_in_price == Decimal("50.00")

    def test_buy_in_price_corporate_action(self, user, broker, asset):
        """Test buy-in price calculation around corporate actions."""
        # Create purchase
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("100.00"),
            cash_flow=Decimal("-10000.00"),
            commission=Decimal("10.00"),
        )

        # Corporate action (stock split)
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Corporate Action",
            date=date(2023, 2, 1),
            quantity=Decimal("100"),  # Additional shares from split
            price=Decimal("50.00"),  # Adjusted price
            cash_flow=Decimal("0.00"),
            commission=None,
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 2, 2))
        # After 2:1 split, effective buy-in price should be $50
        assert buy_in_price == Decimal("50.00")

    def test_buy_in_price_very_small_quantities(self, user, broker, asset):
        """Test buy-in price calculation with very small quantities."""
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("0.001"),
            price=Decimal("1000.00"),
            cash_flow=Decimal("-1.00"),
            commission=Decimal("0.01"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 1, 16))
        assert buy_in_price == Decimal("1000.00")

    def test_buy_in_price_very_large_quantities(self, user, broker, asset):
        """Test buy-in price calculation with very large quantities."""
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("1000000"),
            price=Decimal("0.01"),
            cash_flow=Decimal("-10000.00"),
            commission=Decimal("10.00"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 1, 16))
        assert buy_in_price == Decimal("0.01")

    def test_buy_in_price_high_precision(self, user, broker, asset):
        """Test buy-in price calculation with high precision requirements."""
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("1.234567"),
            price=Decimal("123.456789"),
            cash_flow=Decimal("-152.41579"),
            commission=Decimal("0.15"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 1, 16))
        assert buy_in_price == Decimal("123.456789")
        # Should maintain high precision
        assert buy_in_price.as_tuple().exponent <= -6

    def test_buy_in_price_commission_impact(self, user, broker, asset):
        """Test that commission doesn't affect buy-in price calculation."""
        # Create purchase with high commission
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5100.00"),  # Includes $100 commission
            commission=Decimal("100.00"),
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 1, 16))
        # Commission should not affect buy-in price
        assert buy_in_price == Decimal("50.00")

    def test_buy_in_price_mixed_transaction_types(self, user, broker, asset):
        """Test buy-in price calculation with mixed transaction types."""
        # Create purchase
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create dividend
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Dividend",
            date=date(2023, 2, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("100.00"),
            commission=None,
        )

        # Create interest payment
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Interest",
            date=date(2023, 3, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("50.00"),
            commission=None,
        )

        buy_in_price = asset.calculate_buy_in_price(date(2023, 3, 16))
        # Should only be based on purchase transactions
        assert buy_in_price == Decimal("50.00")


@pytest.mark.nav
@pytest.mark.unit
@pytest.mark.django_db
class TestBuyInPricePerformance:
    """Test performance of buy-in price calculations."""

    def test_buy_in_price_performance_single_calculation(self, user, broker, asset):
        """Test performance of single buy-in price calculation."""
        import time

        # Create multiple transactions
        for i in range(100):
            Transactions.objects.create(
                investor=user,
                broker=broker,
                security=asset,
                currency="USD",
                type="Buy" if i % 2 == 0 else "Sell",
                date=date(2023, 1, 1) + timedelta(days=i),
                quantity=Decimal("10") if i % 2 == 0 else Decimal("-5"),
                price=Decimal("50") + (i % 10),
                cash_flow=Decimal("-500") if i % 2 == 0 else Decimal("250"),
                commission=Decimal("5"),
            )

        start_time = time.time()
        buy_in_price = asset.calculate_buy_in_price(date(2023, 4, 1))
        end_time = time.time()

        execution_time = end_time - start_time
        assert execution_time < 1.0  # Should complete within 1 second
        assert buy_in_price is not None

    def test_buy_in_price_performance_batch_calculation(self, user, broker):
        """Test performance of batch buy-in price calculations."""
        import time

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
            asset.investors.add(user)
            asset.brokers.add(broker)
            assets.append(asset)

            # Create transactions for each asset
            for j in range(20):
                Transactions.objects.create(
                    investor=user,
                    broker=broker,
                    security=asset,
                    currency="USD",
                    type="Buy",
                    date=date(2023, 1, 1) + timedelta(days=j),
                    quantity=Decimal("10"),
                    price=Decimal("50") + j,
                    cash_flow=Decimal("-500") - (j * 10),
                    commission=Decimal("5"),
                )

        start_time = time.time()
        results = []
        for asset in assets:
            buy_in_price = asset.calculate_buy_in_price(date(2023, 6, 15))
            results.append(buy_in_price)
        end_time = time.time()

        execution_time = end_time - start_time
        assert execution_time < 5.0  # Should complete within 5 seconds
        assert len(results) == 10
        assert all(r is not None for r in results)
