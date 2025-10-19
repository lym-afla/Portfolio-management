"""
Test cases for Asset model methods and position calculations.

This module tests the Asset model functionality including:
- Position calculation methods
- Entry and exit date detection
- Price retrieval methods
- Asset-level calculations
- Multi-broker position handling
"""

from datetime import date
from decimal import Decimal

import pytest

from common.models import Prices
from common.models import Transactions


@pytest.mark.unit
class TestAssetPositionCalculation:
    """Test asset position calculation functionality."""

    def test_position_single_purchase(self, user, broker, asset):
        """Test position calculation with single purchase."""
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

        position = asset.position(date(2023, 1, 16))
        assert position == Decimal("100")

    def test_position_multiple_purchases(self, user, broker, asset):
        """Test position calculation with multiple purchases."""
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

        position = asset.position(date(2023, 2, 16))
        assert position == Decimal("150")

    def test_position_with_partial_sale(self, user, broker, asset):
        """Test position calculation after partial sale."""
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
            type="Sell",
            date=date(2023, 3, 15),
            quantity=Decimal("-30"),
            price=Decimal("60.00"),
            cash_flow=Decimal("1800.00"),
            commission=Decimal("3.00"),
        )

        position = asset.position(date(2023, 3, 16))
        assert position == Decimal("70")

    def test_position_after_full_sale(self, user, broker, asset):
        """Test position calculation after full sale."""
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
            type="Sell",
            date=date(2023, 2, 15),
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            cash_flow=Decimal("5500.00"),
            commission=Decimal("5.00"),
        )

        position = asset.position(date(2023, 2, 16))
        assert position == Decimal("0")

    def test_position_short_position(self, user, broker, asset):
        """Test position calculation for short positions."""
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

        position = asset.position(date(2023, 1, 16))
        assert position == Decimal("-100")

    def test_position_covering_short(self, user, broker, asset):
        """Test position calculation when covering short position."""
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

        position = asset.position(date(2023, 2, 16))
        assert position == Decimal("-50")

    def test_position_broker_filtering(self, user, broker, broker_uk, asset):
        """Test position calculation with broker filtering."""
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
            quantity=Decimal("75"),
            price=Decimal("52.00"),
            cash_flow=Decimal("-3900.00"),
            commission=Decimal("4.00"),
        )

        # Calculate position for first broker only
        position_broker1 = asset.position(date(2023, 2, 16), broker_id_list=[broker.id])
        assert position_broker1 == Decimal("100")

        # Calculate position for second broker only
        position_broker2 = asset.position(
            date(2023, 2, 16), broker_id_list=[broker_uk.id]
        )
        assert position_broker2 == Decimal("75")

        # Calculate position for both brokers
        position_both = asset.position(
            date(2023, 2, 16), broker_id_list=[broker.id, broker_uk.id]
        )
        assert position_both == Decimal("175")

    def test_position_date_boundary(self, user, broker, asset):
        """Test position calculation at date boundaries."""
        transaction_date = date(2023, 1, 15)

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=transaction_date,
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Position before transaction should be zero
        position_before = asset.position(date(2023, 1, 14))
        assert position_before == Decimal("0")

        # Position on transaction date should include transaction
        position_on = asset.position(transaction_date)
        assert position_on == Decimal("100")

        # Position after transaction should include transaction
        position_after = asset.position(date(2023, 1, 16))
        assert position_after == Decimal("100")

    def test_position_no_transactions(self, user, broker, asset):
        """Test position calculation with no transactions."""
        position = asset.position(date(2023, 6, 15))
        assert position == Decimal("0")

    def test_position_future_date(self, user, broker, asset):
        """Test position calculation for future dates."""
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

        future_position = asset.position(date(2025, 1, 1))
        current_position = asset.position(date(2023, 6, 15))

        assert future_position == current_position


@pytest.mark.unit
class TestAssetEntryExitDates:
    """Test asset entry and exit date detection."""

    def test_entry_dates_single_purchase(self, user, broker, asset):
        """Test entry date detection with single purchase."""
        purchase_date = date(2023, 1, 15)

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=purchase_date,
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        entry_dates = asset.entry_dates(date(2023, 6, 15))
        assert len(entry_dates) == 1
        assert entry_dates[0] == purchase_date

    def test_entry_dates_multiple_purchases(self, user, broker, asset):
        """Test entry date detection with multiple purchases."""
        first_purchase = date(2023, 1, 15)
        second_purchase = date(2023, 3, 15)

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=first_purchase,
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
            date=second_purchase,
            quantity=Decimal("50"),
            price=Decimal("55.00"),
            cash_flow=Decimal("-2750.00"),
            commission=Decimal("3.00"),
        )

        entry_dates = asset.entry_dates(date(2023, 6, 15))
        assert len(entry_dates) == 1  # Only first entry from zero to non-zero
        assert entry_dates[0] == first_purchase

    def test_entry_dates_after_full_sale(self, user, broker, asset):
        """Test entry date detection after full sale and repurchase."""
        purchase1 = date(2023, 1, 15)
        sale = date(2023, 2, 15)
        purchase2 = date(2023, 3, 15)

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=purchase1,
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
            type="Sell",
            date=sale,
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            cash_flow=Decimal("5500.00"),
            commission=Decimal("5.00"),
        )

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=purchase2,
            quantity=Decimal("75"),
            price=Decimal("52.00"),
            cash_flow=Decimal("-3900.00"),
            commission=Decimal("4.00"),
        )

        entry_dates = asset.entry_dates(date(2023, 6, 15))
        assert len(entry_dates) == 2
        assert entry_dates[0] == purchase1
        assert entry_dates[1] == purchase2

    def test_exit_dates_partial_sale(self, user, broker, asset):
        """Test exit date detection with partial sale."""
        purchase = date(2023, 1, 15)
        sale = date(2023, 3, 15)

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=purchase,
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
            type="Sell",
            date=sale,
            quantity=Decimal("-30"),
            price=Decimal("60.00"),
            cash_flow=Decimal("1800.00"),
            commission=Decimal("3.00"),
        )

        exit_dates = asset.exit_dates(date(2023, 6, 15))
        assert len(exit_dates) == 0  # Position not closed

    def test_exit_dates_full_sale(self, user, broker, asset):
        """Test exit date detection with full sale."""
        purchase = date(2023, 1, 15)
        sale = date(2023, 3, 15)

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=purchase,
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
            type="Sell",
            date=sale,
            quantity=Decimal("-100"),
            price=Decimal("60.00"),
            cash_flow=Decimal("6000.00"),
            commission=Decimal("5.00"),
        )

        exit_dates = asset.exit_dates(date(2023, 6, 15))
        assert len(exit_dates) == 1
        assert exit_dates[0] == sale

    def test_entry_exit_dates_short_position(self, user, broker, asset):
        """Test entry/exit dates for short positions."""
        short_sale = date(2023, 1, 15)
        cover = date(2023, 3, 15)

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Sell",
            date=short_sale,
            quantity=Decimal("-100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("5000.00"),
            commission=Decimal("5.00"),
        )

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=cover,
            quantity=Decimal("100"),
            price=Decimal("45.00"),
            cash_flow=Decimal("-4500.00"),
            commission=Decimal("5.00"),
        )

        entry_dates = asset.entry_dates(date(2023, 6, 15))
        exit_dates = asset.exit_dates(date(2023, 6, 15))

        # For short positions, entry is when position goes from 0 to negative
        assert len(entry_dates) == 1
        assert entry_dates[0] == short_sale

        # Exit is when position goes from negative to 0
        assert len(exit_dates) == 1
        assert exit_dates[0] == cover

    def test_entry_exit_dates_with_start_date(self, user, broker, asset):
        """Test entry/exit dates with start date constraint."""
        old_purchase = date(2022, 1, 15)
        new_purchase = date(2023, 1, 15)
        sale = date(2023, 3, 15)

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=old_purchase,
            quantity=Decimal("100"),
            price=Decimal("40.00"),
            cash_flow=Decimal("-4000.00"),
            commission=Decimal("4.00"),
        )

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=new_purchase,
            quantity=Decimal("50"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-2500.00"),
            commission=Decimal("3.00"),
        )

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Sell",
            date=sale,
            quantity=Decimal("-25"),
            price=Decimal("55.00"),
            cash_flow=Decimal("1375.00"),
            commission=Decimal("3.00"),
        )

        start_date = date(2023, 1, 1)

        entry_dates = asset.entry_dates(date(2023, 6, 15), start_date=start_date)
        exit_dates = asset.exit_dates(date(2023, 6, 15), start_date=start_date)

        # Should ignore old transaction
        assert len(entry_dates) == 1
        assert entry_dates[0] == new_purchase

        # Exit dates should be after start date
        for exit_date in exit_dates:
            assert exit_date >= start_date


@pytest.mark.unit
class TestAssetPriceMethods:
    """Test asset price retrieval methods."""

    def test_price_at_date_exact_match(self, user, broker, asset):
        """Test price retrieval with exact date match."""
        test_date = date(2023, 6, 15)
        test_price = Decimal("55.25")

        Prices.objects.create(date=test_date, security=asset, price=test_price)

        price_record = asset.price_at_date(test_date)
        assert price_record is not None
        assert price_record.price == test_price
        assert price_record.date == test_date

    def test_price_at_date_before_date(self, user, broker, asset):
        """Test price retrieval with date before available data."""
        # Create price data starting from a specific date
        start_date = date(2023, 2, 1)
        Prices.objects.create(date=start_date, security=asset, price=Decimal("50.00"))

        # Request price before start date
        early_date = date(2023, 1, 15)
        price_record = asset.price_at_date(early_date)

        assert price_record is None  # Should return None when no price available

    def test_price_at_date_latest_before(self, user, broker, asset):
        """Test price retrieval getting latest price before date."""
        # Create multiple price records
        Prices.objects.create(
            date=date(2023, 5, 15), security=asset, price=Decimal("50.00")
        )

        Prices.objects.create(
            date=date(2023, 6, 1), security=asset, price=Decimal("52.00")
        )

        # Request price between records
        request_date = date(2023, 6, 10)
        price_record = asset.price_at_date(request_date)

        assert price_record is not None
        assert price_record.price == Decimal("52.00")  # Should get latest before date
        assert price_record.date == date(2023, 6, 1)

    def test_price_at_date_with_currency_conversion(
        self, multi_currency_user, broker, asset_eur, fx_rates_multi_currency
    ):
        """Test price retrieval with currency conversion."""
        test_date = date(2023, 6, 15)
        local_price = Decimal("40.00")

        Prices.objects.create(date=test_date, security=asset_eur, price=local_price)

        # Get price in local currency (EUR)
        price_eur = asset_eur.price_at_date(test_date, currency="EUR")
        assert price_eur.price == local_price

        # Get price in converted currency (USD)
        price_usd = asset_eur.price_at_date(test_date, currency="USD")
        assert price_usd.price > local_price  # USD should be higher value

    def test_price_at_date_no_price_data(self, user, broker, asset):
        """Test price retrieval when no price data exists."""
        price_record = asset.price_at_date(date(2023, 6, 15))
        assert price_record is None

    def test_investment_date_single_transaction(self, user, broker, asset):
        """Test investment date detection with single transaction."""
        transaction_date = date(2023, 1, 15)

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=transaction_date,
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        investment_date = asset.investment_date()
        assert investment_date == transaction_date

    def test_investment_date_multiple_transactions(self, user, broker, asset):
        """Test investment date detection with multiple transactions."""
        first_date = date(2023, 1, 15)
        second_date = date(2023, 2, 15)

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=first_date,
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
            date=second_date,
            quantity=Decimal("50"),
            price=Decimal("55.00"),
            cash_flow=Decimal("-2750.00"),
            commission=Decimal("3.00"),
        )

        investment_date = asset.investment_date()
        assert investment_date == first_date  # Should return earliest transaction

    def test_investment_date_no_transactions(self, user, broker, asset):
        """Test investment date detection with no transactions."""
        investment_date = asset.investment_date()
        assert investment_date is None

    def test_investment_date_with_broker_filter(self, user, broker, broker_uk, asset):
        """Test investment date detection with broker filtering."""
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
            quantity=Decimal("75"),
            price=Decimal("52.00"),
            cash_flow=Decimal("-3900.00"),
            commission=Decimal("4.00"),
        )

        # Investment date for first broker
        investment_date_broker1 = asset.investment_date(broker_id_list=[broker.id])
        assert investment_date_broker1 == date(2023, 1, 15)

        # Investment date for second broker
        investment_date_broker2 = asset.investment_date(broker_id_list=[broker_uk.id])
        assert investment_date_broker2 == date(2023, 2, 15)


@pytest.mark.unit
class TestAssetEdgeCases:
    """Test edge cases in asset model methods."""

    def test_position_very_small_quantities(self, user, broker, asset):
        """Test position calculation with very small quantities."""
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("0.000001"),
            price=Decimal("1000000.00"),
            cash_flow=Decimal("-1.00"),
            commission=Decimal("0.01"),
        )

        position = asset.position(date(2023, 1, 16))
        assert position == Decimal("0.000001")
        assert position.as_tuple().exponent <= -6

    def test_position_very_large_quantities(self, user, broker, asset):
        """Test position calculation with very large quantities."""
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("1000000000"),
            price=Decimal("0.01"),
            cash_flow=Decimal("-10000000.00"),
            commission=Decimal("100.00"),
        )

        position = asset.position(date(2023, 1, 16))
        assert position == Decimal("1000000000")

    def test_position_decimal_precision(self, user, broker, asset):
        """Test position calculation maintains decimal precision."""
        quantity = Decimal("1.23456789")

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=quantity,
            price=Decimal("50.00"),
            cash_flow=Decimal("-61.73"),
            commission=Decimal("0.05"),
        )

        position = asset.position(date(2023, 1, 16))
        assert position == quantity
        assert position.as_tuple().exponent <= -8

    def test_mixed_transaction_types(self, user, broker, asset):
        """Test position calculation with mixed transaction types."""
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

        # Dividend should not affect position
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Dividend",
            date=date(2023, 2, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("200.00"),
            commission=None,
        )

        # Interest should not affect position
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

        position = asset.position(date(2023, 4, 15))
        assert position == Decimal("100")  # Should only count quantity transactions

    def test_position_with_corporate_action(self, user, broker, asset):
        """Test position calculation with corporate actions."""
        # Initial purchase
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
            quantity=Decimal("100"),  # Additional shares from 2:1 split
            price=Decimal("50.00"),  # Adjusted price
            cash_flow=Decimal("0.00"),
            commission=None,
        )

        position = asset.position(date(2023, 2, 2))
        assert position == Decimal("200")  # Should be 200 shares after split
