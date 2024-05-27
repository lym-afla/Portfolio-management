from django.shortcuts import render

from common.models import FX, Assets, Brokers, Transactions
from common.forms import DashboardForm

from utils import Irr, NAV_at_date, create_price_table, currency_format_dict_values, effective_current_date, currency_format, format_percentage

def database(request):
    
    user = request.user
    
    currency_target = user.default_currency
    number_of_digits = user.digits

    sidebar_padding = 0
    sidebar_width = 0
    
    brokers = Brokers.objects.filter(investor=user).all()
    currencies = set()

    if request.method == "GET":
        sidebar_width = request.GET.get("width")
        sidebar_padding = request.GET.get("padding")

    if request.method == "POST":

        dashboard_form = DashboardForm(request.POST, instance=request.user)

        if dashboard_form.is_valid():
            # Process the form data
            currency_target = dashboard_form.cleaned_data['default_currency']
            number_of_digits = dashboard_form.cleaned_data['digits']
            
            # Save new parameters to user setting
            user.default_currency = currency_target
            user.digits = number_of_digits
            user.save()
        else:
            initial_data = {
                'default_currency': currency_target,
                'digits': number_of_digits
            }
        dashboard_form = DashboardForm(instance=request.user, initial=initial_data)

    totals = ['no_of_securities', 'NAV']
    broker_totals = {}        
    
    # Calculate broker metrics
    for broker in brokers:

        currencies.update(broker.get_currencies())
        broker.currencies = ', '.join(broker.get_currencies())

        broker.no_of_securities = 0
        # broker.NAV = 0

        for security in broker.securities.all():
            if security.position(effective_current_date, [broker.id]) != 0:
                broker.no_of_securities += 1
                
        #     security_current_price = security.current_price(effective_current_date)
        #     broker.NAV += security.position(effective_current_date, [broker.id]) * \
        #         security_current_price.price * \
        #             FX.get_rate(security.currency, currency_target, effective_current_date)['FX']

        # for key, value in broker.balance(effective_current_date).items():
        #     broker.NAV += value * FX.get_rate(key, currency_target, effective_current_date)['FX']

        broker.NAV = NAV_at_date([broker.id], effective_current_date, currency_target, [])['Total NAV']

        try:
            broker.first_investment = Transactions.objects.\
                filter(broker = broker).\
                    order_by('date').first().date
        except:
            broker.first_investment = 'None'        

        broker.cash = broker.balance(effective_current_date)
    
        broker.irr = format_percentage(Irr(effective_current_date, currency_target, asset_id=None, broker_id_list=[broker.id]))

        # Calculating totals
        for key in totals:
            broker_totals[key] = broker_totals.get(key, 0) + getattr(broker, key)

        # Prepare outputs for the front-end
        broker.NAV = currency_format(broker.NAV, currency_target, number_of_digits)
        for currency, value in broker.cash.items():
            broker.cash[currency] = currency_format(value, currency, number_of_digits)
    
        # print(f"database. views.py. line 88. {broker.name}")
    
    broker_totals = currency_format_dict_values(broker_totals, currency_target, number_of_digits)
    broker_totals['IRR'] = format_percentage(Irr(effective_current_date, currency_target, asset_id=None, broker_id_list=[broker.id for broker in brokers]))
    
    # Calculate securities' metrics
    securities = Assets.objects.filter(investor=user).all()
    
    for security in securities:
        try:
            security.first_investment = security.investment_date().strftime('%#d-%b-%y')
        except:
            security.first_investment = 'None'
        
        security.open_position = security.position(effective_current_date)
        
        security.current_value = currency_format(security.open_position * security.price_at_date(effective_current_date).price or 0, security.currency, number_of_digits)

        # try:
        #     security.current_value = security.open_position * security.current_price(effective_current_date).price
        # except:
        #     security.current_value = 0
            
        security.realised = 0
        security.get_capital_distribution = 0
        for transaction in security.transactions.all():
            security.get_capital_distribution += (transaction.cash_flow or 0)
            if transaction.quantity and transaction.quantity < 0:
                security.realised += (transaction.price -\
                    security.calculate_buy_in_price(transaction.date, transaction.currency)) * \
                        -transaction.quantity
        try:
            security.unrealised = security.current_value - \
                (security.calculate_buy_in_price(effective_current_date, security.currency)) * \
                    security.open_position
        except:
            security.unrealised = 0
            
        security.irr = Irr(effective_current_date, security.currency, asset_id=security.id)

    # Calculate price data
    fx_data = FX.objects.all()
    ETF = create_price_table('ETF')
    mutual_fund = create_price_table('Mutual fund')
    stock = create_price_table('Stock')
    bond = create_price_table('Bond')

    return render(request, 'database.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'brokers': brokers,
        'broker_totals': broker_totals,
        'currencies': currencies,
        'securities': securities,
        'currency': currency_target,
        'fxData': fx_data,
        'ETF': ETF,
        'mutualFund': mutual_fund,
        'stock': stock,
        'bond': bond
    })