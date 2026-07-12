"""Performance calculation service.

Owns the multi-period performance assembly that previously lived at module
level in ``core.portfolio_utils``:

- :func:`calculate_performance` builds the per-account/per-group performance
  table for a date range (BOP NAV, invested, cash out, price change, capital
  distributions, commission, tax, FX, EOP NAV, TSR).
- :func:`get_selected_account_ids` resolves the user's account selection
  (all / account / group / broker) to a concrete list of account IDs.
- :func:`get_last_exit_date_for_accounts` returns the last relevant date for
  a set of accounts (effective date if any positions open, otherwise the last
  transaction date).
- :func:`calculate_percentage_shares` adds ``*_percentage`` sub-dicts to a NAV
  breakdown dict for the requested categories.

Function names, parameter names, and positions are preserved verbatim from
``core.portfolio_utils`` so that existing keyword-argument callers (tests,
views, core utils) keep working unchanged after switching the import path to
``services.performance``.

Numeric safety: ``Decimal`` everywhere for money and rates. Never ``float``.

Circular-import notes:
- ``services.nav`` is imported at the top level here. ``services.nav`` does
  not import this module, so the dependency is one-way and safe.
- ``services.realized`` and ``services.capital`` do not import this module
  either, so those top-level imports are likewise safe.
"""

import datetime
import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from django.db.models import Prefetch, Q, Sum

from common.models import Accounts, AnnualPerformance, Assets, Brokers, Transactions
from core.formatting_utils import format_percentage
from services.capital import get_capital_distribution
from services.nav import IRR, NAV_at_date, get_fx_rate
from services.realized import realized_gain_loss, unrealized_gain_loss
from users.models import AccountGroup, CustomUser

logger = logging.getLogger("dashboard")


def get_selected_account_ids(
    user: CustomUser, selection_type: str, selection_id: Optional[int] = None
) -> List[int]:
    """
    Get list of broker account IDs based on selection type and ID.

    Args:
        user: CustomUser instance
        selection_type: Type of selection ('all', 'account', 'group', 'broker')
        selection_id: ID of selected item (None for 'all')

    Returns:
        List of broker account IDs
    """
    if selection_type == "all":
        return list(Accounts.objects.filter(broker__investor=user).values_list("id", flat=True))

    elif selection_type == "account":
        return (
            [selection_id]
            if Accounts.objects.filter(id=selection_id, broker__investor=user).exists()
            else []
        )

    elif selection_type == "group":
        try:
            group = AccountGroup.objects.get(id=selection_id, user=user)
            return list(group.accounts.values_list("id", flat=True))
        except AccountGroup.DoesNotExist:
            return []

    elif selection_type == "broker":
        try:
            broker = Brokers.objects.get(id=selection_id, investor=user)
            return list(Accounts.objects.filter(broker=broker).values_list("id", flat=True))
        except Brokers.DoesNotExist:
            return []

    return []


def calculate_performance(
    user,
    start_date,
    end_date,
    account_group_type,
    account_group_id,
    currency_target,
    is_restricted=None,
):
    """Calculate performance metrics for a given date range and account group.

    Args:
        user: The user instance.
        start_date: Start date for performance calculation.
        end_date: End date for performance calculation.
        account_group_type: Type of account group.
        account_group_id: ID of the account group.
        currency_target: Target currency for values.
        is_restricted: Whether to calculate restricted performance (optional).

    Returns:
        dict: Dictionary containing performance metrics including gain_loss,
            nav_start, nav_end, tsr, and breakdown values.
    """
    performance_data = defaultdict(Decimal)
    logger.debug(
        f"Calculating performance for {user.username}, {account_group_type} {account_group_id} "
        f"from {start_date} to {end_date}, currency {currency_target}, restricted {is_restricted}"
    )

    # Initialize all required fields with Decimal(0)
    for field in [
        "bop_nav",
        "invested",
        "cash_out",
        "price_change",
        "capital_distribution",
        "commission",
        "tax",
        "fx",
        "eop_nav",
        "tsr",
    ]:
        performance_data[field] = Decimal("0")

    alternative_fx_check = Decimal("0")

    selected_account_ids = get_selected_account_ids(user, account_group_type, account_group_id)
    accounts = Accounts.objects.filter(
        id__in=selected_account_ids, broker__investor=user
    ).select_related("broker")

    bop_nav = (
        AnnualPerformance.objects.filter(
            investor=user,
            account_type=account_group_type,
            account_id=account_group_id,
            year=start_date.year - 1,
            currency=currency_target,
        )
        .values_list("eop_nav", flat=True)
        .first()
    )

    logger.info(f"BOP NAV: {bop_nav}")
    logger.debug(f"Accounts: {accounts}")

    # bop_nav_dict = {nav['broker']: nav['eop_nav'] for nav in bop_navs}

    for account in accounts:
        # bop_nav = bop_nav_dict.get(broker.id)
        if not bop_nav:
            bop_nav_account = NAV_at_date(
                user.id,
                tuple([account.id]),
                start_date - timedelta(days=1),
                currency_target,
            )["Total NAV"]
            performance_data["bop_nav"] += bop_nav_account

        transactions = Transactions.objects.filter(
            investor=user,
            account=account,
            date__date__gte=start_date,
            date__date__lte=end_date,
        )

        if is_restricted is not None:
            restricted_filter = Q(security__isnull=False, security__restricted=is_restricted)
            if not is_restricted:
                restricted_filter |= Q(security__isnull=True)
            transactions = transactions.filter(restricted_filter)

        # Calculate transaction-based metrics
        for transaction in transactions:
            fx_rate = get_fx_rate(transaction.currency, currency_target, transaction.date)

            if transaction.cash_flow is not None:
                converted_amount = transaction.cash_flow * fx_rate
                if transaction.type == "Cash in":
                    performance_data["invested"] += converted_amount
                elif transaction.type == "Cash out":
                    performance_data["cash_out"] += converted_amount
                elif transaction.type == "Tax":
                    performance_data["tax"] += converted_amount

            performance_data["commission"] += (transaction.commission or 0) * fx_rate

        # Calculate asset-based metrics
        assets = (
            Assets.objects.filter(investors__id=user.id, transactions__account=account)
            .prefetch_related(
                Prefetch(
                    "transactions",
                    queryset=Transactions.objects.filter(
                        account=account, date__date__gte=start_date, date__date__lte=end_date
                    ),
                    to_attr="period_transactions",
                )
            )
            .distinct()
        )

        if is_restricted is not None:
            assets = assets.filter(restricted=is_restricted)

        logger.debug(f"Assets: {assets}")

        for asset in assets:
            asset_realized_gl = realized_gain_loss(
                asset,
                end_date,
                user,
                currency_target,
                account_ids=[account.id],
                start_date=start_date,
            )
            asset_unrealized_gl = unrealized_gain_loss(
                asset,
                end_date,
                user,
                currency_target,
                account_ids=[account.id],
                start_date=start_date,
            )

            performance_data["price_change"] += (
                asset_realized_gl["all_time"]["price_appreciation"] if asset_realized_gl else 0
            )
            logger.debug(f"Realized GL for {asset.name}: {asset_realized_gl}")
            alternative_fx_check += asset_realized_gl["all_time"]["fx_effect"]
            performance_data["price_change"] += asset_unrealized_gl["price_appreciation"]
            logger.debug(f"Unrealized GL for {asset.name}: {asset_unrealized_gl}")
            alternative_fx_check += asset_unrealized_gl["fx_effect"]
            performance_data["capital_distribution"] += get_capital_distribution(
                asset,
                end_date,
                user,
                currency_target,
                account_ids=[account.id],
                start_date=start_date,
            )
            logger.debug(
                f"Capital distribution for {asset.name}: {performance_data['capital_distribution']}"
            )

        # Calculate EOP NAV
        eop_nav = NAV_at_date(user.id, tuple([account.id]), end_date, currency_target)["Total NAV"]
        performance_data["eop_nav"] += eop_nav

    if bop_nav:
        performance_data["bop_nav"] = bop_nav

    # Calculate FX impact
    components_sum = sum(
        performance_data[key]
        for key in [
            "bop_nav",
            "invested",
            "cash_out",
            "price_change",
            "capital_distribution",
            "commission",
            "tax",
        ]
    )
    performance_data["fx"] += performance_data["eop_nav"] - components_sum

    # Calculate TSR
    performance_data["tsr"] = format_percentage(
        IRR(
            user.id,
            end_date,
            currency_target,
            account_ids=selected_account_ids,
            start_date=start_date,
        ),
        digits=1,
    )

    # Adjust FX for rounding errors
    performance_data["fx"] = (
        Decimal("0") if abs(performance_data["fx"]) < 0.1 else performance_data["fx"]
    )

    logger.debug(f"Alternative FX check: {alternative_fx_check}")
    logger.debug(f"FX effect: {performance_data['fx']}")

    return dict(performance_data)


# Add percentage shares to the dict
def calculate_percentage_shares(data_dict, selected_keys):
    """Calculate percentage shares for selected breakdown categories."""
    if not data_dict:
        return

    total_nav = data_dict.get("Total NAV", Decimal(0))

    for key in selected_keys:
        percentage_key = key + "_percentage"
        data_dict[percentage_key] = {}

        for item in data_dict[key]:
            if total_nav > 0:
                percentage = data_dict[key][item] / total_nav * 100
                data_dict[percentage_key][item] = format_percentage(percentage, digits=1)
            else:
                data_dict[percentage_key][item] = "–"


def get_last_exit_date_for_accounts(
    account_ids: List[int], effective_current_date: date
) -> Optional[date]:
    """
    Determine the last relevant date for a set of broker accounts.

    Considers both open positions and transaction history. If any account has
    open positions, returns the effective_current_date. If all positions are
    closed, returns the date of the last transaction. If no transactions exist,
    returns the effective_current_date.

    Args:
        account_ids (List[int]): List of broker account IDs to analyze
        effective_current_date (date): The reference date for position calculations

    Returns:
        Optional[date]:
            - effective_current_date if any positions are open or no transactions exist
            - date of the last transaction if all positions are closed
    """
    # Ensure date is a date object
    if isinstance(effective_current_date, str):
        effective_current_date = datetime.strptime(effective_current_date, "%Y-%m-%d").date()

    # Step 1: Check for open positions using aggregation
    open_positions = (
        Assets.objects.filter(
            transactions__account_id__in=account_ids,
            transactions__date__date__lte=effective_current_date,
        )
        .annotate(
            total_quantity=Sum(
                "transactions__quantity",
                filter=Q(
                    transactions__date__date__lte=effective_current_date,
                    transactions__account_id__in=account_ids,
                ),
            )
        )
        .exclude(total_quantity=0)
        .exists()
    )

    if open_positions:
        return effective_current_date

    # Step 2: If no open positions, find the latest transaction date
    latest_transaction_date = (
        Transactions.objects.filter(account_id__in=account_ids, date__lte=effective_current_date)
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )

    if latest_transaction_date is not None:
        # Convert datetime to date if needed (Transactions.date is DateTimeField)
        if hasattr(latest_transaction_date, "date"):
            latest_transaction_date = latest_transaction_date.date()
        return latest_transaction_date

    return effective_current_date
