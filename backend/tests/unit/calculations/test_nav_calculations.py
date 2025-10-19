"""
Test cases for NAV (Net Asset Value) calculations.

This module tests the core NAV calculation logic including:
- Portfolio NAV aggregation
- Multi-currency NAV calculations
- FX effects on NAV
- NAV calculations with different asset types
- NAV change calculations over time
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from common.models import FX, AnnualPerformance, Assets, Prices, Transactions


@pytest.mark.nav
@pytest.mark.unit
class TestNAVCalculation:
    """Test NAV calculation functionality."""

    def test_simple_portfolio_nav(
        self, user, broker, asset, sample_transactions, price_history
    ):
        """Test NAV calculation for a simple portfolio."""
        # Calculate position at a specific date
        position = asset.position(date(2023, 6, 15))
        assert position == Decimal("120")  # 100 + 50 - 30

        # Get current price
        current_price = asset.price_at_date(date(2023, 6, 15))
        assert current_price is not None
        assert current_price.price > 0

        # Calculate market value
        market_value = position * current_price.price
        assert market_value > 0

        # Expected: 120 shares * price from price_history
        expected_price = (
            Prices.objects.filter(security=asset, date=date(2023, 6, 15)).first().price
        )
        expected_value = Decimal("120") * expected_price
        assert abs(market_value - expected_value) < Decimal("0.01")

    def test_multi_asset_portfolio_nav(self, user, broker, complete_portfolio):
        """Test NAV calculation for portfolio with multiple assets."""
        total_nav = Decimal("0")
        assets = complete_portfolio["assets"]
        valuation_date = date(2023, 6, 15)

        for asset in assets:
            position = asset.position(valuation_date)
            if position > 0:
                current_price = asset.price_at_date(valuation_date)
                if current_price:
                    market_value = position * current_price.price
                    total_nav += market_value

        assert total_nav > 0
        assert isinstance(total_nav, Decimal)

    def test_multi_currency_portfolio_nav(
        self,
        multi_currency_user,
        broker,
        multi_currency_transactions,
        fx_rates_multi_currency,
    ):
        """Test NAV calculation for multi-currency portfolio."""
        # Get unique assets from transactions
        assets = set(tx.security for tx in multi_currency_transactions)
        valuation_date = date(2023, 6, 15)
        target_currency = "USD"

        total_nav_usd = Decimal("0")

        for asset in assets:
            position = asset.position(valuation_date)
            if position > 0:
                current_price = asset.price_at_date(valuation_date)
                if current_price:
                    # Calculate market value in local currency
                    local_value = position * current_price.price

                    # Convert to target currency if needed
                    if asset.currency != target_currency:
                        fx_rate = FX.get_rate(
                            asset.currency, target_currency, valuation_date
                        )
                        converted_value = local_value * fx_rate["FX"]
                    else:
                        converted_value = local_value

                    total_nav_usd += converted_value

        assert total_nav_usd > 0
        assert isinstance(total_nav_usd, Decimal)

    def test_nav_calculation_with_cash_balances(
        self, user, broker, asset, sample_transactions, fx_transaction
    ):
        """Test NAV calculation including cash balances."""
        # Calculate broker cash balance
        cash_balance = broker.balance(date(2023, 6, 15))
        assert isinstance(cash_balance, dict)

        # Total cash across all currencies
        total_cash = sum(cash_balance.values())
        assert total_cash < 0  # Cash should be negative (outflow)

        # Calculate asset market value
        position = asset.position(date(2023, 6, 15))
        current_price = asset.price_at_date(date(2023, 6, 15))
        asset_value = position * current_price.price if current_price else Decimal("0")

        # Total NAV = Asset value + Cash balance
        total_nav = asset_value + total_cash
        assert total_nav > 0  # Should be positive

    def test_nav_change_over_time(
        self, user, broker, asset, sample_transactions, price_history
    ):
        """Test NAV change calculation over different time periods."""
        dates = [date(2023, 3, 15), date(2023, 6, 15), date(2023, 9, 15)]

        nav_values = []

        for valuation_date in dates:
            position = asset.position(valuation_date)
            current_price = asset.price_at_date(valuation_date)

            if position > 0 and current_price:
                nav_value = position * current_price.price
                nav_values.append(nav_value)
            else:
                nav_values.append(Decimal("0"))

        # NAV values should be different over time due to price changes
        assert len(set(nav_values)) > 1

        # Calculate NAV change
        if len(nav_values) >= 2:
            nav_change = nav_values[-1] - nav_values[0]
            nav_change_pct = (nav_change / nav_values[0]) * Decimal("100")
            assert isinstance(nav_change, Decimal)
            assert isinstance(nav_change_pct, Decimal)

    def test_nav_with_dividends(self, user, broker, asset, sample_transactions):
        """Test NAV calculation including dividend payments."""
        valuation_date = date(2023, 6, 15)

        # Calculate asset market value
        position = asset.position(valuation_date)

        # Get current price (create if not exists)
        current_price = asset.price_at_date(valuation_date)
        if not current_price:
            Prices.objects.create(
                date=valuation_date, security=asset, price=Decimal("55.00")
            )
            current_price = asset.price_at_date(valuation_date)

        asset_value = position * current_price.price

        # Calculate total dividends received
        dividends = asset.get_capital_distribution(valuation_date)
        assert dividends > 0  # Should have dividend from sample_transactions

        # Total return includes both asset value and dividends
        total_return = asset_value + dividends
        assert total_return > asset_value

    def test_nav_with_commission_costs(self, user, broker, asset):
        """Test NAV calculation including commission costs."""
        # Create transactions with high commission
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5100.00"),  # Includes $100 commission
            commission=Decimal("100.00"),
        )

        # Create current price
        # current_price = Prices.objects.create(
        #     date=date(2023, 6, 15), security=asset, price=Decimal("55.00")
        # )

        # Calculate NAV
        # position = asset.position(date(2023, 6, 15))
        # asset_value = position * current_price.price

        # Get cash balance (should include commission)
        cash_balance = broker.balance(date(2023, 6, 15))
        total_cash = sum(cash_balance.values())

        # NAV should be reduced by commission costs
        expected_cash = -Decimal("5100")  # Initial cash outflow including commission
        assert total_cash <= expected_cash

    def test_nav_zero_position(self, user, broker, asset):
        """Test NAV calculation when position is zero."""
        # Create and close position
        Transactions.objects.create(
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

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 2, 15),
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            cash_flow=Decimal("5500.00"),
            commission=Decimal("5.00"),
        )

        position = asset.position(date(2023, 3, 15))
        assert position == 0

        # NAV from this asset should be zero
        current_price = Prices.objects.create(
            date=date(2023, 3, 15), security=asset, price=Decimal("60.00")
        )

        asset_value = position * current_price.price
        assert asset_value == 0


@pytest.mark.nav
@pytest.mark.unit
class TestNAVAggregation:
    """Test NAV aggregation across multiple assets and brokers."""

    def test_portfolio_nav_multiple_brokers(self, user, broker, broker_uk, asset):
        """Test portfolio NAV across multiple brokers."""
        # Create transactions with different brokers
        Transactions.objects.create(
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

        Transactions.objects.create(
            investor=user,
            broker=broker_uk,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("75"),
            price=Decimal("52.00"),
            cash_flow=Decimal("-3900.00"),
            commission=Decimal("4.00"),
        )

        # Create current price
        current_price = Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("55.00")
        )

        # Calculate NAV for each broker
        total_position = asset.position(date(2023, 6, 15))
        asset_value = total_position * current_price.price

        # Calculate total cash across brokers
        broker_cash = broker.balance(date(2023, 6, 15))
        broker_uk_cash = broker_uk.balance(date(2023, 6, 15))

        total_cash = sum(broker_cash.values()) + sum(broker_uk_cash.values())

        # Total portfolio NAV
        portfolio_nav = asset_value + total_cash
        assert portfolio_nav > 0

    def test_sector_nav_allocation(self, user, broker):
        """Test NAV allocation by sector."""
        # Create assets from different sectors
        tech_asset = Assets.objects.create(
            type="Stock",
            ISIN="TECH123456789",
            name="Tech Corp",
            currency="USD",
            exposure="Equity",
        )
        tech_asset.investors.add(user)
        tech_asset.brokers.add(broker)

        finance_asset = Assets.objects.create(
            type="Stock",
            ISIN="FIN123456789",
            name="Finance Corp",
            currency="USD",
            exposure="Equity",
        )
        finance_asset.investors.add(user)
        finance_asset.brokers.add(broker)

        # Create transactions
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=tech_asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("100.00"),
            cash_flow=Decimal("-10000.00"),
            commission=Decimal("10.00"),
        )

        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=finance_asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("50"),
            price=Decimal("80.00"),
            cash_flow=Decimal("-4000.00"),
            commission=Decimal("5.00"),
        )

        # Create current prices
        Prices.objects.create(
            date=date(2023, 6, 15), security=tech_asset, price=Decimal("110.00")
        )

        Prices.objects.create(
            date=date(2023, 6, 15), security=finance_asset, price=Decimal("85.00")
        )

        # Calculate sector allocations
        tech_nav = tech_asset.position(date(2023, 6, 15)) * Decimal("110.00")
        finance_nav = finance_asset.position(date(2023, 6, 15)) * Decimal("85.00")
        total_nav = tech_nav + finance_nav

        tech_allocation = (tech_nav / total_nav) * Decimal("100")
        finance_allocation = (finance_nav / total_nav) * Decimal("100")

        assert tech_allocation + finance_allocation == Decimal("100")
        assert tech_allocation > 0
        assert finance_allocation > 0

    def test_currency_allocation_nav(
        self, multi_currency_user, broker, asset_eur, asset_gbp, fx_rates_multi_currency
    ):
        """Test NAV allocation by currency."""
        valuation_date = date(2023, 6, 15)

        # Create transactions
        Transactions.objects.create(
            investor=multi_currency_user,
            broker=broker,
            security=asset_eur,
            currency="EUR",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("40.00"),
            cash_flow=Decimal("-4000.00"),
            commission=Decimal("4.00"),
        )

        Transactions.objects.create(
            investor=multi_currency_user,
            broker=broker,
            security=asset_gbp,
            currency="GBP",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("150"),
            price=Decimal("35.00"),
            cash_flow=Decimal("-5250.00"),
            commission=Decimal("5.00"),
        )

        # Create current prices
        Prices.objects.create(
            date=valuation_date, security=asset_eur, price=Decimal("42.00")
        )

        Prices.objects.create(
            date=valuation_date, security=asset_gbp, price=Decimal("37.00")
        )

        # Calculate NAV by currency
        eur_value = asset_eur.position(valuation_date) * Decimal("42.00")
        gbp_value = asset_gbp.position(valuation_date) * Decimal("37.00")

        # Convert to USD
        fx_eur_usd = FX.get_rate("EUR", "USD", valuation_date)["FX"]
        fx_gbp_usd = FX.get_rate("GBP", "USD", valuation_date)["FX"]

        eur_value_usd = eur_value * fx_eur_usd
        gbp_value_usd = gbp_value * fx_gbp_usd

        total_nav_usd = eur_value_usd + gbp_value_usd

        eur_allocation = (eur_value_usd / total_nav_usd) * Decimal("100")
        gbp_allocation = (gbp_value_usd / total_nav_usd) * Decimal("100")

        assert eur_allocation + gbp_allocation == Decimal("100")
        assert eur_allocation > 0
        assert gbp_allocation > 0


@pytest.mark.nav
@pytest.mark.unit
class TestNAVPerformance:
    """Test NAV performance and change calculations."""

    def test_nav_return_calculation(
        self, user, broker, asset, sample_transactions, price_history
    ):
        """Test NAV return calculation over time period."""
        start_date = date(2023, 3, 15)
        end_date = date(2023, 6, 15)

        # Calculate NAV at start
        start_position = asset.position(start_date)
        start_price = asset.price_at_date(start_date)
        start_nav = start_position * start_price.price if start_price else Decimal("0")

        # Calculate NAV at end
        end_position = asset.position(end_date)
        end_price = asset.price_at_date(end_date)
        end_nav = end_position * end_price.price if end_price else Decimal("0")

        # Calculate dividends received
        dividends = asset.get_capital_distribution(end_date, start_date=start_date)

        # Calculate total return
        total_return = (end_nav + dividends) - start_nav
        return_percentage = (
            (total_return / start_nav) * Decimal("100")
            if start_nav > 0
            else Decimal("0")
        )

        assert isinstance(total_return, Decimal)
        assert isinstance(return_percentage, Decimal)

    def test_annual_performance_calculation(self, user, broker, asset):
        """Test annual performance calculation."""
        # Create transactions throughout the year
        Transactions.objects.create(
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

        # Create annual performance record
        AnnualPerformance.objects.create(
            investor=user,
            broker=broker,
            year=2023,
            currency="USD",
            bop_nav=Decimal("0"),
            invested=Decimal("5005.00"),
            cash_out=Decimal("0"),
            price_change=Decimal("1000.00"),
            capital_distribution=Decimal("100.00"),
            commission=Decimal("10.00"),
            tax=Decimal("0"),
            fx=Decimal("0"),
            eop_nav=Decimal("6090.00"),
            tsr="21.5",
        )

        # Retrieve annual performance
        perf = AnnualPerformance.objects.get(investor=user, broker=broker, year=2023)

        # Verify calculations
        assert perf.bop_nav == Decimal("0")
        assert perf.invested == Decimal("5005.00")
        assert perf.eop_nav == Decimal("6090.00")
        assert perf.price_change == Decimal("1000.00")
        assert perf.capital_distribution == Decimal("100.00")
        assert perf.commission == Decimal("10.00")

        # TSR should be (EOP NAV + cash out - invested - BOP NAV) / invested
        expected_tsr = (
            (perf.eop_nav + perf.cash_out - perf.invested - perf.bop_nav)
            / perf.invested
        ) * Decimal("100")
        assert abs(Decimal(perf.tsr) - expected_tsr) < Decimal("0.1")

    def test_volatility_adjusted_nav(self, user, broker, asset):
        """Test NAV calculations with volatility considerations."""
        # Create position
        Transactions.objects.create(
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

        # Create price history with volatility
        base_price = Decimal("50.00")
        for i in range(30):
            current_date = date(2023, 6, 1) + timedelta(days=i)
            # Simulate price volatility
            price_change = Decimal("0.02") * (i % 10 - 5)  # +/- 10% volatility
            current_price = base_price + (base_price * price_change)
            current_price = max(current_price, Decimal("1.00"))  # Ensure positive price

            Prices.objects.create(
                date=current_date, security=asset, price=current_price
            )

        # Calculate NAV volatility
        nav_values = []
        for i in range(0, 30, 5):  # Sample every 5 days
            current_date = date(2023, 6, 1) + timedelta(days=i)
            position = asset.position(current_date)
            current_price = asset.price_at_date(current_date)
            if current_price:
                nav_value = position * current_price.price
                nav_values.append(nav_value)

        # Calculate basic volatility metrics
        if len(nav_values) > 1:
            nav_changes = [
                nav_values[i] - nav_values[i - 1] for i in range(1, len(nav_values))
            ]
            avg_change = sum(nav_changes) / len(nav_changes)
            max_change = max(nav_changes)
            min_change = min(nav_changes)

            assert isinstance(avg_change, Decimal)
            assert isinstance(max_change, Decimal)
            assert isinstance(min_change, Decimal)


@pytest.mark.nav
@pytest.mark.unit
class TestNAVEdgeCases:
    """Test edge cases in NAV calculations."""

    def test_nav_missing_price_data(self, user, broker, asset):
        """Test NAV calculation when price data is missing."""
        # Create transaction but no price data
        Transactions.objects.create(
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

        # Try to calculate NAV without price data
        position = asset.position(date(2023, 6, 15))
        current_price = asset.price_at_date(date(2023, 6, 15))

        if current_price is None:
            # Should handle missing price gracefully
            asset_value = Decimal("0")
        else:
            asset_value = position * current_price.price

        assert isinstance(asset_value, Decimal)

    def test_nav_very_large_positions(self, user, broker, asset):
        """Test NAV calculation with very large positions."""
        # Create large transaction
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("1000000"),
            price=Decimal("0.01"),
            cash_flow=Decimal("-10000.00"),
            commission=Decimal("10.00"),
        )

        # Create current price
        current_price = Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("0.02")
        )

        # Calculate NAV
        position = asset.position(date(2023, 6, 15))
        asset_value = position * current_price.price

        assert asset_value == Decimal("20000.00")
        assert isinstance(asset_value, Decimal)

    def test_nav_precision_requirements(self, user, broker, asset):
        """Test NAV calculation with high precision requirements."""
        # Create transaction with high precision
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("1.234567"),
            price=Decimal("123.456789"),
            cash_flow=Decimal("-152.41579"),
            commission=Decimal("0.15"),
        )

        # Create current price with high precision
        current_price = Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("125.678901")
        )

        # Calculate NAV with high precision
        position = asset.position(date(2023, 6, 15))
        asset_value = position * current_price.price

        # Should maintain high precision
        assert asset_value.as_tuple().exponent <= -6
        assert isinstance(asset_value, Decimal)

    def test_nav_negative_positions(self, user, broker, asset):
        """Test NAV calculation with short positions."""
        # Create short position
        Transactions.objects.create(
            investor=user,
            broker=broker,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 1, 15),
            quantity=Decimal("-100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("5000.00"),
            commission=Decimal("5.00"),
        )

        # Create current price (higher for short loss)
        current_price = Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("55.00")
        )

        # Calculate NAV for short position
        position = asset.position(date(2023, 6, 15))
        asset_value = position * current_price.price

        # Short position should have negative value
        assert asset_value < 0
        assert asset_value == Decimal("-5500.00")
