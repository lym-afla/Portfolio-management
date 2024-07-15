from datetime import date, datetime
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import Abs
from django.http import JsonResponse
from django.shortcuts import render
from common.models import Brokers, Assets, Transactions
from common.forms import DashboardForm
from constants import TOLERANCE
from utils import calculate_open_table_output, currency_format, get_last_exit_date_for_brokers

from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

import json

@login_required
def open_positions(request):

    user = request.user

    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    use_default_currency = user.use_default_currency_where_relevant
    selected_brokers = user.custom_brokers

    sidebar_padding = 0
    sidebar_width = 0
    user_brokers = Brokers.objects.filter(investor=user).all()

    sidebar_width = request.GET.get("width")
    sidebar_padding = request.GET.get("padding")

    print("views. open positions. 30", effective_current_date)

    initial_data = {
        'selected_brokers': selected_brokers,
        'default_currency': currency_target,
        'table_date': effective_current_date,
        'digits': number_of_digits
    }
    dashboard_form = DashboardForm(instance=user, initial=initial_data)

    # Portfolio at [date] - assets with non zero positions
    # portfolio_open = Assets.objects.filter(
    #     investor=user,
    #     transactions__date__lte=effective_current_date,
    #     transactions__broker_id__in=selected_brokers
    # ).prefetch_related(
    #     'transactions'
    # ).annotate(
    #     total_quantity=Sum('transactions__quantity')
    # ).exclude(total_quantity=0)

    # portfolio_open = Assets.objects.filter(
    #     investor=user,
    #     transactions__date__lte=effective_current_date,
    #     transactions__broker_id__in=selected_brokers
    # ).prefetch_related(
    #     'transactions'
    # ).annotate(
    #     abs_total_quantity=Abs(Sum('transactions__quantity'))
    # ).exclude(
    #     abs_total_quantity__lt=TOLERANCE
    # )

    # print(f"open_positions.views. line 48. Portfolio_open: {portfolio_open}")

    # categories = ['investment_date', 'current_value', 'realized_gl', 'unrealized_gl', 'capital_distribution', 'commission']

    # portfolio_open, portfolio_open_totals = calculate_open_table_output(user.id, portfolio_open,
    #                                                                effective_current_date,
    #                                                                categories,
    #                                                                use_default_currency,
    #                                                                currency_target,
    #                                                                selected_brokers,
    #                                                                number_of_digits
    #                                                                )

    first_year = Transactions.objects.filter(
        investor=user,
        broker__in=selected_brokers
    ).order_by('date').first().date.year
    last_exit_date = get_last_exit_date_for_brokers(selected_brokers, effective_current_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_current_date.year else effective_current_date.year - 1

    open_table_years = list(range(first_year, last_year + 1))

    buttons = ['transaction', 'broker', 'price', 'security', 'settings']
    
    return render(request, 'open-positions.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        # 'portfolio_open': portfolio_open,
        # 'portfolio_open_totals': portfolio_open_totals,
        'brokers': user_brokers,
        'currency': currency_target,
        'table_date': effective_current_date,
        'number_of_digits': number_of_digits,
        'selectedBrokers': selected_brokers,
        'dashboardForm': dashboard_form,
        'buttons': buttons,
        'open_table_years': open_table_years,
    })

@require_POST
def update_open_positions_table(request):
    data = json.loads(request.body)
    timespan = data.get('timespan')
    # broker_id = data.get('broker_id')

    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    use_default_currency = user.use_default_currency_where_relevant
    selected_brokers = user.custom_brokers

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

    if start_date is not None:
        portfolio_open = portfolio_open.filter(transactions__date__gte=start_date)

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
    # Convert the portfolio_open to a list of dictionaries for JSON serialization
    portfolio_open_data = []
    for asset in portfolio_open:
        asset_data = {
            'id': asset.id,
            'investment_date': asset.investment_date,
            'current_value': asset.current_value,
            'realized_gl': asset.realized_gl,
            'unrealized_gl': asset.unrealized_gl,
            'capital_distribution': asset.capital_distribution,
            'commission': asset.commission,
            'entry_value': asset.entry_value,
            'current_position': asset.current_position,
            'entry_price': asset.entry_price,
            'current_price': asset.current_price,
            'share_of_portfolio': asset.share_of_portfolio,
            'price_change_percentage': asset.price_change_percentage,
            'capital_distribution_percentage': asset.capital_distribution_percentage,
            'commission_percentage': asset.commission_percentage,
            'total_return_amount': asset.total_return_amount,
            'total_return_percentage': asset.total_return_percentage,
            'irr': asset.irr,
        }
        portfolio_open_data.append(asset_data)

    print("views. open positions. 187", portfolio_open_data, portfolio_open_totals)

    return JsonResponse({
        'ok': True,
        'data': portfolio_open_data,
        'totals': portfolio_open_totals
    })

@require_POST
def get_cash_balances(request):
    data = json.loads(request.body)
    timespan = data.get('timespan')
    
    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    selected_brokers = user.custom_brokers
    
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

    # Convert Decimal objects to strings for JSON serialization
    serializable_balances = {currency_format('', currency, 0): str(balance) for currency, balance in aggregated_balances.items()}

    return JsonResponse({
        'ok': True,
        'cash_balances': serializable_balances
    })