from decimal import Decimal
from common.models import Brokers, Assets, FX, Prices, Transactions
from django.db.models import Sum, Max, Case, When
from pyxirr import xirr
import pandas as pd
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

# Define the effective 'current' date for the application
effective_current_date = date.today()

# Define custom selected brokers for the application
selected_brokers = [2]

# Portfolio at [table_date] - assets with non zero positions
# func.date used for correct query when transaction is at [table_date] (removes time (HH:MM:SS) effectively)
def portfolio_at_date(date, brokers):
    # Check if brokers is None, if so, return an empty queryset
    if brokers is None:
        return Assets.objects.none()
    
    # Filter Assets objects based on transactions with the given date and brokers
    return Assets.objects.filter(
        transactions__date__lte=date, 
        transactions__broker_id__in=brokers
    ).annotate(total_quantity=Sum('transactions__quantity')).exclude(total_quantity=0)

# Create one dictionary from two. And add values for respective keys if keys present on both dictionaries
def merge_dictionaries(dict_1, dict_2):
    dict_3 = dict_1.copy()  # Create a copy of dict_1
    for key, value in dict_2.items():
        dict_3[key] = dict_3.get(key, 0) + value  # Add values for common keys or set new values if key is not in dict_3
    return dict_3

def calculate_security_nav(item, date, currency):
    current_quote = item.price_at_date(date)
    return round(current_quote.price * FX.get_rate(item.currency.upper(), currency, current_quote.date)['FX'] * item.position(date), 2)

def update_analysis(analysis, key, value, date=None, currency=None, desired_currency=None):
    if currency and date and desired_currency:
        value = round(value * FX.get_rate(currency, desired_currency, date)['FX'], 2)
    if key not in analysis:
        analysis[key] = value
    else:
        analysis[key] += value

# Get all the brokers associated with a given security
def get_brokers_for_security(security_id):
    # Filter transactions based on the security ID
    transactions = Transactions.objects.filter(security_id=security_id)

    # Retrieve distinct brokers from the filtered transactions
    brokers = Brokers.objects.filter(transactions__in=transactions).distinct()

    return brokers

# Calculate NAV breakdown for selected brokers at certain date and in selected currency
def NAV_at_date(broker_ids, date, target_currency, breakdown=['Asset type', 'Currency', 'Asset class', 'Broker']):
    
    # print(f"utils.py, line 51 {breakdown}")
    
    portfolio = portfolio_at_date(date, broker_ids)
    portfolio_brokers = Brokers.objects.filter(id__in=broker_ids)
    analysis = {'Asset type': {}, 'Currency': {}, 'Asset class': {}, 'Broker': {}, 'Total NAV': 0}
    item_type = {'Asset type': 'type', 'Currency': 'currency', 'Asset class': 'exposure'}

    for security in portfolio:
        current_value = security.position(date, broker_ids) * security.price_at_date(date, target_currency).price
        # current_value = calculate_security_nav(security, date, target_currency)

        if 'Broker' in breakdown:
            for broker in get_brokers_for_security(security.id):
                update_analysis(analysis['Broker'], broker.name, current_value)

        # print(f'utils.py, line 65 {breakdown}')
        for breakdown_type in breakdown:
            if breakdown_type == 'Broker':
                continue
            # print(f"utils.py, line 68 {breakdown_type}")
            key = getattr(security, item_type[breakdown_type])
            update_analysis(analysis[breakdown_type], key, current_value)
        
        analysis['Total NAV'] += current_value

    cash_balance = {}
    for broker in portfolio_brokers:
        cash_balance = merge_dictionaries(cash_balance, broker.balance(date))
        for currency, balance in broker.balance(date).items():
            update_analysis(analysis['Broker'], broker.name, balance, date, currency, target_currency)

    cash = 0
    for currency, balance in cash_balance.items():
        converted_cash = round(balance * FX.get_rate(currency, target_currency, date)['FX'], 2)
        cash += converted_cash
        update_analysis(analysis['Currency'], currency, converted_cash)

    if 'Asset type' in breakdown:
        update_analysis(analysis['Asset type'], 'Cash', cash)
    if 'Asset class' in breakdown:
        update_analysis(analysis['Asset class'], 'Cash', cash)

    analysis['Total NAV'] += cash
    
    return analysis

# Calculate portfolio IRR at date for public assets
def Irr(date, currency=None, asset_id=None, broker_id_list=None, start_date=''):
    
    # Calculate portfolio value
    portfolio_value = calculate_portfolio_value(date, currency, asset_id, broker_id_list)

    # Not relevant for short positions
    if portfolio_value < 0:
        return 'N/R'

    cash_flows = []
    transaction_dates = []

    # Collect cash flows and transaction dates for the portfolio
    transactions = Transactions.objects.filter(date__lte=date, security_id=asset_id)
    
    # if asset_id:
    #     transactions = transactions.filter(security_id=asset_id)

    if broker_id_list:
        transactions = transactions.filter(broker_id__in=broker_id_list)

    if start_date:
        transactions = transactions.filter(date__gte=start_date)

    # print(f"utils.py. line 123. Transactions: {transactions}")

    # Calculate cash flows and transaction dates
    for transaction in transactions:
        # print(f"utils.py. line 127. Transaction details: {transaction.quantity}")
        if transaction.type == 'Cash in' or transaction.type == 'Cash out':
            cash_flow = -transaction.cash_flow
        else:
            cash_flow = transaction.cash_flow or (-transaction.quantity * transaction.price + (transaction.commission or 0))
            
        if currency is not None:
            fx_rate = FX.get_rate(transaction.currency.upper(), currency, transaction.date)['FX']
        else:
            fx_rate = 1

        cash_flows.append(round(cash_flow * fx_rate, 2))
        transaction_dates.append(transaction.date)

    # Calculate start portfolio value if provided
    if start_date:
        start_portfolio_value = calculate_portfolio_value(start_date, currency, asset_id, broker_id_list)
        cash_flows.insert(0, -start_portfolio_value)
        transaction_dates.insert(0, start_date)

    # Calculate portfolio value
    portfolio_value = calculate_portfolio_value(date, currency, asset_id, broker_id_list)

    # Append end portfolio value to cash flows and dates
    cash_flows.append(portfolio_value)
    transaction_dates.append(date)

    # print(f"utils. line 146. Cash flows: {cash_flows}, Transaction dates: {transaction_dates}")

    try:
        return round(xirr(transaction_dates, cash_flows), 4)
    except:
        return 'N/A'

def calculate_portfolio_value(date, currency=None, asset_id=None, broker_id_list=None):

    if asset_id is None:
        portfolio_value = NAV_at_date(broker_id_list, date, currency, [])['Total NAV']
    else:
        asset = Assets.objects.get(id=asset_id)
        # print(f"utils.py. line 165. asset current price: {asset.current_price(date)}")
        # print(f"utils.py. line 167. Asset data: {asset.current_price(date).price}, {asset.position(date, broker_id_list)}")
        portfolio_value = round(asset.price_at_date(date, currency).price * asset.position(date, broker_id_list), 2)

    return portfolio_value

# Collect chart dates 
def chart_dates(start_date, end_date, freq):

    # Create matching table for pandas
    frequency = {
        'D': 'B',
        'W': 'W',
        'M': 'ME',
        'Q': 'QE',
        'Y': 'YE'
    }

    # Convert the start_date and end_date strings to date objects
    if type(start_date) == str:
        start_date = date.fromisoformat(start_date)
    if type(end_date) == str:
        end_date = date.fromisoformat(end_date)

    # If the frequency is yearly, adjust the end_date to the end of the current year
    if freq == 'Y':
        end_date = end_date.replace(month=12, day=31)
        start_date = start_date.replace(month=1, day=1)
        # Keep one year if start and end within one calendar year
        if end_date.year - start_date.year != 0:
            start_date = date(start_date.year + 1, 1, 1)

    if freq == 'M':
        # Adjust the end_date to the end of the month
        end_date = end_date + relativedelta(months = 1)
        start_date = start_date + relativedelta(months = 1)

    # Get list of dates from pandas
    return pd.date_range(start_date, end_date, freq=frequency[freq]).date

# Create labels according to dates
def chart_labels(dates, frequency):
    
    if frequency == 'D':
        return [i.strftime("%d-%b-%y") for i in dates]
    if frequency == 'W':
        return [i.strftime("%d-%b-%y") for i in dates]
    if frequency == 'M':
        return [i.strftime("%b-%y") for i in dates]
    if frequency == 'Q':
        labels = []
        for i in dates:
            if i.month == 3:
                labels.append('Q1 ' + i.strftime("%y"))
            if i.month == 6:
                labels.append('Q2 ' + i.strftime("%y"))
            if i.month == 9:
                labels.append('Q3 ' + i.strftime("%y"))
            if i.month == 12:
                labels.append('Q4 ' + i.strftime("%y"))
        return labels
    if frequency == 'Y':
        return [i.strftime("%Y") for i in dates]

# Default colours for stacked bar chart
def chart_colour(number):
    colour_scheme = {
        0: 'rgb(13, 110, 227)',
        1: 'rgb(158, 169, 181)',
        2: 'rgb(40, 167, 69)',
        3: 'rgb(220, 53, 69)',
        4: 'rgb(255, 193, 7)',
        5: 'rgb(23, 162, 184)'
    }
    
    return colour_scheme[number]

# Convert Decimal objects to float
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def format_percentage(value):
    
    # Check if the value is exactly None, which is different from 0
    if value is None:
        return "NA"
    try:
        # Attempt to format the value as a percentage
        if value < 0:
            return f"({float(-value * 100):.1f}%)"
        elif value == 0:
            return "–"
        else:
            return f"{float(value * 100):.1f}%"
    except (TypeError, ValueError):
        # If the value cannot be converted to float, return 'NA'
        return value
    

def currency_format(value, currency, digits):
    """Format value as CUR."""
    match currency.upper():
        case 'USD':
            cur = '$'
        case 'EUR':
            cur = '€'
        case 'GBP':
            cur = '£'
        case 'RUB':            
            cur = '₽'
        case default:
            cur = currency.upper()
    if value < 0:
        return f"({cur}{-value:,.{int(digits)}f})"
    elif value == 0:
        return "–"
    else:
        return f"{cur}{value:,.{int(digits)}f}"
    
# Format dictionaries as strings with currency formatting
def currency_format_dict_values(data, currency, digits):
    formatted_data = {}
    for key, value in data.items():
        if isinstance(value, dict):
            # Recursively format nested dictionaries
            formatted_data[key] = currency_format_dict_values(value, currency, digits)
        elif isinstance(value, Decimal):
            # Apply the currency_format function to Decimal values
            formatted_data[key] = currency_format(value, currency, digits)
        else:
            # Copy other values as is
            formatted_data[key] = value
    return formatted_data

# Add percentage shares to the dict
def calculate_percentage_shares(data_dict, selected_keys):

    # Calculate Total NAV based on one of the categories
    total = sum(data_dict[selected_keys[0]].values())
    
    # Add new dictionaries with percentage shares for selected categories
    for category in selected_keys:
        percentage_key = category + ' percentage'
        data_dict[percentage_key] = {}
        for key, value in data_dict[category].items():
            try:
                data_dict[percentage_key][key] = str((value / total * 100).quantize(Decimal('0.1'))) + '%'
            except ZeroDivisionError:
                data_dict[percentage_key][key] = '–'

def get_chart_data(brokers, frequency, from_date, to_date, currency, breakdown):
    
    # Get the correct starting date for "All time" category
    if from_date == '1900-01-01':
        from_date = Transactions.objects.filter(broker__in=brokers).order_by('date').first().date
        print(f"utils.py. Line 312. From date: {from_date}")

    dates = chart_dates(from_date, to_date, frequency)
        # Create an empty data dictionary
    
    chart_data = {
        'labels': chart_labels(dates, frequency),
        'datasets': [],
        'currency': currency + 'k',
    }

    for d in dates:
        IRR = Irr(d, currency, None, brokers)
        if breakdown == 'No breakdown':
            NAV = NAV_at_date(brokers, d, currency)['Total NAV'] / 1000
            if len(chart_data['datasets']) == 0:
                chart_data['datasets'].append({
                    'label': 'IRR (RHS)',
                    'data': [IRR],
                    'backgroundColor': 'rgb(0, 0, 0)',
                    'type': 'line',
                    'yAxisID': 'y1',
                    'order': 0,
                    'datalabels': {
                        'display': 'true'
                    }
                })
                chart_data['datasets'].append({
                    'label': 'NAV',
                    'data': [NAV],
                    'backgroundColor': chart_colour(0),
                    'stack': 'combined',
                    'type': 'bar',
                    'yAxisID': 'y',
                    'datalabels': {
                        'display': 'true'
                    }
                })
            else:
                chart_data['datasets'][0]['data'].append(IRR)
                chart_data['datasets'][1]['data'].append(NAV)
        else:
            NAV = NAV_at_date(brokers, d, currency, [breakdown])[breakdown]
            if len(chart_data['datasets']) == 0:
                chart_data['datasets'].append({
                    'label': 'IRR (RHS)',
                    'data': [IRR],
                    'backgroundColor': 'rgb(0, 0, 0)',
                    'type': 'line',
                    'yAxisID': 'y1',
                    'order': 0,
                })
            else:
                chart_data['datasets'][0]['data'].append(IRR)
                
            for key, value in NAV.items():
                index = next((index for (index, item) in enumerate(chart_data['datasets']) if item["label"] == key), None)
                if index is None:
                    if len(chart_data['datasets']) == 0 or d == dates[0]:
                        data_entry = [value / 1000]
                    else:
                        data_entry = [0 for i in range(len(chart_data['datasets'][-1]['data']))]
                        data_entry.append(value / 1000)
                    chart_data['datasets'].append({
                        'label': key,
                        'data': data_entry,
                        'backgroundColor': chart_colour(len(chart_data['datasets']) - 1),
                        'stack': 'combined',
                        'type': 'bar',
                        'yAxisID': 'y'
                    })
                else:
                    chart_data['datasets'][index]['data'].append(value / 1000)
                    
    return chart_data

# Calculating from date based on the final date and timeline
def calculate_from_date(to_date, timeline):
    
    if type(to_date) == str:
        to_date = datetime.strptime(to_date, "%Y-%m-%d").date()  # Convert 'to' date to datetime.date

    if timeline == 'YTD':
        from_date = to_date.replace(months=1, day=1)
    elif timeline == '3m':
        from_date = to_date - relativedelta(months=3)
    elif timeline == '6m':
        from_date = to_date - relativedelta(months=6)
    elif timeline == '12m':
        from_date = to_date - relativedelta(years=1)
    elif timeline == '3Y':
        from_date = to_date - relativedelta(years=3)
    elif timeline == '5Y':
        from_date = to_date - relativedelta(years=5)
    elif timeline == 'All time':
        from_date = datetime.strptime('1900-01-01', "%Y-%m-%d").date() # Convention that ultimately will be converted to the date of the first transaction
    else:
        # Handle other cases as needed
        from_date = to_date

    return from_date

# Calculate effective buy-in price for security object (must have id)
# def calculate_buy_in_price(security_id, date, currency, broker_id_list=None, start_date=None):
    
#     try:
        
#         is_long_position = None

#         security = Assets.objects.get(id=security_id)

#         transactions = security.transactions.filter(
#             quantity__isnull=False,  # Filter out transactions where quantity is not empty
#             date__lte=date
#         ).values('price', 'quantity', 'date', 'currency')

#         if broker_id_list:
#             transactions = transactions.filter(broker_id__in=broker_id_list) 

#         if start_date:
#             transactions = transactions.filter(date__gt=start_date)
#             position = security.position(start_date, broker_id_list)
#             if position != 0:
#                 transactions = list(transactions) + [{
#                     'price': security.price_at_date(start_date).price,
#                     'quantity': position,
#                     'date': start_date,
#                     'currency': security.currency,
#                 }]
#                 is_long_position = position > 0

#         # If start date is not provided, or position at start date is 0
#         if is_long_position is None:
#             first_transaction = transactions.order_by('date').first()
#             is_long_position = first_transaction['quantity'] > 0

#         if is_long_position:
#             transactions = [t for t in transactions if t['quantity'] > 0]
#         else:
#             transactions = [t for t in transactions if t['quantity'] < 0]

#         value = 0
#         quantity = 0
#         for transaction in transactions:
#             fx_rate = FX.get_rate(transaction['currency'], currency, transaction['date'])['FX']
#             if fx_rate:
#                 value += transaction['price'] * fx_rate * transaction['quantity']
#                 quantity += transaction['quantity']
            
#         return value / quantity if quantity else None
        
#     except Exception as e:
#         print(f"Error: {e}")
#         return None
    
# Support function to create price table for Database page
def create_price_table(security_type):
    
    # Get security IDs by security type
    selected_ids = Assets.objects.filter(type=security_type).values_list('id', flat=True)

    # Initialize table as a list of dates
    dates = Prices.objects.dates('date', 'day')
    table = [[date] for date in dates]

    # Add columns with each security
    for item in selected_ids:
        asset = Assets.objects.get(id=item)
        prices = Prices.objects.filter(security_id=item).order_by('date').values_list('price', flat=True)
        for i, price in enumerate(prices):
            table[i].append(price)

    # Add column headers: Name and ISIN
    header_row_1 = ['Date'] + [Assets.objects.get(id=item).name for item in selected_ids]
    header_row_2 = [''] + [Assets.objects.get(id=item).ISIN for item in selected_ids]

    table.insert(0, header_row_2)
    table.insert(0, header_row_1)

    # Filter for rows where all prices are empty
    table = [x for x in table if any(i is not None for i in x[1:])]

    return table

def open_position_totals(asset, key, date, currency)
    
    
