from django.shortcuts import render
from .models import Brokers, PA_transactions, FX
from .utils import NAV_at_date, PA_irr, chart_dates, chart_labels, chart_colour
from datetime import date

selected_brokers = [2]
currency_target = 'USD'
table_date = date.today()
numberOfDigits = 0
# Default values for NAV chart
nav_settings = {}
nav_settings['breakdown'] = 'Broker'
nav_settings['frequency'] = 'M'
nav_settings['timeline'] = '6m'
nav_settings['From'] = date(date.today().year, 1, 1)
nav_settings['To'] = table_date

def pa_dashboard(request):

    global currency_target
    global table_date
    global numberOfDigits
    global selected_brokers
    global nav_settings

    sidebar_padding = 0
    sidebar_width = 0
    brokers = Brokers.objects.all()

    if request.method == "GET":
        sidebar_width = request.GET.get("width")
        sidebar_padding = request.GET.get("padding")

    if request.method == "POST":
        currency_target = request.POST.get('tableCurrency', currency_target)
        table_date = request.POST.get('date', table_date)
        numberOfDigits = request.POST.get('numberOfDigits', numberOfDigits)
        selected_brokers = list(map(int, request.POST.getlist('selectedBrokers'))) or selected_brokers

        nav_settings['breakdown'] = request.POST.get('chartBreakdown', nav_settings['breakdown'])
        nav_settings['frequency'] = request.POST.get('chartFrequency', nav_settings['frequency'])
        nav_settings['timeline'] = request.POST.get('chartTimeline', nav_settings['timeline'])
        nav_settings['From'] = request.POST.get('From', nav_settings['From'])
        if nav_settings['From'] == '2000-01-01':
            nav_settings['From'] = PA_transactions.objects.filter(brokers__in=selected_brokers).order_by('date').first().date
        nav_settings['To'] = request.POST.get('To', nav_settings['To'])

    analysis = NAV_at_date(selected_brokers, table_date, currency_target, ['Asset type', 'Currency', 'Asset class'])

    summary = {}
    summary['NAV'] = sum(analysis['Asset class'].values())
    print(summary, analysis)
    currencies = set()
    for broker in Brokers.objects.filter(id__in=selected_brokers):
        currencies.update(broker.currencies())

    summary['Invested'] = summary['Cash-out'] = 0

    for cur in currencies:
        quote = PA_transactions.objects.filter(broker__in=selected_brokers, currency=cur, date__lte=table_date, type__in=['Cash in', 'Cash out']).values_list('cash_flow', 'date', 'type')
        for cash_flow, date, transaction_type in quote:
            if transaction_type == 'Cash in':
                summary['Invested'] += cash_flow * FX.get_rate(cur, currency_target, date)['FX']
            else:
                summary['Cash-out'] += cash_flow * FX.get_rate(cur, currency_target, date)['FX']
    print(summary)
    summary['Return'] = round(summary['NAV'] / summary['Invested'] - 1, 4)
    summary['IRR'] = PA_irr(table_date, currency_target, asset_id='', broker_id_list=selected_brokers)

    dates = chart_dates(nav_settings['From'], nav_settings['To'], nav_settings['frequency'])
    labels = chart_labels(dates, nav_settings['frequency'])

    chart_dataset = []
    for d in dates:
        IRR = PA_irr(d, currency_target, '', selected_brokers)
        if nav_settings["breakdown"] == 'No breakdown':
            NAV = NAV_at_date(selected_brokers, d, currency_target, ['aggregate'])['aggregate'] / 1000
            if len(chart_dataset) == 0:
                chart_dataset.append({
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
                chart_dataset.append({
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
                chart_dataset[0]['data'].append(IRR)
                chart_dataset[1]['data'].append(NAV)
        else:
            print(f"views.py, line 105 {nav_settings}")
            NAV = NAV_at_date(selected_brokers, d, currency_target, [nav_settings['breakdown']])[nav_settings['breakdown']]
            if len(chart_dataset) == 0:
                chart_dataset.append({
                    'label': 'IRR (RHS)',
                    'data': [IRR],
                    'backgroundColor': 'rgb(0, 0, 0)',
                    'type': 'line',
                    'yAxisID': 'y1',
                    'order': 0,
                })
            else:
                chart_dataset[0]['data'].append(IRR)
                
            for key, value in NAV.items():
                index = next((index for (index, item) in enumerate(chart_dataset) if item["label"] == key), None)
                if index is None:
                    if len(chart_dataset) == 0 or d == dates[0]:
                        data_entry = [value / 1000]
                    else:
                        data_entry = [0 for i in range(len(chart_dataset[-1]['data']))]
                        data_entry.append(value / 1000)
                    chart_dataset.append({
                        'label': key,
                        'data': data_entry,
                        'backgroundColor': chart_colour(len(chart_dataset) - 1),
                        'stack': 'combined',
                        'type': 'bar',
                        'yAxisID': 'y'
                    })
                else:
                    chart_dataset[index]['data'].append(value / 1000)
    
    return render(request, 'dashboard/pa-dashboard.html', {
        'analysis': analysis,
        'currency': currency_target,
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'table_date': table_date,
        'number_of_digits': numberOfDigits,
        'brokers': brokers,
        'selectedBrokers': selected_brokers,
        'summary': summary,
        'navSettings': nav_settings,
        'chartLabels': labels,
        'chartDataset': chart_dataset
    })