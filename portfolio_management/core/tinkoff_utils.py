import logging
from decimal import Decimal

from channels.db import database_sync_to_async
from tinkoff.invest import Client, InstrumentType, OperationType
from tinkoff.invest.exceptions import RequestError
from tinkoff.invest.utils import quotation_to_decimal

from common.models import Assets, Transactions
from constants import (
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_COUPON,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_REPO,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_TAX,
)

# Remove circular import
# from core.import_utils import create_security_from_micex
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


async def get_security_by_uid(instrument_uid, user):
    """
    Get security details from Tinkoff API using instrument_uid.
    Returns (name, ISIN, instrument type) or (None, None, None) if not found.
    """
    try:
        token = await get_user_token(user)
        with Client(token) as client:
            instrument = client.instruments.get_instrument_by(
                id_type=3, id=instrument_uid
            )  # id_type=3 is uid
            return (
                instrument.instrument.name,
                instrument.instrument.isin,
                instrument.instrument.instrument_kind,
            )
    except RequestError as e:
        error_message = str(e)
        if "40002" in error_message:
            logger.error("Insufficient privileges for Tinkoff API token")
        elif "40003" in error_message:
            logger.error("Invalid or expired Tinkoff API token")
        else:
            logger.error(f"Tinkoff API error: {error_message}")
        return None, None, None
    except Exception as e:
        logger.error(f"Error getting security details from Tinkoff: {str(e)}")
        return None, None, None


async def _find_or_create_security(instrument_uid, investor):
    """
    Find existing security or create new one using Tinkoff API data.

    Args:
        instrument_uid: Tinkoff instrument UID
        investor: CustomUser instance
        account: Accounts instance

    Returns:
        tuple: (Assets instance, str status)
    """
    # Get security details from Tinkoff
    name, isin, instrument_type = await get_security_by_uid(instrument_uid, investor)
    if not isin:
        return None, "Could not get security details from Tinkoff"

    try:
        # Try to find security with all relationships
        security = await database_sync_to_async(Assets.objects.get)(ISIN=isin, investors=investor)
        return security, "existing_with_relationships"
    except Assets.DoesNotExist:
        try:
            # Try to find security without relationships
            security = await database_sync_to_async(Assets.objects.get)(ISIN=isin)

            # Add relationships
            @database_sync_to_async
            def add_relationships(security, investor):
                security.investors.add(investor)
                return security

            security = await add_relationships(security, investor)
            return security, "existing_added_relationships"
        except Assets.DoesNotExist:
            # Create new security using MICEX data - import function here to avoid circular imports
            from core.import_utils import create_security_from_micex

            security = await create_security_from_micex(name, isin, investor, instrument_type)
            if security:
                return security, "created_new"
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

    logger.debug(f"==== ==== ==== ==== Operation: {operation}")
    logger.debug(operation.instrument_kind == InstrumentType.INSTRUMENT_TYPE_CURRENCY)
    logger.debug(
        operation.type in [OperationType.OPERATION_TYPE_BUY, OperationType.OPERATION_TYPE_SELL]
    )
    logger.debug(f"==== ==== ==== ==== is_fx_transaction: {is_fx_transaction}")

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
            name, isin, instrument_type = await get_security_by_uid(
                operation.instrument_uid, investor
            )
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
            transaction_data["commission"] = abs(quotation_to_decimal(operation.commission))
            transaction_data["commission_currency"] = operation.commission.currency.upper()

        logger.debug(
            f"FX transaction detected: {transaction_data['from_currency']} "
            f"-> {transaction_data['to_currency']}"
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
    }

    transaction_data["type"] = operation_type_mapping.get(operation.type)
    if not transaction_data["type"]:
        return None  # Skip unsupported operation types

    # Handle currency
    if operation.payment and operation.payment.currency:
        transaction_data["currency"] = operation.payment.currency.upper()

    # Handle security matching
    if operation.instrument_uid:
        security, status = await _find_or_create_security(operation.instrument_uid, investor)
        if security:
            transaction_data["security"] = security
            logger.debug(f"Security matched: {security.name} (status: {status})")
        else:
            logger.warning(f"Could not match security for operation {operation.id}")
            # Get security info for potential creation
            name, isin, instrument_type = await get_security_by_uid(
                operation.instrument_uid, investor
            )
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

    # Handle quantity and price for buy/sell operations
    if operation.type in [OperationType.OPERATION_TYPE_BUY, OperationType.OPERATION_TYPE_SELL]:
        transaction_data["quantity"] = Decimal(str(operation.quantity))
        if operation.price:
            transaction_data["price"] = quotation_to_decimal(operation.price)
    else:
        # Handle payment/cash flow
        if operation.payment:
            payment = quotation_to_decimal(operation.payment)
            transaction_data["cash_flow"] = payment

    # Handle commission
    if operation.commission and operation.commission.units != 0:
        transaction_data["commission"] = quotation_to_decimal(operation.commission)

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
        return None, "Transaction already exists"

    # Create new transaction
    try:
        transaction = await database_sync_to_async(Transactions.objects.create)(**transaction_data)
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
