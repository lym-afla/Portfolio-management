"""
Test cases for gain/loss calculations.

This module tests the core gain/loss calculation logic including:
- Realized gain/loss calculations
- Unrealized gain/loss calculations
- Multi-currency gain/loss calculations
- Complex scenarios with partial sales
- FX effects on gain/loss
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from common.models import FX, Prices, Transactions


@pytest.mark.nav
@pytest.mark.unit
class TestRealizedGainLoss:
    """Test realized gain/loss calculation functionality."""

    def test_realized_gain_simple_profit(self, user, account, asset):
        """Test realized gain calculation for simple profitable sale."""
        # Create purchase
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Buy",
            date=datetime(2023, 1, 15, 12, 0, 0),
            quantity=Decimal("100"),
            price=Decimal("50.00"),
            commission=Decimal("-5.00"),
        )

        # Create profitable sale
        Transactions.objects.create(
            investor=user,
            account=account,
            security=asset,
            currency="USD",
            type="Sell",
            date=datetime(2023, 6, 15, 14, 0, 0),
            quantity=Decimal("-100"),
            price=Decimal("60.00"),
            commission=Decimal("-5.00"),
        )

        result = asset.realized_gain_loss(date(2023, 7, 16), investor=user)

        # Expected: (60 - 50) * 100 = 1000 profit
        expected_profit = (Decimal("60.00") - Decimal("50.00")) * Decimal("100")
        assert result["current_position"]["total"] == Decimal("0")  # closed position
        assert result["all_time"]["total"] == expected_profit

    def test_realized_gain_simple_loss(self, user, account, asset):
        """Test realized gain calculation for simple loss sale."""
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
            commission=Decimal("-5.00"),
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
            commission=Decimal("-5.00"),
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        # Expected: (40 - 50) * 100 = -1000 loss
        expected_loss = (Decimal("40.00") - Decimal("50.00")) * Decimal("100")
        assert result["current_position"]["total"] == Decimal("0")  # closed position
        assert result["all_time"]["total"] == expected_loss

    def test_realized_gain_partial_sale(self, user, account, asset):
        """Test realized gain calculation for partial sale."""
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
            commission=Decimal("-5.00"),
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
            commission=Decimal("-3.00"),
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
            commission=Decimal("-3.00"),
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        # Buy-in price: (100*50 + 50*55) / 150 = 51.666...
        # Realized gain: (60 - 51.666...) * 30 = 250
        buy_in_price = (Decimal("5000") + Decimal("2750")) / Decimal("150")
        expected_gain = (Decimal("60.00") - buy_in_price) * Decimal("30")
        assert abs(result["current_position"]["total"] - expected_gain) < Decimal("0.01")

    def test_realized_gain_multiple_partial_sales(self, user, account, asset):
        """Test realized gain calculation with multiple partial sales."""
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
            commission=Decimal("-10.00"),
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
            commission=Decimal("-3.00"),
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
            commission=Decimal("-3.00"),
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        # Should calculate realized gain for both sales
        assert result["current_position"]["total"] > 0  # Should be profitable
        expected_gain = (Decimal("55.00") - Decimal("50.00")) * Decimal("50") + (
            Decimal("60.00") - Decimal("50.00")
        ) * Decimal("30")
        assert result["all_time"]["total"] == expected_gain

    def test_realized_gain_with_dividends(self, user, account, asset):
        """Test that dividends don't affect realized gain calculations."""
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
            commission=Decimal("-5.00"),
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
            commission=Decimal("-5.00"),
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        # Dividend should not affect realized gain calculation
        expected_gain = (Decimal("60.00") - Decimal("50.00")) * Decimal("100")
        assert result["current_position"]["total"] == Decimal("0")  # closed position
        assert result["all_time"]["total"] == expected_gain

    def test_realized_gain_no_sales(self, user, account, asset):
        """Test realized gain calculation when no sales have occurred."""
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
            commission=Decimal("-5.00"),
        )

        result = asset.realized_gain_loss(date(2023, 6, 15), investor=user)

        assert result["current_position"]["total"] == Decimal("0")
        assert result["all_time"]["total"] == Decimal("0")


@pytest.mark.nav
@pytest.mark.unit
class TestUnrealizedGainLoss:
    """Test unrealized gain/loss calculation functionality."""

    def test_unrealized_gain_profit(self, user, account, asset, price_history):
        """Test unrealized gain calculation for profitable position."""
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
            commission=Decimal("-5.00"),
        )

        # Create price
        Prices.objects.update_or_create(
            date=date(2024, 6, 15),
            security=asset,
            price=Decimal("65.00"),
        )

        result = asset.unrealized_gain_loss(date(2024, 6, 15), investor=user)

        expected_gain = (Decimal("65.00") - Decimal("50.00")) * Decimal("100")
        assert result["total"] == expected_gain

    def test_unrealized_gain_loss(self, user, account, asset):
        """Test unrealized gain calculation for loss position."""
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
            commission=Decimal("-5.00"),
        )

        # Create current lower price
        Prices.objects.update_or_create(
            date=date(2023, 6, 15),
            security=asset,
            price=Decimal("35.00"),
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Expected: (35 - 50) * 100 = -1500 loss
        expected_loss = (Decimal("35.00") - Decimal("50.00")) * Decimal("100")
        assert result["total"] == expected_loss

    def test_unrealized_gain_multiple_purchases(self, user, account, asset):
        """Test unrealized gain calculation with multiple purchases."""
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
            commission=Decimal("-5.00"),
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
            commission=Decimal("-3.00"),
        )

        # Create current price
        Prices.objects.create(date=date(2023, 6, 15), security=asset, price=Decimal("60.00"))

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Buy-in price: (100*50 + 50*55) / 150 = 51.666...
        # Unrealized gain: (60 - 51.666...) * 150 = 1250
        buy_in_price = (Decimal("5000") + Decimal("2750")) / Decimal("150")
        expected_gain = (Decimal("60.00") - buy_in_price) * Decimal("150")
        assert abs(result["total"] - expected_gain) < Decimal("0.01")

    def test_unrealized_gain_after_partial_sale(self, user, account, asset):
        """Test unrealized gain calculation after partial sale."""
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
            commission=Decimal("-5.00"),
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
            commission=Decimal("-3.00"),
        )

        # Create current price
        Prices.objects.create(date=date(2023, 6, 15), security=asset, price=Decimal("60.00"))

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Remaining position: 70 shares
        # Buy-in price should still be 50.00
        # Unrealized gain: (60 - 50) * 70 = 700
        expected_gain = (Decimal("60.00") - Decimal("50.00")) * Decimal("70")
        assert result["total"] == expected_gain

    def test_unrealized_gain_zero_position(self, user, account, asset):
        """Test unrealized gain calculation when position is zero."""
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
            commission=Decimal("-5.00"),
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
            commission=Decimal("-5.00"),
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        assert result["total"] == 0

    def test_unrealized_gain_no_price_data(self, user, account, asset):
        """Test unrealized gain calculation when no price data available."""
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
            commission=Decimal("-5.00"),
        )

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        assert result["total"] == 0  # Should return 0 when no price data


@pytest.mark.nav
@pytest.mark.unit
class TestMultiCurrencyGainLoss:
    """Test gain/loss calculations with multi-currency positions."""

    def test_realized_gain_currency_conversion(
        self, multi_currency_user, account, asset_eur, fx_rates_multi_currency
    ):
        """Test realized gain calculation with currency conversion."""
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
            commission=Decimal("-4.00"),
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
            commission=Decimal("-4.00"),
        )

        # Create price data
        Prices.objects.create(date=date(2024, 6, 15), security=asset_eur, price=Decimal("45.00"))

        # Calculate realized gain in EUR (local currency)
        result_eur = asset_eur.realized_gain_loss(
            date(2024, 6, 15), currency="EUR", investor=multi_currency_user
        )
        expected_eur = (Decimal("45.00") - Decimal("40.00")) * Decimal("100")
        assert abs(result_eur["all_time"]["total"] - expected_eur) < Decimal("0.01")

        # Calculate realized gain in USD (converted)
        result_usd = asset_eur.realized_gain_loss(
            date(2024, 6, 15), currency="USD", investor=multi_currency_user
        )
        assert (
            result_usd["all_time"]["total"] > result_eur["all_time"]["total"]
        )  # USD conversion should increase value

    def test_unrealized_gain_currency_conversion(
        self, multi_currency_user, account, asset_eur, fx_rates_multi_currency
    ):
        """Test unrealized gain calculation with currency conversion."""
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
            commission=Decimal("-4.00"),
        )

        # Create current EUR price
        Prices.objects.create(date=date(2023, 6, 15), security=asset_eur, price=Decimal("45.00"))

        # Calculate unrealized gain in EUR
        result_eur = asset_eur.unrealized_gain_loss(
            date(2023, 6, 15), currency="EUR", investor=multi_currency_user
        )
        expected_eur = (Decimal("45.00") - Decimal("40.00")) * Decimal("100")
        assert result_eur["total"] == expected_eur

        # Calculate unrealized gain in USD
        result_usd = asset_eur.unrealized_gain_loss(
            date(2023, 6, 15), currency="USD", investor=multi_currency_user
        )
        assert result_usd["total"] > result_eur["total"]  # USD conversion should increase value

    def test_fx_effect_on_gain_loss(
        self, multi_currency_user, account, asset_eur, fx_rates_multi_currency
    ):
        """Test FX effect on gain/loss calculations."""
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
            commission=Decimal("-4.00"),
        )

        # Create current EUR price
        Prices.objects.create(date=date(2023, 6, 15), security=asset_eur, price=Decimal("45.00"))

        # Calculate gains in both currencies
        gain_eur = asset_eur.unrealized_gain_loss(
            date(2023, 6, 15), currency="EUR", investor=multi_currency_user
        )
        gain_usd = asset_eur.unrealized_gain_loss(
            date(2023, 6, 15), currency="USD", investor=multi_currency_user
        )

        # FX effect should be the difference
        fx_effect = gain_usd["total"] - (
            gain_eur["total"] * FX.get_rate("EUR", "USD", date(2023, 6, 15))["FX"]
        )

        # FX effect should be minimal due to similar conversion rates
        assert abs(fx_effect) < Decimal("50")  # Allow small rounding differences


@pytest.mark.nav
@pytest.mark.unit
class TestGainLossEdgeCases:
    """Test edge cases and complex scenarios in gain/loss calculations."""

    def test_gain_loss_short_position(self, user, account, asset):
        """Test gain/loss calculation for short positions."""
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
            commission=Decimal("-5.00"),
        )

        # Create current price (higher than short price - loss for short)
        Prices.objects.create(date=date(2023, 6, 15), security=asset, price=Decimal("60.00"))

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # For short position: (50 - 60) * 100 = -1000 (loss)
        expected_loss = (Decimal("50.00") - Decimal("60.00")) * Decimal("100")
        assert result["total"] == expected_loss

    def test_gain_loss_very_small_amounts(self, user, account, asset):
        """Test gain/loss calculation with very small amounts."""
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
            commission=Decimal("-0.01"),
        )

        # Create current price
        Prices.objects.create(date=date(2023, 6, 15), security=asset, price=Decimal("1100.00"))

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Expected: (1100 - 1000) * 0.001 = 0.1
        expected_gain = (Decimal("1100.00") - Decimal("1000.00")) * Decimal("0.001")
        assert result["total"] == expected_gain

    def test_gain_loss_high_precision(self, user, account, asset):
        """Test gain/loss calculation with high precision requirements."""
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
            commission=Decimal("-0.15"),
        )

        # Create current price
        Prices.objects.create(date=date(2024, 6, 15), security=asset, price=Decimal("125.678901"))

        result = asset.unrealized_gain_loss(date(2024, 6, 15), investor=user)

        # Expected: (125.678901 - 123.456789) * 1.234567
        # rounded to 2 decimal places as per the method definition
        expected_gain = round(
            (Decimal("125.678901") - Decimal("123.456789")) * Decimal("1.234567"), 2
        )
        assert result["total"] == expected_gain

    def test_gain_loss_commission_impact(self, user, account, asset):
        """Test that commission doesn't affect unrealized gain calculations."""
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
            commission=Decimal("-100.00"),
        )

        # Create current price
        Prices.objects.create(date=date(2023, 6, 15), security=asset, price=Decimal("60.00"))

        result = asset.unrealized_gain_loss(date(2023, 6, 15), investor=user)

        # Commission should not affect unrealized gain calculation
        expected_gain = (Decimal("60.00") - Decimal("50.00")) * Decimal("100")
        assert result["total"] == expected_gain

    def test_gain_loss_broker_filtering(self, user, account, account_uk, asset):
        """Test gain/loss calculation with broker filtering."""
        # Create transaction with first account
        Transactions.objects.create(
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

        # Create transaction with second account
        Transactions.objects.create(
            investor=user,
            account=account_uk,
            security=asset,
            currency="USD",
            type="Buy",
            date=date(2023, 2, 15),
            quantity=Decimal("100"),
            price=Decimal("60.00"),
            commission=Decimal("-6.00"),
        )

        # Create current price
        Prices.objects.create(date=date(2023, 6, 15), security=asset, price=Decimal("55.00"))

        # Calculate for first account only
        result_account1 = asset.unrealized_gain_loss(
            date(2023, 6, 15), account_ids=[account.id], investor=user
        )
        expected_account1 = (Decimal("55.00") - Decimal("50.00")) * Decimal("100")
        assert result_account1["total"] == expected_account1

        # Calculate for second account only
        result_account2 = asset.unrealized_gain_loss(
            date(2023, 6, 15), account_ids=[account_uk.id], investor=user
        )
        expected_account2 = (Decimal("55.00") - Decimal("60.00")) * Decimal("100")
        assert result_account2["total"] == expected_account2

        # Calculate for both accounts
        result_both_accounts = asset.unrealized_gain_loss(
            date(2023, 6, 15), account_ids=[account.id, account_uk.id], investor=user
        )
        # Average buy-in price: (5000 + 6000) / 200 = 55
        # No gain/loss as current price equals average buy-in price
        assert result_both_accounts["total"] == Decimal("0")
