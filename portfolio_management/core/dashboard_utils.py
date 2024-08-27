from decimal import Decimal
from django.db.models import Sum
from common.models import Transactions, FX, AnnualPerformance
from .formatting_utils import currency_format, format_table_data
from .portfolio_utils import broker_group_to_ids, NAV_at_date, IRR
from utils import calculate_performance_old_framework, Irr_old_structure
from datetime import date

# def get_dashboard_summary(user, effective_current_date):
#     currency_target = user.default_currency
#     number_of_digits = user.digits
#     selected_brokers = broker_group_to_ids(user.custom_brokers, user)

#     summary = {}

#     # Calculate NAV
#     analysis = NAV_at_date(user.id, selected_brokers, effective_current_date, currency_target, ['Asset type', 'Currency', 'Asset class'])
#     summary['Current NAV'] = analysis['Total NAV']

#     # Calculate Invested and Cash-out
#     summary['Invested'] = Decimal(0)
#     summary['Cash-out'] = Decimal(0)

#     transactions = Transactions.objects.filter(
#         investor=user,
#         broker__in=selected_brokers,
#         date__lte=effective_current_date,
#         type__in=['Cash in', 'Cash out']
#     ).values('currency', 'type', 'cash_flow', 'date').annotate(
#         total=Sum('cash_flow')
#     )

#     for transaction in transactions:
#         fx_rate = FX.get_rate(transaction['currency'], currency_target, transaction['date'])['FX']
#         if transaction['type'] == 'Cash in':
#             summary['Invested'] += Decimal(transaction['total']) * Decimal(fx_rate)
#         else:
#             summary['Cash-out'] += Decimal(transaction['total']) * Decimal(fx_rate)

#     # Calculate IRR and Return
#     try:
#         summary['total_return'] = (summary['Current NAV'] - summary['Cash-out']) / summary['Invested'] - 1
#     except ZeroDivisionError:
#         summary['total_return'] = None

#     summary['irr'] = IRR(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=selected_brokers)

#     summary = format_table_data(summary, currency_target, number_of_digits)

#     return summary

# def get_dashboard_nav_breakdown(user, effective_current_date):
#     currency_target = user.default_currency
#     number_of_digits = user.digits
#     selected_brokers = broker_group_to_ids(user.custom_brokers, user)

#     analysis = NAV_at_date(user.id, selected_brokers, effective_current_date, currency_target, ['Asset type', 'Currency', 'Asset class'])
    
#     # Remove 'Total NAV' from the analysis
#     total_nav = analysis.pop('Total NAV', None)
    
#     # Calculate percentage breakdowns
#     _calculate_percentage_shares(analysis, ['Asset type', 'Currency', 'Asset class'])
    
#     # Format the values
#     analysis = format_table_data(analysis, currency_target, number_of_digits)
    
#     return {
#         'assetType': {
#             'data': analysis['Asset type'],
#             'percentage': analysis['Asset type percentage']
#         },
#         'currency': {
#             'data': analysis['Currency'],
#             'percentage': analysis['Currency percentage']
#         },
#         'assetClass': {
#             'data': analysis['Asset class'],
#             'percentage': analysis['Asset class percentage']
#         },
#         'totalNAV': currency_format(total_nav, currency_target, number_of_digits)
#     }

# # Add percentage shares to the dict
# def _calculate_percentage_shares(data_dict, selected_keys):

#     # Calculate Total NAV based on one of the categories
#     total = sum(data_dict[selected_keys[0]].values())
    
#     # Add new dictionaries with percentage shares for selected categories
#     for category in selected_keys:
#         percentage_key = category + ' percentage'
#         data_dict[percentage_key] = {}
#         for key, value in data_dict[category].items():
#             try:
#                 data_dict[percentage_key][key] = str(round(Decimal(value / total * 100), 1)) + '%'
#             except ZeroDivisionError:
#                 data_dict[percentage_key][key] = '–'


