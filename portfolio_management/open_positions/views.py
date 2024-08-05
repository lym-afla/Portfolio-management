from datetime import date, datetime
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import Abs
from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from common.models import Brokers, Assets, Transactions
from common.forms import DashboardForm
from constants import TOLERANCE
from utils import broker_group_to_ids, calculate_open_table_output, currency_format, get_last_exit_date_for_brokers

from django.views.decorators.http import require_POST

import json

@login_required
def open_positions(request):

    user = request.user

    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    use_default_currency = user.use_default_currency_where_relevant
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    sidebar_padding = 0
    sidebar_width = 0
    user_brokers = Brokers.objects.filter(investor=user).all()

    sidebar_width = request.GET.get("width")
    sidebar_padding = request.GET.get("padding")

    print("views. open positions. 30", effective_current_date, selected_brokers)

    initial_data = {
        'selected_brokers': selected_brokers,
        'default_currency': currency_target,
        'table_date': effective_current_date,
        'digits': number_of_digits
    }
    dashboard_form = DashboardForm(instance=user, initial=initial_data)

    first_year = Transactions.objects.filter(
        investor=user,
        broker__in=selected_brokers
    ).order_by('date').first()
    
    # Addressing empty broker
    if first_year:
        first_year = first_year.date.year

    last_exit_date = get_last_exit_date_for_brokers(selected_brokers, effective_current_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_current_date.year else effective_current_date.year - 1

    if first_year is not None:
        open_table_years = list(range(first_year, last_year + 1))
    else:
        open_table_years = []

    buttons = ['transaction', 'broker', 'price', 'security', 'settings']
    
    return render(request, 'open_positions.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'brokers': user_brokers,
        'currency': currency_target,
        'table_date': effective_current_date,
        'number_of_digits': number_of_digits,
        'selectedBrokers': user.custom_brokers,
        'dashboardForm': dashboard_form,
        'buttons': buttons,
        'open_table_years': open_table_years,
    })

@require_POST
def update_open_positions_table(request):
    data = json.loads(request.body)
    timespan = data.get('timespan')

    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    use_default_currency = user.use_default_currency_where_relevant
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    # Process the data based on the timespan
    if timespan == 'YTD':
        start_date = date(effective_current_date.year, 1, 1)
        end_date = effective_current_date
    elif timespan == 'All-time':
        start_date = None
        end_date = effective_current_date
    else:
        start_date = date(int(timespan), 1, 1)
        end_date = date(int(timespan), 12, 31)

    portfolio_open = Assets.objects.filter(
        investor=user,
        transactions__broker_id__in=selected_brokers
    )

    # if start_date is not None:
    #     portfolio_open = portfolio_open.filter(transactions__date__gte=start_date)

    portfolio_open = portfolio_open.filter(
        transactions__date__lte=end_date,
    ).prefetch_related(
        'transactions'
    ).annotate(
        abs_total_quantity=Abs(Sum('transactions__quantity'))
    ).exclude(
        abs_total_quantity__lt=TOLERANCE
    )

    categories = ['investment_date', 'current_value', 'realized_gl', 'unrealized_gl', 'capital_distribution', 'commission']
    # Filter your data based on year and broker_id
    portfolio_open, portfolio_open_totals = calculate_open_table_output(user.id, portfolio_open,
                                                                   end_date,
                                                                   categories,
                                                                   use_default_currency,
                                                                   currency_target,
                                                                   selected_brokers,
                                                                   number_of_digits,
                                                                   start_date
                                                                   )

    context = {
        'portfolio_open': portfolio_open,
        'portfolio_open_totals': portfolio_open_totals,
    }

    tbody_html = render_to_string('open_positions_tbody.html', context)
    tfoot_html = render_to_string('open_positions_tfoot.html', context)

    cash_balances = get_cash_balances(user, timespan, effective_current_date)

    return JsonResponse({
        'ok': True,
        'tbody': tbody_html,
        'tfoot': tfoot_html,
        'cash_balances': cash_balances
    })

def get_cash_balances(user, timespan, effective_current_date):

    selected_brokers = broker_group_to_ids(user.custom_brokers, user)
    
    # Process the data based on the timespan
    if timespan == 'YTD':
        balance_date = effective_current_date
    elif timespan == 'All-time':
        balance_date = effective_current_date
    else:
        balance_date = date(int(timespan), 12, 31)
    
     # Initialize a dictionary to store aggregated balances
    aggregated_balances = {}

    for broker_id in selected_brokers:
        try:
            broker = Brokers.objects.get(id=broker_id, investor=user)
            cash_balances = broker.balance(balance_date)
            
            # Aggregate the cash balances
            for currency, balance in cash_balances.items():
                if currency in aggregated_balances:
                    aggregated_balances[currency] += balance
                else:
                    aggregated_balances[currency] = balance
        
        except Brokers.DoesNotExist:
            continue  # Skip brokers that do not exist for the user

    number_of_digits = user.digits
    
    # Convert Decimal objects to strings for JSON serialization
    serializable_balances = {currency_format('', currency, 0): currency_format(balance, currency, number_of_digits) for currency, balance in aggregated_balances.items()}

    return serializable_balances
