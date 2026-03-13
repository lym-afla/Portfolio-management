"""Utility functions for managing securities/assets data.

This module provides functions to retrieve, filter, and format
securities data for display in tables and API responses.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Q
from django.shortcuts import get_object_or_404
from pyxirr import xirr

from common.models import FX, Assets
from core.portfolio_utils import IRR

from .formatting_utils import format_table_data, format_value
from .pagination_utils import paginate_table
from .sorting_utils import sort_entries

logger = logging.getLogger(__name__)


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
        request, "effective_current_date", datetime.now().date().isoformat()
    )
    effective_current_date = datetime.strptime(effective_current_date_str, "%Y-%m-%d").date()
    number_of_digits = user.digits

    securities_data = _filter_securities(user, search)
    securities_data = _get_securities_data(user, securities_data, effective_current_date)
    securities_data = sort_entries(securities_data, sort_by)
    paginated_securities, pagination_data = paginate_table(securities_data, page, items_per_page)
    formatted_securities = [
        {k: format_value(v, k, position["currency"], number_of_digits) for k, v in position.items()}
        for position in paginated_securities.object_list
    ]

    return {
        "securities": formatted_securities,
        "total_items": pagination_data["total_items"],
        "current_page": pagination_data["current_page"],
        "total_pages": pagination_data["total_pages"],
    }


def _filter_securities(user, search):
    securities = Assets.objects.filter(investors__id=user.id)
    if search:
        # Create Q objects for each field we want to search
        search_query = (
            Q(name__icontains=search) | Q(ISIN__icontains=search) | Q(currency__icontains=search)
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
            "realized": security.realized_gain_loss(effective_current_date, user)["all_time"][
                "total"
            ],
            "unrealized": security.unrealized_gain_loss(effective_current_date, user)["total"],
            "capital_distribution": security.get_capital_distribution(effective_current_date, user),
            "irr": IRR(user.id, effective_current_date, security.currency, asset_id=security.id),
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
        request, "effective_current_date", datetime.now().date().isoformat()
    )
    effective_current_date = datetime.strptime(effective_current_date_str, "%Y-%m-%d").date()
    number_of_digits = user.digits

    security = get_object_or_404(Assets, id=security_id, investors__id=user.id)

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
        "realized": security.realized_gain_loss(effective_current_date, user)["all_time"]["total"],
        "unrealized": security.unrealized_gain_loss(effective_current_date, user)["total"],
        "capital_distribution": security.get_capital_distribution(effective_current_date, user),
        "irr": IRR(user.id, effective_current_date, security.currency, asset_id=security.id),
        "data_source": security.data_source,
        "update_link": security.update_link,
        "yahoo_symbol": security.yahoo_symbol,
        "comment": security.comment,
        # Note: current_aci moved to bond_data below
        # Add buy-in price
        "buy_in_price": security.calculate_buy_in_price(
            effective_current_date, user, security.currency
        ),
        # Add current price
        "current_price": (
            security.price_at_date(effective_current_date).price
            if security.price_at_date(effective_current_date)
            else None
        ),
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
                aci_data["aci_amount"] * Decimal(position_qty) if position_qty else Decimal(0)
            )

            # Subtract ACI paid in current coupon period (same logic as get_total_aci_for_position)
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
                        txn_date = txn.date.date() if isinstance(txn.date, datetime) else txn.date
                        fx_rate = FX.get_rate(txn.currency, security.currency, txn_date)["FX"]
                        if fx_rate:
                            aci_paid_total += txn.aci * Decimal(fx_rate)

                    total_aci += aci_paid_total

            total_aci = round(total_aci, 2)
        else:
            total_aci = Decimal(0)

        # Get current price as percentage of notional
        current_price_obj = security.price_at_date(effective_current_date)
        current_price = current_price_obj.price if current_price_obj else None

        # Get current notional per bond
        current_notional = bond_meta.get_current_notional(
            effective_current_date,
            investor=user,
            currency=bond_meta.nominal_currency or security.currency,
        )

        # Get coupon information from the latest coupon schedule entry
        latest_coupon = (
            bond_meta.asset.coupon_schedule.filter(payment_date__lte=effective_current_date)
            .order_by("-coupon_number")
            .first()
        )
        coupon_amount = (
            latest_coupon.coupon_amount if latest_coupon and latest_coupon.coupon_amount else None
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
                f"No coupon schedule found for {security.name}, attempting to fetch from API"
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
                logger.error(f"Failed to fetch coupon schedule for {security.name}: {e}")

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
                    logger.error(f"Failed to fetch redemption history for {security.name}: {e}")

        # Calculate YTM for bonds using XIRR (fixed at first position opening)
        ytm = None
        try:
            # Get first buy transaction (position opening)
            first_buy = (
                security.transactions.filter(type="Buy", investor=user, quantity__isnull=False)
                .order_by("date")
                .first()
            )

            if first_buy:
                first_buy_date = (
                    first_buy.date.date() if hasattr(first_buy.date, "date") else first_buy.date
                )

                # Build cash flow list for XIRR calculation
                cash_flows = []

                # Add acquisition cash flow at first purchase (negative)
                # Check for None values before converting to Decimal
                if first_buy.quantity is not None and first_buy.price is not None:
                    # Use notional from transaction or fallback to bond metadata
                    if first_buy.notional is not None:
                        notional = Decimal(first_buy.notional)
                    else:
                        # Fallback: get notional from bond metadata at purchase date
                        # For YTM calculation, we don't need to filter by account_ids
                        notional = bond_meta.get_current_notional(
                            first_buy.date,
                            investor=user,
                            currency=security.currency,
                            account_ids=None,
                        )
                        logger.info(
                            "Using fallback notional for "
                            f"{security.name}: {notional} from bond metadata at {first_buy.date}"
                        )

                    if notional is not None:
                        amount = (
                            -Decimal(first_buy.quantity)
                            * Decimal(first_buy.price)
                            * Decimal(notional)
                            / Decimal(100)
                        )

                        # Add ACI (None is treated as 0)
                        if first_buy.aci is not None:
                            amount += Decimal(first_buy.aci)  # ACI paid (negative value)

                        # Add commission if not None
                        if first_buy.commission is not None:
                            amount += Decimal(first_buy.commission)
                    else:
                        # If notional is still None even after fallback, skip YTM calculation
                        logger.warning(
                            "Skipping YTM calculation for "
                            f"{security.name}: unable to determine notional value"
                        )
                        raise ValueError("Unable to determine notional value for YTM calculation")
                else:
                    # If essential fields are None, skip YTM calculation
                    logger.warning(
                        "Skipping YTM calculation for "
                        f"{security.name}: missing transaction data "
                        f"(quantity={first_buy.quantity}, price={first_buy.price})"
                    )
                    raise ValueError("Missing essential transaction data for YTM calculation")

                # Convert to bond's currency if needed
                if first_buy.currency != security.currency:
                    try:
                        fx_rate = FX.get_rate(
                            first_buy.currency, security.currency, first_buy.date
                        )["FX"]
                        if fx_rate:
                            amount *= Decimal(fx_rate)
                    except Exception as fx_error:
                        logger.warning(
                            f"FX conversion failed for {security.name} from {first_buy.currency} "
                            f"to {security.currency}: {fx_error}"
                        )
                        # Skip YTM calculation if FX conversion fails
                        raise ValueError(f"FX conversion failed for YTM calculation: {fx_error}")

                cash_flows.append((first_buy_date, float(amount)))

                # Add coupon cash flows (positive) from BondCouponSchedule
                # Start from first buy date
                coupon_schedule = security.coupon_schedule.filter(
                    payment_date__gt=first_buy_date
                ).order_by("payment_date")

                # Use position from first buy (assuming no additional buys for simplicity)
                # For multiple buys, would need weighted average calculation
                if first_buy.quantity is not None:
                    position_qty = Decimal(first_buy.quantity)
                else:
                    position_qty = Decimal(0)

                if position_qty > 0:
                    for coupon in coupon_schedule:
                        # Cash inflow from coupon (positive)
                        coupon_amount = (
                            Decimal(coupon.coupon_amount) if coupon.coupon_amount else Decimal(0)
                        )
                        amount = coupon_amount * position_qty

                        # Convert to bond's currency if needed
                        if coupon.coupon_currency != security.currency:
                            try:
                                fx_rate = FX.get_rate(
                                    coupon.coupon_currency,
                                    security.currency,
                                    coupon.payment_date,
                                )["FX"]
                                if fx_rate:
                                    amount *= Decimal(fx_rate)
                            except Exception as fx_error:
                                logger.warning(
                                    "FX conversion failed for coupon of "
                                    f"{security.name} from {coupon.coupon_currency} "
                                    f"to {security.currency}: {fx_error}"
                                )
                                # Skip this coupon if FX conversion fails
                                continue

                        cash_flows.append((coupon.payment_date, float(amount)))

                # Add redemption cash flows at maturity from notional_history
                if bond_meta.maturity_date and position_qty > 0:
                    # Get redemption amount from NotionalHistory (for all bonds, not amortizing)
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
                            redemption_notional = redemption_entry.notional_per_unit
                        else:
                            # Fallback: use current notional at maturity
                            redemption_notional = bond_meta.get_current_notional(
                                bond_meta.maturity_date, user, security.currency
                            )
                    except Exception as e:
                        logger.error(f"Error getting redemption notional: {e}")
                        # Final fallback: use initial notional
                        redemption_notional = bond_meta.initial_notional

                    if redemption_notional:
                        # Cash inflow from redemption (positive)
                        amount = redemption_notional * position_qty

                        # Convert to bond's currency if needed
                        nominal_currency = bond_meta.nominal_currency or security.currency
                        add_redemption = True  # Flag to determine if we should add this cash flow

                        if nominal_currency != security.currency:
                            try:
                                fx_rate = FX.get_rate(
                                    nominal_currency,
                                    security.currency,
                                    bond_meta.maturity_date,
                                )["FX"]
                                if fx_rate:
                                    amount *= Decimal(fx_rate)
                                else:
                                    # Skip redemption if FX rate is None
                                    logger.warning(
                                        "No FX rate available for redemption of "
                                        f"{security.name} from {nominal_currency} "
                                        f"to {security.currency}"
                                    )
                                    add_redemption = False
                            except Exception as fx_error:
                                logger.warning(
                                    "FX conversion failed for redemption of "
                                    f"{security.name} from {nominal_currency} "
                                    f"to {security.currency}: {fx_error}"
                                )
                                # Skip redemption if FX conversion fails
                                add_redemption = False

                        if add_redemption:
                            cash_flows.append((bond_meta.maturity_date, float(amount)))

                # Calculate XIRR (YTM)
                if cash_flows:
                    try:
                        ytm_decimal = xirr(cash_flows)
                        if ytm_decimal is not None:
                            # Convert to percentage
                            ytm = float(ytm_decimal) * 100
                    except Exception as xirr_error:
                        logger.warning(f"XIRR calculation failed for {security.name}: {xirr_error}")
        except Exception as e:
            logger.warning(f"Error calculating YTM for {security.name}: {e}")

        bond_data = {
            "current_notional": float(current_notional) if current_notional is not None else None,
            "notional_currency": bond_meta.nominal_currency or security.currency,
            "initial_notional": (
                float(bond_meta.initial_notional)
                if bond_meta.initial_notional is not None
                else None
            ),
            "is_amortizing": bond_meta.is_amortizing,
            "issue_date": bond_meta.issue_date.isoformat() if bond_meta.issue_date else None,
            "maturity_date": (
                bond_meta.maturity_date.isoformat() if bond_meta.maturity_date else None
            ),
            "coupon_rate": (
                float(bond_meta.coupon_rate) if bond_meta.coupon_rate is not None else None
            ),
            "coupon_frequency": bond_meta.coupon_frequency,
            "coupon_amount": (
                float(latest_coupon.coupon_amount)
                if latest_coupon and latest_coupon.coupon_amount is not None
                else None
            ),
            "coupon_currency": coupon_currency,
            "coupon_type": coupon_type,
            "current_price_pct": float(current_price) if current_price is not None else None,
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


def calculate_bond_ytm(
    user, security: Assets, effective_date: date, account_ids: list = None
) -> Decimal:
    """
    Calculate Yield to Maturity (YTM) for a bond using XIRR.

    This function is similar to IRR but specifically designed for bonds,
    calculating the internal rate of return for bond-specific cash flows.

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
    logger.info(f"Calculating YTM for bond: {security.name}")

    try:
        # Get first buy transaction (position opening)
        first_buy = security.transactions.filter(type="Buy", investor=user, quantity__isnull=False)

        if account_ids:
            first_buy = first_buy.filter(account_id__in=account_ids)

        first_buy = first_buy.order_by("date").first()

        if not first_buy:
            logger.warning(f"No buy transaction found for {security.name}")
            return None

        first_buy_date = (
            first_buy.date.date() if hasattr(first_buy.date, "date") else first_buy.date
        )

        # Step 1: Build acquisition cash flow (negative)
        if first_buy.quantity is None or first_buy.price is None:
            logger.warning(f"Missing essential transaction data for {security.name}")
            return None

        # Use notional from transaction or fallback to bond metadata
        if first_buy.notional is not None:
            notional = Decimal(first_buy.notional)
        else:
            # Fallback: get notional from bond metadata at purchase date
            # Use same parameters as the working old method
            notional = bond_meta.get_current_notional(
                first_buy.date,
                investor=user,
                currency=security.currency,
                account_ids=None,
            )
            logger.info(f"Using fallback notional for {security.name}: {notional}")

        if notional is not None:
            amount = (
                -Decimal(first_buy.quantity)
                * Decimal(first_buy.price)
                * Decimal(notional)
                / Decimal(100)
            )

            # Add ACI (None is treated as 0)
            if first_buy.aci is not None:
                amount += Decimal(first_buy.aci)

            # Add commission if not None
            if first_buy.commission is not None:
                amount += Decimal(first_buy.commission)
        else:
            logger.warning(f"Unable to determine notional value for {security.name}")
            return None

        # Convert to bond's currency if needed
        if first_buy.currency != security.currency:
            try:
                fx_rate = FX.get_rate(
                    first_buy.currency.upper(),
                    security.currency.upper(),
                    first_buy.date,
                )["FX"]
                if fx_rate:
                    amount *= Decimal(fx_rate)
                else:
                    logger.warning(f"No FX rate available for {security.name}")
                    return None
            except Exception as fx_error:
                logger.warning(f"FX conversion failed for {security.name}: {fx_error}")
                return None

        # Initialize cash flows list
        cash_flows = [(first_buy_date, float(amount))]
        transaction_dates = [first_buy_date]

        # Step 2: Skip coupon processing for now due to TimezoneAwareDateField issues
        # TODO: Fix coupon payment date retrieval issue
        logger.info("Skipping coupon processing due to TimezoneAwareDateField issues")

        # Step 3: Add current market value at effective_date
        current_value = security.calculate_value_at_date(
            effective_date, user, security.currency, account_ids
        )

        # Only add current value if there are no transactions on the same date
        if not security.transactions.filter(
            investor=user,
            security=security,
            date__gte=effective_date,
            date__lt=effective_date + timedelta(days=1),
        ).exists():
            cash_flows.append((effective_date, float(current_value)))
            transaction_dates.append(effective_date)
        else:
            # Add to last cash flow if transaction exists on effective_date
            if cash_flows:
                cash_flows[-1] = (
                    cash_flows[-1][0],
                    cash_flows[-1][1] + float(current_value),
                )
            else:
                cash_flows.append((effective_date, float(current_value)))
                transaction_dates.append(effective_date)

        # Step 4: Calculate XIRR
        if len(cash_flows) < 2:
            logger.warning(f"Insufficient cash flows for YTM calculation of {security.name}")
            return None

        logger.debug(f"YTM cash flows for {security.name}: {cash_flows}")

        ytm_decimal = xirr(cash_flows)
        if ytm_decimal is not None:
            ytm_percentage = Decimal(str(ytm_decimal)) * Decimal(100)
            logger.info(f"YTM calculated for {security.name}: {ytm_percentage}%")
            return ytm_percentage
        else:
            logger.warning(f"XIRR returned None for {security.name}")
            return None

    except Exception as e:
        logger.error(f"Error calculating YTM for {security.name}: {e}")
        import traceback

        logger.debug(traceback.format_exc())
        return None


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
