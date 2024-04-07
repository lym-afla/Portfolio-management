import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from common.models import Brokers, Transactions, FX
from utils import NAV_at_date, Irr, calculate_from_date, calculate_percentage_shares, chart_dates, chart_labels, chart_colour, currency_format, currency_format_dict_values, decimal_default, format_percentage, get_chart_data
from datetime import date

selected_brokers = [2]
currency_target = 'USD'
table_date = date.today()
number_of_digits = 0
# Default values for NAV chart
navchart_settings = {}
navchart_settings['breakdown'] = 'Asset type'
navchart_settings['frequency'] = 'M'
navchart_settings['timeline'] = '6m'
navchart_settings['From'] = date(date.today().year, 1, 1)
navchart_settings['To'] = table_date

@login_required
def dashboard(request):

    currency_target = request.session['default_currency']
    global table_date
    number_of_digits = request.session['digits']
    global selected_brokers
    global navchart_settings

    sidebar_padding = 0
    sidebar_width = 0
    brokers = Brokers.objects.all()

    if request.method == "GET":
        sidebar_width = request.GET.get("width")
        sidebar_padding = request.GET.get("padding")

    # if request.method == "POST":
    #     currency_target = request.POST.get('tableCurrency', currency_target)
    #     table_date = request.POST.get('date', table_date)
    #     number_of_digits = request.POST.get('numberOfDigits', number_of_digits)
    #     selected_brokers = list(map(int, request.POST.getlist('selectedBrokers'))) or selected_brokers

    #     navchart_settings['breakdown'] = request.POST.get('chartBreakdown', navchart_settings['breakdown'])
    #     navchart_settings['frequency'] = request.POST.get('chartFrequency', navchart_settings['frequency'])
    #     navchart_settings['timeline'] = request.POST.get('chartTimeline', navchart_settings['timeline'])
    #     navchart_settings['From'] = request.POST.get('From', navchart_settings['From'])
    #     if navchart_settings['From'] == '2000-01-01':
    #         navchart_settings['From'] = Transactions.objects.filter(brokers__in=selected_brokers).order_by('date').first().date
    #     navchart_settings['To'] = request.POST.get('To', navchart_settings['To'])

    analysis = NAV_at_date(selected_brokers, table_date, currency_target, ['Asset type', 'Currency', 'Asset class'])

    summary = {}
    summary['NAV'] = analysis['Total NAV']
    currencies = set()
    for broker in Brokers.objects.filter(id__in=selected_brokers):
        currencies.update(broker.currencies())

    summary['Invested'] = summary['Cash-out'] = 0

    for cur in currencies:
        quote = Transactions.objects.filter(broker__in=selected_brokers, currency=cur, date__lte=table_date, type__in=['Cash in', 'Cash out']).values_list('cash_flow', 'date', 'type')
        for cash_flow, date, transaction_type in quote:
            if transaction_type == 'Cash in':
                summary['Invested'] += cash_flow * FX.get_rate(cur, currency_target, date)['FX']
            else:
                summary['Cash-out'] += cash_flow * FX.get_rate(cur, currency_target, date)['FX']
    summary['Return'] = format_percentage(summary['NAV'] / summary['Invested'] - 1)
    summary['IRR'] = format_percentage(Irr(table_date, currency_target, asset_id=None, broker_id_list=selected_brokers))
    
    # Convert data to string representation to feed the page
    summary['NAV'] = currency_format(summary['NAV'], currency_target, number_of_digits)
    summary['Invested'] = currency_format(summary['Invested'], currency_target, number_of_digits)
    summary['Cash-out'] = currency_format(summary['Cash-out'], currency_target, number_of_digits)
    
    # Convert Python object to JSON string to be recognizable by Chart.js
    json_analysis = json.dumps(analysis, default=decimal_default)

    # Add percentage breakdowns
    calculate_percentage_shares(analysis, ['Asset type', 'Currency', 'Asset class'])
    
    chart_settings = request.session['chart_settings']
    chart_settings['breakdown'] = navchart_settings['breakdown']
    from_date = calculate_from_date(chart_settings['To'], chart_settings['timeline'])
    chart_settings['From'] = from_date
    analysis = currency_format_dict_values(analysis, currency_target, number_of_digits)
    chart_data = get_chart_data(selected_brokers, chart_settings['frequency'], chart_settings['From'], chart_settings['To'], currency_target, navchart_settings['breakdown'])

    # Add the "Currency" key to the dictionary
    chart_data["currency"] = currency_target + "k"

    # Now convert the dictionary to a JSON string
    chart_dataset = json.dumps(chart_data, default=decimal_default)
    print(chart_dataset)

    return render(request, 'dashboard/pa-dashboard.html', {
        'analysis': analysis,
        'json_analysis': json_analysis,
        'currency_digits': f'{currency_target},{number_of_digits}',
        # 'currency': currency_target,
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'table_date': table_date,
        # 'number_of_digits': numberOfDigits,
        'brokers': brokers,
        'selectedBrokers': selected_brokers,
        'summary': summary,
        'chart_settings': chart_settings,
        'chartDataset': chart_dataset
    })

def nav_chart_data_request(request):
    if request.method == 'GET':
        frequency = request.GET.get('frequency')
        from_date = request.GET.get('from')
        to_date = request.GET.get('to')

        chart_data = get_chart_data(type, id, frequency, from_date, to_date, currency, properties)

        return JsonResponse(chart_data)

    return JsonResponse({'error': 'Invalid request method'}, status=400)