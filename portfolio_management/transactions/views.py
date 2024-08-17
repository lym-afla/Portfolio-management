from datetime import datetime
from decimal import Decimal
from itertools import chain
from operator import attrgetter
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from common.models import Brokers, FXTransaction, Transactions
from common.forms import DashboardForm
from utils import broker_group_to_ids, currency_format_old_structure

@login_required
def transactions(request):

    user = request.user

    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()

    currency_target = user.default_currency
    number_of_digits = user.digits
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

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
        
    # Fetch regular transactions
    transactions = Transactions.objects.filter(
        investor=user,
        date__lte=effective_current_date,
        broker_id__in=selected_brokers
    ).select_related('broker', 'security').order_by('date').all()

    # Fetch FX transactions
    fx_transactions = FXTransaction.objects.filter(
        investor=user,
        date__lte=effective_current_date,
        broker_id__in=selected_brokers
    ).select_related('broker').order_by('date').all()

    # Merge and sort all transactions
    all_transactions = sorted(
        chain(transactions, fx_transactions),
        key=attrgetter('date')
    )

    balance = {currency: Decimal(0) for currency in currencies}

    for transaction in all_transactions:
        transaction.balances = {}

        if isinstance(transaction, Transactions):
            # for currency in currencies:
            #     if transaction.currency == currency:
            balance[transaction.currency] = balance.get(transaction.currency, Decimal(0)) - Decimal((transaction.price or 0) * Decimal(transaction.quantity or 0) \
                - Decimal(transaction.cash_flow or 0) \
                - Decimal(transaction.commission or 0))
                # else:
                #     balance[currency] = balance.get(currency, Decimal(0))
            for currency in currencies:
                transaction.balances[currency] = currency_format_old_structure(balance[currency], currency, number_of_digits)

            # Prepare data for passing to the front-end
            if transaction.quantity:
                transaction.value = currency_format_old_structure(-round(Decimal(transaction.quantity * transaction.price), 2) + (transaction.commission or 0), transaction.currency, number_of_digits)
                transaction.price = currency_format_old_structure(transaction.price, transaction.currency, number_of_digits)
                transaction.quantity = abs(round(transaction.quantity, 0))
            if transaction.cash_flow:
                transaction.cash_flow = currency_format_old_structure(transaction.cash_flow, transaction.currency, number_of_digits)
            if transaction.commission:
                transaction.commission = currency_format_old_structure(-transaction.commission, transaction.currency, number_of_digits)
           
        elif isinstance(transaction, FXTransaction):
            # FX transaction

            transaction.type = 'FX'

            balance[transaction.from_currency] -= transaction.from_amount
            balance[transaction.to_currency] += transaction.to_amount
            if transaction.commission:
                balance[transaction.from_currency] -= transaction.commission

            for currency in currencies:
                transaction.balances[currency] = currency_format_old_structure(balance[currency], currency, number_of_digits)

            # Prepare FX transaction data for front-end
            transaction.from_amount = currency_format_old_structure(-transaction.from_amount, transaction.from_currency, number_of_digits)
            transaction.to_amount = currency_format_old_structure(transaction.to_amount, transaction.to_currency, number_of_digits)
            if transaction.commission:
                transaction.commission = currency_format_old_structure(-transaction.commission, transaction.from_currency, number_of_digits)

        transaction.date = str(transaction.date.strftime('%d-%b-%y'))
                
    buttons = ['transaction', 'fx_transaction', 'settings', 'import', 'edit', 'delete']

    return render(request, 'transactions.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'transactions': all_transactions,
        'brokers': Brokers.objects.filter(investor=user).all(),
        'currencies': currencies,
        'currency': currency_target,
        'table_date': effective_current_date,
        'number_of_digits': number_of_digits,
        'selectedBrokers': user.custom_brokers,
        'dashboardForm': dashboard_form,
        'buttons': buttons,
    })
