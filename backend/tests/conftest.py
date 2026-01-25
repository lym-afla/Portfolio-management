"""Fixed conftest file for pytest - removed broken Asset-Broker relationships."""

from datetime import date, timedelta
from decimal import Decimal

import factory
import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from common.models import (
    FX,
    Accounts,
    Assets,
    Brokers,
    FXTransaction,
    Prices,
    Transactions,
)

CustomUser = get_user_model()


def pytest_configure():
    """Configure global test settings before tests collect/run.

    Set a single Faker locale to avoid provider locale probing and DEBUG logs.
    """
    factory.Faker._DEFAULT_LOCALE = "en_GB"


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment with consistent encryption key and decimal context."""
    # Use the same SECRET_KEY for all tests to ensure consistent encryption
    test_settings = {"SECRET_KEY": "test-secret-key-for-consistent-encryption"}
    with override_settings(**test_settings):
        yield


# ========== USER FIXTURES ==========


@pytest.fixture
def user(db):
    """Create a basic test user."""
    return CustomUser.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )


@pytest.fixture
def admin_user(db):
    """Create an admin user for permission testing."""
    return CustomUser.objects.create_user(
        username="adminuser",
        email="admin@example.com",
        password="adminpass123",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def multi_currency_user(db):
    """Create a user with multi-currency portfolio."""
    return CustomUser.objects.create_user(
        username="multicurrency", email="multi@example.com", password="multipass123"
    )


# ========== BROKER FIXTURES ==========


@pytest.fixture
def broker(user):
    """Create a basic test broker."""
    return Brokers.objects.create(investor=user, name="Test Broker", country="US")


@pytest.fixture
def broker_uk(user):
    """Create a UK-based broker."""
    return Brokers.objects.create(investor=user, name="UK Broker", country="UK")


@pytest.fixture
def broker_eu(user):
    """Create an EU-based broker."""
    return Brokers.objects.create(investor=user, name="EU Broker", country="DE")


@pytest.fixture
def restricted_broker(user):
    """Create a restricted broker for testing permissions."""
    return Brokers.objects.create(
        investor=user, name="Restricted Broker", country="US", restricted=True
    )


# ========== ACCOUNT FIXTURES ==========


@pytest.fixture
def account(broker):
    """Create a basic test account."""
    return Accounts.objects.create(
        broker=broker,
        name="Test Account",
    )


@pytest.fixture
def account_uk(broker_uk):
    """Create a UK-based account."""
    return Accounts.objects.create(
        broker=broker_uk,
        name="UK Account",
    )


@pytest.fixture
def account_us(broker):
    """Create a US-based account."""
    return Accounts.objects.create(
        broker=broker,
        name="US Account",
    )


# ========== ASSET FIXTURES (Fixed - removed broker relationships) ==========


@pytest.fixture
def asset(user):
    """Create a basic USD stock asset."""
    asset = Assets.objects.create(
        type="Stock",
        ISIN="US1234567890",
        name="Test Stock Corp",
        currency="USD",
        exposure="Equity",
        data_source="YAHOO",
        yahoo_symbol="TEST",
    )
    asset.investors.add(user)
    # Note: Asset no longer has brokers relationship
    return asset


@pytest.fixture
def asset_eur(user):
    """Create a EUR-denominated stock."""
    asset = Assets.objects.create(
        type="Stock",
        ISIN="DE1234567890",
        name="European Stock AG",
        currency="EUR",
        exposure="Equity",
        data_source="YAHOO",
        yahoo_symbol="EURTEST",
    )
    asset.investors.add(user)
    # Note: Asset no longer has brokers relationship
    return asset


@pytest.fixture
def asset_gbp(user):
    """Create a GBP-denominated stock."""
    asset = Assets.objects.create(
        type="Stock",
        ISIN="GB1234567890",
        name="British Stock PLC",
        currency="GBP",
        exposure="Equity",
        data_source="YAHOO",
        yahoo_symbol="GBPTEST",
    )
    asset.investors.add(user)
    # Note: Asset no longer has brokers relationship
    return asset


@pytest.fixture
def bond_asset(user):
    """Create a USD bond asset."""
    asset = Assets.objects.create(
        type="Bond",
        ISIN="USBOND123456",
        name="Test Bond 2025",
        currency="USD",
        exposure="Fixed Income",
        data_source="YAHOO",
        yahoo_symbol="TESTBOND",
    )
    asset.investors.add(user)
    # Note: Asset no longer has brokers relationship
    return asset


# ========== TRANSACTION FIXTURES ==========


@pytest.fixture
def sample_transactions(user, broker, asset):
    """Create a set of sample transactions for testing."""
    transactions = []

    # Create account
    account = Accounts.objects.create(
        broker=broker,
        name="Test Account",
    )

    # Initial purchase
    tx1 = Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        currency="USD",
        type="Buy",
        date=date(2023, 1, 15),
        quantity=Decimal("100"),
        price=Decimal("50.00"),
        commission=Decimal("-5.00"),
    )
    transactions.append(tx1)

    # Additional purchase
    tx2 = Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        currency="USD",
        type="Buy",
        date=date(2023, 3, 20),
        quantity=Decimal("50"),
        price=Decimal("55.00"),
        commission=Decimal("-3.00"),
    )
    transactions.append(tx2)

    # Partial sale
    tx3 = Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        currency="USD",
        type="Sell",
        date=date(2023, 6, 10),
        quantity=Decimal("-30"),
        price=Decimal("60.00"),
        commission=Decimal("-3.00"),
    )
    transactions.append(tx3)

    # Dividend
    tx4 = Transactions.objects.create(
        investor=user,
        account=account,
        security=asset,
        currency="USD",
        type="Dividend",
        date=date(2023, 3, 31),
        quantity=None,
        price=None,
        cash_flow=Decimal("75.00"),
        commission=None,
    )
    transactions.append(tx4)

    return transactions


@pytest.fixture
def multi_currency_transactions(
    multi_currency_user, broker, asset, asset_eur, asset_gbp
):
    """Create multi-currency transactions for FX testing."""
    transactions = []

    # Create account
    account = Accounts.objects.create(
        broker=broker,
        name="Multi-Currency Account",
    )

    # USD asset purchase
    tx1 = Transactions.objects.create(
        investor=multi_currency_user,
        account=account,
        security=asset,
        currency="USD",
        type="Buy",
        date=date(2023, 1, 15),
        quantity=Decimal("100"),
        price=Decimal("50.00"),
        cash_flow=Decimal("-5000.00"),
        commission=Decimal("5.00"),
    )
    transactions.append(tx1)

    # EUR asset purchase
    tx2 = Transactions.objects.create(
        investor=multi_currency_user,
        account=account,
        security=asset_eur,
        currency="EUR",
        type="Buy",
        date=date(2023, 2, 15),
        quantity=Decimal("200"),
        price=Decimal("40.00"),
        cash_flow=Decimal("-8000.00"),
        commission=Decimal("4.00"),
    )
    transactions.append(tx2)

    # GBP asset purchase
    tx3 = Transactions.objects.create(
        investor=multi_currency_user,
        account=account,
        security=asset_gbp,
        currency="GBP",
        type="Buy",
        date=date(2023, 3, 15),
        quantity=Decimal("150"),
        price=Decimal("35.00"),
        cash_flow=Decimal("-5250.00"),
        commission=Decimal("3.50"),
    )
    transactions.append(tx3)

    return transactions


# ========== FX RATE FIXTURES ==========


@pytest.fixture
def fx_rates_usd_eur(user):
    """Create USD/EUR FX rate history with reduced data for performance."""
    rates = []
    base_date = date(2023, 1, 1)

    for i in range(10):  # Reduced from 365 to 10 for performance
        current_date = base_date + timedelta(days=i * 30)  # Monthly data
        rate = Decimal("1.3") + (Decimal("0.02") * (i % 5) / 5)  # Some variation
        fx = FX.objects.create(date=current_date, USDEUR=rate)
        fx.investors.add(user)
        rates.append(fx)

    # Ensure we have the specific dates needed by tests
    test_dates = [
        date(2023, 1, 15),  # Multi-date test
        date(2023, 3, 15),  # Multi-date test
        date(2023, 6, 15),  # Most frequently used date
        date(2023, 6, 16),  # Interpolation test
        date(2023, 6, 17),  # Weekend test
        date(2023, 9, 15),  # Multi-date test
        date(2023, 12, 15),  # Multi-date test
    ]

    for test_date in test_dates:
        # Check if date already exists from the loop
        if not any(r.date == test_date for r in rates):
            test_rate = Decimal("1.25") + (
                Decimal("0.01") * test_dates.index(test_date)
            )
            test_fx = FX.objects.create(date=test_date, USDEUR=test_rate)
            test_fx.investors.add(user)
            rates.append(test_fx)

    return rates


@pytest.fixture
def fx_rates_multi_currency(multi_currency_user):
    """Create comprehensive FX rate data for testing cross-currency conversions."""
    rates = []
    base_date = date(2023, 1, 1)

    for i in range(10):  # Reduced from 365 to 10 for performance
        current_date = base_date + timedelta(days=i * 30)  # Monthly data

        # Create FX rates with realistic variations
        # Using correct convention: CUR1CUR2 = number of CUR1 per 1 CUR2
        fx = FX.objects.create(
            date=current_date,
            USDEUR=Decimal("1.1")
            + (Decimal("0.10") * (i % 5) / 5),  # 1.1 USD per 1 EUR
            USDGBP=Decimal("1.22")
            + (Decimal("0.03") * (i % 5) / 5),  # 1.22 USD per 1 GBP
            CHFGBP=Decimal("1.14")
            + (Decimal("0.02") * (i % 5) / 5),  # 1.14 CHF per 1 GBP
            RUBUSD=Decimal("75") + (Decimal("5") * (i % 5) / 5),  # 75 RUB per 1 USD
            PLNUSD=Decimal("4") + (Decimal("0.3") * (i % 5) / 5),  # 4 PLN per 1 USD
        )
        fx.investors.add(multi_currency_user)
        rates.append(fx)

    return rates


@pytest.fixture
def fx_transaction(user, account):
    """Create a sample FX transaction."""
    return FXTransaction.objects.create(
        investor=user,
        account=account,
        date=date(2023, 2, 15),
        from_currency="USD",
        to_currency="EUR",
        from_amount=Decimal("1000.00"),
        to_amount=Decimal("920.00"),
        exchange_rate=Decimal("0.92"),
        commission=Decimal("2.00"),
        comment="Test currency conversion",
    )


# ========== PRICE HISTORY FIXTURES ==========


@pytest.fixture
def price_history(asset):
    """Create price history for an asset with reduced data for performance."""
    prices = []
    base_date = date(2023, 1, 1)
    base_price = Decimal("50.00")

    for i in range(12):  # Reduced from 365 to 12 for performance
        current_date = base_date + timedelta(days=i * 30)  # Monthly data
        # Simulate price movement with some volatility
        price_change = Decimal("0.01") * (i % 4 - 2)  # +/- $0.02 movement
        current_price = (
            base_price + price_change + (Decimal("0.01") * i)
        )  # Slight upward trend

        price = Prices.objects.create(
            date=current_date, security=asset, price=current_price
        )
        prices.append(price)

    # Add price data for June 15, 2023 to ensure test compatibility
    # This date is used in multiple tests and might not be covered by monthly data
    june_15_date = date(2023, 6, 15)
    if not any(price.date == june_15_date for price in prices):
        june_price = base_price + Decimal("0.50")  # Price increased by $0.50 by June
        Prices.objects.create(date=june_15_date, security=asset, price=june_price)
        prices.append(Prices.objects.get(date=june_15_date, security=asset))

    return prices


@pytest.fixture
def price_history_multi_asset(asset, asset_eur, asset_gbp):
    """Create price histories for multiple assets with reduced data for performance."""
    price_data = {}
    base_date = date(2023, 1, 1)
    june_15_date = date(2023, 6, 15)

    # USD asset prices
    prices_usd = []
    for i in range(12):  # Reduced from 365 to 12 for performance
        current_date = base_date + timedelta(days=i * 30)  # Monthly data
        price = Decimal("50.00") + (Decimal("0.2") * i) + (Decimal("0.5") * (i % 4 - 2))
        prices_usd.append(
            Prices.objects.create(date=current_date, security=asset, price=price)
        )
    price_data["USD"] = prices_usd

    # Add price data for June 15, 2023 to USD asset
    june_price_usd = (
        Decimal("50.00") + (Decimal("0.2") * 5) + Decimal("0.5")
    )  # Price increased by June
    Prices.objects.create(date=june_15_date, security=asset, price=june_price_usd)
    price_data["USD"].append(Prices.objects.get(date=june_15_date, security=asset))

    # EUR asset prices
    prices_eur = []
    for i in range(12):
        current_date = base_date + timedelta(days=i * 30)
        price = (
            Decimal("40.00") + (Decimal("0.15") * i) + (Decimal("0.3") * (i % 4 - 2))
        )
        prices_eur.append(
            Prices.objects.create(date=current_date, security=asset_eur, price=price)
        )
    price_data["EUR"] = prices_eur

    # Add price data for June 15, 2023 to EUR asset
    june_price_eur = (
        Decimal("40.00") + (Decimal("0.15") * 5) + Decimal("0.3")
    )  # Price increased by June
    Prices.objects.create(date=june_15_date, security=asset_eur, price=june_price_eur)
    price_data["EUR"].append(Prices.objects.get(date=june_15_date, security=asset_eur))

    # GBP asset prices
    prices_gbp = []
    for i in range(12):
        current_date = base_date + timedelta(days=i * 30)
        price = (
            Decimal("35.00") + (Decimal("0.18") * i) + (Decimal("0.4") * (i % 4 - 2))
        )
        prices_gbp.append(
            Prices.objects.create(date=current_date, security=asset_gbp, price=price)
        )
    price_data["GBP"] = prices_gbp

    # Add price data for June 15, 2023 to GBP asset
    june_price_gbp = (
        Decimal("35.00") + (Decimal("0.18") * 5) + Decimal("0.4")
    )  # Price increased by June
    Prices.objects.create(date=june_15_date, security=asset_gbp, price=june_price_gbp)
    price_data["GBP"].append(Prices.objects.get(date=june_15_date, security=asset_gbp))

    return price_data


# ========== UTILITY FIXTURES ==========


@pytest.fixture
def test_dates():
    """Provide a set of common test dates."""
    return {
        "today": date.today(),
        "start_of_year": date(date.today().year, 1, 1),
        "end_of_year": date(date.today().year, 12, 31),
        "last_year": date(date.today().year - 1, 1, 1),
        "sample_date": date(2023, 6, 15),
        "future_date": date(date.today().year + 1, 6, 15),
    }


@pytest.fixture
def decimal_values():
    """Provide common decimal values for testing."""
    return {
        "zero": Decimal("0"),
        "one": Decimal("1"),
        "hundred": Decimal("100"),
        "thousand": Decimal("1000"),
        "small_amount": Decimal("0.01"),
        "large_amount": Decimal("999999.99"),
        "percentage": Decimal("0.05"),  # 5%
        "rate": Decimal("1.234567"),
    }


# ========== API FIXTURES ==========


@pytest.fixture
def api_client():
    """Create an API client."""
    return APIClient()


@pytest.fixture
def admin_client(admin_user):
    """Create an authenticated API client for admin user."""
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def authenticated_client(user):
    """Create an authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ========== FX FIXTURES ==========


@pytest.fixture
def fx_rates(user):
    """Create a set of basic FX rates for testing."""
    rates = []
    base_date = date(2023, 1, 1)

    for i in range(5):  # Reduced from 10 to 5 for performance
        current_date = base_date + timedelta(days=i)
        rate = Decimal("0.92") + (Decimal("0.01") * (i % 3) / 3)  # Small variation
        fx = FX.objects.create(
            date=current_date,
            USDEUR=rate,
            USDGBP=Decimal("0.82") + (Decimal("0.01") * (i % 3) / 3),
            CHFGBP=Decimal("0.88") + (Decimal("0.01") * (i % 3) / 3),
        )
        fx.investors.add(user)
        rates.append(fx)

    return rates


@pytest.fixture
def multi_currency_portfolio(multi_currency_user, broker):
    """Create a multi-currency portfolio for testing."""
    from common.models import Accounts

    # Create account
    account = Accounts.objects.create(
        broker=broker,
        name="Multi-Currency Account",
    )

    return account
