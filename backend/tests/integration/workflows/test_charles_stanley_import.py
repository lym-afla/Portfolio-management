"""Test Charles Stanley import."""

from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.db import connection

from common.models import Accounts, Brokers, Transactions
from constants import (
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_INTEREST_INCOME,
)
from core.import_utils import parse_charles_stanley_transactions

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def charles_stanley_setup(user, broker, asset):
    """Set up data for Charles Stanley import tests."""
    # Create a Charles Stanley specific broker
    cs_broker = Brokers.objects.create(name="Charles Stanley Test", investor=user, country="UK")

    # Create broker account
    account = Accounts.objects.create(
        broker=cs_broker,
        native_id="TEST001",
        name="Test Account",
        restricted=False,
        is_active=True,
    )

    # Use provided asset but ensure it's available to the user
    asset.investors.add(user)

    return user, cs_broker, asset, account


@pytest.fixture(autouse=True)
def close_db_connection():
    """Close database connection."""
    yield
    connection.close()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_parse_charles_stanley_transactions(charles_stanley_setup):
    """Test parse Charles Stanley transactions."""
    investor, broker, asset, account = charles_stanley_setup

    mock_data = {
        "Date": ["01-Jan-2023"],
        "Description": ["Buy"],
        "Stock Description": [asset.name],  # Use actual asset name for matching
        "Price": [100],
        "Debit": [1000],
        "Credit": [0],
    }
    mock_df = pd.DataFrame(mock_data)

    with patch("core.import_utils.read_excel_file", return_value=mock_df):
        generator = parse_charles_stanley_transactions(
            "dummy.xlsx", "GBP", account.id, investor.id, confirm_every=False
        )

        transactions = []
        async for item in generator:
            if (
                isinstance(item, dict)
                and "data" in item
                and item.get("status") == "add_transaction"
            ):
                transactions.append(item["data"])

    assert len(transactions) == 1
    assert transactions[0]["type"] == TRANSACTION_TYPE_BUY
    assert transactions[0]["quantity"] == Decimal("10")
    assert transactions[0]["price"] == Decimal("100")
    assert transactions[0]["security"] == asset
    assert transactions[0]["account"] == account


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_skip_existing_transaction(charles_stanley_setup):
    """Test skip existing transaction."""
    investor, broker, asset, account = charles_stanley_setup

    # Create an existing transaction with account
    await database_sync_to_async(Transactions.objects.create)(
        investor=investor,
        account=account,
        security=asset,
        currency="GBP",
        type=TRANSACTION_TYPE_BUY,
        date="2023-01-01",
        quantity=Decimal("10"),
        price=Decimal("100"),
    )

    mock_data = {
        "Date": ["01-Jan-2023"],
        "Description": ["Buy"],
        "Stock Description": [asset.name],  # Use actual asset name for matching
        "Price": [100],
        "Debit": [1000],
        "Credit": [0],
    }
    mock_df = pd.DataFrame(mock_data)

    with patch("core.import_utils.read_excel_file", return_value=mock_df):
        generator = parse_charles_stanley_transactions(
            "dummy.xlsx", "GBP", account.id, investor.id, confirm_every=False
        )

        transactions = []
        async for item in generator:
            if item["status"] == "add_transaction":
                transactions.append(item["data"])

    assert len(transactions) == 0  # The transaction should be skipped


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_different_transaction_types(charles_stanley_setup):
    """Test different transaction types."""
    investor, broker, asset, account = charles_stanley_setup

    mock_data = {
        "Date": ["01-Jan-2023", "02-Jan-2023", "03-Jan-2023"],
        "Description": ["Buy", "Dividend", "Gross interest"],
        "Stock Description": [asset.name, asset.name, ""],  # Use actual asset name
        "Price": [100, 0, 0],
        "Debit": [1000, 0, 0],
        "Credit": [0, 50, 25],
    }
    mock_df = pd.DataFrame(mock_data)

    with patch("core.import_utils.read_excel_file", return_value=mock_df):
        generator = parse_charles_stanley_transactions(
            "dummy.xlsx", "GBP", account.id, investor.id, confirm_every=False
        )

        transactions = []
        async for item in generator:
            if item["status"] == "add_transaction":
                transactions.append(item["data"])

    assert len(transactions) == 3
    assert transactions[0]["type"] == TRANSACTION_TYPE_BUY
    assert transactions[1]["type"] == TRANSACTION_TYPE_DIVIDEND
    assert transactions[2]["type"] == TRANSACTION_TYPE_INTEREST_INCOME


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_security_mapping(charles_stanley_setup):
    """Test security mapping."""
    investor, broker, asset, account = charles_stanley_setup

    mock_data = {
        "Date": ["01-Jan-2023"],
        "Description": ["Buy"],
        "Stock Description": ["Unknown Asset"],  # This should trigger mapping requirement
        "Price": [100],
        "Debit": [1000],
        "Credit": [0],
    }
    mock_df = pd.DataFrame(mock_data)

    with patch("core.import_utils.read_excel_file", return_value=mock_df):
        generator = parse_charles_stanley_transactions(
            "dummy.xlsx", "GBP", account.id, investor.id, confirm_every=False
        )

        mapping_required = False
        async for item in generator:
            if item.get("status") == "security_mapping":
                mapping_required = True
                break

    assert mapping_required, "Security mapping should be required for unknown securities"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_invalid_excel_file():
    """Test invalid Excel file."""
    with pytest.raises(ValueError):  # Change back to ValueError if that's what you expect
        generator = parse_charles_stanley_transactions(
            "invalid.xlsx", "GBP", 1, 1, confirm_every=False
        )
        async for item in generator:
            if isinstance(item, dict) and "error" in item:
                raise ValueError(item["error"])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_progress_reporting(charles_stanley_setup):
    """Test progress reporting."""
    investor, broker, asset, account = charles_stanley_setup

    mock_data = {
        "Date": ["01-Jan-2023"] * 100,
        "Description": ["Buy"] * 100,
        "Stock Description": [asset.name] * 100,  # Use actual asset name
        "Price": [100] * 100,
        "Debit": [1000] * 100,
        "Credit": [0] * 100,
    }
    mock_df = pd.DataFrame(mock_data)

    with patch("core.import_utils.read_excel_file", return_value=mock_df):
        generator = parse_charles_stanley_transactions(
            "dummy.xlsx", "GBP", account.id, investor.id, confirm_every=False
        )

        progress_updates = []
        async for item in generator:
            if item.get("status") == "progress":
                progress_updates.append(item)

    assert len(progress_updates) > 0
    assert progress_updates[-1]["progress"] == 100
