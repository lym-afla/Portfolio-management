import random
from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import date, timedelta
from common.models import Assets, Brokers, Transactions, FX, Prices

class AssetsBuyInPriceTestCase(TestCase):
    def setUp(self):
        # Create a user
        self.user = get_user_model().objects.create_user(username='testuser', password='12345')

        # Create a broker
        self.broker = Brokers.objects.create(investor=self.user, name='Test Broker')

        # Create an asset
        self.asset = Assets.objects.create(
            investor=self.user,
            type='Stock',
            ISIN='US0378331005',
            name='Apple Inc.',
            currency='USD'
        )

        self.base_date = date(2023, 1, 1)

        # Create transactions and corresponding prices
        transactions_data = [
            (date(2023, 1, 1), 5, Decimal('2')),
            (date(2023, 2, 15), 2, Decimal('4')),
            (date(2023, 3, 12), 4, Decimal('7')),
            (date(2023, 4, 5), -2, Decimal('9')),
            (date(2023, 5, 23), 3, Decimal('12')),
            (date(2023, 6, 10), -7, Decimal('17')),
            (date(2023, 7, 22), 2, Decimal('18')),
            (date(2023, 8, 10), -7, Decimal('19')),
            (date(2023, 8, 15), -9, Decimal('20')),
            (date(2023, 8, 23), -11, Decimal('18')),
            (date(2023, 9, 10), 5, Decimal('24')),
            (date(2023, 10, 1), 15, Decimal('12')),
            (date(2023, 10, 15), 5, Decimal('18')),
            (date(2023, 10, 20), -2, Decimal('11')),
            (date(2023, 11, 15), 3, Decimal('23')),
            (date(2023, 12, 1), -6, Decimal('21')),
        ]

        # Shuffle the transactions_data list
        random.shuffle(transactions_data)

        for transaction_date, quantity, price in transactions_data:
            Transactions.objects.create(
                investor=self.user,
                broker=self.broker,
                security=self.asset,
                currency='USD',
                type='Buy' if quantity > 0 else 'Sell',
                date=transaction_date,
                quantity=quantity,
                price=price
            )
            Prices.objects.create(
                date=transaction_date,
                security=self.asset,
                price=price
            )

        # Create FX rates
        FX.objects.create(date=date(2023, 1, 1), investor=self.user, USDEUR=Decimal('1.1'))
        FX.objects.create(date=date(2023, 3, 1), investor=self.user, USDEUR=Decimal('1.15'))
        FX.objects.create(date=date(2023, 5, 1), investor=self.user, USDEUR=Decimal('1.25'))

    def test_calculate_buy_in_price_basic_1(self):
        # Test basic functionality
        buy_in_price = self.asset.calculate_buy_in_price(date(2023, 4, 1))
        self.assertAlmostEqual(buy_in_price, Decimal('4.1818'), places=4)

    def test_calculate_buy_in_price_basic_2(self):
        # Test basic functionality
        buy_in_price = self.asset.calculate_buy_in_price(date(2023, 6, 5))
        self.assertAlmostEqual(buy_in_price, Decimal('6.1364'), places=4)

    def test_calculate_buy_in_price_basic_3(self):
        # Test basic functionality
        buy_in_price = self.asset.calculate_buy_in_price(date(2023, 6, 15))
        self.assertAlmostEqual(buy_in_price, Decimal('6.1364'), places=4)

    def test_calculate_buy_in_price_basic_4(self):
        # Test basic functionality
        buy_in_price = self.asset.calculate_buy_in_price(date(2023, 7, 30))
        self.assertAlmostEqual(buy_in_price, Decimal('9.5260'), places=4)

    def test_calculate_buy_in_price_with_currency_conversion_1(self):
        # Test with currency conversion
        buy_in_price = self.asset.calculate_buy_in_price(date(2023, 1, 1), currency='EUR')
        self.assertAlmostEqual(buy_in_price, Decimal('1.8182'), places=4)

    def test_calculate_buy_in_price_with_currency_conversion_2(self):
        # Test with currency conversion
        buy_in_price = self.asset.calculate_buy_in_price(date(2023, 5, 30), currency='EUR')
        self.assertAlmostEqual(buy_in_price, Decimal('5.1758'), places=4)


    def test_calculate_buy_in_price_with_broker_filter(self):
        # Test with broker filter
        another_broker = Brokers.objects.create(investor=self.user, name='Another Broker')
        Transactions.objects.create(
            investor=self.user,
            broker=another_broker,
            security=self.asset,
            currency='USD',
            type='Buy',
            date=date(2023, 2, 5),
            quantity=10,
            price=Decimal('5.00')
        )
        buy_in_price = self.asset.calculate_buy_in_price(
            date(2023, 6, 15),
            broker_id_list=[self.broker.id]
        )
        self.assertAlmostEqual(buy_in_price, Decimal('6.1364'), places=4)

    def test_calculate_buy_in_price_with_start_date(self):
        # Test with start date
        buy_in_price = self.asset.calculate_buy_in_price(
            date(2023, 7, 23),
            start_date=date(2023, 5, 1)
        )
        # Expected: (4*2 + 7*4) / 6
        expected_price = Decimal('12.1071')
        self.assertAlmostEqual(buy_in_price, expected_price, places=4)

    def test_calculate_buy_in_price_no_transactions(self):
        # Test when there are no transactions
        empty_asset = Assets.objects.create(
            investor=self.user,
            type='Stock',
            ISIN='US5949181045',
            name='Microsoft Corp.',
            currency='USD'
        )
        buy_in_price = empty_asset.calculate_buy_in_price(self.base_date)
        self.assertIsNone(buy_in_price)

    def test_calculate_buy_in_price_short_position(self):
        # Test for short position
        buy_in_price = self.asset.calculate_buy_in_price(date(2023, 9, 15))
        self.assertAlmostEqual(buy_in_price, Decimal('18.9000'), places=4)

    # Additional test for long position after short
    def test_calculate_buy_in_price_long_after_short(self):
        # Test for long position after being short
        buy_in_price = self.asset.calculate_buy_in_price(date(2023, 11, 21))
        self.assertAlmostEqual(buy_in_price, Decimal('20.5000'), places=4)