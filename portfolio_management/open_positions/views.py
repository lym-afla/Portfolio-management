from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from common.models import Brokers, Assets, FX
from common.forms import DashboardForm
from utils import Irr, NAV_at_date, calculate_table_output, currency_format, format_percentage, selected_brokers, effective_current_date, currency_format_dict_values


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

    # totals = ['entry_value', 'current_value', 'realized_gl', 'unrealized_gl', 'capital_distribution', 'commission', 'total_return']
    # portfolio_open_totals = {}

    categories = ['investment_date', 'current_value', 'realized_gl', 'unrealized_gl', 'capital_distribution', 'commission']

    portfolio_open, portfolio_open_totals = calculate_table_output(portfolio_open,
                                                                   effective_current_date,
                                                                   categories,
                                                                   use_default_currency,
                                                                   currency_target,
                                                                   selected_brokers,
                                                                   number_of_digits
                                                                   )
    
    for asset in portfolio_open:
        print(asset)
        

    # Convert current value to the target currency
    # for asset in portfolio_open:

    #     currency_used = None if use_default_currency else currency_target

    #     # Calculate position metrics
    #     asset.current_position = asset.position(effective_current_date, selected_brokers)
    #     asset.investment_date = asset.dates_of_zero_positions(effective_current_date, selected_brokers)[0].strftime('%#d-%b-%y')
    #     asset.entry_price = asset.calculate_buy_in_price(effective_current_date, currency_used, selected_brokers)
    #     asset.entry_value = asset.entry_price * asset.current_position
    #     asset.current_price = asset.price_at_date(effective_current_date, currency_used).price
    #     asset.current_value = asset.current_price * asset.current_position
    #     asset.share_of_portfolio = asset.price_at_date(effective_current_date, currency_target).price * asset.current_position / portfolio_NAV
    #     asset.realized_gl = asset.realized_gain_loss(effective_current_date, currency_used, selected_brokers)
    #     asset.unrealized_gl = asset.unrealized_gain_loss(effective_current_date, currency_used, selected_brokers)
    #     asset.price_change_percentage = (asset.realized_gl + asset.unrealized_gl) / abs(asset.entry_value)
    #     asset.capital_distribution = asset.get_capital_distribution(effective_current_date, currency_used, selected_brokers)
    #     asset.capital_distribution_percentage = asset.capital_distribution / asset.entry_value
    #     asset.commission = asset.get_commission(effective_current_date, currency_used, selected_brokers)
    #     asset.commission_percentage = asset.commission / asset.entry_value
    #     asset.total_return_amount = asset.realized_gl + asset.unrealized_gl + asset.capital_distribution + asset.commission
    #     asset.total_return_percentage = asset.total_return_amount / abs(asset.entry_value)
        
    #     # Calculate IRR for security
    #     currency_used = asset.currency if use_default_currency else currency_target
    #     asset.irr = format_percentage(Irr(effective_current_date, currency_used, asset_id=asset.id, broker_id_list=selected_brokers))
        
    #     # Calculating totals
    #     for key in totals:
    #         if not use_default_currency:
    #             addition = getattr(asset, key)
    #         else:
    #             addition = open_position_totals(asset, key, effective_current_date, currency_target, selected_brokers)
    #         portfolio_open_totals[key] = portfolio_open_totals.get(key, 0) + addition
    #     portfolio_open_totals['price_change_percentage'] = (portfolio_open_totals['realized_gl'] + portfolio_open_totals['unrealized_gl']) / portfolio_open_totals['entry_value']
    #     portfolio_open_totals['capital_distribution_percentage'] = portfolio_open_totals['capital_distribution'] / portfolio_open_totals['entry_value']
    #     portfolio_open_totals['commission_percentage'] = portfolio_open_totals['commission'] / portfolio_open_totals['entry_value']
    #     portfolio_open_totals['total_return_percentage'] = portfolio_open_totals['total_return'] / abs(portfolio_open_totals['entry_value'])
        
    #     # Formatting for correct representation
    #     asset.current_position = currency_format(asset.current_position, '', 0)
    #     asset.entry_price = currency_format(asset.entry_price, currency_used, number_of_digits)
    #     asset.entry_value = currency_format(asset.entry_value, currency_used, number_of_digits)
    #     asset.current_price = currency_format(asset.current_price, currency_used, number_of_digits)
    #     asset.current_value = currency_format(asset.current_value, currency_used, number_of_digits)
    #     asset.share_of_portfolio = format_percentage(asset.share_of_portfolio)
    #     asset.realized_gl = currency_format(asset.realized_gl, currency_used, number_of_digits)
    #     asset.unrealized_gl = currency_format(asset.unrealized_gl, currency_used, number_of_digits)
    #     asset.price_change_percentage = format_percentage(asset.price_change_percentage)
    #     asset.capital_distribution = currency_format(asset.capital_distribution, currency_used, number_of_digits)
    #     asset.capital_distribution_percentage = format_percentage(asset.capital_distribution_percentage)
    #     asset.commission = currency_format(asset.commission, currency_used, number_of_digits)
    #     asset.commission_percentage = format_percentage(asset.commission_percentage)
    #     asset.total_return_amount = currency_format(asset.total_return_amount, currency_used, number_of_digits)
    #     asset.total_return_percentage = format_percentage(asset.total_return_percentage)

    # # Format totals
    # portfolio_open_totals = currency_format_dict_values(portfolio_open_totals, currency_target, number_of_digits)

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
