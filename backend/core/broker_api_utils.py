"""
Broker API integration utilities for importing transactions from external brokers.

This module provides abstract base classes and implementations for interacting
with various broker APIs to fetch transactions and account data.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, time, timedelta, timezone
from typing import AsyncGenerator, Dict, Optional

from channels.db import database_sync_to_async
from t_tech.invest import (
    Client,
    GetOperationsByCursorRequest,
    OperationState,
    RequestError,
)

from common.models import Accounts, Brokers
from users.models import BybitApiToken, OKXApiToken

from .crypto_exchange_clients import BybitClient, CryptoExchangeAPIError, OKXClient
from .crypto_exchange_import import (
    _merge_sorted_events,
    normalize_bybit_deposit,
    normalize_bybit_reward,
    normalize_bybit_option_execution,
    normalize_bybit_option_settlement,
    normalize_bybit_spot_execution,
    normalize_bybit_withdrawal,
    normalize_okx_deposit_withdrawal,
    normalize_okx_option_fill,
    normalize_okx_option_settlement,
    normalize_okx_reward,
    normalize_okx_spot_fill,
)
from .tinkoff_utils import (
    get_user_token,
    map_tinkoff_operation_to_transaction,
    verify_token_access,
)

logger = logging.getLogger(__name__)


def _parse_import_boundary(value, *, end_of_day=False):
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max if end_of_day else time.min)
    else:
        parsed_date = datetime.strptime(str(value), "%Y-%m-%d").date()
        parsed = datetime.combine(parsed_date, time.max if end_of_day else time.min)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _crypto_exchange_date_params(date_from, date_to, *, start_key, end_key):
    params = {}
    start_ms = _parse_import_boundary(date_from)
    end_ms = _parse_import_boundary(date_to, end_of_day=True)
    if start_ms is not None:
        params[start_key] = start_ms
    if end_ms is not None:
        params[end_key] = end_ms
    return params


class BrokerAPIException(Exception):
    """Base exception for broker API errors."""

    pass


class TinkoffAPIException(BrokerAPIException):
    """Tinkoff-specific API exceptions."""

    pass


class BrokerAPI(ABC):
    """
    Abstract base class for broker API implementations.

    This class defines the interface that all broker API implementations must follow,
    providing methods for connecting, disconnecting, and fetching transactions.
    """

    def __init__(self):
        """
        Initialize the broker API client.

        Sets up a logger instance for the specific API implementation class.
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to broker API."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to broker API."""
        pass

    @abstractmethod
    async def get_transactions(
        self,
        account: Accounts,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """
        Fetch transactions from broker API.

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
    """
    Tinkoff broker API implementation.

    This class provides methods to interact with the Tinkoff Invest API,
    including authentication, transaction fetching, and error handling with
    automatic retries and backoff.
    """

    def __init__(self):
        """
        Initialize the Tinkoff API client.

        Sets up the client, token, and retry configuration parameters.
        """
        super().__init__()
        self.client = None
        self.token = None
        self.user = None
        self.OPERATIONS_BATCH_SIZE = 1000
        self.MAX_RETRIES = 3
        self.RETRY_DELAY = 2  # seconds
        self.RETRY_BACKOFF_FACTOR = 2  # exponential backoff multiplier

    async def _retry_operation(self, operation_func, *args, **kwargs):
        """Retry wrapper for API operations.

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
        Connect to Tinkoff API using user's token.

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
        """Close connection to Tinkoff API."""
        self.logger.debug("Disconnecting from Tinkoff API")
        try:
            # Just clean up references
            self.token = None
            self.user = None
        except Exception as e:
            self.logger.error(f"Error disconnecting from Tinkoff API: {str(e)}")

    async def get_transactions(
        self,
        account: Accounts,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """
        Fetch transactions from Tinkoff API using cursor-based pagination.

        Args:
            account: Accounts model instance containing broker account details
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format
        """
        self.logger.debug(f"Fetching Tinkoff transactions for account {account.id}")

        total_operations = 0  # Move initialization outside try block

        try:
            self.logger.debug(
                f"Fetching Tinkoff transactions for account {account.id} "
                f"(native ID: {account.native_id})"
            )

            if not self.token:
                raise TinkoffAPIException("Not connected to Tinkoff API")

            # Validate that we have a native_id for this account
            if not account.native_id:
                raise TinkoffAPIException(
                    f"Account {account.id} ({account.name}) "
                    "does not have a native ID set for Tinkoff API"
                )

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
                        self.logger.error(
                            f"Invalid native_id: {account.native_id} "
                            f"not found in Tinkoff accounts: {tinkoff_account_ids}"
                        )
                        raise TinkoffAPIException(
                            f"Account with native ID {account.native_id} not found in Tinkoff. "
                            f"Available accounts: {', '.join(tinkoff_account_ids)}"
                        )

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
                                    operation=operation,
                                    investor=self.user,
                                    account=account,
                                )

                                if transaction_data:
                                    if isinstance(transaction_data, str):
                                        self.logger.warning(f"{{operation.id}}: {transaction_data}")
                                        continue
                                    yield transaction_data
                                else:
                                    self.logger.warning(
                                        f"Opperation {operation.id} is unrecognized"
                                    )
                                    yield {
                                        "unrecognized_operation": True,
                                        "data": operation,
                                    }

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
        """
        Validate the API connection by attempting to fetch user info.

        Returns:
            bool: True if connection is valid and authentication succeeds,
                False otherwise.
        """
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
    """
    Interactive Brokers API implementation (placeholder).

    This class is a stub for future Interactive Brokers API integration.
    """

    async def connect(self) -> bool:
        """
        Establish connection to Interactive Brokers API.

        Returns:
            bool: True if connection successful.

        Raises:
            BrokerAPIException: If connection fails.
        """
        self.logger.debug("Connecting to Interactive Brokers API")
        try:
            # TODO: Implement IB API connection
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to IB API: {str(e)}")
            raise BrokerAPIException(f"IB API connection failed: {str(e)}")

    async def disconnect(self) -> None:
        """
        Close connection to Interactive Brokers API.

        Raises:
            BrokerAPIException: If disconnection fails.
        """
        self.logger.debug("Disconnecting from Interactive Brokers API")
        try:
            # TODO: Implement IB API disconnect
            pass
        except Exception as e:
            self.logger.error(f"Error disconnecting from IB API: {str(e)}")

    async def get_transactions(
        self,
        account: Accounts,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> AsyncGenerator[Dict, None]:
        """
        Fetch transactions from Interactive Brokers API.

        Args:
            account: Accounts model instance.
            date_from: Start date in YYYY-MM-DD format (optional).
            date_to: End date in YYYY-MM-DD format (optional).

        Yields:
            Dict: Transaction data dictionaries.

        Raises:
            BrokerAPIException: If transaction fetching fails.
        """
        self.logger.debug(f"Fetching IB transactions for account {account.id}")
        try:
            # TODO: Implement IB transaction fetching
            # This is a placeholder that yields no transactions
            if False:  # Replace with actual implementation
                yield {}
        except Exception as e:
            self.logger.error(f"Error fetching IB transactions: {str(e)}")
            raise BrokerAPIException(f"Failed to fetch IB transactions: {str(e)}")


class BybitAPI(BrokerAPI):
    """Bybit BrokerAPI adapter returning normalized crypto exchange events."""

    def __init__(self):
        super().__init__()
        self.user = None
        self.partial_failures = []

    async def connect(self, user) -> bool:
        self.user = user
        has_token = await database_sync_to_async(
            lambda: BybitApiToken.objects.filter(user=user, is_active=True).exists()
        )()
        if not has_token:
            raise BrokerAPIException("No active Bybit token configured")
        return True

    async def disconnect(self) -> None:
        self.user = None

    async def get_transactions(
        self,
        account: Accounts,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ):
        if not self.user:
            raise BrokerAPIException("Not connected to Bybit API")

        token = await database_sync_to_async(
            lambda: account.broker.bybit_tokens.filter(
                user=self.user,
                is_active=True,
            ).first()
        )()
        if not token:
            raise BrokerAPIException("No active Bybit token for selected broker")

        client = BybitClient(
            api_key=token.api_key,
            api_secret=token.get_api_secret(self.user),
            testnet=token.testnet,
        )
        date_params = _crypto_exchange_date_params(
            date_from, date_to, start_key="startTime", end_key="endTime"
        )

        def _safe(endpoint_name, normalizer, iter_factory):
            def _gen():
                try:
                    for payload in iter_factory():
                        event = normalizer(payload)
                        if event is not None:
                            yield event
                except CryptoExchangeAPIError as exc:
                    self.partial_failures.append((endpoint_name, str(exc)))
            return _gen()

        streams = [
            _safe("executions", normalize_bybit_spot_execution, lambda: client.iter_executions({"category": "spot", **date_params})),
            _safe("option_executions", normalize_bybit_option_execution, lambda: client.iter_option_executions(date_params)),
            _safe("deposits", normalize_bybit_deposit, lambda: client.iter_deposits(date_params)),
            _safe("withdrawals", normalize_bybit_withdrawal, lambda: client.iter_withdrawals(date_params)),
            _safe("earn", normalize_bybit_reward, lambda: client.iter_transaction_log({"type": "Earn", **date_params})),
            _safe("option_settlements", normalize_bybit_option_settlement, lambda: client.iter_option_settlements(date_params)),
        ]
        for event in _merge_sorted_events(*streams):
            yield event


class OKXAPI(BrokerAPI):
    """OKX BrokerAPI adapter returning normalized crypto exchange events."""

    def __init__(self):
        super().__init__()
        self.user = None
        self.partial_failures = []

    async def connect(self, user) -> bool:
        self.user = user
        has_token = await database_sync_to_async(
            lambda: OKXApiToken.objects.filter(user=user, is_active=True).exists()
        )()
        if not has_token:
            raise BrokerAPIException("No active OKX token configured")
        return True

    async def disconnect(self) -> None:
        self.user = None

    async def get_transactions(
        self,
        account: Accounts,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ):
        if not self.user:
            raise BrokerAPIException("Not connected to OKX API")

        token = await database_sync_to_async(
            lambda: account.broker.okx_tokens.filter(
                user=self.user,
                is_active=True,
            ).first()
        )()
        if not token:
            raise BrokerAPIException("No active OKX token for selected broker")

        client = OKXClient(
            api_key=token.api_key,
            api_secret=token.get_api_secret(self.user),
            passphrase=token.get_passphrase(self.user),
            simulated_trading=token.simulated_trading,
        )
        date_params = _crypto_exchange_date_params(
            date_from, date_to, start_key="begin", end_key="end"
        )

        def _safe(endpoint_name, normalizer, iter_factory):
            def _gen():
                try:
                    for payload in iter_factory():
                        event = normalizer(payload)
                        if event is not None:
                            yield event
                except CryptoExchangeAPIError as exc:
                    self.partial_failures.append((endpoint_name, str(exc)))
            return _gen()

        streams = [
            _safe("spot_fills", normalize_okx_spot_fill, lambda: client.iter_fills_history({"instType": "SPOT", **date_params})),
            _safe("option_fills", normalize_okx_option_fill, lambda: client.iter_option_fills(date_params)),
            _safe("deposits_withdrawals", normalize_okx_deposit_withdrawal, lambda: client.iter_asset_deposits_withdrawals(date_params)),
            _safe("earn", normalize_okx_reward, lambda: client.iter_earn_lending_history(date_params)),
            _safe("option_settlements", normalize_okx_option_settlement, lambda: client.iter_option_settlements(date_params)),
        ]
        for event in _merge_sorted_events(*streams):
            yield event


async def get_broker_api(broker: Brokers) -> Optional[BrokerAPI]:
    """
    Get appropriate broker API handler.

    Args:
        broker: Brokers model instance

    Returns:
        BrokerAPI instance or None if broker not supported/configured
    """
    try:
        # Check for Tinkoff tokens
        has_tinkoff_token = await database_sync_to_async(broker.tinkoff_tokens.exists)()
        has_bybit_token = await database_sync_to_async(
            lambda: broker.bybit_tokens.filter(is_active=True).exists()
        )()
        has_okx_token = await database_sync_to_async(
            lambda: broker.okx_tokens.filter(is_active=True).exists()
        )()

        if has_tinkoff_token:
            return TinkoffAPI()
        elif has_bybit_token:
            return BybitAPI()
        elif has_okx_token:
            return OKXAPI()
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
