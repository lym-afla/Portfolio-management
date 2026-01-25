"""Utility functions for managing securities/assets data.

This module provides functions to retrieve, filter, and format
securities data for display in tables and API responses.
"""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from pyxirr import xirr

from common.models import FX, Assets, Transactions
from core.portfolio_utils import IRR

from .formatting_utils import format_table_data, format_value
from .pagination_utils import paginate_table
from .sorting_utils import sort_entries

logger = logging.getLogger(__name__)


# =============================================================================
# Bond YTM Calculation Helpers
# =============================================================================


def _get_first_buy_transaction(
    security: Assets, user, account_ids: list = None
) -> Optional[Transactions]:
    """Get first buy transaction for a security."""
    query = security.transactions.filter(
        type="Buy", investor=user, quantity__isnull=False
    )
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
    notional = bond_meta.get_current_notional(
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
    security: Assets, bond_meta, user, target_currency: str
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
        return bond_meta.get_current_notional(
            bond_meta.maturity_date, user, target_currency
        )
    except Exception as e:
        logger.error(f"Error getting redemption notional: {e}")
        # Final fallback: use initial notional
        return bond_meta.initial_notional


def _build_bond_cash_flows(
    security: Assets,
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

    first_buy_date = (
        first_buy.date.date() if hasattr(first_buy.date, "date") else first_buy.date
    )
    position_qty = Decimal(first_buy.quantity)

    # Get acquisition notional (use cache if available)
    cache_key = f"notional_{first_buy.date}"
    if cache_key in notional_cache:
        notional = notional_cache[cache_key]
    else:
        notional = _get_acquisition_notional(
            first_buy, bond_meta, user, target_currency
        )
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
        fx_rate = FX.get_rate(first_buy.currency, target_currency, first_buy.date)["FX"]
        if not fx_rate:
            raise ValueError(
                f"No FX rate for {security.name} from {first_buy.currency} "
                f"to {target_currency}"
            )
        amount *= Decimal(fx_rate)

    cash_flows.append((first_buy_date, float(amount)))

    # Add coupon cash flows (positive - money in)
    if position_qty > 0:
        coupon_schedule = security.coupon_schedule.filter(
            payment_date__gt=first_buy_date
        ).order_by("payment_date")

        for coupon in coupon_schedule:
            coupon_amt = (
                Decimal(coupon.coupon_amount) if coupon.coupon_amount else Decimal(0)
            )
            cf_amount = coupon_amt * position_qty

            # FX conversion for coupon if needed
            if coupon.coupon_currency != target_currency:
                fx_rate = FX.get_rate(
                    coupon.coupon_currency, target_currency, coupon.payment_date
                )["FX"]
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
        redemption_notional = _get_redemption_notional(
            security, bond_meta, user, target_currency
        )

        if redemption_notional:
            redemption_amount = redemption_notional * position_qty

            # FX conversion for redemption if needed
            nominal_currency = bond_meta.nominal_currency or target_currency
            if nominal_currency != target_currency:
                fx_rate = FX.get_rate(
                    nominal_currency, target_currency, bond_meta.maturity_date
                )["FX"]
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
    user, security: Assets, effective_date: date, account_ids: list = None
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
        cash_flows = _build_bond_cash_flows(security, bond_meta, first_buy, user)

        # Calculate XIRR
        if len(cash_flows) > 1:
            ytm_decimal = xirr(cash_flows)
            if ytm_decimal is not None:
                ytm_percentage = Decimal(str(ytm_decimal)) * Decimal(100)
                logger.debug(f"YTM calculated for {security.name}: {ytm_percentage}%")
                return ytm_percentage

        logger.warning(
            f"Insufficient cash flows for YTM calculation of {security.name}"
        )
        return None

    except ValueError as e:
        logger.warning(f"YTM calculation skipped for {security.name}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error calculating YTM for {security.name}: {e}")
        return None


# =============================================================================
# Securities API Functions
# =============================================================================


def get_securities_table_api(request):
    """Retrieve and format securities table data for API response.

    Args:
        request: The HTTP request object containing user context and parameters.

    Returns:
        dict: Dictionary containing formatted securities data, totals, and
            pagination information with keys: securities, totals, total_items,
            current_page, total_pages.
    """
    data = request.data
    page = int(data.get("page"))
    items_per_page = int(data.get("itemsPerPage"))
    search = data.get("search", "")
    sort_by = data.get("sortBy", {})

    user = request.user
    # Use JWT middleware instead of session
    effective_current_date_str = getattr(
        request, "effective_current_date", datetime.now(timezone.utc).date().isoformat()
    )
    effective_current_date = datetime.strptime(effective_current_date_str, "%Y-%m-%d")
    number_of_digits = user.digits

    securities_data = _filter_securities(user, search)
    securities_data = _get_securities_data(
        user, securities_data, effective_current_date
    )
    securities_data = sort_entries(securities_data, sort_by)
    paginated_securities, pagination_data = paginate_table(
        securities_data, page, items_per_page
    )
    formatted_securities = [
        {
            k: format_value(v, k, position["currency"], number_of_digits)
            for k, v in position.items()
        }
        for position in paginated_securities.object_list
    ]

    return {
        "securities": formatted_securities,
        "total_items": pagination_data["total_items"],
        "current_page": pagination_data["current_page"],
        "total_pages": pagination_data["total_pages"],
    }


def _filter_securities(user, search):
    """Filter securities with optimized query using prefetch_related."""
    securities = (
        Assets.objects.filter(investors__id=user.id)
        .select_related("bond_metadata")
        .prefetch_related(
            Prefetch(
                "transactions",
                queryset=Transactions.objects.filter(investor=user)
                .select_related("account")
                .order_by("date"),
            ),
            "prices",
            "coupon_schedule",
            "notional_history",
        )
    )

    if search:
        search_query = (
            Q(name__icontains=search)
            | Q(ISIN__icontains=search)
            | Q(currency__icontains=search)
        )
        securities = securities.filter(search_query)

    return securities


def _get_securities_data(user, securities, effective_current_date):
    securities_data = []
    for security in securities:
        security_data = {
            "id": security.id,
            "type": security.type,
            "ISIN": security.ISIN,
            "name": security.name,
            "first_investment": security.investment_date(user) or "None",
            "currency": security.currency,
            "open_position": security.position(effective_current_date, user),
            "current_value": security.calculate_value_at_date(
                effective_current_date, user, security.currency
            ),
            "realized": security.realized_gain_loss(effective_current_date, user)[
                "all_time"
            ]["total"],
            "unrealized": security.unrealized_gain_loss(effective_current_date, user)[
                "total"
            ],
            "capital_distribution": security.get_capital_distribution(
                effective_current_date, user
            ),
            "irr": IRR(
                user.id, effective_current_date, security.currency, asset_id=security.id
            ),
        }

        securities_data.append(security_data)
    return securities_data


def get_security_detail(request, security_id):
    """Retrieve detailed information for a specific security.

    Args:
        request: The HTTP request object.
        security_id: The ID of the security to retrieve details for.

    Returns:
        dict: Dictionary containing detailed security information.
    """
    user = request.user
    # Use JWT middleware instead of session
    effective_current_date_str = getattr(
        request, "effective_current_date", datetime.now(timezone.utc).date().isoformat()
    )
    effective_current_date = datetime.strptime(effective_current_date_str, "%Y-%m-%d")
    number_of_digits = user.digits

    security = get_object_or_404(Assets, id=security_id, investors__id=user.id)

    # Cache price lookup to avoid duplicate queries
    current_price_obj = security.price_at_date(effective_current_date)
    current_price = current_price_obj.price if current_price_obj else None

    # Base security data
    security_data = {
        "id": security.id,
        "instrument_type": security.type,
        "ISIN": security.ISIN,
        "name": security.name,
        "first_investment": security.investment_date(user) or "None",
        "currency": security.currency,
        "open_position": security.position(effective_current_date, user),
        "current_value": security.calculate_value_at_date(
            effective_current_date, user, security.currency
        ),
        "realized": security.realized_gain_loss(effective_current_date, user)[
            "all_time"
        ]["total"],
        "unrealized": security.unrealized_gain_loss(effective_current_date, user)[
            "total"
        ],
        "capital_distribution": security.get_capital_distribution(
            effective_current_date, user
        ),
        "irr": IRR(
            user.id, effective_current_date, security.currency, asset_id=security.id
        ),
        "data_source": security.data_source,
        "update_link": security.update_link,
        "yahoo_symbol": security.yahoo_symbol,
        "comment": security.comment,
        # Note: current_aci moved to bond_data below
        # Add buy-in price
        "buy_in_price": security.calculate_buy_in_price(
            effective_current_date, user, security.currency
        ),
        # Add current price (using cached value)
        "current_price": current_price,
    }

    # Add bond-specific data
    if security.is_bond and security.bond_metadata:
        bond_meta = security.bond_metadata

        # Get current ACI per bond (fetch once to avoid duplicate MICEX API calls)
        aci_data = bond_meta.get_current_aci(
            effective_current_date, currency=security.currency, user=user
        )

        # Calculate total ACI for position using the already-fetched aci_data
        # This avoids calling get_current_aci() twice and duplicating MICEX API calls
        if aci_data:
            position_qty = security.position(effective_current_date, user)
            total_aci = (
                aci_data["aci_amount"] * Decimal(position_qty)
                if position_qty
                else Decimal(0)
            )

            # Subtract ACI paid in current coupon period
            # (same logic as get_total_aci_for_position)
            current_coupon_start = aci_data.get("coupon_start")
            if current_coupon_start and position_qty:
                query_date = effective_current_date
                query_coupon_start = current_coupon_start

                aci_paid_in_period = security.transactions.filter(
                    type="Buy",
                    aci__lt=0,
                    date__gte=query_coupon_start,
                    date__lte=query_date,
                    investor=user,
                )

                if aci_paid_in_period.exists():
                    aci_paid_total = Decimal(0)
                    for txn in aci_paid_in_period:
                        # Convert date to ensure proper comparison
                        txn_date = (
                            txn.date.date()
                            if isinstance(txn.date, datetime)
                            else txn.date
                        )
                        fx_rate = FX.get_rate(
                            txn.currency, security.currency, txn_date
                        )["FX"]
                        if fx_rate:
                            aci_paid_total += txn.aci * Decimal(fx_rate)

                    total_aci += aci_paid_total

            total_aci = round(total_aci, 2)
        else:
            total_aci = Decimal(0)

        # current_price already cached above

        # Get current notional per bond
        current_notional = bond_meta.get_current_notional(
            effective_current_date,
            investor=user,
            currency=bond_meta.nominal_currency or security.currency,
        )

        # Get coupon information from the latest coupon schedule entry
        latest_coupon = (
            bond_meta.asset.coupon_schedule.filter(
                payment_date__lte=effective_current_date
            )
            .order_by("-coupon_number")
            .first()
        )
        coupon_amount = (
            latest_coupon.coupon_amount
            if latest_coupon and latest_coupon.coupon_amount
            else None
        )
        coupon_currency = (
            latest_coupon.coupon_currency
            if latest_coupon
            else (bond_meta.nominal_currency or security.currency)
        )
        coupon_type = latest_coupon.coupon_type if latest_coupon else None

        # Fallback: fetch coupon schedule if not available
        if not latest_coupon and security.tbank_instrument_uid:
            logger.info(
                f"No coupon schedule found for {security.name}, "
                f"attempting to fetch from API"
            )
            try:
                from asgiref.sync import async_to_sync

                from core.tinkoff_utils import fetch_and_cache_bond_coupon_schedule

                success = async_to_sync(fetch_and_cache_bond_coupon_schedule)(
                    security, user, force_refresh=False
                )

                if success:
                    # Try again after fetching
                    latest_coupon = (
                        bond_meta.asset.coupon_schedule.filter(
                            payment_date__lte=effective_current_date
                        )
                        .order_by("-coupon_number")
                        .first()
                    )
                    coupon_amount = (
                        latest_coupon.coupon_amount
                        if latest_coupon and latest_coupon.coupon_amount
                        else None
                    )
                    coupon_currency = (
                        latest_coupon.coupon_currency
                        if latest_coupon
                        else (bond_meta.nominal_currency or security.currency)
                    )
                    coupon_type = latest_coupon.coupon_type if latest_coupon else None
            except Exception as e:
                logger.error(
                    f"Failed to fetch coupon schedule for {security.name}: {e}"
                )

        # Fallback: fetch redemption history if not available for all bonds
        if security.tbank_instrument_uid:
            has_redemption_history = bond_meta.asset.notional_history.exists()
            if not has_redemption_history:
                logger.info(
                    f"No redemption history found for bond "
                    f"{security.name}, attempting to fetch from API"
                )
                try:
                    from asgiref.sync import async_to_sync

                    from core.tinkoff_utils import save_bond_redemption_history

                    entries_created = async_to_sync(save_bond_redemption_history)(
                        security, security.tbank_instrument_uid, user
                    )

                    if entries_created > 0:
                        logger.info(
                            f"Created {entries_created} redemption history entries for "
                            f"{security.name}"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to fetch redemption history for {security.name}: {e}"
                    )

        # Calculate YTM for bonds using XIRR (uses shared helper function)
        ytm_decimal = calculate_bond_ytm(user, security, effective_current_date)
        ytm = float(ytm_decimal) if ytm_decimal is not None else None

        bond_data = {
            "current_notional": (
                float(current_notional) if current_notional is not None else None
            ),
            "notional_currency": bond_meta.nominal_currency or security.currency,
            "initial_notional": (
                float(bond_meta.initial_notional)
                if bond_meta.initial_notional is not None
                else None
            ),
            "is_amortizing": bond_meta.is_amortizing,
            "issue_date": (
                bond_meta.issue_date.isoformat() if bond_meta.issue_date else None
            ),
            "maturity_date": (
                bond_meta.maturity_date.isoformat() if bond_meta.maturity_date else None
            ),
            "coupon_rate": (
                float(bond_meta.coupon_rate)
                if bond_meta.coupon_rate is not None
                else None
            ),
            "coupon_frequency": bond_meta.coupon_frequency,
            "coupon_amount": (
                float(latest_coupon.coupon_amount)
                if latest_coupon and latest_coupon.coupon_amount is not None
                else None
            ),
            "coupon_currency": coupon_currency,
            "coupon_type": coupon_type,
            "current_price_pct": (
                float(current_price) if current_price is not None else None
            ),
            "total_aci": float(total_aci) if total_aci is not None else None,
            "bond_type": bond_meta.bond_type,
            "credit_rating": bond_meta.credit_rating,
            # Move current_aci here and add next_coupon_date
            "current_aci": aci_data,
            "next_coupon_date": (
                aci_data.get("next_payment").isoformat()
                if aci_data and aci_data.get("next_payment")
                else None
            ),
            # Add YTM calculated with XIRR
            "ytm": float(ytm) if ytm is not None else None,
        }
        security_data["bond_data"] = bond_data

    # Apply formatting to main security data only (not bond_data)
    formatted_security_data = format_table_data(
        [security_data], security.currency, number_of_digits
    )[0]

    return formatted_security_data


def get_security_transactions(request, security_id):
    """Retrieve transactions for a specific security.

    Args:
        request: The HTTP request object.
        security_id: The ID of the security.

    Returns:
        dict: Dictionary containing transaction data for the security.
    """
    # Implement logic to fetch and return recent transactions data
    pass
