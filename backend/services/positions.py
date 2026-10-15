"""Positions service.

Owns the position-tracking and date-walking logic that previously lived on
the ``Assets`` model:

- :func:`position` sums ``quantity`` over the asset's transactions up to a
  date, filtered by investor and (optionally) accounts.
- :func:`entry_dates` walks ordered transactions and records each date where
  the running position goes from zero to non-zero.
- :func:`exit_dates` walks ordered transactions and records each date where
  the running position goes from non-zero to zero.
- :func:`get_accounts_with_positions` lists the account IDs that still hold a
  non-zero position of the asset on a given date.
- :func:`investment_date` returns the earliest transaction date for the asset.

Parameter names and positions are preserved verbatim from the original model
methods so that existing keyword-argument callers (tests, views, core utils)
keep working unchanged after switching to ``func(asset, ...)``.

Numeric safety: ``position`` returns a ``Decimal`` (rounded to 6 dp). Never
``float``.

Circular-import notes:
- This module does not import ``common.models`` at its top level. The asset is
  passed in by callers, so there is no circular-import risk. ``services.pricing``
  imports this module at its top level safely.
- ``common.models`` imports this module lazily (deferred, inside method bodies
  via the ``_positions_*`` bridge helpers) because importing it at module top
  level would pull in ``services.pricing`` -> ``services.fx`` -> ``common.models``
  on first load.
"""

import logging
from datetime import datetime
from decimal import Decimal

from django.db.models import Sum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# position
# ---------------------------------------------------------------------------


def position(asset, date, investor, account_ids=None):
    """Get the position of an asset at a given date.

    Args:
        asset: The ``Assets`` instance.
        date: Date/datetime to sum quantities up to (inclusive).
        investor: Investor to filter transactions by.
        account_ids: Optional list of account IDs to restrict the sum to.

    Returns:
        Decimal: Total quantity held at ``date``, rounded to 6 dp. Returns
        ``Decimal(0)`` when there are no matching transactions.

    Cross-currency commissions: for a Crypto asset, any commission on another
    transaction whose ``commission_currency`` matches the asset's name depletes
    this asset's holding. A BTC fee of ``-0.001`` on a BTC-USDT trade is stored
    as ``commission=-0.001`` on the USDT trade row; the BTC asset's position
    must reflect that outflow, so net BTC = ``+1`` (qty) ``+ (-0.001)``
    (commission) = ``+0.999``. The commission is stored signed (negative for a
    fee outflow), so the negative value is ADDED to reduce the position.
    """
    query = asset.transactions.filter(date__date__lte=date, investor=investor)
    if account_ids is not None:
        query = query.filter(account_id__in=account_ids)
    total_quantity = query.aggregate(total=Sum("quantity"))["total"]
    result = Decimal(total_quantity) if total_quantity else Decimal(0)

    # Cross-currency commissions deplete the fee-currency asset's position.
    # A BTC fee on a BTC-USDT trade reduces the BTC holding even though the
    # commission lives on the USDT trade row. Only applies to crypto assets
    # (type="Crypto") whose name is a commission_currency on other rows.
    # Lazy import to avoid a circular dependency (common.models imports this
    # module lazily via the _positions_* bridge helpers).
    #
    # Note: the quantity sum above sums ONLY the ``quantity`` field; the
    # ``commission`` field is independent. Even when a trade row's own security
    # is this asset (e.g. a BTC-USDT buy with a BTC fee has security=BTC,
    # quantity=1, commission=-0.001), the commission is NOT in the quantity
    # sum, so adding it here is correct and not a double-count. Net BTC
    # = +1 (qty) + (-0.001) (commission) = +0.999.
    if asset.type == "Crypto":
        from common.models import Transactions

        comm_query = Transactions.objects.filter(
            investor=investor,
            commission_currency=asset.name,
            date__date__lte=date,
            commission__isnull=False,
        )
        if account_ids is not None:
            comm_query = comm_query.filter(account_id__in=account_ids)
        comm_total = comm_query.aggregate(total=Sum("commission"))["total"]
        if comm_total:
            # commission is signed (negative for a fee outflow); adding the
            # negative value reduces the position.
            result += Decimal(comm_total)

        # Coin-settled option premiums/payouts are real coin-balance movements.
        # The option row's cash_flow carries the signed premium (+received on
        # SELL, -paid on BUY) or payout (-writer ITM payment, +buyer receipt).
        # The exchange's coin balance includes them (verified against the OKX
        # CSV running-balance: buys - fees - transfers + premium ~= 0), so the
        # coin's position must too. Without this the BTC position after a
        # written-option cycle lands on -fee-dust instead of ~0.
        opt_query = Transactions.objects.filter(
            investor=investor,
            currency=asset.name,
            date__date__lte=date,
            cash_flow__isnull=False,
            security__type="Option",
        )
        if account_ids is not None:
            opt_query = opt_query.filter(account_id__in=account_ids)
        opt_total = opt_query.aggregate(total=Sum("cash_flow"))["total"]
        if opt_total:
            result += Decimal(opt_total)

    return round(result, 6)


# ---------------------------------------------------------------------------
# get_accounts_with_positions
# ---------------------------------------------------------------------------


def get_accounts_with_positions(asset, date, investor):
    """Get list of accounts with non-zero positions at a given date.

    Args:
        asset: The ``Assets`` instance.
        date: Date to check positions at.
        investor: Investor to check for.

    Returns:
        list: List of account IDs with non-zero positions.
    """
    # Get all accounts that have transactions for this security
    account_ids = (
        asset.transactions.filter(investor=investor, quantity__isnull=False)
        .values_list("account_id", flat=True)
        .distinct()
    )

    # Check position for each account and keep only non-zero ones
    accounts_with_positions = []
    for account_id in account_ids:
        account_position = position(
            asset, date=date, investor=investor, account_ids=[account_id]
        )
        if account_position and account_position != 0:
            accounts_with_positions.append(account_id)

    return accounts_with_positions


# ---------------------------------------------------------------------------
# get_account_holdings
# ---------------------------------------------------------------------------


def get_account_holdings(asset, date, investor):
    """Per-account remaining holdings of an asset as of a date.

    The read model behind the security detail page's "Currently held with" /
    "Previously held with" context. One row per account whose activity could
    contribute to the asset's position up to ``date``:

    - ``quantity`` is the account's canonical remaining position at ``date``
      (the same :func:`position` sums the position charts use — never lifetime
      buys), as an exact Decimal string rounded to 6 dp.
    - ``status`` is ``"open"`` when the remaining position is non-zero and
      ``"closed"`` when the account held the asset at some point up to
      ``date`` but the remaining position is zero. Partial disposals stay
      ``"open"``; a holding sold out and bought again is ``"open"``.

    Candidate discovery covers the SAME sources canonical :func:`position`
    reads, under the same investor and historical cutoff: direct non-zero
    quantity rows always, plus — for Crypto assets, mirroring ``position``'s
    own gate — commissions paid in this coin and coin-settled option
    cashflows recorded on other securities' rows. Records that could not
    contribute (zero/null quantity, zero commission or cashflow) establish
    nothing: an account with no real holding event never appears, not even
    as "closed".

    Returns:
        list[dict]: ``{"account_id", "quantity", "status"}`` rows, open
        accounts first (each group ordered by account id).
    """
    scoped = dict(investor=investor, date__date__lte=date, account_id__isnull=False)

    # Direct rows that could move the position: a real (non-zero) quantity.
    account_ids = set(
        asset.transactions.filter(**scoped, quantity__isnull=False)
        .exclude(quantity=0)
        .values_list("account_id", flat=True)
    )

    # position() folds in these indirect sources ONLY for Crypto assets;
    # discovery mirrors that gate so non-crypto accounts never surface from
    # rows their position never read.
    if asset.type == "Crypto":
        from common.models import Transactions

        account_ids.update(
            Transactions.objects.filter(**scoped, commission_currency=asset.name)
            .exclude(commission__isnull=True)
            .exclude(commission=0)
            .values_list("account_id", flat=True)
        )
        account_ids.update(
            Transactions.objects.filter(
                **scoped, currency=asset.name, security__type="Option", cash_flow__isnull=False
            )
            .exclude(cash_flow=0)
            .values_list("account_id", flat=True)
        )

    holdings = []
    for account_id in sorted(account_ids):
        quantity = position(asset, date=date, investor=investor, account_ids=[account_id])
        holdings.append(
            {
                "account_id": account_id,
                "quantity": str(quantity),
                "status": "open" if quantity != 0 else "closed",
            }
        )
    holdings.sort(key=lambda row: (0 if row["status"] == "open" else 1, row["account_id"]))
    return holdings


# ---------------------------------------------------------------------------
# investment_date
# ---------------------------------------------------------------------------


def investment_date(asset, investor, account_ids=None):
    """Get the investment date for this security.

    Args:
        asset: The ``Assets`` instance.
        investor: Investor to filter transactions by.
        account_ids: Optional list of account IDs to filter by.

    Returns:
        The earliest transaction date for the asset, or ``None`` when there
        are no matching transactions.
    """
    queryset = asset.transactions.filter(investor=investor)
    if account_ids:
        queryset = queryset.filter(account_id__in=account_ids)
    query = queryset.order_by("date").values_list("date", flat=True).first()
    return query


# ---------------------------------------------------------------------------
# entry_dates
# ---------------------------------------------------------------------------


def entry_dates(asset, date_as_of, investor, account_ids=None, start_date=None):
    """Get a list of dates when the position changes from 0 to non-zero.

    Args:
        asset: The ``Assets`` instance.
        date_as_of: Cutoff date/datetime (inclusive) for transactions.
        investor: Investor to filter transactions by.
        account_ids: Optional list of account IDs to filter by.
        start_date: Optional lower bound; transitions strictly before this
            date advance the running position but are not recorded.

    Returns:
        list: Datetimes at which the position went from zero to non-zero.
    """
    transactions = asset.transactions.filter(quantity__isnull=False, investor=investor)
    if isinstance(date_as_of, datetime):
        transactions = transactions.filter(date__lte=date_as_of)
    else:
        transactions = transactions.filter(date__date__lte=date_as_of)
    if account_ids is not None:
        transactions = transactions.filter(account_id__in=account_ids)

    transactions = transactions.order_by("date", "id")

    entry_dates_list = []
    running_position = 0

    for transaction in transactions:
        new_position = running_position + transaction.quantity
        if running_position == 0 and new_position != 0:
            if start_date is not None:
                if transaction.date < start_date:
                    running_position = new_position
                    continue
            entry_dates_list.append(transaction.date)

        running_position = new_position

    return entry_dates_list


# ---------------------------------------------------------------------------
# exit_dates
# ---------------------------------------------------------------------------


def exit_dates(asset, end_date, investor, account_ids=None, start_date=None):
    """Get a list of dates when the position changes from non-zero to 0.

    Args:
        asset: The ``Assets`` instance.
        end_date: Cutoff date/datetime (inclusive) for transactions.
        investor: Investor to filter transactions by.
        account_ids: Optional list of account IDs to filter by.
        start_date: Optional lower bound for transactions and seed position;
            the opening position is computed from transactions strictly
            before this date.

    Returns:
        list: Datetimes at which the position went from non-zero to zero.
    """
    transactions = asset.transactions.filter(quantity__isnull=False, investor=investor)
    if isinstance(end_date, datetime):
        transactions = transactions.filter(date__lte=end_date)
    else:
        transactions = transactions.filter(date__date__lte=end_date)
    if account_ids is not None:
        transactions = transactions.filter(account_id__in=account_ids)
    if start_date is not None:
        query_start_date = start_date
        if isinstance(query_start_date, datetime):
            transactions = transactions.filter(date__gte=query_start_date)
        else:
            transactions = transactions.filter(date__date__gte=query_start_date)

    transactions = transactions.order_by("date", "id")

    exit_dates_list = []
    if start_date is not None:
        opening_position_query = asset.transactions.filter(
            quantity__isnull=False,
            investor=investor,
        )
        if isinstance(start_date, datetime):
            opening_position_query = opening_position_query.filter(date__lt=start_date)
        else:
            opening_position_query = opening_position_query.filter(date__date__lt=start_date)
        if account_ids is not None:
            opening_position_query = opening_position_query.filter(account_id__in=account_ids)
        running_position = (
            opening_position_query.aggregate(total=Sum("quantity"))["total"] or Decimal(0)
        )
    else:
        running_position = 0

    for transaction in transactions:
        new_position = running_position + transaction.quantity
        if running_position != 0 and new_position == 0:
            exit_dates_list.append(transaction.date)
        running_position = new_position

    return exit_dates_list
