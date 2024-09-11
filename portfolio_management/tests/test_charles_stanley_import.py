import os
import time
import traceback
from django.db import DatabaseError
import pytest
from django.test import TestCase
from unittest.mock import patch, MagicMock
import pandas as pd
from decimal import Decimal
from common.models import Brokers, Assets, Transactions
from users.models import CustomUser
from core.import_utils import parse_charles_stanley_transactions
import core.import_utils  # Add this import
from constants import TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_DIVIDEND, TRANSACTION_TYPE_INTEREST_INCOME

@pytest.mark.django_db
class TestCharlesStanleyImport:
    @pytest.fixture
    def setup_data(self):
        investor = CustomUser.objects.create(username='testuser')
        broker = Brokers.objects.create(name='Charles Stanley Test', investor=investor)  # Associate broker with investor
        asset = Assets.objects.create(name='Test Asset', investor=investor)
        asset.brokers.add(broker)
        return investor, broker, asset

    @patch('pandas.read_excel')
    def test_find_or_prompt_security(self, mock_read_excel, setup_data):
        investor, broker, asset = setup_data
        
        # Mock the Excel file content
        mock_data = {
            'Date': ['01-Jan-2023'],
            'Description': ['Buy'],
            'Stock Description': ['Test Asset'],
            'Price': [100],
            'Debit': [1000],
            'Credit': [0]
        }
        mock_read_excel.return_value = pd.DataFrame(mock_data)

        # Mock user input for security matching
        with patch('builtins.input', return_value='yes'):
            result = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id)

        assert len(result) > 0  # Assuming the function returns a list of transactions
        assert result[0]['security'] == asset
        assert result[0]['type'] == TRANSACTION_TYPE_BUY
        assert result[0]['quantity'] == Decimal('10')
        assert result[0]['price'] == Decimal('100')

    @patch('pandas.read_excel')
    def test_parse_transactions(self, mock_read_excel, setup_data):
        investor, broker, asset = setup_data
        mock_data = {
            'Date': ['01-Jan-2023'],
            'Description': ['Buy'],
            'Stock Description': ['Test Asset'],
            'Price': [100],
            'Debit': [1000],
            'Credit': [0]
        }
        mock_read_excel.return_value = pd.DataFrame(mock_data)

        def mock_find_or_prompt_security(*args, **kwargs):
            return asset

        # Patch the entire parse_charles_stanley_transactions function
        try:
            with patch.object(core.import_utils, 'parse_charles_stanley_transactions', wraps=parse_charles_stanley_transactions) as mock_parse:
                # Replace the internal find_or_prompt_security with our mock version
                mock_parse.find_or_prompt_security = mock_find_or_prompt_security
                
                with patch('builtins.input', side_effect=['yes', 'yes']):
                    transactions = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id)

            assert len(transactions) == 1
            assert transactions[0]['type'] == TRANSACTION_TYPE_BUY
            assert transactions[0]['quantity'] == Decimal('10')
            assert transactions[0]['price'] == Decimal('100')

        except Exception as e:
            pytest.fail(f"Test failed with exception: {str(e)}\n"
                        f"Exception type: {type(e).__name__}\n"
                        f"Exception traceback:\n{traceback.format_exc()}")
    

    @patch('pandas.read_excel')
    def test_skip_existing_transaction(self, mock_read_excel, setup_data):
        investor, broker, asset = setup_data
        # Create an existing transaction
        Transactions.objects.create(
            investor=investor,
            broker=broker,
            security=asset,
            currency='GBP',
            type='Buy',
            date='2023-01-01',
            quantity=Decimal('10'),
            price=Decimal('100')
        )

        # Mock the Excel file content with the same transaction
        mock_data = {
            'Date': ['01-Jan-2023'],
            'Description': ['Buy'],
            'Stock Description': ['Test Asset'],
            'Price': [100],
            'Debit': [1000],
            'Credit': [0]
        }
        mock_read_excel.return_value = pd.DataFrame(mock_data)

        # Mock user input for security matching
        with patch('builtins.input', return_value='yes'):
            transactions = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id)

        assert len(transactions) == 0  # The transaction should be skipped

    @patch('pandas.read_excel')
    def test_different_transaction_types(self, mock_read_excel, setup_data):
        investor, broker, asset = setup_data
        # Test different transaction types
        mock_data = {
            'Date': ['01-Jan-2023', '02-Jan-2023', '03-Jan-2023'],
            'Description': ['Buy', 'Dividend', 'Gross interest'],
            'Stock Description': ['Test Asset', 'Test Asset', ''],
            'Price': [100, 0, 0],
            'Debit': [1000, 0, 0],
            'Credit': [0, 50, 25]
        }
        mock_read_excel.return_value = pd.DataFrame(mock_data)

        # Mock user input for security matching and saving
        with patch('builtins.input', side_effect=['yes', 'yes', 'yes']):
            transactions = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id)

        assert len(transactions) == 3
        assert transactions[0]['type'] == TRANSACTION_TYPE_BUY
        assert transactions[1]['type'] == TRANSACTION_TYPE_DIVIDEND
        assert transactions[2]['type'] == TRANSACTION_TYPE_INTEREST_INCOME

    def test_invalid_excel_file(self, setup_data):
        investor, broker, _ = setup_data
        
        # Construct the path to the Data folder
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        data_file_path = os.path.join(project_root, 'Data', 'Test -- Cash.xlsx')
        
        with pytest.raises(ValueError):
            parse_charles_stanley_transactions(data_file_path, 'GBP', broker.id, investor.id)

    @patch('pandas.read_excel')
    def test_database_error(self, mock_read_excel, setup_data):
        investor, broker, asset = setup_data
        mock_data = {
            'Date': ['01-Jan-2023'],
            'Description': ['Buy'],
            'Stock Description': ['Test Asset'],
            'Price': [100],
            'Debit': [1000],
            'Credit': [0]
        }
        mock_read_excel.return_value = pd.DataFrame(mock_data)

        with patch('builtins.input', side_effect=['yes'] * 2):
            with patch.object(Transactions.objects, 'bulk_create', side_effect=DatabaseError):
                with pytest.raises(DatabaseError):
                    parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id)

    @patch('pandas.read_excel')
    def test_edge_cases(self, mock_read_excel, setup_data):
        investor, broker, asset = setup_data
        mock_data = {
            'Date': ['01-Jan-2023', '02-Jan-2023', '03-Jan-2023'],
            'Description': ['Buy', 'Buy', 'Buy'],
            'Stock Description': ['Test Asset', 'Test Asset', 'Test Asset'],
            'Price': [9999999.99, 1, 0.0001],  # Large, small, and minimum allowed values
            'Debit': [9999999.99, 1, 0.0001],
            'Credit': [0, 0, 0]
        }
        mock_read_excel.return_value = pd.DataFrame(mock_data)

        with patch('builtins.input', side_effect=['yes'] * 6):
            transactions = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id)

        assert len(transactions) == 3
        assert transactions[0]['price'] == Decimal('9999999.99')
        assert transactions[1]['price'] == Decimal('1')
        assert transactions[2]['price'] == Decimal('0.0001')

    @patch('pandas.read_excel')
    def test_user_interaction(self, mock_read_excel, setup_data):
        investor, broker, asset = setup_data
        mock_data = {
            'Date': ['01-Jan-2023', '02-Jan-2023', '03-Jan-2023'],
            'Description': ['Buy', 'Buy', 'Buy'],
            'Stock Description': ['Test Asset', 'Unknown Asset', 'Test Asset'],
            'Price': [100, 200, 300],
            'Debit': [1000, 2000, 3000],
            'Credit': [0, 0, 0]
        }
        mock_read_excel.return_value = pd.DataFrame(mock_data)

        with patch('builtins.input', side_effect=['yes', 'skip', 'no', 'Test Asset', 'yes']):
            transactions = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id)

        assert len(transactions) == 2
        assert transactions[0]['security'] == asset
        assert transactions[1]['security'] == asset

    @patch('pandas.read_excel')
    def test_performance(self, mock_read_excel, setup_data):
        investor, broker, asset = setup_data
        mock_data = {
            'Date': ['01-Jan-2023'] * 10000,
            'Description': ['Buy'] * 10000,
            'Stock Description': ['Test Asset'] * 10000,
            'Price': [100] * 10000,
            'Debit': [1000] * 10000,
            'Credit': [0] * 10000
        }
        mock_read_excel.return_value = pd.DataFrame(mock_data)

        start_time = time.time()
        with patch('builtins.input', return_value='yes'):
            transactions = parse_charles_stanley_transactions('dummy.xlsx', 'GBP', broker.id, investor.id)
        end_time = time.time()

        assert len(transactions) == 10000
        assert end_time - start_time < 15  # Assuming it should take less than 15 seconds

    @patch('builtins.input', side_effect=['yes'] * 100)  # Adjust the number based on expected prompts
    def test_integration(self, mock_input):
        # Assuming you have a test Excel file in your test directory
        # Construct the path to the Data folder
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        test_file_path = os.path.join(project_root, 'Data', 'Statement_ISA_4681921_Generated_2158_08Aug.xlsx')

        investor = CustomUser.objects.create(username='testuser')
        broker = Brokers.objects.create(name='Charles Stanley Test', investor=investor)

        transactions = parse_charles_stanley_transactions(test_file_path, 'GBP', broker.id, investor.id)

        assert len(transactions) > 0
        # Add more specific assertions based on your test file content