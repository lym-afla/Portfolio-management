"""
Factory classes for creating test assets.

Provides realistic asset data for various testing scenarios.
"""

from datetime import date, timedelta
from decimal import Decimal

import factory
from factory import fuzzy

from common.models import Assets, Brokers
from users.models import CustomUser


class AssetFactory(factory.django.DjangoModelFactory):
    """Factory for creating Assets with realistic data."""

    class Meta:
        """Meta class for AssetFactory."""

        model = Assets

    type = fuzzy.FuzzyChoice(["Stock", "Bond", "ETF", "Fund"])
    ISIN = factory.Faker("bothify", text="??##########")  # 12-character ISIN
    name = factory.Faker("company")
    currency = fuzzy.FuzzyChoice(["USD", "EUR", "GBP", "CHF"])
    exposure = fuzzy.FuzzyChoice(["Equity", "Fixed Income", "Mixed", "Alternative"])
    restricted = False
    comment = factory.Faker("text", max_nb_chars=200)
    data_source = fuzzy.FuzzyChoice(["YAHOO", "FT", ""])
    update_link = factory.Faker("url")
    yahoo_symbol = factory.Faker("bothify", text="????")

    @factory.post_generation
    def investors(self, create, extracted, **kwargs):
        """Add investors to the asset."""
        if not create:
            return

        if extracted:
            for investor in extracted:
                self.investors.add(investor)

    @factory.post_generation
    def brokers(self, create, extracted, **kwargs):
        """Add brokers to the asset."""
        if not create:
            return

        if extracted:
            for broker in extracted:
                self.brokers.add(broker)


class StockFactory(AssetFactory):
    """Factory for creating stock assets."""

    type = "Stock"
    exposure = "Equity"
    data_source = "YAHOO"

    @factory.lazy_attribute
    def name(self) -> str:
        """Name for stock assets."""
        return f"{self.ISIN[:3]} Stock Corp"


class BondFactory(AssetFactory):
    """Factory for creating bond assets."""

    type = "Bond"
    exposure = "Fixed Income"

    @factory.lazy_attribute
    def name(self) -> str:
        """Name for bond assets."""
        return f"Bond {self.ISIN[-6:]} {date.today().year + 5}"


class ETFFactory(AssetFactory):
    """Factory for creating ETF assets."""

    type = "ETF"
    exposure = "Equity"
    data_source = "YAHOO"

    @factory.lazy_attribute
    def name(self) -> str:
        """Name for ETF assets."""
        return f"{self.ISIN[:3]} ETF"


class USDStockFactory(StockFactory):
    """Factory for creating USD-denominated stocks."""

    currency = "USD"

    @factory.lazy_attribute
    def ISIN(self) -> str:
        """ISIN for USD-denominated stocks."""
        return f"US{self.faker.bothify(text='#########')}"


class EURStockFactory(StockFactory):
    """Factory for creating EUR-denominated stocks."""

    currency = "EUR"

    @factory.lazy_attribute
    def ISIN(self) -> str:
        """ISIN for EUR-denominated stocks."""
        return f"DE{self.faker.bothify(text='#########')}"


class GBPStockFactory(StockFactory):
    """Factory for creating GBP-denominated stocks."""

    currency = "GBP"

    @factory.lazy_attribute
    def ISIN(self) -> str:
        """ISIN for GBP-denominated stocks."""
        return f"GB{self.faker.bothify(text='#########')}"


class RestrictedAssetFactory(AssetFactory):
    """Factory for creating restricted assets."""

    restricted = True
    comment = "Restricted asset for testing purposes"


class AssetWithPriceFactory(AssetFactory):
    """Factory that creates assets with associated price history."""

    @factory.post_generation
    def create_price_history(self, create, extracted, **kwargs):
        """Create price history for the asset."""
        if not create:
            return

        from common.models import Prices

        # Default parameters
        start_date = kwargs.get("start_date", date(2023, 1, 1))
        days = kwargs.get("days", 365)
        base_price = kwargs.get("base_price", Decimal("100.00"))
        volatility = kwargs.get("volatility", Decimal("0.02"))

        current_price = base_price

        for i in range(days):
            current_date = start_date + timedelta(days=i)

            # Simulate price movement with some randomness
            price_change = Decimal(
                str(self.faker.pyfloat(min_value=-float(volatility), max_value=float(volatility)))
            )
            current_price = current_price * (Decimal("1") + price_change)

            # Ensure price doesn't go below 1
            current_price = max(current_price, Decimal("1.00"))

            Prices.objects.create(
                date=current_date,
                security=self,
                price=current_price.quantize(Decimal("0.01")),
            )


# Batch creation utilities
def create_diversified_portfolio(
    user: CustomUser, brokers: list[Brokers], num_assets=10
) -> list[Assets]:
    """Create a diversified portfolio with various asset types."""
    assets = []

    # Create a mix of different asset types
    for i in range(num_assets):
        if i < num_assets * 0.6:  # 60% stocks
            asset = USDStockFactory.create(investors=[user], brokers=brokers)
        elif i < num_assets * 0.8:  # 20% bonds
            asset = BondFactory.create(investors=[user], brokers=brokers)
        else:  # 20% ETFs
            asset = ETFFactory.create(investors=[user], brokers=brokers)

        assets.append(asset)

    return assets


def create_multi_currency_portfolio(
    user: CustomUser, brokers: list[Brokers], currencies=None
) -> list[Assets]:
    """Create assets in multiple currencies."""
    if currencies is None:
        currencies = ["USD", "EUR", "GBP"]

    assets = []
    factories = {"USD": USDStockFactory, "EUR": EURStockFactory, "GBP": GBPStockFactory}

    for currency in currencies:
        factory = factories.get(currency, USDStockFactory)
        for _ in range(3):  # 3 assets per currency
            asset = factory.create(investors=[user], brokers=brokers)
            assets.append(asset)

    return assets


def create_sector_portfolio(
    user: CustomUser, brokers: list[Brokers], sector: str, num_assets=5
) -> list[Assets]:
    """Create a portfolio focused on a specific sector."""
    sector_names = {
        "technology": [
            "Tech Corp",
            "Software Inc",
            "Digital Systems",
            "Cloud Solutions",
            "AI Platforms",
        ],
        "healthcare": [
            "MediCorp",
            "Pharma Solutions",
            "Health Tech",
            "Bio Medical",
            "Care Systems",
        ],
        "finance": [
            "Finance Corp",
            "Bank Solutions",
            "Investment Tech",
            "Payment Systems",
            "Insurance Tech",
        ],
        "energy": [
            "Energy Corp",
            "Oil & Gas",
            "Renewable Power",
            "Electric Solutions",
            "Green Energy",
        ],
    }

    assets = []
    names = sector_names.get(sector, [f"{sector.title()} Corp {i}" for i in range(num_assets)])

    for i, name in enumerate(names[:num_assets]):
        asset = StockFactory.create(
            investors=[user], brokers=brokers, name=name, ISIN=f"SECTOR{i:02d}########"
        )
        assets.append(asset)

    return assets
