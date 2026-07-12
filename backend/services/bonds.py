"""Bond business-logic service.

Owns the bond calculations that previously lived as methods on the
``BondMetadata`` model (``common.models``) and as module-level functions in
``core.securities_utils``:

- :func:`get_current_notional` — FX-converts per-bond notional, honouring
  amortization via ``NotionalHistory`` (with a transactions fallback).
- :func:`get_current_aci` — accrued coupon interest for a given date, with
  floating-rate fallback to MICEX and lazy T-Bank schedule fetching.
- :func:`get_total_aci_for_position` — position-wide ACI net of ACI paid at
  acquisition in the current coupon period.
- :func:`build_bond_cash_flows` — builds the coupon + redemption cash-flow
  list used by the YTM (XIRR) calculation.
- :func:`calculate_bond_ytm` — bond yield-to-maturity via XIRR.

Numeric safety: ``Decimal`` everywhere for notional, ACI, coupon rates and
FX-converted amounts. Never ``float`` (the YTM cash-flow list is the one
deliberate exception — ``pyxirr.xirr`` consumes ``(date, float)`` tuples).

Import graph: this module imports from ``services.fx`` and
``services.positions`` (one-way, no cycle). The network fetchers in
``services.importer`` and ``core.micex_aci_utils`` are imported lazily inside
``get_current_aci`` so they only execute when needed and to avoid import
cycles.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from django.db.models import Q, Sum
from pyxirr import xirr

from common.models import (
    NotionalHistory,
    Transactions,
)
from constants import (
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_BOND_REDEMPTION,
)
from services.fx import get_rate as fx_get_rate
from services.positions import position as positions_position

logger = logging.getLogger(__name__)


# =============================================================================
# BondMetadata methods (self -> bond_meta)
# =============================================================================


def get_current_notional(bond_meta, date, investor=None, account_ids=None, currency=None):
    """
    Get the current notional value per bond at a given date.

    For non-amortizing bonds, returns the initial notional.
    For amortizing bonds, uses NotionalHistory if available,
    otherwise calculates from redemption transactions.

    Args:
        bond_meta: The BondMetadata instance
        date: The date for which to get the notional
        investor: Optional investor filter
        account_ids: Optional account IDs filter
        currency: Optional currency filter
    Returns:
        Decimal: The notional value per bond at the given date
    """
    if currency is None:
        currency = bond_meta.asset.currency

    # Use nominal_currency if available, otherwise fall back to asset.currency
    source_currency = bond_meta.nominal_currency or bond_meta.asset.currency
    fx_rate = fx_get_rate(source_currency, currency, date)["FX"]
    logger.debug(
        f"FX rate for {bond_meta.asset.name} at {date} "
        f"({source_currency} to {currency}): {fx_rate}"
    )

    if not bond_meta.is_amortizing:
        return bond_meta.initial_notional * fx_rate

    # Try to get from NotionalHistory first (more efficient and accurate)
    try:
        latest_history = (
            NotionalHistory.objects.filter(asset=bond_meta.asset, date__lte=date)
            .order_by("-date")
            .first()
        )

        if latest_history:
            logger.debug(
                f"Using NotionalHistory for {bond_meta.asset.name} at {date}: "
                f"{latest_history.notional_per_unit}"
            )
            return latest_history.notional_per_unit * fx_rate
    except Exception as e:
        logger.warning(f"Error fetching NotionalHistory: {e}, falling back to transactions")

    # Fallback: Calculate from transactions
    if not investor:
        logger.warning(
            "No NotionalHistory found and no investor provided for "
            f"{bond_meta.asset.name}, "
            f"returning initial notional"
        )
        return bond_meta.initial_notional * fx_rate

    redemption_filter = Q(
        security=bond_meta.asset,
        investor=investor,
        date__lte=date,
        type__in=[TRANSACTION_TYPE_BOND_REDEMPTION, TRANSACTION_TYPE_BOND_MATURITY],
    )

    # Ensure account_ids is a list for the __in lookup
    if account_ids:
        if isinstance(account_ids, int):
            account_ids = [account_ids]
        redemption_filter &= Q(account_id__in=account_ids)

    redemptions = Transactions.objects.filter(redemption_filter).aggregate(
        total_redeemed=Sum("notional_change")
    )["total_redeemed"] or Decimal(0)

    current_notional = (bond_meta.initial_notional) - abs(redemptions)
    logger.debug(
        f"Calculated notional from transactions for {bond_meta.asset.name}: "
        f"{current_notional} (initial: {bond_meta.initial_notional}, "
        f"redeemed: {redemptions})"
    )

    return current_notional


def get_current_aci(bond_meta, date, currency=None, user=None, force_refresh=False):
    """
    Calculate the accrued interest for this bond at a given date.

    Uses the cached coupon schedule from BondCouponSchedule.
    If schedule is not available, and user is provided,
    attempts to fetch it from T-Bank API as fallback.

    Args:
        bond_meta: The BondMetadata instance
        date: The date for which to calculate ACI
        currency: Optional currency for FX conversion (defaults to nominal_currency)
        user: Optional CustomUser to fetch schedule from API if not cached
        force_refresh: If True, refresh schedule even if it
            (for floating-rate bonds)

    Returns:
        dict with:
            - 'aci_amount': Decimal - ACI amount in requested currency per bond
            - 'aci_days': int - Number of days accrued
            - 'total_days': int - Total days in coupon period
            - 'coupon_start': date - Start of current coupon period
            - 'coupon_end': date - End of current coupon period
            - 'next_payment': date - Next coupon payment date
        Returns None if schedule is not available or bond has matured
    """
    # Local import to avoid pulling common.modelsBondCouponSchedule at module
    # load (and to keep the import graph one-way).
    from common.models import BondCouponSchedule

    # Find the relevant coupon period for this date
    # Get the most recent coupon end date that is >= date
    try:
        current_coupon = (
            BondCouponSchedule.objects.filter(asset=bond_meta.asset, coupon_start_date__lte=date)
            .order_by("-coupon_start_date")
            .first()
        )

        # Fallback: fetch schedule if not found and user is provided
        if not current_coupon and user:
            logger.info(
                f"No coupon schedule found for {bond_meta.asset.name}, "
                "attempting to fetch from API"
            )
            try:
                from asgiref.sync import async_to_sync

                from services.importer import fetch_and_cache_bond_coupon_schedule

                success = async_to_sync(fetch_and_cache_bond_coupon_schedule)(
                    bond_meta.asset, user, force_refresh=False
                )

                if success:
                    # Try again after fetching
                    current_coupon = (
                        BondCouponSchedule.objects.filter(
                            asset=bond_meta.asset, coupon_start_date__lte=date
                        )
                        .order_by("-coupon_start_date")
                        .first()
                    )
            except Exception as e:
                logger.error(f"Failed to fetch coupon schedule for {bond_meta.asset.name}: {e}")

        # Check if coupon_amount is empty (floating-rate bond)
        # and force_refresh is needed
        if current_coupon and not current_coupon.coupon_amount and user and force_refresh:
            logger.info(f"Coupon amount empty for {bond_meta.asset.name}, refreshing schedule")
            try:
                from asgiref.sync import async_to_sync

                from services.importer import fetch_and_cache_bond_coupon_schedule

                async_to_sync(fetch_and_cache_bond_coupon_schedule)(
                    bond_meta.asset, user, force_refresh=True
                )

                # Reload current coupon
                current_coupon = (
                    BondCouponSchedule.objects.filter(
                        asset=bond_meta.asset, coupon_start_date__lte=date
                    )
                    .order_by("-coupon_start_date")
                    .first()
                )
            except Exception as e:
                logger.error(f"Failed to refresh coupon schedule for {bond_meta.asset.name}: {e}")

        if not current_coupon:
            logger.warning(
                f"No coupon schedule found for {bond_meta.asset.name} at {date}. "
                f"Provide 'user' parameter to fetch from API."
            )
            return None

        # Check if date is past bond maturity
        if bond_meta.maturity_date:
            # Convert to date objects for comparison
            if hasattr(bond_meta.maturity_date, "date"):
                maturity_date = bond_meta.maturity_date.date()
            else:
                maturity_date = bond_meta.maturity_date

            if hasattr(date, "date"):
                date_compare = date.date()
            else:
                date_compare = date

            if date_compare >= maturity_date:
                logger.debug(f"Bond {bond_meta.asset.name} has matured, no ACI")
                return None

        # Calculate days in period
        coupon_start = current_coupon.coupon_start_date
        coupon_end = current_coupon.coupon_end_date

        # Validate that coupon dates exist
        if not coupon_start or not coupon_end:
            logger.error(
                f"Invalid coupon schedule for {bond_meta.asset.name}: "
                f"coupon_start={coupon_start}, coupon_end={coupon_end}"
            )
            return None

        # Convert to date objects for comparison
        if hasattr(coupon_start, "date"):
            coupon_start_date = coupon_start.date()
        else:
            coupon_start_date = coupon_start

        if hasattr(coupon_end, "date"):
            coupon_end_date = coupon_end.date()
        else:
            coupon_end_date = coupon_end

        if hasattr(date, "date"):
            date_compare = date.date()
        else:
            date_compare = date

        # Days accrued: from start to current date
        # (inclusive of start, exclusive of end)
        # Standard day count convention: actual/actual for most bonds
        days_accrued = (date_compare - coupon_start_date).days
        total_days = (coupon_end_date - coupon_start_date).days

        # Don't allow negative days (if date is before coupon start)
        if days_accrued < 0:
            days_accrued = 0

        # Calculate ACI
        if current_coupon.coupon_amount and total_days > 0:
            # Use the exact coupon amount from schedule
            aci_amount = (
                Decimal(current_coupon.coupon_amount)
                * Decimal(days_accrued)
                / Decimal(total_days)
            )
        elif bond_meta.coupon_rate and bond_meta.initial_notional and total_days > 0:
            # Fallback: calculate from coupon rate and notional
            # Annual coupon = notional * rate / 100
            # Period coupon = annual / frequency
            if bond_meta.coupon_frequency:
                period_coupon = (
                    bond_meta.initial_notional
                    * bond_meta.coupon_rate
                    / Decimal(100)
                    / bond_meta.coupon_frequency
                )
                aci_amount = period_coupon * Decimal(days_accrued) / Decimal(total_days)
            else:
                logger.warning(
                    "No coupon_frequency for {bond_meta.asset.name}, " "cannot calculate ACI"
                )
                return None
        else:
            logger.warning(
                f"Insufficient data to calculate ACI for {bond_meta.asset.name}: "
                f"coupon_amount={current_coupon.coupon_amount}, "
                f"coupon_rate={bond_meta.coupon_rate}, "
                f"initial_notional={bond_meta.initial_notional}"
            )

            # Fallback: Try to fetch ACI from MICEX for floating-rate bonds
            if bond_meta.asset.secid:
                logger.info(
                    f"Attempting to fetch ACI from MICEX for floating-rate bond "
                    f"{bond_meta.asset.name} (secid: {bond_meta.asset.secid})"
                )
                from core.micex_aci_utils import fetch_aci_from_micex

                micex_aci = fetch_aci_from_micex(bond_meta.asset.secid, date)

                if micex_aci:
                    # Got ACI from MICEX, convert currency if needed
                    aci_amount = micex_aci["aci_amount"]
                    micex_currency = micex_aci["currency"]

                    if currency and currency != micex_currency:
                        fx_rate = fx_get_rate(micex_currency, currency, date)["FX"]
                        aci_amount *= fx_rate
                        result_currency = currency
                    else:
                        result_currency = micex_currency

                    logger.info(
                        "Successfully retrieved ACI from MICEX for "
                        f"{bond_meta.asset.name}: "
                        f"{aci_amount} {result_currency}"
                    )

                    return {
                        "aci_amount": round(aci_amount, 2),
                        "aci_days": days_accrued,
                        "total_days": total_days,
                        "coupon_start": coupon_start,
                        "coupon_end": coupon_end,
                        "next_payment": current_coupon.payment_date,
                        "currency": result_currency,
                        "source": "MICEX",  # Indicate data source
                    }
                else:
                    logger.warning(
                        f"Failed to fetch ACI from MICEX for {bond_meta.asset.name}, "
                        f"returning None"
                    )

            return None

        # Convert currency if requested
        if currency and currency != (bond_meta.nominal_currency or bond_meta.asset.currency):
            source_currency = bond_meta.nominal_currency or bond_meta.asset.currency
            fx_rate = fx_get_rate(source_currency, currency, date)["FX"]
            aci_amount *= fx_rate
        else:
            currency = bond_meta.nominal_currency or bond_meta.asset.currency

        return {
            "aci_amount": round(aci_amount, 2),
            "aci_days": days_accrued,
            "total_days": total_days,
            "coupon_start": coupon_start_date,
            "coupon_end": coupon_end_date,
            "next_payment": current_coupon.payment_date,
            "currency": currency,
        }

    except Exception as e:
        logger.error(f"Error calculating ACI for {bond_meta.asset.name}: {e}", exc_info=True)
        return None


def get_total_aci_for_position(
    bond_meta, date, investor, currency=None, account_ids=None, user=None
):
    """
    Calculate total ACI for the entire bond position.

    Returns current ACI per bond * position, net of ACI paid at acquisition in the current coupon period. # noqa: E501

    This shows the "net accrued interest" value:
    - Current ACI per bond (what would be received if sold today)
    - Multiplied by position quantity
    - Minus ACI paid when initially acquiring bonds in this coupon period

    Args:
        bond_meta: The BondMetadata instance
        date: The date for which to calculate total ACI
        investor: The investor whose position to calculate
        currency: Optional currency for conversion
        account_ids: Optional account filter
        user: Optional user for API fallback

    Returns:
        Decimal: Total ACI amount for the position in specified currency
    """
    # Get current ACI per bond
    aci_data = get_current_aci(bond_meta, date, currency, user)
    if not aci_data:
        return Decimal(0)

    # Get current position
    position_qty = positions_position(bond_meta.asset, date, investor, account_ids)
    if not position_qty or position_qty == 0:
        return Decimal(0)

    # Total ACI for position
    total_aci = aci_data["aci_amount"] * Decimal(position_qty)

    # Subtract ACI paid when buying in the current coupon period
    # (to show net accrued interest since acquisition)
    current_coupon_start = aci_data.get("coupon_start")
    if current_coupon_start:
        query_date = date
        query_coupon_start = current_coupon_start

        aci_paid_in_period = bond_meta.asset.transactions.filter(
            type="Buy",
            aci__lt=0,
            date__date__gte=query_coupon_start,
            date__date__lte=query_date,
            investor=investor,
        )

        if account_ids is not None:
            if isinstance(account_ids, int):
                account_ids = [account_ids]
            aci_paid_in_period = aci_paid_in_period.filter(account_id__in=account_ids)

        # Sum ACI paid (negative values)
        if aci_paid_in_period.exists():
            target_currency = currency or bond_meta.nominal_currency or bond_meta.asset.currency
            aci_paid_total = Decimal(0)

            for txn in aci_paid_in_period:
                # Convert date to ensure proper comparison
                txn_date = txn.date.date() if isinstance(txn.date, datetime) else txn.date
                fx_rate = fx_get_rate(txn.currency, target_currency, txn_date)["FX"]
                if fx_rate:
                    aci_paid_total += txn.aci * Decimal(fx_rate)

            # Add the negative ACI (subtract from total)
            total_aci += aci_paid_total

    return round(total_aci, 2)


# =============================================================================
# Bond YTM cash-flow helpers (moved from core.securities_utils)
# =============================================================================


def _get_first_buy_transaction(security, user, account_ids: list = None) -> Optional[Transactions]:
    """Get first buy transaction for a security."""
    query = security.transactions.filter(type="Buy", investor=user, quantity__isnull=False)
    if account_ids:
        query = query.filter(account_id__in=account_ids)
    return query.order_by("date").first()


def _get_acquisition_notional(
    first_buy: Transactions, bond_meta, user, target_currency: str
) -> Optional[Decimal]:
    """Get notional value for acquisition, from transaction or bond metadata."""
    if first_buy.notional is not None:
        return Decimal(first_buy.notional)

    # Fallback: get notional from bond metadata at purchase date
    notional = get_current_notional(
        bond_meta,
        first_buy.date,
        investor=user,
        currency=target_currency,
        account_ids=None,
    )
    if notional:
        logger.info(
            f"Using fallback notional for {bond_meta.asset.name}: {notional} "
            f"from bond metadata at {first_buy.date}"
        )
    return notional


def _get_redemption_notional(
    security, bond_meta, user, target_currency: str
) -> Optional[Decimal]:
    """Get redemption notional from NotionalHistory or fallback to metadata."""
    try:
        # Look for redemption entry at or after maturity date
        redemption_entry = (
            security.notional_history.filter(
                date__gte=bond_meta.maturity_date,
                change_reason__in=["MATURITY", "REDEMPTION"],
            )
            .order_by("date")
            .first()
        )

        if redemption_entry:
            return redemption_entry.notional_per_unit

        # Fallback: use current notional at maturity
        return get_current_notional(
            bond_meta,
            bond_meta.maturity_date,
            investor=user,
            currency=target_currency,
        )
    except Exception as e:
        logger.error(f"Error getting redemption notional: {e}")
        # Final fallback: use initial notional
        return bond_meta.initial_notional


def build_bond_cash_flows(
    security,
    bond_meta,
    first_buy: Transactions,
    user,
    notional_cache: dict = None,
) -> list:
    """
    Build cash flow list for bond YTM calculation using XIRR.

    Args:
        security: The bond asset
        bond_meta: BondMetadata for the security
        first_buy: First buy transaction
        user: The user object
        notional_cache: Optional dict to cache notional lookups

    Returns:
        List of (date, amount) tuples for XIRR calculation

    Raises:
        ValueError: If essential data is missing or FX conversion fails
    """
    if notional_cache is None:
        notional_cache = {}

    cash_flows = []
    target_currency = security.currency

    # Validate essential transaction fields
    if first_buy.quantity is None or first_buy.price is None:
        raise ValueError(
            f"Missing essential transaction data for {security.name} "
            f"(quantity={first_buy.quantity}, price={first_buy.price})"
        )

    first_buy_date = first_buy.date.date() if hasattr(first_buy.date, "date") else first_buy.date
    position_qty = Decimal(first_buy.quantity)

    # Get acquisition notional (use cache if available)
    cache_key = f"notional_{first_buy.date}"
    if cache_key in notional_cache:
        notional = notional_cache[cache_key]
    else:
        notional = _get_acquisition_notional(first_buy, bond_meta, user, target_currency)
        notional_cache[cache_key] = notional

    if notional is None:
        raise ValueError(f"Unable to determine notional value for {security.name}")

    # Calculate acquisition cash flow (negative - money out)
    amount = -position_qty * Decimal(first_buy.price) * Decimal(notional) / Decimal(100)

    # Add ACI (negative value = paid, adds to cost)
    if first_buy.aci is not None:
        amount += Decimal(first_buy.aci)

    # Add commission (negative value)
    if first_buy.commission is not None:
        amount += Decimal(first_buy.commission)

    # FX conversion for acquisition if needed
    if first_buy.currency != target_currency:
        fx_rate = fx_get_rate(first_buy.currency, target_currency, first_buy.date)["FX"]
        if not fx_rate:
            raise ValueError(
                f"No FX rate for {security.name} from {first_buy.currency} " f"to {target_currency}"
            )
        amount *= Decimal(fx_rate)

    cash_flows.append((first_buy_date, float(amount)))

    # Add coupon cash flows (positive - money in)
    if position_qty > 0:
        coupon_schedule = security.coupon_schedule.filter(payment_date__gt=first_buy_date).order_by(
            "payment_date"
        )

        for coupon in coupon_schedule:
            coupon_amt = Decimal(coupon.coupon_amount) if coupon.coupon_amount else Decimal(0)
            cf_amount = coupon_amt * position_qty

            # FX conversion for coupon if needed
            if coupon.coupon_currency != target_currency:
                fx_rate = fx_get_rate(coupon.coupon_currency, target_currency, coupon.payment_date)[
                    "FX"
                ]
                if fx_rate:
                    cf_amount *= Decimal(fx_rate)
                else:
                    logger.warning(
                        f"No FX rate for coupon of {security.name} from "
                        f"{coupon.coupon_currency} to {target_currency}, skipping"
                    )
                    continue

            cash_flows.append((coupon.payment_date, float(cf_amount)))

    # Add redemption cash flow at maturity (positive - money in)
    if bond_meta.maturity_date and position_qty > 0:
        redemption_notional = _get_redemption_notional(security, bond_meta, user, target_currency)

        if redemption_notional:
            redemption_amount = redemption_notional * position_qty

            # FX conversion for redemption if needed
            nominal_currency = bond_meta.nominal_currency or target_currency
            if nominal_currency != target_currency:
                fx_rate = fx_get_rate(nominal_currency, target_currency, bond_meta.maturity_date)[
                    "FX"
                ]
                if fx_rate:
                    redemption_amount *= Decimal(fx_rate)
                else:
                    logger.warning(
                        f"No FX rate for redemption of {security.name} from "
                        f"{nominal_currency} to {target_currency}, skipping redemption"
                    )
                    redemption_amount = None

            if redemption_amount is not None:
                cash_flows.append((bond_meta.maturity_date, float(redemption_amount)))

    return cash_flows


def calculate_bond_ytm(
    user, security, effective_date: date, account_ids: list = None
) -> Optional[Decimal]:
    """
    Calculate Yield to Maturity (YTM) for a bond using XIRR.

    Args:
        user: The user object
        security: The bond asset
        effective_date: Date for YTM calculation
        account_ids: Optional list of account IDs to filter transactions

    Returns:
        YTM as a Decimal (percentage) or None if calculation fails
    """
    if not security.is_bond or not security.bond_metadata:
        return None

    bond_meta = security.bond_metadata

    try:
        first_buy = _get_first_buy_transaction(security, user, account_ids)
        if not first_buy:
            logger.warning(f"No buy transaction found for {security.name}")
            return None

        # Build cash flows using helper
        cash_flows = build_bond_cash_flows(security, bond_meta, first_buy, user)

        # Calculate XIRR
        if len(cash_flows) > 1:
            ytm_decimal = xirr(cash_flows)
            if ytm_decimal is not None:
                ytm_percentage = Decimal(str(ytm_decimal)) * Decimal(100)
                logger.debug(f"YTM calculated for {security.name}: {ytm_percentage}%")
                return ytm_percentage

        logger.warning(f"Insufficient cash flows for YTM calculation of {security.name}")
        return None

    except ValueError as e:
        logger.warning(f"YTM calculation skipped for {security.name}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error calculating YTM for {security.name}: {e}")
        return None
