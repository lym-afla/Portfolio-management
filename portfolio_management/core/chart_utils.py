from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from core.portfolio_utils import IRR, NAV_at_date
import pandas as pd
import numpy as np

def get_nav_chart_data(user_id, brokers, frequency, from_date, to_date, currency, breakdown):
    dates = _chart_dates(from_date, to_date, frequency)
    
    chart_data = {
        'labels': _chart_labels(dates, frequency),
        'datasets': [],
        'currency': currency + 'k',
    }

    previous_date = None
    NAV_previous_date = 0

    # Initialize datasets for bar charts first
    if breakdown == 'none':
        chart_data['datasets'].append(create_dataset('NAV', [], 'rgba(54, 162, 235, 0.7)', 'bar', 'y', stack='combined'))
    elif breakdown == 'value_contributions':
        chart_data['datasets'].extend([
            create_dataset('BoP NAV', [], 'rgba(54, 162, 235, 0.7)', 'bar', 'y', stack='combined'),
            create_dataset('Contributions', [], 'rgba(255, 206, 86, 0.7)', 'bar', 'y', stack='combined'),
            create_dataset('Return', [], 'rgba(75, 192, 192, 0.7)', 'bar', 'y', stack='combined')
        ])
    elif breakdown != 'none':
        # Initialize datasets for custom breakdown
        NAV_initial = NAV_at_date(user_id, brokers, dates[0], currency, [breakdown])[breakdown]
        for key, value in NAV_initial.items():
            chart_data['datasets'].append(create_dataset(key, [], get_color(len(chart_data['datasets'])), 'bar', 'y', stack='combined'))

    # Add line chart datasets last
    chart_data['datasets'].extend([
        create_dataset('IRR (RHS)', [], 'rgba(75, 192, 192, 1)', 'line', 'y1'),
        create_dataset('Rolling IRR (RHS)', [], 'rgba(153, 102, 255, 1)', 'line', 'y1')
    ])

    for d in dates:
        IRR_value = IRR(user_id, d, currency, broker_id_list=brokers)
        IRR_rolling = IRR(user_id, d, currency, broker_id_list=brokers, start_date=previous_date)
        
        if breakdown == 'none':
            NAV = NAV_at_date(user_id, brokers, d, currency)['Total NAV'] / 1000
            add_no_breakdown_data(chart_data, IRR_value, IRR_rolling, NAV)
        elif breakdown == 'value_contributions':
            NAV = NAV_at_date(user_id, brokers, d, currency)['Total NAV'] / 1000
            add_contributions_data(chart_data, user_id, brokers, d, currency, IRR_value, IRR_rolling, NAV, NAV_previous_date, previous_date)
        else:
            NAV = NAV_at_date(user_id, brokers, d, currency, [breakdown])[breakdown]
            add_breakdown_data(chart_data, IRR_value, IRR_rolling, NAV)

        NAV_previous_date = NAV
        previous_date = d

    return chart_data

def add_no_breakdown_data(chart_data, IRR, IRR_rolling, NAV):
    chart_data['datasets'][0]['data'].append(NAV)
    chart_data['datasets'][1]['data'].append(IRR)
    chart_data['datasets'][2]['data'].append(IRR_rolling)

def add_contributions_data(chart_data, user_id, brokers, d, currency, IRR, IRR_rolling, NAV, NAV_previous_date, previous_date):
    contributions = calculate_contributions(user_id, brokers, d, previous_date)
    return_amount = NAV - NAV_previous_date - contributions

    chart_data['datasets'][0]['data'].append(NAV_previous_date)
    chart_data['datasets'][1]['data'].append(contributions)
    chart_data['datasets'][2]['data'].append(return_amount)
    chart_data['datasets'][3]['data'].append(IRR)
    chart_data['datasets'][4]['data'].append(IRR_rolling)

def add_breakdown_data(chart_data, IRR, IRR_rolling, NAV):
    for i, (key, value) in enumerate(NAV.items()):
        chart_data['datasets'][i]['data'].append(value / 1000)

    chart_data['datasets'][-2]['data'].append(IRR)
    chart_data['datasets'][-1]['data'].append(IRR_rolling)

def create_dataset(label, data, color, chart_type, axis_id, stack=None):
    dataset = {
        'label': label,
        'data': data,
        'backgroundColor': color,
        'borderColor': color,
        'type': chart_type,
        'yAxisID': axis_id,
        'datalabels': {'display': 'true'}
    }
    if stack:
        dataset['stack'] = stack
    return dataset

def get_color(index):
    colors = ['rgba(54, 162, 235, 0.7)', 'rgba(255, 206, 86, 0.7)', 'rgba(75, 192, 192, 0.7)', 'rgba(153, 102, 255, 0.7)', 'rgba(255, 159, 64, 0.7)']
    return colors[index % len(colors)]

def calculate_contributions(user_id, brokers, end_date, start_date):
    # Implement the logic to calculate contributions between start_date and end_date
    pass


# Collect chart dates 
def _chart_dates(start_date, end_date, freq):
    # Create matching table for pandas
    frequency = {
        'D': 'D',
        'W': 'W-SAT',
        'M': 'ME',
        'Q': 'QE',
        'Y': 'YE'
        }
    
    start_date = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    end_date = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date

    if start_date >= end_date:
        return np.array([start_date])

    if freq == 'W':
        start_date += timedelta(days=(5 - start_date.weekday() + 7) % 7)
    elif freq == 'M':
        start_date = start_date.replace(day=1) + relativedelta(months=1, days=-1)
    elif freq == 'Q':
        start_date = start_date.replace(day=1, month=((start_date.month - 1) // 3 * 3 + 3)) + relativedelta(days=-1)
    elif freq == 'Y':
        start_date = start_date.replace(month=12, day=31)

    # Get list of dates from pandas
    date_range = pd.date_range(start=start_date, end=end_date, freq=frequency[freq]).date
    
    return np.append(date_range, end_date) if date_range[-1] != end_date else date_range

# Create labels according to dates
def _chart_labels(dates, frequency):
    
    if frequency in ('D', 'W'):
        return [d.strftime("%d-%b-%y") for d in dates]
    if frequency == 'M':
        return [d.strftime("%b-%y") for d in dates]
    if frequency == 'Q':
        return [f'Q{(d.month-1)//3+1} {d.strftime("%y")}' for d in dates]
    if frequency == 'Y':
        return [d.strftime("%Y") for d in dates]