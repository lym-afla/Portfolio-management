from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse

from common.models import FX, Assets, Brokers, Transactions
from common.forms import DashboardForm

from .forms import BrokerForm, PriceForm, SecurityForm, TransactionForm
from utils import Irr, NAV_at_date, create_price_table, currency_format_dict_values, effective_current_date, currency_format, format_percentage

@login_required
def database_brokers(request):
    
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

    return render(request, 'brokers.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'brokers': brokers,
        'broker_totals': broker_totals,
        'currencies': currencies,
        'currency': currency_target,
        'transaction_form': TransactionForm(),
        'broker_form': BrokerForm(),
        'price_form': PriceForm(),
        'security_form': SecurityForm(),
    })

@login_required
def database_securities(request):
    
    user = request.user
    
    currency_target = user.default_currency
    number_of_digits = user.digits

    sidebar_padding = 0
    sidebar_width = 0

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

    # Calculate securities' metrics
    securities = Assets.objects.filter(investor=user).all()
    
    for security in securities:
        try:
            security.first_investment = security.investment_date()
        except:
            security.first_investment = 'None'
        
        security.open_position = security.position(effective_current_date)
        security.current_value = currency_format(security.open_position * security.price_at_date(effective_current_date).price or 0, security.currency, number_of_digits)

        security.open_position = currency_format(security.open_position, '', 0)
        
        security.realised = currency_format(security.realized_gain_loss(effective_current_date)['all_time'], security.currency, number_of_digits)
        security.unrealised = currency_format(security.unrealized_gain_loss(effective_current_date), security.currency, number_of_digits)
        security.capital_distribution = currency_format(security.get_capital_distribution(effective_current_date), security.currency, number_of_digits)
        security.irr = format_percentage(Irr(effective_current_date, security.currency, asset_id=security.id))
        

    return render(request, 'securities.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'securities': securities,
        'currency': currency_target,
        'transaction_form': TransactionForm(),
        'broker_form': BrokerForm(),
        'price_form': PriceForm(),
        'security_form': SecurityForm(),
    })

@login_required
def database_prices(request):
    
    user = request.user
    
    currency_target = user.default_currency
    number_of_digits = user.digits

    sidebar_padding = 0
    sidebar_width = 0

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

    # Calculate price data
    fx_data = FX.objects.filter(investor=user).all()
    ETF = create_price_table('ETF', user)
    mutual_fund = create_price_table('Mutual fund', user)
    stock = create_price_table('Stock', user)
    bond = create_price_table('Bond', user)

    return render(request, 'prices.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'fxData': fx_data,
        'ETF': ETF,
        'mutualFund': mutual_fund,
        'stock': stock,
        'bond': bond,
        'transaction_form': TransactionForm(),
        'broker_form': BrokerForm(),
        'price_form': PriceForm(),
        'security_form': SecurityForm(),
    })

def add_transaction(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            form.save()
            # Check if the request is an AJAX request
            if request.is_ajax():
                # If it's an AJAX request, return a JSON response with success and redirect_url
                return JsonResponse({'success': True, 'redirect_url': reverse('transactions:transactions')})
            else:
                # If it's not an AJAX request, redirect to a URL
                return redirect('transactions:transactions')
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    else:
        form = TransactionForm()
    return render(request, 'snippets/add_transaction.html', {'form': form}) 

def add_broker(request):
    if request.method == 'POST':
        form = BrokerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('database:brokers')
    else:
        form = BrokerForm()
    return render(request, 'snippets/add_broker.html', {'form': form})

def add_price(request):
    if request.method == 'POST':
        form = PriceForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('database:prices')
    else:
        form = PriceForm()
    return render(request, 'snippets/add_price.html', {'form': form})

def add_security(request):
    if request.method == 'POST':
        form = SecurityForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('database:securities')
    else:
        form = SecurityForm()
    return render(request, 'snippets/add_security.html', {'form': form})