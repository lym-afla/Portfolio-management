from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from common.models import Brokers, Assets, FX
from common.forms import DashboardForm
from utils import Irr, currency_format, calculate_buy_in_price, format_percentage, selected_brokers, effective_current_date, currency_format_dict_values


@login_required
def open_positions(request):

    user = request.user
    
    global selected_brokers
    global effective_current_date
    
    currency_target = user.default_currency
    number_of_digits = user.digits

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

    totals = ['entry_value', 'current_value', 'unrealized_gl', 'capital_distribution']
    portfolio_open_totals = {}

    # Convert current value to the target currency
    for item in portfolio_open:

        item.position_at_date = item.position(effective_current_date, selected_brokers)
        item.investment_date = item.investment_date().strftime('%#d-%b-%y')

        # Calculate unrealized gain/loss
        item.entry_price = calculate_buy_in_price(item.id, effective_current_date, currency_target, selected_brokers)
        # print(f"view.open_positions. line 70. Entry price: {item.entry_price}")
        item.entry_value = item.entry_price * item.position_at_date
        current_quote = item.price_at_date(effective_current_date)
        item.current_value = round(current_quote.price * \
            FX.get_rate(item.currency.upper(), currency_target, current_quote.date)['FX'] * \
                item.position_at_date, 2)
        item.unrealized_gl = item.current_value - item.entry_value

        # print(f"view.open_positions. line 78. Item: {item.transactions.all()}")

        # Calculate cumulative capital distribution
        item.capital_distribution = 0
        for transaction in item.transactions.all():
            fx_rate = FX.get_rate(transaction.currency.upper(), currency_target, transaction.date)['FX']
            if (transaction.type == 'Dividend'):
                item.capital_distribution += round(transaction.cash_flow * fx_rate, 2)
        
        # Calculate IRR for security
        item.irr = format_percentage(Irr(effective_current_date, currency_target, asset_id=item.id, broker_id_list=selected_brokers))
        
        # Calculating totals
        for key in totals:
            portfolio_open_totals[key] = portfolio_open_totals.get(key, 0) + getattr(item, key)
        
        # Formatting for correct representation
        item.entry_price = currency_format(item.entry_price, currency_target, number_of_digits)
        item.entry_value = currency_format(item.entry_value, currency_target, number_of_digits)
        item.price_at_date = currency_format(current_quote.price, currency_target, number_of_digits)
        item.current_value = currency_format(item.current_value, currency_target, number_of_digits)
        item.unrealized_gl = currency_format(item.unrealized_gl, currency_target, number_of_digits)
        item.capital_distribution = currency_format(item.capital_distribution, currency_target, number_of_digits)

    # Format totals
    portfolio_open_totals = currency_format_dict_values(portfolio_open_totals, currency_target, number_of_digits)

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