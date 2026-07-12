"""Transaction business-logic service.

Owns the cash-flow, price, classification, and lifecycle-history logic that
previously lived as methods on the ``Transactions`` and ``FXTransaction``
models (``common.models``):

Classification helpers (pure field checks, ``self -> transaction``):
- :func:`is_position_increase` — quantity > 0.
- :func:`is_paid_entry_transaction` — type in {BUY, CRYPTO_TRADE_IN}.
- :func:`is_reward_transaction` — type == CRYPTO_REWARD.
- :func:`is_disposal_transaction` — type in {SELL, CRYPTO_TRADE_OUT}.
- :func:`is_neutral_transfer_transaction` — type in {CRYPTO_TRANSFER_IN/OUT}.
- :func:`reward_value` — abs(quantity) * price for reward transactions.

Price and cash flow:
- :func:`get_price` — effective per-unit price; bonds convert percentage to
  money via ``Assets.get_effective_notional``.
- :func:`total_cash_flow` — the SINGLE SOURCE OF TRUTH net cash flow per
  transaction. Trades use ``-qty*price + aci + commission``; cash events use
  the ``cash_flow`` field; FX-converts via :func:`services.fx.get_rate`.
- :func:`get_cash_flow_by_currency` — per-currency cash flow for FX
  transactions (moved from ``FXTransaction``).

Lifecycle history helpers (called by ``Transactions.save()``, which stays on
the model as a Django lifecycle hook):
- :func:`create_notional_history` — was ``Transactions._create_notional_history``;
  finds/matches ``NotionalHistory`` entries, updates or creates.
- :func:`create_split_history` — was ``Transactions._create_split_history``;
  updates or creates ``SplitHistory``, appends a split note to
  ``security.comment``.

Parameter names and positions are preserved verbatim from the original model
methods so that existing keyword-argument callers (tests, views, core utils)
keep working unchanged after switching to ``func(transaction, ...)``. Only
``self`` becomes ``transaction`` (or ``fx_transaction``).

Numeric safety: ``Decimal`` everywhere for money. Never ``float``.

Import graph: this module imports :mod:`services.fx` at its top level for FX
conversion inside ``total_cash_flow``. ``services.fx`` imports the ``FX`` model
from ``common.models`` at its own top level, but does not import this module,
so the import is safe. ``common.models`` imports this module lazily (deferred,
inside ``Transactions.save()``) because importing it at module top level would
also pull in ``services.fx``. The ``NotionalHistory`` and ``SplitHistory``
models are referenced lazily inside the history helpers to keep the import
graph one-way.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from constants import (
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_BOND_REDEMPTION,
    TRANSACTION_TYPE_BROKER_COMMISSION,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_COUPON,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_INTEREST_INCOME,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_STOCK_SPLIT,
    TRANSACTION_TYPE_TAX,
)
from services.fx import get_rate as _fx_get_rate

logger = logging.getLogger(__name__)


# =============================================================================
# Classification helpers (self -> transaction)
# =============================================================================


def is_position_increase(transaction):
    """Return True when the transaction increases asset quantity."""
    return transaction.quantity is not None and transaction.quantity > 0


def is_paid_entry_transaction(transaction):
    """Return True when this transaction should affect paid entry price."""
    return transaction.type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_CRYPTO_TRADE_IN]


def is_reward_transaction(transaction):
    """Return True when this transaction is crypto income."""
    return transaction.type == TRANSACTION_TYPE_CRYPTO_REWARD


def is_disposal_transaction(transaction):
    """Return True when this transaction should realize gain/loss."""
    return transaction.type in [TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_CRYPTO_TRADE_OUT]


def is_neutral_transfer_transaction(transaction):
    """Return True when quantity movement is principal transfer only."""
    return transaction.type in [
        TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    ]


def reward_value(transaction):
    """Return event-date reward value without creating account cash."""
    if (
        not is_reward_transaction(transaction)
        or transaction.quantity is None
        or transaction.price is None
    ):
        return Decimal("0")
    return abs(transaction.quantity) * transaction.price


# =============================================================================
# Price and cash flow (self -> transaction)
# =============================================================================


def get_price(transaction):
    """
    Get the effective price per unit for this transaction.

    For stocks/ETFs/etc: returns transaction.price as-is
    For bonds: converts percentage to actual price using notional
               (price_percentage * notional / 100)

    Returns:
        Decimal: Effective price per unit, or None if price is not available
    """
    if not transaction.price:
        return None

    # Check if this is a bond transaction
    if transaction.security and transaction.security.type == "Bond":
        if transaction.notional:
            notional = transaction.notional
        else:
            # Pass account_id as a list for the __in lookup
            account_ids = [transaction.account_id] if transaction.account_id else None
            notional = transaction.security.get_effective_notional(
                transaction.date, transaction.investor, account_ids, transaction.currency
            )
        # Bond price is stored as percentage of par
        # Convert to actual money per bond: price% * notional / 100
        return (transaction.price * notional) / Decimal(100)
    else:
        # For non-bonds, price is already in actual money terms
        return transaction.price


def total_cash_flow(transaction, target_currency=None):
    """
    Calculate the net cash flow for this transaction.

    This is the SINGLE SOURCE OF TRUTH for cash flow calculations.
    Handles all transaction types and includes ACI, commission, etc.

    For trades (Buy/Sell):
        - cash_flow = -quantity * price + aci - commission
        - (Buy: negative, Sell: positive)

    For cash transactions/dividends/coupons:
        - Uses the cash_flow field directly

    For bond redemptions:
        - Uses the cash_flow field (amount received)

    For corporate actions (stock splits):
        - Always returns 0 (no cash movement)

    Args:
        transaction: The ``Transactions`` instance.
        target_currency: Optional currency code for conversion.
                       If None, returns in transaction's currency.

    Returns:
        Decimal: Net cash flow (can be negative or positive)
    """
    # Corporate actions have no cash flow
    if transaction.type == TRANSACTION_TYPE_STOCK_SPLIT:
        return Decimal(0)

    # Initialize cash flow
    calculated_cash_flow = Decimal(0)

    # Types where cash_flow field is directly used
    cash_flow_types = [
        TRANSACTION_TYPE_CASH_IN,
        TRANSACTION_TYPE_CASH_OUT,
        TRANSACTION_TYPE_DIVIDEND,
        TRANSACTION_TYPE_COUPON,
        TRANSACTION_TYPE_TAX,
        TRANSACTION_TYPE_BROKER_COMMISSION,
        TRANSACTION_TYPE_BOND_REDEMPTION,
        TRANSACTION_TYPE_BOND_MATURITY,
        TRANSACTION_TYPE_INTEREST_INCOME,
    ]

    if transaction.type in cash_flow_types:
        # Use the cash_flow field directly
        calculated_cash_flow = transaction.cash_flow or Decimal(0)

        # Broker commission: the commission field IS the cash flow
        if (
            transaction.type == TRANSACTION_TYPE_BROKER_COMMISSION
            and not transaction.cash_flow
        ):
            calculated_cash_flow = transaction.commission or Decimal(0)

    elif transaction.type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL]:
        # Calculate from quantity and price
        if transaction.quantity and transaction.price is not None:
            effective_price = get_price(transaction) or Decimal(0)

            # Base cash flow: -quantity * price
            # Buy: negative quantity, negative cash flow
            # Sell: positive quantity, positive cash flow
            calculated_cash_flow = -Decimal(transaction.quantity) * effective_price

            # Add ACI (accrued interest for bonds)
            # Buy: ACI is negative (you pay it),
            # Sell: ACI is positive (you receive it)
            if transaction.aci:
                calculated_cash_flow += Decimal(transaction.aci)

            # Subtract commission (always reduces cash)
            if transaction.commission:
                calculated_cash_flow += Decimal(transaction.commission)

    # Convert to target currency if requested
    if target_currency and target_currency != transaction.currency:
        fx_rate = _fx_get_rate(transaction.currency, target_currency, transaction.date)[
            "FX"
        ]
        calculated_cash_flow *= fx_rate

    return round(calculated_cash_flow, 2)


# =============================================================================
# FXTransaction cash flow (self -> fx_transaction)
# =============================================================================


def get_cash_flow_by_currency(fx_transaction, currency: str) -> Decimal:
    """
    Get the cash flow for this FX transaction in a specific currency.

    This is the SINGLE SOURCE OF TRUTH for FX transaction cash flows per currency.
    Handles commission in different currencies correctly.

    Args:
        fx_transaction: The ``FXTransaction`` instance.
        currency: The currency code to get cash flow for

    Returns:
        Decimal: Cash flow for the specified currency
                - Negative for outflow (from_currency)
                - Positive for inflow (to_currency)
                - Includes commission in the appropriate currency
    """
    cash_flow = Decimal(0)

    # From currency: outflow (negative)
    if currency == fx_transaction.from_currency:
        cash_flow = -fx_transaction.from_amount
        # Add commission if it's in the from_currency (commission is negative, makes flow more negative) # noqa: E501
        if fx_transaction.commission and fx_transaction.commission_currency == fx_transaction.from_currency:  # noqa: E501
            cash_flow += fx_transaction.commission

    # To currency: inflow (positive)
    elif currency == fx_transaction.to_currency:
        cash_flow = fx_transaction.to_amount
        # Add commission if it's in the to_currency
        # (commission is negative, reduces the inflow)
        if fx_transaction.commission and fx_transaction.commission_currency == fx_transaction.to_currency:  # noqa: E501
            cash_flow += fx_transaction.commission

    # Commission in a third currency
    elif fx_transaction.commission and currency == fx_transaction.commission_currency:
        cash_flow = fx_transaction.commission

    return cash_flow


# =============================================================================
# Lifecycle history helpers (were Transactions._create_*; called by save())
# =============================================================================


def create_notional_history(transaction):
    """Create NotionalHistory entry for this bond redemption.

    Was ``Transactions._create_notional_history``. Moved here so the
    ``Transactions`` model stays a thin schema; ``Transactions.save()`` calls
    this via a deferred import.
    """
    # Deferred import: services.transactions is imported lazily by
    # common.models, and NotionalHistory lives in common.models.
    from common.models import NotionalHistory

    try:
        # Get bond metadata
        bond_meta = transaction.security.bond_metadata
        if not bond_meta:
            logger.warning(
                f"No bond metadata for {transaction.security.name}, "
                "cannot create NotionalHistory"
            )
            return

        # notional_change is already per-bond (calculated during import)
        notional_per_bond = transaction.notional_change

        # Calculate change_amount (negative for redemptions)
        change_amount_value = -notional_per_bond

        # Determine change reason
        change_reason = (
            "MATURITY"
            if transaction.type == TRANSACTION_TYPE_BOND_MATURITY
            else "REDEMPTION"
        )

        # Search for existing entry within ±7 days with similar change_amount
        # This handles cases where API event dates
        # differ from broker transaction dates
        # (e.g., event on Friday, transaction settles on Monday)
        date_range_start = transaction.date - timedelta(days=7)
        date_range_end = transaction.date + timedelta(days=7)

        # Tolerance for matching change_amount (e.g., 0.01 for rounding differences)
        amount_tolerance = Decimal("0.01")

        # Find potential matches
        nearby_entries = NotionalHistory.objects.filter(
            asset=transaction.security,
            date__gte=date_range_start,
            date__lte=date_range_end,
            change_reason=change_reason,
        )

        # Look for a matching entry based on similar change_amount
        matching_entry = None
        for entry in nearby_entries:
            if (
                entry.change_amount
                and abs(entry.change_amount - change_amount_value) <= amount_tolerance
            ):
                matching_entry = entry
                break

        if matching_entry:
            # Update existing entry with actual transaction date
            old_date = matching_entry.date
            matching_entry.date = transaction.date
            matching_entry.change_amount = change_amount_value
            matching_entry.comment = (
                f"Updated from transaction {transaction.id} "
                f"(original API date: {old_date})"
            )
            matching_entry.save()

            logger.info(
                f"Updated NotionalHistory for {transaction.security.name}: "
                f"date {old_date} → {transaction.date}, "
                f"notional={matching_entry.notional_per_unit}, "
                f"change={change_amount_value}"
            )
        else:
            # Get current notional from previous history or initial
            previous_history = (
                NotionalHistory.objects.filter(
                    asset=transaction.security, date__lt=transaction.date
                )
                .order_by("-date")
                .first()
            )

            if previous_history:
                previous_notional = previous_history.notional_per_unit
            else:
                previous_notional = bond_meta.initial_notional

            # Calculate new notional per unit
            new_notional = previous_notional - notional_per_bond

            # No matching entry found, create new one
            NotionalHistory.objects.create(
                asset=transaction.security,
                date=transaction.date,
                change_reason=change_reason,
                notional_per_unit=new_notional,
                change_amount=change_amount_value,
                comment=f"Auto-created from transaction {transaction.id}",
            )

            logger.info(
                f"Created NotionalHistory for {transaction.security.name}: "
                f"notional={new_notional}, change={change_amount_value}"
            )

    except Exception as e:
        logger.error(
            f"Error creating NotionalHistory for transaction {transaction.id}: {e}",
            exc_info=True,
        )


def create_split_history(transaction):
    """
    Create SplitHistory entry for this Stock Split transaction.

    Uses the split_from and split_to fields directly.

    Was ``Transactions._create_split_history``. Moved here so the
    ``Transactions`` model stays a thin schema; ``Transactions.save()`` calls
    this via a deferred import.
    """
    # Deferred import: services.transactions is imported lazily by
    # common.models, and SplitHistory lives in common.models.
    from common.models import SplitHistory

    try:
        # Avoid duplicate entries - check if entry already exists for this transaction
        existing = SplitHistory.objects.filter(transaction=transaction).first()
        if existing:
            # Update existing entry
            existing.date = transaction.date
            existing.split_from = transaction.split_from
            existing.split_to = transaction.split_to
            existing.comment = transaction.comment
            existing.save()
            logger.info(
                f"Updated SplitHistory for {transaction.security.name}: "
                f"{transaction.split_from}:{transaction.split_to} on {transaction.date}"
            )
        else:
            # Create new entry
            SplitHistory.objects.create(
                asset=transaction.security,
                transaction=transaction,
                date=transaction.date,
                split_from=transaction.split_from,
                split_to=transaction.split_to,
                source="TRANSACTION",
                comment=transaction.comment,
            )
            logger.info(
                f"Created SplitHistory for {transaction.security.name}: "
                f"{transaction.split_from}:{transaction.split_to} on {transaction.date}"
            )

        # Update asset comment with split info
        if transaction.security:
            split_date = (
                transaction.date.date() if hasattr(transaction.date, "date") else transaction.date
            )
            split_note = f"Stock split {transaction.split_to}:{transaction.split_from} on {split_date}"
            if transaction.security.comment:
                if split_note not in transaction.security.comment:
                    transaction.security.comment = (
                        f"{transaction.security.comment}\n{split_note}"
                    )
            else:
                transaction.security.comment = split_note
            transaction.security.save(update_fields=["comment"])

    except Exception as e:
        logger.error(
            f"Error creating SplitHistory for transaction {transaction.id}: {e}",
            exc_info=True,
        )
