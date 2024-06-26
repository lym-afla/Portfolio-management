from collections import defaultdict
from decimal import ROUND_DOWN, Decimal

from common.models import Brokers, Assets, FX, Prices, Transactions
from django.db.models import Sum, F
from pyxirr import xirr
import pandas as pd
import time
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

from users.models import CustomUser

# Define the effective 'current' date for the application
effective_current_date = date.today()

# Define custom selected brokers for the application
selected_brokers = [2]

# Portfolio at [table_date] - assets with non zero positions
# func.date used for correct query when transaction is at [table_date] (removes time (HH:MM:SS) effectively)
def portfolio_at_date(user_id, date, brokers):
    # Check if brokers is None, if so, return an empty queryset
    if brokers is None:
        return Assets.objects.none()
    
    # Filter Assets objects based on transactions with the given date and brokers
    return Assets.objects.filter(
        investor__id=user_id,
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
def get_brokers_for_security(user_id, security_id):
    # Filter transactions based on the security ID
    transactions = Transactions.objects.filter(investor__id=user_id, security_id=security_id)

    # Retrieve distinct brokers from the filtered transactions
    brokers = Brokers.objects.filter(investor__id=user_id, transactions__in=transactions).distinct()

    return brokers

# Calculate NAV breakdown for selected brokers at certain date and in selected currency
def NAV_at_date(user_id, broker_ids, date, target_currency, breakdown=['Asset type', 'Currency', 'Asset class', 'Broker']):
    
    # print(f"utils.py, line 51 {breakdown}")
    
    portfolio = portfolio_at_date(user_id, date, broker_ids)
    portfolio_brokers = Brokers.objects.filter(investor__id=user_id, id__in=broker_ids)
    analysis = {'Asset type': {}, 'Currency': {}, 'Asset class': {}, 'Broker': {}, 'Total NAV': 0}
    item_type = {'Asset type': 'type', 'Currency': 'currency', 'Asset class': 'exposure'}

    # print(f"utils.py, line 68 {portfolio}. Date: {date}")

    for security in portfolio:
        current_value = round(security.position(date, broker_ids) * security.price_at_date(date, target_currency).price, 2)
        # current_value = calculate_security_nav(security, date, target_currency)

        if 'Broker' in breakdown:
            for broker in get_brokers_for_security(user_id, security.id):
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
        # print("utils, 95", date, cash_balance)
        for currency, balance in broker.balance(date).items():
            update_analysis(analysis['Broker'], broker.name, balance, date, currency, target_currency)

    cash = 0
    for currency, balance in cash_balance.items():
        converted_cash = round(balance * FX.get_rate(currency, target_currency, date)['FX'], 2)
        cash += converted_cash
        update_analysis(analysis['Currency'], currency, converted_cash)

    # print("utils. 104", cash_balance, cash)

    if 'Asset type' in breakdown:
        update_analysis(analysis['Asset type'], 'Cash', cash)
    if 'Asset class' in breakdown:
        update_analysis(analysis['Asset class'], 'Cash', cash)

    analysis['Total NAV'] += cash

    # Remove keys with zero values
    for key in list(analysis.keys()):
        if isinstance(analysis[key], dict):
            analysis[key] = {k: v for k, v in analysis[key].items() if v != 0}
    
    return analysis

# Calculate portfolio IRR at date for public assets
def Irr(user_id, date, currency=None, asset_id=None, broker_id_list=None, start_date=None):
    
    # Calculate portfolio value
    portfolio_value = calculate_portfolio_value(user_id, date, currency, asset_id, broker_id_list)

    # Not relevant for short positions
    if portfolio_value < 0:
        return 'N/R'

    cash_flows = []
    transaction_dates = []

    # Collect cash flows and transaction dates for the portfolio
    transactions = Transactions.objects.filter(investor__id=user_id, date__lte=date, security_id=asset_id)
    
    # if asset_id:
    #     transactions = transactions.filter(security_id=asset_id)

    if broker_id_list is not None:
        transactions = transactions.filter(broker_id__in=broker_id_list)

    if start_date is not None:
        transactions = transactions.filter(date__gte=start_date)

        # Calculate start portfolio value if provided
        initial_value_date = start_date - timedelta(days=1)
        start_portfolio_value = calculate_portfolio_value(user_id, initial_value_date, currency, asset_id, broker_id_list)
        # print("utils. 150", start_portfolio_value, transactions)
        
        # Not relevant for short positions
        first_transaction = transactions.order_by('date').first().quantity or 0
        if (start_portfolio_value < 0) or (start_portfolio_value == 0 and first_transaction < 0):
            # print("Short position")
            return 'N/R'

        cash_flows.insert(0, -start_portfolio_value)
        transaction_dates.insert(0, initial_value_date)

    # print(f"utils.py. line 123. Transactions: {transactions}")

    # Calculate cash flows and transaction dates
    for transaction in transactions:
        # print(f"utils.py. line 127. Transaction details: {transaction.quantity}")
        if transaction.type == 'Cash in' or transaction.type == 'Cash out':
            cash_flow = -1 * transaction.cash_flow
        elif transaction.type == 'Broker commission':
            cash_flow = Decimal(0) # Do not account for pay-outs elsewhere
        else:
            cash_flow = transaction.cash_flow or (-transaction.quantity * transaction.price + (transaction.commission or 0))
            
        if currency is not None:
            fx_rate = FX.get_rate(transaction.currency.upper(), currency, transaction.date)['FX']
        else:
            fx_rate = 1
        cash_flows.append(round(cash_flow * fx_rate, 2))
        transaction_dates.append(transaction.date)

    # Check if there are transactions on the given date
    if transactions.filter(date=date).exists():
        # If transactions exist on the given date, add the portfolio value to the last transaction
        cash_flows[-1] += portfolio_value
    else:
        # Otherwise, append the portfolio value as a separate cash flow
        cash_flows.append(portfolio_value)
        transaction_dates.append(date)

    try:
        irr = round(xirr(transaction_dates, cash_flows), 4)
        irr = irr if irr < 2 else 'N/R'
        return irr
    except:
        return 'N/A'

def calculate_portfolio_value(user_id, date, currency=None, asset_id=None, broker_id_list=None):

    if asset_id is None:
        portfolio_value = NAV_at_date(user_id, broker_id_list, date, currency, [])['Total NAV']
    else:
        asset = Assets.objects.get(id=asset_id)
        # print(f"utils.py. line 188. Asset: {asset.name}, {asset.id}, {user_id}, {date}, {currency}, {asset_id}, {broker_id_list}")
        # print(f"utils.py. line 201. Asset data: {asset.price_at_date(date, currency).price}, {asset.position(date, broker_id_list)}")
        try:
            portfolio_value = round(asset.price_at_date(date, currency).price * asset.position(date, broker_id_list), 2)
        except:
            portfolio_value = 0

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

def format_percentage(value, digits=0):
    
    # Check if the value is exactly None, which is different from 0
    if value is None:
        return "NA"
    try:
        # Attempt to format the value as a percentage
        if value < 0:
            return f"({float(-value * 100):.{int(digits)}f}%)"
        elif value == 0:
            return "–"
        else:
            return f"{float(value * 100):.{int(digits)}f}%"
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
            if 'percentage' in key:
                formatted_data[key] = format_percentage(value)
            else:
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

def get_chart_data(user_id, brokers, frequency, from_date, to_date, currency, breakdown):
    
    # Get the correct starting date for "All time" category
    if from_date == '1900-01-01':
        from_date = Transactions.objects.filter(investor__id=user_id, broker__in=brokers).order_by('date').first().date
        # print(f"utils.py. Line 312. From date: {from_date}")

    dates = chart_dates(from_date, to_date, frequency)
        # Create an empty data dictionary
    
    chart_data = {
        'labels': chart_labels(dates, frequency),
        'datasets': [],
        'currency': currency + 'k',
    }

    for d in dates:
        IRR = Irr(user_id, d, currency, None, brokers)
        if breakdown == 'No breakdown':
            NAV = NAV_at_date(user_id, brokers, d, currency)['Total NAV'] / 1000
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
            NAV = NAV_at_date(user_id, brokers, d, currency, [breakdown])[breakdown]
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

    # print("utils. 437", chart_data)
                    
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
    
# Support function to create price table for Database page
def create_price_table(security_type, user):
    
    # Get security IDs by security type
    selected_ids = Assets.objects.filter(type=security_type, investor=user).values_list('id', flat=True)

    # Initialize table as a dictionary of lists with dates as keys
    price_data = defaultdict(lambda: [None] * len(selected_ids))
    dates = set()
    
    for index, item in enumerate(selected_ids):
        prices = Prices.objects.filter(security_id=item).order_by('date').values_list('date', 'price')
        for date, price in prices:
            price_data[date][index] = price
            dates.add(date)

    # Sort the dates
    sorted_dates = sorted(dates)
    
    # Convert the dictionary to a list with sorted dates
    table = [[date] + price_data[date] for date in sorted_dates]

    # Add column headers: Name and ISIN
    header_row_1 = ['Date'] + [Assets.objects.get(id=item).name for item in selected_ids]
    header_row_2 = [''] + [Assets.objects.get(id=item).ISIN for item in selected_ids]

    table.insert(0, header_row_2)
    table.insert(0, header_row_1)

    # Filter for rows where all prices are None
    table = [x for x in table if any(i is not None for i in x[1:])]

    return table

def calculate_open_table_output(user_id, portfolio, date, categories, use_default_currency, currency_target, selected_brokers, number_of_digits):
    
    # if portfolio is None:
    #     return None, None
    # else:
    portfolio_NAV = NAV_at_date(user_id, selected_brokers, date, currency_target)['Total NAV']
    
    totals = ['entry_value', 'current_value', 'realized_gl', 'unrealized_gl', 'capital_distribution', 'commission']
    portfolio_open_totals = {}
    
    for asset in portfolio:
    
        currency_used = None if use_default_currency else currency_target

        asset.current_position = asset.position(date, selected_brokers)

        if asset.current_position == 0:
            print("The position is zero. The asset is not in the portfolio.")
            return None

        asset.entry_price = asset.calculate_buy_in_price(date, currency_used, selected_brokers)
        asset.entry_value = asset.entry_price * asset.current_position
        asset.entry_price = currency_format(asset.entry_price, asset.currency if use_default_currency else currency_target, number_of_digits)
        entry_date = asset.entry_dates(date, selected_brokers)[-1]
        # print(f'utils.py. LIne 508. Entry date: {entry_date}')
        
        if 'investment_date' in categories:
            asset.investment_date = entry_date
        
        if 'current_value' in categories:
            asset.current_price = asset.price_at_date(date, currency_used).price
            asset.current_value = asset.current_price * asset.current_position
            asset.share_of_portfolio = asset.price_at_date(date, currency_used).price * asset.current_position / portfolio_NAV
            
            # Formatting
            asset.current_price = currency_format(asset.current_price, asset.currency if use_default_currency else currency_target, number_of_digits)
            asset.current_value = currency_format(asset.current_value, asset.currency if use_default_currency else currency_target, number_of_digits)
            asset.share_of_portfolio = format_percentage(asset.share_of_portfolio)
        
        if 'realized_gl' in categories:
            asset.realized_gl = asset.realized_gain_loss(date, currency_used, selected_brokers)['current_position']
        else:
            asset.realized_gl = 0

        if 'unrealized_gl' in categories:
            asset.unrealized_gl = asset.unrealized_gain_loss(date, currency_used, selected_brokers)
        else:
            asset.unrealized_gl = 0
        
        asset.price_change_percentage = (asset.realized_gl + asset.unrealized_gl) / asset.entry_value if asset.entry_value > 0 else 'N/R'
        
        if 'capital_distribution' in categories:
            asset.capital_distribution = asset.get_capital_distribution(date, currency_used, selected_brokers, entry_date)
            asset.capital_distribution_percentage = asset.capital_distribution / asset.entry_value if asset.entry_value > 0 else 'N/R'
        else:
            asset.capital_distribution = 0

        if 'commission' in categories:
            asset.commission = asset.get_commission(date, currency_used, selected_brokers, entry_date)
            asset.commission_percentage = asset.commission / asset.entry_value if asset.entry_value > 0 else 'N/R'
        else:
            asset.commission = 0
            
        asset.total_return_amount = asset.realized_gl + asset.unrealized_gl + asset.capital_distribution + asset.commission
        asset.total_return_percentage = asset.total_return_amount / asset.entry_value if asset.entry_value > 0 else 'N/R'
        
        # Calculate IRR for security
        currency_used = asset.currency if use_default_currency else currency_target
        asset.irr = format_percentage(Irr(user_id, date, currency_used, asset_id=asset.id, broker_id_list=selected_brokers, start_date=entry_date))
        
        # Calculating totals
        for key in (list(set(totals) & set(categories)) + ['entry_value', 'total_return_amount']):

            if not use_default_currency:
                addition = getattr(asset, key)
            else:
                if key == 'entry_value':
                    addition = asset.calculate_buy_in_price(date, currency_target, selected_brokers) * asset.current_position
                elif key == 'current_value':
                    addition = asset.price_at_date(date, currency_target).price * asset.current_position
                elif key == 'realized_gl':
                    addition = asset.realized_gain_loss(date, currency_target, selected_brokers)['current_position']
                elif key == 'unrealized_gl':
                    addition = asset.unrealized_gain_loss(date, currency_target, selected_brokers)
                elif key == 'capital_distribution':
                    addition = asset.get_capital_distribution(date, currency_target, selected_brokers, entry_date)
                elif key == 'commission':
                    addition = asset.get_commission(date, currency_target, selected_brokers, entry_date)
                elif key == 'total_return_amount':
                    addition = asset.realized_gain_loss(date, currency_target, selected_brokers)['current_position'] + \
                        asset.unrealized_gain_loss(date, currency_target, selected_brokers) + \
                        asset.get_capital_distribution(date, currency_target, selected_brokers, entry_date) + \
                        asset.get_commission(date, currency_target, selected_brokers, entry_date)
                    # print("Line 636", addition)
                else:
                    # print(use_default_currency, key)
                    addition = None
                    
            try:
                portfolio_open_totals[key] = portfolio_open_totals.get(key, 0) + addition
            except:
                portfolio_open_totals[key] = portfolio_open_totals.get(key, 0)

        # Formatting for correct representation
        asset.current_position = currency_format(asset.current_position, '', 0)
        
        asset.entry_value = currency_format(asset.entry_value, currency_used, number_of_digits)
        
        asset.realized_gl = currency_format(asset.realized_gl, currency_used, number_of_digits)

        asset.unrealized_gl = currency_format(asset.unrealized_gl, currency_used, number_of_digits)
        asset.price_change_percentage = format_percentage(asset.price_change_percentage)
        asset.capital_distribution = currency_format(asset.capital_distribution, currency_used, number_of_digits)
        asset.capital_distribution_percentage = format_percentage(asset.capital_distribution_percentage)
        asset.commission = currency_format(asset.commission, currency_used, number_of_digits)
        asset.commission_percentage = format_percentage(asset.commission_percentage)
        asset.total_return_amount = currency_format(asset.total_return_amount, currency_used, number_of_digits)
        asset.total_return_percentage = format_percentage(asset.total_return_percentage)

    if 'entry_value' in portfolio_open_totals.keys():
        if portfolio_open_totals['entry_value'] != 0:    
            portfolio_open_totals['price_change_percentage'] = (portfolio_open_totals.get('realized_gl', 0) + portfolio_open_totals.get('unrealized_gl', 0)) / abs(portfolio_open_totals['entry_value'])
            if 'capital_distribution' in categories:
                portfolio_open_totals['capital_distribution_percentage'] = portfolio_open_totals['capital_distribution'] / portfolio_open_totals['entry_value']
            if 'commission' in categories:
                portfolio_open_totals['commission_percentage'] = portfolio_open_totals['commission'] / portfolio_open_totals['entry_value']
            portfolio_open_totals['total_return_percentage'] = portfolio_open_totals['total_return_amount'] / abs(portfolio_open_totals['entry_value'])
    
    # Format totals
    portfolio_open_totals = currency_format_dict_values(portfolio_open_totals, currency_target, number_of_digits)

    return portfolio, portfolio_open_totals


def calculate_closed_table_output(user_id, portfolio, date, categories, use_default_currency, currency_target, selected_brokers, number_of_digits):
    
    # if len(portfolio) == 0:
    #     return None, None
    # else:
    closed_positions = []
    
    totals = ['entry_value', 'current_value', 'realized_gl', 'capital_distribution', 'commission']
    portfolio_closed_totals = {}
    
    for asset in portfolio:
        # print('utils.py. Line 573', asset)
        # print('utils.py. Line 574', asset.exit_dates(date, selected_brokers))
        for exit_date in asset.exit_dates(date):
            
            currency_used = None if use_default_currency else currency_target
            
            position = {}
            position['type'] = asset.type
            position['name'] = asset.name
            entry_date = asset.entry_dates(exit_date)[-1]
            position['investment_date'] = entry_date
            position['exit_date'] = exit_date
            position['currency'] = asset.currency

            asset_transactions = asset.transactions.filter(investor__id=user_id, date__gte=entry_date, date__lte=exit_date).order_by('-date')
            is_long_position = asset_transactions.first().quantity < 0
            if is_long_position:
                entry_transactions = asset_transactions.filter(quantity__gt=0)
                exit_transactions = asset_transactions.filter(quantity__lt=0)
            else:
                entry_transactions = asset_transactions.filter(quantity__lt=0)
                exit_transactions = asset_transactions.filter(quantity__gt=0)

            total_value = Decimal(0)
            total_quantity = Decimal(0)
            for transaction in entry_transactions:
                if currency_used is None:
                    fx_rate = 1
                else:
                    fx_rate = FX.get_rate(transaction.currency, currency_used, transaction.date)['FX']
                total_value += transaction.price * abs(transaction.quantity) * fx_rate
                total_quantity += abs(transaction.quantity)
                if asset.id == 8:
                    print(transaction, total_value, total_quantity)
            position['entry_price'] = total_value / total_quantity if total_quantity else Decimal(0)
            position['entry_value'] = total_value
            
            total_value = Decimal(0)
            total_quantity = Decimal(0)
            for transaction in exit_transactions:
                if currency_used is None:
                    fx_rate = 1
                else:
                    fx_rate = FX.get_rate(transaction.currency, currency_used, transaction.date)['FX']
                total_value += transaction.price * abs(transaction.quantity) * fx_rate
                total_quantity += abs(transaction.quantity)
            position['exit_price'] = total_value / total_quantity if total_quantity else Decimal(0)
            position['exit_value'] = total_value

            if 'realized_gl' in categories:
                
                position_transactions = asset.transactions.filter(investor__id=user_id, date__lte=exit_date, date__gte=entry_date, quantity__isnull=False)
                total_gl = 0
                if currency_used is not None:
                    for transaction in position_transactions:
                        fx_rate = FX.get_rate(transaction.currency, currency_used, transaction.date)['FX']
                        if fx_rate:
                            total_gl -= transaction.price * transaction.quantity * fx_rate
                else:
                    total_gl = position_transactions.aggregate(total=Sum(F('price') * F('quantity')))['total'] or 0
                    total_gl = -total_gl
                position['realized_gl'] = total_gl
            else:
                position['realized_gl'] = 0
            
            position['price_change_percentage'] = (position['realized_gl'] ) / position['entry_value'] if position['entry_value'] > 0 else 'N/R'
        
            if 'capital_distribution' in categories:
                position['capital_distribution'] = round(asset.get_capital_distribution(exit_date, currency_used, selected_brokers, entry_date), 2)
                position['capital_distribution_percentage'] = position['capital_distribution'] / position['entry_value'] if position['entry_value'] > 0 else 'N/R'
            else:
                position['capital_distribution'] = 0

            if 'commission' in categories:
                position['commission'] = asset.get_commission(exit_date, currency_used, selected_brokers, entry_date)
                position['commission_percentage'] = position['commission'] / position['entry_value'] if position['entry_value'] > 0 else 'N/R'
            else:
                position['commission'] = 0
            
            position['total_return_amount'] = position['realized_gl'] + position['capital_distribution'] + position['commission']
            position['total_return_percentage'] = position['total_return_amount'] / position['entry_value'] if position['entry_value'] > 0 else 'N/R'
        
            # Calculate IRR for security
            currency_used = asset.currency if use_default_currency else currency_target
            position['irr'] = format_percentage(Irr(user_id, exit_date, currency_used, asset_id=asset.id, broker_id_list=selected_brokers, start_date=entry_date), number_of_digits)
            # print("Utils. Line 786", asset.irr)
        
            # Calculating totals
            for key in (list(set(totals) & set(categories)) + ['entry_value', 'total_return_amount']):
                # print("Line 614", asset)

                if not use_default_currency:
                    addition = getattr(asset, key)
                else:
                    if key == 'entry_value':
                        addition = position['entry_value']
                    elif key == 'realized_gl':
                        total_gl = 0
                        for transaction in position_transactions:
                            fx_rate = FX.get_rate(transaction.currency, currency_target, transaction.date)['FX']
                            if fx_rate:
                                total_gl -= transaction.price * transaction.quantity * fx_rate
                        addition = total_gl
                    elif key == 'capital_distribution':
                        addition = asset.get_capital_distribution(date, currency_target, selected_brokers, entry_date)
                    elif key == 'commission':
                        addition = asset.get_commission(date, currency_target, selected_brokers)
                    elif key == 'total_return_amount':
                        addition = total_gl + \
                            asset.unrealized_gain_loss(date, currency_target, selected_brokers) + \
                            asset.get_capital_distribution(date, currency_target, selected_brokers, entry_date) + \
                            asset.get_commission(date, currency_target, selected_brokers, entry_date)
                        # print("Line 636", addition)
                    else:
                        # print(use_default_currency, key)
                        addition = None
                        
                try:
                    portfolio_closed_totals[key] = portfolio_closed_totals.get(key, 0) + addition
                except:
                    portfolio_closed_totals[key] = portfolio_closed_totals.get(key, 0)

            # Formatting for correct representation
            position['entry_price'] = currency_format(position['entry_price'], currency_used, number_of_digits)
            position['exit_price'] = currency_format(position['exit_price'], currency_used, number_of_digits)


            if position['realized_gl']:
                position['realized_gl'] = currency_format(position['realized_gl'], currency_used, number_of_digits)

            position['price_change_percentage'] = format_percentage(position['price_change_percentage'], number_of_digits)
            position['capital_distribution'] = currency_format(position['capital_distribution'], currency_used, number_of_digits)
            position['capital_distribution_percentage'] = format_percentage(position['capital_distribution_percentage'], number_of_digits)
            position['commission'] = currency_format(position['commission'], currency_used, number_of_digits)
            position['commission_percentage'] = format_percentage(position['commission_percentage'], number_of_digits)
            position['total_return_amount'] = currency_format(position['total_return_amount'], currency_used, number_of_digits)
            position['total_return_percentage'] = format_percentage(position['total_return_percentage'], number_of_digits)

            closed_positions.append(position)

    if 'entry_value' in portfolio_closed_totals.keys():
        if portfolio_closed_totals['entry_value'] != 0:    
            portfolio_closed_totals['price_change_percentage'] = (portfolio_closed_totals.get('realized_gl', 0) + portfolio_closed_totals.get('unrealized_gl', 0)) / abs(portfolio_closed_totals['entry_value'])
            if 'capital_distribution' in categories:
                portfolio_closed_totals['capital_distribution_percentage'] = portfolio_closed_totals['capital_distribution'] / portfolio_closed_totals['entry_value']
            if 'commission' in categories:
                portfolio_closed_totals['commission_percentage'] = portfolio_closed_totals['commission'] / portfolio_closed_totals['entry_value']
            portfolio_closed_totals['total_return_percentage'] = portfolio_closed_totals['total_return_amount'] / abs(portfolio_closed_totals['entry_value'])

    # Format totals
    portfolio_closed_totals = currency_format_dict_values(portfolio_closed_totals, currency_target, number_of_digits)

    return closed_positions, portfolio_closed_totals

def update_fx_database(investor):

    # Get the specific investor
    investor_instance = CustomUser.objects.get(id=investor.id)

    # Scan Transaction instances in the database to collect dates
    transaction_dates = investor_instance.transactions.values_list('date', flat=True)
    
    count = 0
    for date in transaction_dates:
        count += 1
        print(f'{count} of {len(transaction_dates)}')
        FX.update_fx_rate(date, investor)

# THIS IT NOT USED (?!)
def import_transactions_from_file(file, user, broker, currency, confirm_each):
    
    df = pd.read_excel(file, header=None)
    transactions = []
    i = 0

    while i < len(df.columns):
        if pd.notna(df.iloc[1, i]):
            security_name = df.iloc[1, i]
            isin = df.iloc[2, i]
            
            security = Assets.objects.filter(name=security_name, ISIN=isin).first()

            if not security:
                # If the security does not exist, return a response to open the form
                return {
                        'status': 'missing_security',
                        'security': {
                            'name': security_name,
                            'isin': isin,
                            'currency': currency,
                        }
                    }

            # Process transactions...
            transactions_start = df[df.iloc[:, i] == 'Дата'].index[0] + 1

            for row in range(transactions_start, len(df)):
                if pd.isna(df.iloc[row, i]):
                    break

                date = df.iloc[row, i]

                price = df.iloc[row, i + 1]
                quantity = df.iloc[row, i + 2]
                dividend = df.iloc[row, i + 3] if not pd.isna(df.iloc[row, i + 3]) else None
                commission = df.iloc[row, i + 4] if not pd.isna(df.iloc[row, i + 4]) else None

                transaction_data = {
                    'security_name': security_name,
                    'isin': isin,
                    'date': date,
                    'price': price,
                    'quantity': quantity,
                    'dividend': dividend,
                    'commission': commission,
                }

                if confirm_each:
                    transactions.append(transaction_data)
                else:
                    if quantity > 0:
                        transaction_type = 'Buy'
                    elif quantity < 0:
                        transaction_type = 'Sell'
                    else:
                        transaction_type = 'Dividend'
                    
                    Transactions.objects.create(
                        investor=user,
                        broker=broker,
                        security=security,
                        currency=currency,
                        type=transaction_type,
                        date=date,
                        quantity=quantity,
                        price=price,
                        cash_flow=dividend,
                        commission=commission,
                    )

            i += 1
            while i < len(df.columns) and pd.isna(df.iloc[1, i]):
                i += 1
        else:
            i += 1

    # Return transactions list for further processing if needed
    return {
        'status': 'success',
        'transactions': transactions
    }

def parse_excel_file_transactions(file, currency, broker_id):
    df = pd.read_excel(file, header=None)
    securities = []
    transactions = []
    i = 0

    while i < len(df.columns):
        if pd.notna(df.iloc[1, i]):
            security_name = df.iloc[1, i]
            isin = df.iloc[2, i]
            securities.append({'name': security_name, 'isin': isin, 'currency': currency})

            transactions_start = df[df.iloc[:, i] == 'Дата'].index[0] + 1

            for row in range(transactions_start, len(df)):
                if pd.isna(df.iloc[row, i]):
                    continue

                date = df.iloc[row, i].strftime("%Y-%m-%d")
                price = df.iloc[row, i + 1]
                quantity = Decimal(df.iloc[row, i + 2])

                # Validate the quantity
                quantity_field = Transactions._meta.get_field('quantity')
                decimal_places = quantity_field.decimal_places
                # If the number of decimal places exceeds the allowed decimal places,
                # round the quantity to the allowed number of decimal places
                if quantity.as_tuple().exponent < -decimal_places:
                    quantity = quantity.quantize(Decimal(10) ** -decimal_places, rounding=ROUND_DOWN)

                dividend = df.iloc[row, i + 3] if not pd.isna(df.iloc[row, i + 3]) else None
                commission = df.iloc[row, i + 4] if not pd.isna(df.iloc[row, i + 4]) else None

                if quantity > 0:
                        transaction_type = 'Buy'
                elif quantity < 0:
                    transaction_type = 'Sell'
                else:
                    transaction_type = 'Dividend'

                transaction_data = {
                    'broker': broker_id,
                    'security_name': security_name,
                    'isin': isin,
                    'date': date,
                    'type': transaction_type,
                    'currency': currency,
                    'price': price,
                    'quantity': quantity,
                    'cash_flow': dividend,
                    'commission': commission,
                }
                transactions.append(transaction_data)
            i += 1
            while i < len(df.columns) and pd.isna(df.iloc[1, i]):
                i += 1
        else:
            i += 1

    return securities, transactions

def parse_broker_cash_flows(excel_file, currency, broker_id):
    # Read the Excel file
    df = pd.read_excel(excel_file, header=3)  # Line 4 has table headers, so header=3 (0-based index)

    # Initialize an empty list to hold transaction data
    transactions = []

    # Identify columns related to 'Инвестиции' and their corresponding currencies by processing columns in reverse order
    # currency_columns = {}
    # current_currency = None
    # for col in reversed(df.columns):
    #     if 'Cash' in col:
    #         current_currency = col.split('(')[-1].split(')')[0]
    #         if current_currency == '£':
    #             current_currency = 'GBP'
    #     elif 'Инвестиции' in col and current_currency:
    #         currency_columns[col] = current_currency
    #         current_currency = None

    # Iterate over each row in the DataFrame
    for index, row in df.iterrows():
        date = row['Дата'].strftime("%Y-%m-%d")

        # Check if there is any data in the current row
        if pd.notna(date):
            # for inv_col, currency in currency_columns.items():
            cash_investment = row['Инвестиции']
            commission = row['Комиссия']
            tax = row['Tax']

            if pd.notna(cash_investment):
                # Determine the type of transaction based on cash_investment
                if cash_investment > 0:
                    transaction_type = 'Cash in'
                elif cash_investment < 0:
                    transaction_type = 'Cash out'

                transaction_data = {
                        'broker': broker_id,
                        'date': date,
                        'type': transaction_type,
                        'currency': currency,
                        'cash_flow': round(cash_investment, 2),
                        'commission': None,
                        'tax': None,
                    }
                transactions.append(transaction_data)

            if pd.notna(commission):
                transaction_data = {
                    'broker': broker_id,
                    'date': date,
                    'type': 'Broker commission',
                    'currency': currency,
                    'cash_flow': None,
                    'commission': round(commission, 2),
                    'tax': None,
                }
                transactions.append(transaction_data)
            
            if pd.notna(tax):
                transaction_data = {
                    'broker': broker_id,
                    'date': date,
                    'type': 'Tax',
                    'currency': currency,
                    'cash_flow': None,
                    'commission': None,
                    'tax': round(tax, 2),
                }
                transactions.append(transaction_data)

    return transactions

def get_last_exit_date_for_brokers(selected_brokers, date):
    """
    Calculate the last date after which all activities ended and no asset was opened for the selected brokers.

    Args:
        selected_brokers (list): List of broker IDs to include in the calculation.

    Returns:
        date: The last date after which all activities ended and no asset was opened for the selected brokers.
    """
    # Step 1: Check the position of each security at the current date
    for broker in Brokers.objects.filter(id__in=selected_brokers):
        for security in broker.securities.all():
            if security.position(date, [broker.id]) != 0:
                return date

    # Step 2: If positions for all securities at the current date are zero, find the latest transaction date
    latest_transaction_date = Transactions.objects.filter(broker_id__in=selected_brokers, date__lte=date).order_by('-date').values_list('date', flat=True).first()
    
    return latest_transaction_date

# Collect data for summary financials table
def summary_over_time_old(user, effective_date, selected_brokers, currency_target, number_of_digits):
    start_time = time.time()
    start_t = time.time()

    # Determine the starting year
    first_transaction = Transactions.objects.filter(broker_id__in=selected_brokers, date__lte=effective_date).order_by('date').first()
    if first_transaction:
        start_year = first_transaction.date.year
    else:
        context = {
            "years": [],
            "lines": [],
        }
        return context
    
    print("1073. Time taken for determining start year:", time.time() - start_t)

    # Determine the ending year
    start_t = time.time()
    last_exit_date = get_last_exit_date_for_brokers(selected_brokers, effective_date)
    last_year = last_exit_date.year if last_exit_date else effective_date.year
    print("1079. Time taken for determining end year:", time.time() - start_t)

    years = list(range(start_year, last_year + 1))

    # Line names
    line_names = [
        "BoP NAV", "Invested", "Cash-out", "Price change", "Capital distribution",
        "Commission", "Tax", "FX", "EoP NAV", "TSR"
    ]
    
    lines = []

    # Get brokers and currencies
    start_t = time.time()
    brokers = Brokers.objects.filter(id__in=selected_brokers, investor=user).all()
    currencies = set()
    for broker in brokers:
        currencies.update(broker.get_currencies())
    print("1097. Time taken for fetching brokers and currencies:", time.time() - start_t)
            
    # Precompute values for each year
    nav_values = {}
    invested_values = {}
    cash_out_values = {}
    bop_nav = 0
    
    start_t = time.time()
    for year in years:
        
        if year != start_year:
            bop_nav = NAV_at_date(user.id, selected_brokers, date(year-1, 12, 31), currency_target)['Total NAV']

        nav_values[year] = bop_nav

        invested = 0
        cash_out = 0
        for cur in currencies:
            transactions = Transactions.objects.filter(broker_id__in=selected_brokers, currency=cur, type__in=['Cash in', 'Cash out'], date__year=year).values_list('cash_flow', 'type', 'date')
            for cash_flow, transaction_type, transaction_date in transactions:
                if transaction_type == 'Cash in':
                    invested += cash_flow * FX.get_rate(cur, currency_target, transaction_date)['FX']
                elif transaction_type == 'Cash out':
                    cash_out += cash_flow * FX.get_rate(cur, currency_target, transaction_date)['FX']

        invested_values[year] = invested
        cash_out_values[year] = cash_out
    
    print("1128. Time taken for calculating NAVs, invested and cash-out:", time.time() - start_t)

    for line_name in line_names:
        start_line_time = time.time()
        line_data = {"name": line_name, "data": {}, "percentage": {}, "has_percentage": line_name not in ["BoP NAV", "Invested", "Cash-out", "TSR"]}

        for year in years:
            end_of_year_date = date(year, 12, 31)
            start_of_year_date = date(year, 1, 1)

            bop_nav = nav_values[year]
            invested = invested_values[year]
            cash_out = cash_out_values[year]

            # Collect data for each line
            # start_t = time.time()
            if line_name == "BoP NAV":
                line_data["data"][year] = bop_nav
            
            elif line_name == "Invested":
                line_data["data"][year] = invested
                 
            elif line_name == "Cash-out":
                line_data["data"][year] = cash_out
                                
            elif line_name == "Price change":
                realized_gl = 0
                unrealized_gl = 0

                for asset in Assets.objects.filter(investor=user, brokers__id__in=selected_brokers):
                    asset_realized_gl = asset.realized_gain_loss(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)
                    realized_gl += asset_realized_gl["all_time"] if asset_realized_gl else 0

                    unrealized_gl += asset.unrealized_gain_loss(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)

                line_data["data"][year] = realized_gl + unrealized_gl
                # line_data["percentage"][year] = (line_data["data"][year] / (bop_nav + invested + cash_out)) if bop_nav != 0 else 0

            elif line_name == "Capital distribution":
                line_data["data"][year] = 0
                
                for asset in Assets.objects.filter(investor=user, brokers__id__in=selected_brokers):
                    line_data["data"][year] += asset.get_capital_distribution(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)
                
                # line_data["percentage"][year] = (line_data["data"][year] / (bop_nav + invested + cash_out)) if bop_nav != 0 else 0
            
            elif line_name == "Commission":
                line_data["data"][year] = 0

                for cur in currencies:
                    transactions = Transactions.objects.filter(broker_id__in=selected_brokers, currency=cur, date__year=year).values_list('commission', 'date')
                    for commission, transaction_date in transactions:
                        if commission:
                            line_data["data"][year] += commission * FX.get_rate(cur, currency_target, transaction_date)['FX']
                
                # line_data["percentage"][year] = (line_data["data"][year] / (bop_nav + invested + cash_out)) if bop_nav != 0 else 0
            
            elif line_name == "Tax":
                line_data["data"][year] = 0

                for cur in currencies:
                    transactions = Transactions.objects.filter(broker_id__in=selected_brokers, currency=cur, type='Tax', date__year=year).values_list('cash_flow', 'date')
                    for cash_flow, transaction_date in transactions:
                        line_data["data"][year] += cash_flow * FX.get_rate(cur, currency_target, transaction_date)['FX']
                
                # line_data["percentage"][year] = (line_data["data"][year] / (bop_nav + invested + cash_out)) if bop_nav != 0 else 0
            
            # elif line_name == "FX":
                # line_data["data"][year] = Assets.get_fx_impact(None, end_of_year_date, currency_target, broker_id_list=selected_brokers)
                # bop_nav = NAV_at_date(user.id, selected_brokers, date(year-1, 12, 31), currency_target)['Total NAV']
                # line_data["percentage"][year] = (line_data["data"][year] / bop_nav) * 100 if bop_nav != 0 else 0
            
            elif line_name == "EoP NAV":
                if year != last_year:
                    eop_nav = nav_values[year + 1]
                else:
                    eop_nav = NAV_at_date(user.id, selected_brokers, end_of_year_date, currency_target)['Total NAV']
                line_data["data"][year] = eop_nav
            
            elif line_name == "TSR":
                line_data["data"][year] = Irr(user.id, end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)

        # print(f"1192. End of calculating {line_name}. Time taken for {line_name} for year {year}:", time.time() - start_line_time)
        
        # Calculate YTD and All-time values
        # start_t = time.time()
        current_year = effective_date.year
        line_data["data"]["YTD"] = line_data["data"].get(current_year, 0)
        line_data["data"]["All-time"] = sum(value for year, value in line_data["data"].items() if isinstance(year, int))
        
        # if line_data["has_percentage"]:
        #     line_data["percentage"]["YTD"] = line_data["percentage"].get(current_year, 0)
        #     line_data["percentage"]["All-time"] = sum(value for year, value in line_data["percentage"].items() if isinstance(year, int))

        line_data["data"]["All-time"] = 0
        
        if line_name == 'TSR':
            line_data["data"]["All-time"] = format_percentage(Irr(user.id, effective_date, currency_target, broker_id_list=selected_brokers), digits=1)
        
        if line_name == 'EoP NAV':
            line_data["data"]["All-time"] = line_data["data"]["YTD"]
        
        for year, value in line_data["data"].items():
            if isinstance(year, int) and line_name != "EoP NAV" and line_name != "TSR" and line_name != "BoP NAV":
                line_data["data"]["All-time"] += value
            
            if line_name == 'TSR':
                line_data["data"][year] = format_percentage(line_data["data"][year], digits=1)
            else:
                line_data["data"][year] = currency_format(line_data["data"][year], currency_target, number_of_digits)
        
        # for year, value in line_data['percentage'].items():
        #     line_data['percentage'][year] = format_percentage(line_data['percentage'][year], digits=1)

        lines.append(line_data)
        print(f"1240. Finished {line_name}. Time taken: {time.time() - start_line_time}")

    context = {
        "years": years,
        "lines": lines,
    }

    print("1247. Total time taken:", time.time() - start_time)

    return context

def summary_over_time(user, effective_date, selected_brokers, currency_target, number_of_digits):
    start_time = time.time()
    start_t = time.time()

    # Determine the starting year
    first_transaction = Transactions.objects.filter(broker_id__in=selected_brokers, date__lte=effective_date).order_by('date').first()
    if not first_transaction:
        return {"years": [], "lines": []}
    
    start_year = first_transaction.date.year

    # Determine the ending year
    last_exit_date = get_last_exit_date_for_brokers(selected_brokers, effective_date)
    last_year = last_exit_date.year if last_exit_date else effective_date.year

    years = list(range(start_year, last_year + 1))

    line_names = [
        "BoP NAV", "Invested", "Cash-out", "Price change", "Capital distribution",
        "Commission", "Tax", "FX", "EoP NAV", "TSR"
    ]
    
    lines = {name: {"name": name, "data": {}, "percentage": {}, "has_percentage": name not in ["BoP NAV", "Invested", "Cash-out", "TSR"]} for name in line_names}

    print("1276. Time taken for preparations:", time.time() - start_t)

    start_t = time.time()
    # Get brokers and currencies
    brokers = Brokers.objects.filter(id__in=selected_brokers, investor=user).all()
    currencies = set()
    for broker in brokers:
        currencies.update(broker.get_currencies())
    print("1284. Time taken for getting currencies:", time.time() - start_t)

    # Batch query for transactions
    start_t = time.time()
    transactions = Transactions.objects.filter(
        broker_id__in=selected_brokers,
        date__year__in=years
    ).values('cash_flow', 'type', 'commission', 'date', 'currency')

    transactions_df = pd.DataFrame(list(transactions))
    transactions_df['year'] = transactions_df['date'].apply(lambda x: x.year)
    
    # Add FX rate to transactions DataFrame
    transactions_df['fx_rate'] = transactions_df.apply(
        lambda row: FX.get_rate(row['currency'], currency_target, row['date'])['FX'], axis=1
    )
    
    print("1301. Time taken for getting and preparint transactoins:", time.time() - start_t)

    # Fetch all assets once
    assets = Assets.objects.filter(investor=user, brokers__id__in=selected_brokers)

    # Initialize BoP NAV
    bop_nav = 0

    for year in years:
        start_y = time.time()
        start_t = time.time()

        end_of_year_date = date(year, 12, 31)
        start_of_year_date = date(year, 1, 1)
        
        year_transactions = transactions_df[transactions_df['year'] == year]
        
        # Calculate BoP NAV
        if year != start_year:
            bop_nav = lines["EoP NAV"]["data"][year - 1]

        lines["BoP NAV"]["data"][year] = bop_nav
        print(f"1323. Time taken for year preparatory calcs for {year}:", time.time() - start_t)

        # Calculate Invested and Cash-out
        start_t = time.time()
        invested = round((year_transactions[year_transactions['type'] == 'Cash in']['cash_flow'] * 
                    year_transactions[year_transactions['type'] == 'Cash in']['fx_rate']).sum(), 2)
        cash_out = round((year_transactions[year_transactions['type'] == 'Cash out']['cash_flow'] * 
                    year_transactions[year_transactions['type'] == 'Cash out']['fx_rate']).sum(), 2)
        
        lines["Invested"]["data"][year] = invested
        lines["Cash-out"]["data"][year] = cash_out

        print(f"1335. Time taken for calculating invested and cash_out for {year}:", time.time() - start_t)

        # Calculate Price change, Capital distribution, Commission, and Tax
        realized_gl = 0
        unrealized_gl = 0
        capital_distribution = 0

        start_t = time.time()
        for asset in assets:
            asset_realized_gl = asset.realized_gain_loss(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)
            realized_gl += asset_realized_gl["all_time"] if asset_realized_gl else 0
            unrealized_gl += asset.unrealized_gain_loss(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)
            capital_distribution += asset.get_capital_distribution(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)

        lines["Price change"]["data"][year] = realized_gl + unrealized_gl
        lines["Capital distribution"]["data"][year] = capital_distribution
        
        print(f"1352. Time taken for calculating Price change and Capital distribution for {year}:", time.time() - start_t)

        start_t = time.time()
        lines["Commission"]["data"][year] = round((year_transactions['commission'] * 
                                             year_transactions['fx_rate']).sum(), 2)
        lines["Tax"]["data"][year] = round((year_transactions[year_transactions['type'] == 'Tax']['cash_flow'] * 
                                      year_transactions[year_transactions['type'] == 'Tax']['fx_rate']).sum(), 2)

        print(f"1360. Time taken for calculating Commission and Tax for {year}:", time.time() - start_t)

        # Calculate EoP NAV
        start_t = time.time()
        eop_nav = NAV_at_date(user.id, selected_brokers, end_of_year_date, currency_target)['Total NAV']
        lines["EoP NAV"]["data"][year] = eop_nav
        print(f"1366. Time taken for calculating EoP NAV for {year}:", time.time() - start_t)

        # Calculate TSR
        start_t = time.time()
        lines["TSR"]["data"][year] = Irr(user.id, end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)
        print(f"1371. Time taken for calculating TSR for {year}:", time.time() - start_t)

        # Calculate FX impact
        start_t = time.time()
        components_sum = (
            bop_nav + 
            invested + 
            cash_out + 
            lines["Price change"]["data"][year] + 
            lines["Capital distribution"]["data"][year] + 
            lines["Commission"]["data"][year] + 
            lines["Tax"]["data"][year]
        )
        lines["FX"]["data"][year] = eop_nav - components_sum
        print(f"1385. Time taken for calculating FX for {year}:", time.time() - start_t)

    print(f"1387. Time taken for calculating data for {year}:", time.time() - start_y)

    start_t = time.time()
    current_year = effective_date.year
    for line_name, line_data in lines.items():
        line_data["data"]["YTD"] = line_data["data"].get(current_year, 0)
        line_data["data"]["All-time"] = 0

        if line_name == 'TSR':
            line_data["data"]["All-time"] = format_percentage(Irr(user.id, effective_date, currency_target, broker_id_list=selected_brokers), digits=1)

        if line_name == 'EoP NAV':
            line_data["data"]["All-time"] = line_data["data"]["YTD"]

        for year, value in line_data["data"].items():
            if isinstance(year, int) and line_name not in ["EoP NAV", "TSR", "BoP NAV"]:
                line_data["data"]["All-time"] += value

            if line_name == 'TSR':
                line_data["data"][year] = format_percentage(line_data["data"][year], digits=1)
            else:
                line_data["data"][year] = currency_format(line_data["data"][year], currency_target, number_of_digits)
    print("1409. Time taken for calculating All-time and formatting:", time.time() - start_t)

    context = {
        "years": years,
        "lines": list(lines.values()),
    }

    print("Total time taken:", time.time() - start_time)

    return context

