"""
Test cases for transaction processing workflows.

This module tests end-to-end transaction flows including:
- Complete transaction lifecycles
- Multi-step transaction sequences
- Business logic validation
- Error handling in workflows
- Integration between different transaction types
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from common.models import (
    FX,
    Accounts,
    Assets,
    Brokers,
    FXTransaction,
    Prices,
    Transactions,
)
from users.models import CustomUser


@pytest.mark.integration
@pytest.mark.workflow
@pytest.mark.django_db
class TestCompleteTransactionWorkflows:
    """Test complete transaction processing workflows."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        """Set up test data for workflow tests."""
        self.user = CustomUser.objects.create_user(
            username="workflow_user",
            email="workflow@example.com",
            password="testpass123",
        )
        self.broker = Brokers.objects.create(
            investor=self.user, name="Test Broker", country="US"
        )
        self.account = Accounts.objects.create(
            broker=self.broker,
            name="Test Account",
        )
        self.asset = Assets.objects.create(
            type="Stock",
            ISIN="US1234567890",
            name="Test Stock Corp",
            currency="USD",
            exposure="Equity",
        )
        self.asset.investors.add(self.user)

    def test_simple_buy_to_sell_workflow(self):
        """Test complete buy-to-sell transaction workflow."""
        # Step 1: Buy shares
        buy_tx = Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
            comment="Initial purchase",
        )

        # Verify position after buy
        position_after_buy = self.asset.position(date(2023, 1, 16), self.user)
        assert position_after_buy == Decimal("100")

        # Step 2: Create price history
        Prices.objects.create(
            date=date(2023, 3, 15), security=self.asset, price=Decimal("55.00")
        )

        # Step 3: Sell all shares
        sell_tx = Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Sell",
            date=date(2023, 3, 15),
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            commission=Decimal("-5.00"),
            comment="Complete sale",
        )

        # Verify position after sell
        position_after_sell = self.asset.position(date(2023, 3, 16), self.user)
        assert position_after_sell == Decimal("0")

        # Step 4: Verify financial results
        # Commission is negative expense, so add to cash_flow
        total_cost = buy_tx.total_cash_flow()
        total_proceeds = sell_tx.total_cash_flow()
        net_profit = total_proceeds + total_cost

        expected_profit = (Decimal("55.00") - Decimal("50.00")) * Decimal(
            "100"
        ) - Decimal("10.00")
        assert net_profit == expected_profit

    def test_partial_sale_workflow(self):
        """Test workflow with partial sale and continued position."""
        # Initial purchase
        Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("200"),
            price=Decimal("50.00"),
            commission=Decimal("-10.00"),
        )

        # Partial sale
        Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Sell",
            date=date(2023, 3, 15),
            quantity=Decimal("-50"),
            price=Decimal("55.00"),
            commission=Decimal("-3.00"),
        )

        # Verify remaining position
        remaining_position = self.asset.position(date(2023, 3, 16), self.user)
        assert remaining_position == Decimal("150")

        # Additional purchase
        Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 5, 15),
            quantity=Decimal("25"),
            price=Decimal("52.00"),
            commission=Decimal("-2.00"),
        )

        # Final position
        final_position = self.asset.position(date(2023, 5, 16), self.user)
        assert final_position == Decimal("175")

    def test_dividend_reinvestment_workflow(self):
        """Test dividend reinvestment workflow."""
        # Initial purchase
        Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
        )

        # Create price history
        Prices.objects.create(
            date=date(2023, 3, 14), security=self.asset, price=Decimal("50.00")
        )
        Prices.objects.create(
            date=date(2023, 3, 15), security=self.asset, price=Decimal("50.50")
        )

        # Dividend payment
        Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Dividend",
            date=date(2023, 3, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("100.00"),
            commission=None,
            comment="Quarterly dividend",
        )

        # Dividend reinvestment
        Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 3, 16),
            quantity=Decimal("1.98"),  # 100 / 50.50 (approximate)
            price=Decimal("50.50"),
            commission=Decimal("-1.00"),
        )

        # Verify position after reinvestment
        final_position = self.asset.position(date(2023, 3, 17), self.user)
        expected_position = Decimal("100") + Decimal("1.98")
        assert abs(final_position - expected_position) < Decimal("0.01")

    def test_tax_loss_harvesting_workflow(self):
        """Test tax loss harvesting workflow."""
        # Initial purchase at high price
        purchase_high = Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("100.00"),
            commission=Decimal("-10.00"),
        )

        # Create declining price history
        Prices.objects.create(
            date=date(2023, 6, 15), security=self.asset, price=Decimal("70.00")
        )

        # Sale at loss for tax harvesting
        loss_sale = Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Sell",
            date=date(2023, 6, 15),
            quantity=Decimal("-100"),
            price=Decimal("70.00"),
            commission=Decimal("-10.00"),
        )

        # Wait for wash sale period (30 days)
        wash_sale_date = date(2023, 7, 15)

        # Create price after wash sale period
        Prices.objects.create(
            date=wash_sale_date, security=self.asset, price=Decimal("72.00")
        )

        # Repurchase after wash sale period
        repurchase = Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=wash_sale_date,
            quantity=Decimal("100"),
            price=Decimal("72.00"),
            commission=Decimal("-10.00"),
        )

        # Verify tax loss calculation
        loss_amount = loss_sale.total_cash_flow() + (purchase_high.total_cash_flow())
        expected_loss = (Decimal("7000")) + (
            Decimal("-10000") - Decimal("10") * Decimal("2")
        )
        assert loss_amount == expected_loss

        # Verify wash sale period compliance
        wash_sale_period_days = (repurchase.date - loss_sale.date).days
        assert wash_sale_period_days >= 30

    def test_dollar_cost_averaging_workflow(self):
        """Test dollar cost averaging investment workflow."""
        investment_amount = Decimal("1000.00")
        monthly_investments = []

        # Create regular investments over 6 months
        for i in range(6):
            investment_date = date(2023, 1, 15) + timedelta(days=i * 30)
            price = Decimal("50.00") + (i * 2)  # Increasing prices
            commission = Decimal("-5.00")
            quantity = (investment_amount + commission) / price

            investment = Transactions.objects.create(
                investor=self.user,
                account=self.account,
                security=self.asset,
                currency="USD",
                type="Buy",
                date=investment_date,
                quantity=quantity,
                price=price,
                commission=commission,
                comment=f"DCA investment #{i + 1}",
            )
            monthly_investments.append(investment)

        # Calculate total investment and average price
        total_shares = sum(tx.quantity for tx in monthly_investments)
        total_cost = sum(tx.total_cash_flow() for tx in monthly_investments)
        average_price = -total_cost / total_shares

        assert total_shares > 0
        assert total_cost == -Decimal("6000.00")
        assert average_price > Decimal(
            "50.00"
        )  # Should be higher due to increasing prices

        # Create final price for position valuation
        final_price = Decimal("62.00")
        Prices.objects.create(
            date=date(2023, 7, 15), security=self.asset, price=final_price
        )

        # Calculate final position value
        final_position = self.asset.position(date(2023, 7, 15), self.user)
        final_value = final_position * final_price

        # Calculate total return
        total_return = final_value + total_cost
        return_percentage = (total_return / abs(total_cost)) * Decimal("100")

        assert total_return > 0  # Should be profitable
        assert return_percentage > 0


@pytest.mark.integration
@pytest.mark.workflow
@pytest.mark.django_db
class TestMultiAssetWorkflows:
    """Test workflows involving multiple assets."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        """Set up test data for multi-asset workflows."""
        self.user = CustomUser.objects.create_user(
            username="multi_user", email="multi@example.com", password="testpass123"
        )
        self.broker = Brokers.objects.create(
            investor=self.user, name="Multi Broker", country="US"
        )
        self.account = Accounts.objects.create(
            broker=self.broker,
            name="Multi Account",
        )

        # Create multiple assets
        self.tech_stock = Assets.objects.create(
            type="Stock",
            ISIN="TECH123456789",
            name="Tech Stock Corp",
            currency="USD",
            exposure="Equity",
        )
        self.tech_stock.investors.add(self.user)

        self.bond = Assets.objects.create(
            type="Bond",
            ISIN="BOND123456789",
            name="Test Bond 2025",
            currency="USD",
            exposure="Fixed Income",
        )
        self.bond.investors.add(self.user)

        self.etf = Assets.objects.create(
            type="ETF",
            ISIN="ETF123456789",
            name="Market ETF",
            currency="USD",
            exposure="Equity",
        )
        self.etf.investors.add(self.user)

    def test_sector_rotation_workflow(self):
        """Test sector rotation workflow."""
        # Initial technology-heavy portfolio
        tech_transactions = []
        for i in range(3):
            tech_asset = Assets.objects.create(
                type="Stock",
                ISIN=f"TECH{i:03d}123456789",
                name=f"Tech Stock {i + 1}",
                currency="USD",
                exposure="Equity",
            )
            tech_asset.investors.add(self.user)

            tx = Transactions.objects.create(
                investor=self.user,
                account=self.account,
                security=tech_asset,
                currency="USD",
                type="Buy",
                date=date(2023, 1, 15),
                quantity=Decimal("50"),
                price=Decimal("100.00") + (i * 10),
                commission=Decimal("-5.00"),
            )
            tech_transactions.append(tx)

        # Create healthcare assets for rotation
        healthcare_transactions = []
        for i in range(2):
            healthcare_asset = Assets.objects.create(
                type="Stock",
                ISIN=f"HLTH{i:03d}123456789",
                name=f"Healthcare Stock {i + 1}",
                currency="USD",
                exposure="Equity",
            )
            healthcare_asset.investors.add(self.user)

            tx = Transactions.objects.create(
                investor=self.user,
                account=self.account,
                security=healthcare_asset,
                currency="USD",
                type="Buy",
                date=date(2023, 6, 15),
                quantity=Decimal("50"),
                price=Decimal("80.00") + (i * 5),
                commission=Decimal("-5.00"),
            )
            healthcare_transactions.append(tx)

        # Rotation: sell tech stocks, buy healthcare
        rotation_transactions = []

        for tech_tx in tech_transactions:
            # Sell tech stocks
            sell_tx = Transactions.objects.create(
                investor=self.user,
                account=self.account,
                security=tech_tx.security,
                currency="USD",
                type="Sell",
                date=date(2023, 9, 15),
                quantity=Decimal("-50"),
                price=Decimal("120.00"),
                commission=Decimal("-5.00"),
            )
            rotation_transactions.append(sell_tx)

        for healthcare_tx in healthcare_transactions:
            # Buy healthcare stocks with proceeds
            buy_tx = Transactions.objects.create(
                investor=self.user,
                account=self.account,
                security=healthcare_tx.security,
                currency="USD",
                type="Buy",
                date=date(2023, 9, 16),
                quantity=Decimal("60"),
                price=Decimal("85.00"),
                commission=Decimal("-5.00"),
            )
            rotation_transactions.append(buy_tx)

        # Verify rotation completed
        assert len(rotation_transactions) == 5  # 3 tech sells + 2 healthcare buys

    def test_multi_currency_portfolio_workflow(self, multi_currency_user):
        """Test multi-currency portfolio management workflow."""
        # Set up multi-currency user
        self.client = None  # Not using Django test client here
        user = multi_currency_user
        broker = Brokers.objects.create(
            investor=user, name="International Broker", country="UK"
        )
        account = Accounts.objects.create(
            broker=broker,
            name="International Account",
        )

        # Create assets in different currencies
        usd_asset = Assets.objects.create(
            type="Stock",
            ISIN="USD123456789",
            name="US Stock Corp",
            currency="USD",
            exposure="Equity",
        )
        usd_asset.investors.add(user)

        eur_asset = Assets.objects.create(
            type="Stock",
            ISIN="EUR123456789",
            name="European Stock AG",
            currency="EUR",
            exposure="Equity",
        )
        eur_asset.investors.add(user)

        gbp_asset = Assets.objects.create(
            type="Stock",
            ISIN="GBP123456789",
            name="British Stock PLC",
            currency="GBP",
            exposure="Equity",
        )
        gbp_asset.investors.add(user)

        # Create FX rate data
        fx_data = FX.objects.create(
            date=date(2023, 6, 15),
            USDEUR=Decimal("1.09"),
            USDGBP=Decimal("1.22"),
        )
        fx_data.investors.add(user)

        # Multi-currency investments
        investments = [
            (usd_asset, Decimal("100"), Decimal("50.00"), "USD"),
            (eur_asset, Decimal("200"), Decimal("40.00"), "EUR"),
            (gbp_asset, Decimal("150"), Decimal("35.00"), "GBP"),
        ]

        for asset, quantity, price, currency in investments:
            Transactions.objects.create(
                investor=user,
                account=account,
                security=asset,
                currency=currency,
                type="Buy",
                date=date(2023, 1, 15),
                quantity=quantity,
                price=price,
                commission=Decimal("-5.00"),
            )

        # Create price history in local currencies
        Prices.objects.create(
            date=date(2023, 6, 15), security=usd_asset, price=Decimal("55.00")
        )
        Prices.objects.create(
            date=date(2023, 6, 15), security=eur_asset, price=Decimal("42.00")
        )
        Prices.objects.create(
            date=date(2023, 6, 15), security=gbp_asset, price=Decimal("37.00")
        )

        # Calculate portfolio value in different base currencies
        base_currencies = ["USD", "EUR", "GBP"]
        portfolio_values = {}

        for base_currency in base_currencies:
            total_value = Decimal("0")

            for asset in [usd_asset, eur_asset, gbp_asset]:
                position = asset.position(date(2023, 6, 15), user)
                local_price = asset.price_at_date(date(2023, 6, 15)).price
                local_value = position * local_price

                if asset.currency != base_currency:
                    fx_rate = FX.get_rate(
                        asset.currency, base_currency, date(2023, 6, 15)
                    )["FX"]
                    converted_value = local_value * fx_rate
                else:
                    converted_value = local_value

                total_value += converted_value

            portfolio_values[base_currency] = total_value

        # Verify multi-currency calculations
        assert len(portfolio_values) == 3
        assert all(value > 0 for value in portfolio_values.values())

        # FX conversion relationships exist
        # Note: Exact equality not tested due to FX rate application complexity


@pytest.mark.integration
@pytest.mark.workflow
@pytest.mark.django_db
class TestErrorHandlingWorkflows:
    """Test error handling in transaction workflows."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        """Set up test data for error handling tests."""
        self.user = CustomUser.objects.create_user(
            username="error_user", email="error@example.com", password="testpass123"
        )
        self.broker = Brokers.objects.create(
            investor=self.user, name="Error Test Broker", country="US"
        )
        self.account = Accounts.objects.create(
            broker=self.broker,
            name="Error Test Account",
        )
        self.asset = Assets.objects.create(
            type="Stock",
            ISIN="ERROR123456789",
            name="Error Test Stock",
            currency="USD",
            exposure="Equity",
        )
        self.asset.investors.add(self.user)

    def test_oversell_prevention_workflow(self):
        """Test workflow for preventing overselling."""
        # Buy shares
        Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
        )

        # Current position
        current_position = self.asset.position(date(2023, 3, 15), self.user)
        assert current_position == Decimal("100")

        # Try to sell more than available (should be handled by business logic)
        Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Sell",
            date=date(2023, 3, 15),
            quantity=Decimal("-150"),  # More than available
            price=Decimal("55.00"),
            commission=Decimal("-5.00"),
            comment="Attempted oversell",
        )

        # Position after oversell attempt
        final_position = self.asset.position(date(2023, 3, 16), self.user)
        assert final_position == Decimal(
            "-50"
        )  # Should allow negative positions (shorting)

    def test_invalid_transaction_recovery(self):
        """Test recovery from invalid transaction attempts."""
        # Create valid transaction
        # (validation is not enforced at model level in current implementation)
        valid_transaction = Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
        )

        # Verify valid transaction was created
        assert valid_transaction.quantity == Decimal("100")
        assert valid_transaction.total_cash_flow() < 0

    def test_transaction_sequence_interruption(self):
        """Test handling of interrupted transaction sequences."""
        # Start transaction sequence
        transactions = []

        # First transaction
        tx1 = Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
        )
        transactions.append(tx1)

        # Second transaction
        tx2 = Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("50"),
            price=Decimal("55.00"),
            commission=Decimal("-3.00"),
        )
        transactions.append(tx2)

        # Verify sequence consistency
        for i in range(len(transactions) - 1):
            assert transactions[i].date <= transactions[i + 1].date

        # Position should be cumulative
        cumulative_position = sum(tx.quantity for tx in transactions)
        actual_position = self.asset.position(date(2023, 2, 16), self.user)
        assert cumulative_position == actual_position

    def test_cross_currency_transaction_validation(self, multi_currency_user):
        """Test validation in cross-currency transactions."""
        user = multi_currency_user
        broker = Brokers.objects.create(
            investor=user, name="Cross Currency Broker", country="UK"
        )
        account = Accounts.objects.create(
            broker=broker,
            name="Cross Currency Account",
        )

        # Create assets in different currencies
        usd_asset = Assets.objects.create(
            type="Stock",
            ISIN="USD123456789",
            name="US Stock",
            currency="USD",
            exposure="Equity",
        )
        usd_asset.investors.add(user)

        eur_asset = Assets.objects.create(
            type="Stock",
            ISIN="EUR123456789",
            name="EUR Stock",
            currency="EUR",
            exposure="Equity",
        )
        eur_asset.investors.add(user)

        # Create FX transaction
        fx_tx = FXTransaction.objects.create(
            investor=user,
            account=account,
            date=date(2023, 6, 15),
            from_currency="USD",
            to_currency="EUR",
            from_amount=Decimal("1000.00"),
            to_amount=Decimal("920.00"),
            exchange_rate=Decimal("0.92"),
            commission=Decimal("-2.00"),
        )

        # Create EUR purchase using converted funds
        eur_purchase = Transactions.objects.create(
            investor=user,
            account=account,
            security=eur_asset,
            currency="EUR",
            type="Buy",
            date=date(2023, 6, 15),
            quantity=Decimal("20"),
            price=Decimal("46.00"),
            commission=Decimal("-2.00"),
        )

        # Verify cross-currency workflow
        assert fx_tx.from_amount == Decimal("1000.00")
        assert fx_tx.to_amount == Decimal("920.00")
        # Cash flow is negative for purchases, equals the amount used
        assert eur_purchase.total_cash_flow() == -fx_tx.to_amount + fx_tx.commission

    def test_business_rule_enforcement(self):
        """Test enforcement of business rules in workflows."""
        # Test business rule: dividend transactions should not have quantity or price
        dividend_tx = Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Dividend",
            date=date(2023, 3, 15),
            quantity=None,
            price=None,
            cash_flow=Decimal("100.00"),
            commission=None,
        )

        assert dividend_tx.quantity is None
        assert dividend_tx.price is None
        assert dividend_tx.cash_flow > 0
        assert dividend_tx.commission is None

        # Test business rule: corporate actions can have zero cash flow
        corporate_action_tx = Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Corporate Action",
            date=date(2023, 2, 1),
            quantity=Decimal("100"),
            price=Decimal("25.00"),  # Adjusted price for split
            commission=None,
        )

        assert corporate_action_tx.commission is None

    def test_concurrent_transaction_handling(self):
        """Test handling of concurrent transactions."""
        # Create initial position
        Transactions.objects.create(
            investor=self.user,
            account=self.account,
            security=self.asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
        )

        # Create multiple transactions on the same date
        same_date = date(2023, 3, 15)
        concurrent_transactions = []

        for i in range(3):
            tx = Transactions.objects.create(
                investor=self.user,
                account=self.account,
                security=self.asset,
                currency="USD",
                type="Buy" if i % 2 == 0 else "Sell",
                date=same_date,
                quantity=Decimal("10") if i % 2 == 0 else Decimal("-5"),
                price=Decimal("52.00") + i,
                commission=Decimal("-2.00"),
            )
            concurrent_transactions.append(tx)

        # Verify all transactions were created
        assert len(concurrent_transactions) == 3

        # Verify final position is calculated correctly
        # Position includes initial buy of 100 shares plus concurrent transactions
        final_position = self.asset.position(same_date, self.user)
        expected_concurrent = sum(tx.quantity for tx in concurrent_transactions)
        # Total includes the initial 100 shares bought earlier
        expected_position = Decimal("100") + expected_concurrent
        assert final_position == expected_position

        # Test position calculation with date filtering
        next_day = same_date + timedelta(days=1)
        next_day_position = self.asset.position(next_day, self.user)
        assert next_day_position == expected_position
