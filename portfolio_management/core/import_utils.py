from collections import defaultdict
import pandas as pd
from decimal import Decimal, InvalidOperation
from fuzzywuzzy import process

from django.db import transaction

from common.models import Assets, Brokers, Transactions
from users.models import CustomUser
from constants import TRANSACTION_TYPE_INTEREST_INCOME, TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_DIVIDEND, TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_BROKER_COMMISSION
from datetime import datetime

def parse_charles_stanley_transactions(file_path, currency, broker_id, investor_id):
    df = pd.read_excel(file_path, header=3, usecols=['Date', 'Description', 'Stock Description', 'Price', 'Debit', 'Credit'])
    transactions_to_create = []
    security_cache = defaultdict(lambda: None)
    skipped_count = 0
    total_transactions = 0
    imported_transactions = 0
    unrecognized_securities = set()

    broker = Brokers.objects.get(id=broker_id)
    investor = CustomUser.objects.get(id=investor_id)

    quantity_decimal_places = Transactions._meta.get_field('quantity').decimal_places
    price_decimal_places = 5

    SKIP_DESCRIPTIONS = {'* BALANCE B/F *', 'Cash Transfers ISA'}
    COMMISSION_DESCRIPTIONS = {'Funds Platform Fee', 'Govt Flat Rate Int Charge'}
    CASH_IN_DESCRIPTIONS = {'Stocks & Shares Subs', 'ISA Subscription'}

    MIN_PRICE = Decimal('0.0001')

    def find_security(stock_description):
        if security_cache[stock_description] is not None:
            return security_cache[stock_description]
        
        securities = list(Assets.objects.filter(investor=investor, brokers=broker))
        security_names = [security.name for security in securities]
        best_match = process.extractOne(stock_description, security_names, score_cutoff=60)
        
        if best_match:
            match_name, match_score = best_match
            security = next(s for s in securities if s.name == match_name)
            security_cache[stock_description] = security
            return security
        
        unrecognized_securities.add(stock_description)
        return None

    existing_transactions = set(Transactions.objects.filter(investor=investor, broker=broker).values_list(
        'security__id', 'currency', 'type', 'date', 'quantity', 'price', 'cash_flow', 'commission'
    ))

    for _, row in df.iterrows():
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
            security = find_security(stock_description)
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
            security = find_security(stock_description)
            if security is None:
                skipped_count += 1
                continue

            if description == 'Buy':
                transaction_type = TRANSACTION_TYPE_BUY
            elif description == 'Sell':
                transaction_type = TRANSACTION_TYPE_SELL

            try:
                price = Decimal(str(price))
                if price < MIN_PRICE:
                    price = MIN_PRICE
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
        else:
            skipped_count += 1
            continue

        if security is None and 'security' in transaction_data:
            unrecognized_securities.add(stock_description)
            skipped_count += 1
            continue

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
            skipped_count += 1
            continue

        transactions_to_create.append(transaction_data)
        imported_transactions += 1

    # Don't save transactions yet, just return the data
    return {
        'totalTransactions': total_transactions,
        'importedTransactions': imported_transactions,
        'skippedTransactions': skipped_count,
        'unrecognizedSecurities': list(unrecognized_securities),
        'transactionsToCreate': transactions_to_create
    }