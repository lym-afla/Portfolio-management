import datetime
from functools import lru_cache
from django.contrib.auth import get_user_model
from common.models import Brokers, Assets, Transactions
from decimal import Decimal, InvalidOperation
import pandas as pd
from django.core.files.storage import default_storage
from collections import defaultdict
from fuzzywuzzy import process
import structlog
import logging
from channels.db import database_sync_to_async
from django.forms.models import model_to_dict

from constants import TRANSACTION_TYPE_BROKER_COMMISSION, TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_DIVIDEND, TRANSACTION_TYPE_INTEREST_INCOME, TRANSACTION_TYPE_SELL

# logger = structlog.get_logger(__name__)
logger = logging.getLogger(__name__)

CustomUser = get_user_model()

@database_sync_to_async
def get_investor(investor_id):
    return CustomUser.objects.get(id=investor_id)

@database_sync_to_async
def get_broker(broker_id):
    return Brokers.objects.get(id=broker_id)

@database_sync_to_async
def get_existing_transactions(investor, broker):
    return set(Transactions.objects.filter(investor=investor, broker=broker).values_list(
        'security__id', 'currency', 'type', 'date', 'quantity', 'price', 'cash_flow', 'commission'
    ))

def read_excel_file(file_path):
    try:
        with default_storage.open(file_path, 'rb') as file:
            df = pd.read_excel(file, header=3, usecols=['Date', 'Description', 'Stock Description', 'Price', 'Debit', 'Credit'])
        return df
    except pd.errors.EmptyDataError:
        raise ValueError('The uploaded file is empty or could not be read.')
    except Exception as e:
        raise ValueError(f'An error occurred while reading the file: {str(e)}')

@database_sync_to_async
def find_security(stock_description, investor, broker, security_cache):
    if security_cache[stock_description] is not None:
        return security_cache[stock_description], None

    securities = list(Assets.objects.filter(investor=investor, brokers=broker))
    security_names = [security.name for security in securities]
    best_match = process.extractOne(stock_description, security_names, score_cutoff=60)
    
    if best_match:
        match_name, match_score = best_match
        security = next(s for s in securities if s.name == match_name)
        security_cache[stock_description] = security
        return security, best_match
    
    return None, None

async def process_transaction_row(row, investor, broker, currency, security_cache, existing_transactions):
    
    logger.info(f"Processing transaction row, {investor.id}, {broker.id}, {currency}")

    quantity_decimal_places = Transactions._meta.get_field('quantity').decimal_places
    price_decimal_places = Transactions._meta.get_field('price').decimal_places
                
    try:
        if pd.isna(row['Date']):
            return None, 'skipped'

        transaction_date = pd.to_datetime(row['Date'], errors='coerce').date()
        description = row['Description']
        stock_description = row['Stock Description']
        price = Decimal(str(row['Price'])) if not pd.isna(row['Price']) else None
        debit = Decimal(str(row['Debit'])) if not pd.isna(row['Debit']) else Decimal('0')
        credit = Decimal(str(row['Credit'])) if not pd.isna(row['Credit']) else Decimal('0')

        SKIP_DESCRIPTIONS = {'* BALANCE B/F *', 'Cash Transfers ISA'}
        COMMISSION_DESCRIPTIONS = {'Funds Platform Fee', 'Govt Flat Rate Int Charge'}
        CASH_IN_DESCRIPTIONS = {'Stocks & Shares Subs', 'ISA Subscription'}
        INTEREST_INCOME_DESCRIPTIONS = {'Gross interest'}
        DIVIDEND_DESCRIPTIONS = {'Dividend', 'Equalisation', 'Tax Credit'}

        if description in SKIP_DESCRIPTIONS:
            return None, 'skipped'

        if description in COMMISSION_DESCRIPTIONS:
            transaction_type = TRANSACTION_TYPE_BROKER_COMMISSION
        elif description in CASH_IN_DESCRIPTIONS:
            transaction_type = TRANSACTION_TYPE_CASH_IN
        elif description in DIVIDEND_DESCRIPTIONS:
            transaction_type = TRANSACTION_TYPE_DIVIDEND
        elif description in INTEREST_INCOME_DESCRIPTIONS:
            transaction_type = TRANSACTION_TYPE_INTEREST_INCOME
        elif debit > 0:
            transaction_type = TRANSACTION_TYPE_BUY
        elif credit > 0:
            transaction_type = TRANSACTION_TYPE_SELL
        else:
            return None, 'skipped'

        if isinstance(stock_description, str):
            security, best_match = await find_security(stock_description, investor, broker, security_cache)
        else:
            security, best_match = None, None

        if security is None and transaction_type not in [TRANSACTION_TYPE_INTEREST_INCOME, TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_BROKER_COMMISSION]:
            return {'status': 'security_mapping', 'security': stock_description, 'best_match': best_match}, 'mapping_required'

        transaction_data = {
            'investor': investor,
            'broker': broker,
            'security': security,
            'currency': currency,
            'type': transaction_type,
            'date': transaction_date,
        }

        if transaction_type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL]:
            if transaction_type == TRANSACTION_TYPE_BUY:
                quantity = abs(Decimal(str(debit)) / price)
            else:
                quantity = abs(-Decimal(str(credit)) / price)
            transaction_data.update({
                'quantity': round(quantity, quantity_decimal_places),
                'price': round(Decimal(str(price)), price_decimal_places),
            })
        elif transaction_type in [TRANSACTION_TYPE_INTEREST_INCOME, TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_DIVIDEND]:
            transaction_data['cash_flow'] = round(Decimal(str(credit)), 2)
        elif transaction_type == TRANSACTION_TYPE_BROKER_COMMISSION:
            transaction_data['commission'] = round(-Decimal(str(debit)), 2)

        transaction_tuple = (
            transaction_data.get('security').id if transaction_data.get('security') else None,
            transaction_data['currency'],
            transaction_data['type'],
            transaction_data['date'],
            transaction_data.get('quantity'),
            transaction_data.get('price'),
            transaction_data.get('cash_flow'),
            transaction_data.get('commission')
        )

        if transaction_tuple in existing_transactions:
            return None, 'duplicate'

        logger.debug(f"Transaction processed successfully {transaction_type}, {transaction_data}")

        return transaction_data, 'new'
    except ValueError as e:
        logger.error(f"ValueError in process_transaction_row {str(e)}, {row}")
        return None, 'error'
    except Exception as e:
        logger.error(f"Unexpected error in process_transaction_row {str(e)}, {row}")
        return None, 'error'

async def parse_charles_stanley_transactions(file_path, currency, broker_id, user_id, consumer):
    """
    Refactored to ONLY yield messages without awaiting confirmations.
    """
    yield {
        'status': 'progress',
        'message': 'Opening file and preparing for import',
        'progress': 0
    }
    logger.debug("Yielded progress message: Opening file and preparing for import")

    try:
        df = read_excel_file(file_path)
        total_rows = len(df)
        logger.debug(f"File read successfully. Total rows: {total_rows}")
    except ValueError as e:
        yield {'error': str(e)}
        return

    try:
        investor = await get_investor(user_id)
        broker = await get_broker(broker_id)
        existing_transactions = await get_existing_transactions(investor, broker)
        logger.debug("Retrieved investor, broker, and existing transactions")
    except Exception as e:
        logger.error(f"Error getting investor or broker: {str(e)}")
        yield {'error': f'An unexpected error occurred while getting investor or broker: {str(e)}'}
        return

    BATCH_SIZE = 1
    security_cache = defaultdict(lambda: None)
    total_transactions = 0
    imported_transactions = 0
    skipped_count = 0
    duplicate_count = 0
    transactions_to_create = []

    # def serialize_transaction_data(data):
    #     serialized = {}
    #     for key, value in data.items():
    #         if isinstance(value, (CustomUser, Brokers, Assets)):
    #             serialized[key] = model_to_dict(value, fields=['id', 'name'])
    #         elif isinstance(value, (datetime.date, datetime.datetime)):
    #             serialized[key] = value.isoformat()
    #         elif isinstance(value, Decimal):
    #             serialized[key] = float(value)
    #         else:
    #             serialized[key] = value
    #     return serialized

    for index, row in df.iterrows():
        if consumer.stop_event.is_set():
            logger.debug("Stop event detected. Breaking loop.")
            break

        try:
            total_transactions += 1
            transaction_data, status = await process_transaction_row(
                row, investor, broker, currency, security_cache, existing_transactions
            )

            if status == 'new':
                yield {
                    'status': 'transaction_confirmation',
                    # 'data': serialize_transaction_data(transaction_data),
                    'data': transaction_data,
                    'index': index + 1,
                    'total': total_rows
                }
                logger.debug("Yielded transaction_confirmation for row %d", index + 1)
                # No awaiting here; confirmation is handled externally
            elif status == 'skipped':
                skipped_count += 1
                logger.debug("Transaction skipped for row %d", index + 1)
            elif status == 'duplicate':
                duplicate_count += 1
                logger.debug("Transaction duplicate for row %d", index + 1)
            elif status == 'mapping_required':
                yield {
                    'status': 'security_mapping',
                    'security': model_to_dict(transaction_data['security'], fields=['id', 'name']),
                    'best_match': transaction_data.get('best_match', None)
                }
                logger.debug("Yielded security_mapping for row %d", index + 1)
                # Similarly, mapping is handled externally
            else:
                logger.warning("Unknown status '%s' for row %d", status, index + 1)

            if (index + 1) % BATCH_SIZE == 0 or index == total_rows - 1:
                progress = min(((index + 1) / total_rows) * 100, 100)
                yield {
                    'status': 'progress', 
                    'message': f'Processing transaction {index + 1} of {total_rows}', 
                    'progress': progress,
                    'current': index + 1,
                    'total': total_rows
                }
                logger.debug("Yielded progress update: %d%%", progress)

        except InvalidOperation as e:
            logger.error(f"InvalidOperation in process_transaction_row: {str(e)}")
            yield {'error': f'An invalid operation occurred while processing a transaction: {str(e)}'}
        except Exception as e:
            logger.error(f"Error processing transaction: {str(e)}")
            yield {'error': f'An unexpected error occurred while processing a transaction: {str(e)}'}

    if not consumer.stop_event.is_set():
        yield {
            'status': 'complete',
            'data': {
                'totalTransactions': total_transactions,
                'importedTransactions': imported_transactions,
                'skippedTransactions': skipped_count,
                'duplicateTransactions': duplicate_count,
                'transactionsToCreate': [model_to_dict(t) for t in transactions_to_create]
            },
            'message': 'Import process completed'
        }
        logger.debug("Yielded completion of import process")
