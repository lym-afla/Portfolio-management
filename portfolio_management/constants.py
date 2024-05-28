CURRENCY_CHOICES = (
    ('USD', '$'),
    ('EUR', '€'),
    ('GBP', '£'),
    ('RUB', '₽'),
)

TRANSACTION_TYPE_CHOICES = (
    ('Cash in', 'Cash in'),
    ('Cash out', 'Cash out'),
    ('Buy', 'Buy'),
    ('Sell', 'Sell'),
    ('Dividend', 'Dividend'),
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