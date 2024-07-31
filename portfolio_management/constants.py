CURRENCY_CHOICES = (
    ('USD', '$'),
    ('EUR', '€'),
    ('GBP', '£'),
    ('RUB', '₽'),
    ('CHF', 'SF')
)

TRANSACTION_TYPE_CHOICES = (
    ('Cash in', 'Cash in'),
    ('Cash out', 'Cash out'),
    ('Buy', 'Buy'),
    ('Sell', 'Sell'),
    ('Dividend', 'Dividend'),
    ('Broker commission', 'Broker commission'),
    ('Tax', 'Tax'),
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
