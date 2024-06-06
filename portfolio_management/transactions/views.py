from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from common.models import Brokers, Transactions
from common.forms import DashboardForm
from utils import currency_format, effective_current_date, selected_brokers

@login_required
def transactions(request):

    user = request.user

    global effective_current_date

    currency_target = user.default_currency
    number_of_digits = user.digits
    selected_brokers = user.custom_brokers

    sidebar_padding = 0
    sidebar_width = 0
    brokers = Brokers.objects.filter(investor=user, id__in=selected_brokers).all()

    sidebar_width = request.GET.get("width")
    sidebar_padding = request.GET.get("padding")


    initial_data = {
        'selected_brokers': selected_brokers,
        'default_currency': currency_target,
        'table_date': effective_current_date,
        'digits': number_of_digits
    }
    dashboard_form = DashboardForm(instance=user, initial=initial_data)

    currencies = set()
    for broker in brokers:
        currencies.update(broker.get_currencies())
        
    transactions = Transactions.objects.filter(
        investor=user,
        date__lte=effective_current_date,
        broker_id__in=selected_brokers
    ).select_related('broker', 'security').order_by('date').all()

    balance = {}
    for transaction in transactions:
        # transaction.balances = [0 for _ in range(len(currencies))]
        transaction.balances = {}
        for currency in currencies:
            if transaction.currency == currency:
                balance[currency] = balance.get(currency,0) - (transaction.price or 0) * (transaction.quantity or 0) \
                    + (transaction.cash_flow or 0) \
                        + (transaction.commission or 0)
            else:
                balance[currency] = balance.get(currency,0)
            transaction.balances[currency] = currency_format(balance[currency], currency, number_of_digits)

        # Prepare data for passing to the front-end
        if transaction.quantity:
            transaction.value = currency_format(-transaction.quantity * transaction.price + (transaction.commission or 0), transaction.currency, number_of_digits)
            transaction.quantity = abs(round(transaction.quantity, 0))
        if transaction.cash_flow:
            transaction.cash_flow = currency_format(transaction.cash_flow, transaction.currency, number_of_digits)
        transaction.date = str(transaction.date.strftime('%d-%b-%y'))
        if transaction.commission:
            transaction.commission = currency_format(-transaction.commission, transaction.currency, number_of_digits)
           
    buttons = ['transaction', 'settings']

    return render(request, 'transactions.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'transactions': transactions,
        'brokers': brokers,
        'currencies': currencies,
        'currency': currency_target,
        'table_date': effective_current_date,
        'number_of_digits': number_of_digits,
        'selectedBrokers': selected_brokers,
        'dashboardForm': dashboard_form,
        'buttons': buttons,
    })