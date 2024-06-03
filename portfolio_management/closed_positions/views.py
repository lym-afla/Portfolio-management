from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from common.models import Assets, Brokers
from common.forms import DashboardForm
from utils import calculate_closed_table_output, selected_brokers, effective_current_date

@login_required
def closed_positions(request):
    
    user = request.user

    global effective_current_date
    global selected_brokers
    
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

    assets = Assets.objects.filter(
        investor=user,
        transactions__date__lte=effective_current_date,
        transactions__broker_id__in=selected_brokers,
        transactions__quantity__isnull=False
    ).distinct()

    portfolio_closed = []

    for asset in assets:
        if len(asset.exit_dates(effective_current_date)) != 0:
            portfolio_closed.append(asset)

    categories = ['investment_date', 'exit_date', 'realized_gl', 'capital_distribution', 'commission']

    buttons = ['transaction', 'broker', 'price', 'security', 'settings']

    portfolio_closed, portfolio_closed_totals = calculate_closed_table_output(user.id, portfolio_closed,
                                                                   effective_current_date,
                                                                   categories,
                                                                   use_default_currency,
                                                                   currency_target,
                                                                   selected_brokers,
                                                                   number_of_digits
                                                                   )
    
    return render(request, 'closed-positions.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'portfolio_closed': portfolio_closed,
        'portfolio_closed_totals': portfolio_closed_totals,
        'brokers': brokers,
        'currency': currency_target,
        'table_date': effective_current_date,
        'number_of_digits': number_of_digits,
        'selectedBrokers': selected_brokers,
        'dashboardForm': dashboard_form,
        'buttons': buttons,
    })