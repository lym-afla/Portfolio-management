"""
Test data factories for the portfolio management system.

This package contains factory classes for generating realistic test data
for assets, transactions, FX rates, and other portfolio components.
"""

from .asset_factory import (
    AssetFactory,
    AssetWithPriceFactory,
    BondFactory,
    ETFFactory,
    EURStockFactory,
    GBPStockFactory,
    RestrictedAssetFactory,
    StockFactory,
    USDStockFactory,
    create_diversified_portfolio,
    create_multi_currency_portfolio,
    create_sector_portfolio,
)
from .fx_factory import (
    EURToUSDTransactionFactory,
    FXRateFactory,
    FXTransactionFactory,
    USDToEURTransactionFactory,
    create_cross_currency_rates,
    create_currency_hedge_sequence,
    create_fx_conversion_sequence,
    create_fx_rate_history,
    create_volatility_scenario,
)
from .transaction_factory import (
    BuyTransactionFactory,
    DividendTransactionFactory,
    LargeBuyTransactionFactory,
    SellTransactionFactory,
    SmallBuyTransactionFactory,
    TransactionFactory,
    create_buy_sell_sequence,
    create_dividend_schedule,
    create_dollar_cost_averaging,
    create_portfolio_transactions,
    create_tax_loss_harvesting,
)

__all__ = [
    # Asset factories
    "AssetFactory",
    "StockFactory",
    "BondFactory",
    "ETFFactory",
    "USDStockFactory",
    "EURStockFactory",
    "GBPStockFactory",
    "RestrictedAssetFactory",
    "AssetWithPriceFactory",
    "create_diversified_portfolio",
    "create_multi_currency_portfolio",
    "create_sector_portfolio",
    # Transaction factories
    "TransactionFactory",
    "BuyTransactionFactory",
    "SellTransactionFactory",
    "DividendTransactionFactory",
    "LargeBuyTransactionFactory",
    "SmallBuyTransactionFactory",
    "create_buy_sell_sequence",
    "create_dividend_schedule",
    "create_dollar_cost_averaging",
    "create_portfolio_transactions",
    "create_tax_loss_harvesting",
    # FX factories
    "FXRateFactory",
    "FXTransactionFactory",
    "USDToEURTransactionFactory",
    "EURToUSDTransactionFactory",
    "create_fx_rate_history",
    "create_cross_currency_rates",
    "create_fx_conversion_sequence",
    "create_currency_hedge_sequence",
    "create_volatility_scenario",
]
