import datetime
from functools import lru_cache
from io import StringIO
import json
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
import requests
from common.models import Brokers, Assets, Prices, Transactions
from decimal import Decimal, InvalidOperation
import pandas as pd
from django.core.files.storage import default_storage
from collections import defaultdict
from fuzzywuzzy import process
import structlog
import logging
from channels.db import database_sync_to_async
from django.forms.models import model_to_dict
from django.db.models import Q
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from fake_useragent import UserAgent
from requests.exceptions import RequestException
import yfinance as yf

from constants import MUTUAL_FUNDS_IN_PENCES, TRANSACTION_TYPE_BROKER_COMMISSION, TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_CASH_OUT, TRANSACTION_TYPE_DIVIDEND, TRANSACTION_TYPE_INTEREST_INCOME, TRANSACTION_TYPE_SELL

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
def get_security(security_id):
    try:
        return Assets.objects.get(id=security_id)
    except Assets.DoesNotExist:
        logger.error(f"Security with id {security_id} does not exist")
        return None

@database_sync_to_async
def transaction_exists(transaction_data):
    query = Q()
    required_fields = ['investor', 'broker', 'date', 'currency', 'type', 'security']
    optional_fields = ['quantity', 'price', 'cash_flow', 'commission']

    # Add required fields to the query
    for field in required_fields:
        if field not in transaction_data:
            raise ValueError(f"Required field '{field}' is missing from transaction_data")
        query &= Q(**{field: transaction_data[field]})

    # Add optional fields to the query if they exist
    for field in optional_fields:
        if field in transaction_data and transaction_data[field] is not None:
            query &= Q(**{field: transaction_data[field]})

    return Transactions.objects.filter(query).exists()

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
def _find_security(stock_description, investor, broker):
    
    securities = list(Assets.objects.filter(investor=investor, brokers=broker))
    
    # Check for exact match
    security = next((s for s in securities if s.name == stock_description), None)

    # If no exact match, look for best match
    security_names = [security.name for security in securities]
    best_match = process.extractOne(stock_description, security_names)
    
    if best_match:
        match_name, match_score = best_match
        if match_score == 100:  # Perfect match found
            security = next(s for s in securities if s.name == match_name)
            return security, None
        else:  # Close match found, but not perfect
            match_id = next(s.id for s in securities if s.name == match_name)
            return None, {'match_name': match_name, 'match_score': match_score, 'match_id': match_id}
    
    # No match found
    return None, None

async def _process_transaction_row(row, investor, broker, currency):

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
        CASH_OUT_DESCRIPTIONS = { "BACS P'MNT"}
        ### Try to use regex for the below two. Relevant for Gross interest and Tax Credit
        INTEREST_INCOME_DESCRIPTIONS = {'Gross interest'}
        DIVIDEND_DESCRIPTIONS = {'Dividend', 'Equalisation', 'Tax Credit', 'Tax Credit*'}

        if description in SKIP_DESCRIPTIONS:
            return None, 'skipped'
        
        security, best_match = None, None

        if description in COMMISSION_DESCRIPTIONS:
            transaction_type = TRANSACTION_TYPE_BROKER_COMMISSION
        elif any(keyword in description for keyword in CASH_IN_DESCRIPTIONS):
            transaction_type = TRANSACTION_TYPE_CASH_IN
        elif any(keyword in description for keyword in CASH_OUT_DESCRIPTIONS):
            transaction_type = TRANSACTION_TYPE_CASH_OUT
        elif any(keyword in description for keyword in DIVIDEND_DESCRIPTIONS):
            transaction_type = TRANSACTION_TYPE_DIVIDEND
            security, best_match = await _find_security(stock_description, investor, broker)
        elif any(keyword in description for keyword in INTEREST_INCOME_DESCRIPTIONS):
            transaction_type = TRANSACTION_TYPE_INTEREST_INCOME
        elif pd.notna(stock_description):
            security, best_match = await _find_security(stock_description, investor, broker)
            if debit > 0:
                transaction_type = TRANSACTION_TYPE_BUY
            elif credit > 0:
                transaction_type = TRANSACTION_TYPE_SELL
        else:
            return None, 'skipped'

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
                quantity = Decimal(str(debit)) / price
            else:
                quantity = -Decimal(str(credit)) / price
            transaction_data.update({
                'quantity': round(quantity, quantity_decimal_places),
                'price': round(Decimal(str(price)), price_decimal_places),
            })
        elif transaction_type in [TRANSACTION_TYPE_INTEREST_INCOME, TRANSACTION_TYPE_DIVIDEND]:
            transaction_data['cash_flow'] = Decimal(str(credit))
        elif transaction_type == TRANSACTION_TYPE_CASH_IN:
            transaction_data['cash_flow'] = Decimal(str(credit))
        elif transaction_type == TRANSACTION_TYPE_CASH_OUT:
            transaction_data['cash_flow'] = -Decimal(str(debit))
        elif transaction_type == TRANSACTION_TYPE_BROKER_COMMISSION:
            transaction_data['commission'] = -Decimal(str(debit))

        NON_SECURITY_RELATED_TRANSACTION_TYPES = [
            TRANSACTION_TYPE_INTEREST_INCOME,
            TRANSACTION_TYPE_CASH_IN,
            TRANSACTION_TYPE_CASH_OUT,
            TRANSACTION_TYPE_BROKER_COMMISSION
        ]

        exists = await transaction_exists(transaction_data)
        if exists:
            logger.debug(f"Transaction already exists. Duplicate: {transaction_data}")
            return None, 'duplicate'
        
        if security is None and transaction_type not in NON_SECURITY_RELATED_TRANSACTION_TYPES:
            mapping_details = {
                'stock_description': stock_description,
                'best_match': best_match
            }
            logger.debug(f"Mapping required for transaction: {transaction_data}")
            return {'mapping_details': mapping_details, 'transaction_details': transaction_data }, 'mapping_required'

        logger.debug(f"Transaction processed successfully {transaction_type}, {transaction_data}")

        return transaction_data, 'new'
    except ValueError as e:
        logger.error(f"ValueError in process_transaction_row {str(e)}, {row}")
        return None, 'error'
    except Exception as e:
        logger.error(f"Unexpected error in process_transaction_row {str(e)}, {row}")
        return None, 'error'

async def parse_charles_stanley_transactions(file_path, currency, broker_id, user_id, confirm_every):
    """
    Refactored to ONLY yield messages without awaiting confirmations.
    """
    yield {
        'status': 'initialization',
        'message': 'Opening and reading file',
    }
    logger.debug("Yielded progress message: Opening file and preparing for import")

    try:
        df = read_excel_file(file_path)
        if df.empty:
            raise ValueError("The Excel file is empty or could not be read.")
        df = df[df['Date'].notna()]
        total_rows = df.shape[0]
        logger.debug(f"File read successfully. Total rows: {total_rows}")
        yield {
            'status': 'initialization',
            'message': 'File read successfully. Preparing for import',
            'total_to_update': int(total_rows)
        }
    except Exception as e:
        error_message = f"Error reading Excel file: {str(e)}"
        logger.error(error_message)
        yield {'error': error_message}
        return

    try:
        investor = await get_investor(user_id)
        broker = await get_broker(broker_id)
        logger.debug("Retrieved investor and broker")
    except Exception as e:
        logger.error(f"Error getting investor or broker: {str(e)}")
        yield {'error': f'An unexpected error occurred while getting investor or broker: {str(e)}'}
        return

    BATCH_SIZE = 1
    total_transactions = 0
    # imported_transactions = 0
    skipped_count = 0
    duplicate_count = 0
    import_errors = 0

    for index, row in df.iterrows():
        # if consumer.stop_event.is_set():
        #     logger.debug("Stop event detected. Breaking loop.")
        #     break

        try:
            total_transactions += 1
            transaction_data, status = await _process_transaction_row(
                row, investor, broker, currency
            )
            
            logger.debug(f"Row {index + 1} processed. Status: {status}")
            logger.debug(f"Transaction data: {transaction_data}")

            if (index + 1) % BATCH_SIZE == 0 or index == total_rows - 1:
                progress = min(((index + 1) / total_rows) * 100, 100)
                yield {
                    'status': 'progress', 
                    'message': f'Processing transaction {index + 1} of {total_rows}', 
                    'progress': progress,
                    'current': index + 1,
                }

            if status == 'new':
                if confirm_every:
                    yield {
                        'status': 'transaction_confirmation',
                        'data': transaction_data,
                    }
                    logger.debug("Yielded transaction_confirmation for row %d", index + 1)
                else:
                    yield {
                        'status': 'add_transaction',
                        'data': transaction_data,
                    }
            elif status == 'mapping_required':
                # Always yield for security mapping, regardless of confirm_every
                yield {
                    'status': 'security_mapping',
                    'mapping_data': transaction_data.get('mapping_details'),
                    'transaction_data': transaction_data.get('transaction_details')
                }
                logger.debug("Yielded security_mapping for row %d", index + 1)
            elif status == 'skipped':
                skipped_count += 1
                logger.debug("Transaction skipped for row %d", index + 1)
            elif status == 'duplicate':
                duplicate_count += 1
                logger.debug("Transaction duplicate for row %d", index + 1)
            else:
                logger.warning("Unknown status '%s' for row %d", status, index + 1)

        except InvalidOperation as e:
            logger.error(f"InvalidOperation in process_transaction_row: {str(e)}")
            yield {'error': f'An invalid operation occurred while processing a transaction: {str(e)}'}
        except Exception as e:
            logger.error(f"Error processing transaction at row {index + 1}: {str(e)}")
            logger.error(f"Row data: {row}")
            import_errors += 1
            yield {'error': f'An unexpected error occurred while processing a transaction at row {index + 1}: {str(e)}'}

    yield {
        'status': 'complete',
        'data': {
            'totalTransactions': total_transactions,
            'importedTransactions': 0, #Filled in the consumer
            'skippedTransactions': skipped_count,
            'duplicateTransactions': duplicate_count,
            'importErrors': import_errors
        },
    }
    logger.debug("Yielded completion of import process")

def generate_dates_for_price_import(start, end, frequency):
    dates = []
    if frequency == 'monthly':
        current = start.replace(day=1) + relativedelta(months=1) - timedelta(days=1)  # Last day of the start month
    elif frequency == 'quarterly':
        quarter_end_month = 3 * ((start.month - 1) // 3 + 1)
        current = date(start.year, quarter_end_month, 1) + relativedelta(months=1) - timedelta(days=1)
    elif frequency == 'annually':
        current = date(start.year, 12, 31)
    else:
        raise ValueError(f"Unsupported frequency: {frequency}")
    
    while current <= end:
        dates.append(current)
        if frequency == 'monthly':
            current = (current + relativedelta(months=1)).replace(day=1) + relativedelta(months=1) - timedelta(days=1)
        elif frequency == 'quarterly':
            current = (current + relativedelta(months=3)).replace(day=1) + relativedelta(months=1) - timedelta(days=1)
        elif frequency == 'annually':
            current = date(current.year + 1, 12, 31)
    return dates

def import_security_prices_from_ft(security, dates):
    url = security.update_link
    user_agent = UserAgent().random
    headers = {'User-Agent': user_agent}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"Error fetching data for {security.name}: {str(e)}"
        }
        return

    soup = BeautifulSoup(response.content, "html.parser")

    elem = soup.find('section', {'class': 'mod-tearsheet-add-to-watchlist'})
    if elem and 'data-mod-config' in elem.attrs:
        data = json.loads(elem['data-mod-config'])
        xid = data['xid']

        for date in dates:
            result = {
                "security_name": security.name,
                "date": date.strftime('%Y-%m-%d'),
                "status": "skipped"
            }

            # Check if a price already exists for this date
            if Prices.objects.filter(security=security, date=date).exists():
                yield result
                continue

            end_date = date.strftime('%Y/%m/%d')
            start_date = (date - timedelta(days=7)).strftime('%Y/%m/%d')

            try:
                r = requests.get(
                    f'https://markets.ft.com/data/equities/ajax/get-historical-prices?startDate={start_date}&endDate={end_date}&symbol={xid}',
                    headers=headers,
                    timeout=10
                )
                r.raise_for_status()
                data = r.json()

                df = pd.read_html(StringIO('<table>' + data['html'] + '</table>'))[0]
                df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
                df['Date'] = pd.to_datetime(df['Date'].apply(lambda x: x.split(',')[-2][1:] + x.split(',')[-1]))

                # Convert 'date' to pandas Timestamp for comparison
                date_as_timestamp = pd.Timestamp(date)

                df = df[df['Date'] <= date_as_timestamp]

                if not df.empty:
                    latest_price = df.iloc[0]['Close']
                    if security.name in MUTUAL_FUNDS_IN_PENCES:
                        latest_price = latest_price / 100
                    Prices.objects.create(security=security, date=date, price=latest_price)
                    result["status"] = "updated"
                else:
                    result["status"] = "error"
                    result["message"] = f"No data found for {date.strftime('%Y-%m-%d')}"
            except Exception as e:
                result["status"] = "error"
                result["message"] = f"Error processing data for {security.name}: {str(e)}"

            yield result

    else:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"No data found for {security.name}"
        }

def import_security_prices_from_yahoo(security, dates):
    if not security.yahoo_symbol:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"No Yahoo Finance symbol specified for {security.name}"
        }
        return

    ticker = yf.Ticker(security.yahoo_symbol)

    for date in dates:
        result = {
            "security_name": security.name,
            "date": date.strftime('%Y-%m-%d'),
            "status": "skipped"
        }

        # Check if a price already exists for this date
        if Prices.objects.filter(security=security, date=date).exists():
            yield result
            continue

        end_date = (date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (date - pd.Timedelta(days=6)).strftime('%Y-%m-%d')

        try:
            # Set auto_adjust to False to get unadjusted close prices
            history = ticker.history(start=start_date, end=end_date, auto_adjust=False)

            if not history.empty:
                # Use 'Close' for unadjusted close price
                latest_price = history.iloc[-1]['Close']
                Prices.objects.create(security=security, date=date, price=latest_price)
                result["status"] = "updated"
            else:
                result["status"] = "error"
                result["message"] = f"No data found for {date.strftime('%Y-%m-%d')}"
        except RequestException as e:
            logger.error(f"Network error while fetching data for {security.name}: {str(e)}")
            result["status"] = "error"
            result["message"] = f"Network error: {str(e)}"
        except yf.YFinanceException as e:
            logger.error(f"YFinance error for {security.name}: {str(e)}")
            result["status"] = "error"
            result["message"] = f"YFinance error: {str(e)}"
        except pd.errors.EmptyDataError:
            logger.error(f"Empty data received for {security.name}")
            result["status"] = "error"
            result["message"] = "Empty data received from Yahoo Finance"
        except Exception as e:
            logger.exception(f"Unexpected error processing data for {security.name}")
            result["status"] = "error"
            result["message"] = f"Unexpected error: {str(e)}"

        yield result