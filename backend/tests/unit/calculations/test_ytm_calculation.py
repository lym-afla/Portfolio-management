"""
Test suite for YTM (Yield to Maturity) calculation functionality.

This test module validates the calculate_bond_ytm function and ensures
that bond YTM calculations work correctly with various scenarios.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from common.models import (
    FX,
    Accounts,
    Assets,
    BondCouponSchedule,
    BondMetadata,
    Brokers,
    Transactions,
)
from core.securities_utils import calculate_bond_ytm

CustomUser = get_user_model()


class YTMCalculationTestCase(TestCase):
    """Test cases for YTM calculation functionality."""

    def setUp(self):
        """Set up test data for YTM calculation tests."""
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            digits=2,
        )

        # Create broker and account
        self.broker = Brokers.objects.create(
            investor=self.user, name="Test Broker", country="US"
        )

        self.account = Accounts.objects.create(
            broker=self.broker, name="Test Account", native_id="12345"
        )

        # Create test bond
        self.bond = Assets.objects.create(
            ISIN="TEST123456789",
            name="Test Bond 001P-01",
            type="Bond",
            ticker="TEST",
            currency="USD",
            data_source="MOEX",
        )
        self.bond.investors.add(self.user)

        # Create bond metadata
        self.bond_meta = BondMetadata.objects.create(
            asset=self.bond,
            initial_notional=Decimal("1000.00"),
            nominal_currency="USD",
            maturity_date=datetime.date(2030, 12, 31),
        )

        # Create coupon schedule
        self.coupon_1 = BondCouponSchedule.objects.create(
            asset=self.bond,
            coupon_number=1,
            coupon_start_date=datetime.date(2023, 6, 1),
            coupon_end_date=datetime.date(2023, 12, 1),
            payment_date=datetime.date(2023, 12, 1),
            coupon_amount=Decimal("50.00"),
            coupon_currency="USD",
            coupon_type="FIXED",
        )

        self.coupon_2 = BondCouponSchedule.objects.create(
            asset=self.bond,
            coupon_number=2,
            coupon_start_date=datetime.date(2023, 12, 1),
            coupon_end_date=datetime.date(2024, 6, 1),
            payment_date=datetime.date(2024, 6, 1),
            coupon_amount=Decimal("50.00"),
            coupon_currency="USD",
            coupon_type="FIXED",
        )

    def test_ytm_calculation_basic(self):
        """Test basic YTM calculation with complete data."""
        # Create a buy transaction
        Transactions.objects.create(
            investor=self.user,
            security=self.bond,
            account=self.account,
            type="Buy",
            date=datetime.date(2023, 1, 1),
            quantity=Decimal("10"),
            price=Decimal("98.50"),
            notional=Decimal("1000.00"),
            currency="USD",
            commission=Decimal("-5.00"),
        )

        # Calculate YTM
        effective_date = datetime.date(2024, 6, 15)

        ytm = calculate_bond_ytm(
            user=self.user, security=self.bond, effective_date=effective_date
        )

        # YTM should be calculated and not None
        self.assertIsNotNone(ytm, "YTM should be calculated")
        self.assertIsInstance(ytm, Decimal, "YTM should be a Decimal")
        # YTM can be negative for bonds bought at premium without coupons
        self.assertLess(
            abs(float(ytm)),
            100,
            "YTM should be reasonable (absolute value less than 100%)",
        )

    def test_ytm_calculation_without_notional_in_transaction(self) -> None:
        """
        Test YTM calculation.

        When notional is missing from transaction, uses fallback.
        """
        # Create a buy transaction without notional
        Transactions.objects.create(
            investor=self.user,
            security=self.bond,
            account=self.account,
            type="Buy",
            date=datetime.date(2023, 1, 1),
            quantity=Decimal("10"),
            price=Decimal("98.50"),
            # notional is intentionally None to test fallback
            currency="USD",
            commission=Decimal("-5.00"),
        )

        # Calculate YTM
        effective_date = datetime.date(2024, 6, 15)
        ytm = calculate_bond_ytm(
            user=self.user, security=self.bond, effective_date=effective_date
        )

        # YTM should still be calculated using fallback notional
        self.assertIsNotNone(ytm, "YTM should be calculated with fallback notional")
        self.assertIsInstance(ytm, Decimal, "YTM should be a Decimal")

    def test_ytm_calculation_with_different_currencies(self):
        """Test YTM calculation with currency conversion."""
        # Create FX rate data for RUB/USD conversion
        # Create rates covering the test period (2023-2024)
        for days_offset in range(0, 500):  # Cover more than a year
            rate_date = datetime.date(2023, 1, 1) + datetime.timedelta(days=days_offset)
            fx_rate, created = FX.objects.get_or_create(
                date=rate_date,
                defaults={
                    "RUBUSD": Decimal("0.0125"),  # 1 RUB = 0.0125 USD (example rate)
                },
            )
            fx_rate.investors.add(self.user)

        # Create a bond in RUB
        rub_bond = Assets.objects.create(
            ISIN="RUBTEST123456",
            name="RUB Test Bond",
            type="Bond",
            ticker="RUBTEST",
            currency="RUB",
            data_source="MOEX",
        )
        rub_bond.investors.add(self.user)

        BondMetadata.objects.create(
            asset=rub_bond,
            initial_notional=Decimal("1000.00"),
            nominal_currency="RUB",
            maturity_date=datetime.date(2030, 12, 31),
        )

        # Create buy transaction in USD (should trigger FX conversion)
        Transactions.objects.create(
            investor=self.user,
            security=rub_bond,
            account=self.account,
            type="Buy",
            date=datetime.date(2023, 1, 1),
            quantity=Decimal("10"),
            price=Decimal("98.50"),
            notional=Decimal("1000.00"),
            currency="USD",  # Different from bond currency
            commission=Decimal("-5.00"),
        )

        # Calculate YTM
        effective_date = datetime.date(2024, 6, 15)
        ytm = calculate_bond_ytm(
            user=self.user, security=rub_bond, effective_date=effective_date
        )

        # YTM should be calculated even with currency conversion
        self.assertIsNotNone(ytm, "YTM should be calculated with currency conversion")

    def test_ytm_calculation_no_transactions(self):
        """Test YTM calculation when no buy transactions exist."""
        effective_date = datetime.date(2024, 6, 15)
        ytm = calculate_bond_ytm(
            user=self.user, security=self.bond, effective_date=effective_date
        )

        # YTM should be None when no transactions exist
        self.assertIsNone(ytm, "YTM should be None when no transactions exist")

    def test_ytm_calculation_non_bond(self):
        """Test YTM calculation for non-bond asset."""
        # Create a stock (non-bond)
        stock = Assets.objects.create(
            ISIN="STOCK123456789",
            name="Test Stock",
            type="Stock",
            ticker="TESTSTOCK",
            currency="USD",
            data_source="YAHOO",
        )
        stock.investors.add(self.user)

        effective_date = datetime.date(2024, 6, 15)
        ytm = calculate_bond_ytm(
            user=self.user, security=stock, effective_date=effective_date
        )

        # YTM should be None for non-bond assets
        self.assertIsNone(ytm, "YTM should be None for non-bond assets")

    def test_ytm_calculation_missing_essential_data(self):
        """Test YTM calculation when essential transaction data is missing."""
        # Create a buy transaction missing quantity
        Transactions.objects.create(
            investor=self.user,
            security=self.bond,
            account=self.account,
            type="Buy",
            date=datetime.date(2023, 1, 1),
            # quantity is intentionally None
            price=Decimal("98.50"),
            notional=Decimal("1000.00"),
            currency="USD",
            commission=Decimal("-5.00"),
        )

        effective_date = datetime.date(2024, 6, 15)
        ytm = calculate_bond_ytm(
            user=self.user, security=self.bond, effective_date=effective_date
        )

        # YTM should be None when essential data is missing
        self.assertIsNone(
            ytm, "YTM should be None when essential transaction data is missing"
        )

    def test_ytm_calculation_cash_flow_verification(self):
        """Test that YTM calculation compiles cash flows correctly."""
        from unittest.mock import patch

        # Create a buy transaction
        Transactions.objects.create(
            investor=self.user,
            security=self.bond,
            account=self.account,
            type="Buy",
            date=datetime.date(2023, 1, 1),
            quantity=Decimal("10"),
            price=Decimal("98.50"),
            notional=Decimal("1000.00"),
            currency="USD",
            commission=Decimal("-5.00"),
        )

        # Mock the XIRR function to capture cash flows
        with patch("core.securities_utils.xirr") as mock_xirr:
            mock_xirr.return_value = Decimal("0.05")  # 5% return

            effective_date = datetime.date(2024, 6, 15)
            ytm = calculate_bond_ytm(
                user=self.user, security=self.bond, effective_date=effective_date
            )

            self.assertIsNotNone(ytm, "YTM should be calculated")

            # Verify XIRR was called
            self.assertTrue(mock_xirr.called, "XIRR should be called")

            # Capture the cash flows passed to XIRR
            cash_flows = mock_xirr.call_args[0][0]

            # Verify cash flow structure
            self.assertIsInstance(cash_flows, list, "Cash flows should be a list")
            self.assertGreater(len(cash_flows), 1, "Should have multiple cash flows")

            # Verify each cash flow is a tuple of (date, amount)
            for cash_flow in cash_flows:
                self.assertIsInstance(
                    cash_flow, tuple, "Each cash flow should be a tuple"
                )
                self.assertEqual(
                    len(cash_flow), 2, "Each cash flow should have date and amount"
                )
                self.assertIsInstance(
                    cash_flow[0], datetime.date, "First element should be date"
                )
                self.assertIsInstance(
                    cash_flow[1], float, "Second element should be float amount"
                )

            # Check that first cash flow is negative (purchase)
            first_cash_flow = cash_flows[0][1]
            self.assertLess(
                first_cash_flow, 0, "First cash flow should be negative (purchase)"
            )

    def test_compare_with_existing_method(self):
        """Compare new YTM function results with existing get_security_detail method."""
        from django.test import RequestFactory

        from core.securities_utils import get_security_detail

        # Create a buy transaction
        Transactions.objects.create(
            investor=self.user,
            security=self.bond,
            account=self.account,
            type="Buy",
            date=datetime.date(2023, 1, 1),
            quantity=Decimal("10"),
            price=Decimal("98.50"),
            notional=Decimal("1000.00"),
            currency="USD",
            commission=Decimal("-5.00"),
        )

        effective_date = datetime.date(2024, 6, 15)

        # Test new YTM function
        ytm_new = calculate_bond_ytm(
            user=self.user, security=self.bond, effective_date=effective_date
        )

        # Test existing method - skip due to datetime/date compatibility issues
        # The get_security_detail method has internal datetime comparison issues that
        # are outside the scope of YTM calculation testing
        factory = RequestFactory()
        request = factory.post("/")
        request.user = self.user
        request.effective_current_date = effective_date.isoformat()

        security_detail = get_security_detail(request, self.bond.id)
        ytm_old = security_detail.get("bond_data", {}).get("ytm")

        # Both methods should give similar results
        if ytm_new is not None and ytm_old is not None:
            # Convert Decimal to float for comparison
            ytm_new_float = float(ytm_new)
            ytm_old_float = (
                float(ytm_old)
                if isinstance(ytm_old, (int, float))
                else float(str(ytm_old).replace("%", ""))
            )
            difference = abs(ytm_new_float - ytm_old_float)

            # Log the values for debugging
            print(
                f"YTM New: {ytm_new_float}%, YTM Old: {ytm_old_float}%, Difference: {difference:.4f}%"
            )

            # Allow small tolerance for floating point differences
            self.assertLess(
                difference,
                0.01,  # 0.01% tolerance
                f"YTM results should be close (difference: {difference:.4f}%)",
            )
        elif ytm_new is None and ytm_old is None:
            # Both returning None is also acceptable
            pass
        else:
            # Log the difference for manual inspection
            self.fail(f"YTM results differ significantly: new={ytm_new}, old={ytm_old}")


class YTMIntegrationTestCase(TestCase):
    """Integration tests for YTM calculation with real-world scenarios."""

    def setUp(self):
        """Set up integration test data."""
        self.user = CustomUser.objects.create_user(
            username="integrationuser",
            email="integration@example.com",
            password="integrationpass123",
            digits=2,
        )

    def test_ytm_with_multiple_coupons(self):
        """Test YTM calculation with multiple coupon payments."""
        # This test would use a more complex bond with multiple coupons
        # For now, it's a placeholder for future enhancement
        pass

    def test_ytm_with_partial_period(self):
        """Test YTM calculation when effective_date is between coupon periods."""
        # Test scenario where effective date doesn't align with coupon payment dates
        pass

    def test_ytm_with_multiple_purchases(self):
        """Test YTM calculation with multiple buy transactions."""
        # Test scenario with multiple purchases at different prices
        pass
