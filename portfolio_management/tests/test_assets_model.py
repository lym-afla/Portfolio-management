import pytest
import logging
from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth import get_user_model
from common.models import Assets, Brokers, Transactions
from constants import TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_CASH_OUT

User = get_user_model()

@pytest.fixture
def user():
    return User.objects.create_user(username='testuser', password='testpass')

@pytest.fixture
def broker(user):
    return Brokers.objects.create(name='Test Broker', investor=user)

@pytest.fixture
def asset(user, broker):
    asset = Assets.objects.create(
        investor=user,
        type='Stock',
        ISIN='US0378331005',
        name='Apple Inc.',
        currency='USD',
        exposure='Equity',
        restricted=False
    )
    asset.brokers.add(broker)
    return asset

@pytest.mark.django_db
class TestAssetsModel:

    def test_realized_gain_loss_single_trade(self, user, broker, asset, caplog):
        caplog.set_level(logging.DEBUG)

        # Test a simple buy and sell scenario
        buy_date = date(2022, 1, 1)
        sell_date = date(2022, 6, 1)
        
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            date=buy_date,
            type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('10'),
            price=Decimal('100'),
            currency='USD'
        )
        
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            date=sell_date,
            type=TRANSACTION_TYPE_SELL,
            quantity=Decimal('-10'),
            price=Decimal('120'),
            currency='USD'
        )
        
        result = asset.realized_gain_loss(date(2022, 12, 31))
        assert result['all_time'] == Decimal('200')  # (120 - 100) * 10

    def test_realized_gain_loss_long_position(self, user, broker, asset, caplog):
        caplog.set_level(logging.INFO)

        # Test a simple buy and sell scenario (long position)
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 1, 1), type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('10'), price=Decimal('100'), currency='USD'
        )
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 6, 1), type=TRANSACTION_TYPE_SELL,
            quantity=Decimal('-10'), price=Decimal('120'), currency='USD'
        )
        
        result = asset.realized_gain_loss(date(2022, 12, 31))

        # Print captured logs
        print("\nCaptured logs:")
        for record in caplog.records:
            print(f"{record.levelname}: {record.message}")

        assert result['all_time'] == Decimal('200')  # (120 - 100) * 10

    def test_realized_gain_loss_short_position(self, user, broker, asset):
        # Test a simple short sell and buy to cover scenario
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 1, 1), type=TRANSACTION_TYPE_SELL,
            quantity=Decimal('-10'), price=Decimal('100'), currency='USD'
        )
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 6, 1), type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('10'), price=Decimal('80'), currency='USD'
        )
        
        result = asset.realized_gain_loss(date(2022, 12, 31))
        assert result['all_time'] == Decimal('200')  # (100 - 80) * 10

    def test_realized_gain_loss_mixed_positions(self, user, broker, asset):
        # Test a scenario with both long and short positions
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 1, 1), type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('10'), price=Decimal('100'), currency='USD'
        )
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 3, 1), type=TRANSACTION_TYPE_SELL,
            quantity=Decimal('-15'), price=Decimal('120'), currency='USD'
        )
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 6, 1), type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('5'), price=Decimal('110'), currency='USD'
        )
        
        result = asset.realized_gain_loss(date(2022, 12, 31))
        expected_gain = (120 - 100) * 10 + (120 - 110) * 5
        assert result['all_time'] == Decimal(str(expected_gain))

    def test_realized_gain_loss_with_currency_conversion(self, user, broker, asset):
        # Test realized gain/loss with currency conversion
        # You'll need to mock the FX.get_rate function for this test
        pass

    def test_realized_gain_loss_with_broker_filter(self, user, broker, asset):
        # Test realized gain/loss when filtering by broker
        pass

    def test_realized_gain_loss_with_start_date(self, user, broker, asset):
        # Test realized gain/loss with a start date
        pass

    def test_realized_gain_loss_short_position(self, user, broker, asset):
        # Test realized gain/loss for a short position
        pass

    def test_realized_gain_loss_zero_position(self, user, broker, asset):
        # Test realized gain/loss when position becomes zero
        pass
