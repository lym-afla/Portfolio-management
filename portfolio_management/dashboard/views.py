from datetime import datetime
import time
import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from common.models import AnnualPerformance, Brokers, Transactions, FX
from common.forms import DashboardForm
from database.forms import BrokerPerformanceForm
from utils import NAV_at_date_old_structure, Irr_old_structure, broker_group_to_ids, calculate_from_date, calculate_percentage_shares, currency_format_old_structure, currency_format_dict_values, decimal_default, format_percentage_old_structure, get_chart_data, get_last_exit_date_for_brokers, dashboard_summary_over_time

@login_required
def dashboard(request):
    start_time = time.time()
    start_t = time.time()

    user = request.user
    
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    # use_default_currency = user.use_default_currency_where_relevant
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    sidebar_padding = 0
    sidebar_width = 0
    brokers = Brokers.objects.filter(investor=user, id__in=selected_brokers).all()

    sidebar_width = request.GET.get("width")
    sidebar_padding = request.GET.get("padding")

    # print("views. dashboard", effective_current_date)

    initial_data = {
        'selected_brokers': selected_brokers,
        'default_currency': currency_target,
        'table_date': effective_current_date,
        'digits': number_of_digits
    }
    dashboard_form = DashboardForm(instance=user, initial=initial_data)

    print("views. dashboard. Time taken for preparatory calcs", time.time() - start_t)

    start_t = time.time()
    analysis = NAV_at_date_old_structure(user.id, selected_brokers, effective_current_date, currency_target, ['Asset type', 'Currency', 'Asset class'])
    print("views. dashboard. Time taken for NAV at date calc", time.time() - start_t)

    start_t = time.time()

    summary = {}
    summary['NAV'] = analysis['Total NAV']
    currencies = set()
    for broker in brokers:
        currencies.update(broker.get_currencies())

    summary['Invested'] = summary['Cash-out'] = 0

    for cur in currencies:
        quote = Transactions.objects.filter(investor=user, broker__in=selected_brokers, currency=cur, date__lte=effective_current_date, type__in=['Cash in', 'Cash out']).values_list('cash_flow', 'date', 'type')
        for cash_flow, date, transaction_type in quote:
            if transaction_type == 'Cash in':
                summary['Invested'] += cash_flow * FX.get_rate(cur, currency_target, date)['FX']
            else:
                summary['Cash-out'] += cash_flow * FX.get_rate(cur, currency_target, date)['FX']
    
    summary['IRR'] = format_percentage_old_structure(Irr_old_structure(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=selected_brokers), digits=1)
    
    try:
        summary['Return'] = format_percentage_old_structure((summary['NAV'] - summary['Cash-out']) / summary['Invested'] - 1, digits=1)
    except:
        summary['Return'] = '–'
    
    # Convert data to string representation to feed the page
    summary['NAV'] = currency_format_old_structure(summary['NAV'], currency_target, number_of_digits)
    summary['Invested'] = currency_format_old_structure(summary['Invested'], currency_target, number_of_digits)
    summary['Cash-out'] = currency_format_old_structure(summary['Cash-out'], currency_target, number_of_digits)

    # Convert Python object to JSON string to be recognizable by Chart.js
    json_analysis = json.dumps(analysis, default=decimal_default)

    # Add percentage breakdowns
    calculate_percentage_shares(analysis, ['Asset type', 'Currency', 'Asset class'])
    analysis = currency_format_dict_values(analysis, currency_target, number_of_digits)

    print("views. dashboard. Time taken for summary dict calcs", time.time() - start_t)

    start_t = time.time()

    financial_table_context = dashboard_summary_over_time(user, effective_current_date, user.custom_brokers, currency_target)
    # Formatting outputs
    for index in range(len(financial_table_context['lines'])):
        if financial_table_context['lines'][index]['name'] == 'TSR':
            for k, v in financial_table_context['lines'][index]['data'].items():
                financial_table_context['lines'][index]['data'][k] = format_percentage_old_structure(v, digits=1)
        else:
            financial_table_context['lines'][index] = currency_format_dict_values(financial_table_context['lines'][index], currency_target, number_of_digits)
    print("views. dashboard. Time taken for summary table calcs", time.time() - start_t)

    start_t = time.time()

    chart_settings = request.session['chart_settings']
    chart_settings['To'] = get_last_exit_date_for_brokers(selected_brokers, effective_current_date)
    from_date = calculate_from_date(chart_settings['To'], chart_settings['timeline'])
    if from_date == '1900-01-01':
        from_date = Transactions.objects.filter(investor=user, broker__in=selected_brokers).order_by('date').first().date
    chart_settings['From'] = from_date
    # chart_data = get_chart_data(user.id, selected_brokers, chart_settings['frequency'], chart_settings['From'], chart_settings['To'], currency_target, chart_settings['breakdown'])

    # Add the "Currency" key to the dictionary
    chart_data = {}
    chart_data["currency"] = currency_target + "k"

    # Now convert the dictionary to a JSON string
    chart_dataset = json.dumps(chart_data, default=decimal_default)

    print("views. dashboard. Time taken for chart data calcs", time.time() - start_t)

    buttons = ['transaction', 'broker', 'price', 'security', 'settings']

    formBrokerUpdate = BrokerPerformanceForm(investor=user)

    print("Total time taken:", time.time() - start_time)

    return render(request, 'dashboard.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'analysis': analysis,
        'json_analysis': json_analysis, # Feed for chart_dataset
        'currency': currency_target,
        'table_date': effective_current_date,
        'brokers': Brokers.objects.filter(investor=user).all(),
        'selectedBrokers': user.custom_brokers,
        'summary': summary,
        'chart_settings': chart_settings,
        'chartDataset': chart_dataset,
        'dashboardForm': dashboard_form,
        'buttons': buttons,
        'lines': financial_table_context['lines'],
        'years': financial_table_context['years'],
        'formBrokerUpdate': formBrokerUpdate,
    })

def nav_chart_data_request(request):

    # global selected_brokers
    user = request.user
    print("views. dashboard. 148", user)
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    if request.method == 'GET':
        frequency = request.GET.get('frequency')
        from_date = request.GET.get('from')
        to_date = request.GET.get('to')
        breakdown = request.GET.get('breakdown')

        # print("database. views. 115", selected_brokers, frequency, from_date, to_date, request.user.default_currency, breakdown)

        chart_data = get_chart_data(request.user.id, selected_brokers, frequency, from_date, to_date, request.user.default_currency, breakdown)

        return JsonResponse(chart_data)

    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def dashboard_summary_api(request):
    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    currency_target = user.default_currency
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    analysis = NAV_at_date_old_structure(user.id, selected_brokers, effective_current_date, currency_target, ['Asset type', 'Currency', 'Asset class'])
    
    summary_data = {
        'totalValue': currency_format_old_structure(analysis['Total NAV'], currency_target, user.digits),
        'change': format_percentage_old_structure(Irr_old_structure(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=selected_brokers), digits=1)
    }
    return JsonResponse(summary_data)