from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Sum
from common.models import FX, Assets, Brokers, Transactions
from common.forms import DashboardForm
from utils import Irr, currency_format, currency_format_dict_values, format_percentage, selected_brokers, effective_current_date

@login_required
def closed_positions(request):
    
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

    # Get closed positions
    portfolio_closed = Assets.objects.filter(
        transactions__date__lte=effective_current_date,
        transactions__broker_id__in=selected_brokers
    ).annotate(
        total_quantity=Sum('transactions__quantity')
    ).filter(
        total_quantity=0
    )

    totals = ['unrealized_gl', 'capital_distribution']
    portfolio_closed_totals = {}

    # portfolio_closed = PA.query.join(PA_transactions).\
    #     filter(func.date(PA_transactions.date) <= table_date,
    #            PA_transactions.broker_id.in_(selected_brokers)).\
    #                group_by(PA_transactions.security_id).\
    #                    having(func.sum(PA_transactions.quantity) == 0).all()
    
    # Convert exit value to the target currency
    for item in portfolio_closed:

        # Identify whether the position was long or short
        last_transaction = Transactions.objects.filter(
            security=item,
            broker__in=selected_brokers,
            date__lte=effective_current_date
        ).order_by('-date').first()

        if last_transaction is None:
            continue

        is_long_position = last_transaction.quantity < 0

        transactions_sells = Transactions.objects.filter(
                security=item,
                broker__in=selected_brokers,
                date__lte=effective_current_date,
                quantity__lt=0
            ).order_by('-date')
        transactions_buys = Transactions.objects.filter(
            security=item,
            broker__in=selected_brokers,
            date__lte=effective_current_date,
            quantity__gt=0
        ).order_by('-date')

        # Get transactions when selling stakes
        if is_long_position:
            transactions_exit = transactions_sells
            transactions_entry = transactions_buys
        else:
            transactions_exit = transactions_buys
            transactions_entry = transactions_sells

        # transactions_exit = Transactions.objects.filter(
        #     security=item,
        #     broker__in=selected_brokers,
        #     date__lte=effective_current_date,
        #     quantity__lt=0 if is_long_position else quantity__gt=0
        # ).order_by('-date').all()

        # transactions_exit = db.session.query(PA_transactions.price,
        #                                  PA_transactions.currency,
        #                                  PA_transactions.quantity,
        #                                  PA_transactions.date).\
        #     filter(PA_transactions.security_id == item.id,
        #            PA_transactions.broker_id.in_(selected_brokers),
        #            func.date(PA_transactions.date) <= table_date,
        #            PA_transactions.quantity < 0).order_by(PA_transactions.date.desc()).all()
        
        item.exit_date = transactions_exit.first().date if transactions_exit.exists() else None
        
        # Calculate exit value in target currency
        item.exit_value = 0
        for transaction in transactions_exit:
            item.exit_value += round(transaction.price * \
                                     FX.get_rate(transaction.currency,
                                                 currency_target,
                                                 transaction.date)['FX'] * \
                                                    abs(transaction.quantity), 2)
            # item.exit_value += round(transaction.price * FX_rate(transaction.currency,
            #                                             currency_target,
            #                                             transaction.date)['FX'] * \
            #                                                 -transaction.quantity, 2)
        # Get transactions when buyting stakes
        # transactions_entry = Transactions.objects.filter(
        #     security=item,
        #     broker__in=selected_brokers,
        #     date__lte=effective_current_date,
        #     quantity__gt=0 if is_long_position else quantity__lt=0
        # )

        # transactions_entry = db.session.query(PA_transactions.price,
        #                                     PA_transactions.currency,
        #                                     PA_transactions.quantity,
        #                                     PA_transactions.date).\
        #         filter(PA_transactions.security_id == item.id,
        #             PA_transactions.broker_id.in_(selected_brokers),
        #             func.date(PA_transactions.date) <= table_date,
        #             PA_transactions.quantity > 0).all()
        
        # Calculate exit value in target currency
        item.entry_value = 0
        for transaction in transactions_entry:
            item.entry_value += round(transaction.price * \
                                      FX.get_rate(transaction.currency,
                                                  currency_target,
                                                  transaction.date)['FX'] * \
                                                    abs(transaction.quantity), 2)
        
        item.realized_gl = item.exit_value - item.entry_value
        
        # Calculate cumulative capital distribution
        item.capital_distribution = 0
        transactions = Transactions.objects.filter(
            security=item,
            broker__in=selected_brokers,
            date__lte=effective_current_date,
            type='Dividend'
        )
        # transactions = PA_transactions.query.\
        #     filter(PA_transactions.security_id == item.id,
        #            PA_transactions.broker_id.in_(selected_brokers),
        #            func.date(PA_transactions.date) <= table_date,
        #            PA_transactions.type == 'Dividend').all()
        
        for transaction in transactions:
            fx_rate = FX.get_rate(transaction.currency.upper(), currency_target, transaction.date)['FX']
            item.capital_distribution += round(transaction.cash_flow * fx_rate, 2)
    
        item.irr = format_percentage(Irr(effective_current_date, currency_target, item.id, selected_brokers))
    
        # Calculating totals
        for key in totals:
            portfolio_closed_totals[key] = portfolio_closed_totals.get(key, 0) + getattr(item, key)

        # Formatting for correct representation
        item.entry_value = currency_format(item.entry_value, currency_target, number_of_digits)
        item.investment_date = item.investment_date(selected_brokers)
        # item.exit_date = currency_format(item.exit_date, currency_target, number_of_digits)
        item.exit_value = currency_format(item.exit_value, currency_target, number_of_digits)
        item.realized_gl = currency_format(item.realized_gl, currency_target, number_of_digits)
        item.capital_distribution = currency_format(item.capital_distribution, currency_target, number_of_digits)

    # Format totals
    portfolio_closed_totals = currency_format_dict_values(portfolio_closed_totals, currency_target, number_of_digits)

    return render(request, 'closed_positions/closed-positions.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'portfolio_closed': portfolio_closed,
        'portfolio_closed_totals': portfolio_closed_totals,
        'brokers': brokers,
        'currency': currency_target,
        'table_date': effective_current_date,
        'number_of_digits': number_of_digits,
        'selectedBrokers': selected_brokers,
    })