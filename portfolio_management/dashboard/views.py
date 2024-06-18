import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from common.models import Brokers, Transactions, FX
from common.forms import DashboardForm
from utils import NAV_at_date, Irr, calculate_from_date, calculate_percentage_shares, currency_format, currency_format_dict_values, decimal_default, format_percentage, get_chart_data, effective_current_date

@login_required
def dashboard(request):

    user = request.user
    
    # global selected_brokers
    global effective_current_date
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    use_default_currency = user.use_default_currency_where_relevant
    selected_brokers = user.custom_brokers

    sidebar_padding = 0
    sidebar_width = 0
    brokers = Brokers.objects.filter(id__in=selected_brokers, investor=user).all()

    sidebar_width = request.GET.get("width")
    sidebar_padding = request.GET.get("padding")

    initial_data = {
        'selected_brokers': selected_brokers,
        'default_currency': currency_target,
        'table_date': effective_current_date,
        'digits': number_of_digits
    }
    dashboard_form = DashboardForm(instance=request.user, initial=initial_data)

    analysis = NAV_at_date(user.id, selected_brokers, effective_current_date, currency_target, ['Asset type', 'Currency', 'Asset class'])

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
    
    summary['IRR'] = format_percentage(Irr(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=selected_brokers), digits=1)
    
    try:
        summary['Return'] = format_percentage((summary['NAV'] - summary['Cash-out']) / summary['Invested'] - 1, digits=1)
    except:
        summary['Return'] = '–'
    
    # Convert data to string representation to feed the page
    summary['NAV'] = currency_format(summary['NAV'], currency_target, number_of_digits)
    summary['Invested'] = currency_format(summary['Invested'], currency_target, number_of_digits)
    summary['Cash-out'] = currency_format(summary['Cash-out'], currency_target, number_of_digits)
    

    # Convert Python object to JSON string to be recognizable by Chart.js
    json_analysis = json.dumps(analysis, default=decimal_default)

    # Add percentage breakdowns
    calculate_percentage_shares(analysis, ['Asset type', 'Currency', 'Asset class'])
    
    chart_settings = request.session['chart_settings']
    chart_settings['To'] = effective_current_date
    from_date = calculate_from_date(chart_settings['To'], chart_settings['timeline'])
    if from_date == '1900-01-01':
        from_date = Transactions.objects.filter(investor=user, broker__in=brokers).order_by('date').first().date
    # print(f"views.dashboard. Line 65. From date: {from_date}")
    chart_settings['From'] = from_date
    # print(f"dashboard.views line 86. chart_settings['From']: {chart_settings['From']}")
    analysis = currency_format_dict_values(analysis, currency_target, number_of_digits)
    chart_data = get_chart_data(user.id, selected_brokers, chart_settings['frequency'], chart_settings['From'], chart_settings['To'], currency_target, chart_settings['breakdown'])

    # Add the "Currency" key to the dictionary
    chart_data["currency"] = currency_target + "k"

    # Now convert the dictionary to a JSON string
    chart_dataset = json.dumps(chart_data, default=decimal_default)

    # selected_brokers = [{'id': broker.id, 'name': broker.name} for broker in brokers]

    buttons = ['transaction', 'broker', 'price', 'security', 'settings']
    print("views. dashboard. 94", selected_brokers, user.custom_brokers)

    return render(request, 'dashboard.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'analysis': analysis,
        'json_analysis': json_analysis, # Feed for chart_dataset
        'currency': currency_target,
        'table_date': effective_current_date,
        'brokers': Brokers.objects.filter(investor=user).all(),
        'selectedBrokers': selected_brokers,
        'summary': summary,
        'chart_settings': chart_settings,
        'chartDataset': chart_dataset,
        'dashboardForm': dashboard_form,
        'buttons': buttons,
    })

def nav_chart_data_request(request):

    # global selected_brokers
    selected_brokers = request.user.custom_brokers

    if request.method == 'GET':
        frequency = request.GET.get('frequency')
        from_date = request.GET.get('from')
        to_date = request.GET.get('to')
        breakdown = request.GET.get('breakdown')

        # print("database. views. 115", selected_brokers, frequency, from_date, to_date, request.user.default_currency, breakdown)

        chart_data = get_chart_data(request.user.id, selected_brokers, frequency, from_date, to_date, request.user.default_currency, breakdown)

        return JsonResponse(chart_data)

    return JsonResponse({'error': 'Invalid request method'}, status=400)