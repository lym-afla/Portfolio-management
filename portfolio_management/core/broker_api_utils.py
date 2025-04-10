import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import AsyncGenerator, Dict, Optional

from channels.db import database_sync_to_async
from tinkoff.invest import Client, GetOperationsByCursorRequest, OperationState, RequestError

from common.models import Accounts, Brokers

from .tinkoff_utils import get_user_token, map_tinkoff_operation_to_transaction, verify_token_access

logger = logging.getLogger(__name__)


class BrokerAPIException(Exception):
    """Base exception for broker API errors"""

    pass


class TinkoffAPIException(BrokerAPIException):
    """Tinkoff-specific API exceptions"""

    pass


class BrokerAPI(ABC):
    """Base class for broker API implementations"""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to broker API"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to broker API"""
        pass

    @abstractmethod
    async def get_transactions(
        self, account: Accounts, date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Fetch transactions from broker API

        Args:
            account: Accounts model instance containing broker account details
            date_from: Start date in YYYY-MM-DD format (optional)
            date_to: End date in YYYY-MM-DD format (optional)

        Yields:
            Dict containing transaction data with fields:
                - date: Transaction date (YYYY-MM-DD)
                - type: Transaction type (BUY, SELL, etc.)
                - security: Security object or None
                - quantity: Number of securities
                - price: Price per security
                - currency: Transaction currency
                - cash_flow: Total cash flow
                - commission: Transaction commission
                - needs_security_mapping: Boolean indicating if security needs mapping
                - security_description: Description of security if needs mapping
                - isin: ISIN code if available
                - symbol: Trading symbol if available
        """
        pass


class TinkoffAPI(BrokerAPI):
    """Tinkoff broker API implementation"""

    def __init__(self):
        super().__init__()
        self.client = None
        self.token = None
        self.user = None
        self.OPERATIONS_BATCH_SIZE = 1000
        self.MAX_RETRIES = 3
        self.RETRY_DELAY = 2  # seconds
        self.RETRY_BACKOFF_FACTOR = 2  # exponential backoff multiplier

    async def _retry_operation(self, operation_func, *args, **kwargs):
        """
        Retry wrapper for API operations

        Args:
            operation_func: Function to retry
            *args, **kwargs: Arguments for the function

        Returns:
            Result of the operation function

        Raises:
            TinkoffAPIException: If all retries fail
        """
        last_exception = None

        for attempt in range(self.MAX_RETRIES):
            try:
                # Check if operation_func is a coroutine function (asynchronous)
                if asyncio.iscoroutinefunction(operation_func):
                    return await operation_func(*args, **kwargs)
                else:
                    # For synchronous functions like the Tinkoff API methods
                    return operation_func(*args, **kwargs)

            except RequestError as e:
                last_exception = e
                error_message = str(e)

                # Don't retry on authentication or permission errors
                if any(code in error_message for code in ["40002", "40003"]):
                    raise TinkoffAPIException(f"Authentication error: {error_message}")

                # Don't retry on invalid request errors
                if "30001" in error_message:  # Example error code for invalid request
                    raise TinkoffAPIException(f"Invalid request: {error_message}")

                # Calculate delay with exponential backoff
                delay = self.RETRY_DELAY * (self.RETRY_BACKOFF_FACTOR**attempt)

                self.logger.warning(
                    f"Attempt {attempt + 1}/{self.MAX_RETRIES} failed. "
                    f"Retrying in {delay} seconds. Error: {error_message}"
                )

                await asyncio.sleep(delay)

            except Exception as e:
                last_exception = e
                self.logger.error(f"Unexpected error during retry attempt {attempt + 1}: {str(e)}")
                raise

        raise TinkoffAPIException(f"All retry attempts failed. Last error: {str(last_exception)}")

    async def connect(self, user) -> bool:
        """
        Connect to Tinkoff API using user's token

        Args:
            user: CustomUser instance

        Returns:
            bool: True if connection successful
        """
        self.logger.debug("Connecting to Tinkoff API")
        try:
            self.user = user
            self.token = await get_user_token(user)

            # Verify token access
            if not await verify_token_access(user):
                raise TinkoffAPIException("Invalid or insufficient token access")

            # Validate token by creating a temporary client
            with Client(self.token) as client:
                # Just verify we can access the API
                client.users.get_info()
            
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to Tinkoff API: {str(e)}")
            raise TinkoffAPIException(f"Tinkoff API connection failed: {str(e)}")

    async def disconnect(self) -> None:
        """Close connection to Tinkoff API"""
        self.logger.debug("Disconnecting from Tinkoff API")
        try:
            # Just clean up references
            self.token = None
            self.user = None
        except Exception as e:
            self.logger.error(f"Error disconnecting from Tinkoff API: {str(e)}")

    async def get_transactions(
        self, account: Accounts, date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Fetch transactions from Tinkoff API using cursor-based pagination

        Args:
            account: Accounts model instance containing broker account details
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format
        """
        self.logger.debug(f"Fetching Tinkoff transactions for account {account.id}")

        total_operations = 0  # Move initialization outside try block

        try:
            self.logger.debug(f"Fetching Tinkoff transactions for account {account.id} (native ID: {account.native_id})")

            if not self.token:
                raise TinkoffAPIException("Not connected to Tinkoff API")

            # Validate that we have a native_id for this account
            if not account.native_id:
                raise TinkoffAPIException(f"Account {account.id} ({account.name}) does not have a native ID set for Tinkoff API")

            from_date = (
                datetime.strptime(date_from, "%Y-%m-%d")
                if date_from
                else datetime.now() - timedelta(days=30)
            )
            to_date = datetime.strptime(date_to, "%Y-%m-%d") if date_to else datetime.now()

            # Use Client with context manager instead of storing it as instance attribute
            with Client(self.token) as client:
                # Verify the account exists in Tinkoff
                try:
                    # First try to get accounts to verify the account ID
                    tinkoff_accounts = client.users.get_accounts()
                    tinkoff_account_ids = [acc.id for acc in tinkoff_accounts.accounts]
                    
                    if account.native_id not in tinkoff_account_ids:
                        self.logger.error(f"Invalid native_id: {account.native_id} not found in Tinkoff accounts: {tinkoff_account_ids}")
                        raise TinkoffAPIException(f"Account with native ID {account.native_id} not found in Tinkoff. Available accounts: {', '.join(tinkoff_account_ids)}")
                    
                except Exception as e:
                    self.logger.error(f"Error verifying account: {str(e)}")
                    raise TinkoffAPIException(f"Error verifying account: {str(e)}")
                
                cursor = ""

                while True:
                    try:
                        # Wrap the API call with retry logic
                        response = await self._retry_operation(
                            client.operations.get_operations_by_cursor,
                            GetOperationsByCursorRequest(
                                account_id=str(account.native_id),
                                from_=from_date,
                                to=to_date,
                                cursor=cursor,
                                limit=self.OPERATIONS_BATCH_SIZE,
                                operation_types=[],
                                state=OperationState.OPERATION_STATE_EXECUTED,
                            ),
                        )

                        # Process operations in current batch
                        for operation in response.items:
                            total_operations += 1
                            self.logger.debug(
                                f"Processing operation {total_operations}: {operation.id}"
                            )

                            try:
                                transaction_data = await map_tinkoff_operation_to_transaction(
                                    operation=operation, investor=self.user, account=account
                                )

                                if transaction_data:
                                    yield transaction_data

                            except Exception as e:
                                self.logger.error(
                                    f"Error processing operation {operation.id}: {str(e)}"
                                )
                                continue

                        if not response.has_next:
                            self.logger.debug(
                                f"Completed fetching all operations. "
                                f"Total processed: {total_operations}"
                            )
                            break

                        cursor = response.next_cursor

                    except Exception as e:
                        self.logger.error(f"Error in batch processing: {str(e)}")
                        raise

        except Exception as e:
            self.logger.error(f"Error fetching Tinkoff transactions: {str(e)}")
            raise TinkoffAPIException(f"Failed to fetch Tinkoff transactions: {str(e)}")
        finally:
            self.logger.info(f"Finished processing {total_operations} operations from Tinkoff API")

    async def validate_connection(self) -> bool:
        """Validate API connection"""
        try:
            if not self.token:
                return False

            # Use context manager for proper resource handling
            with Client(self.token) as client:
                # Try to get user info as a validation check
                client.users.get_info()
                return True

        except Exception as e:
            self.logger.error(f"Connection validation failed: {str(e)}")
            return False


class InteractiveBrokersAPI(BrokerAPI):
    """Interactive Brokers API implementation"""

    async def connect(self) -> bool:
        self.logger.debug("Connecting to Interactive Brokers API")
        try:
            # TODO: Implement IB API connection
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to IB API: {str(e)}")
            raise BrokerAPIException(f"IB API connection failed: {str(e)}")

    async def disconnect(self) -> None:
        self.logger.debug("Disconnecting from Interactive Brokers API")
        try:
            # TODO: Implement IB API disconnect
            pass
        except Exception as e:
            self.logger.error(f"Error disconnecting from IB API: {str(e)}")

    async def get_transactions(
        self, account: Accounts, date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> AsyncGenerator[Dict, None]:
        self.logger.debug(f"Fetching IB transactions for account {account.id}")
        try:
            # TODO: Implement IB transaction fetching
            # This is a placeholder that yields no transactions
            if False:  # Replace with actual implementation
                yield {}
        except Exception as e:
            self.logger.error(f"Error fetching IB transactions: {str(e)}")
            raise BrokerAPIException(f"Failed to fetch IB transactions: {str(e)}")


async def get_broker_api(broker: Brokers) -> Optional[BrokerAPI]:
    """
    Factory function to get appropriate broker API handler

    Args:
        broker: Brokers model instance

    Returns:
        BrokerAPI instance or None if broker not supported/configured
    """
    try:
        # Check for Tinkoff tokens
        has_tinkoff_token = await database_sync_to_async(broker.tinkoff_tokens.exists)()

        if has_tinkoff_token:
            return TinkoffAPI()
        elif broker.name == "Interactive Brokers":
            # Add similar check for IB when implemented
            return InteractiveBrokersAPI()
        else:
            if has_tinkoff_token:
                logger.warning(
                    f"{broker.name} found but no API tokens configured for user: "
                    f"{broker.investor.id}"
                )
            else:
                logger.warning(f"No API implementation found for broker: {broker.name}")
            return None

    except Exception as e:
        logger.error(f"Error initializing broker API for {broker.name}: {str(e)}")
        return None
