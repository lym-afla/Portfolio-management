from io import StringIO
import json
from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
import requests
from common.models import BrokerAccounts, Assets, Prices, Transactions
from decimal import Decimal, InvalidOperation
import pandas as pd
from django.core.files.storage import default_storage
from fuzzywuzzy import process
import logging
from channels.db import database_sync_to_async
from django.db.models import Q
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from fake_useragent import UserAgent
import yfinance as yf
import aiohttp
import asyncio

from constants import MUTUAL_FUNDS_IN_PENCES, TRANSACTION_TYPE_BROKER_COMMISSION, TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_CASH_OUT, TRANSACTION_TYPE_DIVIDEND, TRANSACTION_TYPE_INTEREST_INCOME, TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_TAX

# logger = structlog.get_logger(__name__)
logger = logging.getLogger(__name__)

CustomUser = get_user_model()

@database_sync_to_async
def get_investor(investor_id):
    return CustomUser.objects.get(id=investor_id)

@database_sync_to_async
def get_broker_account(account_id):
    return BrokerAccounts.objects.get(id=account_id)

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
    required_fields = ['investor', 'broker_account', 'date', 'currency', 'type']
    optional_fields = ['security', 'quantity', 'price', 'cash_flow', 'commission']

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
def _find_security(stock_description, investor, broker_account):
    
    securities = list(Assets.objects.filter(investors=investor, broker_accounts=broker_account))
    
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

async def _process_transaction_row(row, investor, broker_account, currency):

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
        COMMISSION_DESCRIPTIONS = {'Funds Platform Fee',
                                   'Govt Flat Rate Int Charge',
                                   'Platform Charge',
                                   'Stocks & Shares Custody Fee',
                                   'Stocks & Shares Platform Fee'
                                   }
        CASH_IN_DESCRIPTIONS = {'Stocks & Shares Subs',
                                'ISA Subscription',
                                'Sage Pay Debit Card',
                                'DIRECT CREDIT',
                                'WIRED'
                                }
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
            security, best_match = await _find_security(stock_description, investor, broker_account)
        elif any(keyword in description for keyword in INTEREST_INCOME_DESCRIPTIONS):
            transaction_type = TRANSACTION_TYPE_INTEREST_INCOME
        elif pd.notna(stock_description):
            security, best_match = await _find_security(stock_description, investor, broker_account)
            if debit > 0:
                transaction_type = TRANSACTION_TYPE_BUY
            elif credit > 0:
                transaction_type = TRANSACTION_TYPE_SELL
        else:
            return None, 'skipped'

        transaction_data = {
            'investor': investor,
            'broker_account': broker_account,
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

async def parse_charles_stanley_transactions(file_path, currency, broker_account_id, user_id, confirm_every):
    """
    Refactored to ONLY yield messages without awaiting confirmations.
    Parse Charles Stanley transaction file. 
    
    Args:
        file_path: Path to the transaction file
        currency: Transaction currency
        broker_account_id: ID of the broker account
        user_id: ID of the user
        confirm_every: Whether to confirm each transaction
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
        broker_account = await get_broker_account(broker_account_id)
        logger.debug("Retrieved investor and broker account")
    except Exception as e:
        logger.error(f"Error getting investor or broker account: {str(e)}")
        yield {'error': f'An unexpected error occurred while getting investor or broker account: {str(e)}'}
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
                row, investor, broker_account, currency
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
    if frequency == 'daily':
        current = start
        while current <= end:
            if current.weekday() < 5:  # Monday is 0, Friday is 4
                dates.append(current)
            current += timedelta(days=1)
    elif frequency == 'weekly':
        # Find the next Friday
        days_until_friday = (4 - start.weekday()) % 7
        current = start + timedelta(days=days_until_friday)
        if current <= start:
            current += timedelta(days=7)  # Move to the next Friday if we're already on or past Friday
        while current <= end:
            dates.append(current)
            current += timedelta(days=7)
    elif frequency == 'monthly':
        current = start.replace(day=1) + relativedelta(months=1) - timedelta(days=1)  # Last day of the start month
        while current <= end:
            dates.append(current)
            current = (current + relativedelta(months=1)).replace(day=1) + relativedelta(months=1) - timedelta(days=1)
    elif frequency == 'quarterly':
        quarter_end_month = 3 * ((start.month - 1) // 3 + 1)
        current = date(start.year, quarter_end_month, 1) + relativedelta(months=1) - timedelta(days=1)
        while current <= end:
            dates.append(current)
            current = (current + relativedelta(months=3)).replace(day=1) + relativedelta(months=1) - timedelta(days=1)
    elif frequency == 'yearly':
        current = date(start.year, 12, 31)
        while current <= end:
            dates.append(current)
            current = date(current.year + 1, 12, 31)
    else:
        raise ValueError(f"Unsupported frequency: {frequency}")
    
    return dates

async def import_security_prices_from_ft(security, dates):
    url = security.update_link
    user_agent = UserAgent().random
    headers = {'User-Agent': user_agent}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                response.raise_for_status()
                content = await response.text()
        except aiohttp.ClientError as e:
            yield {
                "security_name": security.name,
                "status": "error",
                "message": f"Error fetching data for {security.name}: {str(e)}"
            }
            return

        soup = BeautifulSoup(content, "html.parser")

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
                price_exists_func = database_sync_to_async(Prices.objects.filter(security=security, date=date).exists)
                price_exists = await price_exists_func()
                if price_exists:
                    yield result
                    continue

                end_date = date.strftime('%Y/%m/%d')
                start_date = (date - timedelta(days=7)).strftime('%Y/%m/%d')

                try:
                    async with session.get(
                        f'https://markets.ft.com/data/equities/ajax/get-historical-prices?startDate={start_date}&endDate={end_date}&symbol={xid}',
                        headers=headers,
                        timeout=10
                    ) as r:
                        r.raise_for_status()
                        data = await r.json()

                    df = pd.read_html(StringIO('<table>' + data['html'] + '</table>'))[0]
                    df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
                    df['Date'] = pd.to_datetime(df['Date'].apply(lambda x: x.split(',')[-2][1:] + x.split(',')[-1]))

                    date_as_timestamp = pd.Timestamp(date)
                    df = df[df['Date'] <= date_as_timestamp]

                    if not df.empty:
                        latest_price = df.iloc[0]['Close']
                        if security.name in MUTUAL_FUNDS_IN_PENCES:
                            latest_price = latest_price / 100
                        create_price_func = database_sync_to_async(Prices.objects.create)
                        await create_price_func(security=security, date=date, price=latest_price)
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

async def import_security_prices_from_yahoo(security, dates):
    if not security.yahoo_symbol:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"No Yahoo Finance symbol specified for {security.name}"
        }
        return

    for date in dates:
        result = {
            "security_name": security.name,
            "date": date.strftime('%Y-%m-%d'),
            "status": "skipped"
        }

        # Check if a price already exists for this date
        price_exists_func = database_sync_to_async(Prices.objects.filter(security=security, date=date).exists)
        price_exists = await price_exists_func()
        if price_exists:
            yield result
            continue

        end_date = (date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (date - pd.Timedelta(days=6)).strftime('%Y-%m-%d')

        try:
            # Use run_in_executor to run yfinance operations in a separate thread
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(None, yf.Ticker, security.yahoo_symbol)
            # Set auto_adjust to False to get unadjusted close prices
            history = await loop.run_in_executor(None, lambda: ticker.history(start=start_date, end=end_date, auto_adjust=False))

            if not history.empty:
                # Use 'Close' for unadjusted close price
                latest_price = history['Close'].iloc[-1]
                create_price_func = database_sync_to_async(Prices.objects.create)
                await create_price_func(security=security, date=date, price=latest_price)
                result["status"] = "updated"
            else:
                result["status"] = "error"
                result["message"] = f"No data found for {date.strftime('%Y-%m-%d')}"
        except Exception as e:
            logger.exception(f"Unexpected error processing data for {security.name}")
            result["status"] = "error"
            result["message"] = f"Unexpected error: {str(e)}"

        yield result

async def import_security_prices_from_micex(security, dates):
    if not security.secid:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"No MICEX symbol specified for {security.name}"
        }
        return
    
    for date in dates:
        result = {
            "security_name": security.name,
            "date": date.strftime('%Y-%m-%d'),
            "status": "skipped"
        }

        # Check if price already exists
        price_exists_func = database_sync_to_async(
            Prices.objects.filter(security=security, date=date).exists
        )
        price_exists = await price_exists_func()
        
        if price_exists:
            yield result
            continue

        # Get wide enough interval to fetch data
        target_date = pd.Timestamp(date)
        end_date = (target_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')  # Include next day
        start_date = (target_date - pd.Timedelta(days=7)).strftime('%Y-%m-%d')

        # Constants for MICEX API
        selected_engine = 'stock'
        selected_market = 'shares'
        selected_board = 'TQBR'

        url = (
            f'https://iss.moex.com/iss/history/engines/{selected_engine}/markets/{selected_market}/boards/'
            f'{selected_board}/securities/{security.secid}.json'
            f'?from={start_date}&till={end_date}'
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        error_msg = f"MOEX API error: {response.status}"
                        yield {
                            "security_name": security.name,
                            "date": date.strftime('%Y-%m-%d'),
                            "status": "error",
                            "message": error_msg
                        }
                        continue

                    data = await response.json()

            if 'history' in data and data['history']['data']:
                df = pd.DataFrame(
                    data['history']['data'],
                    columns=data['history']['columns']
                )
                # Convert date strings to datetime
                df['TRADEDATE'] = pd.to_datetime(df['TRADEDATE'])
                df.set_index('TRADEDATE', inplace=True)
                df = df.sort_index()  # Ensure chronological order

                if not df.empty:
                    # Find the closest trading day (preference to previous days)
                    closest_date = None
                    
                    # First try to find exact date
                    if target_date in df.index:
                        closest_date = target_date
                    else:
                        # Find the closest previous trading day
                        prev_dates = df.index[df.index <= target_date]
                        if not prev_dates.empty:
                            closest_date = prev_dates[-1]
                    
                    if closest_date is not None:
                        price = df.loc[closest_date, 'CLOSE']
                        if pd.notna(price):
                            create_price_func = database_sync_to_async(
                                Prices.objects.create
                            )
                            await create_price_func(
                                security=security,
                                date=date,  # Use original date
                                price=float(price)
                            )
                            result.update({
                                "status": "updated",
                                "message": f"Used price from {closest_date.strftime('%Y-%m-%d')}"
                                if closest_date != target_date else None
                            })
                        else:
                            result.update({
                                "status": "error",
                                "message": "No closing price available for the closest date"
                            })
                    else:
                        result.update({
                            "status": "error",
                            "message": "No suitable trading day found in the date range"
                        })
                else:
                    result.update({
                        "status": "error",
                        "message": "No data available in the date range"
                    })
            else:
                result.update({
                    "status": "error",
                    "message": "No data available from MOEX"
                })

            yield result

        except Exception as e:
            logger.exception(f"Error fetching MOEX data for {security.name}")
            yield {
                "security_name": security.name,
                "date": date.strftime('%Y-%m-%d'),
                "status": "error",
                "message": f"Unexpected error: {str(e)}"
            }


async def _process_galaxy_transaction(user, broker_account, date, currency, transaction_type, cash_flow=None, commission=None):
    """
    Process a Galaxy transaction.
    
    Args:
        user: User object
        broker_account: BrokerAccounts object
        date: Transaction date
        currency: Transaction currency
        transaction_type: Type of transaction
        cash_flow: Cash flow amount
        commission: Commission amount
    """
    transaction_data = {
        'investor': user,
        'broker_account': broker_account,
        'date': date,
        'type': transaction_type,
        'currency': currency,
        'cash_flow': round(Decimal(cash_flow), 2) if cash_flow is not None else None,
        'commission': round(Decimal(commission), 2) if commission is not None else None,
    }

    existing_transaction = await transaction_exists(transaction_data)
    if existing_transaction:
        return 'duplicate', transaction_data
    return 'new', transaction_data

async def parse_galaxy_broker_account_cash_flows(file_path, currency, broker_account, user, confirm_every):
    """
    Parse Galaxy broker account cash flows with async support and progress tracking.
    """
    yield {
        'status': 'initialization',
        'message': 'Opening and reading Galaxy cash flow file',
    }
    logger.debug("Yielded progress message: Opening Galaxy cash flow file")

    try:
        # Read the Excel file
        df = pd.read_excel(file_path, header=3)  # Line 4 has table headers
        if df.empty:
            raise ValueError("The Excel file is empty or could not be read.")
        df = df[df['Дата'].notna()]  # Filter out rows without dates
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

    BATCH_SIZE = 1
    total_transactions = 0
    skipped_count = 0
    duplicate_count = 0
    import_errors = 0

    # Iterate over each row in the DataFrame
    for index, row in df.iterrows():
        try:
            date = row['Дата'].strftime("%Y-%m-%d")
            transactions_to_process = []

            # Collect all transactions from the row
            if pd.notna(row['Инвестиции']):
                transaction_type = TRANSACTION_TYPE_CASH_IN if row['Инвестиции'] > 0 else TRANSACTION_TYPE_CASH_OUT
                transactions_to_process.append(('cash_flow', transaction_type, row['Инвестиции']))

            if pd.notna(row['Комиссия']):
                transactions_to_process.append(('commission', TRANSACTION_TYPE_BROKER_COMMISSION, row['Комиссия']))

            if 'Tax' in row and pd.notna(row['Tax']):
                transactions_to_process.append(('cash_flow', TRANSACTION_TYPE_TAX, row['Tax']))

            total_transactions += len(transactions_to_process)

            # Process each transaction
            for trans_type, trans_name, value in transactions_to_process:
                kwargs = {trans_type: value}
                status, transaction_data = await _process_galaxy_transaction(
                    user=user,
                    broker_account=broker_account,
                    date=date,
                    currency=currency,
                    transaction_type=trans_name,
                    **kwargs
                )

                if status == 'duplicate':
                    duplicate_count += 1
                    logger.debug(f"Duplicate {trans_type} transaction found for row {index + 1}")
                else:
                    if confirm_every:
                        yield {
                            'status': 'transaction_confirmation',
                            'data': transaction_data,
                        }
                    else:
                        yield {
                            'status': 'add_transaction',
                            'data': transaction_data,
                        }

            # Report progress
            if (index + 1) % BATCH_SIZE == 0 or index == total_rows - 1:
                progress = min(((index + 1) / total_rows) * 100, 100)
                yield {
                    'status': 'progress', 
                    'message': f'Processing row {index + 1} of {total_rows}', 
                    'progress': progress,
                    'current': index + 1,
                }

        except Exception as e:
            logger.error(f"Error processing row {index + 1}: {str(e)}")
            import_errors += 1
            yield {'error': f'An unexpected error occurred while processing row {index + 1}: {str(e)}'}

    # Final yield with import summary
    yield {
        'status': 'complete',
        'data': {
            'totalTransactions': total_transactions,
            'importedTransactions': 0,  # Will be filled in the consumer
            'skippedTransactions': skipped_count,
            'duplicateTransactions': duplicate_count,
            'importErrors': import_errors
        },
    }
    logger.debug("Yielded completion of Galaxy cash flow import process")

async def parse_galaxy_broker_account_security_transactions(file_path, currency, broker_account, user, confirm_every=False):
    """Async generator for parsing Galaxy broker account security transactions"""
    try:
        # Send initialization message
        yield {
            'status': 'initialization',
            # 'total_to_update': total_potential_transactions,
            'message': 'Starting Galaxy transactions import'
        }
        
        df = pd.read_excel(file_path, header=None)
        
        # Find transactions_start once
        transactions_start = None
        for i in range(len(df.columns)):
            if pd.notna(df.iloc[1, i]):
                date_row_index = df[df.iloc[:, i] == 'Дата'].index
                if date_row_index.size > 0:
                    transactions_start = date_row_index[0] + 1
                    break
        
        if transactions_start is None:
            yield {'error': 'Could not find transaction start row in the file'}
            return

        quantity_field = Transactions._meta.get_field('quantity')
        quantity_decimal_places = quantity_field.decimal_places
        price_field = Transactions._meta.get_field('price')
        price_decimal_places = price_field.decimal_places

        yield {
            'status': 'initialization',
            # 'total_to_update': total_potential_transactions,
            'message': 'Starting security processing'
        }

        # Process securities first
        valid_columns = None
        async for update in _process_galaxy_securities(df, user, broker_account):
            if update['status'] == 'security_processing_complete':
                valid_columns = update['valid_columns']
                yield {
                    'status': 'progress',
                    'message': 'Security processing complete',
                }
            else:
                yield update

        logger.debug(f"Valid columns: {valid_columns}")
            
        if not valid_columns:
            yield {
                'status': 'complete',
                'data': {
                    'totalTransactions': 0,
                    'importedTransactions': 0,
                    'skippedTransactions': 0,
                    'duplicateTransactions': 0,
                    'importErrors': 0,
                    'message': 'No valid securities found'
                }
            }
            return

        # Calculate total number of potential transactions
        total_columns = len(valid_columns)
        rows_per_security = len(df) - transactions_start
        total_potential_transactions = int(total_columns * rows_per_security)  # Convert to int for proper serialization

        yield {
            'status': 'initialization',
            'total_to_update': total_potential_transactions,
            'message': f'Starting processing {total_potential_transactions} transactions'
        }

        # Now process transactions only for valid columns
        processed = 0
        import_errors = 0
        duplicate_count = 0
        
        for i in valid_columns:
            security_name = df.iloc[1, i]
            isin = df.iloc[2, i]
            logger.debug(f"Processing transactions for security: {security_name} ({isin})")

            try:
                security = await database_sync_to_async(Assets.objects.get)(
                    name=security_name, 
                    ISIN=isin, 
                    investors=user,
                    broker_accounts=broker_account
                )
            except Assets.DoesNotExist:
                logger.debug(f"Security not found with all conditions, yielding creation request for {security_name}.")
                continue

            for row in range(transactions_start, len(df)):
                if pd.isna(df.iloc[row, i]):
                    processed += 1
                    continue

                try:
                    date = df.iloc[row, i].strftime("%Y-%m-%d")
                    price = round(Decimal(df.iloc[row, i + 1]), price_decimal_places) if not pd.isna(df.iloc[row, i + 1]) else None
                    quantity = round(Decimal(df.iloc[row, i + 2]), quantity_decimal_places) if not pd.isna(df.iloc[row, i + 2]) else None
                    dividend = round(Decimal(df.iloc[row, i + 3]), 2) if not pd.isna(df.iloc[row, i + 3]) else None
                    commission = round(Decimal(df.iloc[row, i + 4]), 2) if not pd.isna(df.iloc[row, i + 4]) else None

                    if quantity is None and dividend is None and commission is None:
                        processed += 1
                        logger.debug(f"Skipping empty row for security: {security_name}")
                        continue

                    transaction_type = None
                    if quantity is not None:
                        transaction_type = TRANSACTION_TYPE_BUY if quantity > 0 else TRANSACTION_TYPE_SELL
                    elif dividend is not None:
                        transaction_type = TRANSACTION_TYPE_DIVIDEND

                    transaction_data = {
                        'investor': user,
                        'broker_account': broker_account,
                        'security': security,  # Use actual security object
                        'date': date,
                        'type': transaction_type,
                        'currency': currency,
                        'price': price,
                        'quantity': quantity,
                        'cash_flow': dividend,
                        'commission': commission,
                    }

                    # Check for duplicates
                    exists = await transaction_exists(transaction_data)

                    processed += 1
                    yield {
                        'status': 'progress',
                        'current': processed,
                        'progress': (processed / total_potential_transactions) * 100,
                        'message': f'Processing transaction {processed}'
                    }

                    if exists:
                        duplicate_count += 1
                        continue

                    if confirm_every:
                        # processed += 1
                        yield {
                            'status': 'transaction_confirmation',
                            'data': transaction_data
                        }
                    else:
                        yield {
                            'status': 'add_transaction',
                            'data': transaction_data,
                        }

                except Exception as e:
                    import_errors += 1
                    yield {'error': f'Error processing transaction: {str(e)}'}
                    continue

        yield {
            'status': 'complete',
            'data': {
                'totalTransactions': total_potential_transactions,
                'importedTransactions': 0,
                'skippedTransactions': 0,
                'duplicateTransactions': duplicate_count,
                'importErrors': import_errors
            }
        }

    except Exception as e:
        logger.error(f"Error in parse_galaxy_broker_account_security_transactions: {str(e)}")
        yield {
            'status': 'critical_error',
            'message': f'Error during import: {str(e)}'
        }

async def _process_galaxy_securities(df, user, broker_account):
    """Process all securities in the Excel file before handling transactions."""
    security_columns = []
    
    logger.debug("Starting security processing phase")
    for i in range(len(df.columns)):
        if pd.notna(df.iloc[1, i]):
            security_name = df.iloc[1, i]
            isin = df.iloc[2, i]
            logger.debug(f"Processing security: {security_name} ({isin})")
            
            try:
                # First try to get security with all conditions
                security = await database_sync_to_async(Assets.objects.get)(
                    name=security_name, 
                    ISIN=isin, 
                    investors=user,
                    broker_accounts=broker_account
                )
                logger.debug(f"Found existing security with all relationships: {security}")
                security_columns.append(i)
                
                # Yield progress update
                yield {
                    'status': 'progress',
                    'message': f'Checked existing security: {security_name}',
                    # 'security': security_name
                }
                
            except Assets.DoesNotExist:
                try:
                    # Check if security exists without relationships
                    security = await database_sync_to_async(Assets.objects.get)(
                        name=security_name,
                        ISIN=isin
                    )
                    
                    # Add relationships
                    @database_sync_to_async
                    def add_relationships(security, user, broker_account):
                        security.investors.add(user)
                        security.broker_accounts.add(broker_account)
                        return security

                    await add_relationships(security, user, broker_account)
                    security_columns.append(i)
                    logger.debug(f"Added relationships for existing security: {security_name}")
                    
                    # Yield progress update
                    yield {
                        'status': 'progress',
                        'message': f'Added: {security_name}',
                        # 'security': security_name
                    }
                    
                except Assets.DoesNotExist:
                    # Try to create security using MICEX data
                    security = await create_security_from_micex(security_name, isin, user, broker_account)
                    if security:
                        security_columns.append(i)
                        yield {
                            'status': 'progress',
                            'message': f'Created new security: {security_name}',
                            # 'security': security_name
                        }
                    else:
                        yield {
                            'status': 'progress',
                            'message': f'Failed to create security: {security_name}',
                            # 'security': security_name,
                            # 'error': True
                        }
                        continue
    
    # Return list of valid column indices
    yield {
        'status': 'security_processing_complete',
        'valid_columns': security_columns,
        'message': f'Found {len(security_columns)} valid securities'
    }

async def create_security_from_micex(security_name, isin, user, broker_account):
    """Create a new security using MICEX API data"""
    try:
        # Constants for MICEX API
        selected_engine = 'stock'
        selected_market = 'shares'
        selected_board = 'TQBR'
        
        # First, get the securities list and find our security
        url = f'https://iss.moex.com/iss/engines/{selected_engine}/markets/{selected_market}/boards/{selected_board}/securities.json'
        response = requests.get(url)
        if response.status_code != 200:
            logger.error(f"Failed to fetch securities list from MICEX: {response.status_code}")
            return None
            
        data = response.json()
        securities_df = pd.DataFrame(data['securities']['data'], 
                                   columns=data['securities']['columns'])
        
        # Try to find the security by ISIN first (more reliable)
        security = securities_df[securities_df['ISIN'] == isin]
        if security.empty:
            # If not found by ISIN, try by name
            security = securities_df[securities_df['SECNAME'].str.contains(security_name, case=False, na=False)]
        
        if security.empty:
            logger.error(f"Security not found in MICEX: {security_name} ({isin})")
            return None
            
        # Get the first match if multiple found
        security = security.iloc[0]
        
        # Get detailed security info
        ticker = security['SECID']
        security_url = f'https://iss.moex.com/iss/engines/{selected_engine}/markets/{selected_market}/boards/{selected_board}/securities/{ticker}.json'
        detail_response = requests.get(security_url)
        if detail_response.status_code != 200:
            logger.error(f"Failed to fetch security details from MICEX: {detail_response.status_code}")
            return None
            
        detail_data = detail_response.json()
        
        # Create new asset
        @database_sync_to_async
        def create_asset():
            asset = Assets.objects.create(
                type='Stock',  # From ASSET_TYPE_CHOICES
                ISIN=isin,
                name=security_name,
                currency='RUB' if security['CURRENCYID'] == 'SUR' else security['CURRENCYID'],
                exposure='Equity',  # From EXPOSURE_CHOICES
                restricted=False,
                data_source='MICEX',
                secid = security['SECID']
            )
            # Add both relationships in one transaction
            asset.investors.add(user)
            asset.broker_accounts.add(broker_account)
            return asset
            
        asset = await create_asset()
        logger.info(f"Created new asset: {asset.name} ({asset.ISIN}) with user and broker account relationships")
        return asset
        
    except Exception as e:
        logger.error(f"Error creating security from MICEX: {str(e)}")
        return None