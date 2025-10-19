"""
Factory classes for creating FX rate test data.
Provides realistic FX rate scenarios for various testing scenarios.
"""

from datetime import date, timedelta
from decimal import Decimal

import factory
from factory import fuzzy

from common.models import FX, FXTransaction


class FXRateFactory(factory.django.DjangoModelFactory):
    """Factory for creating FX rate records."""

    class Meta:
        model = FX

    date = fuzzy.FuzzyDate(date(2020, 1, 1), date.today())

    @factory.lazy_attribute
    def USDEUR(self):
        """USD to EUR exchange rate."""
        return self.faker.pydecimal(left_digits=1, right_digits=6, min_value=0.8, max_value=1.2)

    @factory.lazy_attribute
    def USDGBP(self):
        """USD to GBP exchange rate."""
        return self.faker.pydecimal(left_digits=1, right_digits=6, min_value=0.7, max_value=1.0)

    @factory.lazy_attribute
    def CHFGBP(self):
        """CHF to GBP exchange rate."""
        return self.faker.pydecimal(left_digits=1, right_digits=6, min_value=0.8, max_value=1.0)

    @factory.lazy_attribute
    def RUBUSD(self):
        """RUB to USD exchange rate."""
        return self.faker.pydecimal(left_digits=1, right_digits=6, min_value=0.01, max_value=0.02)

    @factory.lazy_attribute
    def PLNUSD(self):
        """PLN to USD exchange rate."""
        return self.faker.pydecimal(left_digits=1, right_digits=6, min_value=0.2, max_value=0.3)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override create to handle required investor."""
        investor = kwargs.pop("investor", None)

        if not investor:
            raise ValueError("FXRateFactory requires investor")

        return model_class.objects.create(investor=investor, **kwargs)


class FXTransactionFactory(factory.django.DjangoModelFactory):
    """Factory for creating FX transactions."""

    class Meta:
        model = FXTransaction

    date = fuzzy.FuzzyDate(date(2020, 1, 1), date.today())
    from_currency = fuzzy.FuzzyChoice(["USD", "EUR", "GBP", "CHF", "RUB", "PLN"])
    to_currency = fuzzy.FuzzyChoice(["USD", "EUR", "GBP", "CHF", "RUB", "PLN"])
    from_amount = fuzzy.FuzzyDecimal(100, 100000, 6)
    commission = fuzzy.FuzzyDecimal(0, 100, 2)

    @factory.lazy_attribute
    def to_amount(self):
        """Calculate to_amount based on from_amount and typical exchange rates."""
        # Simple exchange rate simulation
        rate_map = {
            ("USD", "EUR"): Decimal("0.92"),
            ("USD", "GBP"): Decimal("0.82"),
            ("EUR", "USD"): Decimal("1.09"),
            ("EUR", "GBP"): Decimal("0.89"),
            ("GBP", "USD"): Decimal("1.22"),
            ("GBP", "EUR"): Decimal("1.12"),
            ("USD", "CHF"): Decimal("0.92"),
            ("CHF", "USD"): Decimal("1.09"),
        }

        rate = rate_map.get((self.from_currency, self.to_currency), Decimal("1.0"))
        base_amount = self.from_amount * rate

        # Add some random variation
        variation = Decimal(str(self.faker.pyfloat(min_value=-0.01, max_value=0.01)))
        return base_amount * (Decimal("1") + variation)

    @factory.lazy_attribute
    def exchange_rate(self):
        """Calculate implied exchange rate."""
        if self.from_amount and self.to_amount:
            return self.to_amount / self.from_amount
        return Decimal("1.0")

    @factory.lazy_attribute
    def comment(self):
        """Realistic FX transaction comments."""
        comments = [
            f"Currency conversion {self.from_currency} to {self.to_currency}",
            f"FX trade {self.from_currency}/{self.to_currency}",
            f"Exchange {self.from_currency} for {self.to_currency}",
            f"Currency hedge {self.from_currency}->{self.to_currency}",
        ]
        return self.faker.random_element(comments)

    @factory.post_generation
    def ensure_different_currencies(self, create, extracted, **kwargs):
        """Ensure from_currency and to_currency are different."""
        if self.from_currency == self.to_currency:
            # Change to_currency to be different
            available_currencies = ["USD", "EUR", "GBP", "CHF", "RUB", "PLN"]
            available_currencies.remove(self.from_currency)
            self.to_currency = self.faker.random_element(available_currencies)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override create to handle required relationships."""
        investor = kwargs.pop("investor", None)
        broker = kwargs.pop("broker", None)

        if not all([investor, broker]):
            raise ValueError("FXTransactionFactory requires investor and broker")

        # Ensure different currencies
        if kwargs.get("from_currency") == kwargs.get("to_currency"):
            available_currencies = ["USD", "EUR", "GBP", "CHF", "RUB", "PLN"]
            available_currencies.remove(kwargs["from_currency"])
            kwargs["to_currency"] = factory.Faker(
                "random_element", elements=available_currencies
            ).generate()

        return model_class.objects.create(investor=investor, broker=broker, **kwargs)


class USDToEURTransactionFactory(FXTransactionFactory):
    """Factory for USD to EUR transactions."""

    from_currency = "USD"
    to_currency = "EUR"

    @factory.lazy_attribute
    def to_amount(self):
        """USD to EUR conversion."""
        rate = Decimal("0.92")
        variation = Decimal(str(self.faker.pyfloat(min_value=-0.01, max_value=0.01)))
        return self.from_amount * rate * (Decimal("1") + variation)


class EURToUSDTransactionFactory(FXTransactionFactory):
    """Factory for EUR to USD transactions."""

    from_currency = "EUR"
    to_currency = "USD"

    @factory.lazy_attribute
    def to_amount(self):
        """EUR to USD conversion."""
        rate = Decimal("1.09")
        variation = Decimal(str(self.faker.pyfloat(min_value=-0.01, max_value=0.01)))
        return self.from_amount * rate * (Decimal("1") + variation)


# Batch creation utilities
def create_fx_rate_history(investor, start_date=date(2023, 1, 1), days=365):
    """Create a comprehensive FX rate history."""

    rates = []
    base_rates = {
        "USDEUR": Decimal("0.92"),
        "USDGBP": Decimal("0.82"),
        "CHFGBP": Decimal("0.88"),
        "RUBUSD": Decimal("0.013"),
        "PLNUSD": Decimal("0.25"),
    }

    for i in range(days):
        current_date = start_date + timedelta(days=i)

        # Create rates with realistic daily variations
        rate_data = {"investor": investor, "date": current_date}

        for pair, base_rate in base_rates.items():
            # Add small daily variations
            variation = Decimal(str(0.001 * (i % 30) / 30))  # Small cyclical variation
            current_rate = base_rate + (base_rate * variation)

            # Add some random noise
            noise = Decimal(
                str(factory.Faker("pyfloat", min_value=-0.002, max_value=0.002).generate())
            )
            current_rate = current_rate * (Decimal("1") + noise)

            rate_data[pair] = max(current_rate, Decimal("0.001"))  # Ensure positive rates

        fx_rate = FXRateFactory.create(**rate_data)
        rates.append(fx_rate)

    return rates


def create_cross_currency_rates(investor, currency_pairs, start_date=date(2023, 1, 1), days=365):
    """Create FX rates for specific currency pairs."""

    rates = []

    for i in range(days):
        current_date = start_date + timedelta(days=i)

        rate_data = {"investor": investor, "date": current_date}

        for from_curr, to_curr in currency_pairs:
            # Generate realistic exchange rates
            if (from_curr, to_curr) == ("USD", "EUR"):
                base_rate = Decimal("0.92")
            elif (from_curr, to_curr) == ("EUR", "USD"):
                base_rate = Decimal("1.09")
            elif (from_curr, to_curr) == ("USD", "GBP"):
                base_rate = Decimal("0.82")
            elif (from_curr, to_curr) == ("GBP", "USD"):
                base_rate = Decimal("1.22")
            else:
                base_rate = Decimal("1.0")

            # Add variation
            variation = Decimal(str(0.01 * (i % 60) / 60))  # Cyclical variation
            current_rate = base_rate + (base_rate * variation)

            # Create field name
            field_name = f"{from_curr}{to_curr}"
            if hasattr(FX, field_name):
                rate_data[field_name] = max(current_rate, Decimal("0.001"))

        if len(rate_data) > 2:  # More than just investor and date
            fx_rate = FXRateFactory.create(**rate_data)
            rates.append(fx_rate)

    return rates


def create_fx_conversion_sequence(investor, broker, conversions):
    """Create a sequence of FX transactions."""

    transactions = []
    base_date = date(2023, 1, 1)

    for i, (from_curr, to_curr, amount) in enumerate(conversions):
        tx_date = base_date + timedelta(days=i * 15)

        tx = FXTransactionFactory.create(
            investor=investor,
            broker=broker,
            date=tx_date,
            from_currency=from_curr,
            to_currency=to_curr,
            from_amount=Decimal(str(amount)),
        )
        transactions.append(tx)

    return transactions


def create_currency_hedge_sequence(
    investor, broker, base_currency="USD", hedge_currency="EUR", periods=12
):
    """Create a sequence of currency hedge transactions."""

    transactions = []
    base_date = date(2023, 1, 1)

    for i in range(periods):
        hedge_date = base_date + timedelta(days=i * 30)

        # Create hedge transaction
        if i % 2 == 0:  # Hedge every other period
            tx = FXTransactionFactory.create(
                investor=investor,
                broker=broker,
                date=hedge_date,
                from_currency=base_currency,
                to_currency=hedge_currency,
                from_amount=Decimal("10000"),
                comment=f"Currency hedge period {i + 1}",
            )
            transactions.append(tx)

    return transactions


def create_volatility_scenario(investor, start_date=date(2023, 1, 1), days=90):
    """Create FX rates during high volatility period."""

    rates = []

    for i in range(days):
        current_date = start_date + timedelta(days=i)

        # Simulate high volatility with larger variations
        volatility_factor = Decimal("0.05")  # 5% daily volatility

        base_rates = {
            "USDEUR": Decimal("0.92"),
            "USDGBP": Decimal("0.82"),
            "RUBUSD": Decimal("0.013"),
        }

        rate_data = {"investor": investor, "date": current_date}

        for pair, base_rate in base_rates.items():
            # High volatility variations
            variation = volatility_factor * (i % 10 - 5) / 5  # +/- volatility
            current_rate = base_rate + (base_rate * variation)

            # Add random spikes
            if i % 20 == 0:  # Spike every 20 days
                spike = Decimal("0.02") * (1 if i % 40 == 0 else -1)
                current_rate = current_rate + (base_rate * spike)

            rate_data[pair] = max(current_rate, Decimal("0.001"))

        fx_rate = FXRateFactory.create(**rate_data)
        rates.append(fx_rate)

    return rates
