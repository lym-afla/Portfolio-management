import pytest
import logging
from decimal import Decimal
from datetime import date, timedelta, datetime
from django.contrib.auth import get_user_model
from common.models import FX, Assets, Brokers, Transactions
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

@pytest.fixture
def general_transactions(user, broker, asset):
    transactions_data = [
        ("01/01/2023", 2, 5),
        ("15/02/2023", 4, 2),
        ("12/03/2023", 7, 4),
        ("05/04/2023", 9, -2),
        ("23/05/2023", 12, 3),
        ("10/06/2023", 17, -7),
        ("22/07/2023", 18, 2),
        ("10/08/2023", 19, -7),
        ("15/08/2023", 20, -9),
        ("23/08/2023", 18, -11),
        ("10/09/2023", 24, 5),
        ("01/10/2023", 12, 15),
        ("15/10/2023", 18, 5),
        ("20/10/2023", 11, -2),
        ("15/11/2023", 23, 3),
        ("01/12/2023", 21, -6),
    ]

    for date_str, price, quantity in transactions_data:
        date = datetime.strptime(date_str, "%d/%m/%Y").date()
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            date=date,
            type=TRANSACTION_TYPE_BUY if quantity > 0 else TRANSACTION_TYPE_SELL,
            quantity=Decimal(quantity),
            price=Decimal(price),
            currency='USD'
        )

    return Transactions.objects.filter(security=asset)

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

    def test_realized_gain_loss_complex_scenario(self, asset, general_transactions, broker, caplog):
        caplog.set_level(logging.INFO)

        test_dates = [
            (datetime(2023, 2, 1).date(), Decimal('0'), Decimal('0')),
            (datetime(2023, 4, 1).date(), Decimal('0'), Decimal('0')),
            (datetime(2023, 5, 1).date(), Decimal('9.64'), Decimal('9.64')),
            (datetime(2023, 7, 1).date(), Decimal('85.68'), Decimal('85.68')),
            (datetime(2023, 9, 1).date(), Decimal('152'), Decimal('0')),
            (datetime(2023, 9, 30).date(), Decimal('126.5'), Decimal('-25.5')),
            (datetime(2023, 10, 1).date(), Decimal('230'), Decimal('0')),
            (datetime(2023, 11, 30).date(), Decimal('216'), Decimal('-14')),
            (datetime(2023, 12, 31).date(), Decimal('219'), Decimal('0')),
        ]

        for test_date, expected_gain_loss_all_time, expected_gain_loss_current_position in test_dates:
            caplog.clear()
            # Calculate realized gain/loss
            result = asset.realized_gain_loss(test_date, currency='USD', broker_id_list=[broker.id])
            
            print(f"\nTest for date: {test_date}")
            print("Logs:")
            print(caplog.text)
            
            assert result['current_position'] == expected_gain_loss_current_position, f"For date {test_date}: Expected gain/loss to be {expected_gain_loss_current_position}, but got {result['current_position']}"
            assert result['all_time'] == expected_gain_loss_all_time, f"For date {test_date}: Expected gain/loss to be {expected_gain_loss_all_time}, but got {result['all_time']}"

    def test_calculate_buy_in_price(self, user, broker, asset, general_transactions, caplog):
        caplog.set_level(logging.INFO)

        # Create another broker for testing broker filtering
        broker2 = Brokers.objects.create(name='Test Broker 2', investor=user)
        asset.brokers.add(broker2)

        # Test basic functionality
        test_dates = [
            (datetime(2023, 2, 1).date(), Decimal('2')),
            (datetime(2023, 4, 1).date(), Decimal('4.181818')),
            (datetime(2023, 5, 1).date(), Decimal('4.181818')),
            (datetime(2023, 7, 1).date(), Decimal('6.136364')),
            (datetime(2023, 8, 1).date(), Decimal('9.525974')),
            (datetime(2023, 9, 30).date(), Decimal('18.9')),
            (datetime(2023, 11, 30).date(), Decimal('20.5')),
            (datetime(2023, 12, 31).date(), Decimal('20.5')),
        ]

        for test_date, expected_price in test_dates:
            caplog.clear()
            buy_in_price = asset.calculate_buy_in_price(test_date)
            
            print(f"\nTest for date: {test_date}")
            print("Logs:")
            print(caplog.text)
            
            assert buy_in_price == expected_price, f"For date {test_date}: Expected buy-in price to be {expected_price}, but got {buy_in_price}"

        # Test with no transactions
        empty_asset = Assets.objects.create(
            investor=user,
            type='Stock',
            ISIN='US1234567890',
            name='Test Stock',
            currency='USD',
            exposure='Equity',
            restricted=False
        )
        caplog.clear()
        buy_in_price_no_transactions = empty_asset.calculate_buy_in_price(datetime(2023, 12, 31).date())
        
        print("\nTest for empty asset:")
        print("Logs:")
        print(caplog.text)
        
        assert buy_in_price_no_transactions is None, f"Expected buy-in price to be None, but got {buy_in_price_no_transactions}"

    def test_calculate_buy_in_price_with_start_date(self, user, broker, asset, general_transactions):
        # Set start date and end date for the test
        start_date = datetime(2023, 5, 1).date()
        end_date = datetime(2023, 7, 30).date()

        # Calculate realized gain/loss
        result = asset.calculate_buy_in_price(end_date, currency='USD', broker_id_list=[broker.id], start_date=start_date)

        expected_price = Decimal('12.107143')
        # expected_all_time = Decimal('150.00')  # Same as current position because we're using start_date

        assert result == expected_price, f"Expected current position gain/loss to be {expected_price}, but got {result['current_position']}"

    def test_calculate_buy_in_price_with_FX(self, user, broker, asset, general_transactions, caplog):
        caplog.set_level(logging.INFO)

        # Set start date and end date for the test
        end_date = datetime(2023, 7, 22).date()

        # Add FX rates for USD/EUR
        FX.objects.create(date=datetime(2023, 1, 1).date(), USDEUR=Decimal('1.1'))
        FX.objects.create(date=datetime(2023, 3, 1).date(), USDEUR=Decimal('1.15'))
        FX.objects.create(date=datetime(2023, 5, 1).date(), USDEUR=Decimal('1.25'))

        test_dates = [
            (datetime(2023, 1, 1).date(), Decimal('1.818182')),
            (datetime(2023, 2, 15).date(), Decimal('2.337662')),
            (datetime(2023, 3, 12).date(), Decimal('3.701042')),
            (datetime(2023, 4, 5).date(), Decimal('3.701042')),
            (datetime(2023, 5, 23).date(), Decimal('5.175782')),
            (datetime(2023, 6, 10).date(), Decimal('5.175782')),
            (datetime(2023, 7, 22).date(), Decimal('7.811273')),
        ]

        for test_date, expected_price in test_dates:
            caplog.clear()
            buy_in_price = asset.calculate_buy_in_price(test_date, currency='EUR')
            
            print(f"\nTest for date: {test_date}")
            print("Logs:")
            print(caplog.text)
            
            assert round(buy_in_price, 4) == round(expected_price, 4), f"For date {test_date}: Expected buy-in price to be {expected_price}, but got {buy_in_price}"



