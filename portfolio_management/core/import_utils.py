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
from channels.db import database_sync_to_async
from django.forms.models import model_to_dict

logger = structlog.get_logger(__name__)

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
    
    logger.info("Processing transaction row", 
                investor_id=investor.id, 
                broker_id=broker.id, 
                currency=currency)
                
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

        if description in SKIP_DESCRIPTIONS:
            return None, 'skipped'

        if description in COMMISSION_DESCRIPTIONS:
            transaction_type = 'COMMISSION'
        elif description in CASH_IN_DESCRIPTIONS:
            transaction_type = 'DEPOSIT'
        elif 'Dividend' in description:
            transaction_type = 'DIVIDEND'
        elif debit > 0:
            transaction_type = 'BUY'
        elif credit > 0:
            transaction_type = 'SELL'
        else:
            return None, 'skipped'

        if isinstance(stock_description, str):
            security, best_match = await find_security(stock_description, investor, broker, security_cache)
        else:
            security, best_match = None, None

        if security is None and transaction_type not in ['COMMISSION', 'DEPOSIT']:
            return {'status': 'security_mapping', 'security': stock_description, 'best_match': best_match}, 'mapping_required'

        transaction_data = {
            'investor': investor,
            'broker': broker,
            'security': security,
            'currency': currency,
            'type': transaction_type,
            'date': transaction_date,
        }

        if transaction_type in ['BUY', 'SELL']:
            quantity = abs(Decimal(str(debit if debit > 0 else credit)) / price)
            transaction_data.update({
                'quantity': quantity,
                'price': price,
            })
        elif transaction_type in ['COMMISSION', 'DEPOSIT', 'DIVIDEND']:
            transaction_data['cash_flow'] = credit - debit

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

        logger.debug("Transaction processed successfully", 
                        transaction_type=transaction_type, 
                        security_id=security.id if security else None)

        return transaction_data, 'new'
    except ValueError as e:
        logger.error("ValueError in process_transaction_row", 
                     error=str(e), 
                     row=row)
        return None, 'error'
    except Exception as e:
        logger.error("Unexpected error in process_transaction_row", 
                     error=str(e), 
                     exc_info=True, 
                     row=row)
        return None, 'error'

async def parse_charles_stanley_transactions(file_path, currency, broker_id, user_id, consumer):
    """
    Modified to accept the consumer instance to communicate with.
    """
    yield {'status': 'progress', 'message': 'Opening file and preparing for import', 'progress': 0}
    
    try:
        df = read_excel_file(file_path)
        total_rows = len(df)
    except ValueError as e:
        yield {'error': str(e)}
        return

    BATCH_SIZE = 1
    security_cache = defaultdict(lambda: None)
    try:
        investor = await get_investor(user_id)
        broker = await get_broker(broker_id)
        existing_transactions = await get_existing_transactions(investor, broker)
    except Exception as e:
        logger.error(f"Error getting investor or broker: {str(e)}")
        yield {'error': f'An unexpected error occurred while getting investor or broker: {str(e)}'}
        return

    skipped_count = 0
    total_transactions = 0
    imported_transactions = 0
    transactions_to_create = []

    def serialize_transaction_data(data):
        serialized = {}
        for key, value in data.items():
            if isinstance(value, (CustomUser, Brokers, Assets)):
                serialized[key] = model_to_dict(value, fields=['id', 'name'])
            elif isinstance(value, (datetime.date, datetime.datetime)):
                serialized[key] = value.isoformat()
            elif isinstance(value, Decimal):
                serialized[key] = float(value)
            else:
                serialized[key] = value
        return serialized

    for index, row in df.iterrows():
        if consumer.stop_event.is_set():
            break
        try:
            total_transactions += 1
            transaction_data, status = await process_transaction_row(row, investor, broker, currency, security_cache, existing_transactions)

            if status == 'new':
                yield {
                    'status': 'transaction_confirmation',
                    'data': serialize_transaction_data(transaction_data),
                    'index': index + 1,
                    'total': total_rows
                }
                confirmation = await consumer.confirmation_events.get()

                if confirmation:
                    transactions_to_create.append(transaction_data)
                    imported_transactions += 1
                else:
                    skipped_count += 1
            elif status == 'skipped' or status == 'duplicate':
                skipped_count += 1
            elif status == 'mapping_required':
                yield {
                    'status': 'security_mapping',
                    'security': model_to_dict(transaction_data['security'], fields=['id', 'name']),
                    'best_match': transaction_data.get('best_match', None)
                }
                # Wait for user to map the security
                security_id = await consumer.mapping_events.get()
                
                if security_id:
                    transaction_data['security'] = security_id
                    transactions_to_create.append(transaction_data)
                    imported_transactions += 1
                else:
                    skipped_count += 1

        except InvalidOperation as e:
            logger.error(f"InvalidOperation in process_transaction_row: {str(e)}")
            yield {'error': f'An invalid operation occurred while processing a transaction: {str(e)}'}
        except Exception as e:
            logger.error(f"Error processing transaction: {str(e)}")
            yield {'error': f'An unexpected error occurred while processing a transaction: {str(e)}'}

        if (index + 1) % BATCH_SIZE == 0 or index == total_rows - 1:
            progress = min((index + 1) / total_rows * 100, 100)
            yield {
                'status': 'progress', 
                'message': f'Processing transaction {index + 1} of {total_rows}', 
                'progress': progress,
                'current': index + 1,
                'total': total_rows
            }

    if not consumer.stop_event.is_set():
        yield {'status': 'complete', 'data': {
            'totalTransactions': total_transactions,
            'importedTransactions': imported_transactions,
            'skippedTransactions': skipped_count,
            'transactionsToCreate': transactions_to_create
        }}
