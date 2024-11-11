import pytest
import logging
from decimal import Decimal
from datetime import date, timedelta, datetime
from django.contrib.auth import get_user_model
from common.models import FX, Assets, Brokers, Prices, Transactions
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
        type='Stock',
        ISIN='US0378331005',
        name='Apple Inc.',
        currency='USD',
        exposure='Equity',
        restricted=False
    )
    asset.investors.add(user)
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
        
        result = asset.realized_gain_loss(date(2022, 12, 31), user)
        assert result['all_time']['total'] == Decimal('200')  # (120 - 100) * 10

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
        
        result = asset.realized_gain_loss(date(2022, 12, 31), user)

        # Print captured logs
        print("\nCaptured logs:")
        for record in caplog.records:
            print(f"{record.levelname}: {record.message}")

        assert result['all_time']['total'] == Decimal('200')  # (120 - 100) * 10

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
        
        result = asset.realized_gain_loss(date(2022, 12, 31), user)
        assert result['all_time']['total'] == Decimal('200')  # (100 - 80) * 10

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
        
        result = asset.realized_gain_loss(date(2022, 12, 31), user)
        expected_gain = (120 - 100) * 10 + (120 - 110) * 5
        assert result['all_time']['total'] == Decimal(str(expected_gain))

    def test_realized_gain_loss_complex_scenario(self, user, broker, asset, general_transactions, caplog):
        caplog.set_level(logging.INFO)

        test_dates = [
            # (datetime(2023, 2, 1).date(), Decimal('0'), Decimal('0')),
            # (datetime(2023, 4, 1).date(), Decimal('0'), Decimal('0')),
            # (datetime(2023, 5, 1).date(), Decimal('9.64'), Decimal('9.64')),
            # (datetime(2023, 7, 1).date(), Decimal('85.68'), Decimal('85.68')),
            # (datetime(2023, 9, 1).date(), Decimal('152'), Decimal('0')),
            # (datetime(2023, 9, 30).date(), Decimal('126.5'), Decimal('-25.5')),
            (datetime(2023, 10, 1).date(), Decimal('230'), Decimal('0')),
            # (datetime(2023, 11, 30).date(), Decimal('216'), Decimal('-14')),
            # (datetime(2023, 12, 31).date(), Decimal('219'), Decimal('0')),
        ]

        for test_date, expected_gain_loss_all_time, expected_gain_loss_current_position in test_dates:
            caplog.clear()
            # Calculate realized gain/loss
            result = asset.realized_gain_loss(test_date, user, currency='USD', broker_id_list=[broker.id])
            
            print(f"\nTest for date: {test_date}")
            print("Logs:")
            print(caplog.text)
            
            assert result['current_position']['total'] == expected_gain_loss_current_position, f"For date {test_date}: Expected gain/loss to be {expected_gain_loss_current_position}, but got {result['current_position']['total']}"
            assert result['all_time']['total'] == expected_gain_loss_all_time, f"For date {test_date}: Expected gain/loss to be {expected_gain_loss_all_time}, but got {result['all_time']['total']}"

    def test_calculate_buy_in_price(self, user, broker, asset, general_transactions, caplog):
        caplog.set_level(logging.INFO)

        # Create another broker for testing broker filtering
        broker2 = Brokers.objects.create(name='Test Broker 2', investor=user)

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
            buy_in_price = asset.calculate_buy_in_price(test_date, user)
            
            print(f"\nTest for date: {test_date}")
            print("Logs:")
            print(caplog.text)
            
            assert buy_in_price == expected_price, f"For date {test_date}: Expected buy-in price to be {expected_price}, but got {buy_in_price}"

        # Test with no transactions
        empty_asset = Assets.objects.create(
            type='Stock',
            ISIN='US1234567890',
            name='Test Stock',
            currency='USD',
            exposure='Equity',
            restricted=False
        )
        empty_asset.investors.add(user)
        caplog.clear()
        buy_in_price_no_transactions = empty_asset.calculate_buy_in_price(datetime(2023, 12, 31).date(), user)
        
        print("\nTest for empty asset:")
        print("Logs:")
        print(caplog.text)
        
        assert buy_in_price_no_transactions is None, f"Expected buy-in price to be None, but got {buy_in_price_no_transactions}"

    def test_calculate_buy_in_price_with_start_date(self, user, broker, asset, general_transactions):
        # Set start date and end date for the test
        start_date = datetime(2023, 5, 1).date()
        end_date = datetime(2023, 7, 30).date()

        # Calculate realized gain/loss
        result = asset.calculate_buy_in_price(end_date, user, currency='USD', broker_id_list=[broker.id], start_date=start_date)

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
            buy_in_price = asset.calculate_buy_in_price(test_date, user, currency='EUR')
            
            print(f"\nTest for date: {test_date}")
            print("Logs:")
            print(caplog.text)
            
            assert round(buy_in_price, 4) == round(expected_price, 4), f"For date {test_date}: Expected buy-in price to be {expected_price}, but got {buy_in_price}"

    def test_realized_gain_loss_with_start_date(self, user, broker, asset):
        # Create transactions
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 1, 1), type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('10'), price=Decimal('100'), currency='USD'
        )
        Prices.objects.create(
            security=asset,
            date=date(2022, 1, 31),
            price=Decimal('110')
        )
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 3, 1), type=TRANSACTION_TYPE_SELL,
            quantity=Decimal('-5'), price=Decimal('120'), currency='USD'
        )
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 6, 1), type=TRANSACTION_TYPE_SELL,
            quantity=Decimal('-5'), price=Decimal('130'), currency='USD'
        )
        
        # Test with start date after first transaction
        result = asset.realized_gain_loss(date(2022, 12, 31), user, start_date=date(2022, 2, 1))
        assert result['current_position']['total'] == Decimal('0') # 0 because current position is 0
        assert result['all_time']['total'] == Decimal('150') # (120 - 110) * 5 + (130 - 110) * 5

    def test_realized_gain_loss_for_closed_with_currency_conversion(self, user, broker, asset):
        # Create transactions
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
        
        # Create FX rates
        FX.objects.create(date=date(2022, 1, 1), USDEUR=Decimal('1.1'))
        FX.objects.create(date=date(2022, 6, 1), USDEUR=Decimal('1.2'))
        
        result = asset.realized_gain_loss(date(2022, 12, 31), user, currency='EUR')
        expected_gain = (Decimal('120') / Decimal('1.2') - Decimal('100') / Decimal('1.1')) * Decimal('10')
        assert result['all_time']['total'] == pytest.approx(expected_gain, rel=Decimal('1e-2'))

    def test_realized_gain_loss_for_opened_with_start_date(self, user, broker, asset):
        # Create transactions
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 1, 1), type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('10'), price=Decimal('100'), currency='USD'
        )
        FX.objects.create(date=date(2022, 1, 1), RUBUSD=Decimal('35'))

        asset.prices.create(date=date(2022, 2, 1), price=Decimal('110'))
        FX.objects.create(date=date(2022, 2, 1), RUBUSD=Decimal('42'))

        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 6, 1), type=TRANSACTION_TYPE_SELL,
            quantity=Decimal('-5'), price=Decimal('120'), currency='USD'
        )
        FX.objects.create(date=date(2022, 6, 1), RUBUSD=Decimal('47'))

        asset.prices.create(date=date(2022, 12, 31), price=Decimal('145'))
        FX.objects.create(date=date(2022, 12, 31), RUBUSD=Decimal('62'))

        result = asset.realized_gain_loss(date(2022, 12, 31), user, currency='RUB')
        expected_gain = (Decimal('120') * Decimal('47') - Decimal('100') * Decimal('35')) * Decimal('5')
        assert result['current_position']['total'] == pytest.approx(expected_gain, rel=Decimal('1e-2'))
        assert result['all_time']['total'] == pytest.approx(expected_gain, rel=Decimal('1e-2'))

        result = asset.realized_gain_loss(date(2022, 12, 31), user, currency='RUB', start_date=date(2022, 3, 1))
        expected_gain = (Decimal('120') * Decimal('47') - Decimal('110') * Decimal('42')) * Decimal('5')
        assert result['current_position']['total'] == pytest.approx(expected_gain, rel=Decimal('1e-2'))
        assert result['all_time']['total'] == pytest.approx(expected_gain, rel=Decimal('1e-2'))

        result = asset.realized_gain_loss(date(2022, 12, 31), user, currency='RUB', start_date=date(2022, 7, 1))
        assert result['current_position']['total'] == Decimal('0')
        assert result['all_time']['total'] == Decimal('0')

    def test_unrealized_gain_loss_with_start_date(self, user, broker, asset):
        # Create transactions
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 1, 1), type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('10'), price=Decimal('100'), currency='USD'
        )
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 3, 1), type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('5'), price=Decimal('110'), currency='USD'
        )
        
        # Create price data
        asset.prices.create(date=date(2022, 12, 31), price=Decimal('130'))
        
        # Test with start date after first transaction
        result = asset.unrealized_gain_loss(date(2022, 12, 31), user, start_date=date(2022, 2, 1))
        expected_gain = (Decimal('130') - Decimal('110')) * Decimal('5') + (Decimal('130') - Decimal('100')) * Decimal('10')
        assert result['total'] == pytest.approx(expected_gain, rel=Decimal('1e-2'))

        asset.prices.create(date=date(2022, 2, 10), price=Decimal('105'))

        result = asset.unrealized_gain_loss(date(2022, 12, 31), user, start_date=date(2022, 2, 10))
        expected_gain = (Decimal('130') - Decimal('105')) * Decimal('10') + (Decimal('130') - Decimal('110')) * Decimal('5')
        assert result['total'] == pytest.approx(expected_gain, rel=Decimal('1e-2'))

        asset.prices.create(date=date(2022, 3, 15), price=Decimal('115'))

        result = asset.unrealized_gain_loss(date(2022, 12, 31), user, start_date=date(2022, 3, 15))
        expected_gain = (Decimal('130') - Decimal('115')) * Decimal('15')
        assert result['total'] == pytest.approx(expected_gain, rel=Decimal('1e-2'))

    def test_unrealized_gain_loss_with_currency_conversion_and_start_date(self, user, broker, asset):
        # Create transactions
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 1, 1), type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('10'), price=Decimal('100'), currency='USD'
        )
        
        # Create price data
        asset.prices.create(date=date(2022, 12, 31), price=Decimal('120'))
        
        # Create FX rates
        FX.objects.create(date=date(2022, 1, 1), USDEUR=Decimal('1.15'))
        FX.objects.create(date=date(2022, 12, 31), USDEUR=Decimal('1.25'))
        
        result = asset.unrealized_gain_loss(date(2022, 12, 31), user, currency='EUR')
        expected_gain = ((Decimal('120') / Decimal('1.25')) - (Decimal('100') / Decimal('1.15'))) * Decimal('10')
        assert result['total'] == pytest.approx(expected_gain, rel=Decimal('1e-2'))

        asset.prices.create(date=date(2022, 1, 15), price=Decimal('110'))
        FX.objects.create(date=date(2022, 1, 15), USDEUR=Decimal('1.05'))

        result = asset.unrealized_gain_loss(date(2022, 12, 31), user, currency='EUR', start_date=date(2022, 3, 10))
        expected_gain = ((Decimal('120') / Decimal('1.25')) - (Decimal('110') / Decimal('1.05'))) * Decimal('10')
        assert result['total'] == pytest.approx(expected_gain, rel=Decimal('1e-2'))

    def test_realized_and_unrealized_gain_loss_combined(self, user, broker, asset):
        
        # Create transactions
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 1, 1), type=TRANSACTION_TYPE_BUY,
            quantity=Decimal('10'), price=Decimal('100'), currency='USD'
        )
        Transactions.objects.create(
            investor=user, broker=broker, security=asset,
            date=date(2022, 6, 1), type=TRANSACTION_TYPE_SELL,
            quantity=Decimal('-5'), price=Decimal('120'), currency='USD'
        )
        
        # Create price data
        asset.prices.create(date=date(2022, 12, 31), price=Decimal('130'))
        
        realized_result = asset.realized_gain_loss(date(2022, 12, 31), user)
        unrealized_result = asset.unrealized_gain_loss(date(2022, 12, 31), user)
        
        expected_realized = (120 - 100) * 5
        expected_unrealized = (130 - 100) * 5
        
        assert realized_result['all_time']['total'] == pytest.approx(Decimal(expected_realized), rel=1e-2)
        assert unrealized_result['total'] == pytest.approx(Decimal(expected_unrealized), rel=1e-2)

@pytest.mark.django_db
class TestRealizedGainLoss:

    @pytest.fixture(autouse=True)
    def setup(self, db):
        self.user = User.objects.create(username='testuser')
        self.broker = Brokers.objects.create(name='Test Broker', investor=self.user)
        self.asset = Assets.objects.create(name='Test Asset', currency='CHF')
        self.asset.investors.add(self.user)

    def create_transaction(self, transaction_date, transaction_type, quantity, price):
        return Transactions.objects.create(
            investor=self.user,
            broker=self.broker,
            security=self.asset,
            date=transaction_date,
            type=transaction_type,
            quantity=Decimal(quantity),
            price=Decimal(price),
            currency='CHF'
        )

    def test_start_date_after_first_entry_zero_end_position(self, caplog):
        caplog.set_level(logging.DEBUG)
        
        self.create_transaction(date(2022, 1, 1), TRANSACTION_TYPE_BUY, '10', '100')
        self.create_transaction(date(2022, 3, 1), TRANSACTION_TYPE_SELL, '-5', '110')
        self.create_transaction(date(2022, 5, 1), TRANSACTION_TYPE_SELL, '-5', '120')
        
        result = self.asset.realized_gain_loss(date(2022, 12, 31), self.user, start_date=date(2022, 2, 1))
        
        print("\nResult:", result)
        assert result['all_time']['total'] == Decimal('150')
        assert result['current_position']['total'] == Decimal('0')

    def test_start_date_after_first_entry_nonzero_end_position(self, caplog):
        caplog.set_level(logging.DEBUG)
        
        self.create_transaction(date(2022, 1, 1), TRANSACTION_TYPE_BUY, '15', '100')
        self.create_transaction(date(2022, 3, 1), TRANSACTION_TYPE_SELL, '-5', '110')
        self.create_transaction(date(2022, 5, 1), TRANSACTION_TYPE_SELL, '-5', '120')
        
        result = self.asset.realized_gain_loss(date(2022, 12, 31), self.user, start_date=date(2022, 2, 1))
        
        print("\nResult:", result)
        assert result['all_time']['total'] == Decimal('150')
        assert result['current_position']['total'] == Decimal('150')

    def test_zero_position_at_start_date(self, caplog):
        caplog.set_level(logging.DEBUG)
        
        self.create_transaction(date(2022, 2, 1), TRANSACTION_TYPE_BUY, '10', '100')
        self.create_transaction(date(2022, 3, 1), TRANSACTION_TYPE_SELL, '-5', '110')
        self.create_transaction(date(2022, 5, 1), TRANSACTION_TYPE_SELL, '-5', '120')
        
        result = self.asset.realized_gain_loss(date(2022, 12, 31), self.user, start_date=date(2022, 1, 1))
        
        print("\nResult:", result)
        assert result['all_time']['total'] == Decimal('150')
        assert result['current_position']['total'] == Decimal('0')

    def test_same_day_open_close(self, caplog):
        caplog.set_level(logging.DEBUG)
        
        # Day before: zero position
        self.create_transaction(date(2022, 2, 28), TRANSACTION_TYPE_BUY, '10', '100')
        self.create_transaction(date(2022, 2, 28), TRANSACTION_TYPE_SELL, '-10', '105')

        result = self.asset.realized_gain_loss(date(2022, 12, 31), self.user, start_date=date(2022, 2, 1))

        expected_total = Decimal('50')
        assert result['all_time']['total'] == expected_total
        assert result['current_position']['total'] == Decimal('0')
        
        # Same day open and close
        self.create_transaction(date(2022, 3, 1), TRANSACTION_TYPE_BUY, '5', '110')
        self.create_transaction(date(2022, 3, 1), TRANSACTION_TYPE_SELL, '-5', '115')
        
        # Day after: zero position
        self.create_transaction(date(2022, 3, 2), TRANSACTION_TYPE_BUY, '8', '112')
        self.create_transaction(date(2022, 3, 2), TRANSACTION_TYPE_SELL, '-8', '114')

        # Existing position
        self.create_transaction(date(2022, 8, 3), TRANSACTION_TYPE_BUY, '10', '250')
        self.create_transaction(date(2023, 3, 3), TRANSACTION_TYPE_SELL, '-10', '255')
        
        result = self.asset.realized_gain_loss(date(2022, 12, 31), self.user, start_date=date(2022, 2, 1))
        
        print("\nResult:", result)
        expected_total = Decimal('50') + Decimal('25') + Decimal('16')  # (105-100)*10 + (115-110)*5 + (114-112)*8
        assert result['all_time']['total'] == expected_total
        assert result['current_position']['total'] == Decimal('0')

    def test_multiple_long_and_short_positions(self, caplog):
        caplog.set_level(logging.DEBUG)
        
        self.create_transaction(date(2022, 1, 1), TRANSACTION_TYPE_BUY, '10', '100')
        self.create_transaction(date(2022, 2, 1), TRANSACTION_TYPE_SELL, '-10', '110')
        self.create_transaction(date(2022, 3, 1), TRANSACTION_TYPE_SELL, '-5', '120')
        self.create_transaction(date(2022, 4, 1), TRANSACTION_TYPE_BUY, '5', '115')
        self.create_transaction(date(2022, 5, 1), TRANSACTION_TYPE_BUY, '10', '105')
        self.create_transaction(date(2022, 6, 1), TRANSACTION_TYPE_SELL, '-10', '125')
        
        result = self.asset.realized_gain_loss(date(2022, 12, 31), self.user)
        
        print("\nResult:", result)
        assert result['all_time']['total'] == Decimal('325')
        assert result['current_position']['total'] == Decimal('0')

    def test_UBS_example(self, caplog):
        caplog.set_level(logging.DEBUG)

        self.create_transaction(date(2010, 9, 3), TRANSACTION_TYPE_BUY, '270', '18.09')
        FX.objects.create(date=date(2010, 9, 3), CHFGBP=Decimal('1.5592'))
        self.create_transaction(date(2010, 9, 4), TRANSACTION_TYPE_BUY, '90', '0')
        FX.objects.create(date=date(2010, 9, 4), CHFGBP=Decimal('1.5723'))

        self.asset.prices.create(date=date(2010, 12, 31), price=Decimal('15.35'))
        FX.objects.create(date=date(2010, 12, 31), CHFGBP=Decimal('1.4575'))

        self.asset.prices.create(date=date(2012, 12, 31), price=Decimal('14.27'))
        FX.objects.create(date=date(2012, 12, 31), CHFGBP=Decimal('1.4849'))

        self.create_transaction(date(2013, 3, 1), TRANSACTION_TYPE_SELL, '-47', '14.84')
        FX.objects.create(date=date(2013, 3, 1), CHFGBP=Decimal('1.4279'))

        result = self.asset.realized_gain_loss(date(2013, 12, 31), self.user, currency='GBP', start_date=date(2013, 1, 1))
        print("\nResult:", result)
        assert result['all_time']['total'] == Decimal('36.79')
        assert result['current_position']['total'] == Decimal('36.79')
        assert result['all_time']['price_appreciation'] == Decimal('18.76')
        assert result['current_position']['price_appreciation'] == Decimal('18.76')
        assert result['all_time']['fx_effect'] == Decimal('18.03')
        assert result['current_position']['fx_effect'] == Decimal('18.03')


    # Print captured logs for all tests
    @pytest.fixture(autouse=True)
    def print_logs(self, caplog):
        yield
        print("\nCaptured logs:")
        for record in caplog.records:
            print(f"{record.levelname}: {record.message}")
