"""Corporate-action workflow service.

Owns the two multi-step corporate-action workflows that previously lived
inlined in viewsets:

- :func:`execute_merger` — was inlined in
  ``database/views.py:api_create_merger``. Applies a merger/reorganization
  of one security into another across every account where the investor
  holds the old security: creates one :class:`~common.models.MergerRecord`
  and per-account ``MERGER_OUT`` (and, when applicable, ``MERGER_IN``)
  transactions.
- :func:`execute_transfer` — was inlined in
  ``transactions/views.py:TransactionViewSet.transfer_asset``. Moves an
  asset between two broker accounts at average cost basis (zero realized
  gain), producing four transactions (Sell, Buy, Cash out, Cash in).

The view layer is now a thin orchestrator: it pulls raw values off the
request, calls one of these functions with plain parameters (user, ids,
dates, decimals), and translates the result/exception into an HTTP
response.

User-facing validation failures are signalled with
:class:`CorporateActionError`, which carries a message and an HTTP status
code; the view converts these into ``Response({"error": ...}, status=...)``.
``get_object_or_404`` is used inside :func:`execute_merger` for security
lookups so that missing securities still produce a 404 exactly as the
original view did.

Numeric safety: ``Decimal`` everywhere for money (conversion_ratio,
cash_per_share, transfer_value). Never ``float``.

Import graph: this module imports :mod:`services.realized` (for
``calculate_buy_in_price``) and :mod:`services.positions` (for
``position``) at its top level. Neither of those imports this module or
``common.models`` at its top level, so these imports are safe. The model
classes are imported from ``common.models`` at the top level; this module
is not imported by ``common.models``, so there is no cycle.
"""

import logging
from datetime import datetime
from decimal import Decimal

from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404

from common.models import Accounts, Assets, MergerRecord, Transactions
from constants import (
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_MERGER_IN,
    TRANSACTION_TYPE_MERGER_OUT,
    TRANSACTION_TYPE_SELL,
)
from services.positions import position as _positions_position
from services.realized import calculate_buy_in_price as _calculate_buy_in_price

logger = logging.getLogger(__name__)


class CorporateActionError(Exception):
    """Raised by corporate-action services for user-facing validation errors.

    The view layer catches this and converts it into an HTTP response with
    the carried message and status code.

    Attributes:
        message: Human-readable error message for the response body.
        status_code: HTTP status code to return (default 400).
    """

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# =============================================================================
# Merger / reorganization
# =============================================================================


def execute_merger(
    user,
    old_security_id,
    new_security_id,
    merger_date,
    conversion_ratio,
    cash_per_share,
):
    """Execute a merger/reorganization between two securities.

    A merger is a corporate action applied to the security itself, so it is
    executed against every account where the investor currently holds the
    old security. One :class:`~common.models.MergerRecord` is created for
    the event, and per-account ``MERGER_OUT`` (and, if applicable,
    ``MERGER_IN``) transactions are created. All writes run inside a single
    ``transaction.atomic()`` block so the event is all-or-nothing.

    Args:
        user: The investor (User) the merger applies to.
        old_security_id (int): ID of the old security being merged out.
        new_security_id (int|None): ID of the new security. Omit/None for
            all-cash mergers.
        merger_date (str): Date of the merger (``YYYY-MM-DD``).
        conversion_ratio (str|None): New shares per old share. Required when
            ``new_security_id`` is provided.
        cash_per_share (str|None): Cash per old share. Required for
            all-cash/hybrid mergers. Defaults to ``"0"``.

    Returns:
        dict: ``{"merger": {...}, "accounts": [...]}`` describing the
        created record and per-account results.

    Raises:
        CorporateActionError: For user-facing validation failures
            (missing/invalid fields, no positive position held). Carries the
            appropriate HTTP status code.
        Http404: When ``old_security_id`` or ``new_security_id`` does not
            reference a security owned by the investor (via
            ``get_object_or_404``).
    """
    if not old_security_id or not merger_date:
        raise CorporateActionError(
            "old_security_id and merger_date are required",
        )

    try:
        merger_date = datetime.strptime(merger_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise CorporateActionError(
            "Invalid merger_date format. Use YYYY-MM-DD.",
        )

    old_security = get_object_or_404(Assets, id=old_security_id, investors=user)

    new_security = None
    if new_security_id:
        new_security = get_object_or_404(Assets, id=new_security_id, investors=user)
        if not conversion_ratio:
            raise CorporateActionError(
                "conversion_ratio is required when new_security_id is provided",
            )

    try:
        conversion_ratio_dec = Decimal(str(conversion_ratio)) if conversion_ratio else None
    except Exception:
        raise CorporateActionError("Invalid conversion_ratio")

    try:
        cash_per_share_dec = (
            Decimal(str(cash_per_share)) if cash_per_share else Decimal("0")
        )
    except Exception:
        raise CorporateActionError("Invalid cash_per_share")

    # Find every account of this investor that has a positive position in the
    # old security as of the merger date.
    candidate_account_ids = (
        Transactions.objects.filter(
            investor=user, security=old_security, date__date__lte=merger_date
        )
        .values_list("account_id", flat=True)
        .distinct()
    )
    accounts_with_positions = []
    for acc in Accounts.objects.filter(
        id__in=list(candidate_account_ids), broker__investor=user
    ):
        pos = _positions_position(old_security, merger_date, user, account_ids=[acc.id])
        if pos and pos > 0:
            accounts_with_positions.append((acc, pos))

    if not accounts_with_positions:
        raise CorporateActionError(
            f"Old security has no positive position in any account as of {merger_date}",
        )

    is_all_stock = new_security is not None and cash_per_share_dec == 0

    with db_transaction.atomic():
        merger_record = MergerRecord.objects.create(
            investor=user,
            old_security=old_security,
            new_security=new_security,
            merger_date=merger_date,
            conversion_ratio=conversion_ratio_dec,
            cash_per_share=cash_per_share_dec,
        )

        if new_security:
            new_security.investors.add(user)

        per_account = []
        for account, old_position in accounts_with_positions:
            old_cost_per_share = _calculate_buy_in_price(
                old_security,
                merger_date,
                user,
                old_security.currency,
                account_ids=[account.id],
            )
            if old_cost_per_share is None:
                old_cost_per_share = Decimal("0")

            total_old_cost = old_position * old_cost_per_share
            merger_out_cash_flow = (
                cash_per_share_dec * old_position if not is_all_stock else Decimal("0")
            )

            merger_out = Transactions.objects.create(
                investor=user,
                account=account,
                security=old_security,
                currency=old_security.currency,
                type=TRANSACTION_TYPE_MERGER_OUT,
                date=datetime.combine(merger_date, datetime.min.time()),
                quantity=-old_position,
                price=old_cost_per_share,
                cash_flow=merger_out_cash_flow if merger_out_cash_flow else None,
                merger=merger_record,
            )

            entry = {
                "account_id": account.id,
                "account_name": account.name,
                "old_position": str(old_position),
                "old_cost_per_share": str(old_cost_per_share),
                "merger_out_id": merger_out.id,
            }

            if new_security:
                new_quantity = old_position * conversion_ratio_dec
                carryover_cost = total_old_cost
                new_cost_per_share = (
                    carryover_cost / new_quantity if new_quantity else Decimal("0")
                )
                merger_in = Transactions.objects.create(
                    investor=user,
                    account=account,
                    security=new_security,
                    currency=new_security.currency,
                    type=TRANSACTION_TYPE_MERGER_IN,
                    date=datetime.combine(merger_date, datetime.min.time()),
                    quantity=new_quantity,
                    price=new_cost_per_share,
                    cash_flow=None,
                    merger=merger_record,
                )
                entry["merger_in_id"] = merger_in.id
                entry["new_quantity"] = str(new_quantity)
                entry["new_cost_per_share"] = str(new_cost_per_share)

            per_account.append(entry)

    return {
        "merger": {
            "id": merger_record.id,
            "old_security": {"id": old_security.id, "name": old_security.name},
            "new_security": (
                {"id": new_security.id, "name": new_security.name}
                if new_security
                else None
            ),
            "merger_date": merger_date.isoformat(),
            "conversion_ratio": str(conversion_ratio_dec) if conversion_ratio_dec else None,
            "cash_per_share": str(cash_per_share_dec),
        },
        "accounts": per_account,
    }


# =============================================================================
# Inter-account asset transfer
# =============================================================================


def execute_transfer(
    investor,
    security_id,
    from_account_id,
    to_account_id,
    quantity,
    transfer_date,
):
    """Transfer an asset from one broker account to another.

    Creates a sale from the source account and a purchase in the destination
    account at the average cost basis (zero realized gain), plus matching
    phantom ``Cash out`` / ``Cash in`` transactions to balance the cash
    effect. All four transactions are created inside a single
    ``transaction.atomic()`` block.

    Args:
        investor: The investor (User) the transfer applies to.
        security_id (int): ID of the security to transfer.
        from_account_id (int): ID of the source broker account.
        to_account_id (int): ID of the destination broker account.
        quantity (str|Decimal): Quantity to transfer.
        transfer_date (datetime.date): Date of the transfer.

    Returns:
        dict: ``{"message": ..., "sale_transaction_id": ..., ...}``
        describing the four created transactions and the transfer value.

    Raises:
        CorporateActionError: For user-facing validation failures
            (security/account not found, unable to compute buy-in price).
            Carries the appropriate HTTP status code.
    """
    # Get the security
    try:
        security = Assets.objects.get(id=security_id, investors=investor)
    except Assets.DoesNotExist:
        raise CorporateActionError(
            f"Security with id {security_id} not found",
            status_code=404,
        )

    # Get the accounts
    try:
        from_account = Accounts.objects.get(
            id=from_account_id, broker__investor=investor
        )
        to_account = Accounts.objects.get(id=to_account_id, broker__investor=investor)
    except Accounts.DoesNotExist:
        raise CorporateActionError(
            "One or both accounts not found",
            status_code=404,
        )

    # Calculate the average buy-in price for the security in the from_account
    buy_in_price = _calculate_buy_in_price(
        security,
        date=transfer_date,
        investor=investor,
        account_ids=[from_account_id],
    )

    if buy_in_price is None:
        raise CorporateActionError(
            "Unable to calculate buy-in price. "
            "No prior transactions found for this security in the "
            "source account.",
        )

    # Get the currency from the security
    currency = security.currency

    # Create comments
    sale_comment = f"Transfer out to {to_account.name}"
    buy_comment = f"Transfer in from {from_account.name}"
    cash_comment = f"Phantom cash movement for asset transfer: {security.name}"

    # Calculate transfer value
    quantity_dec = Decimal(quantity)
    transfer_value = quantity_dec * buy_in_price

    # Create all transactions atomically
    with db_transaction.atomic():
        # 1. Sell transaction (from_account) - negative quantity
        sale_transaction = Transactions.objects.create(
            investor=investor,
            account=from_account,
            security=security,
            date=transfer_date,
            type=TRANSACTION_TYPE_SELL,
            quantity=-quantity_dec,  # Negative for sell
            price=buy_in_price,
            currency=currency,
            cash_flow=None,  # Empty cash flow
            commission=None,  # Empty commission
            comment=sale_comment,
        )

        # 2. Buy transaction (to_account) - positive quantity
        buy_transaction = Transactions.objects.create(
            investor=investor,
            account=to_account,
            security=security,
            date=transfer_date,
            type=TRANSACTION_TYPE_BUY,
            quantity=quantity_dec,  # Positive for buy
            price=buy_in_price,
            currency=currency,
            cash_flow=None,  # Empty cash flow
            commission=None,  # Empty commission
            comment=buy_comment,
        )

        # 3. Phantom cash-out transaction (from_account) -
        # to balance the cash effect
        cash_in_transaction = Transactions.objects.create(
            investor=investor,
            account=from_account,
            security=None,
            date=transfer_date,
            type=TRANSACTION_TYPE_CASH_OUT,
            quantity=None,
            price=None,
            currency=currency,
            cash_flow=-transfer_value,  # Negative cash flow
            commission=None,
            comment=cash_comment,
        )

        # 4. Phantom cash-in transaction (to_account) -
        # to balance the cash effect
        cash_out_transaction = Transactions.objects.create(
            investor=investor,
            account=to_account,
            security=None,
            date=transfer_date,
            type=TRANSACTION_TYPE_CASH_IN,
            quantity=None,
            price=None,
            currency=currency,
            cash_flow=transfer_value,  # Positive cash flow
            commission=None,
            comment=cash_comment,
        )

    logger.info(
        f"Asset transfer completed: {quantity} units of {security.name} "
        f"from {from_account.name} to {to_account.name} at "
        f"{buy_in_price} {currency}"
    )

    return {
        "message": "Asset transfer completed successfully",
        "sale_transaction_id": sale_transaction.id,
        "buy_transaction_id": buy_transaction.id,
        "cash_in_transaction_id": cash_in_transaction.id,
        "cash_out_transaction_id": cash_out_transaction.id,
        "transfer_price": float(buy_in_price),
        "transfer_value": float(transfer_value),
    }
