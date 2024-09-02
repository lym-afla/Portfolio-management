CURRENCY_CHOICES = (
    ('USD', '$'),
    ('EUR', '€'),
    ('GBP', '£'),
    ('RUB', '₽'),
    ('CHF', 'Fr')
)

TRANSACTION_TYPE_CASH_IN = 'Cash in'
TRANSACTION_TYPE_CASH_OUT = 'Cash out'
TRANSACTION_TYPE_BUY = 'Buy'
TRANSACTION_TYPE_SELL = 'Sell'
TRANSACTION_TYPE_DIVIDEND = 'Dividend'
TRANSACTION_TYPE_BROKER_COMMISSION = 'Broker commission'
TRANSACTION_TYPE_TAX = 'Tax'
TRANSACTION_TYPE_INTEREST_INCOME = 'Interest income'

TRANSACTION_TYPE_CHOICES = (
    (TRANSACTION_TYPE_CASH_IN, 'Cash in'),
    (TRANSACTION_TYPE_CASH_OUT, 'Cash out'),
    (TRANSACTION_TYPE_BUY, 'Buy'),
    (TRANSACTION_TYPE_SELL, 'Sell'),
    (TRANSACTION_TYPE_DIVIDEND, 'Dividend'),
    (TRANSACTION_TYPE_BROKER_COMMISSION, 'Broker commission'),
    (TRANSACTION_TYPE_TAX, 'Tax'),
    (TRANSACTION_TYPE_INTEREST_INCOME, 'Interest income'),
)

NAV_BARCHART_CHOICES = (
    ('Broker', 'Broker'),
    ('Asset type', 'Asset type'),
    ('Asset class', 'Asset class'),
    ('Currency', 'Currency'),
    ('No breakdown', 'No breakdown'),
)

ASSET_TYPE_CHOICES = (
    ('Stock', 'Stock'),
    ('Bond', 'Bond'),
    ('ETF', 'ETF'),
    ('Mutual fund', 'Mutual fund'),
    ('Option', 'Option'),
    ('Future', 'Future'),
)

EXPOSURE_CHOICES = (
    ('Equity', 'Equity'),
    ('FI', 'Fixed income'),
    ('FX', 'Forex'),
    ('Commodity', 'Commodity'),
)

TOLERANCE = 1e-7

YTD = 'ytd'
ALL_TIME = 'all_time'

BROKER_GROUPS = {
    'UK': [3, 6],
    # Add other groups as needed
}

# Names of mutual funds that are kept in FT database in pences, so need to be divided by 100
MUTUAL_FUNDS_IN_PENCES = [
    'Fidelity Index US Fund P Accumulation',
    'BlackRock Corporate Bond',
    'Fidelity Index Europe ex UK',
    'Baillie Gifford High Yield Bond',
    'Legal & General Multi-Index',
    'Barings Europe Select Trust',
    'Legal & General Global Technology Index',
    'Fidelity Index Emerging Markets',
    'Rathbone Ethical Bond',

]