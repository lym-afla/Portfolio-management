from collections import defaultdict
from decimal import Decimal
from functools import lru_cache

from django.db import IntegrityError, transaction

from common.models import AnnualPerformance, Brokers, Assets, FX, Prices, Transactions
from django.db.models import Sum, F
from pyxirr import xirr
import pandas as pd
import time
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging

from constants import BROKER_GROUPS
from users.models import CustomUser

logger = logging.getLogger(__name__)

# Define the effective 'current' date for the application
# effective_current_date = date.today()

# Define custom selected brokers for the application
# selected_brokers = [2]

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
    # return round(current_quote.price * FX.get_rate(item.currency.upper(), currency, current_quote.date)['FX'] * item.position(date), 2)
    return round(Decimal(current_quote.price * get_fx_rate(item.currency.upper(), currency, current_quote.date) * item.position(date)), 2)

def update_analysis(analysis, key, value, date=None, currency=None, desired_currency=None):
    if currency and date and desired_currency:
        # value = round(value * FX.get_rate(currency, desired_currency, date)['FX'], 2)
        value = round(value * get_fx_rate(currency, desired_currency, date), 2)
    
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
        # converted_cash = round(balance * FX.get_rate(currency, target_currency, date)['FX'], 2)
        converted_cash = round(balance * get_fx_rate(currency, target_currency, date), 2)
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
        if asset_id is not None:
            first_transaction = transactions.order_by('date').first()
            if first_transaction is not None:
                first_transaction = first_transaction.quantity
            else:
                first_transaction = 0
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
            # fx_rate = FX.get_rate(transaction.currency.upper(), currency, transaction.date)['FX']
            fx_rate = get_fx_rate(transaction.currency.upper(), currency, transaction.date)
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
        irr = Decimal(round(xirr(transaction_dates, cash_flows), 4))
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
    try:
        if value < 0:
            return f"({cur}{-value:,.{int(digits)}f})"
        elif value == 0:
            return "–"
        elif value > 0:
            return f"{cur}{value:,.{int(digits)}f}"
    except:
        return cur
    
# Format dictionaries as strings with currency formatting
def currency_format_dict_values(data, currency, digits):
    formatted_data = {}
    for key, value in data.items():
        if isinstance(value, dict):
            # Recursively format nested dictionaries
            formatted_data[key] = currency_format_dict_values(value, currency, digits)
        elif isinstance(value, Decimal):
            if 'percentage' in str(key):
                formatted_data[key] = format_percentage(value, 1)
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
                data_dict[percentage_key][key] = str(round(Decimal(value / total * 100), 1)) + '%'
            except ZeroDivisionError:
                data_dict[percentage_key][key] = '–'

def get_chart_data(user_id, brokers, frequency, from_date, to_date, currency, breakdown):
    
    # Get the correct starting date for "All time" category
    if from_date == '1900-01-01':
        from_date = Transactions.objects.filter(investor__id=user_id, broker__in=brokers).order_by('date').first().date
        # print(f"utils.py. Line 312. From date: {from_date}")

    dates = chart_dates(from_date, to_date, frequency)
        
    chart_data = {
        'labels': chart_labels(dates, frequency),
        'datasets': [],
        'currency': currency + 'k',
    }

    previous_date = None
    NAV_previous_date = 0

    for d in dates:
        IRR = Irr(user_id, d, currency, None, brokers)
        IRR_rolling = Irr(user_id, d, currency, None, brokers, previous_date)
        if breakdown in 'No breakdown':
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
                    'label': 'Rolling IRR (RHS)',
                    'data': [IRR_rolling],
                    # 'backgroundColor': 'rgb(120, 120, 50)',
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
                chart_data['datasets'][1]['data'].append(IRR_rolling)
                chart_data['datasets'][2]['data'].append(NAV)
        elif breakdown == 'Contributions':
            NAV = Decimal(NAV_at_date(user_id, brokers, d, currency)['Total NAV'] / 1000)
            if previous_date is not None:
                contributions = Transactions.objects.filter(investor__id=user_id, broker__in=brokers, date__gt=previous_date, date__lte=d, type__in=['Cash in', 'Cash out']).aggregate(Sum('cash_flow'))['cash_flow__sum'] or 0
                contributions = Decimal(contributions) / 1000
            else:
                contributions = Transactions.objects.filter(investor__id=user_id, broker__in=brokers, date__lte=d, type__in=['Cash in', 'Cash out']).aggregate(Sum('cash_flow'))['cash_flow__sum'] or 0
                contributions = Decimal(contributions) / 1000
            return_amount = NAV - NAV_previous_date - contributions
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
                    'label': 'Rolling IRR (RHS)',
                    'data': [IRR_rolling],
                    # 'backgroundColor': 'rgb(120, 120, 50)',
                    'type': 'line',
                    'yAxisID': 'y1',
                    'order': 0,
                    'datalabels': {
                        'display': 'true'
                    }
                })
                chart_data['datasets'].append({
                    'label': 'BoP NAV',
                    'data': [NAV_previous_date],
                    'backgroundColor': 'rgb(255, 0, 0)',
                    'stack': 'combined',
                    'type': 'bar',
                    'yAxisID': 'y',
                    'datalabels': {
                        'display': 'true'
                    }
                })
                chart_data['datasets'].append({
                    'label': 'Contributions',
                    'data': [contributions],
                    'backgroundColor': 'rgb(0, 128, 0)',
                    'stack': 'combined',
                    'type': 'bar',
                    'yAxisID': 'y',
                    'datalabels': {
                        'display': 'true'
                    }
                })
                chart_data['datasets'].append({
                    'label': 'Return',
                    'data': [return_amount],
                    'backgroundColor': 'rgb(0, 0, 255)',
                    'stack': 'combined',
                    'type': 'bar',
                    'yAxisID': 'y',
                    'datalabels': {
                        'display': 'true'
                    }
                })
            else:
                chart_data['datasets'][0]['data'].append(IRR)
                chart_data['datasets'][1]['data'].append(IRR_rolling)
                chart_data['datasets'][2]['data'].append(NAV_previous_date)
                chart_data['datasets'][3]['data'].append(contributions)
                chart_data['datasets'][4]['data'].append(return_amount)
            NAV_previous_date = NAV
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
                chart_data['datasets'].append({
                    'label': 'Rolling IRR (RHS)',
                    'data': [IRR_rolling],
                    # 'backgroundColor': 'rgb(120, 120, 50)',
                    'type': 'line',
                    'yAxisID': 'y1',
                    'order': 0,
                })
            else:
                chart_data['datasets'][0]['data'].append(IRR)
                chart_data['datasets'][1]['data'].append(IRR_rolling)
                
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
        
        previous_date = d - timedelta(days=1)

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

def calculate_open_table_output(user_id, portfolio, end_date, categories, use_default_currency, currency_target, selected_brokers, number_of_digits, start_date=None):
    
    # if portfolio is None:
    #     return None, None
    # else:
    portfolio_NAV = NAV_at_date(user_id, selected_brokers, end_date, currency_target)['Total NAV']
    
    totals = ['entry_value', 'current_value', 'realized_gl', 'unrealized_gl', 'capital_distribution', 'commission']
    portfolio_open_totals = {}
    
    for asset in portfolio:
    
        currency_used = None if use_default_currency else currency_target

        asset.current_position = asset.position(end_date, selected_brokers)

        if asset.current_position == 0:
            print("The position is zero. The asset is not in the portfolio.")
            return None

        position_entry_date = asset.entry_dates(end_date, selected_brokers)[-1]
        if 'investment_date' in categories:
            asset.investment_date = position_entry_date

        if start_date is None:
            start_date = position_entry_date
            
        asset.entry_price = asset.calculate_buy_in_price(end_date, currency_used, selected_brokers, start_date)
        asset.entry_value = asset.entry_price * asset.current_position
        asset.entry_price = currency_format(asset.entry_price, asset.currency if use_default_currency else currency_target, number_of_digits)
        
        # print(f'utils.py. LIne 508. Entry date: {entry_date}')
        
        if 'current_value' in categories:
            asset.current_price = asset.price_at_date(end_date, currency_used).price
            asset.current_value = asset.current_price * asset.current_position
            asset.share_of_portfolio = asset.price_at_date(end_date, currency_used).price * asset.current_position / portfolio_NAV
            
            # Formatting
            asset.current_price = currency_format(asset.current_price, asset.currency if use_default_currency else currency_target, number_of_digits)
            asset.current_value = currency_format(asset.current_value, asset.currency if use_default_currency else currency_target, number_of_digits)
            asset.share_of_portfolio = format_percentage(asset.share_of_portfolio)
        
        if 'realized_gl' in categories:
            asset.realized_gl = asset.realized_gain_loss(end_date, currency_used, selected_brokers, start_date)['current_position']
        else:
            asset.realized_gl = 0

        if 'unrealized_gl' in categories:
            asset.unrealized_gl = asset.unrealized_gain_loss(end_date, currency_used, selected_brokers, start_date)
        else:
            asset.unrealized_gl = 0
        
        asset.price_change_percentage = (asset.realized_gl + asset.unrealized_gl) / asset.entry_value if asset.entry_value > 0 else 'N/R'
        
        if 'capital_distribution' in categories:
            asset.capital_distribution = asset.get_capital_distribution(end_date, currency_used, selected_brokers, start_date)
            asset.capital_distribution_percentage = asset.capital_distribution / asset.entry_value if asset.entry_value > 0 else 'N/R'
        else:
            asset.capital_distribution = 0

        if 'commission' in categories:
            asset.commission = asset.get_commission(end_date, currency_used, selected_brokers, start_date)
            asset.commission_percentage = asset.commission / asset.entry_value if asset.entry_value > 0 else 'N/R'
        else:
            asset.commission = 0
            
        asset.total_return_amount = asset.realized_gl + asset.unrealized_gl + asset.capital_distribution + asset.commission
        asset.total_return_percentage = asset.total_return_amount / asset.entry_value if asset.entry_value > 0 else 'N/R'
        
        # Calculate IRR for security
        currency_used = asset.currency if use_default_currency else currency_target
        asset.irr = format_percentage(Irr(user_id, end_date, currency_used, asset_id=asset.id, broker_id_list=selected_brokers, start_date=start_date))
        
        # Calculating totals
        for key in (['entry_value', 'total_return_amount'] + list(set(totals) & set(categories))):

            if not use_default_currency:
                addition = getattr(asset, key)
            else:
                if key == 'entry_value':
                    addition = asset.entry_value
                elif key == 'total_return_amount':
                    asset.realized_gl = asset.realized_gain_loss(end_date, currency_target, selected_brokers, start_date)['current_position']
                    asset.unrealized_gl = asset.unrealized_gain_loss(end_date, currency_target, selected_brokers, start_date)
                    asset.capital_distribution = asset.get_capital_distribution(end_date, currency_target, selected_brokers, start_date)
                    asset.commission = asset.get_commission(end_date, currency_target, selected_brokers, start_date)
                    
                    addition = asset.realized_gl + asset.unrealized_gl + asset.capital_distribution + asset.commission
                    # print("Line 709", addition)
                elif key == 'current_value':
                    addition = asset.price_at_date(end_date, currency_target).price * asset.current_position
                elif key == 'realized_gl':
                    addition = asset.realized_gain_loss(end_date, currency_target, selected_brokers, start_date)['current_position']
                elif key == 'unrealized_gl':
                    addition = asset.unrealized_gain_loss(end_date, currency_target, selected_brokers, start_date)
                elif key == 'capital_distribution':
                    addition = asset.get_capital_distribution(end_date, currency_target, selected_brokers, start_date)
                elif key == 'commission':
                    addition = asset.get_commission(end_date, currency_target, selected_brokers, start_date)
                
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
                    # fx_rate = FX.get_rate(transaction.currency, currency_used, transaction.date)['FX']
                    fx_rate = get_fx_rate(transaction.currency, currency_used, transaction.date)
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
                    # fx_rate = FX.get_rate(transaction.currency, currency_used, transaction.date)['FX']
                    fx_rate = get_fx_rate(transaction.currency, currency_used, transaction.date)
                total_value += transaction.price * abs(transaction.quantity) * fx_rate
                total_quantity += abs(transaction.quantity)
            position['exit_price'] = total_value / total_quantity if total_quantity else Decimal(0)
            position['exit_value'] = total_value

            if 'realized_gl' in categories:
                
                position_transactions = asset.transactions.filter(investor__id=user_id, date__lte=exit_date, date__gte=entry_date, quantity__isnull=False)
                total_gl = 0
                if currency_used is not None:
                    for transaction in position_transactions:
                        # fx_rate = FX.get_rate(transaction.currency, currency_used, transaction.date)['FX']
                        fx_rate = get_fx_rate(transaction.currency, currency_used, transaction.date)
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
                            fx_rate = get_fx_rate(transaction.currency, currency_target, transaction.date)
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

    quantity_field = Transactions._meta.get_field('quantity')
    quantity_decimal_places = quantity_field.decimal_places
    price_field = Transactions._meta.get_field('price')
    price_decimal_places = price_field.decimal_places

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
                price = round(Decimal(df.iloc[row, i + 1]), price_decimal_places)
                quantity = round(Decimal(df.iloc[row, i + 2]), quantity_decimal_places) if not pd.isna(df.iloc[row, i + 2]) else None
                
                # # Validate the quantity
                # quantity_field = Transactions._meta.get_field('quantity')
                # decimal_places = quantity_field.decimal_places
                # # If the number of decimal places exceeds the allowed decimal places,
                # # round the quantity to the allowed number of decimal places
                # if quantity is not None:
                #     if int(quantity.as_tuple().exponent) < -decimal_places:
                #         quantity = quantity.quantize(Decimal(10) ** -decimal_places, rounding=ROUND_DOWN)

                dividend = round(Decimal(df.iloc[row, i + 3]), 2) if not pd.isna(df.iloc[row, i + 3]) else None
                commission = round(Decimal(df.iloc[row, i + 4]), 2) if not pd.isna(df.iloc[row, i + 4]) else None

                if quantity is None and dividend is None and commission is None:
                    print("utils. 1059. Skipping row for: ", security_name)
                    continue

                if quantity is not None:
                    if quantity > 0:
                        transaction_type = 'Buy'
                    elif quantity < 0:
                        transaction_type = 'Sell'
                    else:
                        transaction_type = 'Dividend'
                else:
                    transaction_type = None

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
            if 'Tax' in row:
                tax = row['Tax']
            else:
                tax = None

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
                        'cash_flow': round(Decimal(cash_investment), 2),
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
                    'commission': round(Decimal(commission), 2),
                    'tax': None,
                }
                transactions.append(transaction_data)
            
            if tax is not None and pd.notna(tax):
                transaction_data = {
                    'broker': broker_id,
                    'date': date,
                    'type': 'Tax',
                    'currency': currency,
                    'cash_flow': None,
                    'commission': None,
                    'tax': round(Decimal(tax), 2),
                }
                transactions.append(transaction_data)

    return transactions


def import_FX_from_csv(file_path):
    # Read the CSV file
    df = pd.read_csv(file_path)

    # Convert the 'date' column to datetime format with the specified format
    df['date'] = pd.to_datetime(df['date'], format='%d/%m/%Y')

    # Iterate through the DataFrame and update the FX model
    for index, row in df.iterrows():
        date = pd.to_datetime(row['date']).date()
        investor_id = row['investor_id']
        # print(date)
        
        # Prepare the data for the FX model
        fx_data = {
            'date': date,
            'investor_id': investor_id,
            'USDEUR': row['USDEUR'] if not pd.isna(row['USDEUR']) else None,
            'CHFGBP': row['CHFGBP'] if not pd.isna(row['CHFGBP']) else None,
            'RUBUSD': row['RUBUSD'] if not pd.isna(row['RUBUSD']) else None,
            'PLNUSD': row['PLNUSD'] if not pd.isna(row['PLNUSD']) else None,
            'USDGBP': row['USDGBP'] if not pd.isna(row['USDGBP']) else None,
        }
        
        # Update or create the FX entry
        try:
            fx_instance, created = FX.objects.update_or_create(
                date=fx_data['date'], investor_id=fx_data['investor_id'],
                defaults=fx_data
            )
            print(f"{'Created' if created else 'Updated'} FX for date {date} and investor {investor_id}")
        except IntegrityError as e:
            print(f"Error updating FX for date {date} and investor {investor_id}: {e}")

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
    
    if latest_transaction_date is None:
        return date
    
    return latest_transaction_date

# Collect data for summary financials table
# def summary_over_time_old(user, effective_date, selected_brokers, currency_target, number_of_digits):
#     start_time = time.time()
#     start_t = time.time()

#     # Determine the starting year
#     first_transaction = Transactions.objects.filter(broker_id__in=selected_brokers, date__lte=effective_date).order_by('date').first()
#     if first_transaction:
#         start_year = first_transaction.date.year
#     else:
#         context = {
#             "years": [],
#             "lines": [],
#         }
#         return context
    
#     print("1073. Time taken for determining start year:", time.time() - start_t)

#     # Determine the ending year
#     start_t = time.time()
#     last_exit_date = get_last_exit_date_for_brokers(selected_brokers, effective_date)
#     last_year = last_exit_date.year if last_exit_date else effective_date.year
#     print("1079. Time taken for determining end year:", time.time() - start_t)

#     years = list(range(start_year, last_year + 1))

#     # Line names
#     line_names = [
#         "BoP NAV", "Invested", "Cash-out", "Price change", "Capital distribution",
#         "Commission", "Tax", "FX", "EoP NAV", "TSR"
#     ]
    
#     lines = []

#     # Get brokers and currencies
#     start_t = time.time()
#     brokers = Brokers.objects.filter(id__in=selected_brokers, investor=user).all()
#     currencies = set()
#     for broker in brokers:
#         currencies.update(broker.get_currencies())
#     print("1097. Time taken for fetching brokers and currencies:", time.time() - start_t)
            
#     # Precompute values for each year
#     nav_values = {}
#     invested_values = {}
#     cash_out_values = {}
#     bop_nav = 0
    
#     start_t = time.time()
#     for year in years:
        
#         if year != start_year:
#             bop_nav = NAV_at_date(user.id, selected_brokers, date(year-1, 12, 31), currency_target)['Total NAV']

#         nav_values[year] = bop_nav

#         invested = 0
#         cash_out = 0
#         for cur in currencies:
#             transactions = Transactions.objects.filter(broker_id__in=selected_brokers, currency=cur, type__in=['Cash in', 'Cash out'], date__year=year).values_list('cash_flow', 'type', 'date')
#             for cash_flow, transaction_type, transaction_date in transactions:
#                 if transaction_type == 'Cash in':
#                     invested += cash_flow * FX.get_rate(cur, currency_target, transaction_date)['FX']
#                 elif transaction_type == 'Cash out':
#                     cash_out += cash_flow * FX.get_rate(cur, currency_target, transaction_date)['FX']

#         invested_values[year] = invested
#         cash_out_values[year] = cash_out
    
#     print("1128. Time taken for calculating NAVs, invested and cash-out:", time.time() - start_t)

#     for line_name in line_names:
#         start_line_time = time.time()
#         line_data = {"name": line_name, "data": {}, "percentage": {}, "has_percentage": line_name not in ["BoP NAV", "Invested", "Cash-out", "TSR"]}

#         for year in years:
#             end_of_year_date = date(year, 12, 31)
#             start_of_year_date = date(year, 1, 1)

#             bop_nav = nav_values[year]
#             invested = invested_values[year]
#             cash_out = cash_out_values[year]

#             # Collect data for each line
#             # start_t = time.time()
#             if line_name == "BoP NAV":
#                 line_data["data"][year] = bop_nav
            
#             elif line_name == "Invested":
#                 line_data["data"][year] = invested
                 
#             elif line_name == "Cash-out":
#                 line_data["data"][year] = cash_out
                                
#             elif line_name == "Price change":
#                 realized_gl = 0
#                 unrealized_gl = 0

#                 for asset in Assets.objects.filter(investor=user, brokers__id__in=selected_brokers):
#                     asset_realized_gl = asset.realized_gain_loss(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)
#                     realized_gl += asset_realized_gl["all_time"] if asset_realized_gl else 0

#                     unrealized_gl += asset.unrealized_gain_loss(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)

#                 line_data["data"][year] = realized_gl + unrealized_gl
#                 # line_data["percentage"][year] = (line_data["data"][year] / (bop_nav + invested + cash_out)) if bop_nav != 0 else 0

#             elif line_name == "Capital distribution":
#                 line_data["data"][year] = 0
                
#                 for asset in Assets.objects.filter(investor=user, brokers__id__in=selected_brokers):
#                     line_data["data"][year] += asset.get_capital_distribution(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)
                
#                 # line_data["percentage"][year] = (line_data["data"][year] / (bop_nav + invested + cash_out)) if bop_nav != 0 else 0
            
#             elif line_name == "Commission":
#                 line_data["data"][year] = 0

#                 for cur in currencies:
#                     transactions = Transactions.objects.filter(broker_id__in=selected_brokers, currency=cur, date__year=year).values_list('commission', 'date')
#                     for commission, transaction_date in transactions:
#                         if commission:
#                             line_data["data"][year] += commission * FX.get_rate(cur, currency_target, transaction_date)['FX']
                
#                 # line_data["percentage"][year] = (line_data["data"][year] / (bop_nav + invested + cash_out)) if bop_nav != 0 else 0
            
#             elif line_name == "Tax":
#                 line_data["data"][year] = 0

#                 for cur in currencies:
#                     transactions = Transactions.objects.filter(broker_id__in=selected_brokers, currency=cur, type='Tax', date__year=year).values_list('cash_flow', 'date')
#                     for cash_flow, transaction_date in transactions:
#                         line_data["data"][year] += cash_flow * FX.get_rate(cur, currency_target, transaction_date)['FX']
                
#                 # line_data["percentage"][year] = (line_data["data"][year] / (bop_nav + invested + cash_out)) if bop_nav != 0 else 0
            
#             # elif line_name == "FX":
#                 # line_data["data"][year] = Assets.get_fx_impact(None, end_of_year_date, currency_target, broker_id_list=selected_brokers)
#                 # bop_nav = NAV_at_date(user.id, selected_brokers, date(year-1, 12, 31), currency_target)['Total NAV']
#                 # line_data["percentage"][year] = (line_data["data"][year] / bop_nav) * 100 if bop_nav != 0 else 0
            
#             elif line_name == "EoP NAV":
#                 if year != last_year:
#                     eop_nav = nav_values[year + 1]
#                 else:
#                     eop_nav = NAV_at_date(user.id, selected_brokers, end_of_year_date, currency_target)['Total NAV']
#                 line_data["data"][year] = eop_nav
            
#             elif line_name == "TSR":
#                 line_data["data"][year] = Irr(user.id, end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)

#         # print(f"1192. End of calculating {line_name}. Time taken for {line_name} for year {year}:", time.time() - start_line_time)
        
#         # Calculate YTD and All-time values
#         # start_t = time.time()
#         current_year = effective_date.year
#         line_data["data"]["YTD"] = line_data["data"].get(current_year, 0)
#         line_data["data"]["All-time"] = sum(value for year, value in line_data["data"].items() if isinstance(year, int))
        
#         # if line_data["has_percentage"]:
#         #     line_data["percentage"]["YTD"] = line_data["percentage"].get(current_year, 0)
#         #     line_data["percentage"]["All-time"] = sum(value for year, value in line_data["percentage"].items() if isinstance(year, int))

#         line_data["data"]["All-time"] = 0
        
#         if line_name == 'TSR':
#             line_data["data"]["All-time"] = format_percentage(Irr(user.id, effective_date, currency_target, broker_id_list=selected_brokers), digits=1)
        
#         if line_name == 'EoP NAV':
#             line_data["data"]["All-time"] = line_data["data"]["YTD"]
        
#         for year, value in line_data["data"].items():
#             if isinstance(year, int) and line_name != "EoP NAV" and line_name != "TSR" and line_name != "BoP NAV":
#                 line_data["data"]["All-time"] += value
            
#             if line_name == 'TSR':
#                 line_data["data"][year] = format_percentage(line_data["data"][year], digits=1)
#             else:
#                 line_data["data"][year] = currency_format(line_data["data"][year], currency_target, number_of_digits)
        
#         # for year, value in line_data['percentage'].items():
#         #     line_data['percentage'][year] = format_percentage(line_data['percentage'][year], digits=1)

#         lines.append(line_data)
#         print(f"1240. Finished {line_name}. Time taken: {time.time() - start_line_time}")

#     context = {
#         "years": years,
#         "lines": lines,
#     }

#     print("1247. Total time taken:", time.time() - start_time)

#     return context

# def summary_over_time_old(user, effective_date, selected_brokers, currency_target):
#     start_time = time.time()
#     start_t = time.time()

#     # Determine the starting year
#     first_transaction = Transactions.objects.filter(broker_id__in=selected_brokers, date__lte=effective_date).order_by('date').first()
#     if not first_transaction:
#         return {"years": [], "lines": []}
    
#     start_year = first_transaction.date.year

#     # Determine the ending year
#     last_exit_date = get_last_exit_date_for_brokers(selected_brokers, effective_date)
#     last_year = last_exit_date.year if last_exit_date else effective_date.year

#     years = list(range(start_year, last_year + 1))

#     line_names = [
#         "BoP NAV", "Invested", "Cash-out", "Price change", "Capital distribution",
#         "Commission", "Tax", "FX", "EoP NAV", "TSR"
#     ]
    
#     lines = {name: {"name": name, "data": {}, "percentage": {}, "has_percentage": name not in ["BoP NAV", "Invested", "Cash-out", "TSR"]} for name in line_names}

#     print("1276. Time taken for preparations:", time.time() - start_t)

#     start_t = time.time()
#     # Get brokers and currencies
#     brokers = Brokers.objects.filter(id__in=selected_brokers, investor=user).all()
#     currencies = set()
#     for broker in brokers:
#         currencies.update(broker.get_currencies())
#     print("1284. Time taken for getting currencies:", time.time() - start_t)

#     # Batch query for transactions
#     start_t = time.time()
#     transactions = Transactions.objects.filter(
#         investor=user,
#         broker_id__in=selected_brokers,
#         date__year__in=years
#     ).values('cash_flow', 'type', 'commission', 'date', 'currency')

#     transactions_df = pd.DataFrame(list(transactions))
#     transactions_df['year'] = transactions_df['date'].apply(lambda x: x.year)
    
#     # Add FX rate to transactions DataFrame
#     transactions_df['fx_rate'] = transactions_df.apply(
#         lambda row: FX.get_rate(row['currency'], currency_target, row['date'])['FX'], axis=1
#     )
    
#     print("1301. Time taken for getting and preparing transactions:", time.time() - start_t)

#     # Fetch all assets once
#     assets = Assets.objects.filter(investor=user, brokers__id__in=selected_brokers)

#     # Initialize BoP NAV
#     bop_nav = Decimal(0)

#     for year in years:
#         start_y = time.time()
#         start_t = time.time()

#         end_of_year_date = date(year, 12, 31)
#         start_of_year_date = date(year, 1, 1)
        
#         year_transactions = transactions_df[transactions_df['year'] == year]
        
#         # Calculate BoP NAV
#         if year != start_year:
#             bop_nav = lines["EoP NAV"]["data"][year - 1]

#         lines["BoP NAV"]["data"][year] = bop_nav
#         print(f"1323. Time taken for year preparatory calcs for {year}:", time.time() - start_t)

#         # Calculate Invested and Cash-out
#         start_t = time.time()
#         invested = round((year_transactions[year_transactions['type'] == 'Cash in']['cash_flow'] * 
#                     year_transactions[year_transactions['type'] == 'Cash in']['fx_rate']).sum(), 2)
#         cash_out = round((year_transactions[year_transactions['type'] == 'Cash out']['cash_flow'] * 
#                     year_transactions[year_transactions['type'] == 'Cash out']['fx_rate']).sum(), 2)
        
#         lines["Invested"]["data"][year] = invested
#         lines["Cash-out"]["data"][year] = cash_out

#         print(f"1335. Time taken for calculating invested and cash_out for {year}:", time.time() - start_t)

#         # Calculate Price change, Capital distribution, Commission, and Tax
#         realized_gl = Decimal(0)
#         unrealized_gl = Decimal(0)
#         capital_distribution = Decimal(0)

#         start_t = time.time()
#         for asset in assets:
#             asset_realized_gl = asset.realized_gain_loss(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)
#             realized_gl += asset_realized_gl["all_time"] if asset_realized_gl else 0
#             unrealized_gl += asset.unrealized_gain_loss(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)
#             capital_distribution += asset.get_capital_distribution(end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)

#         lines["Price change"]["data"][year] = realized_gl + unrealized_gl
#         lines["Capital distribution"]["data"][year] = capital_distribution
        
#         print(f"1352. Time taken for calculating Price change and Capital distribution for {year}:", time.time() - start_t)

#         start_t = time.time()
#         lines["Commission"]["data"][year] = round((year_transactions['commission'] * 
#                                              year_transactions['fx_rate']).sum(), 2)
#         lines["Tax"]["data"][year] = round((year_transactions[year_transactions['type'] == 'Tax']['cash_flow'] * 
#                                       year_transactions[year_transactions['type'] == 'Tax']['fx_rate']).sum(), 2)

#         print(f"1360. Time taken for calculating Commission and Tax for {year}:", time.time() - start_t)

#         # Calculate EoP NAV
#         start_t = time.time()
#         eop_nav = NAV_at_date(user.id, selected_brokers, end_of_year_date, currency_target)['Total NAV']
#         lines["EoP NAV"]["data"][year] = eop_nav
#         print(f"1366. Time taken for calculating EoP NAV for {year}:", time.time() - start_t)

#         # Calculate TSR
#         start_t = time.time()
#         lines["TSR"]["data"][year] = Irr(user.id, end_of_year_date, currency_target, broker_id_list=selected_brokers, start_date=start_of_year_date)
#         print(f"1371. Time taken for calculating TSR for {year}:", time.time() - start_t)

#         # Calculate FX impact
#         start_t = time.time()
#         components_sum = (
#             bop_nav + 
#             invested + 
#             cash_out + 
#             lines["Price change"]["data"][year] + 
#             lines["Capital distribution"]["data"][year] + 
#             lines["Commission"]["data"][year] + 
#             lines["Tax"]["data"][year]
#         )
#         lines["FX"]["data"][year] = eop_nav - components_sum
#         print(f"1385. Time taken for calculating FX for {year}:", time.time() - start_t)

#     print(f"1387. Time taken for calculating data for {year}:", time.time() - start_y)

#     start_t = time.time()
#     current_year = effective_date.year
#     for line_name, line_data in lines.items():
#         line_data["data"]["YTD"] = line_data["data"].get(current_year, Decimal(0))
#         line_data["data"]["All-time"] = Decimal(0)

#         if line_name == 'TSR':
#             line_data["data"]["All-time"] = Irr(user.id, effective_date, currency_target, broker_id_list=selected_brokers)

#         if line_name == 'EoP NAV':
#             line_data["data"]["All-time"] = line_data["data"]["YTD"]

#         for year, value in line_data["data"].items():
#             if isinstance(year, int) and line_name not in ["EoP NAV", "TSR", "BoP NAV"]:
#                 line_data["data"]["All-time"] += value

#             # if line_name == 'TSR':
#             #     line_data["data"][year] = format_percentage(line_data["data"][year], digits=1)
#             # else:
#             #     line_data["data"][year] = currency_format(line_data["data"][year], currency_target, number_of_digits)
#     print("1409. Time taken for calculating All-time and formatting:", time.time() - start_t)

#     context = {
#         "years": years,
#         "lines": list(lines.values()),
#     }

#     print("Total time taken:", time.time() - start_time)

#     return context

def dashboard_summary_over_time(user, effective_date, brokers_or_group, currency_target):
    start_time = time.time()

    if isinstance(brokers_or_group, str):
        # It's a group name
        group_name = brokers_or_group
        selected_brokers = BROKER_GROUPS.get(group_name)
        if not selected_brokers:
            raise ValueError(f"Invalid group name: {group_name}")
    else:
        # It's a list of broker IDs
        selected_brokers = brokers_or_group
        group_name = None

    # Determine the starting year
    stored_data = AnnualPerformance.objects.filter(
        investor=user,
        broker__in=selected_brokers,
        currency=currency_target,
        restricted=None
    )

    first_entry = stored_data.order_by('year').first()
    if not first_entry:
        return {"years": [], "lines": []}
    
    start_year = first_entry.year
    
    last_exit_date = get_last_exit_date_for_brokers(selected_brokers, effective_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_date.year else effective_date.year - 1
    years = list(range(start_year, last_year + 1))

    line_names = [
        "BoP NAV", "Invested", "Cash out", "Price change", "Capital distribution",
        "Commission", "Tax", "FX", "EoP NAV", "TSR"
    ]
    
    lines = {name: {"name": name, "data": {}} for name in line_names}

    # Fetch stored data
    stored_data = stored_data.filter(year__in=years).values()

    # Process stored data
    for entry in stored_data:
        year = entry['year']
        for line_name in line_names:
            db_field_name = line_name.lower().replace(' ', '_')
            lines[line_name]['data'][year] = entry[db_field_name]

    # Calculate YTD for the current year
    current_year = effective_date.year
    
    ytd_data = calculate_performance(user, date(current_year, 1, 1), effective_date, selected_brokers, currency_target)
    # for line_name, value in ytd_data.items():
    #     lines[line_name]["data"]["YTD"] = value

    for line_name in line_names:
        ytd_field_name = line_name.lower().replace(' ', '_')
        lines[line_name]["data"]["YTD"] = ytd_data[ytd_field_name]

    for line_name, line_data in lines.items():
        # line_data["data"]["YTD"] = line_data["data"].get(current_year, Decimal(0))
        line_data["data"]["All-time"] = sum(value for year, value in line_data["data"].items() if year != "All-time")

    lines['TSR']["data"]["All-time"] = Irr(user.id, effective_date, currency_target, broker_id_list=selected_brokers)
    lines['BoP NAV']['data']['All-time'] = Decimal(0)
    lines['EoP NAV']["data"]["All-time"] = lines['EoP NAV']["data"].get("YTD", Decimal(0))

    context = {
        "years": years,
        "lines": list(lines.values()),
    }

    print("Total time for summary performance calculation taken:", time.time() - start_time)

    return context

# def summary_data_old(user, effective_date, brokers, currency_target, number_of_digits):
#     summary_context = {
#         'years': [],  # List of years for which data is displayed
#         'lines': []   # List of data lines for each broker
#     }
    
#     # Determine the starting year
#     stored_data = AnnualPerformance.objects.filter(
#         investor=user,
#         broker__in=brokers,
#         currency=currency_target,
#     )

#     first_entry = stored_data.order_by('year').first()
#     if not first_entry:
#         return {"years": [], "lines": []}
    
#     start_year = first_entry.year

#     # Determine the ending year
#     last_exit_date = get_last_exit_date_for_brokers(brokers, effective_date)
#     last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_date.year else effective_date.year - 1

#     years = list(range(start_year, last_year + 1))

#     # Fetch stored data
#     stored_data = stored_data.filter(year__in=years).values()

#     current_year = effective_date.year

#     # Initialize totals
#     totals = {year: {
#             'bop_nav': Decimal(0),
#             'invested': Decimal(0),
#             'cash_out': Decimal(0),
#             'price_change': Decimal(0),
#             'capital_distribution': Decimal(0),
#             'commission': Decimal(0),
#             'tax': Decimal(0),
#             'fx': Decimal(0),
#             'eop_nav': Decimal(0),
#             'tsr': Decimal(0)
#         } for year in ['YTD'] + years + ['All-time']}
    
#     for broker in brokers:
#         line_data = {'name': broker.name, 'data': {}}

#         # Add YTD data
#         ytd_data = calculate_performance(user, date(current_year, 1, 1), effective_date, [broker.id], currency_target)
#         compiled_ytd_data = compile_summary_data(ytd_data, currency_target, number_of_digits)
#         line_data['data']['YTD'] = compiled_ytd_data

#         # Update totals for YTD
#         for key, value in ytd_data.items():
#             if isinstance(value, Decimal) and key != 'tsr':
#                 totals['YTD'][key] += value
        
#         # Initialize all-time data
#         all_time_data = {
#             'bop_nav': Decimal(0),
#             'invested': Decimal(0),
#             'cash_out': Decimal(0),
#             'price_change': Decimal(0),
#             'capital_distribution': Decimal(0),
#             'commission': Decimal(0),
#             'tax': Decimal(0),
#             'fx': Decimal(0),
#             'eop_nav': Decimal(0),
#             'tsr': Decimal(0)
#         }

#         # Add stored data for each year
#         for entry in stored_data:
#             if entry['broker_id'] == broker.id:
#                 year_data = {}
#                 # print("utils. 1684", entry)
#                 for key, value in entry.items():
#                     if key in ('id', 'broker_id', 'investor_id'):
#                         continue
#                     year_data[key] = value
#                 # print("utils. 1692", year_data)
#                 formatted_year_data = compile_summary_data(year_data, currency_target, number_of_digits)
#                 line_data['data'][entry['year']] = formatted_year_data

#                 # Update totals for each year
#                 for key, value in year_data.items():
#                     if isinstance(value, Decimal) and key != 'tsr':
#                         totals[entry['year']][key] += value

#                 # Accumulate all-time data
#                 for key in all_time_data.keys():
#                     if key not in ['bop_nav', 'eop_nav', 'tsr']:
#                         all_time_data[key] += year_data.get(key, Decimal(0))

#         # Add YTD data
#         for key in all_time_data.keys():
#             if key not in ['bop_nav', 'eop_nav', 'tsr']:
#                 all_time_data[key] += ytd_data.get(key, Decimal(0))

#         # Add final year EoP NAV to all-time
#         all_time_data['eop_nav'] = ytd_data.get('eop_nav', Decimal(0))

#         # Add all-time TSR separately
#         all_time_data['tsr'] = Irr(user.id, effective_date, currency_target, broker_id_list=[broker.id])
#         # print("utils. 1703", all_time_data)

#         # Format all-time data
#         formatted_all_time_data = compile_summary_data(all_time_data, currency_target, number_of_digits)
#         line_data['data']['All-time'] = formatted_all_time_data
#         # print("utils. 1707", line_data['data']['All-time'])

#         # Update totals for All-time
#         for key, value in all_time_data.items():
#             if isinstance(value, Decimal) and key != 'tsr':
#                 totals['All-time'][key] += value

#         summary_context['lines'].append(line_data)

#     # Add Totals line
#     totals_line = {'name': 'TOTAL', 'data': {}}
#     for year in ['YTD'] + years + ['All-time']:
#         if year == 'YTD':
#             totals[year]['tsr'] = Irr(user.id, effective_date, currency_target, broker_id_list=[broker.id for broker in brokers], start_date = date(effective_date.year, 1, 1))
#         elif year == 'All-time':
#             totals[year]['tsr'] = Irr(user.id, effective_date, currency_target, broker_id_list=[broker.id for broker in brokers])
#         else:
#             totals[year]['tsr'] = Irr(user.id, date(year, 12, 31), currency_target, broker_id_list=[broker.id for broker in brokers], start_date = date(year, 1, 1))
#         totals_line['data'][year] = compile_summary_data(totals[year], currency_target, number_of_digits)
#     summary_context['lines'].append(totals_line)

#     summary_context['years'] = ['YTD'] + years[::-1] + ['All-time']
    
#     return summary_context

def brokers_summary_data(user, effective_date, brokers_or_group, currency_target, number_of_digits):
    def initialize_context():
        return {
            'years': [],
            'lines': []
        }

    def initialize_totals(years):
        return {year: {
            'bop_nav': Decimal(0),
            'invested': Decimal(0),
            'cash_out': Decimal(0),
            'price_change': Decimal(0),
            'capital_distribution': Decimal(0),
            'commission': Decimal(0),
            'tax': Decimal(0),
            'fx': Decimal(0),
            'eop_nav': Decimal(0),
            'tsr': Decimal(0)
        } for year in ['YTD'] + years + ['All-time']}

    if isinstance(brokers_or_group, str):
        # It's a group name
        group_name = brokers_or_group
        selected_brokers_ids = BROKER_GROUPS.get(group_name)
        if not selected_brokers_ids:
            raise ValueError(f"Invalid group name: {group_name}")
    else:
        # It's a list of broker IDs
        selected_brokers_ids = brokers_or_group
        group_name = None

    public_markets_context = initialize_context()
    restricted_investments_context = initialize_context()
    
    # Determine the starting and ending years
    stored_data = AnnualPerformance.objects.filter(
        investor=user,
        currency=currency_target,
    )

    if group_name is not None:
        stored_data = stored_data.filter(broker_group=group_name)
    else:
        stored_data = stored_data.filter(broker_id__in=selected_brokers_ids)

    first_entry = stored_data.order_by('year').first()
    if not first_entry:
        return {"public_markets_context": public_markets_context, "restricted_investments_context": restricted_investments_context}
    
    start_year = first_entry.year
    last_exit_date = get_last_exit_date_for_brokers(selected_brokers_ids, effective_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_date.year else effective_date.year - 1
    years = list(range(start_year, last_year + 1))

    stored_data = stored_data.filter(year__in=years).values()
    current_year = effective_date.year

    public_totals = initialize_totals(years)
    restricted_totals = initialize_totals(years)

    brokers = Brokers.objects.filter(id__in=selected_brokers_ids, investor=user)

    for restricted in [False, True]:
        context = public_markets_context if not restricted else restricted_investments_context
        totals = public_totals if not restricted else restricted_totals

        brokers_subgroup = brokers.filter(restricted=restricted)

        for broker in brokers_subgroup:
            line_data = {'name': broker.name, 'data': {}}

             # Initialize data for all years
            for year in ['YTD'] + years + ['All-time']:
                line_data['data'][year] = {
                    'bop_nav': Decimal(0),
                    'invested': Decimal(0),
                    'cash_out': Decimal(0),
                    'price_change': Decimal(0),
                    'capital_distribution': Decimal(0),
                    'commission': Decimal(0),
                    'tax': Decimal(0),
                    'fx': Decimal(0),
                    'eop_nav': Decimal(0),
                    'tsr': Decimal(0)
                }
                line_data['data'][year] = compile_summary_data(line_data['data'][year], currency_target, number_of_digits)

            # Add YTD data
            try:
                ytd_data = calculate_performance(user, date(current_year, 1, 1), effective_date, [broker.id], currency_target, is_restricted=restricted)
                compiled_ytd_data = compile_summary_data(ytd_data, currency_target, number_of_digits)
                line_data['data']['YTD'] = compiled_ytd_data

                # Update totals for YTD
                for key, value in ytd_data.items():
                    if isinstance(value, Decimal) and key != 'tsr':
                        totals['YTD'][key] += value
            except Exception as e:
                print(f"Error calculating YTD data for broker {broker.name}: {e}")
            
            # Initialize all-time data
            all_time_data = {key: Decimal(0) for key in totals['All-time'].keys()}

            # Add stored data for each year
            for entry in stored_data:
                if entry['broker_id'] == broker.id and entry['restricted'] == restricted:
                    year_data = {k: v for k, v in entry.items() if k not in ('id', 'broker_id', 'investor_id', 'broker_group')}
                    formatted_year_data = compile_summary_data(year_data, currency_target, number_of_digits)
                    line_data['data'][entry['year']] = formatted_year_data

                    # Update totals for each year
                    for key, value in year_data.items():
                        if isinstance(value, Decimal) and key != 'tsr':
                            totals[entry['year']][key] += value

                    # Accumulate all-time data
                    for key in all_time_data.keys():
                        if key not in ['bop_nav', 'eop_nav', 'tsr']:
                            all_time_data[key] += year_data.get(key, Decimal(0))

            # Add YTD data to all-time
            for key in all_time_data.keys():
                if key not in ['bop_nav', 'eop_nav', 'tsr']:
                    all_time_data[key] += ytd_data.get(key, Decimal(0))

            # Add final year EoP NAV to all-time
            all_time_data['eop_nav'] = ytd_data.get('eop_nav', Decimal(0))

            # Add all-time TSR separately if broker matches the restriction condition
            if broker.restricted == restricted:
                try:
                    all_time_data['tsr'] = Irr(user.id, effective_date, currency_target, broker_id_list=[broker.id])
                except Exception as e:
                    print(f"Error calculating all-time TSR for broker {broker.name}: {e}")
                    all_time_data['tsr'] = 'N/A'
            else:
                all_time_data['tsr'] = 'N/R'

            # Format all-time data
            formatted_all_time_data = compile_summary_data(all_time_data, currency_target, number_of_digits)
            line_data['data']['All-time'] = formatted_all_time_data

            # Update totals for All-time
            for key, value in all_time_data.items():
                if isinstance(value, Decimal) and key != 'tsr':
                    totals['All-time'][key] += value

            context['lines'].append(line_data)

        # Add Sub-totals line
        sub_totals_line = {'name': 'Sub-total', 'data': {}}
        for year in ['YTD'] + years + ['All-time']:
            # try:
            if year == 'YTD':
                totals[year]['tsr'] = Irr(user.id, effective_date, currency_target, broker_id_list=[broker.id for broker in brokers_subgroup], start_date=date(effective_date.year, 1, 1))
            elif year == 'All-time':
                totals[year]['tsr'] = Irr(user.id, effective_date, currency_target, broker_id_list=[broker.id for broker in brokers_subgroup])
            else:
                totals[year]['tsr'] = Irr(user.id, date(year, 12, 31), currency_target, broker_id_list=[broker.id for broker in brokers_subgroup], start_date=date(year, 1, 1))
            # except Exception as e:
            #     print(f"Error calculating TSR for year {year}: {e}")
            #     totals[year]['tsr'] = 'N/R'

            sub_totals_line['data'][year] = compile_summary_data(totals[year], currency_target, number_of_digits)
        
        context['lines'].append(sub_totals_line)

        context['years'] = ['YTD'] + years[::-1] + ['All-time']

    # Add Totals line
    totals_line = {'name': 'TOTAL', 'data': {}}
    for year in ['YTD'] + years + ['All-time']:
        totals_line['data'][year] = {
            'bop_nav': Decimal(0),
            'invested': Decimal(0),
            'cash_out': Decimal(0),
            'price_change': Decimal(0),
            'capital_distribution': Decimal(0),
            'commission': Decimal(0),
            'tax': Decimal(0),
            'fx': Decimal(0),
            'eop_nav': Decimal(0),
            'tsr': Decimal(0)
        }
        
        # Sum up values from both public markets and restricted investments contexts
        for sub_total in [public_totals[year], restricted_totals[year]]:
            for key, value in sub_total.items():
                if key != 'tsr' and isinstance(value, Decimal):
                    totals_line['data'][year][key] += value
        
        try:
            if year == 'YTD':
                totals_line['data'][year]['tsr'] = Irr(user.id, effective_date, currency_target, broker_id_list=[broker.id for broker in brokers], start_date=date(effective_date.year, 1, 1))
            elif year == 'All-time':
                totals_line['data'][year]['tsr'] = Irr(user.id, effective_date, currency_target, broker_id_list=[broker.id for broker in brokers])
            else:
                totals_line['data'][year]['tsr'] = Irr(user.id, date(year, 12, 31), currency_target, broker_id_list=[broker.id for broker in brokers], start_date=date(year, 1, 1))
        except Exception as e:
            print(f"Error calculating TSR for year {year}: {e}")
            totals_line['data'][year]['tsr'] = 'N/R'

        # Calculate fee per AUM
        total_nav = totals_line['data'][year]['eop_nav']
        total_commission = totals_line['data'][year]['commission']
        if total_nav > 0:
            fee_per_aum = -(total_commission / total_nav)  # as a percentage
        else:
            fee_per_aum = Decimal(0)
        
        totals_line['data'][year]['fee_per_aum'] = fee_per_aum
        
        # Compile and format the data
        totals_line['data'][year] = compile_summary_data(totals_line['data'][year], currency_target, number_of_digits)
    
    # Create a new context for the total line
    total_context = {
        'years': ['YTD'] + years[::-1] + ['All-time'],
        'line': totals_line
    }

    return {
        "public_markets_context": public_markets_context,
        "restricted_investments_context": restricted_investments_context,
        "total_context": total_context
    }

def compile_summary_data(data, currency_target, number_of_digits):
    
    bop_nav = data.get('bop_nav', Decimal(0))
    eop_nav = data.get('eop_nav', Decimal(0))
    invested = data.get('invested', Decimal(0))
    cash_out = data.get('cash_out', Decimal(0))
    price_change = data.get('price_change', Decimal(0))
    capital_distribution = data.get('capital_distribution', Decimal(0))
    commission = data.get('commission', Decimal(0))
    tax = data.get('tax', Decimal(0))
    fx = data.get('fx', Decimal(0))
    tsr = data.get('tsr', Decimal(0))

    # Calculate additional metrics
    cash_in_out = invested + cash_out
    return_value = price_change + capital_distribution + commission + tax
    avg_nav = (bop_nav + eop_nav) / 2 if (bop_nav + eop_nav) != 0 else -1  # Avoid division by zero
    fee_per_aum = -(commission / avg_nav) if avg_nav != -1 else Decimal(0)  # Fee per AuM as percentage

    formatted_data = {
        'BoP NAV': round(bop_nav, number_of_digits),
        'Cash-in/out': round(cash_in_out, number_of_digits),
        'Return': round(return_value, number_of_digits),
        'FX': round(fx, number_of_digits),
        'TSR percentage': tsr,
        'EoP NAV': round(eop_nav, number_of_digits),
        'Commission': round(commission, number_of_digits),
        'Fee per AuM (percentage)': fee_per_aum,
    }

    formatted_data = currency_format_dict_values(formatted_data, currency_target, number_of_digits)

    return formatted_data

def save_or_update_annual_broker_performance(user, effective_date, brokers_or_group, currency_target, is_restricted=None):

    try:
        if isinstance(brokers_or_group, str):
            # It's a group name
            group_name = brokers_or_group
            selected_brokers_ids = BROKER_GROUPS.get(group_name)
            if not selected_brokers_ids:
                raise ValueError(f"Invalid group name: {group_name}")
        else:
            # It's a list of broker IDs
            selected_brokers_ids = brokers_or_group
            group_name = None

        print("utils. 2083", selected_brokers_ids, is_restricted)

        # Determine the starting year
        first_transaction = Transactions.objects.filter(broker_id__in=selected_brokers_ids, date__lte=effective_date).order_by('date').first()
        if not first_transaction:
            logger.info(f"No transactions found for investor {user.id} and brokers/group {brokers_or_group}")
            return
        
        start_year = first_transaction.date.year

        # Determine the ending year
        last_exit_date = get_last_exit_date_for_brokers(selected_brokers_ids, effective_date)
        last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_date.year else effective_date.year - 1
        years = list(range(start_year, last_year + 1))

        for year in years:
            with transaction.atomic():

                if group_name:
                    performance_data = calculate_performance(user, date(year, 1, 1), date(year, 12, 31), selected_brokers_ids, currency_target, is_restricted)
                    # Save group performance
                    performance, created = AnnualPerformance.objects.update_or_create(
                        investor=user,
                        broker_group=group_name,
                        year=year,
                        currency=currency_target,
                        restricted=is_restricted,
                        defaults=performance_data
                    )
                    logger.info(f"Updated group performance for investor {user.id}, group {group_name}, year {year}")
                else:
                    # Save individual broker performances
                    for broker_id in selected_brokers_ids:
                        performance_data = calculate_performance(user, date(year, 1, 1), date(year, 12, 31), [broker_id], currency_target, is_restricted)
                        performance, created = AnnualPerformance.objects.update_or_create(
                            investor=user,
                            broker_id=broker_id,
                            year=year,
                            currency=currency_target,
                            restricted=is_restricted,
                            defaults=performance_data
                        )
                    logger.info(f"Updated individual performances for investor {user.id}, broker ids {selected_brokers_ids}, year {year}")

    except IntegrityError as e:
        logger.error(f"Integrity error updating annual performance: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error updating annual performance: {str(e)}")
        raise

    logger.info(f"Completed updating annual performance for investor {user.id}")

def calculate_performance(user, start_date, end_date, selected_brokers_ids, currency_target, is_restricted=None):
    performance_data = {name: Decimal(0) for name in [
        "bop_nav", "invested", "cash_out", "price_change", "capital_distribution",
        "commission", "tax", "fx", "eop_nav", "tsr"
    ]}

    # Calculate the performance values for each line
    transactions = Transactions.objects.filter(
        investor=user,
        broker_id__in=selected_brokers_ids,
        date__gte=start_date,
        date__lte=end_date,
    )

    if is_restricted is not None:
        # Filter for transactions related to securities
        security_transactions = transactions.filter(security__isnull=False, security__restricted=is_restricted)
        # Include all transactions not related to specific securities
        non_security_transactions = transactions.filter(security__isnull=True)
        # Combine both querysets
        transactions = security_transactions | non_security_transactions

    else:
        transactions = transactions

    transactions = transactions.values('cash_flow', 'type', 'commission', 'date', 'currency', 'broker_id')

    transactions_df = pd.DataFrame(list(transactions))
    if transactions_df.empty:
        return performance_data

    transactions_df['fx_rate'] = transactions_df.apply(
        # lambda row: FX.get_rate(row['currency'], currency_target, row['date'])['FX'], axis=1
        lambda row: get_fx_rate(row['currency'], currency_target, row['date']), axis=1
    )

    brokers = Brokers.objects.filter(id__in=selected_brokers_ids, investor=user).all()

    for broker in brokers:
        broker_transactions = transactions_df[transactions_df['broker_id'] == broker.id]
        if broker_transactions.empty:
            continue

        bop_nav = AnnualPerformance.objects.filter(investor=user, broker=broker, year=start_date.year - 1, currency=currency_target)
        if len(bop_nav) == 0:
            bop_nav = NAV_at_date(user.id, [broker.id], start_date - timedelta(days=1), currency_target)['Total NAV']
        else:
            bop_nav = bop_nav.values('eop_nav')[0]['eop_nav']
        performance_data['bop_nav'] += bop_nav

        invested = round((broker_transactions[broker_transactions['type'] == 'Cash in']['cash_flow'] * 
                          broker_transactions[broker_transactions['type'] == 'Cash in']['fx_rate']).sum(), 2)
        performance_data['invested'] += invested

        cash_out = round((broker_transactions[broker_transactions['type'] == 'Cash out']['cash_flow'] * 
                          broker_transactions[broker_transactions['type'] == 'Cash out']['fx_rate']).sum(), 2)
        performance_data['cash_out'] += cash_out

        realized_gl = Decimal(0)
        unrealized_gl = Decimal(0)
        capital_distribution = Decimal(0)

        assets = Assets.objects.filter(investor=user, brokers=broker)
        if is_restricted is not None:
            assets = assets.filter(restricted=is_restricted)                                       

        for asset in assets:
            asset_realized_gl = asset.realized_gain_loss(end_date, currency_target, broker_id_list=[broker.id], start_date=start_date)
            realized_gl += asset_realized_gl["all_time"] if asset_realized_gl else 0
            unrealized_gl += asset.unrealized_gain_loss(end_date, currency_target, broker_id_list=[broker.id], start_date=start_date)
            capital_distribution += asset.get_capital_distribution(end_date, currency_target, broker_id_list=[broker.id], start_date=start_date)

        performance_data['price_change'] += realized_gl + unrealized_gl
        performance_data['capital_distribution'] += capital_distribution

        commission = round((broker_transactions['commission'] * broker_transactions['fx_rate']).sum(), 2)
        performance_data['commission'] += commission

        tax = round((broker_transactions[broker_transactions['type'] == 'Tax']['cash_flow'] * 
                     broker_transactions[broker_transactions['type'] == 'Tax']['fx_rate']).sum(), 2)
        performance_data['tax'] += tax

        eop_nav = NAV_at_date(user.id, [broker.id], end_date, currency_target)['Total NAV']
        performance_data['eop_nav'] += eop_nav
        
        components_sum = (
            performance_data['bop_nav'] + 
            performance_data['invested'] + 
            performance_data['cash_out'] + 
            performance_data['price_change'] + 
            performance_data['capital_distribution'] + 
            performance_data['commission'] + 
            performance_data['tax']
        )
        performance_data['fx'] += eop_nav - components_sum

    tsr = Irr(user.id, end_date, currency_target, broker_id_list=selected_brokers_ids, start_date=start_date)
    performance_data['tsr'] += tsr

    return performance_data

@lru_cache(maxsize=None)
def get_fx_rate(currency, target_currency, date):
    return FX.get_rate(currency, target_currency, date)['FX']