"""Realized and unrealized gain/loss engine.

Owns the four most protected financial-calculation methods that previously
lived on the ``Assets`` model:

- :func:`calculate_buy_in_price` weighted average cost basis for the latest
  open lot; supports long/short, artificial opening transaction, excludes a
  txn, FX-converts via :func:`services.fx.get_rate`.
- :func:`get_economic_basis` crypto-aware cost basis replay engine with
  inner closures for transfer-group tracking.
- :func:`realized_gain_loss` pairs entry/exit dates, walks transactions
  computing realized G/L (price + FX). Branches for bonds, crypto, closing
  long/short.
- :func:`unrealized_gain_loss` ``(current_price - buy_in_price) * position``
  for the open lot; bonds use notional; crypto uses :func:`get_economic_basis`.

Parameter names and positions are preserved verbatim from the original model
methods so that existing keyword-argument callers (tests, views, core utils)
keep working unchanged after switching to ``func(asset, ...)``. Only ``self``
becomes ``asset``.

Numeric safety: ``Decimal`` everywhere with ``ROUND_HALF_UP``. Never ``float``.
This is non-negotiable for these methods.

Circular-import notes:
- This module imports :mod:`services.fx`, :mod:`services.pricing`, and
  :mod:`services.positions` at its top level. None of those modules import
  this module or ``common.models`` at their top level (the asset is always
  passed in by callers), so these imports are safe.
- ``common.models`` cannot import this module at its top level (it would pull
  in the chain ``services.realized`` -> ``services.fx`` -> ``common.models.FX``
  on first load), so callers in ``common.models`` resolve these functions
  lazily inside method bodies.
- Internal cross-calls (e.g. ``realized_gain_loss`` calling
  ``calculate_buy_in_price``) become plain local function calls within this
  module. Calls to other services (fx, pricing, positions) go through the
  top-level imports. Calls that stay on the model (``asset.transactions``,
  ``asset.get_effective_notional``, ``asset.is_bond``, ``asset.currency``)
  remain attribute/method accesses.
"""

import logging
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum

from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_BOND_REDEMPTION,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
)
from services import options
from services.fx import get_rate as _fx_get_rate
from services.positions import (
    entry_dates as _positions_entry_dates,
    exit_dates as _positions_exit_dates,
    position as _positions_position,
)
from services.pricing import price_at_date as _pricing_price_at_date
from services.transactions import (
    get_price as _transactions_get_price,
    is_disposal_transaction as _transactions_is_disposal_transaction,
    is_neutral_transfer_transaction as _transactions_is_neutral_transfer_transaction,
    is_paid_entry_transaction as _transactions_is_paid_entry_transaction,
    is_reward_transaction as _transactions_is_reward_transaction,
    reward_value as _transactions_reward_value,
)

logger = logging.getLogger(__name__)


# Until issue #29's two-account model lands, ALL crypto transfers are neutral
# (position += quantity, no realized G/L). OKX Funding↔Trading internal moves
# dominate real data and are indistinguishable from external withdrawals
# pre-#29. Set True to reactivate the matched-vs-unmatched disposition logic
# (the _transfer_is_matched helper is retained for that future use).
TRANSFER_DISPOSITION_ENABLED = False


def _option_contract_size(asset) -> Decimal:
    """Return the contract size for an option asset, or Decimal(1) otherwise.

    Option paid-entries are recorded in *contract* units but priced in coin
    per contract, so the cost basis must multiply by ``contract_size`` to
    express coin notional (e.g. 7 contracts × 0.0022 BTC × 0.01 BTC/contract
    = 0.000154 BTC). For non-option assets this returns ``Decimal(1)`` so the
    basis math is a no-op for crypto/stocks/bonds.

    ``OptionMetadata`` is imported lazily to avoid pulling ``common.models``
    at module load (matches realized.py's lazy-import pattern for circulars).
    """
    if not options.is_option_asset(asset):
        return Decimal(1)
    from common.models import OptionMetadata

    meta = OptionMetadata.objects.filter(asset=asset).first()
    if meta is None or meta.contract_size is None:
        return Decimal(1)
    return Decimal(meta.contract_size)


def _realized_option_close(
    asset, transaction, position_before, investor, account_ids, start
):
    """Compute realized G/L for an Option settlement that closes a position.

    The opening leg (``Crypto trade in/out``) recorded the premium on its
    ``cash_flow`` (signed: +received for sell / -paid for buy). The settlement
    closes at the terminal price (0 OTM / intrinsic ITM); its ``cash_flow``
    already carries the payout sign (negative for writer ITM payout, 0 OTM,
    positive for buyer ITM receipt).

    The single formula ``realized = premium_at_open + settlement_proceeds +
    fee_at_open`` works for BOTH short and long closes because ``cash_flow``
    carries the sign convention (negative = coin outflow). ``commission`` is
    stored as a negative number, so adding ``fee_at_open`` subtracts the fee.

    Verification against the regression fixtures (8 dp):
        OTM writer: +0.000154 + 0 + (-0.00001078)        = +0.00014322
        ITM writer: +0.000154 + (-0.00411765) + 0        = -0.00396365
        Long OTM:   -0.000154 + 0 + 0                    = -0.000154

    ``position_before``, ``account_ids``, and ``start`` are accepted for
    interface symmetry with the walker; the helper itself reads the opening
    row directly so it works regardless of whether the position-reducing
    detection above fired.

    Returns a 3-key dict (``price_appreciation``, ``fx_effect``, ``total``)
    matching the walker's accumulator shape. For a single-currency option
    cycle the FX effect is 0 (no cross-currency conversion).
    """
    # Find the opening row (most recent open position before this settlement).
    opening = (
        asset.transactions.filter(
            investor=investor,
            quantity__isnull=False,
            date__lt=transaction.date,
        )
        .exclude(type=TRANSACTION_TYPE_OPTION_SETTLEMENT)
        .order_by("-date", "-id")
        .first()
    )
    premium_at_open = (
        Decimal(opening.cash_flow)
        if (opening and opening.cash_flow is not None)
        else Decimal(0)
    )
    fee_at_open = (
        Decimal(opening.commission)
        if (opening and opening.commission is not None)
        else Decimal(0)
    )
    # Settlement cash_flow already carries the payout sign (negative for writer
    # ITM, positive for buyer ITM, 0 for OTM). Use it directly as the proceeds.
    proceeds = (
        Decimal(transaction.cash_flow)
        if transaction.cash_flow is not None
        else Decimal(0)
    )

    realized_local = premium_at_open + proceeds + fee_at_open

    # FX effect: option premiums and payouts are in the settlement coin (BTC).
    # For a single-currency option cycle, fx_effect is 0 (no FX conversion).
    return {
        "price_appreciation": realized_local,
        "fx_effect": Decimal(0),
        "total": realized_local,
    }


def _transfer_is_matched(transaction, investor, account_ids=None):
    """Return True when this transfer has a matching partner leg in-portfolio.

    A transfer is matched when another transfer of the opposite direction
    exists for the same asset, same ``import_group_id``, same provider, within
    the investor's account set. Transfers without an ``import_group_id`` are
    unmatched by definition (no pairing signal) — these are cold-wallet
    withdrawals, external deposits, or moves to an un-modeled account.

    This is the realized-G/L counterpart to the multi-source discrimination
    already performed by ``allocate_group_carry`` in ``get_economic_basis``
    (``len(source_keys) != 1`` -> no basis carry): both enforce that a transfer
    must have an unambiguous in-portfolio partner to be treated as principal-
    preserving. The difference is that ``allocate_group_carry`` protects the
    basis replay, while this helper protects the realized P&L walker so an
    unmatched transfer flows into the disposal (OUT) or paid-entry (IN) branch.
    """
    group_id = getattr(transaction, "import_group_id", None)
    if not group_id:
        return False
    provider = getattr(transaction, "import_provider", None) or ""
    # Look for the opposite-direction sibling in the same group.
    # Lazy import: realized.py sits above common.models in the import chain
    # (see module docstring) so a top-level import would be circular.
    from common.models import Transactions as _Tx

    target_type = (
        TRANSACTION_TYPE_CRYPTO_TRANSFER_IN
        if transaction.type == TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT
        else TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT
    )
    qs = _Tx.objects.filter(
        investor=investor,
        security_id=transaction.security_id,
        import_group_id=group_id,
        type=target_type,
    )
    if provider:
        qs = qs.filter(import_provider=provider)
    if account_ids is not None:
        qs = qs.filter(account_id__in=account_ids)
    return qs.exists()


# ---------------------------------------------------------------------------
# calculate_buy_in_price
# ---------------------------------------------------------------------------


def calculate_buy_in_price(
    asset,
    date_as_of,
    investor,
    currency=None,
    account_ids=None,
    start_date=None,
    exclude_transaction_id=None,
):
    """
    Calculate average buy-in price for an asset.

    Calculates the average buy-in price for the given date, currency,
    broker account IDs, and start date.

    Args:
        asset (Assets): The asset instance.
        date_as_of (datetime.date): Date for which to calculate the buy-in price.
        investor (User): Investor for which to calculate the buy-in price.
        currency (str): Currency in which to calculate the buy-in price.
        account_ids (list): List of broker account IDs to filter transactions by.
        start_date (datetime.date): Start date for the calculation.
        exclude_transaction_id (int, optional): Transaction ID to exclude from calculation.

    Returns:
        float: Calculated buy-in price. Returns None if an error occurs.
    """
    logger.debug(f"Calculating buy-in price for {asset.name} as of {date_as_of}")
    logger.debug(
        f"Parameters: currency={currency}, account_ids={account_ids}, "
        f"start_date={start_date}, exclude_transaction_id={exclude_transaction_id}"
    )

    is_long_position = None

    transactions = asset.transactions.filter(quantity__isnull=False, investor=investor)
    if isinstance(date_as_of, datetime):
        transactions = transactions.filter(date__lte=date_as_of)
    else:
        transactions = transactions.filter(date__date__lte=date_as_of)
    transactions = transactions.order_by("date", "id")

    # Exclude the specified transaction if provided
    if exclude_transaction_id is not None:
        transactions = transactions.exclude(id=exclude_transaction_id)

    if account_ids is not None:
        transactions = transactions.filter(account_id__in=account_ids)

    logger.debug(f"Number of transactions: {transactions.count()}")

    if not transactions:
        logger.debug("Buy-in price: No transactions found")
        return None

    # Get latest entry date
    entry_dates = _positions_entry_dates(asset, date_as_of, investor, account_ids)
    if not entry_dates:
        logger.warning("No entry dates found")
        return None
    entry_date = entry_dates[-1]
    logger.debug(f"Latest entry date: {entry_date}")

    # Convert start_date to datetime object if it's a date
    if start_date and isinstance(start_date, date):
        start_date = datetime.combine(start_date, datetime.min.time()).replace(
            tzinfo=None
        )
    elif start_date and isinstance(start_date, datetime):
        pass
    elif start_date is None:
        pass
    else:
        raise ValueError("Invalid start date")

    # Convert entry_date to datetime offset-naive object if it's a date
    if entry_date and isinstance(entry_date, date):
        entry_date = datetime.combine(entry_date, datetime.min.time()).replace(
            tzinfo=None
        )

    if start_date and start_date > entry_date:
        # Add artificial transaction at start_date
        logger.debug(f"Start date {start_date} is after latest entry date {entry_date}")
        position = _positions_position(asset, start_date, investor, account_ids)
        logger.debug(f"Position at start date: {position}")
        if position != 0:
            price_at_start = _pricing_price_at_date(asset, start_date)
            if price_at_start:
                logger.debug(f"Price at start date: {price_at_start.price}")
                artificial_transaction = {
                    "date": start_date,
                    "quantity": position,
                    "price": price_at_start.price,
                    "currency": asset.currency,
                }
                transactions = list(transactions.filter(date__gte=start_date))
                transactions.insert(0, type("obj", (object,), artificial_transaction))
                is_long_position = position > 0
                logger.debug(f"Added artificial transaction: {artificial_transaction}")
        entry_date = start_date

    # Handle both date and datetime objects in comparison
    filtered_transactions = []
    for t in transactions:
        if t.date >= entry_date:
            if getattr(t, "type", None) in [
                TRANSACTION_TYPE_CRYPTO_REWARD,
                TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
                TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
            ]:
                continue
            filtered_transactions.append(t)
    transactions = filtered_transactions
    logger.debug(f"Number of transactions after filtering: {len(transactions)}")

    if not transactions:
        logger.debug("Buy-in price: No paid entry transactions found")
        return None

    # Determine position direction based on current position
    # When exclude_transaction_id is provided, we need to calculate position
    # using only the filtered transactions (excluding the specified transaction)
    if exclude_transaction_id is not None:
        # Calculate position using only filtered transactions
        current_position = sum((t.quantity or Decimal(0)) for t in transactions)
    else:
        # Use the existing position method for performance
        current_position = _positions_position(asset, date_as_of, investor, account_ids)

    # Determine if it's a long or short position:
    # - If current_position > 0: currently long -> use average buy price
    # - If current_position < 0: currently short -> use average sell price
    # - If current_position == 0: closed position -> look at the LAST non-zero
    #   position direction to determine what was being closed
    if abs(current_position) > Decimal("1e-6"):
        # Non-zero position: direction based on current position
        is_long_position = current_position > 0
    elif transactions:
        # Zero position: find the direction of the last non-zero position
        # This handles mixed position scenarios (long -> short -> zero)
        temp_position = Decimal(0)
        last_non_zero_direction = None
        for t in transactions:
            temp_position += t.quantity
            if abs(temp_position) > Decimal("1e-6"):
                last_non_zero_direction = temp_position > 0
        # If we found a non-zero state, use that direction
        # Otherwise, fall back to first transaction direction
        if last_non_zero_direction is not None:
            is_long_position = last_non_zero_direction
        else:
            first_transaction = transactions[0]
            is_long_position = first_transaction.quantity > 0
    else:
        is_long_position = True  # Default to long if no transactions

    logger.debug(
        f"Current position: {current_position}, Is long position: {is_long_position}"
    )

    # For short positions, find the price at which the short position was established
    if not is_long_position:
        # For short positions, find the average sell price that created the short
        sell_value = Decimal(0)
        sell_quantity = Decimal(0)
        buy_value = Decimal(0)
        buy_quantity = Decimal(0)

        for transaction in transactions:
            if currency is not None:
                fx_rate = _fx_get_rate(
                    transaction.currency, currency, transaction.date
                )["FX"]
            else:
                fx_rate = Decimal(1)

            current_price = transaction.price * fx_rate

            if transaction.quantity < 0:  # Sell transaction
                sell_value += current_price * abs(transaction.quantity)
                sell_quantity += abs(transaction.quantity)
            else:  # Buy transaction
                buy_value += current_price * transaction.quantity
                buy_quantity += transaction.quantity

        # For short positions (including closed shorts), return the average sell price
        # This is the "entry price" for the short position
        if sell_quantity >= buy_quantity and sell_quantity > 0:
            avg_sell_price = sell_value / sell_quantity
            logger.debug(f"Short position buy-in price (avg sell): {avg_sell_price}")
            return round(avg_sell_price, 6)

    # For long positions, use the original calculation logic
    value_entry = Decimal(0)
    quantity_entry = Decimal(0)
    previous_entry_price = Decimal(0)

    for transaction in transactions:
        logger.debug(
            f"Processing transaction: Date={transaction.date}, "
            f"Quantity={transaction.quantity}, Price={transaction.price}"
        )

        if currency is not None:
            fx_rate = _fx_get_rate(transaction.currency, currency, transaction.date)[
                "FX"
            ]
        else:
            fx_rate = Decimal(1)
        logger.debug(f"FX rate: {fx_rate}")

        # Use price as-is (percentage for bonds, actual for others)
        current_price = transaction.price * fx_rate
        weight_current = transaction.quantity

        # Calculate entry price
        previous_entry_price = (
            value_entry / quantity_entry if quantity_entry != 0 else Decimal(0)
        )
        weight_entry_previous = quantity_entry
        # For long positions, use the current price for buy transactions
        entry_price = (
            current_price
            if (is_long_position and transaction.quantity > 0)
            else previous_entry_price
        )

        if (weight_entry_previous + weight_current) == 0:
            entry_price = previous_entry_price
        else:
            entry_price = (
                previous_entry_price * weight_entry_previous
                + entry_price * weight_current
            ) / (weight_entry_previous + weight_current)

        quantity_entry += transaction.quantity
        value_entry = entry_price * quantity_entry

        logger.debug(
            f"After transaction: Entry price={entry_price}, "
            f"Quantity={quantity_entry}, Value={value_entry}"
        )

    final_price = (
        round(Decimal(value_entry / quantity_entry), 6)
        if quantity_entry
        else previous_entry_price
    )
    logger.debug(f"Final buy-in price: {final_price}")
    return final_price


# ---------------------------------------------------------------------------
# get_economic_basis
# ---------------------------------------------------------------------------


def get_economic_basis(
    asset,
    date_as_of,
    investor,
    currency=None,
    account_ids=None,
    start_date=None,
    exclude_transaction_id=None,
    rounded=True,
):
    """Return paid basis plus reward event value for current crypto lots."""
    target_currency = currency or asset.currency

    def transaction_fx_rate(transaction, target):
        if target is not None and transaction.currency != target:
            return _fx_get_rate(transaction.currency, target, transaction.date)["FX"]
        return Decimal(1)

    def provider_matches(provider):
        if provider:
            return Q(import_provider=provider)
        return Q(import_provider__isnull=True) | Q(import_provider="")

    def filter_until(query, cutoff_date):
        if isinstance(cutoff_date, datetime):
            return query.filter(date__lte=cutoff_date)
        return query.filter(date__date__lte=cutoff_date)

    def transfer_group_key(transaction):
        if not transaction.import_group_id:
            return None
        return (transaction.import_provider or "", transaction.import_group_id)

    def transfer_source_key(transaction):
        return (transaction.account_id, transaction.import_account_id or "")

    def add_group_carry(carried_basis_by_group, group_key, source_key, basis, quantity):
        if not group_key or quantity <= 0:
            return
        group_carry = carried_basis_by_group.setdefault(
            group_key,
            {
                "basis": Decimal(0),
                "quantity": Decimal(0),
                "source_keys": set(),
            },
        )
        group_carry["basis"] += basis
        group_carry["quantity"] += quantity
        group_carry["source_keys"].add(source_key)

    def allocate_group_carry(carried_basis_by_group, group_key, quantity):
        group_carry = carried_basis_by_group.get(group_key)
        requested_quantity = abs(quantity or Decimal(0))
        if (
            not group_carry
            or requested_quantity <= 0
            or group_carry["quantity"] <= 0
            or len(group_carry["source_keys"]) != 1
        ):
            return Decimal(0)

        allocated_quantity = min(requested_quantity, group_carry["quantity"])
        allocated_basis = (
            group_carry["basis"] * allocated_quantity / group_carry["quantity"]
        )
        group_carry["basis"] -= allocated_basis
        group_carry["quantity"] -= allocated_quantity
        if group_carry["quantity"] <= 0:
            carried_basis_by_group.pop(group_key, None)
        return allocated_basis

    def transactions_until(cutoff_date, selected_account_ids=None):
        query = filter_until(
            asset.transactions.filter(
                quantity__isnull=False,
                investor=investor,
            ),
            cutoff_date,
        )
        if selected_account_ids is not None:
            query = query.filter(account_id__in=selected_account_ids)
        if exclude_transaction_id is not None:
            query = query.exclude(id=exclude_transaction_id)
        return query.order_by("date", "id")

    def transactions_before(transaction):
        query = asset.transactions.filter(
            (
                Q(date__lt=transaction.date)
                | (Q(date=transaction.date) & Q(id__lt=transaction.id))
            ),
            quantity__isnull=False,
            investor=investor,
            account_id=transaction.account_id,
            security=asset,
        )
        return query.order_by("date", "id")

    def replay(
        transactions,
        target,
        allow_group_lookup=True,
        visited_transfer_ids=None,
        return_state=False,
    ):
        basis = Decimal(0)
        position = Decimal(0)
        average_basis = Decimal(0)
        carried_basis_by_group = {}
        visited_transfer_ids = visited_transfer_ids or frozenset()

        for transaction in transactions:
            quantity = transaction.quantity or Decimal(0)
            fx_rate = transaction_fx_rate(transaction, target)

            if _transactions_is_paid_entry_transaction(transaction):
                if transaction.price is not None:
                    csize = _option_contract_size(asset)  # Decimal(1) for non-options
                    basis += quantity * transaction.price * csize * fx_rate
                position += quantity
            elif _transactions_is_reward_transaction(transaction):
                basis += _transactions_reward_value(transaction) * fx_rate
                position += quantity
            elif _transactions_is_disposal_transaction(transaction):
                disposed_quantity = (
                    min(abs(quantity), position) if position > 0 else Decimal(0)
                )
                basis -= average_basis * disposed_quantity
                position += quantity
                if position <= 0:
                    basis = Decimal(0)
                    average_basis = Decimal(0)
                    continue
            elif transaction.type == TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT:
                transferred_quantity = (
                    min(abs(quantity), position) if position > 0 else Decimal(0)
                )
                transferred_basis = average_basis * transferred_quantity
                basis -= transferred_basis
                group_key = transfer_group_key(transaction)
                add_group_carry(
                    carried_basis_by_group,
                    group_key,
                    transfer_source_key(transaction),
                    transferred_basis,
                    transferred_quantity,
                )
                position += quantity
                if position <= 0:
                    basis = Decimal(0)
                    average_basis = Decimal(0)
                    continue
            elif transaction.type == TRANSACTION_TYPE_CRYPTO_TRANSFER_IN:
                group_key = transfer_group_key(transaction)
                if group_key:
                    carried_basis = allocate_group_carry(
                        carried_basis_by_group,
                        group_key,
                        quantity,
                    )
                    basis += carried_basis
                    if allow_group_lookup and carried_basis == 0:
                        basis += lookup_group_transfer_basis(
                            transaction,
                            target,
                            visited_transfer_ids,
                        )
                position += quantity

            average_basis = basis / position if position else Decimal(0)

        if return_state:
            return basis, position
        return basis

    def lookup_group_transfer_basis(transaction, target, visited_transfer_ids=None):
        if not transaction.import_group_id:
            return Decimal(0)
        visited_transfer_ids = visited_transfer_ids or frozenset()

        transfer_out_query = asset.transactions.filter(
            investor=investor,
            security=asset,
            import_group_id=transaction.import_group_id,
            type=TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
            quantity__lt=0,
        ).filter(
            provider_matches(transaction.import_provider),
            Q(date__lt=transaction.date)
            | (Q(date=transaction.date) & Q(id__lt=transaction.id)),
        )

        transfer_outs = list(
            transfer_out_query.exclude(id=transaction.id).order_by("date", "id")
        )
        if not transfer_outs:
            return Decimal(0)
        if (
            len({transfer_source_key(transfer_out) for transfer_out in transfer_outs})
            != 1
        ):
            return Decimal(0)

        total_transferred_basis = Decimal(0)
        total_transferred_quantity = Decimal(0)
        visited_ids = visited_transfer_ids | frozenset(
            transfer_out.id for transfer_out in transfer_outs
        )
        for transfer_out in transfer_outs:
            if transfer_out.id in visited_transfer_ids:
                return Decimal(0)

            source_basis, source_position = replay(
                transactions_before(transfer_out),
                target,
                allow_group_lookup=True,
                visited_transfer_ids=visited_ids,
                return_state=True,
            )
            if source_position <= 0:
                continue

            transferred_quantity = min(
                abs(transfer_out.quantity or Decimal(0)),
                source_position,
            )
            if transferred_quantity <= 0:
                continue

            total_transferred_quantity += transferred_quantity
            total_transferred_basis += (
                source_basis / source_position
            ) * transferred_quantity

        if total_transferred_quantity <= 0:
            return Decimal(0)

        first_transfer_out = transfer_outs[0]
        prior_transfer_in_quantity = asset.transactions.filter(
            (
                Q(date__gt=first_transfer_out.date)
                | (Q(date=first_transfer_out.date) & Q(id__gt=first_transfer_out.id))
            ),
            (
                Q(date__lt=transaction.date)
                | (Q(date=transaction.date) & Q(id__lt=transaction.id))
            ),
            investor=investor,
            security=asset,
            import_group_id=transaction.import_group_id,
            type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
            quantity__gt=0,
        ).filter(provider_matches(transaction.import_provider)).aggregate(
            total=Sum("quantity")
        )["total"] or Decimal(0)
        remaining_quantity = total_transferred_quantity - min(
            prior_transfer_in_quantity,
            total_transferred_quantity,
        )
        allocated_quantity = min(
            abs(transaction.quantity or Decimal(0)),
            max(remaining_quantity, Decimal(0)),
        )
        return (
            total_transferred_basis / total_transferred_quantity
        ) * allocated_quantity

    basis = replay(transactions_until(date_as_of, account_ids), target_currency)
    if not rounded:
        return basis
    return basis.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# realized_gain_loss
# ---------------------------------------------------------------------------


def realized_gain_loss(
    asset, date_as_of, investor, currency=None, account_ids=None, start_date=None
):
    """
    Calculate the realized gain/loss for an asset.

    Calculates the realized gain/loss for an asset
    and breaks it down into components price appreciation, and FX effect.

    Parameters:
        asset (Asset): The asset object for which realized gain/loss is calculated.
        date_as_of (datetime.date): The date as of which the calculation is performed.
        investor (User): The investor for which the calculation is performed.
        currency (str): The reporting currency.
        account_ids (list): The list of account IDs.
        start_date (datetime.date): The start date for the calculation.
    """

    def calculate_position_gain_loss(start, end, investor):
        """Calculate the position gain/loss helper function."""
        result = {
            "price_appreciation": Decimal(0),
            "fx_effect": Decimal(0),
            "total": Decimal(0),
        }

        transactions = asset.transactions.filter(
            quantity__isnull=False, investor=investor
        )
        if isinstance(start, datetime):
            transactions = transactions.filter(date__gte=start)
        else:
            transactions = transactions.filter(date__date__gte=start)
        if isinstance(end, datetime):
            transactions = transactions.filter(date__lte=end)
        else:
            transactions = transactions.filter(date__date__lte=end)
        transactions = transactions.order_by("date", "id")
        if account_ids is not None:
            transactions = transactions.filter(account_id__in=account_ids)

        position_query = asset.transactions.filter(
            quantity__isnull=False,
            investor=investor,
        )
        if isinstance(start, datetime):
            position_query = position_query.filter(date__lt=start)
        else:
            position_query = position_query.filter(date__date__lt=start)
        if account_ids is not None:
            position_query = position_query.filter(account_id__in=account_ids)
        position = position_query.aggregate(total=Sum("quantity"))["total"] or Decimal(
            0
        )
        logger.debug(f"Starting position at {start}: {position}")

        for transaction in transactions:
            logger.debug(
                f"Transaction: {transaction.date}, {transaction.type}, "
                f"Quantity: {transaction.quantity}, "
                f"Price: {_transactions_get_price(transaction)}"
            )

            # Check if this is a bond redemption transaction
            is_bond_redemption = transaction.type in [
                TRANSACTION_TYPE_BOND_REDEMPTION,
                TRANSACTION_TYPE_BOND_MATURITY,
            ]

            # Handle bond redemptions separately
            if is_bond_redemption:
                # For bond redemption:
                # gain = cash_received - (notional_redeemed * buy_in_price)
                # Gain is zero only if bought at par and redeemed at par
                cash_received = transaction.cash_flow or Decimal(0)
                notional_redeemed_per_bond = getattr(
                    transaction, "notional_change", None
                )
                notional_redeemed = notional_redeemed_per_bond * _positions_position(
                    transaction.security, transaction.date, investor, account_ids
                )

                logger.debug(
                    f"Bond redemption: cash_flow={cash_received}, "
                    f"Total notional redeemed={notional_redeemed}, "
                    f"Per-bond notional redeemed={notional_redeemed_per_bond}"
                )

                if notional_redeemed and notional_redeemed != 0:
                    buy_in_price_target_currency = calculate_buy_in_price(
                        asset, transaction.date, investor, currency, account_ids, start
                    )
                    buy_in_price_lcl_currency = calculate_buy_in_price(
                        asset,
                        transaction.date,
                        investor,
                        transaction.currency,
                        account_ids,
                        start,
                    )

                    if (
                        buy_in_price_target_currency is not None
                        and buy_in_price_lcl_currency is not None
                    ):
                        fx_rate_exit = (
                            _fx_get_rate(
                                transaction.currency, currency, transaction.date
                            )["FX"]
                            if currency
                            else 1
                        )

                        # Redemption G/L = notional_redeemed_per_bond * quantity * (100 - buy_in_price%) # noqa: E501
                        # For bonds, buy_in_price is in percentage terms

                        # Price appreciation in local currency (100 = 100% of par = redemption at par) # noqa: E501
                        price_appreciation_lcl = (
                            cash_received
                            - notional_redeemed
                            * buy_in_price_lcl_currency
                            / Decimal(100)
                        )
                        price_appreciation = price_appreciation_lcl * fx_rate_exit

                        # Total G/L in target currency
                        gl_target_currency = (
                            cash_received * fx_rate_exit
                            - notional_redeemed
                            * buy_in_price_target_currency
                            / Decimal(100)
                        )

                        # FX effect
                        fx_effect = gl_target_currency - price_appreciation

                        result["total"] += Decimal(gl_target_currency)
                        result["price_appreciation"] += Decimal(price_appreciation)
                        result["fx_effect"] += Decimal(fx_effect)

                        logger.debug(
                            "Redemption G/L: notional_redeemed="
                            f"{notional_redeemed}, "
                            f"buy_in_price%={buy_in_price_lcl_currency}, "
                            f"gain={gl_target_currency}"
                        )

                # Position doesn't change for partial redemptions
                # (quantity is None/0)
                # For final redemption with negative quantity, update position
                if transaction.quantity:
                    position += transaction.quantity

                logger.debug(f"Position after redemption: {position}")
                continue

            if _transactions_is_neutral_transfer_transaction(transaction):
                # Pre-#29: all crypto transfers are neutral (internal wallet
                # moves cannot be distinguished from external flows). When
                # TRANSFER_DISPOSITION_ENABLED is True (#29), unmatched
                # transfers fall through to the disposal/entry branches below.
                if TRANSFER_DISPOSITION_ENABLED and not _transfer_is_matched(
                    transaction, investor, account_ids
                ):
                    logger.debug(
                        "Unmatched %s for asset %s: treating as disposition/entry.",
                        transaction.type, getattr(asset, "name", asset),
                    )
                    # fall through to is_position_reducing logic below
                else:
                    position += transaction.quantity
                    logger.debug(f"Position after neutral transfer: {position}")
                    continue

            is_position_reducing = (
                position > 0 and _transactions_is_disposal_transaction(transaction)
            ) or (
                position < 0 and _transactions_is_paid_entry_transaction(transaction)
            )

            # Determine the quantity that is actually closing the position
            # vs opening a new position in the opposite direction
            if position > 0 and _transactions_is_disposal_transaction(transaction):
                # Closing long: portion that closes is min(abs(tx.quantity), position)
                closing_quantity = -min(abs(transaction.quantity), position)
            elif position < 0 and _transactions_is_paid_entry_transaction(transaction):
                # Closing short: portion that closes is min(tx.quantity, abs(position))
                closing_quantity = min(transaction.quantity, abs(position))
            else:
                closing_quantity = transaction.quantity

            # --- Option close (sub-project 4) -------------------------------
            # An Option settlement row closes an open short/long at the terminal
            # price (0 OTM / intrinsic ITM). The premium received/paid lives on
            # the opening row's cash_flow; the settlement row's cash_flow already
            # carries the signed payout. Realized G/L = premium_at_open +
            # settlement_proceeds + fee_at_open (cash_flow carries sign). This
            # branch fires before the generic crypto/stock close so option-specific
            # math (contract_size, intrinsic) applies.
            if (
                options.is_option_asset(asset)
                and transaction.type == TRANSACTION_TYPE_OPTION_SETTLEMENT
            ):
                option_gl = _realized_option_close(
                    asset, transaction, position, investor, account_ids, start
                )
                result["price_appreciation"] += option_gl["price_appreciation"]
                result["fx_effect"] += option_gl["fx_effect"]
                result["total"] += option_gl["total"]
                position += transaction.quantity
                logger.debug(f"Position after option settlement: {position}")
                continue

            if is_position_reducing:
                # For position-reducing transactions, we need to calculate the buy-in price
                # for the portion that closes the existing position.
                #
                # For closing long positions (position > 0, SELL):
                #   - Use the avg buy price of the long position being closed
                #   - closing_quantity is the amount that closes the long position
                #   - The remaining transaction quantity opens a short position (no gain/loss)
                #
                # For closing short positions (position < 0, BUY):
                #   - Use the avg sell price that created the short position
                #   - closing_quantity is the amount that closes the short position
                #   - The remaining transaction quantity opens a long position (no gain/loss)
                #
                # We use position (before current transaction) for the buy-in price:
                # - If position > 0 (closing long): calculate avg buy price up to this point
                # - If position < 0 (closing short): calculate avg sell price
                #
                # Importantly: we calculate buy-in price using the running position, which
                # represents the quantity of shares that are actually being closed.

                if (
                    asset.type == ASSET_TYPE_CRYPTO
                    and position > 0
                    and transaction.type == TRANSACTION_TYPE_CRYPTO_TRADE_OUT
                ):
                    economic_basis_target_currency = get_economic_basis(
                        asset,
                        transaction.date,
                        investor,
                        currency,
                        account_ids,
                        start,
                        exclude_transaction_id=transaction.id,
                        rounded=False,
                    )
                    economic_basis_lcl_currency = get_economic_basis(
                        asset,
                        transaction.date,
                        investor,
                        transaction.currency,
                        account_ids,
                        start,
                        exclude_transaction_id=transaction.id,
                        rounded=False,
                    )
                    buy_in_price_target_currency = (
                        economic_basis_target_currency / position if position else None
                    )
                    buy_in_price_lcl_currency = (
                        economic_basis_lcl_currency / position if position else None
                    )
                elif position > 0:
                    # Closing long position: calculate avg buy price of these shares
                    # Use transaction.date and exclude current transaction to include
                    # same-day earlier transactions
                    buy_in_price_target_currency = calculate_buy_in_price(
                        asset,
                        transaction.date,
                        investor,
                        currency,
                        account_ids,
                        start,
                        exclude_transaction_id=transaction.id,
                    )
                    buy_in_price_lcl_currency = calculate_buy_in_price(
                        asset,
                        transaction.date,
                        investor,
                        transaction.currency,
                        account_ids,
                        start,
                        exclude_transaction_id=transaction.id,
                    )
                else:
                    # Closing short position: use the avg sell price that created the short
                    # Use transaction.date and exclude current transaction to include
                    # same-day earlier transactions
                    buy_in_price_target_currency = calculate_buy_in_price(
                        asset,
                        transaction.date,
                        investor,
                        currency,
                        account_ids,
                        start,
                        exclude_transaction_id=transaction.id,
                    )
                    buy_in_price_lcl_currency = calculate_buy_in_price(
                        asset,
                        transaction.date,
                        investor,
                        transaction.currency,
                        account_ids,
                        start,
                        exclude_transaction_id=transaction.id,
                    )

                logger.debug(
                    "Buy-in price in target currency: "
                    f"{buy_in_price_target_currency}, in LCL currency: "
                    f"{buy_in_price_lcl_currency}"
                )

                if (
                    buy_in_price_target_currency is not None
                    and buy_in_price_lcl_currency is not None
                ):
                    fx_rate_exit = (
                        _fx_get_rate(transaction.currency, currency, transaction.date)[
                            "FX"
                        ]
                        if currency
                        else 1
                    )

                    # For bonds: G/L = notional_at_sell * (sale_price% - buy_in_price%) * quantity_sold # noqa: E501
                    # For others: G/L = (sale_price - buy_in_price) * quantity_sold
                    if asset.is_bond:
                        notional_at_sell = asset.get_effective_notional(
                            transaction.date,
                            investor,
                            account_ids,
                            transaction.currency,
                        )

                        # Prices are in percentage terms
                        price_appreciation_lcl = (
                            notional_at_sell
                            * (transaction.price - buy_in_price_lcl_currency)
                            * (-transaction.quantity)
                            / Decimal(100)
                        )
                        price_appreciation = price_appreciation_lcl * fx_rate_exit

                        gl_target_currency = (
                            notional_at_sell
                            * (
                                transaction.price * fx_rate_exit
                                - buy_in_price_target_currency
                            )
                            * (-transaction.quantity)
                            / Decimal(100)
                        )
                    else:
                        # Standard calculation for non-bonds
                        # Use closing_quantity to only calculate gain/loss on the
                        # portion that actually closes the position (not the portion
                        # that opens a new one).
                        # Unmatched transfers carry no fill price (price=None);
                        # treat proceeds as 0 (a withdrawal receives no cash, a
                        # deposit adds basis at zero/FMV).
                        tx_price = (
                            transaction.price
                            if transaction.price is not None
                            else Decimal(0)
                        )
                        price_appreciation = (
                            -(tx_price - buy_in_price_lcl_currency)
                            * closing_quantity
                            * fx_rate_exit
                        )
                        gl_target_currency = (
                            -(tx_price * fx_rate_exit - buy_in_price_target_currency)
                            * closing_quantity
                        )

                    fx_effect = gl_target_currency - price_appreciation

                    result["total"] += Decimal(gl_target_currency)
                    result["price_appreciation"] += Decimal(price_appreciation)
                    result["fx_effect"] += Decimal(fx_effect)

                    logger.debug(
                        f"Realized G/L for this transaction: {gl_target_currency}"
                    )

            position += transaction.quantity
            logger.debug(f"Position after transaction: {position}")

        logger.debug(f"Final position at {end}: {position}")
        return result

    result = {
        "current_position": {
            "price_appreciation": Decimal(0),
            "fx_effect": Decimal(0),
            "total": Decimal(0),
        },
        "all_time": {
            "price_appreciation": Decimal(0),
            "fx_effect": Decimal(0),
            "total": Decimal(0),
        },
    }

    # Convert date_as_of to datetime object if it's a date
    if date_as_of and isinstance(date_as_of, date):
        date_as_of = datetime.combine(date_as_of, datetime.max.time()).replace(
            tzinfo=None
        )
    elif date_as_of and isinstance(date_as_of, datetime):
        pass
    elif date_as_of is None:
        pass
    else:
        raise ValueError("Invalid date_as_of")

    # Convert start_date to datetime object if it's a date
    if start_date and isinstance(start_date, date):
        start_date = datetime.combine(start_date, datetime.min.time()).replace(
            tzinfo=None
        )
    elif start_date and isinstance(start_date, datetime):
        pass
    elif start_date is None:
        pass
    else:
        raise ValueError("Invalid start_date")

    # Calculate all-time realized gain/loss
    exit_dates = _positions_exit_dates(
        asset, date_as_of, investor, account_ids, start_date
    )
    entry_dates = _positions_entry_dates(
        asset, date_as_of, investor, account_ids, start_date
    )

    if start_date is not None and len(entry_dates) == 0:
        entry_dates = [start_date]

    logger.debug(f"Exit dates: {exit_dates}")
    logger.debug(f"Entry dates: {entry_dates}")

    # Pair entry and exit dates
    date_pairs = []
    for entry_date in entry_dates:
        exit_date = next((d for d in exit_dates if d >= entry_date), date_as_of)
        date_pairs.append((entry_date, exit_date))

    # Adjust date pairs based on start_date and end_date
    adjusted_pairs = []
    for entry_date, exit_date in date_pairs:
        logger.debug(f"Unadjusted pair: {entry_date} to {exit_date}")

        if start_date and start_date > entry_date and start_date <= exit_date:
            entry_date = start_date
        if exit_date > date_as_of and date_as_of >= start_date:
            exit_date = date_as_of
        adjusted_pairs.append((entry_date, exit_date))

    logger.debug(f"Adjusted date pairs: {adjusted_pairs}")

    # Calculate gain/loss for each position
    for position_start, position_end in adjusted_pairs:
        logger.debug(f"Calculating for position: {position_start} to {position_end}")
        position_result = calculate_position_gain_loss(
            position_start, position_end, investor
        )
        logger.debug(f"Position result: {position_result}")

        for key in result["all_time"]:
            result["all_time"][key] += position_result[key]

        # If this is the current position,
        # update the current_position result as well
        if position_end == date_as_of and position_end not in exit_dates:
            result["current_position"] = position_result.copy()

        logger.debug(f"Current position result: {result['current_position']}")

    # Round all results to 2 decimal places
    for period in result:
        for component in result[period]:
            result[period][component] = round(result[period][component], 2)

    return result


# ---------------------------------------------------------------------------
# unrealized_gain_loss
# ---------------------------------------------------------------------------


def unrealized_gain_loss(
    asset, date_as_of, investor, currency=None, account_ids=None, start_date=None
):
    """
    Calculate the unrealized gain/loss for an asset.

    Calculates the unrealized gain/loss for an asset
    and breaks it down into components price appreciation, and FX effect.

    Parameters:
        asset (Asset): The asset object for which unrealized gain/loss is calculated.
        date_as_of (datetime.date): The date as of which the calculation is performed.
        investor (CustomUser): The investor for whom the calculation is performed.
        currency (str): The reporting currency.
        account_ids (list): List of broker account IDs to filter transactions.
        start_date (datetime.date): The start date for calculating buy-in price.

    Returns:
        dict: A dictionary containing the breakdown of unrealized gain/loss:
            - 'price_appreciation': Price appreciation in reporting currency.
            - 'fx_effect': FX effect in reporting currency.
            - 'total': Total unrealized gain/loss in reporting currency.
    """
    # Options (sub-project 4): unrealized G/L is not meaningful for option
    # positions because ``get_economic_basis`` is long-only — a written (short)
    # option zeros its basis on open, so the generic unrealized path would
    # report the full negative mark as "unrealized loss" rather than the
    # NAV-neutral 0. Realized G/L at expiry is correct (``_realized_option_close``);
    # NAV values the liability via the dedicated option-mark branch. A future
    # sub-project may add true option unrealized G/L; until then, return zeros
    # so the UI does not display a misleading number.
    if options.is_option_asset(asset):
        return {
            "price_appreciation": Decimal(0),
            "fx_effect": Decimal(0),
            "total": Decimal(0),
        }

    unrealized_gain_loss = 0
    price_appreciation = 0
    fx_effect = 0

    if asset.type == ASSET_TYPE_CRYPTO:
        current_position_query = asset.transactions.filter(
            quantity__isnull=False,
            investor=investor,
        )
        if isinstance(date_as_of, datetime):
            current_position_query = current_position_query.filter(date__lte=date_as_of)
        else:
            current_position_query = current_position_query.filter(
                date__date__lte=date_as_of
            )
        if account_ids is not None:
            current_position_query = current_position_query.filter(
                account_id__in=account_ids
            )
        current_position = current_position_query.aggregate(total=Sum("quantity"))[
            "total"
        ] or Decimal(0)
    else:
        current_position = _positions_position(asset, date_as_of, investor, account_ids)

    current_price_in_lcl_cur = (
        _pricing_price_at_date(asset, date_as_of, currency=None).price
        if _pricing_price_at_date(asset, date_as_of)
        else 0
    )
    current_price_in_target_cur = (
        _pricing_price_at_date(asset, date_as_of, currency).price
        if _pricing_price_at_date(asset, date_as_of)
        else 0
    )
    buy_in_price_in_lcl_cur = calculate_buy_in_price(
        asset,
        date_as_of,
        investor,
        currency=None,
        account_ids=account_ids,
        start_date=start_date,
    )
    buy_in_price_in_target_cur = calculate_buy_in_price(
        asset, date_as_of, investor, currency, account_ids, start_date
    )

    fx_rate_eop = (
        _fx_get_rate(asset.currency, currency, date_as_of)["FX"] if currency else 1
    )

    if asset.type == ASSET_TYPE_CRYPTO:
        economic_basis_lcl_cur = get_economic_basis(
            asset,
            date_as_of,
            investor,
            asset.currency,
            account_ids=account_ids,
            start_date=start_date,
            rounded=False,
        )
        economic_basis_target_cur = get_economic_basis(
            asset,
            date_as_of,
            investor,
            currency or asset.currency,
            account_ids=account_ids,
            start_date=start_date,
            rounded=False,
        )
        current_value_lcl_cur = current_price_in_lcl_cur * current_position
        current_value_target_cur = current_price_in_target_cur * current_position
        price_appreciation = (
            current_value_lcl_cur - economic_basis_lcl_cur
        ) * fx_rate_eop
        unrealized_gain_loss = current_value_target_cur - economic_basis_target_cur
        fx_effect = unrealized_gain_loss - price_appreciation
    elif buy_in_price_in_lcl_cur is not None and buy_in_price_in_target_cur is not None:
        # For bonds: unrealized G/L = notional_at_date * (price_at_date% - buy_in_price%) * position / 100 # noqa: E501
        # For others: unrealized G/L = (current_price - buy_in_price) * position
        if asset.is_bond:
            notional_lcl = asset.get_effective_notional(
                date_as_of, investor, account_ids
            )

            price_appreciation = (
                notional_lcl
                * (current_price_in_lcl_cur - buy_in_price_in_lcl_cur)
                * current_position
                * fx_rate_eop
                / Decimal(100)
            )
            unrealized_gain_loss = (
                notional_lcl
                * (current_price_in_target_cur - buy_in_price_in_target_cur)
                * current_position
                / Decimal(100)
            )
        else:
            price_appreciation = (
                (current_price_in_lcl_cur - buy_in_price_in_lcl_cur)
                * current_position
                * fx_rate_eop
            )
            unrealized_gain_loss = (
                current_price_in_target_cur - buy_in_price_in_target_cur
            ) * current_position

        fx_effect = unrealized_gain_loss - price_appreciation

    return {
        "price_appreciation": round(Decimal(price_appreciation), 2),
        "fx_effect": round(Decimal(fx_effect), 2),
        "total": round(Decimal(unrealized_gain_loss), 2),
    }
