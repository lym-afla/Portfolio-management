from datetime import date
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from common.models import FX
from common.models import Assets
from common.models import Brokers
from common.models import FXTransaction
from common.models import Prices
from common.models import Transactions

CustomUser = get_user_model()


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment with consistent encryption key and decimal context"""
    # Use the same SECRET_KEY for all tests to ensure consistent encryption
    test_settings = {"SECRET_KEY": "test-secret-key-for-consistent-encryption"}
    with override_settings(**test_settings):
        yield


# ========== USER FIXTURES ==========


@pytest.fixture
def user(db):
    """Create a basic test user"""
    return CustomUser.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )


@pytest.fixture
def admin_user(db):
    """Create an admin user for permission testing"""
    return CustomUser.objects.create_user(
        username="adminuser",
        email="admin@example.com",
        password="adminpass123",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def multi_currency_user(db):
    """Create a user with multi-currency portfolio"""
    return CustomUser.objects.create_user(
        username="multicurrency", email="multi@example.com", password="multipass123"
    )


# ========== BROKER FIXTURES ==========


@pytest.fixture
def broker(user):
    """Create a basic test broker"""
    return Brokers.objects.create(investor=user, name="Test Broker", country="US")


@pytest.fixture
def broker_uk(user):
    """Create a UK-based broker"""
    return Brokers.objects.create(investor=user, name="UK Broker", country="UK")


@pytest.fixture
def broker_eu(user):
    """Create an EU-based broker"""
    return Brokers.objects.create(investor=user, name="EU Broker", country="DE")


@pytest.fixture
def restricted_broker(user):
    """Create a restricted broker for testing permissions"""
    return Brokers.objects.create(
        investor=user, name="Restricted Broker", country="US", restricted=True
    )


# ========== ASSET FIXTURES ==========


@pytest.fixture
def asset(user, broker):
    """Create a basic USD stock asset"""
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
    asset.brokers.add(broker)
    return asset


@pytest.fixture
def asset_eur(user, broker_eu):
    """Create a EUR-denominated stock"""
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
    asset.brokers.add(broker_eu)
    return asset


@pytest.fixture
def asset_gbp(user, broker_uk):
    """Create a GBP-denominated stock"""
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
    asset.brokers.add(broker_uk)
    return asset


@pytest.fixture
def bond_asset(user, broker):
    """Create a USD bond asset"""
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
    asset.brokers.add(broker)
    return asset


# ========== TRANSACTION FIXTURES ==========


@pytest.fixture
def sample_transactions(user, broker, asset):
    """Create a set of sample transactions for testing"""
    transactions = []

    # Initial purchase
    tx1 = Transactions.objects.create(
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
    transactions.append(tx1)

    # Additional purchase
    tx2 = Transactions.objects.create(
        investor=user,
        broker=broker,
        security=asset,
        currency="USD",
        type="Buy",
        date=date(2023, 3, 20),
        quantity=Decimal("50"),
        price=Decimal("55.00"),
        cash_flow=Decimal("-2750.00"),
        commission=Decimal("3.00"),
    )
    transactions.append(tx2)

    # Partial sale
    tx3 = Transactions.objects.create(
        investor=user,
        broker=broker,
        security=asset,
        currency="USD",
        type="Sell",
        date=date(2023, 6, 10),
        quantity=Decimal("-30"),
        price=Decimal("60.00"),
        cash_flow=Decimal("1800.00"),
        commission=Decimal("3.00"),
    )
    transactions.append(tx3)

    # Dividend
    tx4 = Transactions.objects.create(
        investor=user,
        broker=broker,
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
    """Create multi-currency transactions for FX testing"""
    transactions = []

    # USD asset purchase
    tx1 = Transactions.objects.create(
        investor=multi_currency_user,
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
    transactions.append(tx1)

    # EUR asset purchase
    tx2 = Transactions.objects.create(
        investor=multi_currency_user,
        broker=broker,
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
        broker=broker,
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
    """Create USD/EUR FX rate history"""
    rates = []
    base_date = date(2023, 1, 1)

    for i in range(365):  # One year of data
        current_date = base_date + timedelta(days=i)
        rate = Decimal("0.92") + (Decimal("0.02") * (i % 30) / 30)  # Some variation
        fx = FX.objects.create(date=current_date, investor=user, USDEUR=rate)
        rates.append(fx)

    return rates


@pytest.fixture
def fx_rates_multi_currency(multi_currency_user):
    """Create comprehensive FX rate data for testing cross-currency conversions"""
    rates = []
    base_date = date(2023, 1, 1)

    for i in range(365):
        current_date = base_date + timedelta(days=i)

        # Create FX rates with realistic variations
        fx = FX.objects.create(
            date=current_date,
            investor=multi_currency_user,
            USDEUR=Decimal("0.92") + (Decimal("0.02") * (i % 30) / 30),
            USDGBP=Decimal("0.82") + (Decimal("0.03") * (i % 30) / 30),
            CHFGBP=Decimal("0.88") + (Decimal("0.02") * (i % 30) / 30),
            RUBUSD=Decimal("0.013") + (Decimal("0.001") * (i % 30) / 30),
            PLNUSD=Decimal("0.25") + (Decimal("0.02") * (i % 30) / 30),
        )
        rates.append(fx)

    return rates


@pytest.fixture
def fx_transaction(user, broker):
    """Create a sample FX transaction"""
    return FXTransaction.objects.create(
        investor=user,
        broker=broker,
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
def price_history(user, asset):
    """Create price history for an asset"""
    prices = []
    base_date = date(2023, 1, 1)
    base_price = Decimal("50.00")

    for i in range(365):
        current_date = base_date + timedelta(days=i)
        # Simulate price movement with some volatility
        price_change = Decimal("0.01") * (i % 20 - 10)  # +/- $0.10 movement
        current_price = (
            base_price + price_change + (Decimal("0.001") * i)
        )  # Slight upward trend

        price = Prices.objects.create(
            date=current_date, security=asset, price=current_price
        )
        prices.append(price)

    return prices


@pytest.fixture
def price_history_multi_asset(user, asset, asset_eur, asset_gbp):
    """Create price histories for multiple assets"""
    price_data = {}

    # USD asset prices
    base_date = date(2023, 1, 1)
    prices_usd = []
    for i in range(365):
        current_date = base_date + timedelta(days=i)
        price = (
            Decimal("50.00") + (Decimal("0.02") * i) + (Decimal("0.5") * (i % 10 - 5))
        )
        prices_usd.append(
            Prices.objects.create(date=current_date, security=asset, price=price)
        )
    price_data["USD"] = prices_usd

    # EUR asset prices
    prices_eur = []
    for i in range(365):
        current_date = base_date + timedelta(days=i)
        price = (
            Decimal("40.00") + (Decimal("0.015") * i) + (Decimal("0.3") * (i % 10 - 5))
        )
        prices_eur.append(
            Prices.objects.create(date=current_date, security=asset_eur, price=price)
        )
    price_data["EUR"] = prices_eur

    # GBP asset prices
    prices_gbp = []
    for i in range(365):
        current_date = base_date + timedelta(days=i)
        price = (
            Decimal("35.00") + (Decimal("0.018") * i) + (Decimal("0.4") * (i % 10 - 5))
        )
        prices_gbp.append(
            Prices.objects.create(date=current_date, security=asset_gbp, price=price)
        )
    price_data["GBP"] = prices_gbp

    return price_data


# ========== COMPLEX SCENARIO FIXTURES ==========


@pytest.fixture
def complete_portfolio(
    user,
    broker,
    asset,
    bond_asset,
    sample_transactions,
    price_history,
    fx_rates_usd_eur,
):
    """Create a complete portfolio scenario with multiple asset types"""
    return {
        "user": user,
        "broker": broker,
        "assets": [asset, bond_asset],
        "transactions": sample_transactions,
        "price_history": price_history,
        "fx_rates": fx_rates_usd_eur,
    }


@pytest.fixture
def loss_making_portfolio(user, broker):
    """Create a portfolio that shows losses for testing loss calculations"""
    # Create an asset that loses value
    losing_asset = Assets.objects.create(
        type="Stock",
        ISIN="LOSS123456789",
        name="Losing Stock Corp",
        currency="USD",
        exposure="Equity",
    )
    losing_asset.investors.add(user)
    losing_asset.brokers.add(broker)

    # Create high buy price transactions
    tx1 = Transactions.objects.create(
        investor=user,
        broker=broker,
        security=losing_asset,
        currency="USD",
        type="Buy",
        date=date(2023, 1, 15),
        quantity=Decimal("100"),
        price=Decimal("100.00"),  # High buy price
        cash_flow=Decimal("-10000.00"),
        commission=Decimal("10.00"),
    )

    # Create current low prices
    for i in range(30):  # Create recent low prices
        current_date = date(2023, 2, 1) + timedelta(days=i)
        Prices.objects.create(
            date=current_date,
            security=losing_asset,
            price=Decimal("30.00"),  # Low current price
        )

    return {
        "asset": losing_asset,
        "transactions": [tx1],
        "buy_price": Decimal("100.00"),
        "current_price": Decimal("30.00"),
    }


# ========== UTILITY FIXTURES ==========


@pytest.fixture
def test_dates():
    """Provide a set of common test dates"""
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
    """Provide common decimal values for testing"""
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


@pytest.fixture
def currency_pairs():
    """Provide common currency pairs for FX testing"""
    return {
        "direct": [("USD", "EUR"), ("USD", "GBP"), ("EUR", "GBP")],
        "cross": [("USD", "JPY"), ("EUR", "JPY"), ("GBP", "JPY")],
        "exotic": [("USD", "RUB"), ("EUR", "PLN"), ("GBP", "CHF")],
    }


# Legacy fixtures for backward compatibility
@pytest.fixture
def asset_basic(user, broker):
    """Legacy fixture name - create a basic USD stock asset"""
    asset = Assets.objects.create(
        type="Stock",
        ISIN="TEST123456789",
        name="Test Stock",
        currency="USD",
        exposure="Equity",
    )
    asset.investors.add(user)
    asset.brokers.add(broker)
    return asset
