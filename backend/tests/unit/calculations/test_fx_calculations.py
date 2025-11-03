"""
Test cases for FX rate calculations.

This module tests the core FX calculation logic including:
- Direct currency conversions
- Cross-currency conversions
- FX rate lookup and interpolation
- Edge cases and error handling
"""

from datetime import date
from decimal import Decimal

import pytest

from common.models import FX


@pytest.mark.fx
@pytest.mark.unit
class TestFXRateCalculation:
    """Test FX rate calculation functionality."""

    def test_fx_get_rate_direct_currency_same_currency(self, user):
        """Test FX rate lookup for same currency."""
        result = FX.get_rate("USD", "USD", date(2023, 6, 15))

        assert result["FX"] == Decimal("1")
        assert result["conversions"] == 0
        assert result["dates_async"] is False
        assert result["dates"] == []

    def test_fx_get_rate_direct_currency_success(self, user, fx_rates_usd_eur):
        """Test successful direct FX rate lookup."""
        result = FX.get_rate("USD", "EUR", date(2023, 6, 15))

        assert isinstance(result["FX"], Decimal)
        assert result["FX"] > 0
        assert result["FX"] < 1  # EUR is worth less than USD
        assert result["conversions"] == 1
        assert result["dates_async"] is False
        assert len(result["dates"]) == 1

    def test_fx_get_rate_cross_currency_success(self, user, fx_rates_multi_currency):
        """Test successful cross-currency FX rate lookup."""
        result = FX.get_rate("GBP", "EUR", date(2023, 6, 15))

        assert isinstance(result["FX"], Decimal)
        assert result["FX"] > 0
        assert result["conversions"] >= 2
        assert isinstance(result["dates_async"], bool)
        assert len(result["dates"]) >= 2

    def test_fx_get_rate_date_exact_match(self, user, fx_rates_usd_eur):
        """Test FX rate lookup with exact date match."""
        test_date = date(2023, 6, 15)
        result = FX.get_rate("USD", "EUR", test_date)

        # Find the expected rate from our fixture data
        expected_fx = FX.objects.filter(
            date=test_date, investors=user, USDEUR__isnull=False
        ).first()

        assert expected_fx is not None
        assert result["dates"] == [test_date]

    def test_fx_get_rate_date_interpolation_before(self, user, fx_rates_usd_eur):
        """Test FX rate lookup with date interpolation (use rate before date)."""
        # Use a date that might not have exact data
        test_date = date(2023, 6, 16)
        result = FX.get_rate("USD", "EUR", test_date)

        assert isinstance(result["FX"], Decimal)
        assert result["FX"] > 0
        assert len(result["dates"]) >= 1
        # Should use the rate from the closest previous date
        assert all(d <= test_date for d in result["dates"])

    def test_fx_get_rate_date_interpolation_after(self, user, fx_rates_usd_eur):
        """Test FX rate lookup with date interpolation (use rate after date)."""
        # Use a date before our data starts
        test_date = date(2022, 12, 15)

        # This should find the first available rate
        result = FX.get_rate("USD", "EUR", test_date)

        assert isinstance(result["FX"], Decimal)
        assert result["FX"] > 0
        assert len(result["dates"]) >= 1
        # Should use the rate from the closest future date
        assert all(d >= test_date for d in result["dates"])

    def test_fx_get_rate_no_data_available(self, user):
        """Test FX rate lookup when no data is available."""
        # Use currency pair that doesn't exist in our fixtures
        with pytest.raises(ValueError, match="No FX rate found"):
            FX.get_rate("USD", "JPY", date(2023, 6, 15))

    def test_fx_get_rate_invalid_currency_pair(self, user):
        """Test FX rate lookup with invalid currency pair."""
        # Test with currencies that don't have direct or cross rates
        with pytest.raises(ValueError):
            FX.get_rate("INVALID", "PAIR", date(2023, 6, 15))

    def test_fx_get_rate_uses_networkx_algorithm(self, user, fx_rates_multi_currency):
        """Test that FX rate calculation uses NetworkX for path finding."""
        # This is implicitly tested by successful cross-currency conversions
        result = FX.get_rate("RUB", "PLN", date(2023, 6, 15))

        assert isinstance(result["FX"], Decimal)
        assert result["FX"] > 0
        assert result["conversions"] >= 2  # Should involve cross-currency conversion

    def test_fx_rate_precision(self, user, fx_rates_usd_eur):
        """Test FX rate precision and rounding."""
        result = FX.get_rate("USD", "EUR", date(2023, 6, 15))

        # Result should be properly rounded to 6 decimal places
        expected_precision = Decimal("0.000001")
        assert result["FX"].quantize(expected_precision) == result["FX"]

    def test_fx_rate_calculation_multiple_dates(self, user, fx_rates_usd_eur):
        """Test FX rate calculation across multiple dates."""
        test_dates = [
            date(2023, 1, 15),
            date(2023, 3, 15),
            date(2023, 6, 15),
            date(2023, 9, 15),
            date(2023, 12, 15),
        ]

        results = []
        for test_date in test_dates:
            result = FX.get_rate("USD", "EUR", test_date)
            results.append(result)
            assert isinstance(result["FX"], Decimal)
            assert result["FX"] > 0

        # Rates should be different across different dates
        rates = [r["FX"] for r in results]
        assert len(set(rates)) > 1  # Should have different rates

    def test_fx_rate_async_dates_detection(self, user, fx_rates_multi_currency):
        """Test detection of asynchronous date usage in cross-currency conversions."""
        result = FX.get_rate("GBP", "RUB", date(2023, 6, 15))

        # Cross-currency conversions might use different dates for different legs
        assert isinstance(result["dates_async"], bool)
        assert len(result["dates"]) >= result["conversions"]


@pytest.mark.fx
@pytest.mark.unit
class TestFXRateScenarios:
    """Test realistic FX rate scenarios."""

    def test_portfolio_currency_conversion_usd_to_eur(
        self, multi_currency_user, fx_rates_multi_currency
    ):
        """Test typical portfolio conversion from USD to EUR."""
        amount = Decimal("10000.00")
        conversion_date = date(2023, 6, 15)

        fx_result = FX.get_rate("USD", "EUR", conversion_date)
        converted_amount = amount * fx_result["FX"]

        assert converted_amount < amount  # EUR is worth less than USD
        assert converted_amount > Decimal("8000")  # Reasonable conversion rate

    def test_portfolio_currency_conversion_eur_to_gbp(
        self, multi_currency_user, fx_rates_multi_currency
    ):
        """Test cross-currency conversion from EUR to GBP."""
        amount = Decimal("8000.00")
        conversion_date = date(2023, 6, 15)

        fx_result = FX.get_rate("EUR", "GBP", conversion_date)
        converted_amount = amount * fx_result["FX"]

        assert isinstance(converted_amount, Decimal)
        assert converted_amount > 0
        assert fx_result["conversions"] >= 2  # Should be cross-currency

    def test_multi_currency_portfolio_valuation(
        self, multi_currency_user, fx_rates_multi_currency
    ):
        """Test valuing a multi-currency portfolio in a single currency."""
        portfolio = {
            "USD": Decimal("10000.00"),
            "EUR": Decimal("8000.00"),
            "GBP": Decimal("6000.00"),
        }
        valuation_date = date(2023, 6, 15)
        target_currency = "USD"

        total_usd = Decimal("0")

        # Convert each currency to USD
        for currency, amount in portfolio.items():
            if currency == target_currency:
                total_usd += amount
            else:
                fx_result = FX.get_rate(currency, target_currency, valuation_date)
                converted_amount = amount * fx_result["FX"]
                total_usd += converted_amount

        assert total_usd > Decimal("20000")  # Should be more than sum of USD portion
        assert isinstance(total_usd, Decimal)

    def test_fx_rate_volatility_impact(
        self, multi_currency_user, fx_rates_multi_currency
    ):
        """Test FX rate volatility impact on portfolio valuation."""
        amount = Decimal("10000.00")

        # Test valuation at different times
        dates = [
            date(2023, 1, 15),  # Beginning of period
            date(2023, 6, 15),  # Middle of period
            date(2023, 12, 15),  # End of period
        ]

        valuations = []
        for valuation_date in dates:
            fx_result = FX.get_rate("USD", "EUR", valuation_date)
            converted_amount = amount * fx_result["FX"]
            valuations.append(converted_amount)

        # Valuations should differ due to FX rate changes
        assert len(set(valuations)) > 1

        # Calculate volatility impact
        max_valuation = max(valuations)
        min_valuation = min(valuations)
        volatility_impact = max_valuation - min_valuation

        assert volatility_impact > 0
        assert (volatility_impact / min_valuation) > Decimal(
            "0.01"
        )  # At least 1% volatility


@pytest.mark.fx
@pytest.mark.unit
class TestFXRateEdgeCases:
    """Test edge cases and error conditions in FX rate calculations."""

    def test_fx_rate_very_small_amounts(self, user, fx_rates_usd_eur):
        """Test FX rate conversion with very small amounts."""
        small_amount = Decimal("0.01")
        fx_result = FX.get_rate("USD", "EUR", date(2023, 6, 15))
        converted_amount = small_amount * fx_result["FX"]

        assert converted_amount > 0
        assert converted_amount < small_amount

    def test_fx_rate_very_large_amounts(self, user, fx_rates_usd_eur):
        """Test FX rate conversion with very large amounts."""
        large_amount = Decimal("1000000000.00")  # 1 billion
        fx_result = FX.get_rate("USD", "EUR", date(2023, 6, 15))
        converted_amount = large_amount * fx_result["FX"]

        assert converted_amount > 0
        assert converted_amount < large_amount

    def test_fx_rate_weekend_holidays(self, user, fx_rates_usd_eur):
        """Test FX rate lookup on weekends/holidays."""
        # Test with a weekend date
        weekend_date = date(2023, 6, 17)  # Saturday
        result = FX.get_rate("USD", "EUR", weekend_date)

        assert isinstance(result["FX"], Decimal)
        assert result["FX"] > 0
        # Should use the closest available date

    def test_fx_rate_future_date(self, user, fx_rates_usd_eur):
        """Test FX rate lookup for future dates."""
        future_date = date(2025, 1, 1)

        with pytest.raises(ValueError, match="No FX rate found"):
            FX.get_rate("USD", "EUR", future_date)

    def test_fx_rate_ancient_date(self, user, fx_rates_usd_eur):
        """Test FX rate lookup for very old dates."""
        ancient_date = date(1990, 1, 1)

        with pytest.raises(ValueError, match="No FX rate found"):
            FX.get_rate("USD", "EUR", ancient_date)

    def test_fx_rate_calculation_consistency(self, user, fx_rates_multi_currency):
        """Test FX rate calculation consistency across multiple calls."""
        test_date = date(2023, 6, 15)

        # Multiple calls should return same result
        result1 = FX.get_rate("USD", "EUR", test_date)
        result2 = FX.get_rate("USD", "EUR", test_date)

        assert result1["FX"] == result2["FX"]
        assert result1["conversions"] == result2["conversions"]
        assert result1["dates"] == result2["dates"]

    def test_fx_rate_round_trip_conversion(self, user, fx_rates_usd_eur):
        """Test round-trip currency conversion accuracy."""
        original_amount = Decimal("10000.00")
        test_date = date(2023, 6, 15)

        # Convert USD to EUR
        usd_to_eur = FX.get_rate("USD", "EUR", test_date)
        eur_amount = original_amount * usd_to_eur["FX"]

        # Convert EUR back to USD
        eur_to_usd = FX.get_rate("EUR", "USD", test_date)
        final_amount = eur_amount * eur_to_usd["FX"]

        # Should be very close to original (allowing for rounding)
        difference = abs(final_amount - original_amount)
        tolerance = original_amount * Decimal("0.01")  # 1% tolerance

        assert difference < tolerance


@pytest.mark.fx
@pytest.mark.unit
class TestFXRatePerformance:
    """Test performance of FX rate calculations."""

    def test_fx_calculation_performance_single_lookup(
        self, user, fx_rates_multi_currency
    ):
        """Test performance of single FX rate lookup."""
        import time

        start_time = time.time()
        result = FX.get_rate("USD", "EUR", date(2023, 6, 15))
        end_time = time.time()

        execution_time = end_time - start_time
        assert execution_time < 1.0  # Should complete within 1 second
        assert result["FX"] > 0

    def test_fx_calculation_performance_batch_lookup(
        self, user, fx_rates_multi_currency
    ):
        """Test performance of batch FX rate lookups."""
        import time

        currency_pairs = [
            ("USD", "EUR"),
            ("USD", "GBP"),
            ("EUR", "GBP"),
            ("USD", "RUB"),
            ("EUR", "PLN"),
        ]

        start_time = time.time()
        results = []
        for from_curr, to_curr in currency_pairs:
            result = FX.get_rate(from_curr, to_curr, date(2023, 6, 15))
            results.append(result)
        end_time = time.time()

        execution_time = end_time - start_time
        assert execution_time < 5.0  # Should complete within 5 seconds
        assert len(results) == len(currency_pairs)
        assert all(r["FX"] > 0 for r in results)
