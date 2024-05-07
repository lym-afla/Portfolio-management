from django.shortcuts import render

from common.models import FX, Assets, Brokers, Transactions
from common.forms import DashboardForm

from utils import Irr, create_price_table, effective_current_date, entry_price

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
        broker.NAV = 0

        for security in broker.securities.all():
            if security.position(effective_current_date, [broker.id]) != 0:
                broker.no_of_securities += 1
                
            security_current_price = security.current_price(effective_current_date)
            broker.NAV += security.position(effective_current_date, [broker.id]) * \
                security_current_price.price * \
                    FX.get_rate(security.currency, currency_target, security_current_price.date)['FX']

        for key, value in broker.balance(effective_current_date).items():
            broker.NAV += value * FX.get_rate(key, currency_target, effective_current_date)['FX']

        try:
            broker.first_investment = Transactions.objects.\
                filter(broker == broker).\
                    order_by('date').first().date
        except:
            broker.first_investment = 'None'        
        
        broker.cash = {}    
        for currency in currencies:
            cash_flow = sum((-(x.price or 0) * (x.quantity or 0) + (x.cash_flow or 0)) \
                for x in broker.transactions.all() if x.currency == currency)
            broker.cash[currency] = cash_flow
    
        broker.irr = Irr(effective_current_date, currency_target, asset_id=None, broker_id_list=[broker.id])

        # Calculating totals
        for key in totals:
            broker_totals[key] = broker_totals.get(key, 0) + getattr(broker, key)

        print(f"database. views.py. line 88. {broker.name}")
    
    # Calculate securities' metrics
    securities = Assets.objects.filter(investor=user).all()
    
    for security in securities:
        try:
            security.first_investment = security.investment_date()
        except:
            security.first_investment = 'None'
        
        security.open_position = security.position(effective_current_date)
        
        try:
            security.current_value = security.open_position * security.current_price(effective_current_date).price
        except:
            security.current_value = 0
            
        security.realised = 0
        security.capital_distribution = 0
        for transaction in security.transactions.all():
            security.capital_distribution += (transaction.cash_flow or 0)
            if transaction.quantity and transaction.quantity < 0:
                security.realised += (transaction.price -\
                    entry_price(security.id, transaction.date, transaction.currency)) * \
                        -transaction.quantity
        try:
            security.unrealised = security.current_value - \
                (entry_price(security, effective_current_date, security.currency)) * \
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