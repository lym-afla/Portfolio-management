from django.apps import apps
import pytest
import uuid
from decimal import Decimal
from django.db import connection
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from common.models import Brokers, Assets, Transactions, FX
from core.import_utils import parse_charles_stanley_transactions
from constants import TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_DIVIDEND, TRANSACTION_TYPE_INTEREST_INCOME
import pandas as pd
from unittest.mock import patch, MagicMock
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async

pytestmark = pytest.mark.django_db

@pytest.fixture
async def setup_data():
    User = get_user_model()
    unique_username = f"testuser_{uuid.uuid4().hex[:8]}"
    investor = await database_sync_to_async(User.objects.create_user)(username=unique_username, password='12345')
    broker = await database_sync_to_async(Brokers.objects.create)(name='Charles Stanley Test', investor=investor)
    asset = await database_sync_to_async(Assets.objects.create)(name='Test Asset', type='Stock', currency='GBP')
    await database_sync_to_async(asset.investors.add)(investor)
    await database_sync_to_async(asset.brokers.add)(broker)
    return investor, broker, asset

@pytest.fixture(autouse=True)
def close_db_connection():
    yield
    connection.close()

@pytest.fixture(autouse=True)
async def clear_database(django_db_setup, django_db_blocker):
    yield
    @database_sync_to_async
    def clear_db():
        for model in apps.get_models():
            model.objects.all().delete()
        if connection.vendor == 'sqlite':
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM sqlite_sequence;")
    
    await clear_db()

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_parse_charles_stanley_transactions(setup_data):
    investor, broker, asset = setup_data
    
    mock_data = {
        'Date': ['01-Jan-2023'],
        'Description': ['Buy'],
        'Stock Description': ['Test Asset'],
        'Price': [100],
        'Debit': [1000],
        'Credit': [0]
    }
    mock_df = pd.DataFrame(mock_data)

    with patch('core.import_utils.read_excel_file', return_value=mock_df):
        generator = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id, confirm_every=False)
        
        transactions = []
        async for item in generator:
            # Check the structure of the yielded item and adjust accordingly
            # print(item)  # This will help us see the actual structure
            if isinstance(item, dict) and 'data' in item and item.get('status') == 'add_transaction':
                transactions.append(item['data'])

    assert len(transactions) == 1
    assert transactions[0]['type'] == TRANSACTION_TYPE_BUY
    assert transactions[0]['quantity'] == Decimal('10')
    assert transactions[0]['price'] == Decimal('100')
    assert transactions[0]['security'] == asset

@pytest.mark.asyncio
async def test_skip_existing_transaction(setup_data):
    investor, broker, asset = setup_data
    
    # Create an existing transaction
    await database_sync_to_async(Transactions.objects.create)(
        investor=investor,
        broker=broker,
        security=asset,
        currency='GBP',
        type=TRANSACTION_TYPE_BUY,
        date='2023-01-01',
        quantity=Decimal('10'),
        price=Decimal('100')
    )

    mock_data = {
        'Date': ['01-Jan-2023'],
        'Description': ['Buy'],
        'Stock Description': ['Test Asset'],
        'Price': [100],
        'Debit': [1000],
        'Credit': [0]
    }
    mock_df = pd.DataFrame(mock_data)

    with patch('core.import_utils.read_excel_file', return_value=mock_df):
        generator = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id, confirm_every=False)
        
        transactions = []
        async for item in generator:
            if item['status'] == 'add_transaction':
                transactions.append(item['data'])

    assert len(transactions) == 0  # The transaction should be skipped

@pytest.mark.asyncio
async def test_different_transaction_types(setup_data):
    investor, broker, asset = setup_data
    
    mock_data = {
        'Date': ['01-Jan-2023', '02-Jan-2023', '03-Jan-2023'],
        'Description': ['Buy', 'Dividend', 'Gross interest'],
        'Stock Description': ['Test Asset', 'Test Asset', ''],
        'Price': [100, 0, 0],
        'Debit': [1000, 0, 0],
        'Credit': [0, 50, 25]
    }
    mock_df = pd.DataFrame(mock_data)

    with patch('core.import_utils.read_excel_file', return_value=mock_df):
        generator = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id, confirm_every=False)
        
        transactions = []
        async for item in generator:
            if item['status'] == 'add_transaction':
                transactions.append(item['data'])

    assert len(transactions) == 3
    assert transactions[0]['type'] == TRANSACTION_TYPE_BUY
    assert transactions[1]['type'] == TRANSACTION_TYPE_DIVIDEND
    assert transactions[2]['type'] == TRANSACTION_TYPE_INTEREST_INCOME

@pytest.mark.asyncio
async def test_security_mapping(setup_data):
    investor, broker, _ = setup_data
    
    mock_data = {
        'Date': ['01-Jan-2023'],
        'Description': ['Buy'],
        'Stock Description': ['Unknown Asset'],
        'Price': [100],
        'Debit': [1000],
        'Credit': [0]
    }
    mock_df = pd.DataFrame(mock_data)

    with patch('core.import_utils.read_excel_file', return_value=mock_df):
        generator = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id, confirm_every=False)
        
        mapping_required = False
        async for item in generator:
            if item['status'] == 'security_mapping':
                mapping_required = True
                break

    assert mapping_required, "Security mapping should be required for unknown securities"

@pytest.mark.asyncio
async def test_invalid_excel_file():
    with pytest.raises(ValueError):  # Change back to ValueError if that's what you expect
        generator = parse_charles_stanley_transactions('invalid.xlsx', 'GBP', 1, 1, confirm_every=False)
        async for item in generator:
            if isinstance(item, dict) and 'error' in item:
                raise ValueError(item['error'])

@pytest.mark.asyncio
async def test_progress_reporting(setup_data):
    investor, broker, asset = setup_data
    
    mock_data = {
        'Date': ['01-Jan-2023'] * 100,
        'Description': ['Buy'] * 100,
        'Stock Description': ['Test Asset'] * 100,
        'Price': [100] * 100,
        'Debit': [1000] * 100,
        'Credit': [0] * 100
    }
    mock_df = pd.DataFrame(mock_data)

    with patch('core.import_utils.read_excel_file', return_value=mock_df):
        generator = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id, confirm_every=False)
        
        progress_updates = []
        async for item in generator:
            if item['status'] == 'progress':
                progress_updates.append(item)

    assert len(progress_updates) > 0
    assert progress_updates[-1]['progress'] == 100