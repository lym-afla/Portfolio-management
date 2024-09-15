from collections import defaultdict
import pandas as pd
from decimal import Decimal, InvalidOperation
from fuzzywuzzy import process

from common.models import Assets, Brokers, Prices, Transactions
from users.models import CustomUser
from constants import TRANSACTION_TYPE_INTEREST_INCOME, TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_DIVIDEND, TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_BROKER_COMMISSION
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def parse_charles_stanley_transactions(file_path, currency, broker_id, investor_id):
    df = pd.read_excel(file_path, header=3, usecols=['Date', 'Description', 'Stock Description', 'Price', 'Debit', 'Credit'])
    total_rows = len(df)
    
    yield {'status': 'progress', 'message': 'Opening file', 'progress': 0}
    yield {'status': 'progress', 'message': 'Preparing for import', 'progress': 5}

    broker = Brokers.objects.get(id=broker_id)
    logger.debug(f"Investor ID in parse_charles_stanley_transactions: {investor_id}")
    try:
        investor = CustomUser.objects.get(id=investor_id)
    except CustomUser.DoesNotExist:
        yield {'error': f'User with id {investor_id} does not exists.'}
        return

    quantity_decimal_places = Transactions._meta.get_field('quantity').decimal_places
    price_decimal_places = Prices._meta.get_field('price').decimal_places

    SKIP_DESCRIPTIONS = {'* BALANCE B/F *', 'Cash Transfers ISA'}
    COMMISSION_DESCRIPTIONS = {'Funds Platform Fee', 'Govt Flat Rate Int Charge'}
    CASH_IN_DESCRIPTIONS = {'Stocks & Shares Subs', 'ISA Subscription'}

    security_cache = defaultdict(lambda: None)
    skipped_count = 0
    total_transactions = 0
    imported_transactions = 0
    transactions_to_create = []

    def find_security(stock_description):
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

    def handle_security_recognition(stock_description):
        security, best_match = find_security(stock_description)
        if security is None:
            yield {
                'status': 'security_mapping',
                'security': stock_description,
                'best_match': best_match
            }
            security_id = yield  # Wait for user input
            if security_id:
                security = Assets.objects.get(id=security_id)
                security_cache[stock_description] = security
            else:
                return None
        return security

    existing_transactions = set(Transactions.objects.filter(investor=investor, broker=broker).values_list(
        'security__id', 'currency', 'type', 'date', 'quantity', 'price', 'cash_flow', 'commission'
    ))

    for index, row in df.iterrows():
        total_transactions += 1
        if pd.isna(row['Date']):
            continue

        date = datetime.strptime(row['Date'], '%d-%b-%Y').date()
        description = row['Description']
        stock_description = row['Stock Description']
        price = row['Price']
        debit = row['Debit']
        credit = row['Credit']

        if description in SKIP_DESCRIPTIONS:
            skipped_count += 1
            continue

        transaction_data = None

        if "Gross interest" in description:
            transaction_data = {
                'investor': investor,
                'broker': broker,
                'currency': currency,
                'type': TRANSACTION_TYPE_INTEREST_INCOME,
                'date': date,
                'cash_flow': round(Decimal(str(credit)), 2),
            }
        elif description in COMMISSION_DESCRIPTIONS:
            transaction_data = {
                'investor': investor,
                'broker': broker,
                'currency': currency,
                'type': TRANSACTION_TYPE_BROKER_COMMISSION,
                'date': date,
                'commission': round(-Decimal(str(debit)), 2),
            }
        elif description in CASH_IN_DESCRIPTIONS or 'ISA Subscription' in description:
            transaction_data = {
                'investor': investor,
                'broker': broker,
                'currency': currency,
                'type': TRANSACTION_TYPE_CASH_IN,
                'date': date,
                'cash_flow': Decimal(str(credit)),
            }
        elif 'Dividend' in description or 'Equalisation' in description or 'Tax Credit' in description:
            security = yield from handle_security_recognition(stock_description)
            if security is None:
                skipped_count += 1
                continue
            transaction_data = {
                'investor': investor,
                'broker': broker,
                'security': security,
                'currency': currency,
                'type': TRANSACTION_TYPE_DIVIDEND,
                'date': date,
                'cash_flow': Decimal(str(credit)),
            }
        elif pd.notna(stock_description):
            security = yield from handle_security_recognition(stock_description)
            if security is None:
                skipped_count += 1
                continue

            if description == 'Buy':
                transaction_type = TRANSACTION_TYPE_BUY
            elif description == 'Sell':
                transaction_type = TRANSACTION_TYPE_SELL
            else:
                skipped_count += 1
                continue

            try:
                price = Decimal(str(price))
                price = round(price, price_decimal_places)
            except InvalidOperation:
                skipped_count += 1
                continue

            try:
                quantity = Decimal(str(debit if debit > 0 else -credit)) / price
                quantity = round(quantity, quantity_decimal_places)
                if quantity == 0:
                    skipped_count += 1
                    continue
            except InvalidOperation:
                skipped_count += 1
                continue

            transaction_data = {
                'investor': investor,
                'broker': broker,
                'security': security,
                'currency': currency,
                'type': transaction_type,
                'date': date,
                'quantity': quantity,
                'price': price,
            }

        if transaction_data:
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

            if transaction_tuple not in existing_transactions:
                transactions_to_create.append(transaction_data)
                imported_transactions += 1
            else:
                skipped_count += 1

        progress = (index + 1) / total_rows * 100
        yield {'status': 'progress', 'message': f'Processing transaction {index + 1} of {total_rows}', 'progress': progress}

    yield {'status': 'complete', 'data': {
        'totalTransactions': total_transactions,
        'importedTransactions': imported_transactions,
        'skippedTransactions': skipped_count,
        'transactionsToCreate': transactions_to_create
    }}