from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from common.models import Brokers, Transactions
from common.forms import DashboardForm
from utils import currency_format, effective_current_date, selected_brokers

@login_required
def transactions(request):

    user = request.user

    global effective_current_date
    global selected_brokers

    currency_target = user.default_currency
    number_of_digits = user.digits

    sidebar_padding = 0
    sidebar_width = 0
    brokers = Brokers.objects.all()

    if request.method == "GET":
        sidebar_width = request.GET.get("width")
        sidebar_padding = request.GET.get("padding")

    if request.method == "POST":

        dashboard_form = DashboardForm(request.POST, instance=request.user)

        if dashboard_form.is_valid():
            # Process the form data
            selected_brokers = dashboard_form.cleaned_data['selected_brokers']
            currency_target = dashboard_form.cleaned_data['default_currency']
            effective_current_date = dashboard_form.cleaned_data['table_date']
            number_of_digits = dashboard_form.cleaned_data['digits']
            
            # Save new parameters to user setting
            user.default_currency = currency_target
            user.digits = number_of_digits
            user.save()
    else:
        initial_data = {
            'selected_brokers': selected_brokers,
            'default_currency': currency_target,
            'table_date': effective_current_date,
            'digits': number_of_digits
        }
        dashboard_form = DashboardForm(instance=request.user, initial=initial_data)

    currencies = set()
    for broker in Brokers.objects.filter(id__in=selected_brokers):
        currencies.update(broker.get_currencies())
        
    transactions = Transactions.objects.filter(
        date__lte=effective_current_date,
        broker_id__in=selected_brokers
    ).select_related('broker', 'security').order_by('date')

    # transactions = db.session.query(PA_transactions, PA.name).join(PA).\
    #     filter(func.date(PA_transactions.date) <= table_date,
    #            PA_transactions.broker_id.in_(selected_brokers)).all()
                   
    # # Add cash movements
    # transactions.extend(db.session.query(PA_transactions, PA_transactions.type).\
    #     filter(func.date(PA_transactions.date) <= table_date,
    #        PA_transactions.broker_id.in_(selected_brokers),
    #        PA_transactions.security_id == None).all())
        
    # transactions.sort(key=lambda x: x[0].date)
        
    # Calculate cash balance for each currency
    # balance = [0 for _ in range(len(currencies))]
    balance = {}
    for transaction in transactions:
        # transaction.balances = [0 for _ in range(len(currencies))]
        transaction.balances = {}
        for currency in currencies:
            if transaction.currency == currency:
                balance[currency] = balance.get(currency,0) - (transaction.price or 0) * (transaction.quantity or 0) \
                    + (transaction.cash_flow or 0) \
                        + (transaction.commission or 0)
            transaction.balances[currency] = currency_format(balance[currency], currency, number_of_digits)

        # Prepare data for passing to the front-end
        if transaction.quantity:
            transaction.value = currency_format(-transaction.quantity * transaction.price, currency_target, number_of_digits)
            transaction.quantity = abs(transaction.quantity)
        if transaction.cash_flow:
            transaction.cash_flow = currency_format(transaction.cash_flow, currency, number_of_digits)
        transaction.date = str(transaction.date.strftime('%d-%b-%y'))
           
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
    })