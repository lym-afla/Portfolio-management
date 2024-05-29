from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from common.models import Brokers, Assets, FX
from common.forms import DashboardForm
from database.forms import BrokerForm, PriceForm, SecurityForm, TransactionForm
from utils import calculate_open_table_output, selected_brokers, effective_current_date


@login_required
def open_positions(request):

    user = request.user
    
    global selected_brokers
    global effective_current_date
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    use_default_currency = user.use_default_currency_where_relevant

    sidebar_padding = 0
    sidebar_width = 0
    brokers = Brokers.objects.filter(investor=request.user).all()

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

    # Portfolio at [date] - assets with non zero positions
    # func.date used for correct query when transaction is at [table_date] (removes time effectively)
    portfolio_open = Assets.objects.filter(
        investor=request.user,
        transactions__date__lte=effective_current_date,
        transactions__broker_id__in=selected_brokers
    ).prefetch_related(
        'transactions'
    ).annotate(
        total_quantity=Sum('transactions__quantity')
    ).exclude(total_quantity=0)

    # print(f"open_positions.views. line 61. Portfolio_open: {portfolio_open[0].position}")

    categories = ['investment_date', 'current_value', 'realized_gl', 'unrealized_gl', 'capital_distribution', 'commission']

    portfolio_open, portfolio_open_totals = calculate_open_table_output(user.id, portfolio_open,
                                                                   effective_current_date,
                                                                   categories,
                                                                   use_default_currency,
                                                                   currency_target,
                                                                   selected_brokers,
                                                                   number_of_digits
                                                                   )
    
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
    })
