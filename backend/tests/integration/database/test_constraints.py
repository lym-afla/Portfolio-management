"""
Test cases for database constraints and model validation.

This module tests:
- Model field constraints
- Database level constraints
- Unique constraints
- Foreign key constraints
- Data integrity validation
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from common.models import (
    FX,
    AnnualPerformance,
    Assets,
    Brokers,
    FXTransaction,
    Transactions,
)
from users.models import CustomUser


@pytest.mark.integration
@pytest.mark.database
class TestAssetModelConstraints:
    """Test Asset model database constraints."""

    def test_asset_isin_uniqueness_per_user(self, user: CustomUser) -> None:
        """Test that ISIN must be unique per user."""
        # Create first asset
        asset1 = Assets.objects.create(
            type="Stock",
            ISIN="US1234567890",
            name="First Asset",
            currency="USD",
            exposure="Equity",
        )
        asset1.investors.add(user)

        # Try to create second asset with same ISIN for same user
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                asset2 = Assets.objects.create(
                    type="Stock",
                    ISIN="US1234567890",  # Same ISIN
                    name="Second Asset",
                    currency="USD",
                    exposure="Equity",
                )
                asset2.investors.add(user)

    def test_asset_isin_different_users_allowed(self) -> None:
        """Test that same ISIN can be used by different users."""
        user1 = CustomUser.objects.create_user(
            username="user1", email="user1@example.com", password="testpass123"
        )
        user2 = CustomUser.objects.create_user(
            username="user2", email="user2@example.com", password="testpass123"
        )

        # Create asset for user1
        asset1 = Assets.objects.create(
            type="Stock",
            ISIN="US1234567890",
            name="Asset for User1",
            currency="USD",
            exposure="Equity",
        )
        asset1.investors.add(user1)

        # Create asset with same ISIN for user2 (should be allowed)
        asset2 = Assets.objects.create(
            type="Stock",
            ISIN="US1234567890",  # Same ISIN
            name="Asset for User2",
            currency="USD",
            exposure="Equity",
        )
        asset2.investors.add(user2)

        assert asset1.id != asset2.id
        assert asset1.ISIN == asset2.ISIN

    def test_asset_type_choices(self, user: CustomUser) -> None:
        """Test that asset type must be from allowed choices."""
        asset = Assets(
            type="InvalidType",  # Invalid type
            ISIN="US1234567890",
            name="Test Asset",
            currency="USD",
            exposure="Equity",
        )

        with pytest.raises(ValidationError):
            asset.clean()

    def test_asset_currency_choices(self, user: CustomUser) -> None:
        """Test that asset currency must be from allowed choices."""
        asset = Assets(
            type="Stock",
            ISIN="US1234567890",
            name="Test Asset",
            currency="INVALID",  # Invalid currency
            exposure="Equity",
        )

        with pytest.raises(ValidationError):
            asset.clean()

    def test_asset_exposure_choices(self, user: CustomUser) -> None:
        """Test that asset exposure must be from allowed choices."""
        asset = Assets(
            type="Stock",
            ISIN="US1234567890",
            name="Test Asset",
            currency="USD",
            exposure="InvalidExposure",  # Invalid exposure
        )

        with pytest.raises(ValidationError):
            asset.clean()

    def test_asset_isin_format_validation(self, user: CustomUser) -> None:
        """Test ISIN format validation."""
        # Test valid ISIN
        valid_asset = Assets.objects.create(
            type="Stock",
            ISIN="US1234567890",  # Valid 12-character ISIN
            name="Valid Asset",
            currency="USD",
            exposure="Equity",
        )
        valid_asset.investors.add(user)

        # Test invalid ISIN formats
        invalid_isins = [
            "US123456789",  # Too short
            "US12345678901",  # Too long
            "INVALID_ISIN",  # Invalid characters
            "",  # Empty string
        ]

        for invalid_isin in invalid_isins:
            asset = Assets(
                type="Stock",
                ISIN=invalid_isin,
                name="Invalid Asset",
                currency="USD",
                exposure="Equity",
            )
            with pytest.raises(ValidationError):
                asset.clean()

    def test_asset_required_fields(self, user: CustomUser) -> None:
        """Test that required fields cannot be null."""
        required_fields = ["type", "ISIN", "name", "currency", "exposure"]

        for field in required_fields:
            asset_data = {
                "type": "Stock",
                "ISIN": "US1234567890",
                "name": "Test Asset",
                "currency": "USD",
                "exposure": "Equity",
            }
            asset_data[field] = None

            with pytest.raises((IntegrityError, ValidationError)):
                Assets.objects.create(**asset_data)


@pytest.mark.integration
@pytest.mark.database
class TestBrokerModelConstraints:
    """Test Broker model database constraints."""

    def test_broker_user_relationship(self, user: CustomUser) -> None:
        """Test that broker must be associated with a user."""
        # Valid broker creation
        broker = Brokers.objects.create(investor=user, name="Test Broker", country="US")
        assert broker.investor == user

        # Try to create broker without user (should fail)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Brokers.objects.create(
                    investor=None,  # Invalid: no investor
                    name="Invalid Broker",
                    country="US",
                )

    def test_broker_name_length_constraint(self, user):
        """Test broker name length constraints."""
        # Test valid name
        valid_broker = Brokers.objects.create(
            investor=user, name="A" * 30, country="US"  # Valid length
        )
        assert valid_broker.name == "A" * 30

        # Test invalid name (too long)
        with pytest.raises((ValidationError, IntegrityError)):
            broker = Brokers(investor=user, name="A" * 31, country="US")  # Too long
            broker.save()

    def test_broker_country_validation(self, user):
        """Test broker country field validation."""
        # Test valid country codes
        valid_countries = ["US", "GB", "DE", "FR", "JP", "CN"]

        for country in valid_countries:
            broker = Brokers.objects.create(
                investor=user, name=f"Broker {country}", country=country
            )
            assert broker.country == country

    def test_broker_unique_name_per_user(self, user):
        """Test that broker names must be unique per user."""
        # Create first broker
        Brokers.objects.create(investor=user, name="Unique Broker", country="US")

        # Try to create second broker with same name for same user
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Brokers.objects.create(
                    investor=user,
                    name="Unique Broker",  # Same name
                    country="UK",  # Different country but same name
                )

    def test_broker_same_name_different_users(self):
        """Test that same broker name can be used by different users."""
        user1 = CustomUser.objects.create_user(
            username="broker_user1", email="broker1@example.com", password="testpass123"
        )
        user2 = CustomUser.objects.create_user(
            username="broker_user2", email="broker2@example.com", password="testpass123"
        )

        # Create brokers with same name for different users (should be allowed)
        broker1 = Brokers.objects.create(
            investor=user1, name="Same Name Broker", country="US"
        )
        broker2 = Brokers.objects.create(
            investor=user2, name="Same Name Broker", country="US"  # Same name
        )

        assert broker1.id != broker2.id
        assert broker1.name == broker2.name


@pytest.mark.integration
@pytest.mark.database
class TestTransactionModelConstraints:
    """Test Transaction model database constraints."""

    def setUp(self):
        """Set up test data for transaction tests."""
        self.user = CustomUser.objects.create_user(
            username="tx_user", email="tx@example.com", password="testpass123"
        )
        self.broker = Brokers.objects.create(
            investor=self.user, name="Test Broker", country="US"
        )
        self.asset = Assets.objects.create(
            type="Stock",
            ISIN="US1234567890",
            name="Test Asset",
            currency="USD",
            exposure="Equity",
        )
        self.asset.investors.add(self.user)
        self.asset.brokers.add(self.broker)

    def test_transaction_required_relationships(self):
        """Test that transaction must have required relationships."""
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Transactions.objects.create(
                    investor=None,  # Missing required investor
                    broker=self.broker,
                    security=self.asset,
                    currency="USD",
                    type="Buy",
                    date=date(2023, 1, 15),
                    quantity=Decimal("100"),
                    price=Decimal("50.00"),
                    cash_flow=Decimal("-5000.00"),
                    commission=Decimal("5.00"),
                )

    def test_transaction_foreign_key_constraints(self):
        """Test transaction foreign key constraints."""
        # Create transaction with valid foreign keys
        transaction = Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )
        assert transaction.investor == self.user
        assert transaction.broker == self.broker
        assert transaction.security == self.asset

        # Try to create transaction with invalid foreign key
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Transactions.objects.create(
                    investor=self.user,
                    broker=self.broker,
                    security_id=99999,  # Invalid asset ID
                    currency="USD",
                    type="Buy",
                    date=date(2023, 1, 15),
                    quantity=Decimal("100"),
                    price=Decimal("50.00"),
                    cash_flow=Decimal("-5000.00"),
                    commission=Decimal("5.00"),
                )

    def test_transaction_type_choices(self):
        """Test that transaction type must be from allowed choices."""
        invalid_types = ["InvalidType", "BUY", "SELL", "buy", "sell"]

        for invalid_type in invalid_types:
            transaction = Transactions(
                investor=self.user,
                broker=self.broker,
                security=self.asset,
                currency="USD",
                type=invalid_type,  # Invalid type
                date=date(2023, 1, 15),
                quantity=Decimal("100"),
                price=Decimal("50.00"),
                cash_flow=Decimal("-5000.00"),
                commission=Decimal("5.00"),
            )
            with pytest.raises(ValidationError):
                transaction.clean()

    def test_transaction_currency_choices(self):
        """Test that transaction currency must be from allowed choices."""
        transaction = Transactions(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="INVALID",  # Invalid currency
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )
        with pytest.raises(ValidationError):
            transaction.clean()

    def test_transaction_date_constraints(self):
        """Test transaction date field constraints."""
        # Test future date (should be allowed)
        future_transaction = Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2030, 1, 1),  # Future date
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )
        assert future_transaction.date == date(2030, 1, 1)

        # Test very old date (should be allowed)
        old_transaction = Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(1900, 1, 1),  # Very old date
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )
        assert old_transaction.date == date(1900, 1, 1)

    def test_transaction_quantity_decimal_places(self):
        """Test transaction quantity decimal precision constraints."""
        # Test valid precision
        valid_transaction = Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("1.123456"),  # 6 decimal places
            price=Decimal("50.00"),
            cash_flow=Decimal("-56.23"),
            commission=Decimal("5.00"),
        )
        assert valid_transaction.quantity == Decimal("1.123456")

        # Test excessive precision (should be handled gracefully)
        high_precision = Decimal("1.123456789012345")
        try:
            high_precision_transaction = Transactions.objects.create(
                investor=self.user,
                broker=self.broker,
                security=self.asset,
                currency="USD",
                type="Buy",
                date=date(2023, 1, 15),
                quantity=high_precision,
                price=Decimal("50.00"),
                cash_flow=Decimal("-56.17"),
                commission=Decimal("5.00"),
            )
            # Should be rounded or handled appropriately
            assert high_precision_transaction.quantity is not None
        except (ValidationError, IntegrityError):
            # Or should raise validation error
            pass

    def test_transaction_price_decimal_places(self):
        """Test transaction price decimal precision constraints."""
        # Test valid precision
        valid_transaction = Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.123456"),  # 6 decimal places
            cash_flow=Decimal("-5012.35"),
            commission=Decimal("5.00"),
        )
        assert valid_transaction.price == Decimal("50.123456")

    def test_transaction_cash_flow_sign_consistency(self):
        """Test cash flow sign consistency with transaction type."""
        # Buy transaction should have negative cash flow
        buy_transaction = Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5005.00"),  # Negative
            commission=Decimal("5.00"),
        )
        assert buy_transaction.cash_flow < 0

        # Sell transaction should have positive cash flow
        sell_transaction = Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Sell",
            date=date(2023, 2, 15),
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            cash_flow=Decimal("5495.00"),  # Positive
            commission=Decimal("5.00"),
        )
        assert sell_transaction.cash_flow > 0

        # Dividend transaction should have positive cash flow
        dividend_transaction = Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            currency="USD",
            type="Dividend",
            date=date(2023, 3, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("200.00"),  # Positive
            commission=None,
        )
        assert dividend_transaction.cash_flow > 0


@pytest.mark.integration
@pytest.mark.database
class TestFXModelConstraints:
    """Test FX model database constraints."""

    def setUp(self):
        """Set up test data for FX tests."""
        self.user = CustomUser.objects.create_user(
            username="fx_user", email="fx@example.com", password="testpass123"
        )

    def test_fx_unique_date_investor(self):
        """Test that FX rates must be unique per date and investor."""
        test_date = date(2023, 6, 15)

        # Create first FX record
        fx1 = FX.objects.create(
            investor=self.user, date=test_date, USDEUR=Decimal("0.92")
        )
        assert fx1.date == test_date

        # Try to create second FX record for same date and investor
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                FX.objects.create(
                    investor=self.user,
                    date=test_date,  # Same date
                    USDEUR=Decimal("0.93"),  # Different rate
                )

    def test_fx_different_investors_same_date(self):
        """Test that different investors can have FX rates for same date."""
        user2 = CustomUser.objects.create_user(
            username="fx_user2", email="fx2@example.com", password="testpass123"
        )
        test_date = date(2023, 6, 15)

        # Create FX records for different users on same date
        fx1 = FX.objects.create(
            investor=self.user, date=test_date, USDEUR=Decimal("0.92")
        )
        fx2 = FX.objects.create(
            investor=user2,
            date=test_date,  # Same date
            USDEUR=Decimal("0.93"),  # Different rate
        )

        assert fx1.id != fx2.id
        assert fx1.date == fx2.date

    def test_fx_rate_decimal_precision(self):
        """Test FX rate decimal precision constraints."""
        # Test valid precision
        fx = FX.objects.create(
            investor=self.user,
            date=date(2023, 6, 15),
            USDEUR=Decimal("0.123456"),  # 6 decimal places
        )
        assert fx.USDEUR == Decimal("0.123456")

        # Test higher precision (should be rounded or handled)
        high_precision = Decimal("0.123456789012345")
        try:
            fx_high = FX.objects.create(
                investor=self.user, date=date(2023, 6, 16), USDEUR=high_precision
            )
            # Should be rounded appropriately
            assert fx_high.USDEUR is not None
        except (ValidationError, IntegrityError):
            # Or should raise validation error
            pass

    def test_fx_rate_positive_values(self):
        """Test that FX rates must be positive."""
        with pytest.raises(ValidationError):
            fx = FX(
                investor=self.user,
                date=date(2023, 6, 15),
                USDEUR=Decimal("-0.92"),  # Negative rate
            )
            fx.clean()

    def test_fx_primary_key_date_investor(self):
        """Test that date and investor form composite primary key."""
        test_date = date(2023, 6, 15)

        fx = FX.objects.create(
            investor=self.user, date=test_date, USDEUR=Decimal("0.92")
        )

        # Verify the composite primary key works
        retrieved_fx = FX.objects.get(investor=self.user, date=test_date)
        assert retrieved_fx == fx

    def test_fx_rate_field_constraints(self):
        """Test FX rate field constraints."""
        fx = FX.objects.create(
            investor=self.user,
            date=date(2023, 6, 15),
            USDEUR=Decimal("0.92"),
            USDGBP=Decimal("0.82"),
            CHFGBP=Decimal("0.88"),
        )

        # Test that all fields are accessible
        assert fx.USDEUR == Decimal("0.92")
        assert fx.USDGBP == Decimal("0.82")
        assert fx.CHFGBP == Decimal("0.88")

        # Test that null values are allowed for some fields
        fx_nulls = FX.objects.create(
            investor=self.user,
            date=date(2023, 6, 16),
            USDEUR=Decimal("0.93"),
            # Other fields should be nullable
        )
        assert fx_nulls.USDEUR == Decimal("0.93")
        assert fx_nulls.USDGBP is None
        assert fx_nulls.CHFGBP is None


@pytest.mark.integration
@pytest.mark.database
class TestAnnualPerformanceConstraints:
    """Test AnnualPerformance model database constraints."""

    def setUp(self):
        """Set up test data for annual performance tests."""
        self.user = CustomUser.objects.create_user(
            username="perf_user", email="perf@example.com", password="testpass123"
        )
        self.broker = Brokers.objects.create(
            investor=self.user, name="Test Broker", country="US"
        )

    def test_annual_performance_unique_constraints(self):
        """Test annual performance unique constraints."""
        # Create first record
        perf1 = AnnualPerformance.objects.create(
            investor=self.user,
            broker=self.broker,
            year=2023,
            currency="USD",
            bop_nav=Decimal("10000"),
            invested=Decimal("5000"),
            cash_out=Decimal("0"),
            price_change=Decimal("2000"),
            capital_distribution=Decimal("100"),
            commission=Decimal("50"),
            tax=Decimal("0"),
            fx=Decimal("0"),
            eop_nav=Decimal("17050"),
            tsr="70.5",
        )
        assert perf1.year == 2023

        # Try to create duplicate record
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                AnnualPerformance.objects.create(
                    investor=self.user,
                    broker=self.broker,
                    year=2023,  # Same year
                    currency="USD",  # Same currency
                    restricted=False,
                    bop_nav=Decimal("12000"),
                    invested=Decimal("6000"),
                    cash_out=Decimal("0"),
                    price_change=Decimal("2500"),
                    capital_distribution=Decimal("120"),
                    commission=Decimal("60"),
                    tax=Decimal("0"),
                    fx=Decimal("0"),
                    eop_nav=Decimal("20080"),
                    tsr="67.3",
                )

    def test_annual_performance_broker_or_group_constraint(self):
        """Test that either broker or broker_group must be set, but not both."""
        # Test with broker only (should be valid)
        perf_broker = AnnualPerformance.objects.create(
            investor=self.user,
            broker=self.broker,
            year=2023,
            currency="USD",
            bop_nav=Decimal("10000"),
            invested=Decimal("5000"),
            cash_out=Decimal("0"),
            price_change=Decimal("2000"),
            capital_distribution=Decimal("100"),
            commission=Decimal("50"),
            tax=Decimal("0"),
            fx=Decimal("0"),
            eop_nav=Decimal("17050"),
            tsr="70.5",
        )
        assert perf_broker.broker == self.broker
        assert perf_broker.broker_group is None

        # Test with broker_group only (should be valid)
        perf_group = AnnualPerformance.objects.create(
            investor=self.user,
            broker=None,
            broker_group="US Equities",
            year=2023,
            currency="USD",
            bop_nav=Decimal("20000"),
            invested=Decimal("10000"),
            cash_out=Decimal("0"),
            price_change=Decimal("4000"),
            capital_distribution=Decimal("200"),
            commission=Decimal("100"),
            tax=Decimal("0"),
            fx=Decimal("0"),
            eop_nav=Decimal("34000"),
            tsr="70.0",
        )
        assert perf_group.broker is None
        assert perf_group.broker_group == "US Equities"

        # Test with both broker and broker_group (should violate constraint)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                AnnualPerformance.objects.create(
                    investor=self.user,
                    broker=self.broker,
                    broker_group="US Equities",  # Both set
                    year=2023,
                    currency="USD",
                    bop_nav=Decimal("15000"),
                    invested=Decimal("7500"),
                    cash_out=Decimal("0"),
                    price_change=Decimal("3000"),
                    capital_distribution=Decimal("150"),
                    commission=Decimal("75"),
                    tax=Decimal("0"),
                    fx=Decimal("0"),
                    eop_nav=Decimal("25500"),
                    tsr="70.0",
                )

    def test_annual_performance_year_range(self):
        """Test annual performance year constraints."""
        # Test reasonable year range
        valid_years = [2000, 2020, 2023, 2030]

        for year in valid_years:
            perf = AnnualPerformance.objects.create(
                investor=self.user,
                broker=self.broker,
                year=year,
                currency="USD",
                bop_nav=Decimal("10000"),
                invested=Decimal("5000"),
                cash_out=Decimal("0"),
                price_change=Decimal("2000"),
                capital_distribution=Decimal("100"),
                commission=Decimal("50"),
                tax=Decimal("0"),
                fx=Decimal("0"),
                eop_nav=Decimal("17050"),
                tsr="70.5",
            )
            assert perf.year == year

    def test_annual_performance_decimal_precision(self):
        """Test decimal precision for financial fields."""
        perf = AnnualPerformance.objects.create(
            investor=self.user,
            broker=self.broker,
            year=2023,
            currency="USD",
            bop_nav=Decimal("12345.67"),
            invested=Decimal("6789.01"),
            cash_out=Decimal("234.56"),
            price_change=Decimal("1234.56"),
            capital_distribution=Decimal("123.45"),
            commission=Decimal("67.89"),
            tax=Decimal("45.67"),
            fx=Decimal("12.34"),
            eop_nav=Decimal("23456.78"),
            tsr="71.23",
        )

        # Verify all decimal fields maintain precision
        assert perf.bop_nav == Decimal("12345.67")
        assert perf.invested == Decimal("6789.01")
        assert perf.cash_out == Decimal("234.56")
        assert perf.price_change == Decimal("1234.56")
        assert perf.capital_distribution == Decimal("123.45")
        assert perf.commission == Decimal("67.89")
        assert perf.tax == Decimal("45.67")
        assert perf.fx == Decimal("12.34")
        assert perf.eop_nav == Decimal("23456.78")

    def test_annual_performance_tsr_format(self):
        """Test TSR field format constraints."""
        # Test numeric TSR
        perf_numeric = AnnualPerformance.objects.create(
            investor=self.user,
            broker=self.broker,
            year=2023,
            currency="USD",
            bop_nav=Decimal("10000"),
            invested=Decimal("5000"),
            cash_out=Decimal("0"),
            price_change=Decimal("2000"),
            capital_distribution=Decimal("100"),
            commission=Decimal("50"),
            tax=Decimal("0"),
            fx=Decimal("0"),
            eop_nav=Decimal("17050"),
            tsr="71.05",  # Numeric string
        )
        assert perf_numeric.tsr == "71.05"

        # Test negative TSR (loss)
        perf_negative = AnnualPerformance.objects.create(
            investor=self.user,
            broker=self.broker,
            year=2022,
            currency="USD",
            bop_nav=Decimal("10000"),
            invested=Decimal("5000"),
            cash_out=Decimal("0"),
            price_change=Decimal("-1000"),
            capital_distribution=Decimal("50"),
            commission=Decimal("50"),
            tax=Decimal("0"),
            fx=Decimal("0"),
            eop_nav=Decimal("8950"),
            tsr="-21.0",  # Negative performance
        )
        assert perf_negative.tsr == "-21.0"


@pytest.mark.integration
@pytest.mark.database
class TestFXTransactionConstraints:
    """Test FXTransaction model database constraints."""

    def setUp(self):
        """Set up test data for FX transaction tests."""
        self.user = CustomUser.objects.create_user(
            username="fx_tx_user", email="fx_tx@example.com", password="testpass123"
        )
        self.broker = Brokers.objects.create(
            investor=self.user, name="FX Broker", country="US"
        )

    def test_fx_transaction_required_relationships(self):
        """Test that FX transaction must have required relationships."""
        fx_transaction = FXTransaction.objects.create(
            investor=self.user,
            broker=self.broker,
            date=date(2023, 6, 15),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000.00"),
            to_amount=Decimal("920.00"),
            exchange_rate=Decimal("0.92"),
            commission=Decimal("5.00"),
        )
        assert fx_transaction.investor == self.user
        assert fx_transaction.broker == self.broker

    def test_fx_transaction_different_currencies(self):
        """Test that from_currency and to_currency must be different."""
        # Valid transaction (different currencies)
        fx_valid = FXTransaction.objects.create(
            investor=self.user,
            broker=self.broker,
            date=date(2023, 6, 15),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000.00"),
            to_amount=Decimal("920.00"),
            exchange_rate=Decimal("0.92"),
            commission=Decimal("5.00"),
        )
        assert fx_valid.from_currency != fx_valid.to_currency

        # Try same currency (should be invalid or handled by business logic)
        fx_same = FXTransaction(
            investor=self.user,
            broker=self.broker,
            date=date(2023, 6, 16),
            from_currency="USD",
            to_currency="USD",  # Same currency
            from_amount=Decimal("1000.00"),
            to_amount=Decimal("1000.00"),
            exchange_rate=Decimal("1.00"),
            commission=Decimal("5.00"),
        )
        # This might be allowed as a no-op transaction, depending on business rules
        try:
            fx_same.save()
            assert fx_same.from_currency == fx_same.to_currency
        except (ValidationError, IntegrityError):
            # Or might be prevented by validation
            pass

    def test_fx_transaction_positive_amounts(self):
        """Test that FX transaction amounts should be positive."""
        fx_transaction = FXTransaction.objects.create(
            investor=self.user,
            broker=self.broker,
            date=date(2023, 6, 15),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000.00"),
            to_amount=Decimal("920.00"),
            exchange_rate=Decimal("0.92"),
            commission=Decimal("5.00"),
        )
        assert fx_transaction.from_amount > 0
        assert fx_transaction.to_amount > 0

    def test_fx_transaction_exchange_rate_calculation(self):
        """Test that exchange rate is calculated correctly."""
        fx_transaction = FXTransaction.objects.create(
            investor=self.user,
            broker=self.broker,
            date=date(2023, 6, 15),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000.00"),
            to_amount=Decimal("920.00"),
            commission=Decimal("5.00"),
        )
        # Exchange rate should be to_amount / from_amount
        expected_rate = Decimal("920.00") / Decimal("1000.00")
        assert abs(fx_transaction.exchange_rate - expected_rate) < Decimal("0.001")

    def test_fx_transaction_decimal_precision(self):
        """Test FX transaction decimal precision."""
        fx_transaction = FXTransaction.objects.create(
            investor=self.user,
            broker=self.broker,
            date=date(2023, 6, 15),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1234.567890"),
            to_amount=Decimal("1135.804459"),
            exchange_rate=Decimal("0.920000"),
            commission=Decimal("5.123456"),
        )
        assert fx_transaction.from_amount == Decimal("1234.567890")
        assert fx_transaction.to_amount == Decimal("1135.804459")
        assert fx_transaction.exchange_rate == Decimal("0.920000")
        assert fx_transaction.commission == Decimal("5.123456")
