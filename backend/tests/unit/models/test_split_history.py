"""
Test cases for SplitHistory model and Stock split transaction handling.

This module tests:
- SplitHistory model creation
- Adjustment factor calculation
- Cumulative split factor across multiple splits
- Auto-creation of SplitHistory from Stock split transactions
- Stock split cash flow (should be zero)
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from common.models import Assets, SplitHistory, Transactions


@pytest.mark.unit
class TestSplitHistoryModel:
    """Test SplitHistory model functionality."""

    def test_split_history_creation(self, user, account, asset):
        """Test creating a split history entry."""
        split = SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="MANUAL",
            comment="2:1 stock split",
        )

        assert split.asset == asset
        assert split.date == date(2023, 6, 15)
        assert split.split_from == 1
        assert split.split_to == 2
        assert split.source == "MANUAL"

    def test_adjustment_factor_auto_calculation(self, user, account, asset):
        """Test that adjustment factor is auto-calculated on save."""
        # 2:1 split: 1 share becomes 2, price halves
        split_2_to_1 = SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="MANUAL",
        )
        assert split_2_to_1.adjustment_factor == Decimal("0.5")

        # Create another asset for different split ratio tests
        asset2 = Assets.objects.create(
            type="Stock",
            ISIN="US0987654321",
            name="Test Stock 2",
            currency="USD",
            exposure="Equity",
        )
        asset2.investors.add(user)

        # 3:1 split: 1 share becomes 3, price is 1/3
        split_3_to_1 = SplitHistory.objects.create(
            asset=asset2,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=3,
            source="MANUAL",
        )
        # Use approximate comparison for repeating decimals
        expected_factor = Decimal("1") / Decimal("3")
        assert abs(split_3_to_1.adjustment_factor - expected_factor) < Decimal("0.0001")

    def test_reverse_split_adjustment_factor(self, user, asset):
        """Test adjustment factor for reverse split."""
        # 1:5 reverse split: 5 shares become 1, price quintuples
        reverse_split = SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=5,
            split_to=1,
            source="MANUAL",
            comment="1:5 reverse split",
        )
        assert reverse_split.adjustment_factor == Decimal("5")

    def test_split_history_string_representation(self, user, asset):
        """Test split history string representation."""
        split = SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="MANUAL",
        )
        expected = f"{asset.name}: 1:2 split on 2023-06-15"
        assert str(split) == expected


@pytest.mark.unit
class TestCumulativeSplitFactor:
    """Test cumulative split factor calculations."""

    def test_no_splits_returns_one(self, user, asset):
        """Test that no splits returns factor of 1."""
        factor = asset.get_cumulative_split_factor(date(2023, 1, 1))
        assert factor == Decimal("1")

    def test_single_split_factor(self, user, asset):
        """Test cumulative factor with single split."""
        SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="MANUAL",
        )

        # Price before split should be adjusted
        factor = asset.get_cumulative_split_factor(date(2023, 1, 1))
        assert factor == Decimal("0.5")

        # Price after split should not be adjusted
        factor_after = asset.get_cumulative_split_factor(date(2023, 7, 1))
        assert factor_after == Decimal("1")

    def test_multiple_splits_cumulative_factor(self, user, asset):
        """Test cumulative factor with multiple splits."""
        # First split: 2:1 on June 15
        SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="MANUAL",
        )

        # Second split: 3:1 on September 15
        SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 9, 15),
            split_from=1,
            split_to=3,
            source="MANUAL",
        )

        # Price from January should be adjusted by both splits: 0.5 * 0.333... = 0.1666...
        factor = asset.get_cumulative_split_factor(date(2023, 1, 1))
        expected = Decimal("0.5") * Decimal("1") / Decimal("3")
        assert abs(factor - expected) < Decimal("0.0001")

        # Price from July (between splits) should only be adjusted by second split
        factor_july = asset.get_cumulative_split_factor(date(2023, 7, 1))
        expected_july = Decimal("1") / Decimal("3")
        assert abs(factor_july - expected_july) < Decimal("0.0001")

        # Price from October (after both splits) should not be adjusted
        factor_oct = asset.get_cumulative_split_factor(date(2023, 10, 1))
        assert factor_oct == Decimal("1")

    def test_cumulative_factor_with_to_date(self, user, asset):
        """Test cumulative factor with explicit to_date parameter."""
        # First split: 2:1 on June 15
        SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="MANUAL",
        )

        # Second split: 3:1 on September 15
        SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 9, 15),
            split_from=1,
            split_to=3,
            source="MANUAL",
        )

        # From January to July: only first split applies
        factor = asset.get_cumulative_split_factor(
            date(2023, 1, 1), to_date=date(2023, 7, 1)
        )
        assert factor == Decimal("0.5")


@pytest.mark.unit
class TestSplitAdjustedPrice:
    """Test price adjustment methods."""

    def test_get_split_adjusted_price(self, user, asset):
        """Test get_split_adjusted_price method."""
        SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="MANUAL",
        )

        # Historical price of 100 before 2:1 split should show as 50 today
        adjusted = asset.get_split_adjusted_price(
            Decimal("100"), date(2023, 1, 1)
        )
        assert adjusted == Decimal("50")

    def test_reverse_split_adjustment(self, user, asset):
        """Test reverse_split_adjustment method."""
        SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="MANUAL",
        )

        # T-Bank reports split-adjusted price of 50
        # Actual historical price before split was 100
        actual_price = asset.reverse_split_adjustment(
            Decimal("50"), date(2023, 1, 1)
        )
        assert actual_price == Decimal("100")

    def test_none_price_handling(self, user, asset):
        """Test that None prices are handled gracefully."""
        SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="MANUAL",
        )

        adjusted = asset.get_split_adjusted_price(None, date(2023, 1, 1))
        assert adjusted is None

        reversed_price = asset.reverse_split_adjustment(None, date(2023, 1, 1))
        assert reversed_price is None


@pytest.mark.unit
class TestCorporateActionTransaction:
    """Test Stock split transaction behavior."""

    def test_stock_split_zero_cash_flow(self, user, account, asset):
        """Test that Stock split transactions have zero cash flow."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("100"),  # Additional shares from 2:1 split
            price=Decimal("50.00"),  # Adjusted price post-split
            cash_flow=Decimal("0.00"),
            commission=None,
            split_from=1,
            split_to=2,
            comment="2:1 stock split",
        )

        # Cash flow should always be 0 for Stock split
        assert transaction.total_cash_flow() == Decimal("0")

    def test_stock_split_with_nonzero_cash_flow_field(self, user, account, asset):
        """Test that total_cash_flow returns 0 even if cash_flow field is set."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("1000.00"),  # Incorrectly set, should be ignored
            commission=None,
            split_from=1,
            split_to=2,
            comment="2:1 stock split",
        )

        # total_cash_flow should still return 0
        assert transaction.total_cash_flow() == Decimal("0")

    def test_stock_split_auto_creates_split_history(self, user, account, asset):
        """Test that Stock split transaction auto-creates SplitHistory."""
        # Verify no split history exists
        assert SplitHistory.objects.filter(asset=asset).count() == 0

        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("0.00"),
            commission=None,
            split_from=1,
            split_to=2,
            comment="2:1 stock split",
        )

        # SplitHistory should be auto-created
        split = SplitHistory.objects.get(asset=asset)
        assert split.transaction == transaction
        assert split.split_from == 1
        assert split.split_to == 2
        assert split.source == "TRANSACTION"

    def test_stock_split_reverse_split(self, user, account, asset):
        """Test reverse split with explicit split_from/split_to fields."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("-80"),  # Losing shares in reverse split
            price=Decimal("250.00"),
            cash_flow=Decimal("0.00"),
            commission=None,
            split_from=5,
            split_to=1,
            comment="1:5 reverse split",
        )

        # SplitHistory should be created with reverse split ratio
        split = SplitHistory.objects.get(asset=asset)
        assert split.split_from == 5
        assert split.split_to == 1
        assert split.adjustment_factor == Decimal("5")

    def test_stock_split_three_for_one(self, user, account, asset):
        """Test 3:1 split with explicit split_from/split_to fields."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("200"),
            price=Decimal("33.33"),
            cash_flow=Decimal("0.00"),
            commission=None,
            split_from=1,
            split_to=3,
            comment="3-for-1 stock split",
        )

        split = SplitHistory.objects.get(asset=asset)
        assert split.split_from == 1
        assert split.split_to == 3

    def test_stock_split_without_ratio_fields(self, user, account, asset):
        """Test that no SplitHistory is created if split_from/split_to are not provided."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("0.00"),
            commission=None,
            # split_from and split_to not provided
            comment="Stock dividend",
        )

        # No SplitHistory should be created without split ratio fields
        assert SplitHistory.objects.filter(asset=asset).count() == 0

    def test_stock_split_string_representation(self, user, account, asset):
        """Test Stock split transaction string representation."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("0.00"),
            commission=None,
            split_from=1,
            split_to=2,
            comment="2:1 stock split",
        )

        expected = f"Stock split || {transaction.date}"
        assert str(transaction) == expected

    def test_split_history_cascade_delete(self, user, account, asset):
        """Test that SplitHistory is deleted when transaction is deleted."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("0.00"),
            commission=None,
            split_from=1,
            split_to=2,
            comment="2:1 stock split",
        )

        # Verify split history exists
        assert SplitHistory.objects.filter(asset=asset).count() == 1

        # Delete transaction
        transaction.delete()

        # Split history should be cascade deleted
        assert SplitHistory.objects.filter(asset=asset).count() == 0


@pytest.mark.unit
class TestSplitHistorySourceTypes:
    """Test different source types for SplitHistory."""

    def test_manual_source(self, user, asset):
        """Test manually created split history."""
        split = SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="MANUAL",
            comment="Manually entered 2:1 split",
        )
        assert split.source == "MANUAL"
        assert split.transaction is None

    def test_transaction_source(self, user, account, asset):
        """Test split history created from transaction."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Stock split",
            date=date(2023, 6, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("0.00"),
            split_from=1,
            split_to=2,
            comment="2:1 split",
        )

        split = SplitHistory.objects.get(asset=asset)
        assert split.source == "TRANSACTION"
        assert split.transaction == transaction

    def test_import_source(self, user, asset):
        """Test imported split history."""
        split = SplitHistory.objects.create(
            asset=asset,
            date=date(2023, 6, 15),
            split_from=1,
            split_to=2,
            source="IMPORT",
            comment="Imported from external data source",
        )
        assert split.source == "IMPORT"
        assert split.transaction is None
