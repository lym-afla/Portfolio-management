from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from typing import AsyncGenerator, Dict, Optional
from tinkoff.invest import Client, RequestError, OperationType, GetOperationsByCursorRequest, OperationState
from tinkoff.invest.utils import quotation_to_decimal
import asyncio
from channels.db import database_sync_to_async

from common.models import Brokers

from .tinkoff_utils import (
    get_user_token,
    map_tinkoff_operation_to_transaction,
    verify_token_access
)

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
        self,
        account: Dict,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Fetch transactions from broker API
        
        Args:
            account: Account object containing broker account details
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
                return await operation_func(*args, **kwargs)
                
            except RequestError as e:
                last_exception = e
                error_message = str(e)
                
                # Don't retry on authentication or permission errors
                if any(code in error_message for code in ['40002', '40003']):
                    raise TinkoffAPIException(f"Authentication error: {error_message}")
                
                # Don't retry on invalid request errors
                if '30001' in error_message:  # Example error code for invalid request
                    raise TinkoffAPIException(f"Invalid request: {error_message}")
                
                # Calculate delay with exponential backoff
                delay = self.RETRY_DELAY * (self.RETRY_BACKOFF_FACTOR ** attempt)
                
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
            
            self.client = Client(self.token)
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Tinkoff API: {str(e)}")
            raise TinkoffAPIException(f"Tinkoff API connection failed: {str(e)}")

    async def disconnect(self) -> None:
        """Close connection to Tinkoff API"""
        self.logger.debug("Disconnecting from Tinkoff API")
        try:
            if self.client:
                self.client.close()
                self.client = None
                self.token = None
                self.user = None
        except Exception as e:
            self.logger.error(f"Error disconnecting from Tinkoff API: {str(e)}")

    async def get_transactions(
        self,
        account: Dict,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Fetch transactions from Tinkoff API using cursor-based pagination
        
        Args:
            account: Account object containing broker account details
            date_from: Start date in YYYY-MM-DD format
            date_to: End date in YYYY-MM-DD format
        """
        self.logger.debug(f"Fetching Tinkoff transactions for account {account['id']}")
        
        total_operations = 0  # Move initialization outside try block
    
        try:
            self.logger.debug(f"Fetching Tinkoff transactions for account {account['id']}")
            
            if not self.client:
                raise TinkoffAPIException("Not connected to Tinkoff API")

            from_date = datetime.strptime(date_from, '%Y-%m-%d') if date_from else datetime.now() - timedelta(days=30)
            to_date = datetime.strptime(date_to, '%Y-%m-%d') if date_to else datetime.now()

            cursor = ""
            
            while True:
                try:
                    # Wrap the API call with retry logic
                    response = await self._retry_operation(
                        self.client.operations.get_operations_by_cursor,
                        GetOperationsByCursorRequest(
                            account_id=str(account['id']),
                            from_=from_date,
                            to=to_date,
                            cursor=cursor,
                            limit=self.OPERATIONS_BATCH_SIZE,
                            operation_types=[],
                            state=OperationState.OPERATION_STATE_EXECUTED
                        )
                    )
                    
                    # Process operations in current batch
                    for operation in response.items:
                        total_operations += 1
                        self.logger.debug(f"Processing operation {total_operations}: {operation.id}")
                        
                        try:
                            transaction_data = await map_tinkoff_operation_to_transaction(
                                operation=operation,
                                investor=self.user,
                                account=account
                            )

                            if transaction_data:
                                yield transaction_data
                            
                        except Exception as e:
                            self.logger.error(f"Error processing operation {operation.id}: {str(e)}")
                            continue

                    if not response.has_next:
                        self.logger.debug(f"Completed fetching all operations. Total processed: {total_operations}")
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
            if not self.client:
                return False
            
            # Try to get user info as a validation check
            self.client.users.get_info()
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
        self,
        account: Dict,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> AsyncGenerator[Dict, None]:
        self.logger.debug(f"Fetching IB transactions for account {account['id']}")
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
        elif broker.name == 'Interactive Brokers':
            # Add similar check for IB when implemented
            return InteractiveBrokersAPI()
        else:
            if has_tinkoff_token:
                logger.warning(f"{broker.name} found but no API tokens configured for user: {broker.investor.id}")
            else:
                logger.warning(f"No API implementation found for broker: {broker.name}")
            return None
            
    except Exception as e:
        logger.error(f"Error initializing broker API for {broker.name}: {str(e)}")
        return None