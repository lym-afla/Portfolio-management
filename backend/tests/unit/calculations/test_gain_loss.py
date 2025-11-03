"""
Test cases for gain/loss calculations.

This module tests the core gain/loss calculation logic including:
- Realized gain/loss calculations
- Unrealized gain/loss calculations
- Multi-currency gain/loss calculations
- Complex scenarios with partial sales
- FX effects on gain/loss
"""

from datetime import date
from decimal import Decimal

import pytest

from common.models import FX, Accounts, Prices, Transactions


@pytest.mark.nav
@pytest.mark.unit
class TestRealizedGainLoss:
    """Test realized gain/loss calculation functionality."""

    def test_realized_gain_simple_profit(self, user, broker, asset):
        """Test realized gain calculation for simple profitable sale."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create profitable sale
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 6, 15),
            quantity=Decimal("-100"),
            price=Decimal("60.00"),
            cash_flow=Decimal("6000.00"),
            commission=Decimal("5.00"),
        )

        # Create price data for buy-in price calculation
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("60.00")
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        # Expected: (60 - 50) * 100 = 1000 profit
        expected_profit = (Decimal("60.00") - Decimal("50.00")) * Decimal("100")
        assert result["current_position"] == expected_profit - Decimal(
            "10"
        )  # Subtract commission
        assert result["all_time"] == expected_profit - Decimal("10")

    def test_realized_gain_simple_loss(self, user, broker, asset):
        """Test realized gain calculation for simple loss sale."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create loss sale
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 6, 15),
            quantity=Decimal("-100"),
            price=Decimal("40.00"),
            cash_flow=Decimal("4000.00"),
            commission=Decimal("5.00"),
        )

        # Create price data for buy-in price calculation
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("40.00")
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        # Expected: (40 - 50) * 100 = -1000 loss
        expected_loss = (Decimal("40.00") - Decimal("50.00")) * Decimal("100")
        assert result["current_position"] == expected_loss - Decimal(
            "10"
        )  # Subtract commission
        assert result["all_time"] == expected_loss - Decimal("10")

    def test_realized_gain_partial_sale(self, user, broker, asset):
        """Test realized gain calculation for partial sale."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create initial purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create additional purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("50"),
            price=Decimal("55.00"),
            cash_flow=Decimal("-2750.00"),
            commission=Decimal("3.00"),
        )

        # Create partial sale
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 6, 15),
            quantity=Decimal("-30"),
            price=Decimal("60.00"),
            cash_flow=Decimal("1800.00"),
            commission=Decimal("3.00"),
        )

        # Create price data
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("60.00")
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        # Buy-in price: (100*50 + 50*55) / 150 = 51.666...
        # Realized gain: (60 - 51.666...) * 30 = 250
        buy_in_price = (Decimal("5000") + Decimal("2750")) / Decimal("150")
        expected_gain = (Decimal("60.00") - buy_in_price) * Decimal("30")
        assert abs(
            result["current_position"] - (expected_gain - Decimal("3"))
        ) < Decimal("0.01")

    def test_realized_gain_multiple_partial_sales(self, user, broker, asset):
        """Test realized gain calculation with multiple partial sales."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create initial purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("200"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-10000.00"),
            commission=Decimal("10.00"),
        )

        # First partial sale
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 3, 15),
            quantity=Decimal("-50"),
            price=Decimal("55.00"),
            cash_flow=Decimal("2750.00"),
            commission=Decimal("3.00"),
        )

        # Second partial sale
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 6, 15),
            quantity=Decimal("-30"),
            price=Decimal("60.00"),
            cash_flow=Decimal("1800.00"),
            commission=Decimal("3.00"),
        )

        # Create price data
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("60.00")
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        # Should calculate realized gain for both sales
        assert result["current_position"] > 0  # Should be profitable
        assert result["all_time"] > 0

    def test_realized_gain_with_dividends(self, user, broker, asset):
        """Test that dividends don't affect realized gain calculations."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create dividend
        Transactions.objects.create(
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

        # Create sale
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 6, 15),
            quantity=Decimal("-100"),
            price=Decimal("60.00"),
            cash_flow=Decimal("6000.00"),
            commission=Decimal("5.00"),
        )

        # Create price data
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("60.00")
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        # Dividend should not affect realized gain calculation
        expected_gain = (Decimal("60.00") - Decimal("50.00")) * Decimal("100")
        assert result["current_position"] == expected_gain - Decimal("10")

    def test_realized_gain_no_sales(self, user, broker, asset):
        """Test realized gain calculation when no sales have occurred."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchase only
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        assert result["current_position"] == 0
        assert result["all_time"] == 0


@pytest.mark.nav
@pytest.mark.unit
class TestUnrealizedGainLoss:
    """Test unrealized gain/loss calculation functionality."""

    def test_unrealized_gain_profit(self, user, broker, asset, price_history):
        """Test unrealized gain calculation for profitable position."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Current price should be higher than purchase price (from price_history)
        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        assert result > 0  # Should be unrealized profit
        assert isinstance(result, Decimal)

    def test_unrealized_gain_loss(self, user, broker, asset):
        """Test unrealized gain calculation for loss position."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create current lower price
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("40.00")
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Expected: (40 - 50) * 100 = -1000 loss
        expected_loss = (Decimal("40.00") - Decimal("50.00")) * Decimal("100")
        assert result == expected_loss

    def test_unrealized_gain_multiple_purchases(self, user, broker, asset):
        """Test unrealized gain calculation with multiple purchases."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchases at different prices
        Transactions.objects.create(
            investor=user,
            account=account,
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
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("50"),
            price=Decimal("55.00"),
            cash_flow=Decimal("-2750.00"),
            commission=Decimal("3.00"),
        )

        # Create current price
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("60.00")
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Buy-in price: (100*50 + 50*55) / 150 = 51.666...
        # Unrealized gain: (60 - 51.666...) * 150 = 1250
        buy_in_price = (Decimal("5000") + Decimal("2750")) / Decimal("150")
        expected_gain = (Decimal("60.00") - buy_in_price) * Decimal("150")
        assert abs(result - expected_gain) < Decimal("0.01")

    def test_unrealized_gain_after_partial_sale(self, user, broker, asset):
        """Test unrealized gain calculation after partial sale."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create initial purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create partial sale
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 3, 15),
            quantity=Decimal("-30"),
            price=Decimal("55.00"),
            cash_flow=Decimal("1650.00"),
            commission=Decimal("3.00"),
        )

        # Create current price
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("60.00")
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Remaining position: 70 shares
        # Buy-in price should still be 50.00
        # Unrealized gain: (60 - 50) * 70 = 700
        expected_gain = (Decimal("60.00") - Decimal("50.00")) * Decimal("70")
        assert result == expected_gain

    def test_unrealized_gain_zero_position(self, user, broker, asset):
        """Test unrealized gain calculation when position is zero."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create full sale
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 3, 15),
            quantity=Decimal("-100"),
            price=Decimal("55.00"),
            cash_flow=Decimal("5500.00"),
            commission=Decimal("5.00"),
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        assert result == 0

    def test_unrealized_gain_no_price_data(self, user, broker, asset):
        """Test unrealized gain calculation when no price data available."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        assert result == 0  # Should return 0 when no price data


@pytest.mark.nav
@pytest.mark.unit
class TestMultiCurrencyGainLoss:
    """Test gain/loss calculations with multi-currency positions."""

    def test_realized_gain_currency_conversion(
        self, multi_currency_user, broker, asset_eur, fx_rates_multi_currency
    ):
        """Test realized gain calculation with currency conversion."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create EUR purchase
        Transactions.objects.create(
            investor=multi_currency_user,
            account=account,
            security=asset_eur,
            currency="EUR",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("40.00"),
            cash_flow=Decimal("-4000.00"),
            commission=Decimal("4.00"),
        )

        # Create EUR sale
        Transactions.objects.create(
            investor=multi_currency_user,
            account=account,
            security=asset_eur,
            currency="EUR",
            type="Sell",
            date=date(2023, 6, 15),
            quantity=Decimal("-100"),
            price=Decimal("45.00"),
            cash_flow=Decimal("4500.00"),
            commission=Decimal("4.00"),
        )

        # Create price data
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset_eur, price=Decimal("45.00")
        )

        # Calculate realized gain in EUR (local currency)
        result_eur = asset_eur.realized_gain_loss(
            date(2023, 6, 15), currency="EUR", investor=multi_currency_user
        )
        expected_eur = (Decimal("45.00") - Decimal("40.00")) * Decimal("100") - Decimal(
            "8"
        )
        assert abs(result_eur["current_position"] - expected_eur) < Decimal("0.01")

        # Calculate realized gain in USD (converted)
        result_usd = asset_eur.realized_gain_loss(
            date(2023, 6, 15), currency="USD", investor=multi_currency_user
        )
        assert (
            result_usd["current_position"] > result_eur["current_position"]
        )  # USD conversion should increase value

    def test_unrealized_gain_currency_conversion(
        self, multi_currency_user, broker, asset_eur, fx_rates_multi_currency
    ):
        """Test unrealized gain calculation with currency conversion."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create EUR purchase
        Transactions.objects.create(
            investor=multi_currency_user,
            account=account,
            security=asset_eur,
            currency="EUR",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("40.00"),
            cash_flow=Decimal("-4000.00"),
            commission=Decimal("4.00"),
        )

        # Create current EUR price
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset_eur, price=Decimal("45.00")
        )

        # Calculate unrealized gain in EUR
        result_eur = asset_eur.unrealized_gain_loss(
            date(2023, 6, 15), currency="EUR", investor=multi_currency_user
        )
        expected_eur = (Decimal("45.00") - Decimal("40.00")) * Decimal("100")
        assert result_eur == expected_eur

        # Calculate unrealized gain in USD
        result_usd = asset_eur.unrealized_gain_loss(
            date(2023, 6, 15), currency="USD", investor=multi_currency_user
        )
        assert result_usd > result_eur  # USD conversion should increase value

    def test_fx_effect_on_gain_loss(
        self, multi_currency_user, broker, asset_eur, fx_rates_multi_currency
    ):
        """Test FX effect on gain/loss calculations."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create EUR purchase
        Transactions.objects.create(
            investor=multi_currency_user,
            account=account,
            security=asset_eur,
            currency="EUR",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("40.00"),
            cash_flow=Decimal("-4000.00"),
            commission=Decimal("4.00"),
        )

        # Create current EUR price
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset_eur, price=Decimal("45.00")
        )

        # Calculate gains in both currencies
        gain_eur = asset_eur.unrealized_gain_loss(
            date(2023, 6, 15), currency="EUR", investor=multi_currency_user
        )
        gain_usd = asset_eur.unrealized_gain_loss(
            date(2023, 6, 15), currency="USD", investor=multi_currency_user
        )

        # FX effect should be the difference
        fx_effect = gain_usd - (
            gain_eur * FX.get_rate("EUR", "USD", date(2023, 6, 15))["FX"]
        )

        # FX effect should be minimal due to similar conversion rates
        assert abs(fx_effect) < Decimal("50")  # Allow small rounding differences


@pytest.mark.nav
@pytest.mark.unit
class TestGainLossEdgeCases:
    """Test edge cases and complex scenarios in gain/loss calculations."""

    def test_gain_loss_short_position(self, user, broker, asset):
        """Test gain/loss calculation for short positions."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create short sale
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=date(2023, 1, 15),
            quantity=Decimal("-100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("5000.00"),
            commission=Decimal("5.00"),
        )

        # Create current price (higher than short price - loss for short)
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("60.00")
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # For short position: (50 - 60) * 100 = -1000 (loss)
        expected_loss = (Decimal("50.00") - Decimal("60.00")) * Decimal("100")
        assert result == expected_loss

    def test_gain_loss_very_small_amounts(self, user, broker, asset):
        """Test gain/loss calculation with very small amounts."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create small purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("0.001"),
            price=Decimal("1000.00"),
            cash_flow=Decimal("-1.00"),
            commission=Decimal("0.01"),
        )

        # Create current price
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("1100.00")
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Expected: (1100 - 1000) * 0.001 = 0.1
        expected_gain = (Decimal("1100.00") - Decimal("1000.00")) * Decimal("0.001")
        assert result == expected_gain

    def test_gain_loss_high_precision(self, user, broker, asset):
        """Test gain/loss calculation with high precision requirements."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchase with high precision
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("1.234567"),
            price=Decimal("123.456789"),
            cash_flow=Decimal("-152.41579"),
            commission=Decimal("0.15"),
        )

        # Create current price
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("125.678901")
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Expected: (125.678901 - 123.456789) * 1.234567
        expected_gain = (Decimal("125.678901") - Decimal("123.456789")) * Decimal(
            "1.234567"
        )
        assert abs(result - expected_gain) < Decimal("0.000001")

    def test_gain_loss_commission_impact(self, user, broker, asset):
        """Test that commission doesn't affect unrealized gain calculations."""
        # Create account
        account = Accounts.objects.create(
            broker=broker,
            name="Test Account",
        )

        # Create purchase with high commission
        Transactions.objects.create(
            investor=user,
            account=account,
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
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("60.00")
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Commission should not affect unrealized gain calculation
        expected_gain = (Decimal("60.00") - Decimal("50.00")) * Decimal("100")
        assert result == expected_gain

    def test_gain_loss_broker_filtering(self, user, broker, broker_uk, asset):
        """Test gain/loss calculation with broker filtering."""
        # Create account for first broker
        account1 = Accounts.objects.create(
            broker=broker,
            name="Test Account 1",
        )

        # Create account for second broker
        account2 = Accounts.objects.create(
            broker=broker_uk,
            name="Test Account 2",
        )

        # Create transaction with first broker
        Transactions.objects.create(
            investor=user,
            account=account1,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 1, 15),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            cash_flow=Decimal("-5000.00"),
            commission=Decimal("5.00"),
        )

        # Create transaction with second broker
        Transactions.objects.create(
            investor=user,
            account=account2,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("100"),
            price=Decimal("60.00"),
            cash_flow=Decimal("-6000.00"),
            commission=Decimal("6.00"),
        )

        # Create current price
        Prices.objects.create(
            date=date(2023, 6, 15), security=asset, price=Decimal("55.00")
        )

        # Calculate for first broker only
        result_broker1 = asset.unrealized_gain_loss(
            date(2023, 6, 15), broker_id_list=[broker.id], investor=user
        )
        expected_broker1 = (Decimal("55.00") - Decimal("50.00")) * Decimal("100")
        assert result_broker1 == expected_broker1

        # Calculate for second broker only
        result_broker2 = asset.unrealized_gain_loss(
            date(2023, 6, 15), broker_id_list=[broker_uk.id], investor=user
        )
        expected_broker2 = (Decimal("55.00") - Decimal("60.00")) * Decimal("100")
        assert result_broker2 == expected_broker2

        # Calculate for both brokers
        result_both = asset.unrealized_gain_loss(
            date(2023, 6, 15), broker_id_list=[broker.id, broker_uk.id], investor=user
        )
        # Average buy-in price: (5000 + 6000) / 200 = 55
        # No gain/loss as current price equals average buy-in price
        assert result_both == 0
