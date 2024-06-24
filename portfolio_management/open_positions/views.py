from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import Abs
from django.shortcuts import render
from common.models import Brokers, Assets
from common.forms import DashboardForm
from constants import TOLERANCE
from utils import calculate_open_table_output, effective_current_date


@login_required
def open_positions(request):

    user = request.user

    global effective_current_date
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    use_default_currency = user.use_default_currency_where_relevant
    selected_brokers = user.custom_brokers

    sidebar_padding = 0
    sidebar_width = 0
    brokers = Brokers.objects.filter(investor=user).all()

    sidebar_width = request.GET.get("width")
    sidebar_padding = request.GET.get("padding")

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

    portfolio_open = Assets.objects.filter(
        investor=user,
        transactions__date__lte=effective_current_date,
        transactions__broker_id__in=selected_brokers
    ).prefetch_related(
        'transactions'
    ).annotate(
        abs_total_quantity=Abs(Sum('transactions__quantity'))
    ).exclude(
        abs_total_quantity__lt=TOLERANCE
    )

    print(f"open_positions.views. line 48. Portfolio_open: {portfolio_open}")

    categories = ['investment_date', 'current_value', 'realized_gl', 'unrealized_gl', 'capital_distribution', 'commission']

    portfolio_open, portfolio_open_totals = calculate_open_table_output(user.id, portfolio_open,
                                                                   effective_current_date,
                                                                   categories,
                                                                   use_default_currency,
                                                                   currency_target,
                                                                   selected_brokers,
                                                                   number_of_digits
                                                                   )
    
    buttons = ['transaction', 'broker', 'price', 'security', 'settings']
    
    return render(request, 'open-positions.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'portfolio_open': portfolio_open,
        'portfolio_open_totals': portfolio_open_totals,
        'brokers': brokers,
        'currency': currency_target,
        'table_date': effective_current_date,
        'number_of_digits': number_of_digits,
        'selectedBrokers': selected_brokers,
        'dashboardForm': dashboard_form,
        'buttons': buttons,
    })
