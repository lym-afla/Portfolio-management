"""
Tests for Bond ACI (Accrued Interest) calculation and capital distribution.

Tests cover:
1. BondMetadata.get_current_aci() - calculating current accrued interest
2. Assets.get_capital_distribution() - excluding negative ACI (paid when buying)
3. fetch_and_cache_bond_coupon_schedule() - T-Bank API integration
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from common.models import FX, Assets, BondCouponSchedule, BondMetadata, Transactions
from constants import (
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_COUPON,
    TRANSACTION_TYPE_SELL,
)
from core.tinkoff_utils import fetch_and_cache_bond_coupon_schedule

User = get_user_model()


class BondACICalculationTests(TestCase):
    """Test BondMetadata.get_current_aci() method"""

    def setUp(self):
        """Set up test bond with metadata and coupon schedule"""
        self.user = User.objects.create_user(username="testuser", email="test@test.com")

        # Create FX rates (RUBUSD = 1/75 = 0.0133, 1/80 = 0.0125)
        FX.objects.create(date=date(2024, 1, 1), RUBUSD=Decimal("0.0133"))
        FX.objects.create(date=date(2024, 6, 1), RUBUSD=Decimal("0.0125"))

        # Create a bond
        self.bond = Assets.objects.create(
            name="Test Bond",
            ISIN="RU000TEST001",
            type="Bond",
            currency="RUB",
            exposure="Fixed Income",
            tbank_instrument_uid="test-uid-123",
        )
        self.bond.investors.add(self.user)

        # Create bond metadata
        self.bond_meta = BondMetadata.objects.create(
            asset=self.bond,
            initial_notional=Decimal("1000"),
            nominal_currency="RUB",
            coupon_rate=Decimal("8.5"),  # 8.5% per annum
            coupon_frequency=4,  # Quarterly
            issue_date=date(2023, 1, 15),
            maturity_date=date(2026, 1, 15),
            bond_type="FIXED",
        )

        # Create coupon schedule (quarterly coupons)
        # Q1 2024: Jan 15 - Apr 15 (payment Apr 15)
        BondCouponSchedule.objects.create(
            asset=self.bond,
            coupon_number=5,
            coupon_start_date=date(2024, 1, 15),
            coupon_end_date=date(2024, 4, 15),
            payment_date=date(2024, 4, 15),
            coupon_amount=Decimal("21.25"),  # 1000 * 8.5% / 4
            coupon_type="FIXED",
        )

        # Q2 2024: Apr 15 - Jul 15 (payment Jul 15)
        BondCouponSchedule.objects.create(
            asset=self.bond,
            coupon_number=6,
            coupon_start_date=date(2024, 4, 15),
            coupon_end_date=date(2024, 7, 15),
            payment_date=date(2024, 7, 15),
            coupon_amount=Decimal("21.25"),
            coupon_type="FIXED",
        )

    def test_aci_calculation_mid_period(self):
        """Test ACI calculation in the middle of a coupon period"""
        # Calculate ACI as of March 1, 2024 (45 days into Q1)
        # Q1 period: Jan 15 - Apr 15 (91 days)
        test_date = date(2024, 3, 1)

        aci_data = self.bond_meta.get_current_aci(test_date)

        self.assertIsNotNone(aci_data)
        self.assertEqual(aci_data["coupon_start"], date(2024, 1, 15))
        self.assertEqual(aci_data["coupon_end"], date(2024, 4, 15))
        self.assertEqual(aci_data["next_payment"], date(2024, 4, 15))
        self.assertEqual(aci_data["total_days"], 91)
        self.assertEqual(aci_data["aci_days"], 46)  # Jan 15 to Mar 1

        # Expected ACI = 21.25 * (46/91) ≈ 10.74
        expected_aci = Decimal("21.25") * Decimal("46") / Decimal("91")
        self.assertEqual(aci_data["aci_amount"], round(expected_aci, 2))
        self.assertEqual(aci_data["currency"], "RUB")

    def test_aci_at_period_start(self):
        """Test ACI at the start of a coupon period (should be 0)"""
        test_date = date(2024, 4, 15)

        aci_data = self.bond_meta.get_current_aci(test_date)

        self.assertIsNotNone(aci_data)
        # Should be in the new period (Q2)
        self.assertEqual(aci_data["aci_days"], 0)
        self.assertEqual(aci_data["aci_amount"], Decimal("0.00"))

    def test_aci_with_currency_conversion(self):
        """Test ACI calculation with currency conversion"""
        test_date = date(2024, 6, 1)

        # Calculate in USD
        aci_data = self.bond_meta.get_current_aci(test_date, currency="USD")

        self.assertIsNotNone(aci_data)
        self.assertEqual(aci_data["currency"], "USD")

        # ACI should be converted using FX rate (RUBUSD = 0.0125 at 2024-6-1)
        # First calculate RUB ACI, then convert
        days_accrued = (test_date - date(2024, 4, 15)).days
        total_days = (date(2024, 7, 15) - date(2024, 4, 15)).days
        aci_rub = Decimal("21.25") * Decimal(days_accrued) / Decimal(total_days)
        expected_aci_usd = aci_rub * Decimal("0.0125")

        self.assertEqual(aci_data["aci_amount"], round(expected_aci_usd, 2))

    def test_aci_no_schedule(self):
        """Test ACI calculation when no coupon schedule exists"""
        # Create a new bond without schedule
        bond2 = Assets.objects.create(
            name="Bond Without Schedule",
            ISIN="RU000TEST002",
            type="Bond",
            currency="RUB",
            exposure="Fixed Income",
        )
        bond2.investors.add(self.user)

        bond_meta2 = BondMetadata.objects.create(
            asset=bond2,
            initial_notional=Decimal("1000"),
            coupon_rate=Decimal("10.0"),
            coupon_frequency=2,
        )

        aci_data = bond_meta2.get_current_aci(date(2024, 6, 1))
        self.assertIsNone(aci_data)

    def test_aci_after_maturity(self):
        """Test that ACI is None after bond maturity"""
        # Test date after maturity
        test_date = date(2026, 2, 1)

        aci_data = self.bond_meta.get_current_aci(test_date)
        self.assertIsNone(aci_data)


class CapitalDistributionTests(TestCase):
    """Test Assets.get_capital_distribution() with ACI handling"""

    def setUp(self):
        """Set up test data with bond transactions including ACI"""
        self.user = User.objects.create_user(username="testuser", email="test@test.com")

        # Create FX rates
        FX.objects.create(date=date(2024, 1, 1), RUBUSD=Decimal("0.0133"))

        # Create a bond
        self.bond = Assets.objects.create(
            name="Test Bond",
            ISIN="RU000TEST001",
            type="Bond",
            currency="RUB",
            exposure="Fixed Income",
        )
        self.bond.investors.add(self.user)

        # Create bond metadata
        BondMetadata.objects.create(
            asset=self.bond,
            initial_notional=Decimal("1000"),
            nominal_currency="RUB",
            coupon_rate=Decimal("10.0"),
            coupon_frequency=4,
        )

        # Create an account
        from common.models import Accounts, Brokers

        broker = Brokers.objects.create(name="Test Broker", investor=self.user)
        self.account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
            investor=self.user,
            currency="RUB",
        )

    def test_capital_distribution_excludes_negative_aci(self):
        """Test that negative ACI (paid when buying) is excluded from capital distribution"""
        # Buy bond with negative ACI (paid to seller)
        Transactions.objects.create(
            security=self.bond,
            date=date(2024, 2, 15),
            investor=self.user,
            account=self.account,
            type=TRANSACTION_TYPE_BUY,
            quantity=10,
            price=Decimal("98.5"),  # Bought at 98.5% of par
            currency="RUB",
            aci=Decimal("-50.00"),  # Paid ACI to seller (negative)
        )

        # Sell bond with positive ACI (received from buyer)
        Transactions.objects.create(
            security=self.bond,
            date=date(2024, 5, 20),
            investor=self.user,
            account=self.account,
            type=TRANSACTION_TYPE_SELL,
            quantity=-5,
            price=Decimal("102.0"),  # Sold at 102% of par
            currency="RUB",
            aci=Decimal("30.00"),  # Received ACI from buyer (positive)
        )

        # Received coupon payment
        Transactions.objects.create(
            security=self.bond,
            date=date(2024, 4, 15),
            investor=self.user,
            account=self.account,
            type=TRANSACTION_TYPE_COUPON,
            cash_flow=Decimal("250.00"),  # 10 bonds * 25 RUB coupon
            currency="RUB",
        )

        # Calculate capital distribution
        capital_dist = self.bond.get_capital_distribution(
            date=date(2024, 6, 1),
            investor=self.user,
        )

        # Should include:
        # - Coupon: 250.00
        # - Positive ACI (from sell): 30.00
        # Should NOT include:
        # - Negative ACI (from buy): -50.00

        expected = Decimal("250.00") + Decimal("30.00")
        self.assertEqual(capital_dist, expected)

    def test_capital_distribution_with_currency_conversion(self):
        """Test capital distribution calculation with currency conversion"""
        # Create a coupon transaction
        Transactions.objects.create(
            security=self.bond,
            date=date(2024, 3, 15),
            investor=self.user,
            account=self.account,
            type=TRANSACTION_TYPE_COUPON,
            cash_flow=Decimal("250.00"),
            currency="RUB",
        )

        # Sell with positive ACI
        Transactions.objects.create(
            security=self.bond,
            date=date(2024, 5, 20),
            investor=self.user,
            account=self.account,
            type=TRANSACTION_TYPE_SELL,
            quantity=-5,
            price=Decimal("101.0"),
            currency="RUB",
            aci=Decimal("45.00"),
        )

        # Calculate in USD
        capital_dist_usd = self.bond.get_capital_distribution(
            date=date(2024, 6, 1),
            investor=self.user,
            currency="USD",
        )

        # Total RUB: 250 + 45 = 295
        # Convert to USD at rate RUBUSD = 0.0133
        expected_usd = (Decimal("250.00") + Decimal("45.00")) * Decimal("0.0133")
        self.assertEqual(capital_dist_usd, round(expected_usd, 2))


class CouponScheduleFetchTests(TestCase):
    """Test fetch_and_cache_bond_coupon_schedule() function"""

    def setUp(self):
        """Set up test bond and user"""
        self.user = User.objects.create_user(username="testuser", email="test@test.com")

        self.bond = Assets.objects.create(
            name="Test Bond",
            ISIN="RU000A106YJ4",
            type="Bond",
            currency="RUB",
            exposure="Fixed Income",
            tbank_instrument_uid="test-uid-123",
        )
        self.bond.investors.add(self.user)

        BondMetadata.objects.create(
            asset=self.bond,
            initial_notional=Decimal("1000"),
            nominal_currency="RUB",
            issue_date=date(2023, 1, 1),
            maturity_date=date(2026, 1, 1),
            coupon_frequency=4,
        )

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_fetch_coupon_schedule_success(self):
        """Test successful fetching and caching of coupon schedule"""
        from channels.db import database_sync_to_async

        # Mock T-Bank API response
        mock_coupon = Mock()
        mock_coupon.coupon_number = 1
        mock_coupon.coupon_start_date = datetime(2024, 1, 1)
        mock_coupon.coupon_end_date = datetime(2024, 4, 1)
        mock_coupon.coupon_date = datetime(2024, 4, 1)
        mock_coupon.pay_one_bond = Mock(units=21, nano=250000000)
        mock_coupon.coupon_type = "FIXED"

        mock_response = Mock()
        mock_response.events = [mock_coupon]

        with patch(
            "core.tinkoff_utils.get_user_token", new_callable=AsyncMock
        ) as mock_get_token:
            mock_get_token.return_value = "test-token"

            with patch("core.tinkoff_utils.Client") as mock_client:
                mock_client_instance = mock_client.return_value.__enter__.return_value
                mock_client_instance.instruments.get_bond_coupons.return_value = (
                    mock_response
                )

                result = await fetch_and_cache_bond_coupon_schedule(
                    self.bond, self.user
                )

                self.assertTrue(result)

                # Check that coupon schedule was cached using database_sync_to_async
                cached_coupons_count = await database_sync_to_async(
                    lambda: BondCouponSchedule.objects.filter(asset=self.bond).count()
                )()
                self.assertEqual(cached_coupons_count, 1)

                coupon = await database_sync_to_async(
                    lambda: BondCouponSchedule.objects.filter(asset=self.bond).first()
                )()
                self.assertEqual(coupon.coupon_number, 1)
                self.assertEqual(coupon.coupon_start_date, date(2024, 1, 1))
                self.assertEqual(coupon.coupon_amount, Decimal("21.25"))

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_fetch_schedule_uses_cache(self):
        """Test that recent schedule is not re-fetched"""
        from channels.db import database_sync_to_async

        # Create a recent coupon schedule using database_sync_to_async
        await database_sync_to_async(BondCouponSchedule.objects.create)(
            asset=self.bond,
            coupon_number=1,
            coupon_start_date=date(2024, 1, 1),
            coupon_end_date=date(2024, 4, 1),
            payment_date=date(2024, 4, 1),
            coupon_amount=Decimal("25.00"),
        )

        with patch(
            "core.tinkoff_utils.get_user_token", new_callable=AsyncMock
        ) as mock_get_token:
            # Should not call API if schedule is recent
            result = await fetch_and_cache_bond_coupon_schedule(self.bond, self.user)

            self.assertTrue(result)
            mock_get_token.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_fetch_schedule_force_refresh(self):
        """Test force refresh deletes old schedule and fetches new"""
        from channels.db import database_sync_to_async

        # Create old schedule using database_sync_to_async
        await database_sync_to_async(BondCouponSchedule.objects.create)(
            asset=self.bond,
            coupon_number=1,
            coupon_start_date=date(2024, 1, 1),
            coupon_end_date=date(2024, 4, 1),
            payment_date=date(2024, 4, 1),
            coupon_amount=Decimal("25.00"),
        )

        # Mock new data
        mock_coupon = Mock()
        mock_coupon.coupon_number = 2
        mock_coupon.coupon_start_date = datetime(2024, 4, 1)
        mock_coupon.coupon_end_date = datetime(2024, 7, 1)
        mock_coupon.coupon_date = datetime(2024, 7, 1)
        mock_coupon.pay_one_bond = Mock(units=21, nano=250000000)
        mock_coupon.coupon_type = "FIXED"

        mock_response = Mock()
        mock_response.events = [mock_coupon]

        with patch(
            "core.tinkoff_utils.get_user_token", new_callable=AsyncMock
        ) as mock_get_token:
            mock_get_token.return_value = "test-token"

            with patch("core.tinkoff_utils.Client") as mock_client:
                mock_client_instance = mock_client.return_value.__enter__.return_value
                mock_client_instance.instruments.get_bond_coupons.return_value = (
                    mock_response
                )

                result = await fetch_and_cache_bond_coupon_schedule(
                    self.bond, self.user, force_refresh=True
                )

                self.assertTrue(result)

                # Old schedule should be deleted
                old_coupon = await database_sync_to_async(
                    lambda: BondCouponSchedule.objects.filter(
                        asset=self.bond, coupon_number=1
                    ).first()
                )()
                self.assertIsNone(old_coupon)

                # New schedule should be created
                new_coupon = await database_sync_to_async(
                    lambda: BondCouponSchedule.objects.filter(
                        asset=self.bond, coupon_number=2
                    ).first()
                )()
                self.assertIsNotNone(new_coupon)
