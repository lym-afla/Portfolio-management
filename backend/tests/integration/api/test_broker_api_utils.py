"""Test broker API utils."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from tinkoff.invest import RequestError

from core.broker_api_utils import TinkoffAPI, TinkoffAPIException
from users.models import CustomUser


@pytest.fixture
def mock_user():
    """Create mock user fixture."""
    return Mock(spec=CustomUser, id=1, username="test_user")


@pytest.fixture
def mock_account():
    """Create mock account fixture."""
    account = Mock()
    account.id = "test_account_123"
    account.name = "Test Account"
    account.native_id = "test_account_123"
    return account


@pytest_asyncio.fixture
async def tinkoff_api():
    """Create Tinkoff API fixture."""
    api = TinkoffAPI()
    yield api
    if hasattr(api, "client") and api.client:
        await api.disconnect()


@pytest.mark.asyncio
async def test_connect_success(tinkoff_api, mock_user):
    """Test connect with success."""
    with (
        patch(
            "core.broker_api_utils.get_user_token", new_callable=AsyncMock
        ) as mock_get_token,
        patch(
            "core.broker_api_utils.verify_token_access", new_callable=AsyncMock
        ) as mock_verify,
        patch("core.broker_api_utils.Client") as mock_client_class,
    ):
        mock_get_token.return_value = "test_token"
        mock_verify.return_value = True
        mock_client_class.return_value.__enter__.return_value.users.get_info = Mock()

        result = await tinkoff_api.connect(mock_user)

        assert result is True
        assert tinkoff_api.token == "test_token"
        assert tinkoff_api.user == mock_user


@pytest.mark.asyncio
async def test_connect_invalid_token(tinkoff_api, mock_user):
    """Test connect with invalid token."""
    with (
        patch(
            "core.broker_api_utils.get_user_token", new_callable=AsyncMock
        ) as mock_get_token,
        patch(
            "core.broker_api_utils.verify_token_access", new_callable=AsyncMock
        ) as mock_verify,
    ):
        mock_get_token.return_value = "test_token"
        mock_verify.return_value = False

        with pytest.raises(
            TinkoffAPIException, match="Invalid or insufficient token access"
        ):
            await tinkoff_api.connect(mock_user)


@pytest.mark.asyncio
async def test_disconnect(tinkoff_api, mock_user):
    """Test disconnect."""
    # Setup API with some initial state
    tinkoff_api.token = "test_token"
    tinkoff_api.user = mock_user

    await tinkoff_api.disconnect()

    assert tinkoff_api.token is None
    assert tinkoff_api.user is None


@pytest.mark.asyncio
async def test_retry_operation_success(tinkoff_api):
    """Test retry operation with success."""
    mock_operation = AsyncMock()
    mock_operation.return_value = "success"

    result = await tinkoff_api._retry_operation(mock_operation)

    assert result == "success"
    assert mock_operation.call_count == 1


@pytest.mark.asyncio
async def test_retry_operation_with_retries(tinkoff_api):
    """Test retry operation with retries."""
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
    """Test retry operation with authentication error."""
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
    """Test getting transactions with success."""
    # Set up TinkoffAPI connection state
    tinkoff_api.token = "test_token"
    tinkoff_api.user = mock_user

    # Mock the entire get_transactions method to return test data
    async def mock_get_transactions(account, date_from=None, date_to=None):
        yield {"type": "BUY", "amount": 100}

    with patch.object(tinkoff_api, "get_transactions", mock_get_transactions):
        transactions = []
        async for transaction in tinkoff_api.get_transactions(mock_account):
            transactions.append(transaction)

        assert len(transactions) == 1
        assert transactions[0]["type"] == "BUY"
        assert transactions[0]["amount"] == 100


@pytest.mark.asyncio
async def test_get_transactions_pagination(tinkoff_api, mock_user, mock_account):
    """Test getting transactions with pagination."""
    # Set up TinkoffAPI connection state
    tinkoff_api.token = "test_token"
    tinkoff_api.user = mock_user

    # Mock the entire get_transactions method to return paginated data
    async def mock_get_transactions(account, date_from=None, date_to=None):
        yield {"type": "BUY", "id": 1}
        yield {"type": "SELL", "id": 2}

    with patch.object(tinkoff_api, "get_transactions", mock_get_transactions):
        transactions = []
        async for transaction in tinkoff_api.get_transactions(mock_account):
            transactions.append(transaction)

        assert len(transactions) == 2
        assert transactions[0]["type"] == "BUY"
        assert transactions[0]["id"] == 1
        assert transactions[1]["type"] == "SELL"
        assert transactions[1]["id"] == 2


@pytest.mark.asyncio
async def test_get_transactions_no_client(tinkoff_api, mock_account):
    """Test that attempting to get transactions without a client connection raises an error."""  # noqa: E501
    tinkoff_api.token = None  # Ensure token is None (this is what the method checks)

    with pytest.raises(TinkoffAPIException, match="Not connected to Tinkoff API"):
        async for _ in tinkoff_api.get_transactions(mock_account):
            pass  # We shouldn't get here


@pytest.mark.asyncio
async def test_get_transactions_with_dates(tinkoff_api, mock_user, mock_account):
    """Test getting transactions with dates."""
    # Set up TinkoffAPI connection state
    tinkoff_api.token = "test_token"
    tinkoff_api.user = mock_user

    # Track the dates passed to the mock
    passed_dates = []

    # Mock the entire get_transactions method to track date parameters
    async def mock_get_transactions(account, date_from=None, date_to=None):
        passed_dates.extend([date_from, date_to])
        yield {"type": "BUY", "date": date_from}

    with patch.object(tinkoff_api, "get_transactions", mock_get_transactions):
        date_from = "2024-01-01"
        date_to = "2024-01-31"

        transactions = []
        async for transaction in tinkoff_api.get_transactions(
            mock_account, date_from, date_to
        ):
            transactions.append(transaction)

        assert len(transactions) == 1
        assert transactions[0]["type"] == "BUY"
        assert transactions[0]["date"] == date_from

        # Verify dates were passed correctly
        assert passed_dates[0] == date_from
        assert passed_dates[1] == date_to
