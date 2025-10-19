"""
Factory classes for creating test transactions.
Provides realistic transaction data for various testing scenarios.
"""

from datetime import date
from datetime import timedelta
from decimal import Decimal

import factory
from factory import fuzzy

from common.models import Transactions


class TransactionFactory(factory.django.DjangoModelFactory):
    """Factory for creating Transactions with realistic data."""

    class Meta:
        model = Transactions

    currency = fuzzy.FuzzyChoice(["USD", "EUR", "GBP", "CHF"])
    type = fuzzy.FuzzyChoice(
        ["Buy", "Sell", "Dividend", "Interest", "Corporate Action"]
    )
    date = fuzzy.FuzzyDate(date(2020, 1, 1), date.today())
    # quantity = fuzzy.FuzzyDecimal(-1000, 1000, 6)
    # price = fuzzy.FuzzyDecimal(1, 1000, 6)
    # cash_flow = fuzzy.FuzzyDecimal(-100000, 100000, 2)
    # commission = fuzzy.FuzzyDecimal(0, 100, 2)
    comment = factory.Faker("text", max_nb_chars=200)

    @factory.lazy_attribute
    def quantity(self):
        """Generate quantity based on transaction type."""
        if self.type in ["Dividend", "Interest"]:
            return None
        return self.faker.pydecimal(
            left_digits=6, right_digits=6, min_value=-1000, max_value=1000
        )

    @factory.lazy_attribute
    def price(self):
        """Generate price based on transaction type."""
        if self.type in ["Dividend", "Interest"]:
            return None
        return self.faker.pydecimal(
            left_digits=3, right_digits=6, min_value=1, max_value=1000
        )

    @factory.lazy_attribute
    def cash_flow(self):
        """Generate realistic cash flow based on transaction details."""
        if self.type == "Buy":
            # Cash outflow for buys
            if self.quantity and self.price:
                amount = -(abs(self.quantity) * self.price)
                if self.commission:
                    amount -= self.commission
                return amount
            return self.faker.pydecimal(
                left_digits=6, right_digits=2, min_value=-100000, max_value=-100
            )
        elif self.type == "Sell":
            # Cash inflow for sells
            if self.quantity and self.price:
                amount = abs(self.quantity) * self.price
                if self.commission:
                    amount -= self.commission
                return amount
            return self.faker.pydecimal(
                left_digits=6, right_digits=2, min_value=100, max_value=100000
            )
        elif self.type in ["Dividend", "Interest"]:
            # Positive cash flow for dividends and interest
            return self.faker.pydecimal(
                left_digits=4, right_digits=2, min_value=10, max_value=10000
            )
        else:
            # Corporate actions can have various cash flows
            return self.faker.pydecimal(
                left_digits=6, right_digits=2, min_value=-10000, max_value=10000
            )

    @factory.lazy_attribute
    def commission(self):
        """Generate commission based on transaction type."""
        if self.type in ["Dividend", "Interest"]:
            return None
        return self.faker.pydecimal(
            left_digits=2, right_digits=2, min_value=0, max_value=100
        )

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override create to handle required relationships."""
        investor = kwargs.pop("investor", None)
        broker = kwargs.pop("broker", None)
        security = kwargs.pop("security", None)

        if not all([investor, broker, security]):
            raise ValueError(
                "TransactionFactory requires investor, broker, and security"
            )

        return model_class.objects.create(
            investor=investor, broker=broker, security=security, **kwargs
        )


class BuyTransactionFactory(TransactionFactory):
    """Factory for creating buy transactions."""

    type = "Buy"

    @factory.lazy_attribute
    def quantity(self):
        """Positive quantity for buys."""
        return self.faker.pydecimal(
            left_digits=6, right_digits=6, min_value=1, max_value=1000
        )

    @factory.lazy_attribute
    def cash_flow(self):
        """Negative cash flow for buys."""
        if self.quantity and self.price:
            amount = -(self.quantity * self.price)
            if self.commission:
                amount -= self.commission
            return amount
        return self.faker.pydecimal(
            left_digits=6, right_digits=2, min_value=-100000, max_value=-100
        )


class SellTransactionFactory(TransactionFactory):
    """Factory for creating sell transactions."""

    type = "Sell"

    @factory.lazy_attribute
    def quantity(self):
        """Negative quantity for sells."""
        return -self.faker.pydecimal(
            left_digits=6, right_digits=6, min_value=1, max_value=1000
        )

    @factory.lazy_attribute
    def cash_flow(self):
        """Positive cash flow for sells."""
        if self.quantity and self.price:
            amount = abs(self.quantity) * self.price
            if self.commission:
                amount -= self.commission
            return amount
        return self.faker.pydecimal(
            left_digits=6, right_digits=2, min_value=100, max_value=100000
        )


class DividendTransactionFactory(TransactionFactory):
    """Factory for creating dividend transactions."""

    type = "Dividend"
    quantity = None
    price = None
    commission = None

    @factory.lazy_attribute
    def cash_flow(self):
        """Positive cash flow for dividends."""
        return self.faker.pydecimal(
            left_digits=4, right_digits=2, min_value=10, max_value=10000
        )

    @factory.lazy_attribute
    def comment(self):
        """Realistic dividend comments."""
        return f"Dividend payment - {self.faker.date_between(date(2023, 1, 1), date(2023, 12, 31))}"


class LargeBuyTransactionFactory(BuyTransactionFactory):
    """Factory for creating large buy transactions."""

    @factory.lazy_attribute
    def quantity(self):
        """Large quantity for institutional trades."""
        return self.faker.pydecimal(
            left_digits=6, right_digits=6, min_value=1000, max_value=100000
        )

    @factory.lazy_attribute
    def price(self):
        """Lower price for large quantities."""
        return self.faker.pydecimal(
            left_digits=2, right_digits=6, min_value=1, max_value=100
        )


class SmallBuyTransactionFactory(BuyTransactionFactory):
    """Factory for creating small buy transactions."""

    @factory.lazy_attribute
    def quantity(self):
        """Small quantity for retail trades."""
        return self.faker.pydecimal(
            left_digits=3, right_digits=6, min_value=1, max_value=1000
        )


# Batch creation utilities
def create_buy_sell_sequence(investor, broker, security, num_pairs=3):
    """Create a sequence of buy-sell transaction pairs."""

    transactions = []
    base_date = date(2023, 1, 1)

    for i in range(num_pairs):
        # Buy transaction
        buy_date = base_date + timedelta(days=i * 30)
        buy_tx = BuyTransactionFactory.create(
            investor=investor,
            broker=broker,
            security=security,
            date=buy_date,
            quantity=Decimal("100") + (i * 50),
            price=Decimal("50") + (i * 2),
        )
        transactions.append(buy_tx)

        # Sell transaction (partial or full)
        sell_date = buy_date + timedelta(days=15)
        sell_quantity = -(Decimal("100") + (i * 50)) * Decimal("0.3")  # Sell 30%
        sell_tx = SellTransactionFactory.create(
            investor=investor,
            broker=broker,
            security=security,
            date=sell_date,
            quantity=sell_quantity,
            price=Decimal("55") + (i * 2),  # Slightly higher sell price
        )
        transactions.append(sell_tx)

    return transactions


def create_dividend_schedule(investor, broker, security, num_dividends=4):
    """Create a schedule of dividend payments."""

    transactions = []
    base_date = date(2023, 3, 31)  # Typical dividend start date

    for i in range(num_dividends):
        dividend_date = base_date + timedelta(days=i * 90)  # Quarterly dividends
        dividend_tx = DividendTransactionFactory.create(
            investor=investor,
            broker=broker,
            security=security,
            date=dividend_date,
            cash_flow=Decimal("50") + (i * 5),  # Growing dividends
        )
        transactions.append(dividend_tx)

    return transactions


def create_dollar_cost_averaging(
    investor, broker, security, months=12, amount=Decimal("1000")
):
    """Create a dollar cost averaging strategy."""

    transactions = []
    base_date = date(2023, 1, 1)

    for i in range(months):
        investment_date = base_date + timedelta(days=i * 30)

        # Simulate varying prices
        price = Decimal("50") + (Decimal("10") * (i % 6) / 6)
        quantity = amount / price

        tx = BuyTransactionFactory.create(
            investor=investor,
            broker=broker,
            security=security,
            date=investment_date,
            quantity=quantity,
            price=price,
            cash_flow=-amount,
            commission=Decimal("5"),
        )
        transactions.append(tx)

    return transactions


def create_portfolio_transactions(investor, broker, assets, transactions_per_asset=5):
    """Create transactions for multiple assets."""

    all_transactions = []

    for asset in assets:
        # Mix of transaction types for each asset
        for i in range(transactions_per_asset):
            if i < transactions_per_asset * 0.6:  # 60% buys
                tx = BuyTransactionFactory.create(
                    investor=investor,
                    broker=broker,
                    security=asset,
                    date=date(2023, 1, 1) + timedelta(days=i * 45),
                )
            elif i < transactions_per_asset * 0.8:  # 20% sells
                tx = SellTransactionFactory.create(
                    investor=investor,
                    broker=broker,
                    security=asset,
                    date=date(2023, 1, 1) + timedelta(days=i * 45),
                )
            else:  # 20% dividends
                tx = DividendTransactionFactory.create(
                    investor=investor,
                    broker=broker,
                    security=asset,
                    date=date(2023, 1, 1) + timedelta(days=i * 45),
                )

            all_transactions.append(tx)

    return all_transactions


def create_tax_loss_harvesting(investor, broker, security):
    """Create transactions for tax loss harvesting scenario."""

    transactions = []

    # Initial purchase at high price
    initial_buy = BuyTransactionFactory.create(
        investor=investor,
        broker=broker,
        security=security,
        date=date(2023, 1, 15),
        quantity=Decimal("100"),
        price=Decimal("100"),
        cash_flow=Decimal("-10000"),
        commission=Decimal("10"),
    )
    transactions.append(initial_buy)

    # Price drops, sell for loss
    loss_sale = SellTransactionFactory.create(
        investor=investor,
        broker=broker,
        security=security,
        date=date(2023, 6, 15),
        quantity=Decimal("-100"),
        price=Decimal("70"),
        cash_flow=Decimal("6990"),
        commission=Decimal("10"),
    )
    transactions.append(loss_sale)

    # Wait 30 days (wash sale rule) and buy back
    repurchase = BuyTransactionFactory.create(
        investor=investor,
        broker=broker,
        security=security,
        date=date(2023, 7, 15),
        quantity=Decimal("100"),
        price=Decimal("72"),
        cash_flow=Decimal("-7200"),
        commission=Decimal("10"),
    )
    transactions.append(repurchase)

    return transactions
