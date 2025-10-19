"""
Test data factories for the portfolio management system.

This package contains factory classes for generating realistic test data
for assets, transactions, FX rates, and other portfolio components.
"""

from .asset_factory import AssetFactory
from .asset_factory import AssetWithPriceFactory
from .asset_factory import BondFactory
from .asset_factory import ETFFactory
from .asset_factory import EURStockFactory
from .asset_factory import GBPStockFactory
from .asset_factory import RestrictedAssetFactory
from .asset_factory import StockFactory
from .asset_factory import USDStockFactory
from .asset_factory import create_diversified_portfolio
from .asset_factory import create_multi_currency_portfolio
from .asset_factory import create_sector_portfolio
from .fx_factory import EURToUSDTransactionFactory
from .fx_factory import FXRateFactory
from .fx_factory import FXTransactionFactory
from .fx_factory import USDToEURTransactionFactory
from .fx_factory import create_cross_currency_rates
from .fx_factory import create_currency_hedge_sequence
from .fx_factory import create_fx_conversion_sequence
from .fx_factory import create_fx_rate_history
from .fx_factory import create_volatility_scenario
from .transaction_factory import BuyTransactionFactory
from .transaction_factory import DividendTransactionFactory
from .transaction_factory import LargeBuyTransactionFactory
from .transaction_factory import SellTransactionFactory
from .transaction_factory import SmallBuyTransactionFactory
from .transaction_factory import TransactionFactory
from .transaction_factory import create_buy_sell_sequence
from .transaction_factory import create_dividend_schedule
from .transaction_factory import create_dollar_cost_averaging
from .transaction_factory import create_portfolio_transactions
from .transaction_factory import create_tax_loss_harvesting

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
