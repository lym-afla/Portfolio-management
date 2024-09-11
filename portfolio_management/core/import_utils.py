from collections import defaultdict
import pandas as pd
from decimal import Decimal
from django.db.models import Q
from fuzzywuzzy import process

from common.models import Assets, Brokers, Transactions
from constants import TRANSACTION_TYPE_INTEREST_INCOME, TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_DIVIDEND, TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_BROKER_COMMISSION
from users.models import CustomUser
import sys
from datetime import datetime

from decimal import Decimal, InvalidOperation

def parse_charles_stanley_transactions(file, currency, broker_id, investor_id):
    df = pd.read_excel(file, header=3, usecols=['Date', 'Description', 'Stock Description', 'Price', 'Debit', 'Credit'])
    transactions = []
    security_cache = defaultdict(lambda: None)
    skipped_count = 0

    broker = Brokers.objects.get(id=broker_id)
    investor = CustomUser.objects.get(id=investor_id)

    quantity_decimal_places = Transactions._meta.get_field('quantity').decimal_places
    price_decimal_places = 5

    # Precompute sets for faster lookups
    SKIP_DESCRIPTIONS = {'* BALANCE B/F *', 'Cash Transfers ISA'}
    COMMISSION_DESCRIPTIONS = {'Funds Platform Fee', 'Govt Flat Rate Int Charge'}
    CASH_IN_DESCRIPTIONS = {'Stocks & Shares Subs', 'ISA Subscription'}

    MIN_PRICE = Decimal('0.0001')  # Define a minimum acceptable price

    def find_or_prompt_security(stock_description):
        if security_cache[stock_description] is not None:
            return security_cache[stock_description]
        
        securities = list(Assets.objects.filter(investor=investor, brokers=broker))
        security_names = [security.name for security in securities]
        best_match = process.extractOne(stock_description, security_names, score_cutoff=60)
        
        if best_match:
            match_name, match_score = best_match
            print(f"Potential match found: '{match_name}' (Similarity: {match_score}%)")
            user_confirm = input(f"Do you agree with this match for '{stock_description}'? (yes/no/skip/exit): ").lower()
            
            if user_confirm == 'yes':
                security_cache[stock_description] = next(s for s in securities if s.name == match_name)
                print(f"Match confirmed and cached for future use.")
                return security_cache[stock_description]
            elif user_confirm == 'exit':
                raise KeyboardInterrupt("User requested to exit")
            elif user_confirm == 'skip':
                print("Skipping this transaction.")
                return None
        
        print(f"No matching security found for '{stock_description}'.")
        user_input = input("Please enter the correct security name, 'skip' to skip this transaction, or 'exit' to stop processing: ")
        
        if user_input.lower() == 'exit':
            raise KeyboardInterrupt("User requested to exit")
        elif user_input.lower() != 'skip' and user_input:
            try:
                security = next(s for s in securities if s.name.lower() == user_input.lower())
                print(f"Security '{security.name}' found and selected.")
                security_cache[stock_description] = security
                return security
            except StopIteration:
                print(f"No exact match found for '{user_input}'. This transaction will be skipped.")
        
        print("No security name provided or skipped. This transaction will be skipped.")
        return None

    existing_transactions = set(Transactions.objects.filter(investor=investor, broker=broker).values_list(
        'security__id', 'currency', 'type', 'date', 'quantity', 'price', 'cash_flow', 'commission'
    ))

    for _, row in df.iterrows():
        if pd.isna(row['Date']):
            continue

        date = datetime.strptime(row['Date'], '%d-%b-%Y').date()
        description = row['Description']
        stock_description = row['Stock Description']
        price = row['Price']
        debit = row['Debit']
        credit = row['Credit']

        if description in SKIP_DESCRIPTIONS:
            print(f'Skipped: {description}')
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
            security = find_or_prompt_security(stock_description)
            if security is None:
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
            security = find_or_prompt_security(stock_description)
            if security is None:
                continue

            if description == 'Buy':
                transaction_type = TRANSACTION_TYPE_BUY
            elif description == 'Sell':
                transaction_type = TRANSACTION_TYPE_SELL

            try:
                price = Decimal(str(price))
                if price < MIN_PRICE:
                    print(f"Warning: Very small price ({price}) for {stock_description}. Setting to minimum price.")
                    price = MIN_PRICE
                price = round(price, price_decimal_places)
            except InvalidOperation:
                print(f"Error: Invalid price ({price}) for {stock_description}. Skipping transaction.")
                continue

            try:
                quantity = Decimal(str(debit if debit > 0 else -credit)) / price
                quantity = round(quantity, quantity_decimal_places)
                if quantity == 0:
                    print(f"Warning: Zero quantity calculated for {stock_description}. Skipping transaction.")
                    continue
            except InvalidOperation:
                print(f"Error: Invalid quantity calculation for {stock_description}. Skipping transaction.")
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
            print(f'Skipped: {description}')
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
            print(f"Skipping existing transaction: {transaction_data}")
            skipped_count += 1
            continue

        transactions.append(transaction_data)

    print(f"\nProcessed {len(transactions)} transactions.")
    print(f"Skipped {skipped_count} existing transactions.")

    if transactions:
        save_choice = input(f"Do you want to save these transactions for {broker.name}? (yes/no): ").lower()
        if save_choice == 'yes':
            Transactions.objects.bulk_create([Transactions(**data) for data in transactions])
            print("Transactions saved to the database.")
        else:
            print("Transactions were not saved to the database.")
    else:
        print("No transactions to save.")

    return transactions