import logging
from decimal import Decimal

from channels.db import database_sync_to_async
from tinkoff.invest import Client, OperationType
from tinkoff.invest.exceptions import RequestError
from tinkoff.invest.utils import quotation_to_decimal

from common.models import Assets, Transactions
from constants import (
    TRANSACTION_TYPE_BROKER_COMMISSION,
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_SELL,
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
    Returns (name, ISIN) or (None, None) if not found.
    """
    try:
        token = await get_user_token(user)
        with Client(token) as client:
            instrument = client.instruments.get_instrument_by(
                id_type=3, id=instrument_uid
            )  # id_type=3 is uid
            return (instrument.instrument.name, instrument.instrument.isin)
    except RequestError as e:
        error_message = str(e)
        if "40002" in error_message:
            logger.error("Insufficient privileges for Tinkoff API token")
        elif "40003" in error_message:
            logger.error("Invalid or expired Tinkoff API token")
        else:
            logger.error(f"Tinkoff API error: {error_message}")
        return None, None
    except Exception as e:
        logger.error(f"Error getting security details from Tinkoff: {str(e)}")
        return None, None


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
    name, isin = await get_security_by_uid(instrument_uid, investor)
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

            security = await create_security_from_micex(name, isin, investor)
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
        dict: Transaction data ready for creating a Transaction instance
    """
    # Initialize base transaction data
    transaction_data = {
        "investor": investor,
        "account": account,
        "date": operation.date.date(),
        "comment": operation.description,
    }

    # Map operation type
    operation_type_mapping = {
        OperationType.OPERATION_TYPE_BUY: TRANSACTION_TYPE_BUY,
        OperationType.OPERATION_TYPE_SELL: TRANSACTION_TYPE_SELL,
        OperationType.OPERATION_TYPE_DIVIDEND: TRANSACTION_TYPE_DIVIDEND,
        OperationType.OPERATION_TYPE_BROKER_FEE: TRANSACTION_TYPE_BROKER_COMMISSION,
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

    # Handle quantity and price for buy/sell operations
    if operation.type in [OperationType.OPERATION_TYPE_BUY, OperationType.OPERATION_TYPE_SELL]:
        transaction_data["quantity"] = Decimal(str(operation.quantity))
        if operation.price:
            transaction_data["price"] = quotation_to_decimal(operation.price)

    # Handle payment/cash flow
    if operation.payment:
        payment = quotation_to_decimal(operation.payment)
        if operation.type == OperationType.OPERATION_TYPE_BUY:
            transaction_data["cash_flow"] = -abs(payment)
        else:
            transaction_data["cash_flow"] = abs(payment)

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
