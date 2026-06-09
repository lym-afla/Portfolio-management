"""Utility functions for integrating with TBank Invest API.

This module provides functions to map Tinkoff operations to transactions,
manage API tokens, and handle Tinkoff-specific data formats.
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from channels.db import database_sync_to_async
from t_tech.invest import CandleInterval, Client, InstrumentType, OperationType
from t_tech.invest.exceptions import RequestError
from t_tech.invest.schemas import EventType, GetBondEventsRequest
from t_tech.invest.utils import quotation_to_decimal

from common.models import Assets, BondCouponSchedule, Transactions
from constants import (
    TRANSACTION_TYPE_ASSET_TRANSFER,
    TRANSACTION_TYPE_BOND_MATURITY,
    TRANSACTION_TYPE_BOND_REDEMPTION,
    TRANSACTION_TYPE_BROKER_COMMISSION,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_COUPON,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_REPO,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_TAX,
)
from users.models import TinkoffApiToken

logger = logging.getLogger(__name__)


async def get_user_token(user, sandbox_mode=False):
    """Get user's Tinkoff API token."""
    try:
        token = await database_sync_to_async(TinkoffApiToken.objects.get)(
            user=user, token_type="read_only", sandbox_mode=sandbox_mode, is_active=True
        )
        return token.get_token(user)
    except TinkoffApiToken.DoesNotExist:
        raise ValueError("No active Tinkoff API token found for user")
    except Exception as e:
        logger.error(f"Error getting Tinkoff token: {str(e)}")
        raise


async def get_bond_initial_notional(instrument_uid, user):
    """
    Fetch the initial notional value of a bond from T-Bank API.

    Args:
        instrument_uid: T-Bank instrument UID for the bond
        user: CustomUser instance (to get API token)

    Returns:
        Decimal: The initial notional value per bond, or None if not found.
    """
    try:
        token = await get_user_token(user)
        if not token:
            logger.error("No T-Bank API token found for user")
            return None

        with Client(token) as client:
            response = client.instruments.bond_by(id_type=3, id=instrument_uid)
            if response.instrument and response.instrument.initial_nominal:
                initial_notional = quotation_to_decimal(response.instrument.initial_nominal)
                logger.debug(f"Fetched initial notional for {instrument_uid}: {initial_notional}")
                return initial_notional
            else:
                logger.warning(f"No initial_nominal found in bond response for {instrument_uid}")
                return None

    except RequestError as e:
        logger.error(f"T-Bank API error fetching bond info for {instrument_uid}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error fetching initial notional for {instrument_uid}: {str(e)}")
        return None


async def get_bond_notional_at_date(instrument_uid, date, user, initial_notional):
    """
    Calculate the remaining notional value of a bond at a given date based on redemption history.

    Uses T-Bank's bond events API to fetch all MTY (maturity/redemption) events and calculates
    the remaining notional by subtracting all redemptions that occurred before or on the given date.

    Bond Event Structure:
    - event.value (Quotation): Percentage of par redeemed (e.g., 12.5% or 0.125)
    - event.pay_one_bond (MoneyValue): Actual cash paid per bond
    - event.event_date: Date of redemption
    - event.operation_type: 'OA' (partial amortization), 'CA' (call option), 'CM' (full maturity)

    Example:
        If a bond with 1000 initial notional had two redemptions:
        - 2022-08-19: 12.5% redeemed
        - 2022-11-18: 12.5% redeemed

        On 2022-12-01, remaining notional = 1000 * (1 - 0.125 - 0.125) = 750

    Args:
        instrument_uid: T-Bank instrument UID for the bond
        date: The date for which to calculate notional (datetime.date or datetime)
        user: CustomUser instance (to get API token)
        initial_notional: Initial par value of the bond

    Returns:
        Decimal: The remaining notional value per bond at the given date
    """
    try:
        token = await get_user_token(user)
        if not token:
            logger.error("No T-Bank API token found for user")
            return initial_notional

        # Convert date to datetime if needed
        if isinstance(date, datetime):
            target_date = date
        else:
            # Use timezone-aware datetime to avoid warnings
            from django.utils import timezone

            target_date = timezone.make_aware(datetime.combine(date, datetime.min.time()))

        logger.debug(
            f"Fetching bond events for instrument {instrument_uid} up to {target_date.date()}"
        )

        with Client(token) as client:
            # Fetch all MTY (maturity/redemption) events from inception to target date
            request = GetBondEventsRequest(
                from_=datetime(1980, 1, 1),
                to=target_date,
                instrument_id=instrument_uid,
                type=EventType.EVENT_TYPE_MTY,
            )

            response = client.instruments.get_bond_events(request)

            if not response.events:
                logger.debug(
                    f"No redemption events found for bond {instrument_uid}, using initial notional"
                )
                return initial_notional

            # Calculate total redeemed amount
            total_redeemed_percentage = Decimal(0)

            for event in response.events:
                if event.event_date.date() <= target_date.date():
                    # event.value is a Quotation representing percentage of par redeemed
                    redeemed_pct = quotation_to_decimal(event.value)
                    total_redeemed_percentage += redeemed_pct

                    logger.debug(
                        f"Redemption on {event.event_date.date()}: "
                        f"{redeemed_pct}% (pay_one_bond: {event.pay_one_bond.units})"
                    )

            # Calculate remaining notional
            remaining_percentage = Decimal(100) - total_redeemed_percentage

            remaining_notional = initial_notional * (remaining_percentage / Decimal(100))

            logger.info(
                f"Bond {instrument_uid} at {target_date.date()}: "
                f"redeemed {total_redeemed_percentage}%, "
                f"remaining notional: {remaining_notional} (from {initial_notional})"
            )

            return remaining_notional

    except RequestError as e:
        logger.error(f"T-Bank API error fetching bond events for {instrument_uid}: {str(e)}")
        return initial_notional
    except Exception as e:
        logger.error(f"Error calculating bond notional for {instrument_uid} at {date}: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return initial_notional


async def fetch_and_cache_bond_coupon_schedule(asset: Assets, user, force_refresh=False):
    """
    Fetch bond coupon schedule from T-Bank API and cache it in BondCouponSchedule model.

    For fixed-rate bonds, schedule is cached indefinitely as it doesn't change.
    Use force_refresh=True for floating-rate bonds or when coupon_amount is None.

    Args:
        asset: Assets instance (must be a bond with tbank_instrument_uid)
        user: CustomUser instance (to get API token)
        force_refresh: If True, delete existing schedule and fetch fresh data
                      (use when coupon_amount is empty for floating-rate bonds)

    Returns:
        bool: True if schedule was fetched and cached successfully, False otherwise
    """

    from channels.db import database_sync_to_async

    # Get asset data in sync context (cache frequently used fields)
    asset_name = await database_sync_to_async(lambda: asset.name)()
    is_bond = await database_sync_to_async(lambda: asset.is_bond)()

    if not is_bond:
        logger.warning(f"Asset {asset_name} is not a bond")
        return False

    # Check if asset has T-Bank instrument UID
    has_uid = await database_sync_to_async(lambda: asset.tbank_instrument_uid)()

    if not has_uid:
        # Try to get instrument UID from T-Bank API
        instrument_uid = await get_instrument_uid(asset, user)
        if instrument_uid:
            # Save the UID to the asset
            @database_sync_to_async
            def save_uid():
                asset.tbank_instrument_uid = instrument_uid
                asset.save()

            await save_uid()
            # Update has_uid flag since we just saved it
            has_uid = instrument_uid
        else:
            logger.warning(f"Bond {asset_name} has no T-Bank instrument UID")
            return False

    try:
        # Check if we already have a schedule
        # For fixed-rate bonds, schedule doesn't change so we cache indefinitely
        if not force_refresh:
            schedule_exists = await database_sync_to_async(
                lambda: BondCouponSchedule.objects.filter(asset=asset).exists()
            )()

            if schedule_exists:
                logger.debug(f"Coupon schedule exists for {asset_name}, skipping fetch")
                return True

        # Fetch from T-Bank API
        token = await get_user_token(user)
        if not token:
            logger.error("No T-Bank API token found for user")
            return False

        bond_meta = await database_sync_to_async(lambda: asset.bond_metadata)()
        if not bond_meta:
            logger.warning(f"No bond metadata for {asset_name}")
            return False

        # Determine date range (from issue_date or 1 year ago, to maturity or 5 years ahead)
        from_date = bond_meta.issue_date or (datetime.now().date() - timedelta(days=365))
        to_date = bond_meta.maturity_date or (datetime.now().date() + timedelta(days=365 * 5))

        logger.info(f"Fetching coupon schedule for {asset_name} from {from_date} to {to_date}")

        # Get instrument UID (either from earlier check or from freshly saved value)
        if not has_uid:
            has_uid = await database_sync_to_async(lambda: asset.tbank_instrument_uid)()

        with Client(token) as client:
            from django.utils import timezone

            response = client.instruments.get_bond_coupons(
                instrument_id=has_uid,
                from_=timezone.make_aware(datetime.combine(from_date, datetime.min.time())),
                to=timezone.make_aware(datetime.combine(to_date, datetime.max.time())),
            )

            if not response.events:
                logger.warning(f"No coupon events found for bond {asset_name}")
                return False

            # Delete existing schedule if refreshing
            if force_refresh:
                deleted_count = await database_sync_to_async(
                    lambda: BondCouponSchedule.objects.filter(asset=asset).delete()[0]
                )()
                logger.debug(f"Deleted {deleted_count} existing coupon schedule entries")

            # Cache the coupon schedule
            coupons_created = 0
            for coupon in response.events:
                coupon_amount = None
                coupon_currency = None
                if hasattr(coupon, "pay_one_bond") and coupon.pay_one_bond:
                    coupon_amount = quotation_to_decimal(coupon.pay_one_bond)
                    coupon_currency = coupon.pay_one_bond.currency

                # Convert coupon type enum to user-friendly string
                coupon_type_str = None
                if hasattr(coupon, "coupon_type"):
                    coupon_type_mapping = {
                        0: "Unspecified",
                        1: "Constant",
                        2: "Floating",
                        3: "Discount",
                        4: "Mortgage",
                        5: "Fixed",
                        6: "Variable",
                        7: "Other",
                    }
                    raw_type = coupon.coupon_type
                    try:
                        type_key = int(raw_type)
                    except (ValueError, TypeError):
                        # SDK may return enum strings like 'FIXED' — map directly
                        type_key = str(raw_type).upper()
                        coupon_type_str = type_key.title() if type_key else "Unknown"
                    if coupon_type_str is None:
                        coupon_type_str = coupon_type_mapping.get(type_key, "Unknown")

                # Create or update coupon schedule entry using database_sync_to_async
                await database_sync_to_async(BondCouponSchedule.objects.update_or_create)(
                    asset=asset,
                    coupon_number=coupon.coupon_number,
                    defaults={
                        "coupon_start_date": coupon.coupon_start_date.date(),
                        "coupon_end_date": coupon.coupon_end_date.date(),
                        "payment_date": coupon.coupon_date.date(),
                        "coupon_amount": coupon_amount,
                        "coupon_currency": coupon_currency,
                        "coupon_type": coupon_type_str,
                    },
                )
                coupons_created += 1

            logger.info(f"Successfully cached {coupons_created} coupon periods for {asset_name}")
            return True

    except RequestError as e:
        logger.error(f"T-Bank API error fetching coupon schedule for {asset_name}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error fetching coupon schedule for {asset_name}: {str(e)}", exc_info=True)
        return False


async def save_bond_redemption_history(security, instrument_uid, user, date_to_save=None):
    """
    Fetch and save all bond redemption history to NotionalHistory model.

    This function fetches all MTY (maturity/redemption) events for a bond from T-Bank API
    and creates NotionalHistory entries for each redemption event.

    Args:
        security: Assets instance (the bond)
        instrument_uid: T-Bank instrument UID for the bond
        date_to_save: The date until which to save redemption history
        user: CustomUser instance (to get API token)

    Returns:
        int: Number of NotionalHistory entries created
    """
    try:
        token = await get_user_token(user)
        if not token:
            logger.error("No T-Bank API token found for user")
            return 0

        # Get bond metadata to get initial notional
        bond_meta = await database_sync_to_async(lambda: security.bond_metadata)()
        if not bond_meta or not bond_meta.initial_notional:
            logger.warning(f"No bond metadata with initial_notional for {security.name}")
            return 0

        initial_notional = bond_meta.initial_notional

        with Client(token) as client:
            # Fetch all MTY events from inception to now
            request = GetBondEventsRequest(
                from_=datetime(1980, 1, 1),
                # to=date_to_save if date_to_save else datetime.now(),
                instrument_id=instrument_uid,
                type=EventType.EVENT_TYPE_MTY,
            )

            response = client.instruments.get_bond_events(request)

            if not response.events:
                logger.info(f"No redemption events found for bond {security.name}")
                return 0

            # Sort events by date
            sorted_events = sorted(response.events, key=lambda e: e.event_date)

            # Track cumulative notional changes
            current_notional = initial_notional
            entries_created = 0

            @database_sync_to_async
            def create_notional_history_entry(
                event_date, notional_per_unit, change_amount, operation_type
            ):
                from common.models import NotionalHistory

                # Determine change reason based on operation_type
                if operation_type in ["CM", "OM"]:
                    change_reason = "MATURITY"
                else:
                    change_reason = "REDEMPTION"

                _, created = NotionalHistory.objects.update_or_create(
                    asset=security,
                    date=event_date,
                    change_reason=change_reason,
                    defaults={
                        "notional_per_unit": notional_per_unit,
                        "change_amount": change_amount,
                        "comment": (
                            f"Auto-imported from T-Bank API (operation_type: {operation_type})",
                        ),
                    },
                )
                return created

            for event in sorted_events:
                # event.value is percentage redeemed
                redeemed_pct = quotation_to_decimal(event.value)

                # Calculate absolute change amount
                # redeemed_pct is already a percentage
                change_amount = -initial_notional * (redeemed_pct / Decimal(100))

                current_notional += change_amount

                # Create NotionalHistory entry
                created = await create_notional_history_entry(
                    event.event_date.date(),
                    current_notional,
                    change_amount,
                    event.operation_type,
                )

                if created:
                    entries_created += 1
                    logger.info(
                        f"Created NotionalHistory for {security.name} "
                        f"on {event.event_date.date()}: "
                        f"notional={current_notional}, change={change_amount}"
                    )

            logger.info(f"Saved {entries_created} NotionalHistory entries for {security.name}")
            return entries_created

    except RequestError as e:
        logger.error(f"T-Bank API error fetching bond events for {instrument_uid}: {str(e)}")
        return 0
    except Exception as e:
        logger.error(f"Error saving bond redemption history for {security.name}: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return 0


async def get_security_by_uid(instrument_uid, user, position_uid=None, name=None):
    """
    Get security details from Tinkoff API using instrument_uid.

    Falls back to find_instrument if get_instrument_by fails.

    Args:
        instrument_uid: Tinkoff instrument UID
        user: CustomUser instance
        position_uid: Optional position UID for fallback search
        name: Optional name for fallback search

    Returns:
        List of tuples (name, ISIN, instrument type, ticker) or empty list if not found.
    """
    token = await get_user_token(user)
    try:
        with Client(token) as client:
            instrument = client.instruments.get_instrument_by(
                id_type=3, id=instrument_uid
            )  # id_type=3 is uid
            return [
                (
                    instrument.instrument.name,
                    instrument.instrument.isin,
                    instrument.instrument.instrument_kind,
                    instrument.instrument.ticker,
                )
            ]
    except RequestError as e:
        error_message = str(e)
        if "40002" in error_message:
            logger.error("Insufficient privileges for Tinkoff API token")
            return []
        elif "40003" in error_message:
            logger.error("Invalid or expired Tinkoff API token")
            return []
        elif "50002" in error_message:
            logger.warning(f"Instrument not found by UID {instrument_uid}, trying fallback methods")

            # Try fallback with position_uid or name
            if position_uid or name:
                try:
                    with Client(token) as client:
                        # Try position_uid first as it's more specific
                        query = position_uid if position_uid else name
                        logger.info(f"Searching instrument with query: {query}")

                        result = client.instruments.find_instrument(query=query)

                        if result.instruments:
                            if len(result.instruments) == 1:
                                # Single match - use it
                                found = result.instruments[0]
                                logger.info(f"Found single match: {found.name} ({found.isin})")
                                return [
                                    (
                                        found.name,
                                        found.isin,
                                        found.instrument_kind,
                                        found.ticker,
                                    )
                                ]
                            else:
                                # Multiple matches - try to find exact match by position_uid
                                if position_uid:
                                    for inst in result.instruments:
                                        if inst.position_uid == position_uid:
                                            logger.info(
                                                f"Found match by position_uid: {inst.name} "
                                                f"({inst.isin})"
                                            )
                                            return [
                                                (
                                                    inst.name,
                                                    inst.isin,
                                                    inst.instrument_kind,
                                                    inst.ticker,
                                                )
                                            ]

                                # No exact match, return all found
                                logger.warning(
                                    f"Multiple instruments found ({len(result.instruments)})"
                                )
                                securities_found = []
                                for _, inst in enumerate(result.instruments):
                                    securities_found.append(
                                        (
                                            inst.name,
                                            inst.isin,
                                            inst.instrument_kind,
                                            inst.ticker,
                                        )
                                    )
                                return securities_found
                        else:
                            logger.error(f"No instruments found with query: {query}")
                            return []

                except Exception as fallback_error:
                    logger.error(f"Fallback search failed: {str(fallback_error)}")
                    return []
            else:
                logger.error("No position_uid or name provided for fallback search")
                return []
        else:
            logger.error(f"Tinkoff API error: {error_message}")
            return []
    except Exception as e:
        logger.error(f"Error getting security details from Tinkoff: {str(e)}")
        return []


async def _find_or_create_security(
    instrument_uid, investor, position_uid=None, name=None, date_to_save=None
) -> tuple[Assets | None, str]:
    """
    Find existing security or create new one using Tinkoff API data.

    Args:
        instrument_uid: Tinkoff instrument UID
        investor: CustomUser instance
        position_uid: Optional position UID for fallback search
        name: Optional security name for fallback search

    Returns:
        tuple: (Assets instance, str status)
    """
    # Get security details from Tinkoff
    securities_found = await get_security_by_uid(instrument_uid, investor, position_uid, name)
    if not securities_found or len(securities_found) == 0:
        return None, "Could not get security details from Tinkoff"

    # Try to find a security with all relationships; only go to except if none found
    found_security = None
    for sec in securities_found:
        try:
            found_security = await database_sync_to_async(Assets.objects.get)(
                ISIN=sec[1], investors=investor
            )
            return found_security, "existing_with_relationships"
        except Assets.DoesNotExist:
            continue
    # If none found, fall through to next except block

    # Try to find security without relationships
    for sec in securities_found:
        try:
            found_security = await database_sync_to_async(Assets.objects.get)(ISIN=sec[1])
            await database_sync_to_async(found_security.investors.add)(investor)
            return found_security, "existing_added_relationships"
        except Assets.DoesNotExist:
            continue

    if not found_security and len(securities_found) == 1:
        # Create new security using MICEX data - import function here to avoid circular imports
        from core.import_utils import (
            create_security_from_micex,
            create_security_from_tinkoff,
        )

        # Try to create from MICEX first
        # securities_found tuple: (name, isin, instrument_kind, ticker)
        security_name = securities_found[0][0]
        security_isin = securities_found[0][1]
        security_type = securities_found[0][2]
        security_ticker = securities_found[0][3] if len(securities_found[0]) > 3 else None

        found_security = await create_security_from_micex(
            security_name,
            security_isin,
            investor,
            security_type,
            ticker=security_ticker,
            date_to_save=date_to_save,
        )

        if found_security:
            return found_security, "created_new_from_micex"

        # Fallback to T-Bank data if MICEX fails (e.g., matured bonds, delisted securities)
        logger.warning(
            f"MICEX creation failed for {security_name} ({security_isin}), "
            f"falling back to T-Bank data"
        )
        found_security = await create_security_from_tinkoff(
            security_name,
            security_isin,
            security_ticker,
            investor,
            security_type,
            instrument_uid,  # Pass the T-Bank instrument UID
            date_to_save=date_to_save,
        )

        if found_security:
            return found_security, "created_new_from_tbank"

        return None, "failed_to_create"


async def map_tinkoff_operation_to_transaction(operation, investor, account):
    """
    Map a Tinkoff API operation to our Transaction model format.

    Args:
        operation: Tinkoff API OperationItem
        investor: CustomUser instance
        account: Accounts instance

    Returns:
        dict: Transaction data ready for creating a Transaction or FXTransaction instance.
    """
    # Initialize base transaction data
    transaction_data = {
        "investor": investor,
        "account": account,
        "date": operation.date,  # Keep full datetime from T-Bank API
        "comment": operation.description,
    }

    # Check if this is an FX transaction
    is_fx_transaction = (
        operation.instrument_kind == InstrumentType.INSTRUMENT_TYPE_CURRENCY
        and operation.type in [OperationType.OPERATION_TYPE_BUY, OperationType.OPERATION_TYPE_SELL]
    )

    logger.debug(f"==== Processing operation ID: {operation.id} ====")
    logger.debug(f"  Instrument kind: {operation.instrument_kind}")
    logger.debug(
        f"  Is currency: {operation.instrument_kind == InstrumentType.INSTRUMENT_TYPE_CURRENCY}"
    )
    logger.debug(f"  Operation type: {operation.type}")
    logger.debug(
        "  Is buy/sell: "
        f"{operation.type in [OperationType.OPERATION_TYPE_BUY, OperationType.OPERATION_TYPE_SELL]}"
    )
    logger.debug(f"  >> IS FX TRANSACTION: {is_fx_transaction} <<")

    if is_fx_transaction:
        # This is an FX transaction
        transaction_data["is_fx"] = True

        # Extract currency being traded from operation name or instrument_uid
        # The 'name' field contains the currency name (e.g., "Доллар США" for USD)
        currency_map = {
            "Доллар США": "USD",
            "Евро": "EUR",
            "Фунт стерлингов": "GBP",
            "Швейцарский франк": "CHF",
            "Юань": "CNY",
        }

        to_currency = None
        # Try to extract from name
        for key, value in currency_map.items():
            if key in operation.name:
                to_currency = value
                break

        # Fallback: try to get from instrument details
        if not to_currency and operation.instrument_uid:
            securities_found = await get_security_by_uid(
                operation.instrument_uid,
                investor,
                operation.position_uid,
                operation.name,
            )
            if len(securities_found) == 1:
                name = securities_found[0][0]
                for key, value in currency_map.items():
                    if name and key in name:
                        to_currency = value
                        break

        # Determine from_currency and to_currency based on operation type
        if operation.type == OperationType.OPERATION_TYPE_BUY:
            # Buying foreign currency, paying with account currency
            transaction_data["from_currency"] = operation.payment.currency.upper()
            transaction_data["to_currency"] = to_currency or "USD"  # Default to USD if unknown
            transaction_data["from_amount"] = abs(quotation_to_decimal(operation.payment))
            transaction_data["to_amount"] = Decimal(str(operation.quantity))
        else:  # SELL
            # Selling foreign currency, receiving account currency
            transaction_data["from_currency"] = to_currency or "USD"
            transaction_data["to_currency"] = operation.payment.currency.upper()
            transaction_data["from_amount"] = Decimal(str(operation.quantity))
            transaction_data["to_amount"] = abs(quotation_to_decimal(operation.payment))

        # Calculate exchange rate
        if transaction_data.get("from_amount") and transaction_data.get("to_amount"):
            transaction_data["exchange_rate"] = (
                transaction_data["from_amount"] / transaction_data["to_amount"]
            )

        # Handle commission
        if operation.commission and operation.commission.units != 0:
            transaction_data["commission"] = -1 * abs(
                quotation_to_decimal(operation.commission)
            )
            transaction_data["commission_currency"] = (
                operation.commission.currency.upper()
            )

        logger.debug(
            f"✓ FX transaction created: {transaction_data['from_currency']} "
            f"-> {transaction_data['to_currency']}, "
            f"Rate: {transaction_data.get('exchange_rate', 'N/A')}"
        )

        return transaction_data

    # Regular (non-FX) transaction handling
    # Map operation type
    operation_type_mapping = {
        OperationType.OPERATION_TYPE_BUY: TRANSACTION_TYPE_BUY,
        OperationType.OPERATION_TYPE_SELL: TRANSACTION_TYPE_SELL,
        OperationType.OPERATION_TYPE_DIVIDEND: TRANSACTION_TYPE_DIVIDEND,
        OperationType.OPERATION_TYPE_DIVIDEND_TAX: TRANSACTION_TYPE_TAX,
        OperationType.OPERATION_TYPE_OVERNIGHT: TRANSACTION_TYPE_REPO,
        OperationType.OPERATION_TYPE_COUPON: TRANSACTION_TYPE_COUPON,
        OperationType.OPERATION_TYPE_TAX_CORRECTION: TRANSACTION_TYPE_TAX,
        OperationType.OPERATION_TYPE_TAX: TRANSACTION_TYPE_TAX,
        OperationType.OPERATION_TYPE_OUTPUT: TRANSACTION_TYPE_CASH_OUT,
        OperationType.OPERATION_TYPE_INPUT: TRANSACTION_TYPE_CASH_IN,
        OperationType.OPERATION_TYPE_SERVICE_FEE: TRANSACTION_TYPE_BROKER_COMMISSION,
        OperationType.OPERATION_TYPE_BOND_TAX: TRANSACTION_TYPE_TAX,
        OperationType.OPERATION_TYPE_BENEFIT_TAX: TRANSACTION_TYPE_TAX,
        OperationType.OPERATION_TYPE_INPUT_SECURITIES: TRANSACTION_TYPE_ASSET_TRANSFER,
        OperationType.OPERATION_TYPE_OUTPUT_SECURITIES: TRANSACTION_TYPE_ASSET_TRANSFER,
        OperationType.OPERATION_TYPE_BOND_REPAYMENT: TRANSACTION_TYPE_BOND_REDEMPTION,
        OperationType.OPERATION_TYPE_BOND_REPAYMENT_FULL: TRANSACTION_TYPE_BOND_MATURITY,
    }

    if operation.type == OperationType.OPERATION_TYPE_BROKER_FEE:
        return "Separate entry for transaction broker fee"

    # Check if this is an asset transfer operation (before type mapping)
    is_asset_transfer = operation.type in [
        OperationType.OPERATION_TYPE_INPUT_SECURITIES,
        OperationType.OPERATION_TYPE_OUTPUT_SECURITIES,
    ]

    transaction_data["type"] = operation_type_mapping.get(operation.type)
    if not transaction_data["type"]:
        return None  # Skip unsupported operation types

    if is_asset_transfer:
        transaction_data["is_asset_transfer"] = True
        logger.debug(f"Detected asset transfer operation: {operation.type}")

    # Handle currency
    if operation.payment and operation.payment.currency:
        transaction_data["currency"] = operation.payment.currency.upper()

    # Handle security matching
    if operation.instrument_uid:
        security, status = await _find_or_create_security(
            operation.instrument_uid,
            investor,
            operation.position_uid,
            operation.name,
            date_to_save=operation.date.date(),
        )
        if security:
            transaction_data["security"] = security
            logger.debug(f"Security matched: {security.name} (status: {status})")
        else:
            logger.warning(f"Could not match security for operation {operation.id}")
            # Get security info for potential creation
            securities_found = await get_security_by_uid(
                operation.instrument_uid,
                investor,
                operation.position_uid,
                operation.name,
            )
            if len(securities_found) == 1:
                name = securities_found[0][0]
                isin = securities_found[0][1]
                instrument_type = securities_found[0][2]

                # Mark this transaction as needing security mapping
                transaction_data["needs_security_mapping"] = True
                if name and isin:
                    transaction_data["security_description"] = name
                    transaction_data["isin"] = isin
                    transaction_data["instrument_type"] = instrument_type
                else:
                    transaction_data["security_description"] = operation.name
                    transaction_data["instrument_type"] = operation.instrument_type
                transaction_data["security"] = None
            else:
                raise ValueError(f"Multiple securities found for operation {operation.id}")

    # Handle bond redemption operations
    if operation.type in [
        OperationType.OPERATION_TYPE_BOND_REPAYMENT,
        OperationType.OPERATION_TYPE_BOND_REPAYMENT_FULL,
    ]:
        # Note: T-Bank API returns quantity=0 for bond redemptions
        # The actual redemption information is in the payment field
        # We don't change quantity for amortizing bonds - the notional changes instead

        # Payment represents the cash received from redemption
        if operation.payment:
            cash_received = quotation_to_decimal(operation.payment)
            transaction_data["cash_flow"] = cash_received

            # For bond redemptions, we need to infer the notional change
            # The payment is typically: number_of_bonds * notional_redeemed_per_bond
            # Since we don't have the quantity, we'll store the total cash as notional_change
            # This will need to be adjusted manually or via bond metadata
            transaction_data["notional_change"] = cash_received

        # Set quantity to None since T-Bank doesn't provide it
        # The bond position doesn't change in terms of number of bonds held
        transaction_data["quantity"] = None

        # Price isn't meaningful for amortizing redemptions
        # It's the notional being returned, not a market transaction
        transaction_data["price"] = None

        logger.debug(
            f"Bond redemption: cash_flow={transaction_data.get('cash_flow')}, "
            f"notional_change={transaction_data.get('notional_change')}"
        )

    # Handle quantity and price for buy/sell operations (including asset transfers)
    elif operation.type in [
        OperationType.OPERATION_TYPE_BUY,
        OperationType.OPERATION_TYPE_SELL,
        OperationType.OPERATION_TYPE_INPUT_SECURITIES,
        OperationType.OPERATION_TYPE_OUTPUT_SECURITIES,
    ]:
        # For regular buy/sell, use the operation price
        # For asset transfers, price might be 0, will be set later to buy-in/market price
        if operation.price:
            actual_price = quotation_to_decimal(operation.price)

            # For bonds, convert price to percentage of par
            # Use bond events API to determine notional based on redemption history
            if security and security.type == "Bond":
                try:
                    # Get initial notional from T-Bank API
                    initial_notional = await get_bond_initial_notional(
                        operation.instrument_uid, investor
                    )

                    if not initial_notional:
                        # Fallback to bond metadata
                        bond_meta = await database_sync_to_async(lambda: security.bond_metadata)()
                        if bond_meta and bond_meta.initial_notional:
                            initial_notional = bond_meta.initial_notional
                        else:
                            logger.warning(
                                f"Could not determine initial notional for bond {security.name}, "
                                f"storing actual price: {actual_price}"
                            )
                            transaction_data["price"] = actual_price
                            raise ValueError("No initial notional available")

                    # Calculate notional at transaction date based on redemption history
                    notional = await get_bond_notional_at_date(
                        operation.instrument_uid,
                        operation.date.date(),
                        investor,
                        initial_notional,
                    )

                    if notional and notional > 0:
                        # Convert actual price to percentage: (actual_price / notional) * 100
                        price_percentage = (actual_price / notional) * Decimal(100)

                        transaction_data["price"] = price_percentage
                        transaction_data["notional"] = notional
                        logger.info(
                            f"Bond transaction: actual_price={actual_price}, "
                            f"notional={notional}, percentage={price_percentage:.2f}%"
                        )
                    else:
                        logger.warning(
                            f"Could not determine notional for bond {security.name}, "
                            f"storing actual price: {actual_price}"
                        )
                        transaction_data["price"] = actual_price
                except Exception as e:
                    logger.error(
                        f"Error converting bond price to percentage: {e}. "
                        f"Using actual price: {actual_price}"
                    )
                    transaction_data["price"] = actual_price
            else:
                # For non-bonds, use actual price as-is
                transaction_data["price"] = actual_price

        aci = operation.accrued_int

        if operation.type in [
            OperationType.OPERATION_TYPE_BUY,
            OperationType.OPERATION_TYPE_INPUT_SECURITIES,
        ]:
            transaction_data["quantity"] = Decimal(str(operation.quantity))
            if quotation_to_decimal(aci) != 0:
                transaction_data["aci"] = -1 * abs(quotation_to_decimal(aci))
        else:  # SELL or OUTPUT_SECURITIES
            transaction_data["quantity"] = -1 * Decimal(str(operation.quantity))
            if quotation_to_decimal(aci) != 0:
                transaction_data["aci"] = abs(quotation_to_decimal(aci))
            if is_asset_transfer:
                transaction_data["needs_price_calculation"] = True

    else:
        # Handle payment/cash flow
        if operation.payment:
            payment = quotation_to_decimal(operation.payment)
            transaction_data["cash_flow"] = payment

    # Handle commission
    if operation.commission and operation.commission.units != 0:
        transaction_data["commission"] = -1 * abs(quotation_to_decimal(operation.commission))

    return transaction_data


async def create_transaction_from_tinkoff(operation, investor, account):
    """
    Create a Transaction instance from Tinkoff operation data if it doesn't exist.

    Args:
        operation: Tinkoff API OperationItem
        investor: CustomUser instance
        account: Accounts instance

    Returns:
        tuple: (Transaction instance or None, str status message).
    """
    transaction_data = await map_tinkoff_operation_to_transaction(operation, investor, account)

    if not transaction_data:
        return None, "Unsupported operation type"

    # Check if similar transaction already exists
    # All dates are now naive datetime objects for consistent comparison

    transaction_date = transaction_data["date"]

    # Ensure the transaction date is naive (strip timezone if present)
    if hasattr(transaction_date, "tzinfo") and transaction_date.tzinfo is not None:
        transaction_date = transaction_date.replace(tzinfo=None)

    # Check for existing transactions within a reasonable time window (1 minute)
    # to handle potential timestamp differences

    time_window = timedelta(minutes=1)

    existing = await database_sync_to_async(Transactions.objects.filter)(
        investor=investor,
        account=account,
        date__date__gte=transaction_date - time_window,
        date__date__lte=transaction_date + time_window,
        type=transaction_data["type"],
        quantity=transaction_data.get("quantity"),
        price=transaction_data.get("price"),
        cash_flow=transaction_data.get("cash_flow"),
    ).first()

    if existing:
        logger.debug(f"Transaction already exists: {existing}")
        return None, "Transaction already exists"

    # Create new transaction
    try:
        transaction = await database_sync_to_async(Transactions.objects.create)(**transaction_data)
        logger.info(f"Transaction created successfully: {transaction}")
        return transaction, "Transaction created successfully"
    except Exception as e:
        return None, f"Error creating transaction: {str(e)}"


# New utility functions for token management
async def verify_token_access(user, required_access="read_only"):
    """
    Verify if user has valid token with required access level.

    Args:
        user: CustomUser instance
        required_access: str, access level required ('read_only' or 'full_access')

    Returns:
        bool: True if token is valid and has required access.
    """
    try:
        token = await get_user_token(user)
        with Client(token):
            return True
    except Exception as e:
        logger.error(f"Token verification failed: {str(e)}")
        return False


async def get_account_info(user):
    """
    Get user's Tinkoff account information.

    Args:
        user: CustomUser instance

    Returns:
        dict: Account information or None if failed
    """
    try:
        token = await get_user_token(user)
        with Client(token) as client:
            accounts = client.users.get_accounts()
            return {
                "accounts": [
                    {
                        "id": acc.id,
                        "type": acc.type.name,
                        "name": acc.name,
                        "status": acc.status.name,
                    }
                    for acc in accounts.accounts
                ]
            }
    except Exception as e:
        logger.error(f"Failed to get account info: {str(e)}")
        return None


async def get_price_from_tbank(instrument_uid: str, date: datetime.date, user):
    """
    Get the closing price for a security from T-Bank (Tinkoff) API for a specific date.

    Optimized to fetch minimal data: starts with 1 day, expands only if needed.

    Args:
        instrument_uid: T-Bank instrument UID
        date: datetime.date object for which to fetch the price
        user: CustomUser instance (to get API token)

    Returns:
        Decimal: The closing price, or None if not found
    """

    try:
        token = await get_user_token(user)
        if not token:
            logger.error("No T-Bank API token found for user")
            return None

        logger.debug(f"Fetching price for instrument {instrument_uid} on {date}")

        # Convert target date to timezone-aware datetime (UTC)
        target_dt = datetime.combine(date, datetime.min.time(), tzinfo=timezone.utc)

        # Try progressively larger date ranges: 1 day, 7 days, 14 days
        lookback_days = [1, 7, 14]

        with Client(token) as client:
            from django.utils import timezone

            for days_back in lookback_days:
                # Convert naive dates to timezone-aware for API call
                # Tinkoff API expects timezone-aware datetime objects
                from_dt = date - timedelta(days=days_back)
                to_dt = date

                from_dt = datetime.combine(
                    from_dt, datetime.min.time(), tzinfo=timezone.utc
                )
                to_dt = datetime.combine(
                    to_dt, datetime.max.time(), tzinfo=timezone.utc
                )

                logger.debug(
                    f"Attempt with {days_back} day(s) lookback: "
                    f"from {from_dt} to {to_dt}"
                )

                try:
                    response = client.market_data.get_candles(
                        instrument_id=instrument_uid,
                        from_=from_dt,
                        to=to_dt,
                        interval=CandleInterval.CANDLE_INTERVAL_DAY,
                    )

                    if response.candles and len(response.candles) > 0:
                        # Find exact match first, then most recent before target date
                        selected_candle = None
                        exact_match = None

                        for candle in response.candles:
                            candle_date = candle.time.date()

                            # Check for exact date match
                            if candle_date == date:
                                exact_match = candle
                                break

                            # Track the most recent candle before or on target date
                            if candle.time <= to_dt:
                                if (
                                    selected_candle is None
                                    or candle.time > selected_candle.time
                                ):
                                    selected_candle = candle

                        # Prefer exact match, fall back to most recent
                        final_candle = exact_match if exact_match else selected_candle

                        if final_candle:
                            close_price = quotation_to_decimal(final_candle.close)
                            logger.info(
                                f"Fetched price for {instrument_uid} on "
                                f"{final_candle.time.date()}: {close_price} "
                                f"(requested: {date}, {'exact' if exact_match else 'closest'})"
                            )
                            return close_price

                    # If we got a response but no suitable candles, try next range
                    logger.debug(
                        f"No suitable candle in {days_back}-day range, " f"trying larger range..."
                    )

                except RequestError as e:
                    # API error on this attempt, try next range
                    logger.warning(
                        f"API error with {days_back}-day lookback: {str(e)}, "
                        f"trying larger range..."
                    )
                    continue

            # Exhausted all attempts
            logger.warning(
                f"No candle data found for instrument {instrument_uid} "
                f"on or before {date} (tried up to {max(lookback_days)} days back)"
            )
            return None

    except RequestError as e:
        logger.error(f"T-Bank API error fetching price for {instrument_uid} on {date}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error fetching price from T-Bank for {instrument_uid} on {date}: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return None


async def get_instrument_uid(asset: Assets, user):
    """Get instrument UID from T-Bank API.

    Args:
        asset: Assets instance
        user: CustomUser instance

    Returns:
        str: Instrument UID or None if not found
    """
    from channels.db import database_sync_to_async

    token = await get_user_token(user)
    if not token:
        logger.error("No T-Bank API token found for user")
        return None

    # Get asset data in sync context
    asset_isin = await database_sync_to_async(lambda: asset.ISIN)()
    asset_type = await database_sync_to_async(lambda: asset.type)()

    with Client(token) as client:
        instruments = client.instruments.find_instrument(query=asset_isin).instruments

        if asset_type == "Bond":
            return instruments[0].uid if instruments else None
        elif asset_type == "ETF":
            for instrument in instruments:
                if instrument.class_code == "TQTF":
                    return instrument.uid
        elif asset_type == "Share":
            for instrument in instruments:
                if instrument.class_code == "TQBR":
                    return instrument.uid

        return None
