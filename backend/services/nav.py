"""NAV (Net Asset Value) and IRR service.

Owns the portfolio-level NAV assembly and Internal Rate of Return (IRR)
calculations that previously lived at module level in ``core.portfolio_utils``:

- :func:`NAV_at_date` builds the NAV breakdown for a set of accounts at a
  single date (asset values plus cash balances, optionally split by asset
  type / currency / asset class / account).
- :func:`calculate_portfolio_cash` returns the total cash balance across
  accounts in a target currency.
- :func:`IRR` computes the XIRR-based internal rate of return for a portfolio
  or a single asset over a date range.
- :func:`get_fx_rate` is a cached wrapper around :func:`services.fx.get_rate`
  returning just the ``"FX"`` multiplier.
- :func:`get_accounts_for_security` and :func:`_portfolio_at_date` are the ORM
  lookups backing NAV assembly.
- :func:`merge_dictionaries`, :func:`_calculate_cash_flow`, and
  :func:`_calculate_portfolio_value` are small internal helpers.

Function names, parameter names, and positions are preserved verbatim from
``core.portfolio_utils`` so that existing keyword-argument callers (tests,
views, core utils) keep working unchanged after switching the import path to
``services.nav``.

Numeric safety: ``Decimal`` everywhere for money and rates. Never ``float``.

Circular-import notes:
- ``services.fx``, ``services.pricing``, ``services.positions``,
  ``services.accounts``, ``services.transactions`` do not import this module
  at top level, so importing them here is safe.
- ``common.models`` is imported lazily by the dependent services and at module
  top level here (NAV_at_date needs ``Accounts``); Django's app registry is
  ready by the time any caller invokes these functions.
"""

import datetime
import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Dict, List, Optional, Tuple, Union

from django.db.models import Q, QuerySet, Sum
from pyxirr import xirr

from common.models import Accounts, Assets, Transactions
from constants import (
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
)
from services import options
from services.accounts import balance as account_balance
from services.crypto import is_crypto, is_crypto_code
from services.fx import get_rate as fx_get_rate
from services.pricing import calculate_value_at_date
from services.positions import position
from services.transactions import (
    is_reward_transaction,
    total_cash_flow,
)

logger = logging.getLogger("dashboard")


def _portfolio_at_date(user_id: int, to_date: date, account_ids: List[int]) -> QuerySet[Assets]:
    """
    Get the portfolio assets for a user at a specific date for given broker accounts.

    :param user_id: The ID of the user
    :param to_date: The date to calculate the portfolio for
    :param account_ids: List of broker account IDs to filter by
    :return: QuerySet of Assets with non-zero total quantity
    """
    if not account_ids:
        return Assets.objects.none()

    return (
        Assets.objects.filter(
            investors__id=user_id,
            transactions__date__date__lte=to_date,
            transactions__account_id__in=account_ids,
        )
        .annotate(
            total_quantity=Sum(
                "transactions__quantity",
                filter=Q(
                    transactions__date__date__lte=to_date,
                    transactions__account_id__in=account_ids,
                ),
            )
        )
        .exclude(total_quantity=0)
        .distinct()
    )


# Get all the broker accounts associated with a given security
def get_accounts_for_security(user_id: int, security_id: int) -> QuerySet[Accounts]:
    """
    Get all broker accounts associated with a given security for a user.

    :param user_id: The ID of the user
    :param security_id: The ID of the security
    :return: QuerySet of Accounts
    """
    return Accounts.objects.filter(
        broker__investor__id=user_id, transactions__security_id=security_id
    ).distinct()


@lru_cache(maxsize=None)
def get_fx_rate(
    currency: str, target_currency: str, date: date, user: Optional[int] = None
) -> Decimal:
    """Get FX rate with caching for performance.

    Args:
        currency: Source currency code.
        target_currency: Target currency code.
        date: The date for the FX rate.
        user: User ID for user-specific rates (optional).

    Returns:
        Decimal: The FX rate.
    """
    return fx_get_rate(currency, target_currency, date, user)["FX"]


def merge_dictionaries(dict_1: dict, dict_2: dict) -> dict:
    """Merge two dictionaries, adding values for matching keys.

    Args:
        dict_1: First dictionary.
        dict_2: Second dictionary.

    Returns:
        dict: Merged dictionary with combined values.
    """
    dict_3 = dict_1.copy()  # Create a copy of dict_1
    for key, value in dict_2.items():
        dict_3[key] = (
            dict_3.get(key, 0) + value
        )  # Add values for common keys or set new values if key is not in dict_3
    return dict_3


def NAV_at_date(
    user_id: int,
    account_ids: Tuple[int],
    date: date,
    target_currency: str,
    breakdown: Tuple[str] = (),
) -> Dict:
    """Calculate NAV breakdown for selected accounts at a given date.

    Args:
        user_id: The ID of the user.
        account_ids: Tuple of account IDs to include in calculation.
        date: The date for NAV calculation.
        target_currency: Target currency for NAV values.
        breakdown: Tuple of breakdown categories (optional).

    Returns:
        dict: Dictionary containing Total NAV and breakdown values by category.
    """
    account_ids = list(account_ids)  # Convert tuple back to list for internal use
    breakdown = list(breakdown)  # Convert tuple back to list for internal use

    # Initialize analysis with default structure
    analysis = defaultdict(lambda: defaultdict(Decimal))
    analysis["Total NAV"] = Decimal(0)
    # Crypto is a first-class NAV class (Cash / Crypto / Securities, spec §4.3).
    # Initialize unconditionally so the key always appears in the output dict
    # (callers rely on it existing even for crypto-free portfolios).
    analysis["Crypto"] = defaultdict(Decimal)

    # Initialize breakdown categories even if empty
    if "asset_type" in breakdown:
        analysis["asset_type"] = defaultdict(Decimal)
    if "currency" in breakdown:
        analysis["currency"] = defaultdict(Decimal)
    if "asset_class" in breakdown:
        analysis["asset_class"] = defaultdict(Decimal)
    if "account" in breakdown:
        analysis["account"] = defaultdict(Decimal)

    portfolio = _portfolio_at_date(user_id, date, account_ids)
    portfolio_accounts = Accounts.objects.filter(broker__investor__id=user_id, id__in=account_ids)

    if not portfolio.exists() and not portfolio_accounts.exists():
        return analysis

    item_type = {
        "asset_type": "type",
        "currency": "currency",
        "asset_class": "exposure",
    }

    for security in portfolio:
        for account in portfolio_accounts:
            account_position = position(security, date, user_id, [account.id])
            if account_position == 0:
                continue

            # Options (sub-project 4, spec §5.4): short options are liabilities
            # valued at the manual mark (a Prices row on the OPTION asset) if
            # present, else at entry cost (the per-contract fill price from
            # ``calculate_buy_in_price``) so opening a short is NAV-neutral
            # against the BTC premium in the Crypto bucket. Handled BEFORE the
            # generic ``calculate_value_at_date`` path, which prices an option
            # at ``position × price`` with no contract_size — that would blow
            # the premium/liability match 100x (0.0154 BTC vs 0.000154 BTC
            # premium) and break the spec §3.4 NAV-neutral contract.
            #
            # The option does NOT enter the Crypto bucket (it is type="Option",
            # not "Crypto"); it appears in the Securities-side breakdowns under
            # its asset_type ("Option") as a negative value (short = liability).
            if options.is_option_asset(security):
                mark = options.option_mark_for_nav(security, date, user_id)
                if mark is None:
                    # Fall back to entry cost: the average per-contract fill
                    # price (sell-side for a short, buy-side for a long), in
                    # the OPTION's native currency (the settlement coin, e.g.
                    # BTC). We deliberately do NOT pass ``target_currency``:
                    # the FX conversion to target happens once, below, after
                    # the contract_size scaling — passing target_currency here
                    # would FX-convert the mark AND the final coin-notional
                    # (double conversion, 60000x too large for BTC->USD).
                    # ``calculate_buy_in_price`` returns None when there are no
                    # paid-entry transactions; treat that as a 0 mark.
                    from services.realized import calculate_buy_in_price
                    try:
                        mark = calculate_buy_in_price(
                            security, date, user_id, None, [account.id]
                        )
                    except (ValueError, TypeError):
                        mark = None
                    if mark is None:
                        mark = Decimal(0)
                # option_value (coin) = position(contracts) × mark(coin/contract)
                #                       × contract_size (coin-per-contract scale).
                # contract_size is required: the mark is coin-per-contract but
                # position is in contracts, so the coin-notional needs the size
                # to match the premium magnitude (spec §3.4 NAV-neutral table).
                option_value = (
                    account_position * Decimal(mark)
                    * options.contract_size_for_asset(security)
                )
                # FX-convert the coin-notional to the target currency. The
                # option's currency is the settlement coin (e.g. "BTC"); for a
                # crypto coin this chains through crypto_fx_rate (the coin's
                # USD price) -> target via the fiat FX graph.
                if security.currency != target_currency:
                    fx = get_fx_rate(security.currency, target_currency, date)
                    option_value *= fx
                analysis["Total NAV"] += option_value
                if "account" in breakdown:
                    analysis["account"][account.name] += option_value
                else:
                    for breakdown_type in breakdown:
                        key = getattr(security, item_type[breakdown_type])
                        analysis[breakdown_type][key] += option_value
                continue

            # Use calculate_value_at_date for proper bond notional handling.
            # An unpriced crypto coin (no Prices row and no Yahoo quote — e.g.
            # TRUMP) raises ValueError from crypto_usd_price via fx.get_rate.
            # Rather than crashing the whole NAV page (issue #5a), skip the
            # unpriced coin with a warning: it can't be valued, so it is
            # excluded from Total NAV until a price is imported.
            try:
                account_value = calculate_value_at_date(
                    security, date, user_id, target_currency, [account.id]
                )
            except ValueError:
                if is_crypto(security):
                    logger.warning(
                        "Skipping unpriced crypto coin %s in NAV at %s "
                        "(no USD price available)",
                        security.name,
                        date,
                    )
                    continue
                raise

            analysis["Total NAV"] += account_value

            # Crypto gets its own bucket; never the securities-side breakdowns.
            if is_crypto(security):
                analysis["Crypto"]["__total__"] += account_value
                analysis["Crypto"][security.name] += account_value
                continue

            if "account" in breakdown:
                analysis["account"][account.name] += account_value
            else:
                for breakdown_type in breakdown:
                    key = getattr(security, item_type[breakdown_type])
                    analysis[breakdown_type][key] += account_value

    # Option premiums/payouts (sub-project 4, spec §3.5): option rows carry
    # their premium (SELL, positive cash_flow) or payout (ITM settlement,
    # negative cash_flow for the writer) in the settlement coin. Route the
    # crypto-denominated ones into the Crypto bucket alongside ``position()``
    # and BTC fees so opening a short option is NAV-neutral (the premium in
    # the BTC bucket exactly offsets the option liability booked above at
    # entry-cost mark — spec §3.4 NAV-neutral table).
    #
    # Populates ONLY ``analysis["Crypto"]`` (for the per-coin breakdown), NOT
    # ``analysis["Total NAV"]``. The same option cash_flows are already
    # captured in Total NAV by the cash-balance loop below via
    # ``account_balance`` — which now rounds to the broker's cash_precision
    # (8 for crypto, services/accounts.py), so a 0.000154 BTC premium is no
    # longer dropped to 0.00. Adding them to Total NAV here as well would
    # double-count the premium (regression caught by
    # ``test_open_short_option_is_nav_neutral``). The raw ``cash_flow`` is
    # still read here (not ``account_balance``) so the Crypto-bucket
    # breakdown shows the full-precision coin value regardless of how the
    # cash side aggregates it.
    #
    # No double-count with the option-liability loop above: that values the
    # option CONTRACT (the liability, in the Securities-side breakdowns);
    # this values the option's CASH_FLOW (the premium/payout, in the Crypto
    # bucket). They are SEPARATE contributions that cancel for an open short
    # marked at entry cost (the spec's NAV-neutral contract).
    #
    # Only crypto-coin cash_flows route here: USD/EUR-denominated option
    # premiums belong in the fiat cash side, not the Crypto bucket. The
    # ``Assets(type="Crypto")`` lookup enforces this.
    option_cash_flows = Transactions.objects.filter(
        investor=user_id,
        date__date__lte=date,
        security__type="Option",
        cash_flow__isnull=False,
    ).filter(
        # Option open/close event types (the importer emits these for crypto
        # option fills and settlements; constants mirror transactions.py).
        type__in=[
            TRANSACTION_TYPE_CRYPTO_TRADE_IN,
            TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
            TRANSACTION_TYPE_OPTION_SETTLEMENT,
        ],
    )
    if account_ids:
        option_cash_flows = option_cash_flows.filter(account_id__in=account_ids)
    for tx in option_cash_flows:
        coin = (tx.currency or "").upper().strip()
        if not is_crypto_code(coin):
            # Skip fiat-denominated option cash_flows (USD/EUR premium).
            continue
        try:
            coin_to_target = get_fx_rate(coin, target_currency, date)
        except ValueError:
            logger.warning(
                "No FX rate for option cash_flow coin %s -> %s on %s; "
                "skipping from Crypto bucket",
                coin, target_currency, date,
            )
            continue
        cf_value = (tx.cash_flow or Decimal(0)) * coin_to_target
        if cf_value == 0:
            continue
        analysis["Crypto"]["__total__"] += cf_value
        analysis["Crypto"][coin] += cf_value

    # Handle cash balances
    for account in portfolio_accounts:
        broker_balance = account_balance(account, date)
        for currency, balance in broker_balance.items():
            # Defensive: if a currency in the cash dict has no FX rate
            # (e.g. an unpriced crypto coin that leaked in, or a currency
            # with no FX data yet), skip it with a warning rather than
            # crashing the whole NAV. The balance is still in the dict for
            # the per-currency breakdown; we just can't convert/total it.
            try:
                fx_rate = get_fx_rate(currency, target_currency, date)
            except ValueError:
                logger.warning(
                    "No FX rate for cash currency %s -> %s on %s; "
                    "skipping from NAV total",
                    currency,
                    target_currency,
                    date,
                )
                continue
            converted_balance = balance * fx_rate
            analysis["Total NAV"] += converted_balance

            if "account" in breakdown:
                analysis["account"][account.name] += converted_balance
            if "currency" in breakdown:
                analysis["currency"][currency] += converted_balance
            if "asset_type" in breakdown:
                analysis["asset_type"]["Cash"] += converted_balance
            if "asset_class" in breakdown:
                analysis["asset_class"]["Cash"] += converted_balance

    return dict(analysis)


# Helper for IRR calculation
def _calculate_portfolio_value(
    user_id: int,
    date: date,
    currency: Optional[str] = None,
    asset_id: Optional[int] = None,
    account_ids: Optional[List[int]] = None,
) -> Decimal:
    if asset_id is None:
        portfolio_value = NAV_at_date(user_id, tuple(account_ids), date, currency)["Total NAV"]
    else:
        asset = Assets.objects.get(id=asset_id, investors__id=user_id)
        try:
            portfolio_value = calculate_value_at_date(asset, date, user_id, currency, account_ids)
        except Exception:
            portfolio_value = Decimal(0)

    return portfolio_value


def calculate_portfolio_cash(
    user_id: int, account_ids: List[int], date: date, target_currency: str
) -> Decimal:
    """
    Calculate the total cash balance for a user's portfolio across multiple broker accounts.

    :param user_id: The ID of the user
    :param account_ids: List of broker account IDs to include in the calculation
    :param date: The date for which to calculate the cash balance
    :param target_currency: The currency to convert all cash balances to
    :return: The total cash balance as a Decimal
    """
    portfolio_accounts = Accounts.objects.filter(broker__investor__id=user_id, id__in=account_ids)

    cash_balance = {}
    for account in portfolio_accounts:
        cash_balance = merge_dictionaries(cash_balance, account_balance(account, date))

    cash = sum(
        balance * get_fx_rate(currency, target_currency, date)
        for currency, balance in cash_balance.items()
    )

    return Decimal(cash).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


MAX_IRR = Decimal("3")
IRR_PRECISION = Decimal("0.0001")


def IRR(
    user_id: int,
    date: date,
    currency: Optional[str] = None,
    asset_id: Optional[int] = None,
    account_ids: Optional[List[int]] = None,
    start_date: Optional[date] = None,
    cached_nav: Optional[Decimal] = None,
) -> Union[Decimal, str]:
    """
    Calculate the Internal Rate of Return (IRR) for a given portfolio or asset.

    :param user_id: The ID of the user
    :param date: The end date for IRR calculation
    :param currency: The currency to use for calculations (optional)
    :param asset_id: The ID of the specific asset to calculate IRR for (optional)
    :param account_ids: List of broker account IDs to include in the calculation (optional)
    :param start_date: The start date for IRR calculation (optional)
    :param cached_nav: Precalculated NAV value (optional)
    :return: The calculated IRR as a Decimal, or 'N/R' if not relevant,
               or 'N/A' if calculation fails
    """
    if cached_nav is not None:
        portfolio_value = cached_nav
    else:
        portfolio_value = _calculate_portfolio_value(user_id, date, currency, asset_id, account_ids)

    # Not relevant for short positions
    if portfolio_value < 0:
        return "N/R"

    cash_flows = []
    transaction_dates = []

    transactions = Transactions.objects.filter(investor__id=user_id, date__date__lte=date)
    if asset_id is not None:
        transactions = transactions.filter(security_id=asset_id)

    # For portfolio-level IRR (no specific asset), only external cash flows
    # matter. Internal items (broker commission, tax, interest income) are
    # already reflected in the terminal NAV / cash-out amounts; including
    # them would double-count.
    if asset_id is None:
        transactions = transactions.filter(
            type__in=[
                "Cash in",
                "Cash out",
                TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
                TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
            ]
        )

    if account_ids is not None:
        transactions = transactions.filter(account_id__in=account_ids)

    if start_date is not None:
        transactions = transactions.filter(date__gte=start_date)

        # Calculate start portfolio value if provided
        initial_value_date = start_date - timedelta(days=1)
        start_portfolio_value = _calculate_portfolio_value(
            user_id, initial_value_date, currency, asset_id, account_ids
        )

        if asset_id is not None:
            first_transaction = transactions.order_by("date").first()
            # Handle case where quantity might be None
            first_transaction_quantity = (
                first_transaction.quantity
                if first_transaction and first_transaction.quantity is not None
                else 0
            )
            if (start_portfolio_value < 0) or (
                start_portfolio_value == 0 and first_transaction_quantity < 0
            ):
                return "N/R"

        cash_flows.insert(0, -start_portfolio_value)
        transaction_dates.insert(0, initial_value_date)

    for transaction in transactions:
        cash_flow = _calculate_cash_flow(transaction)
        fx_rate = (
            get_fx_rate(transaction.currency.upper(), currency, transaction.date) if currency else 1
        )
        cash_flows.append(
            Decimal(cash_flow * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        transaction_dates.append(transaction.date)

    # Always add the final portfolio value as a separate terminal cash flow
    # Note: If there are transactions on this date, XIRR will sum them automatically
    # (multiple cash flows on the same date are allowed and summed)
    cash_flows.append(portfolio_value)
    transaction_dates.append(date)

    try:
        irr = Decimal(xirr(transaction_dates, cash_flows)).quantize(
            IRR_PRECISION, rounding=ROUND_HALF_UP
        )
        return irr if irr < MAX_IRR else "N/R"
    except Exception as e:
        print(f"Error calculating IRR: {e}")
        return "N/A"


def _calculate_cash_flow(transaction: Transactions) -> Decimal:
    """
    Calculate cash flow for a transaction for IRR calculation.

    Uses the centralized total_cash_flow() method and applies
    sign convention for IRR (negative = outflow, positive = inflow).
    """
    if is_reward_transaction(transaction):
        return Decimal(0)

    if transaction.type in [
        TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    ]:
        if transaction.quantity is not None and transaction.price is not None:
            # IRR treats crypto trades as asset cash flows: buys are negative,
            # sells are positive, while account cash balances stay unchanged.
            cf = -transaction.quantity * transaction.price
            # Add commission. A cross-currency commission (e.g. a BTC fee on a
            # BTC-USDT trade) must NOT be folded into the trade's primary-
            # currency cash flow — it depletes a different currency's balance,
            # handled by ``services.positions.position``. Only same-currency
            # commissions (or legacy rows with no commission_currency) are
            # applied. Mirrors services.transactions.total_cash_flow.
            if transaction.commission:
                comm_ccy = (getattr(transaction, "commission_currency", None) or "").upper()
                trade_ccy = (transaction.currency or "").upper()
                if not comm_ccy or comm_ccy == trade_ccy:
                    cf += Decimal(transaction.commission)
            # Round to the broker's cash_precision to absorb price-storage
            # residuals (matches total_cash_flow's rounding).
            cash_precision = 2
            if (
                hasattr(transaction, "account")
                and transaction.account
                and transaction.account.broker
            ):
                cash_precision = transaction.account.broker.cash_precision
            return cf.quantize(
                Decimal(1).scaleb(-cash_precision), rounding=ROUND_HALF_UP
            )
        return Decimal(0)

    # Get the cash flow using the centralized method
    cash_flow = total_cash_flow(transaction)

    # For IRR calculation, "Cash in" and "Cash out" need to be inverted
    # because they represent external cash flows
    if transaction.type in ["Cash in", "Cash out"]:
        return -cash_flow

    return cash_flow
