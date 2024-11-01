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
    'iShares Physical Platinum ETC',
    'VT Garraway Absolute Equity',
    'ES River & Mercantile Global Recovery',
    'Baillie Gifford Japanese Smaller Companies',
    'Invesco MSCI World',
    'iShares Global Property Securities Equity',
    'Legal & General International Index Trust',
    'iShares Overseas Corporate Bond',
    'iShares Emerging Markets Equity',
    'Legal & General Pacific Index Trust',
    'iShares Pacific ex Japan Equity',
    'Fidelity Multi Asset Allocator',
    'Ninety One UK Smaller Companies',
]

# Broker identifiers for transaction import
BROKER_IDENTIFIERS = {
    # 'Charles Stanley': {
    #     'keywords': ['Charles Stanley & Co. Limited',
    #                  '1903304',
    #                  'Contract Reference',
    #                  'Sedol',
    #                  'Stocks & Shares Subs'
    #                  ],
    #     'fuzzy_threshold': 59  # Adjust this threshold as needed
    # },
    'Charles Stanley – JISA || TL': {
        'keywords': ['Charles Stanley & Co. Limited',
                     '1903304',
                     'JISA - MASTER TIMOTHY LINIK',
                     '4682720'
                     ],
        'fuzzy_threshold': 65  # Adjust this threshold as needed
    },
    'Charles Stanley – JISA || LL': {
        'keywords': ['Charles Stanley & Co. Limited',
                     '1903304',
                     'JISA - MASTER LEO LINIK',
                     '4682719'
                     ],
        'fuzzy_threshold': 65  # Adjust this threshold as needed
    },
    'Charles Stanley – ISA': {
        'keywords': ['Charles Stanley & Co. Limited',
                     '1903304',
                     'Mr Y Linik',
                     '4681921'
                     ],
        'fuzzy_threshold': 65  # Adjust this threshold as needed
    },
    'Charles Stanley – Investment': {
        'keywords': ['Charles Stanley & Co. Limited',
                     '1903304',
                     'Mr Y Linik',
                     'Investment',
                     '4432757'
                     ],
        'fuzzy_threshold': 65  # Adjust this threshold as needed
    },
    'Charles Stanley – SIPP': {
        'keywords': ['Charles Stanley & Co. Limited',
                     '1903304',
                     'Charles Stanley Direct Sipp',
                     'SIPP',
                     '4455068'
                     ],
        'fuzzy_threshold': 65  # Adjust this threshold as needed
    },
    # Add more brokers here
    # 'Broker Name': {
    #     'keywords': ['Keyword 1', 'Keyword 2', 'Registration Number'],
    #     'fuzzy_threshold': 85
    # },
}

# Broker names
CHARLES_STANLEY_BROKER = 'Charles Stanley'