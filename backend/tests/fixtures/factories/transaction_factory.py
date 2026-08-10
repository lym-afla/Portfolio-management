"""
Factory classes for creating test transactions.

Provides realistic transaction data for various testing scenarios.
"""

from datetime import date, timedelta
from decimal import Decimal

import factory
from factory import fuzzy

from common.models import Accounts, Assets, Transactions
from users.models import CustomUser


class TransactionFactory(factory.django.DjangoModelFactory):
    """Factory for creating Transactions with realistic data."""

    class Meta:
        """Meta class for TransactionFactory."""

        model = Transactions

    currency = fuzzy.FuzzyChoice(["USD", "EUR", "GBP", "CHF"])
    type = fuzzy.FuzzyChoice(["Buy", "Sell", "Dividend", "Interest", "Corporate Action"])
    date = fuzzy.FuzzyDate(date(2020, 1, 1), date.today())
    comment = factory.Faker("text", max_nb_chars=200)

    quantity = fuzzy.FuzzyDecimal(-1000, 1000, 6)
    price = fuzzy.FuzzyDecimal(1, 1000, 6)
    cash_flow = None  # Will be None for Buy/Sell, generated for Dividend/Interest
    commission = fuzzy.FuzzyDecimal(0, -100, -2)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override create to handle required relationships."""
        investor = kwargs.pop("investor", None)
        account = kwargs.pop("account", None)
        security = kwargs.pop("security", None)

        if not all([investor, account, security]):
            raise ValueError("TransactionFactory requires investor, account, and security")

        return model_class.objects.create(
            investor=investor, account=account, security=security, **kwargs
        )


class BuyTransactionFactory(TransactionFactory):
    """Factory for creating buy transactions."""

    type = "Buy"
    cash_flow = None  # Auto-calculated from price × quantity
    quantity = fuzzy.FuzzyDecimal(1, 1000, 6)  # Positive quantity for buys


class SellTransactionFactory(TransactionFactory):
    """Factory for creating sell transactions."""

    type = "Sell"
    cash_flow = None  # Auto-calculated from price × quantity
    quantity = fuzzy.FuzzyDecimal(-1000, -1, 6)  # Negative quantity for sells


class DividendTransactionFactory(TransactionFactory):
    """Factory for creating dividend transactions."""

    type = "Dividend"
    quantity = None
    price = None
    commission = None
    cash_flow = fuzzy.FuzzyDecimal(10, 10000, 2)  # Positive cash flow for dividends
    comment = factory.Faker("sentence", nb_words=4)


class LargeBuyTransactionFactory(BuyTransactionFactory):
    """Factory for creating large buy transactions."""

    quantity = fuzzy.FuzzyDecimal(1000, 100000, 6)  # Large quantity for institutional trades
    price = fuzzy.FuzzyDecimal(1, 100, 6)  # Lower price for large quantities


class SmallBuyTransactionFactory(BuyTransactionFactory):
    """Factory for creating small buy transactions."""

    quantity = fuzzy.FuzzyDecimal(1, 100, 6)  # Small quantity for retail trades


# Batch creation utilities
def create_buy_sell_sequence(
    investor: CustomUser, account: Accounts, security: Assets, num_pairs=3
) -> list[Transactions]:
    """Create a sequence of buy-sell transaction pairs."""
    transactions = []
    base_date = date(2023, 1, 1)

    for i in range(num_pairs):
        # Buy transaction
        buy_date = base_date + timedelta(days=i * 30)
        buy_tx = BuyTransactionFactory.create(
            investor=investor,
            account=account,
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
            account=account,
            security=security,
            date=sell_date,
            quantity=sell_quantity,
            price=Decimal("55") + (i * 2),  # Slightly higher sell price
        )
        transactions.append(sell_tx)

    return transactions


def create_dividend_schedule(investor, account, security, num_dividends=4) -> list[Transactions]:
    """Create a schedule of dividend payments."""
    transactions = []
    base_date = date(2023, 3, 31)  # Typical dividend start date

    for i in range(num_dividends):
        dividend_date = base_date + timedelta(days=i * 90)  # Quarterly dividends
        dividend_tx = DividendTransactionFactory.create(
            investor=investor,
            account=account,
            security=security,
            date=dividend_date,
            cash_flow=Decimal("50") + (i * 5),  # Growing dividends
        )
        transactions.append(dividend_tx)

    return transactions


def create_dollar_cost_averaging(
    investor, account, security, months=12, amount=None
) -> list[Transactions]:
    """Create a dollar cost averaging strategy."""
    if amount is None:
        amount = Decimal("1000")

    transactions = []
    base_date = date(2023, 1, 1)

    for i in range(months):
        investment_date = base_date + timedelta(days=i * 30)

        # Simulate varying prices
        price = Decimal("50") + (Decimal("10") * (i % 6) / 6)
        quantity = amount / price

        tx = BuyTransactionFactory.create(
            investor=investor,
            account=account,
            security=security,
            date=investment_date,
            quantity=quantity,
            price=price,
            commission=Decimal("-5"),
        )
        transactions.append(tx)

    return transactions


def create_portfolio_transactions(
    investor, account, assets, transactions_per_asset=5
) -> list[Transactions]:
    """Create transactions for multiple assets."""
    all_transactions = []

    for asset in assets:
        # Mix of transaction types for each asset
        for i in range(transactions_per_asset):
            if i < transactions_per_asset * 0.6:  # 60% buys
                tx = BuyTransactionFactory.create(
                    investor=investor,
                    account=account,
                    security=asset,
                    date=date(2023, 1, 1) + timedelta(days=i * 45),
                )
            elif i < transactions_per_asset * 0.8:  # 20% sells
                tx = SellTransactionFactory.create(
                    investor=investor,
                    account=account,
                    security=asset,
                    date=date(2023, 1, 1) + timedelta(days=i * 45),
                )
            else:  # 20% dividends
                tx = DividendTransactionFactory.create(
                    investor=investor,
                    account=account,
                    security=asset,
                    date=date(2023, 1, 1) + timedelta(days=i * 45),
                )

            all_transactions.append(tx)

    return all_transactions


def create_tax_loss_harvesting(investor, account, security) -> list[Transactions]:
    """Create transactions for tax loss harvesting scenario."""
    transactions = []

    # Initial purchase at high price
    initial_buy = BuyTransactionFactory.create(
        investor=investor,
        account=account,
        security=security,
        date=date(2023, 1, 15),
        quantity=Decimal("100"),
        price=Decimal("100"),
        commission=Decimal("-10"),
    )
    transactions.append(initial_buy)

    # Price drops, sell for loss
    loss_sale = SellTransactionFactory.create(
        investor=investor,
        account=account,
        security=security,
        date=date(2023, 6, 15),
        quantity=Decimal("-100"),
        price=Decimal("70"),
        commission=Decimal("-10"),
    )
    transactions.append(loss_sale)

    # Wait 30 days (wash sale rule) and buy back
    repurchase = BuyTransactionFactory.create(
        investor=investor,
        account=account,
        security=security,
        date=date(2023, 7, 15),
        quantity=Decimal("100"),
        price=Decimal("72"),
        commission=Decimal("-10"),
    )
    transactions.append(repurchase)

    return transactions
