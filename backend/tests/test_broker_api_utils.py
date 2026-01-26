"""
Test cases for Tinkoff broker API utilities.

This module contains unit tests for the TinkoffAPI client class
and related broker API utility functions.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from tinkoff.invest import (
    GetOperationsByCursorRequest,
    Operation,
    OperationState,
    OperationType,
    RequestError,
)

from core.broker_api_utils import TinkoffAPI, TinkoffAPIException
from users.models import CustomUser


@pytest.fixture
def mock_user():
    """
    Create a mock user fixture.

    Returns:
        Mock: Mocked CustomUser instance.
    """
    return Mock(spec=CustomUser, id=1, username="test_user")


@pytest.fixture
def mock_account():
    """
    Create a mock account fixture.

    Returns:
        dict: Mock account data.
    """
    return {"id": "test_account_123", "name": "Test Account", "broker": "Tinkoff"}


@pytest.fixture
async def tinkoff_api():
    """
    Create a TinkoffAPI fixture for testing.

    Yields:
        TinkoffAPI: API client instance.
    """
    api = TinkoffAPI()
    yield api
    await api.disconnect()


@pytest.mark.asyncio
async def test_connect_success(tinkoff_api, mock_user):
    """Test successful API connection with valid token."""
    with (
        patch("core.broker_api_utils.get_user_token", new_callable=AsyncMock) as mock_get_token,
        patch("core.broker_api_utils.verify_token_access", new_callable=AsyncMock) as mock_verify,
    ):
        mock_get_token.return_value = "test_token"
        mock_verify.return_value = True

        result = await tinkoff_api.connect(mock_user)

        assert result is True
        assert tinkoff_api.token == "test_token"
        assert tinkoff_api.user == mock_user
        assert tinkoff_api.client is not None


@pytest.mark.asyncio
async def test_connect_invalid_token(tinkoff_api, mock_user):
    """Test API connection fails with invalid token."""
    with (
        patch("core.broker_api_utils.get_user_token", new_callable=AsyncMock) as mock_get_token,
        patch("core.broker_api_utils.verify_token_access", new_callable=AsyncMock) as mock_verify,
    ):
        mock_get_token.return_value = "test_token"
        mock_verify.return_value = False

        with pytest.raises(TinkoffAPIException, match="Invalid or insufficient token access"):
            await tinkoff_api.connect(mock_user)


@pytest.mark.asyncio
async def test_disconnect(tinkoff_api):
    """Test API disconnection clears client and token."""
    tinkoff_api.client = Mock()
    await tinkoff_api.disconnect()

    assert tinkoff_api.client is None
    assert tinkoff_api.token is None
    assert tinkoff_api.user is None


@pytest.mark.asyncio
async def test_retry_operation_success(tinkoff_api):
    """Test retry operation succeeds on first attempt."""
    mock_operation = AsyncMock()
    mock_operation.return_value = "success"

    result = await tinkoff_api._retry_operation(mock_operation)

    assert result == "success"
    assert mock_operation.call_count == 1


@pytest.mark.asyncio
async def test_retry_operation_with_retries(tinkoff_api):
    """Test retry operation succeeds after multiple attempts."""
    mock_operation = AsyncMock()

    # Create proper RequestError instances with required arguments
    error1 = RequestError(
        "Temporary error",
        details="Test error details",
        metadata={"code": "500", "message": "Temporary server error"},
    )
    error2 = RequestError(
        "Temporary error",
        details="Test error details",
        metadata={"code": "500", "message": "Temporary server error"},
    )

    mock_operation.side_effect = [error1, error2, "success"]

    result = await tinkoff_api._retry_operation(mock_operation)

    assert result == "success"
    assert mock_operation.call_count == 3


@pytest.mark.asyncio
async def test_retry_operation_auth_error(tinkoff_api):
    """Test retry operation fails on authentication error."""
    mock_operation = AsyncMock()

    # Create RequestError with authentication error code using positional arguments
    auth_error = RequestError(
        "Authentication failed",  # message as first positional argument
        "Invalid token",  # details as second positional argument
        {  # metadata as third positional argument
            "code": "40002",
            "message": "Authentication error: Invalid or expired token",
        },
    )

    mock_operation.side_effect = auth_error

    with pytest.raises(TinkoffAPIException, match="Authentication error"):
        await tinkoff_api._retry_operation(mock_operation)

    assert mock_operation.call_count == 1


@pytest.mark.asyncio
async def test_get_transactions_success(tinkoff_api, mock_user, mock_account):
    """Test successful transaction retrieval from API."""
    # Setup mock response for operations
    mock_operation = Mock(spec=Operation)
    mock_operation.id = "op123"
    mock_operation.type = OperationType.OPERATION_TYPE_BUY

    mock_response = Mock()
    mock_response.items = [mock_operation]
    mock_response.has_next = False

    with patch.object(tinkoff_api, "client") as mock_client:
        # Make the get_operations_by_cursor method an AsyncMock
        mock_client.operations.get_operations_by_cursor = AsyncMock(return_value=mock_response)

        # Mock the transaction mapping function
        with patch(
            "core.broker_api_utils.map_tinkoff_operation_to_transaction",
            new_callable=AsyncMock,
        ) as mock_map:
            mock_map.return_value = {"type": "BUY", "amount": 100}
            tinkoff_api.user = mock_user

            transactions = []
            async for transaction in tinkoff_api.get_transactions(mock_account):
                transactions.append(transaction)

            assert len(transactions) == 1
            assert transactions[0]["type"] == "BUY"
            assert mock_map.call_count == 1

            # Verify the API was called with correct parameters
            call_args = mock_client.operations.get_operations_by_cursor.call_args[0][0]
            assert call_args.account_id == str(mock_account["id"])
            assert call_args.state == OperationState.OPERATION_STATE_EXECUTED


@pytest.mark.asyncio
async def test_get_transactions_pagination(tinkoff_api, mock_user, mock_account):
    """Test transaction retrieval with pagination."""
    # Setup mock responses for pagination
    mock_operation1 = Mock(spec=Operation, id="op1")
    mock_operation2 = Mock(spec=Operation, id="op2")

    mock_response1 = Mock()
    mock_response1.items = [mock_operation1]
    mock_response1.has_next = True
    mock_response1.next_cursor = "cursor1"

    mock_response2 = Mock()
    mock_response2.items = [mock_operation2]
    mock_response2.has_next = False

    with (
        patch.object(tinkoff_api, "client") as mock_client,
        patch(
            "core.broker_api_utils.map_tinkoff_operation_to_transaction",
            new_callable=AsyncMock,
        ) as mock_map,
    ):
        # Make get_operations_by_cursor an AsyncMock with side_effect
        mock_client.operations.get_operations_by_cursor = AsyncMock(
            side_effect=[mock_response1, mock_response2]
        )

        mock_map.side_effect = [{"type": "BUY", "id": 1}, {"type": "SELL", "id": 2}]

        tinkoff_api.user = mock_user

        transactions = []
        async for transaction in tinkoff_api.get_transactions(mock_account):
            transactions.append(transaction)

        assert len(transactions) == 2
        assert transactions[0]["type"] == "BUY"
        assert transactions[1]["type"] == "SELL"
        assert mock_map.call_count == 2

        # Verify pagination behavior
        calls = mock_client.operations.get_operations_by_cursor.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0].cursor == ""  # First call should have empty cursor
        assert (
            calls[1][0][0].cursor == "cursor1"
        )  # Second call should use next_cursor from first response


@pytest.mark.asyncio
async def test_get_transactions_no_client(tinkoff_api, mock_account):
    """Test that attempting to get transactions without a client connection raises error."""
    tinkoff_api.client = None  # Ensure client is None

    with pytest.raises(TinkoffAPIException, match="Not connected to Tinkoff API"):
        async for _ in tinkoff_api.get_transactions(mock_account):
            pass  # We shouldn't get here


@pytest.mark.asyncio
async def test_get_transactions_with_dates(tinkoff_api, mock_user, mock_account):
    """Test transaction retrieval with date range filter."""
    mock_response = Mock()
    mock_response.items = []
    mock_response.has_next = False

    with patch.object(tinkoff_api, "client") as mock_client:
        # Make get_operations_by_cursor an AsyncMock
        mock_client.operations.get_operations_by_cursor = AsyncMock(return_value=mock_response)
        tinkoff_api.user = mock_user

        date_from = "2024-01-01"
        date_to = "2024-01-31"

        async for _ in tinkoff_api.get_transactions(mock_account, date_from, date_to):
            pass

        # Verify correct date parameters were used
        call_args = mock_client.operations.get_operations_by_cursor.call_args[0][0]
        assert call_args.from_.date() == datetime.strptime(date_from, "%Y-%m-%d").date()
        assert call_args.to.date() == datetime.strptime(date_to, "%Y-%m-%d").date()

        # Additional verifications
        assert isinstance(call_args, GetOperationsByCursorRequest)
        assert call_args.account_id == str(mock_account["id"])
        assert call_args.limit == tinkoff_api.OPERATIONS_BATCH_SIZE
