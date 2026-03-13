"""
Test cases for Transaction model methods and processing.

This module tests the Transaction model functionality including:
- Transaction creation and validation
- Cash flow calculations
- Transaction type handling
- Transaction processing workflows
- Multi-currency transaction handling
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from common.models import Transactions


@pytest.mark.unit
class TestTransactionCreation:
    """Test transaction creation and basic functionality."""

    def test_transaction_creation_buy(self, user, account, asset):
        """Test creating a buy transaction."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
            comment="Initial purchase",
        )

        assert transaction.investor == user
        assert transaction.account == account
        assert transaction.security == asset
        assert transaction.type == "Buy"
        assert transaction.quantity == Decimal("100")
        assert transaction.price == Decimal("50.00")
        assert transaction.commission == Decimal("-5.00")
        assert transaction.comment == "Initial purchase"

    def test_transaction_creation_sell(self, user, account, asset):
        """Test creating a sell transaction."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 6, 15),
            quantity=Decimal("-50"),
            price=Decimal("55.00"),
            commission=Decimal("-3.00"),
            comment="Partial sale",
        )

        assert transaction.type == "Sell"
        assert transaction.quantity == Decimal("-50")
        assert transaction.commission == Decimal("-3.00")

    def test_transaction_creation_dividend(self, user, account, asset):
        """Test creating a dividend transaction."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Dividend",
            date=date(2023, 3, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("200.00"),
            commission=None,
            comment="Quarterly dividend",
        )

        assert transaction.type == "Dividend"
        assert transaction.quantity is None
        assert transaction.price is None
        assert transaction.cash_flow == Decimal("200.00")
        assert transaction.commission is None

    def test_transaction_creation_interest(self, user, account, asset):
        """Test creating an interest transaction."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Interest",
            date=date(2023, 6, 30),
            quantity=None,
            price=None,
            cash_flow=Decimal("75.00"),
            commission=None,
            comment="Bond interest payment",
        )

        assert transaction.type == "Interest"
        assert transaction.cash_flow == Decimal("75.00")

    def test_transaction_creation_corporate_action(self, user, account, asset):
        """Test creating a corporate action transaction."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Corporate Action",
            date=date(2023, 2, 1),
            quantity=Decimal("100"),
            price=Decimal("25.00"),
            cash_flow=Decimal("0.00"),
            commission=None,
            comment="2:1 stock split",
        )

        assert transaction.type == "Corporate Action"
        assert transaction.cash_flow == Decimal("0.00")
        assert transaction.commission is None

    def test_transaction_string_representation(self, user, account, asset):
        """Test transaction string representation."""
        transaction = Transactions.objects.create(
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

        expected = f"{transaction.type} || {transaction.date}"
        assert str(transaction) == expected

    def test_transaction_currency_choices(self, user, account, asset):
        """Test transaction with different currencies."""
        currencies = ["USD", "EUR", "GBP", "CHF"]

        for currency in currencies:
            transaction = Transactions.objects.create(
                investor=user,
                account=account,
                security=asset,
                currency=currency,
                type="Buy",
                date=date(2023, 1, 15),
                quantity=Decimal("100"),
                price=Decimal("50.00"),
                commission=Decimal("-5.00"),
            )

            assert transaction.currency == currency


@pytest.mark.unit
class TestTransactionValidation:
    """Test transaction validation and constraints."""

    def test_transaction_quantity_validation_buy(self, user, account, asset):
        """Test quantity validation for buy transactions."""
        # Buy transactions should have positive quantity
        transaction = Transactions.objects.create(
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

        assert transaction.quantity > 0

    def test_transaction_quantity_validation_sell(self, user, account, asset):
        """Test quantity validation for sell transactions."""
        # Sell transactions should have negative quantity
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 1, 15),
            quantity=Decimal("-100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
        )

        assert transaction.quantity < 0

    def test_transaction_quantity_validation_non_trading(self, user, account, asset):
        """Test quantity validation for non-trading transactions."""
        # Dividend, Interest, Corporate Action should have null quantity
        for tx_type in ["Dividend", "Interest"]:
            transaction = Transactions.objects.create(
                investor=user,
                account=account,
                security=asset,
                currency="USD",
                type=tx_type,
                date=date(2023, 1, 15),
                quantity=None,
                price=None,
                cash_flow=Decimal("100.00"),
                commission=None,
            )

            assert transaction.quantity is None
            assert transaction.price is None

    def test_transaction_cash_flow_direction(self, user, account, asset):
        """Test cash flow direction validation."""
        # Buy transactions should have negative cash flow (outflow)
        buy_tx = Transactions.objects.create(
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
        assert buy_tx.total_cash_flow() < 0

        # Sell transactions should have positive cash flow (inflow)
        sell_tx = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 2, 15),
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            commission=Decimal("-5.00"),
        )
        assert sell_tx.total_cash_flow() > 0

        # Dividend transactions should have positive cash flow
        dividend_tx = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Dividend",
            date=date(2023, 3, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("200.00"),
            commission=None,
        )
        assert dividend_tx.total_cash_flow() > 0

    def test_transaction_commission_validation(self, user, account, asset):
        """Test commission validation."""
        # Trading transactions can have commission (negative for outflow)
        trading_tx = Transactions.objects.create(
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
        # Commission should be negative for outflow
        assert trading_tx.commission < 0

        # Non-trading transactions should have null commission
        non_trading_tx = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Dividend",
            date=date(2023, 3, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("200.00"),
            commission=None,
        )
        assert non_trading_tx.commission is None

    def test_transaction_date_validation(self, user, account, asset):
        """Test transaction date validation."""
        future_date = date.today() + timedelta(days=30)
        past_date = date.today() - timedelta(days=30)

        # Should allow past dates
        past_transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=past_date,
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
        )
        # Model uses NaiveDateTimeField, so date is stored as datetime
        assert past_transaction.date.date() == past_date

        # Should allow future dates (for planned transactions)
        future_transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=future_date,
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
        )
        # Model uses NaiveDateTimeField, so date is stored as datetime
        assert future_transaction.date.date() == future_date


@pytest.mark.unit
class TestTransactionCashFlowCalculations:
    """Test transaction cash flow calculations."""

    def test_buy_transaction_cash_flow_calculation(self, user, account, asset):
        """Test cash flow calculation for buy transactions."""
        quantity = Decimal("100")
        price = Decimal("50.00")
        commission = Decimal("-5.00")  # Negative for outflow

        # Expected: -(100 * 50) - 5 = -5005
        expected_cash_flow = -(quantity * price) + commission  # commission is already negative

        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=quantity,
            price=price,
            commission=commission,
        )

        # Use the calculation method instead of accessing the field directly
        assert transaction.total_cash_flow() == expected_cash_flow

    def test_sell_transaction_cash_flow_calculation(self, user, account, asset):
        """Test cash flow calculation for sell transactions."""
        quantity = Decimal("-100")  # Negative for sell
        price = Decimal("55.00")
        commission = Decimal("-5.00")  # Negative for outflow

        # Expected: (100 * 55) - 5 = 5495
        expected_cash_flow = (abs(quantity) * price) + commission  # commission is already negative

        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 1, 15),
            quantity=quantity,
            price=price,
            commission=commission,
        )

        # Use the calculation method instead of manual calculation
        assert transaction.total_cash_flow() == expected_cash_flow

    def test_zero_commission_transaction(self, user, account, asset):
        """Test transaction with zero commission."""
        quantity = Decimal("100")
        price = Decimal("50.00")
        commission = Decimal("0.00")

        expected_cash_flow = -(quantity * price)

        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=quantity,
            price=price,
            commission=commission,
        )

        # Use the calculation method instead of manual calculation
        assert transaction.total_cash_flow() == expected_cash_flow
        assert transaction.commission == Decimal("0.00")

    def test_high_value_transaction(self, user, account, asset):
        """Test cash flow calculation for high-value transactions."""
        quantity = Decimal("10000")
        price = Decimal("250.00")
        commission = Decimal("-100.00")  # Negative for outflow

        expected_cash_flow = -(quantity * price) + commission  # commission is already negative

        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=quantity,
            price=price,
            commission=commission,
        )

        # Use the calculation method instead of manual calculation
        assert transaction.total_cash_flow() == expected_cash_flow
        assert transaction.total_cash_flow() < -Decimal("1000000")  # Should be over $1M

    def test_fractional_shares_transaction(self, user, account, asset):
        """Test cash flow calculation for fractional shares."""
        quantity = Decimal("0.123456")
        price = Decimal("1234.56")
        commission = Decimal("-1.50")  # Negative for outflow

        expected_cash_flow = -(quantity * price) + commission  # commission is already negative

        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=quantity,
            price=price,
            commission=commission,
        )

        # Use the calculation method and maintain high precision (allow for model rounding)
        assert abs(transaction.total_cash_flow() - expected_cash_flow) < Decimal("0.01")


@pytest.mark.unit
class TestTransactionProcessing:
    """Test transaction processing workflows."""

    def test_transaction_sequence_buy_sell(self, user, account, asset):
        """Test processing buy followed by sell transaction sequence."""
        # Buy transaction
        buy_tx = Transactions.objects.create(
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

        # Sell transaction
        sell_tx = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 6, 15),
            quantity=Decimal("-100"),
            price=Decimal("60.00"),
            commission=Decimal("-5.00"),
        )

        # Verify sequence
        assert buy_tx.date < sell_tx.date
        assert buy_tx.quantity == -sell_tx.quantity  # Same quantity, opposite signs

        # Calculate profit/loss
        profit = (sell_tx.price * sell_tx.quantity + sell_tx.commission) + (
            buy_tx.price * buy_tx.quantity + buy_tx.commission
        )
        expected_profit = (Decimal("60.00") * Decimal("-100") + Decimal("-5.00")) + (
            Decimal("50.00") * Decimal("100") + Decimal("-5.00")
        )
        assert profit == expected_profit

    def test_transaction_sequence_multiple_buys(self, user, account, asset):
        """Test processing multiple buy transactions."""
        transactions = []

        # Create multiple buy transactions
        for i in range(5):
            tx = Transactions.objects.create(
                investor=user,
                account=account,
                security=asset,
                currency="USD",
                type="Buy",
                date=date(2023, 1, 1) + timedelta(days=i * 30),
                quantity=Decimal("100"),
                price=Decimal("50.00") + (i * 2),
                commission=Decimal("-5.00"),
            )
            transactions.append(tx)

        # Verify chronological order
        for i in range(len(transactions) - 1):
            assert transactions[i].date < transactions[i + 1].date
            assert transactions[i].price < transactions[i + 1].price

        # Calculate total position and cost using calculation method
        total_quantity = sum(tx.quantity for tx in transactions)
        total_cost = sum(tx.total_cash_flow() for tx in transactions)
        total_commission = sum(tx.commission for tx in transactions)

        assert total_quantity == Decimal("500")
        assert total_cost < -Decimal("25000")  # Should be negative (outflow)
        assert total_commission == Decimal("-25.00")

    def test_transaction_sequence_dividend_reinvestment(self, user, account, asset):
        """Test dividend reinvestment transaction sequence."""
        # Initial purchase
        initial_buy = Transactions.objects.create(
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

        # Dividend payment
        dividend = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Dividend",
            date=date(2023, 3, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("200.00"),
            commission=None,
        )

        # Dividend reinvestment
        reinvestment = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 3, 16),
            quantity=Decimal("3.96"),  # 200 / 50.5 (approximate)
            price=Decimal("50.50"),
            commission=Decimal("-0.50"),
        )

        # Verify sequence
        assert initial_buy.date < dividend.date < reinvestment.date
        # Use calculation method for reinvestment cash flow (may have small rounding difference)
        total_reinvestment = dividend.total_cash_flow() + reinvestment.total_cash_flow()
        assert abs(total_reinvestment) < Decimal("1.00")  # Allow small difference due to commission

    def test_transaction_sequence_tax_loss_harvesting(self, user, account, asset):
        """Test tax loss harvesting transaction sequence."""
        # Initial purchase at high price
        purchase = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("100.00"),
            commission=Decimal("-10.00"),
        )

        # Sale at loss for tax harvesting
        loss_sale = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 6, 15),
            quantity=Decimal("-100"),
            price=Decimal("70.00"),
            commission=Decimal("-10.00"),
        )

        # Repurchase after wash sale period
        repurchase = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 7, 15),  # After 30 days
            quantity=Decimal("100"),
            price=Decimal("72.00"),
            commission=Decimal("-10.00"),
        )

        # Verify wash sale rule timing
        wash_sale_period = repurchase.date - loss_sale.date
        assert wash_sale_period.days >= 30

        # Calculate realized loss using calculation method
        loss = loss_sale.total_cash_flow() + purchase.total_cash_flow()
        assert abs(loss) == Decimal("3020.00")  # Exact calculated loss

    def test_transaction_sequence_dollar_cost_averaging(self, user, account, asset):
        """Test dollar cost averaging transaction sequence."""
        transactions = []
        investment_amount = Decimal("1000.00")

        # Create regular investments over 6 months
        for i in range(6):
            investment_date = date(2023, 1, 15) + timedelta(days=i * 30)
            price = Decimal("50.00") + (i * 2)  # Increasing prices
            quantity = (investment_amount - Decimal("5.00")) / price  # Subtract commission

            tx = Transactions.objects.create(
                investor=user,
                account=account,
                security=asset,
                currency="USD",
                type="Buy",
                date=investment_date,
                quantity=quantity,
                price=price,
                commission=Decimal("-5.00"),
            )
            transactions.append(tx)

        # Calculate total investment and average price
        total_shares = sum(tx.quantity for tx in transactions)
        total_invested = sum(abs(tx.total_cash_flow()) for tx in transactions)
        average_price = total_invested / total_shares

        assert total_shares > 0
        assert total_invested == Decimal("6000.00")
        assert average_price > Decimal("50.00")  # Should be higher than initial price

    def test_transaction_sequence_corporate_action_split(self, user, account, asset):
        """Test corporate action (stock split) transaction sequence."""
        # Pre-split purchase
        pre_split = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("100.00"),
            commission=Decimal("-10.00"),
        )

        # Corporate action (2:1 split)
        corporate_action = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Corporate Action",
            date=date(2023, 2, 1),
            quantity=Decimal("100"),  # Additional shares
            price=Decimal("50.00"),  # Adjusted price
            commission=None,
        )

        # Post-split sale
        post_split = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 3, 15),
            quantity=Decimal("-150"),  # Sell 150 of 200 shares
            price=Decimal("55.00"),
            commission=Decimal("-8.00"),
        )

        # Verify split effect
        assert pre_split.quantity == Decimal("100")
        assert corporate_action.quantity == Decimal("100")
        assert post_split.quantity == Decimal("-150")

        # Position after split: 200 shares, sold 150 = 50 remaining


@pytest.mark.unit
class TestTransactionEdgeCases:
    """Test edge cases in transaction processing."""

    def test_zero_quantity_transaction(self, user, account, asset):
        """Test transaction with zero quantity."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Corporate Action",
            date=date(2023, 1, 15),
            quantity=Decimal("0"),
            price=Decimal("50.00"),
            commission=None,
        )

        assert transaction.quantity == Decimal("0")

    def test_very_small_transaction(self, user, account, asset):
        """Test transaction with very small values."""
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("0.000001"),
            price=Decimal("1000000.00"),
            commission=Decimal("-0.01"),
        )

        assert transaction.quantity == Decimal("0.000001")
        assert transaction.price == Decimal("1000000.00")
        # Use the calculation method instead of manual calculation
        assert transaction.total_cash_flow() == Decimal("-1.01")

    def test_negative_price_transaction(self, user, account, asset):
        """Test transaction with negative price (should be avoided in practice)."""
        # This might occur in certain corporate actions or adjustments
        transaction = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Corporate Action",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("-10.00"),
            commission=None,
        )

        assert transaction.price == Decimal("-10.00")

    def test_transaction_same_day_multiple(self, user, account, asset):
        """Test multiple transactions on the same day."""
        same_date = date(2023, 1, 15)

        tx1 = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=same_date,
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
        )

        tx2 = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=same_date,
            quantity=Decimal("50"),
            price=Decimal("51.00"),
            commission=Decimal("-3.00"),
        )

        # Model uses NaiveDateTimeField, so date is stored as datetime
        assert tx1.date.date() == tx2.date.date() == same_date
        assert tx1.id != tx2.id  # Should be different transactions

    def test_transaction_extreme_commission(self, user, account, asset):
        """Test transaction with extreme commission values."""
        # Very high commission
        high_commission_tx = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-1000.00"),
        )

        # Very low commission
        low_commission_tx = Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 2, 15),
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            commission=Decimal("-0.01"),
        )

        assert high_commission_tx.commission == Decimal("-1000.00")
        assert low_commission_tx.commission == Decimal("-0.01")
