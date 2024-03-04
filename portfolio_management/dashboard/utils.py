from .models import Brokers, PA, FX, PA_transactions
from django.db.models import Sum
from pyxirr import xirr
import pandas as pd

# Portfolio at [table_date] - assets with non zero positions
# func.date used for correct query when transaction is at [table_date] (removes time (HH:MM:SS) effectively)
def portfolio_at_date(date, brokers):
    # Check if brokers is None, if so, return an empty queryset
    if brokers is None:
        return PA.objects.none()
    
    # Filter PA objects based on transactions with the given date and brokers
    return PA.objects.filter(
        transactions__date__lte=date, 
        transactions__broker_id__in=brokers
    ).annotate(total_quantity=Sum('transactions__quantity')).filter(total_quantity__gt=0)

# Create one dictionary from two. And add values for respective keys if keys present on both dictionaries
def merge_dictionaries(dict_1, dict_2):
    dict_3 = dict_1.copy()  # Create a copy of dict_1
    for key, value in dict_2.items():
        dict_3[key] = dict_3.get(key, 0) + value  # Add values for common keys or set new values if key is not in dict_3
    return dict_3

def calculate_security_nav(item, date, currency):
    current_quote = item.current_price(date)
    return round(current_quote.price * FX.get_rate(item.currency.upper(), currency, current_quote.date)['FX'] * item.position(date), 2)

def update_analysis(analysis, key, value, date=None, currency=None, desired_currency=None):
    if currency and date and desired_currency:
        value = round(value * FX.get_rate(currency, desired_currency, date)['FX'], 2)
    if key not in analysis:
        analysis[key] = value
    else:
        analysis[key] += value

# Calculate NAV breakdown for selected brokers at certain date and in selected currency
def NAV_at_date(broker_ids, date, target_currency, breakdown=['Asset type', 'Currency', 'Asset class', 'Broker']):
    portfolio = portfolio_at_date(date, broker_ids)
    portfolio_brokers = Brokers.objects.filter(id__in=broker_ids)
    analysis = {'Asset type': {}, 'Currency': {}, 'Asset class': {}, 'Broker': {}, 'aggregate': 0}

    for item in portfolio:
        current_value = calculate_security_nav(item, date, target_currency)

        if 'Broker' in breakdown:
            for broker in item.brokers.all():
                update_analysis(analysis['Broker'], broker.name, current_value)

        for breakdown_type in breakdown:
            if breakdown_type == 'Broker':
                continue
            key = getattr(item, breakdown_type)
            update_analysis(analysis[breakdown_type], key, current_value)
        
        if 'aggregate' in breakdown:
            analysis['aggregate'] += current_value

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
    if 'aggregate' in breakdown:
        analysis['aggregate'] += cash
    
    return analysis

# Calculate portfolio IRR at date for public assets
def PA_irr(date, currency, asset_id='', broker_id_list=[], start_date=''):
    portfolio_value = 0
    cash_flows = []
    transaction_dates = []

    # Collect cash flows and transaction dates for the portfolio
    transactions = PA_transactions.objects.filter(date__lte=date)
    
    if asset_id:
        transactions = transactions.filter(security_id=asset_id)

    if broker_id_list:
        transactions = transactions.filter(broker_id__in=broker_id_list)

    if start_date:
        transactions = transactions.filter(date__gte=start_date)

    # Calculate cash flows and transaction dates
    for transaction in transactions:
        fx_rate = FX.get_rate(transaction.currency.upper(), currency, transaction.date)['FX']
        cash_flow = transaction.cash_flow or (-transaction.quantity * transaction.price + (transaction.commission or 0))
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

    try:
        return round(xirr(cash_flows, transaction_dates), 4)
    except:
        return 'N/A'

def calculate_portfolio_value(date, currency, asset_id='', broker_id_list=[]):
    portfolio_value = 0

    if not asset_id:
        portfolio_value = NAV_at_date(broker_id_list, date, currency, ['aggregate'])['aggregate']
    else:
        asset = PA.objects.get(pk=asset_id)
        fx_rate = FX.get_rate(asset.currency.upper(), currency, date)['FX']
        portfolio_value = round(fx_rate * asset.current_price(date) * asset.position(date, broker_id_list), 2)

    return portfolio_value

# Collect chart dates 
def chart_dates(start_date, end_date, freq):

    # Create matching table for pandas
    frequency = {
        'D': 'B',
        'W': 'W',
        'M': 'M',
        'Q': 'Q',
        'Y': 'Y'
    }

    # Get DatetimeIndex from pandas
    date_range = pd.date_range(start_date, end_date, freq=frequency[freq])

    # Convert DatetimeIndex to list of dates
    return date_range.date.tolist()

# Create labels according to dates
def chart_labels(dates, freq):
    
    labels = []

    for date in dates:
        if freq == 'D' or freq == 'W':
            labels.append(date.strftime("%d-%b-%y"))
        elif freq == 'M':
            labels.append(date.strftime("%b-%y"))
        elif freq == 'Q':
            quarter = ((date.month - 1) // 3) + 1
            labels.append('Q{} {}'.format(quarter, date.strftime("%y")))
        elif freq == 'Y':
            labels.append(date.strftime("%Y"))

    return labels

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

# def NAV_at_date(broker_id, date, currency, breakdown=['Asset type', 'Currency', 'Asset class', 'Broker']):
    
#     portfolio = portfolio_at_date(date, broker_id) 
    
#     portfolio_brokers = Brokers.objects.filter(id__in=broker_id)
        
#     # Convert current value to the target currency + fill data for Analysis tab
#     analysis = {'Asset type': {}, 'Currency': {}, 'Asset class': {}, 'Broker': {}, 'aggregate': 0}

#     for item in portfolio:
        
#         # Calculate security NAV in target currency
#         current_quote = item.current_price(date)
#         item.current_value = round(current_quote.price * \
#             FX.get_rate(item.currency.upper(), currency, current_quote.date)['FX'] * \
#                 item.position(date), 2)
        
#         if 'Broker' in breakdown:
#             for broker in item.brokers.all():
#                 if broker.name not in analysis['Broker']:
#                     analysis['Broker'][broker.name] = item.current_value
#                 else:
#                     analysis['Broker'][broker.name] += item.current_value
        
#         if 'Asset type' in breakdown:
#             if item.type not in analysis['Asset type']:
#                 analysis['Asset type'][item.type] = item.current_value
#             else:
#                 analysis['Asset type'][item.type] += item.current_value

#         if 'Currency' in breakdown:
#             if item.currency not in analysis['Currency']:
#                 analysis['Currency'][item.currency] = item.current_value
#             else:
#                 analysis['Currency'][item.currency] += item.current_value
            
#         if 'Asset class' in breakdown:
#             if item.exposure not in analysis['Asset class']:
#                 analysis['Asset class'][item.exposure] = item.current_value
#             else:
#                 analysis['Asset class'][item.exposure] += item.current_value
        
#         if 'aggregate' in breakdown:
#             analysis['aggregate'] += item.current_value

#     # Get cash balances in native currency for selected brokers
#     cash_balance = {}
#     for broker in portfolio_brokers:
#         cash_balance = merge_dictionaries(cash_balance, broker.balance(date))
#         if 'Broker' in breakdown:
#             for cur, balance in broker.balance(date).items():
#                 if broker.name not in analysis['Broker']:
#                     analysis['Broker'][broker.name] = round(balance * FX.get_rate(cur, currency, date)['FX'], 2)
#                 else:
#                     analysis['Broker'][broker.name] += round(balance * FX.get_rate(cur, currency, date)['FX'], 2)

#     # Convert cash balance to target currency
#     cash = 0
#     for cur, balance in cash_balance.items():
#         converted_cash = round(balance * FX.get_rate(cur, currency, date)['FX'], 2)
#         cash += converted_cash
#         if 'Currency' in breakdown:
#             if cur in analysis['Currency']:
#                 analysis['Currency'][cur] += converted_cash
#             else:
#                 analysis['Currency'][cur] = converted_cash

#     if 'Asset type' in breakdown:
#         analysis['Asset type']['Cash'] = cash
#     if 'Asset class' in breakdown:
#         analysis['Asset class']['Cash'] = cash
#     if 'aggregate' in breakdown:
#         analysis['aggregate'] += cash
    
#     return analysis

