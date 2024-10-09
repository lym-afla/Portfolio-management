from datetime import date, datetime
from decimal import Decimal
import time
import json
import logging
from collections import defaultdict

from django.db import DatabaseError
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Sum

from common.models import AnnualPerformance, Brokers, Transactions, FX
from common.forms import DashboardForm_old_setup
from core.formatting_utils import currency_format, format_percentage, format_table_data
from core.portfolio_utils import IRR, NAV_at_date, broker_group_to_ids, calculate_percentage_shares, calculate_performance, get_last_exit_date_for_brokers
from core.chart_utils import get_nav_chart_data

from database.forms import BrokerPerformanceForm

from utils import NAV_at_date_old_structure, Irr_old_structure, broker_group_to_ids_old_approach, calculate_from_date, calculate_percentage_shares_old_framework, currency_format_old_structure, currency_format_dict_values, decimal_default, format_percentage_old_structure, get_chart_data, get_last_exit_date_for_brokers_old_approach, dashboard_summary_over_time

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

# @login_required
# def dashboard(request):
#     start_time = time.time()
#     start_t = time.time()

#     user = request.user
    
#     effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
#     currency_target = user.default_currency
#     number_of_digits = user.digits
#     selected_brokers = broker_group_to_ids_old_approach(user.custom_brokers, user)

#     sidebar_padding = request.GET.get("padding", 0)
#     sidebar_width = request.GET.get("width", 0)
#     brokers = Brokers.objects.filter(investor=user, id__in=selected_brokers).all()

#     initial_data = {
#         'selected_brokers': selected_brokers,
#         'default_currency': currency_target,
#         'table_date': effective_current_date.strftime('%Y-%m-%d'),  # Convert date to string
#         'digits': number_of_digits
#     }
#     dashboard_form = DashboardForm_old_setup(instance=user, initial=initial_data)

#     print("views. dashboard. Time taken for preparatory calcs", time.time() - start_t)

#     start_t = time.time()
#     analysis = NAV_at_date_old_structure(user.id, selected_brokers, effective_current_date, currency_target, ['Asset type', 'Currency', 'Asset class'])
#     print("views. dashboard. Time taken for NAV at date calc", time.time() - start_t)

#     start_t = time.time()

#     summary = {}
#     summary['NAV'] = analysis['Total NAV']
#     currencies = set()
#     for broker in brokers:
#         currencies.update(broker.get_currencies())

#     summary['Invested'] = summary['Cash-out'] = 0

#     for cur in currencies:
#         quote = Transactions.objects.filter(investor=user, broker__in=selected_brokers, currency=cur, date__lte=effective_current_date, type__in=['Cash in', 'Cash out']).values_list('cash_flow', 'date', 'type')
#         for cash_flow, date, transaction_type in quote:
#             if transaction_type == 'Cash in':
#                 summary['Invested'] += cash_flow * FX.get_rate(cur, currency_target, date, user)['FX']
#             else:
#                 summary['Cash-out'] += cash_flow * FX.get_rate(cur, currency_target, date, user)['FX']

    
#     summary['IRR'] = format_percentage_old_structure(Irr_old_structure(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=selected_brokers), digits=1)
    
#     try:
#         summary['Return'] = format_percentage_old_structure((summary['NAV'] - summary['Cash-out']) / summary['Invested'] - 1, digits=1)
#     except ZeroDivisionError:
#         summary['Return'] = '–'
    
#     # Convert data to string representation to feed the page
#     summary['NAV'] = currency_format_old_structure(summary['NAV'], currency_target, number_of_digits)
#     summary['Invested'] = currency_format_old_structure(summary['Invested'], currency_target, number_of_digits)
#     summary['Cash-out'] = currency_format_old_structure(summary['Cash-out'], currency_target, number_of_digits)

#     # Convert Python object to JSON string to be recognizable by Chart.js
#     json_analysis = json.dumps(analysis, default=decimal_default)

#     # Add percentage breakdowns
#     calculate_percentage_shares_old_framework(analysis, ['Asset type', 'Currency', 'Asset class'])
#     analysis = currency_format_dict_values(analysis, currency_target, number_of_digits)

#     print("views. dashboard. Time taken for summary dict calcs", time.time() - start_t)

#     start_t = time.time()

#     financial_table_context = dashboard_summary_over_time(user, effective_current_date, user.custom_brokers, currency_target)
#     # Formatting outputs
#     for index in range(len(financial_table_context['lines'])):
#         if financial_table_context['lines'][index]['name'] == 'TSR':
#             for k, v in financial_table_context['lines'][index]['data'].items():
#                 financial_table_context['lines'][index]['data'][k] = format_percentage_old_structure(v, digits=1)
#         else:
#             financial_table_context['lines'][index] = currency_format_dict_values(financial_table_context['lines'][index], currency_target, number_of_digits)
#     print("views. dashboard. Time taken for summary table calcs", time.time() - start_t)

#     start_t = time.time()

#     chart_settings = request.session['chart_settings']
#     chart_settings['To'] = get_last_exit_date_for_brokers_old_approach(selected_brokers, effective_current_date).strftime('%Y-%m-%d')
#     from_date = calculate_from_date(chart_settings['To'], chart_settings['timeline'])
#     if from_date == '1900-01-01':
#         from_date = Transactions.objects.filter(investor=user, broker__in=selected_brokers).order_by('date').first().date
#     chart_settings['From'] = from_date.strftime('%Y-%m-%d')
#     # chart_data = get_chart_data(user.id, selected_brokers, chart_settings['frequency'], chart_settings['From'], chart_settings['To'], currency_target, chart_settings['breakdown'])

#     # Add the "Currency" key to the dictionary
#     chart_data = {}
#     chart_data["currency"] = currency_target + "k"

#     # Now convert the dictionary to a JSON string
#     chart_dataset = json.dumps(chart_data, default=decimal_default)

#     print("views. dashboard. Time taken for chart data calcs", time.time() - start_t)

#     buttons = ['transaction', 'broker', 'price', 'security', 'settings']

#     formBrokerUpdate = BrokerPerformanceForm(investor=user)

#     print("Total time taken:", time.time() - start_time)

#     return render(request, 'dashboard.html', {
#         'sidebar_width': sidebar_width,
#         'sidebar_padding': sidebar_padding,
#         'analysis': analysis,
#         'json_analysis': json_analysis, # Feed for chart_dataset
#         'currency': currency_target,
#         'table_date': effective_current_date,
#         'brokers': Brokers.objects.filter(investor=user).all(),
#         'selectedBrokers': user.custom_brokers,
#         'summary': summary,
#         'chart_settings': chart_settings,
#         'chartDataset': chart_dataset,
#         'dashboardForm': dashboard_form,
#         'buttons': buttons,
#         'lines': financial_table_context['lines'],
#         'years': financial_table_context['years'],
#         'formBrokerUpdate': formBrokerUpdate,
#     })

# def nav_chart_data_request(request):

#     # global selected_brokers
#     user = request.user
#     print("views. dashboard. 148", user)
#     selected_brokers = broker_group_to_ids_old_approach(user.custom_brokers, user)

#     if request.method == 'GET':
#         frequency = request.GET.get('frequency')
#         from_date = request.GET.get('from')
#         to_date = request.GET.get('to')
#         breakdown = request.GET.get('breakdown')

#         # print("database. views. 115", selected_brokers, frequency, from_date, to_date, request.user.default_currency, breakdown)

#         chart_data = get_chart_data(request.user.id, selected_brokers, frequency, from_date, to_date, request.user.default_currency, breakdown)

#         return JsonResponse(chart_data)

#     return JsonResponse({'error': 'Invalid request method'}, status=400)

# @login_required
# def dashboard_summary_api(request):
#     user = request.user
#     effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
#     currency_target = user.default_currency
#     selected_brokers = broker_group_to_ids_old_approach(user.custom_brokers, user)

#     analysis = NAV_at_date_old_structure(user.id, selected_brokers, effective_current_date, currency_target, ['Asset type', 'Currency', 'Asset class'])
    
#     summary_data = {
#         'totalValue': currency_format_old_structure(analysis['Total NAV'], currency_target, user.digits),
#         'change': format_percentage_old_structure(Irr_old_structure(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=selected_brokers), digits=1)
#     }
#     return JsonResponse(summary_data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_summary_api(request):
    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    summary = {}

    # Calculate NAV
    summary['Current NAV'] = NAV_at_date(user.id, tuple (selected_brokers), effective_current_date, currency_target)['Total NAV']

    # Calculate Invested and Cash-out
    summary['Invested'] = Decimal(0)
    summary['Cash-out'] = Decimal(0)

    transactions = Transactions.objects.filter(
        investor=user,
        broker__in=selected_brokers,
        date__lte=effective_current_date,
        type__in=['Cash in', 'Cash out']
    ).values('currency', 'type', 'cash_flow', 'date').annotate(
        total=Sum('cash_flow')
    )

    for transaction in transactions:
        fx_rate = FX.get_rate(transaction['currency'], currency_target, transaction['date'], user)['FX']
        if transaction['type'] == 'Cash in':
            summary['Invested'] += Decimal(transaction['total']) * Decimal(fx_rate)
        else:
            summary['Cash-out'] += Decimal(transaction['total']) * Decimal(fx_rate)

    # Calculate IRR and Return
    try:
        summary['total_return'] = (summary['Current NAV'] - summary['Cash-out']) / summary['Invested'] - 1
    except ZeroDivisionError:
        summary['total_return'] = None

    summary['irr'] = IRR(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=selected_brokers)

    summary = format_table_data(summary, currency_target, number_of_digits)
    
    return Response(summary)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_breakdown_api(request):
    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    analysis = NAV_at_date(user.id, tuple(selected_brokers), effective_current_date, currency_target, tuple(['asset_type', 'currency', 'asset_class']))
    
    # Remove 'Total NAV' from the analysis
    total_nav = analysis.pop('Total NAV', None)
    
    # Calculate percentage breakdowns
    calculate_percentage_shares(analysis, ['asset_type', 'currency', 'asset_class'])
    
    # Format the values
    analysis = format_table_data(analysis, currency_target, number_of_digits)
    
    return Response({
        'assetType': {
            'data': analysis['asset_type'],
            'percentage': analysis['asset_type_percentage']
        },
        'currency': {
            'data': analysis['currency'],
            'percentage': analysis['currency_percentage']
        },
        'assetClass': {
            'data': analysis['asset_class'],
            'percentage': analysis['asset_class_percentage']
        },
        'totalNAV': currency_format(total_nav, currency_target, number_of_digits)
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_summary_over_time_api(request):
    try:
        user = request.user
        effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
        
        currency_target = user.default_currency
        selected_brokers = broker_group_to_ids(user.custom_brokers, user)

        # Determine the starting year
        stored_data = AnnualPerformance.objects.select_related('investor').filter(
            investor=user,
            broker_group=user.custom_brokers,
            currency=currency_target,
            restricted=None
        )

        first_entry = stored_data.order_by('year').first()
        if not first_entry:
            return Response({"message": "No data available for the selected period."}, status=status.HTTP_404_NOT_FOUND)
        
        start_year = first_entry.year
        last_exit_date = get_last_exit_date_for_brokers(selected_brokers, effective_current_date)
        last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_current_date.year else effective_current_date.year - 1
        years = list(range(start_year, last_year + 1))

        line_names = [
            "BoP NAV", "Invested", "Cash out", "Price change", "Capital distribution",
            "Commission", "Tax", "FX", "EoP NAV", "TSR"
        ]
        
        lines = defaultdict(lambda: {"name": "", "data": {}})
        for name in line_names:
            lines[name]["name"] = name
        
        # Fetch stored data
        stored_data = stored_data.filter(year__in=years).values_list('year', *[name.lower().replace(' ', '_') for name in line_names])

        # Process stored data
        processed_data = {
            entry[0]: {line_names[i]: entry[i+1] for i in range(len(line_names))}
            for entry in stored_data
        }

        for line_name in line_names:
            lines[line_name]['data'] = {year: processed_data[year][line_name] for year in processed_data}

        # Calculate YTD for the current year
        current_year = effective_current_date.year
        ytd_data = calculate_performance(user, date(current_year, 1, 1), effective_current_date, selected_brokers, currency_target)

        for line_name in line_names:
            ytd_field_name = line_name.lower().replace(' ', '_')
            lines[line_name]["data"]["YTD"] = ytd_data[ytd_field_name]

        # Calculate All-time data
        for line_name, line_data in lines.items():
            if line_name != 'TSR':
                line_data["data"]["All-time"] = sum(value for year, value in line_data["data"].items() if year != "All-time")

        lines['TSR']["data"]["All-time"] = format_percentage(IRR(user.id, effective_current_date, currency_target, broker_id_list=selected_brokers), digits=1)
        lines['BoP NAV']['data']['All-time'] = Decimal(0)
        lines['EoP NAV']["data"]["All-time"] = lines['EoP NAV']["data"].get("YTD", Decimal(0))

        # Format the data
        format_funcs = {
            Decimal: lambda v: currency_format(v, currency_target, user.digits),
            float: lambda v: f"{v:.2%}"
        }

        for line in lines.values():
            line['data'] = {
                year: format_funcs.get(type(value), str)(value)
                for year, value in line['data'].items()
            }

        return Response({
            "years": years,
            "lines": list(lines.values()),
            "currentYear": str(current_year)
        }, status=status.HTTP_200_OK)
    
    except AnnualPerformance.DoesNotExist:
        return Response({"error": "No annual performance data found."}, status=status.HTTP_404_NOT_FOUND)
    except DatabaseError:
        return Response({"error": "Database error occurred while fetching data"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except KeyError:
        return Response({"error": "Invalid session data"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_nav_chart_data(request):
    user = request.user
    frequency = request.GET.get('frequency')
    from_date = request.GET.get('dateFrom')
    to_date = request.GET.get('dateTo')
    breakdown = request.GET.get('breakdown')
    currency = user.default_currency
    brokers = broker_group_to_ids(user.custom_brokers, user)

    # If no dates are provided, use 'ytd' as default
    if not from_date or not to_date:
        to_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
        from_date = date(to_date.year, 1, 1).isoformat()  # Start of current year

    logger.info(f"Received request for NAV chart data with frequency: {frequency}, from date: {from_date}, to date: {to_date}, breakdown: {breakdown}, currency: {currency}, brokers: {user.custom_brokers}")

    # try:
    chart_data = get_nav_chart_data(user.id, brokers, frequency, from_date, to_date, currency, breakdown)
    return Response(chart_data)
    # except ValueError as e:
    #     return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    # except Exception as e:
    #     return Response({'error': 'An unexpected error occurred: ' + str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)