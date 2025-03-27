from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from tinkoff.invest import MoneyValue, OperationType, Quotation
from tinkoff.invest.exceptions import RequestError

from common.models import Assets, Brokers
from constants import TRANSACTION_TYPE_BUY
from core.tinkoff_utils import (
    _find_or_create_security,
    get_account_info,
    get_security_by_uid,
    get_user_token,
    map_tinkoff_operation_to_transaction,
    verify_token_access,
)
from users.models import TinkoffApiToken

CustomUser = get_user_model()


@pytest.fixture
def user():
    return CustomUser.objects.create_user(
        username="testuser", email="test@example.com", password="testpass123"
    )


@pytest.fixture
def broker(user):
    return Brokers.objects.create(name="Test Broker", investor=user)


@pytest.fixture
def tinkoff_token(user, broker):
    token = TinkoffApiToken.objects.create(
        user=user, broker=broker, token_type="read_only", sandbox_mode=False, is_active=True
    )
    token.set_token("test-token", user)
    return token


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_get_user_token(user, tinkoff_token):
    """Test token retrieval functionality"""
    # Test successful token retrieval
    token = await get_user_token(user)
    assert token == "test-token"

    # Test inactive token
    tinkoff_token.is_active = False
    await database_sync_to_async(tinkoff_token.save)()

    with pytest.raises(ValueError, match="No active Tinkoff API token found for user"):
        await get_user_token(user)

    # Test non-existent token
    await database_sync_to_async(tinkoff_token.delete)()
    with pytest.raises(ValueError, match="No active Tinkoff API token found for user"):
        await get_user_token(user)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@patch("core.tinkoff_utils.Client")
async def test_get_security_by_uid(mock_client, user, tinkoff_token):
    """Test security details retrieval from Tinkoff API"""
    # Mock the Tinkoff API response
    mock_instrument = MagicMock()
    mock_instrument.instrument.name = "Test Stock"
    mock_instrument.instrument.isin = "TEST123456789"

    mock_client_instance = MagicMock()
    mock_client_instance.instruments.get_instrument_by.return_value = mock_instrument
    mock_client.return_value.__enter__.return_value = mock_client_instance

    # Test successful retrieval
    name, isin = await get_security_by_uid("test-uid", user)
    assert name == "Test Stock"
    assert isin == "TEST123456789"
    mock_client_instance.instruments.get_instrument_by.assert_called_once_with(
        id_type=3, id="test-uid"
    )

    # Test API error handling for insufficient privileges
    mock_client_instance.instruments.get_instrument_by.side_effect = RequestError(
        "Token has insufficient privileges", {"code": "40002"}, {}  # message  # details  # metadata
    )
    name, isin = await get_security_by_uid("test-uid", user)
    assert name is None and isin is None

    # Test API error handling for invalid token
    mock_client_instance.instruments.get_instrument_by.side_effect = RequestError(
        "Invalid token", {"code": "40003"}, {}
    )
    name, isin = await get_security_by_uid("test-uid", user)
    assert name is None and isin is None

    # Test API error handling for generic error
    mock_client_instance.instruments.get_instrument_by.side_effect = RequestError(
        "Internal server error", {"code": "50000"}, {}
    )
    name, isin = await get_security_by_uid("test-uid", user)
    assert name is None and isin is None

    # Test unexpected exception
    mock_client_instance.instruments.get_instrument_by.side_effect = Exception("Unexpected error")
    name, isin = await get_security_by_uid("test-uid", user)
    assert name is None and isin is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@patch("core.tinkoff_utils.get_security_by_uid")
@patch("core.tinkoff_utils.create_security_from_micex")
async def test_find_or_create_security(mock_create_security, mock_get_security, user, broker):
    mock_get_security.return_value = ("Test Stock", "TEST123456789")

    # Test case 1: Security exists with relationships
    asset = await Assets.objects.acreate(
        type="Stock", ISIN="TEST123456789", name="Test Stock", currency="USD", exposure="Equity"
    )
    await asset.investors.aset([user])

    security, status = await _find_or_create_security("test-uid", user)
    assert status == "existing_with_relationships"
    assert security.ISIN == "TEST123456789"

    # Test case 2: Security exists without relationships
    await asset.investors.aclear()

    security, status = await _find_or_create_security("test-uid", user)
    assert status == "existing_added_relationships"
    assert security.ISIN == "TEST123456789"

    # Test case 3: Security doesn't exist, create new
    await asset.adelete()
    mock_create_security.return_value = await Assets.objects.acreate(
        type="Stock", ISIN="NEW123456789", name="New Stock", currency="USD", exposure="Equity"
    )

    security, status = await _find_or_create_security("test-uid", user)
    assert status == "created_new"
    assert security.ISIN == "NEW123456789"


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@patch("core.tinkoff_utils._find_or_create_security")
async def test_map_tinkoff_operation_to_transaction(mock_find_or_create, user, broker):
    # Create mock operation
    operation = MagicMock()
    operation.date = datetime.now(timezone.utc)
    operation.description = "Test transaction"
    operation.type = OperationType.OPERATION_TYPE_BUY
    operation.payment = MoneyValue(currency="USD", units=-100, nano=0)
    operation.price = Quotation(units=50, nano=0)
    operation.quantity = 2
    operation.commission = MoneyValue(currency="USD", units=1, nano=0)
    operation.instrument_uid = "test-uid"

    asset = await database_sync_to_async(Assets.objects.create)(
        type="Stock", ISIN="TEST123456789", name="Test Stock", currency="USD", exposure="Equity"
    )
    mock_find_or_create.return_value = (asset, "existing_with_relationships")

    transaction_data = await map_tinkoff_operation_to_transaction(operation, user, broker)

    assert transaction_data["type"] == TRANSACTION_TYPE_BUY
    assert transaction_data["currency"] == "USD"
    assert transaction_data["quantity"] == Decimal("2")
    assert transaction_data["price"] == Decimal("50")
    assert transaction_data["cash_flow"] == Decimal("-100")
    assert transaction_data["commission"] == Decimal("1")
    assert transaction_data["security"] == asset


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@patch("core.tinkoff_utils.Client")
async def test_verify_token_access(mock_client, user, tinkoff_token):
    mock_client_instance = MagicMock()
    mock_client_instance.users.get_info.return_value = MagicMock()
    mock_client.return_value.__enter__.return_value = mock_client_instance

    result = await verify_token_access(user)
    assert result is True

    mock_client_instance.users.get_info.side_effect = Exception("Token invalid")
    result = await verify_token_access(user)
    assert result is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
@patch("core.tinkoff_utils.Client")
async def test_get_account_info(mock_client, user, tinkoff_token):
    mock_account = MagicMock()
    mock_account.id = "test-account"
    mock_account.type.name = "broker"
    mock_account.name = "Test Account"
    mock_account.status.name = "active"

    mock_response = MagicMock()
    mock_response.accounts = [mock_account]

    mock_client_instance = MagicMock()
    mock_client_instance.users.get_accounts.return_value = mock_response
    mock_client.return_value.__enter__.return_value = mock_client_instance

    result = await get_account_info(user)
    assert result is not None
    assert len(result["accounts"]) == 1
    assert result["accounts"][0]["id"] == "test-account"
    assert result["accounts"][0]["type"] == "broker"
