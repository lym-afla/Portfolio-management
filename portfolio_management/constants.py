from tinkoff.invest import InstrumentType, OperationType

CURRENCY_CHOICES = (("USD", "$"), ("EUR", "€"), ("GBP", "£"), ("RUB", "₽"), ("CHF", "Fr"))

# Account selection types
ACCOUNT_TYPE_ALL = "all"
ACCOUNT_TYPE_INDIVIDUAL = "account"
ACCOUNT_TYPE_GROUP = "group"
ACCOUNT_TYPE_BROKER = "broker"

ACCOUNT_TYPE_CHOICES = [
    (ACCOUNT_TYPE_ALL, "All Accounts"),
    (ACCOUNT_TYPE_INDIVIDUAL, "Individual Account"),
    (ACCOUNT_TYPE_GROUP, "Account Group"),
    (ACCOUNT_TYPE_BROKER, "Broker"),
]

TRANSACTION_TYPE_CASH_IN = "Cash in"
TRANSACTION_TYPE_CASH_OUT = "Cash out"
TRANSACTION_TYPE_BUY = "Buy"
TRANSACTION_TYPE_SELL = "Sell"
TRANSACTION_TYPE_DIVIDEND = "Dividend"
TRANSACTION_TYPE_BROKER_COMMISSION = "Broker commission"
TRANSACTION_TYPE_TAX = "Tax"
TRANSACTION_TYPE_INTEREST_INCOME = "Interest income"

TRANSACTION_TYPE_CHOICES = (
    (TRANSACTION_TYPE_CASH_IN, "Cash in"),
    (TRANSACTION_TYPE_CASH_OUT, "Cash out"),
    (TRANSACTION_TYPE_BUY, "Buy"),
    (TRANSACTION_TYPE_SELL, "Sell"),
    (TRANSACTION_TYPE_DIVIDEND, "Dividend"),
    (TRANSACTION_TYPE_BROKER_COMMISSION, "Broker commission"),
    (TRANSACTION_TYPE_TAX, "Tax"),
    (TRANSACTION_TYPE_INTEREST_INCOME, "Interest income"),
)

NAV_BARCHART_CHOICES = (
    ("Broker", "Broker"),
    ("Asset type", "Asset type"),
    ("Asset class", "Asset class"),
    ("Currency", "Currency"),
    ("No breakdown", "No breakdown"),
)

ASSET_TYPE_CHOICES = (
    ("Stock", "Stock"),
    ("Bond", "Bond"),
    ("ETF", "ETF"),
    ("Mutual fund", "Mutual fund"),
    ("Option", "Option"),
    ("Future", "Future"),
)

EXPOSURE_CHOICES = (
    ("Equity", "Equity"),
    ("FI", "Fixed income"),
    ("FX", "Forex"),
    ("Commodity", "Commodity"),
)

TOLERANCE = 1e-7

YTD = "ytd"
ALL_TIME = "all_time"

BROKER_GROUPS = {
    "UK": [3, 6],
    # Add other groups as needed
}

# Names of mutual funds that are kept in FT database in pences, so need to be divided by 100
MUTUAL_FUNDS_IN_PENCES = [
    "Fidelity Index US Fund P Accumulation",
    "BlackRock Corporate Bond",
    "Fidelity Index Europe ex UK",
    "Baillie Gifford High Yield Bond",
    "Legal & General Multi-Index",
    "Barings Europe Select Trust",
    "Legal & General Global Technology Index",
    "Fidelity Index Emerging Markets",
    "Rathbone Ethical Bond",
    "iShares Physical Platinum ETC",
    "VT Garraway Absolute Equity",
    "ES River & Mercantile Global Recovery",
    "Baillie Gifford Japanese Smaller Companies",
    "Invesco MSCI World",
    "iShares Global Property Securities Equity",
    "Legal & General International Index Trust",
    "iShares Overseas Corporate Bond",
    "iShares Emerging Markets Equity",
    "Legal & General Pacific Index Trust",
    "iShares Pacific ex Japan Equity",
    "Fidelity Multi Asset Allocator",
    "Ninety One UK Smaller Companies",
]

# Broker identifiers for transaction import
ACCOUNT_IDENTIFIERS = {
    # 'Charles Stanley': {
    #     'keywords': ['Charles Stanley & Co. Limited',
    #                  '1903304',
    #                  'Contract Reference',
    #                  'Sedol',
    #                  'Stocks & Shares Subs'
    #                  ],
    #     'fuzzy_threshold': 59  # Adjust this threshold as needed
    # },
    "Charles Stanley – JISA || TL": {
        "keywords": [
            "Charles Stanley & Co. Limited",
            "1903304",
            "JISA - MASTER TIMOTHY LINIK",
            "4682720",
        ],
        "fuzzy_threshold": 65,  # Adjust this threshold as needed
    },
    "Charles Stanley – JISA || LL": {
        "keywords": [
            "Charles Stanley & Co. Limited",
            "1903304",
            "JISA - MASTER LEO LINIK",
            "4682719",
        ],
        "fuzzy_threshold": 65,  # Adjust this threshold as needed
    },
    "Charles Stanley – ISA": {
        "keywords": ["Charles Stanley & Co. Limited", "1903304", "Mr Y Linik", "4681921"],
        "fuzzy_threshold": 65,  # Adjust this threshold as needed
    },
    "Charles Stanley – Investment": {
        "keywords": [
            "Charles Stanley & Co. Limited",
            "1903304",
            "Mr Y Linik",
            "Investment",
            "4432757",
        ],
        "fuzzy_threshold": 65,  # Adjust this threshold as needed
    },
    "Charles Stanley – SIPP": {
        "keywords": [
            "Charles Stanley & Co. Limited",
            "1903304",
            "Charles Stanley Direct Sipp",
            "SIPP",
            "4455068",
        ],
        "fuzzy_threshold": 65,  # Adjust this threshold as needed
    },
    # Add more broker accounts here
    # 'Broker Name': {
    #     'keywords': ['Keyword 1', 'Keyword 2', 'Registration Number'],
    #     'fuzzy_threshold': 85
    # },
}

# Broker names
CHARLES_STANLEY_BROKER = "Charles Stanley"

OPERATION_TYPE_DESCRIPTIONS = {
    OperationType.OPERATION_TYPE_UNSPECIFIED: "Unspecified",
    OperationType.OPERATION_TYPE_INPUT: "Account Deposit",
    OperationType.OPERATION_TYPE_BOND_TAX: "Bond Coupon Tax",
    OperationType.OPERATION_TYPE_OUTPUT_SECURITIES: "Securities Withdrawal",
    OperationType.OPERATION_TYPE_OVERNIGHT: "Overnight REPO Income",
    OperationType.OPERATION_TYPE_TAX: "Tax Deduction",
    OperationType.OPERATION_TYPE_BOND_REPAYMENT_FULL: "Full Bond Repayment",
    OperationType.OPERATION_TYPE_SELL_CARD: "Sell Securities (Card)",
    OperationType.OPERATION_TYPE_DIVIDEND_TAX: "Dividend Tax",
    OperationType.OPERATION_TYPE_OUTPUT: "Funds Withdrawal",
    OperationType.OPERATION_TYPE_BOND_REPAYMENT: "Partial Bond Repayment",
    OperationType.OPERATION_TYPE_TAX_CORRECTION: "Tax Correction",
    OperationType.OPERATION_TYPE_SERVICE_FEE: "Account Service Fee",
    OperationType.OPERATION_TYPE_BENEFIT_TAX: "Material Benefit Tax",
    OperationType.OPERATION_TYPE_MARGIN_FEE: "Margin Position Fee",
    OperationType.OPERATION_TYPE_BUY: "Buy Securities",
    OperationType.OPERATION_TYPE_BUY_CARD: "Buy Securities (Card)",
    OperationType.OPERATION_TYPE_INPUT_SECURITIES: "Securities Deposit",
    OperationType.OPERATION_TYPE_SELL_MARGIN: "Margin Call Sell",
    OperationType.OPERATION_TYPE_BROKER_FEE: "Broker Commission",
    OperationType.OPERATION_TYPE_BUY_MARGIN: "Margin Call Buy",
    OperationType.OPERATION_TYPE_DIVIDEND: "Dividend Payment",
    OperationType.OPERATION_TYPE_SELL: "Sell Securities",
    OperationType.OPERATION_TYPE_COUPON: "Coupon Payment",
    OperationType.OPERATION_TYPE_SUCCESS_FEE: "Success Fee",
    OperationType.OPERATION_TYPE_DIVIDEND_TRANSFER: "Dividend Transfer",
    OperationType.OPERATION_TYPE_ACCRUING_VARMARGIN: "Variation Margin Credit",
    OperationType.OPERATION_TYPE_WRITING_OFF_VARMARGIN: "Variation Margin Debit",
    OperationType.OPERATION_TYPE_DELIVERY_BUY: "Futures Expiration Buy",
    OperationType.OPERATION_TYPE_DELIVERY_SELL: "Futures Expiration Sell",
    OperationType.OPERATION_TYPE_TRACK_MFEE: "Auto-follow Account Management Fee",
    OperationType.OPERATION_TYPE_TRACK_PFEE: "Auto-follow Account Performance Fee",
    OperationType.OPERATION_TYPE_TAX_PROGRESSIVE: "Progressive Tax (15%)",
    OperationType.OPERATION_TYPE_BOND_TAX_PROGRESSIVE: "Progressive Bond Coupon Tax (15%)",
    OperationType.OPERATION_TYPE_DIVIDEND_TAX_PROGRESSIVE: "Progressive Dividend Tax (15%)",
    OperationType.OPERATION_TYPE_BENEFIT_TAX_PROGRESSIVE: "Progressive Material Benefit Tax (15%)",
    OperationType.OPERATION_TYPE_TAX_CORRECTION_PROGRESSIVE: "Progressive Tax Correction (15%)",
    OperationType.OPERATION_TYPE_TAX_REPO_PROGRESSIVE: "Progressive REPO Tax (15%)",
    OperationType.OPERATION_TYPE_TAX_REPO: "REPO Tax",
    OperationType.OPERATION_TYPE_TAX_REPO_HOLD: "REPO Tax Hold",
    OperationType.OPERATION_TYPE_TAX_REPO_REFUND: "REPO Tax Refund",
    OperationType.OPERATION_TYPE_TAX_REPO_HOLD_PROGRESSIVE: "Progressive REPO Tax Hold (15%)",
    OperationType.OPERATION_TYPE_TAX_REPO_REFUND_PROGRESSIVE: "Progressive REPO Tax Refund (15%)",
    OperationType.OPERATION_TYPE_DIV_EXT: "Dividend Payment to Card",
    OperationType.OPERATION_TYPE_TAX_CORRECTION_COUPON: "Coupon Tax Correction",
    OperationType.OPERATION_TYPE_CASH_FEE: "Cash Balance Fee",
    OperationType.OPERATION_TYPE_OUT_FEE: "Withdrawal Fee",
    OperationType.OPERATION_TYPE_OUT_STAMP_DUTY: "Stamp Duty",
    OperationType.OPERATION_TYPE_OUTPUT_SWIFT: "SWIFT Transfer Out",
    OperationType.OPERATION_TYPE_INPUT_SWIFT: "SWIFT Transfer In",
    OperationType.OPERATION_TYPE_OUTPUT_ACQUIRING: "Transfer to Card",
    OperationType.OPERATION_TYPE_INPUT_ACQUIRING: "Transfer from Card",
    OperationType.OPERATION_TYPE_OUTPUT_PENALTY: "Withdrawal Penalty",
    OperationType.OPERATION_TYPE_ADVICE_FEE: "Advisory Service Fee",
    OperationType.OPERATION_TYPE_TRANS_IIS_BS: "Transfer from IIS to Brokerage Account",
    OperationType.OPERATION_TYPE_TRANS_BS_BS: "Transfer between Brokerage Accounts",
    OperationType.OPERATION_TYPE_OUT_MULTI: "Multi-currency Withdrawal",
    OperationType.OPERATION_TYPE_INP_MULTI: "Multi-currency Deposit",
    OperationType.OPERATION_TYPE_OVER_PLACEMENT: "Overnight Placement",
    OperationType.OPERATION_TYPE_OVER_COM: "Overnight Commission",
    OperationType.OPERATION_TYPE_OVER_INCOME: "Overnight Income",
    OperationType.OPERATION_TYPE_OPTION_EXPIRATION: "Option Expiration",
}

# Dictionary for instrument kinds
INSTRUMENT_KIND_DESCRIPTIONS = {
    InstrumentType.INSTRUMENT_TYPE_UNSPECIFIED: "Unspecified",
    InstrumentType.INSTRUMENT_TYPE_BOND: "Bond",
    InstrumentType.INSTRUMENT_TYPE_SHARE: "Share",
    InstrumentType.INSTRUMENT_TYPE_CURRENCY: "Currency",
    InstrumentType.INSTRUMENT_TYPE_ETF: "ETF",
    InstrumentType.INSTRUMENT_TYPE_FUTURES: "Futures",
    InstrumentType.INSTRUMENT_TYPE_SP: "Structured Product",
    InstrumentType.INSTRUMENT_TYPE_OPTION: "Option",
    InstrumentType.INSTRUMENT_TYPE_CLEARING_CERTIFICATE: "Clearing Certificate",
}

# Tinkoff account types
TINKOFF_ACCOUNT_TYPES = {0: "UNSPECIFIED", 1: "TINKOFF", 2: "TINKOFF_IIS", 3: "INVEST_BOX"}

# Tinkoff account statuses
TINKOFF_ACCOUNT_STATUSES = {0: "UNSPECIFIED", 1: "NEW", 2: "OPEN", 3: "CLOSED"}
