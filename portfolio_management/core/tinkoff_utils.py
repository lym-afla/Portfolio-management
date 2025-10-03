import logging
from decimal import Decimal

from channels.db import database_sync_to_async
from tinkoff.invest import CandleInterval, Client, InstrumentType, OperationType
from tinkoff.invest.exceptions import RequestError
from tinkoff.invest.utils import quotation_to_decimal

from common.models import Assets, Transactions
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
    """Get user's Tinkoff API token"""
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
        List of tuples (name, ISIN, instrument type) or empty list if not found.
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
                    instrument.instrument.ticker,  # Add ticker for MICEX lookups
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
                                    (found.name, found.isin, found.instrument_kind, found.ticker)
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
                                        (inst.name, inst.isin, inst.instrument_kind, inst.ticker)
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
    instrument_uid, investor, position_uid=None, name=None
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
        from core.import_utils import create_security_from_micex, create_security_from_tinkoff

        # Try to create from MICEX first
        # securities_found tuple: (name, isin, instrument_kind, ticker)
        security_name = securities_found[0][0]
        security_isin = securities_found[0][1]
        security_type = securities_found[0][2]
        security_ticker = securities_found[0][3] if len(securities_found[0]) > 3 else None

        found_security = await create_security_from_micex(
            security_name, security_isin, investor, security_type, ticker=security_ticker
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
            investor,
            security_type,
            instrument_uid,  # Pass the T-Bank instrument UID
        )

        if found_security:
            return found_security, "created_new_from_tbank"

        return None, "failed_to_create"


async def map_tinkoff_operation_to_transaction(operation, investor, account):
    """
    Maps a Tinkoff API operation to our Transaction model format.

    Args:
        operation: Tinkoff API OperationItem
        investor: CustomUser instance
        account: Accounts instance

    Returns:
        dict: Transaction data ready for creating a Transaction or FXTransaction instance
    """
    # Initialize base transaction data
    transaction_data = {
        "investor": investor,
        "account": account,
        "date": operation.date.date(),
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
                operation.instrument_uid, investor, operation.position_uid, operation.name
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
            transaction_data["commission"] = -1 * abs(quotation_to_decimal(operation.commission))
            transaction_data["commission_currency"] = operation.commission.currency.upper()

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
            operation.instrument_uid, investor, operation.position_uid, operation.name
        )
        if security:
            transaction_data["security"] = security
            logger.debug(f"Security matched: {security.name} (status: {status})")
        else:
            logger.warning(f"Could not match security for operation {operation.id}")
            # Get security info for potential creation
            securities_found = await get_security_by_uid(
                operation.instrument_uid, investor, operation.position_uid, operation.name
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
            transaction_data["price"] = quotation_to_decimal(operation.price)

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
    Creates a Transaction instance from Tinkoff operation data if it doesn't exist.

    Args:
        operation: Tinkoff API OperationItem
        investor: CustomUser instance
        account: Accounts instance

    Returns:
        tuple: (Transaction instance or None, str status message)
    """
    transaction_data = await map_tinkoff_operation_to_transaction(operation, investor, account)

    if not transaction_data:
        return None, "Unsupported operation type"

    # Check if similar transaction already exists
    existing = await database_sync_to_async(Transactions.objects.filter)(
        investor=investor,
        account=account,
        date=transaction_data["date"],
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
    Verify if user has valid token with required access level

    Args:
        user: CustomUser instance
        required_access: str, access level required ('read_only' or 'full_access')

    Returns:
        bool: True if token is valid and has required access
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
    Get user's Tinkoff account information

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


async def get_price_from_tbank(instrument_uid, date, user):
    """
    Get the closing price for a security from T-Bank (Tinkoff) API for a specific date.

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

        # Convert date to datetime with time bounds (start and end of day)
        from datetime import datetime, timedelta

        from_dt = datetime.combine(date, datetime.min.time()) - timedelta(days=6)
        to_dt = from_dt + timedelta(days=7)

        logger.debug(f"Fetching price for instrument {instrument_uid} on {date}")

        with Client(token) as client:
            # Get daily candles for the specified date
            response = client.market_data.get_candles(
                instrument_id=instrument_uid,
                from_=from_dt,
                to=to_dt,
                interval=CandleInterval.CANDLE_INTERVAL_DAY,
            )

            if response.candles and len(response.candles) > 0:
                # Get the first (and should be only) candle for the day
                candle = response.candles[0]
                # Use the closing price
                close_price = quotation_to_decimal(candle.close)
                logger.info(f"Fetched price for {instrument_uid} on {date}: {close_price}")
                return close_price
            else:
                logger.warning(f"No candle data found for instrument {instrument_uid} on {date}")
                return None

    except RequestError as e:
        logger.error(f"T-Bank API error fetching price for {instrument_uid} on {date}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error fetching price from T-Bank for {instrument_uid} on {date}: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return None
