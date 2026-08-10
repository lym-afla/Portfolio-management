"""Account balance service.

Owns the account-level cash-balance and currency-collection logic that
previously lived as methods on the ``Accounts`` model (``common.models``):

- :func:`get_currencies` iterates an account's transactions collecting the
  distinct set of currency codes.
- :func:`balance` computes the per-currency cash balance as of a given date
  by summing :func:`services.transactions.total_cash_flow` over the account's
  transactions and :func:`services.transactions.get_cash_flow_by_currency`
  over the account's FX transactions.

Parameter names and positions are preserved verbatim from the original model
methods so that existing keyword-argument callers (tests, views, core utils)
keep working unchanged after switching to ``func(account, ...)``. Only
``self`` becomes ``account``.

Numeric safety: ``Decimal`` everywhere for money. Never ``float``.

Import graph: this module imports :mod:`services.transactions` at its top
level. ``services.transactions`` imports :mod:`services.fx`, which imports
the ``FX`` model from ``common.models`` — but none of those modules import
this one, so the import is safe. ``common.models`` imports this module
lazily (deferred, inside caller method bodies) because importing it at
module top level would also pull in ``services.fx``.
"""

import logging
from decimal import Decimal

from constants import (
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
)
from services.transactions import (
    get_cash_flow_by_currency,
    total_cash_flow,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# get_currencies
# ---------------------------------------------------------------------------


def get_currencies(account):
    """Get currencies for this account."""
    currencies = set()
    for transaction in account.transactions.all():
        currencies.add(transaction.currency)
    return currencies


# ---------------------------------------------------------------------------
# balance
# ---------------------------------------------------------------------------


def balance(account, date):
    """
    Calculate account cash balance as of a given date.

    Uses the centralized total_cash_flow() method for consistency.
    """
    balance_result = {}

    # Filter transactions up to and including the given date
    # Use date__date__lte to compare only the date portion, ignoring time component
    # of the DateTimeField

    # Process regular transactions using centralized cash flow calculation
    transactions = account.transactions.filter(date__date__lte=date)
    for transaction in transactions:
        cash_flow = total_cash_flow(transaction)
        if cash_flow == 0 and transaction.type in [
            TRANSACTION_TYPE_CRYPTO_REWARD,
            TRANSACTION_TYPE_CRYPTO_TRADE_IN,
            TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
            TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
            TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
        ]:
            continue
        balance_result[transaction.currency] = (
            balance_result.get(transaction.currency, Decimal(0)) + cash_flow
        )

    # Calculate balance from FX transactions using centralized method
    fx_transactions = account.fx_transactions.filter(date__date__lte=date)
    for fx_transaction in fx_transactions:
        # Get all currencies involved in this FX transaction
        involved_currencies = {
            fx_transaction.from_currency,
            fx_transaction.to_currency,
        }
        if fx_transaction.commission_currency:
            involved_currencies.add(fx_transaction.commission_currency)

        # Update balance for each currency using centralized method
        for currency in involved_currencies:
            cash_flow = get_cash_flow_by_currency(fx_transaction, currency)
            balance_result[currency] = balance_result.get(currency, Decimal(0)) + cash_flow

    for key, value in balance_result.items():
        balance_result[key] = round(Decimal(value), 2)

    return balance_result
