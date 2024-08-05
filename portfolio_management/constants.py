CURRENCY_CHOICES = (
    ('USD', '$'),
    ('EUR', '€'),
    ('GBP', '£'),
    ('RUB', '₽'),
    ('CHF', '₣')
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
)

TOLERANCE = 1e-7

BROKER_GROUPS = {
    'UK': [3, 6],
    # Add other groups as needed
}
