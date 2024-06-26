from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.db.models import Q


from common.models import FX, Assets, Brokers, Prices, Transactions
from common.forms import DashboardForm
from constants import CURRENCY_CHOICES

from .forms import BrokerForm, PriceForm, SecurityForm, TransactionForm
from utils import Irr, NAV_at_date, create_price_table, currency_format_dict_values, effective_current_date, currency_format, format_percentage, parse_broker_cash_flows, parse_excel_file_transactions

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

        dashboard_form = DashboardForm(request.POST, instance=user)

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

        for security in broker.securities.filter(investor__id=user.id).all():
            if security.position(effective_current_date, [broker.id]) != 0:
                broker.no_of_securities += 1

        broker.NAV = NAV_at_date(user.id, [broker.id], effective_current_date, currency_target, [])['Total NAV']

        try:
            broker.first_investment = Transactions.objects.\
                filter(investor=user,
                       broker=broker).\
                    order_by('date').first().date
        except:
            broker.first_investment = 'None'        

        broker.cash = broker.balance(effective_current_date)
    
        broker.irr = format_percentage(Irr(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=[broker.id]))

        # Calculating totals
        for key in totals:
            broker_totals[key] = broker_totals.get(key, 0) + getattr(broker, key)

        # Prepare outputs for the front-end
        broker.NAV = currency_format(broker.NAV, currency_target, number_of_digits)
        for currency, value in broker.cash.items():
            broker.cash[currency] = currency_format(value, currency, number_of_digits)
    
        # print(f"database. views.py. line 88. {broker.name}")
    
    broker_totals = currency_format_dict_values(broker_totals, currency_target, number_of_digits)
    broker_totals['IRR'] = format_percentage(Irr(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=[broker.id for broker in brokers]))

    buttons = ['broker', 'edit', 'delete']

    return render(request, 'brokers.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'brokers': brokers,
        'broker_totals': broker_totals,
        'currencies': currencies,
        'currency': currency_target,
        'buttons': buttons,
    })

@login_required
def database_securities(request):
    
    user = request.user
    
    currency_target = user.default_currency
    number_of_digits = user.digits

    sidebar_padding = 0
    sidebar_width = 0

    sidebar_width = request.GET.get("width")
    sidebar_padding = request.GET.get("padding")

    # Calculate securities' metrics
    securities = Assets.objects.filter(investor=user).all()
    
    for security in securities:
        try:
            security.first_investment = security.investment_date()
        except:
            security.first_investment = 'None'
        
        security.open_position = security.position(effective_current_date)
        if security.price_at_date(effective_current_date) is not None:
            security.current_value = currency_format(security.open_position * security.price_at_date(effective_current_date).price or 0, security.currency, number_of_digits)
            security.irr = format_percentage(Irr(user.id, effective_current_date, security.currency, asset_id=security.id))
        
        security.open_position = currency_format(security.open_position, '', 0)
        
        security.realised = currency_format(security.realized_gain_loss(effective_current_date)['all_time'], security.currency, number_of_digits)
        security.unrealised = currency_format(security.unrealized_gain_loss(effective_current_date), security.currency, number_of_digits)
        security.capital_distribution = currency_format(security.get_capital_distribution(effective_current_date), security.currency, number_of_digits)
        

    buttons = ['security', 'edit', 'delete']        

    return render(request, 'securities.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'securities': securities,
        'currency': currency_target,
        'buttons': buttons,
    })

@login_required
def database_prices(request):
    
    user = request.user

    sidebar_padding = 0
    sidebar_width = 0

    sidebar_width = request.GET.get("width")
    sidebar_padding = request.GET.get("padding")

    # Calculate price data
    fx_data = FX.objects.filter(investor=user).order_by('date').all()
    ETF = create_price_table('ETF', user)
    mutual_fund = create_price_table('Mutual fund', user)
    stock = create_price_table('Stock', user)
    bond = create_price_table('Bond', user)

    buttons = ['price', 'update_FX', 'edit', 'delete']

    return render(request, 'prices.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'fxData': fx_data,
        'ETF': ETF,
        'mutualFund': mutual_fund,
        'stock': stock,
        'bond': bond,
        'buttons': buttons,
    })

def add_transaction(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST, investor=request.user.id)
        import_flag = request.POST.get('importing', False)

        if form.is_valid():
            transaction = form.save(commit=False)  # Don't save to the database yet
            transaction.investor = request.user     # Set the investor field
            transaction.save()

            # When adding new transaction update FX rates from Yahoo
            FX.update_fx_rate(transaction.date, request.user)

            price_instance = Prices(
                date=transaction.date,
                security=transaction.security,
                price=transaction.price,
            )
            price_instance.save()
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # If it's an AJAX request, return a JSON response with success and redirect_url
                if import_flag:
                    return JsonResponse({'status': 'import_success'})
                else:
                    return JsonResponse({'success': True, 'redirect_url': reverse('transactions:transactions')})
            else:
                # If it's not an AJAX request, redirect to a URL
                return redirect('transactions:transactions')
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    else:
        form = TransactionForm(investor=request.user)
        form_html = render_to_string('snippets/add_database_item.html', {'form': form, 'type': 'Transaction', 'action_url': 'database:add_transaction'}, request)
    return JsonResponse({'form_html': form_html})

@login_required
def add_broker(request):
    if request.method == 'POST':
        form = BrokerForm(request.POST)
        if form.is_valid():
            broker = form.save(commit=False)  # Don't save to the database yet
            broker.investor = request.user     # Set the investor field
            broker.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # If it's an AJAX request, return a JSON response with success and redirect_url
                return JsonResponse({'success': True, 'redirect_url': reverse('database:brokers')})
            else:
                # If it's not an AJAX request, redirect to a URL
                return redirect('database:brokers')
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    else:
        form = BrokerForm()
        form_html = render_to_string('snippets/add_database_item.html', {'form': form, 'type': 'Broker', 'action_url': 'database:add_broker'}, request)
    return JsonResponse({'form_html': form_html})

def add_price(request):
    if request.method == 'POST':
        form = PriceForm(request.POST, investor=request.user)
        if form.is_valid():
            form.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # If it's an AJAX request, return a JSON response with success and redirect_url
                return JsonResponse({'success': True, 'redirect_url': reverse('database:prices')})
            else:
                # If it's not an AJAX request, redirect to a URL
                return redirect('database:prices')
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    else:
        form = PriceForm(investor=request.user)
        form_html = render_to_string('snippets/add_database_item.html', {'form': form, 'type': 'Price', 'action_url': 'database:add_price'}, request)
    return JsonResponse({'form_html': form_html})

def add_security(request):
    if request.method == 'POST':
        form = SecurityForm(request.POST, investor=request.user)  # Pass user to form
        import_flag = request.POST.get('importing', False)

        if form.is_valid():
            isin = form.cleaned_data['ISIN']
            broker = form.cleaned_data['broker']
            
            # Check if the security already exists
            try:
                security = Assets.objects.get(ISIN=isin)
                # new_security = False
            except Assets.DoesNotExist:
                security = form.save(commit=False)  # Create new security instance
                security.investor = request.user
                security.save()
                # new_security = True

            # Attach the security to the broker
            broker.securities.add(security)
            
            security = form.save(commit=False)  # Don't save to the database yet
            security.investor = request.user     # Set the investor field
            broker = form.cleaned_data['broker']
            security.save()

            broker.securities.add(security)

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # If it's an AJAX request, return a JSON response with success and redirect_url
                if import_flag:
                    return JsonResponse({'status': 'success'})
                else:
                    return JsonResponse({'success': True, 'redirect_url': reverse('database:securities')})
            else:
                # If it's not an AJAX request, redirect to a URL
                return redirect('database:securities')
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    else:
        form = SecurityForm(investor=request.user)
        form_html = render_to_string('snippets/add_database_item.html', {'form': form, 'type': 'Security', 'action_url': 'database:add_security'}, request)
    return JsonResponse({'form_html': form_html})

@login_required
def edit_item(request, model_class, form_class, item_id, type):
    item = get_object_or_404(model_class, id=item_id)
    if request.method == 'POST':
        form = form_class(request.POST, instance=item, investor=request.user)
        if form.is_valid():
            item = form.save(commit=False)
            if type in ['broker', 'security', 'transaction']:
                item.investor = request.user
            item.save()

            # Handle attaching security to broker
            if type == 'security':
                brokers = form.cleaned_data['custom_brokers']
                print(brokers)
                for broker_id in brokers:
                    broker = Brokers.objects.get(id=broker_id)
                    broker.securities.add(item)

            if type == 'transaction':
                redirect_url = reverse('transactions:transactions')
            elif type == 'security':
                redirect_url = reverse(f'database:securities')
            else:
                redirect_url = reverse(f'database:{type}s')
            return JsonResponse({'success': True, 'redirect_url': redirect_url})
        else:
            print(form.errors)
            return JsonResponse({'errors': form.errors}, status=400)
    else:
        form = form_class(instance=item, investor=request.user)
        form_html = render_to_string(
            'snippets/add_database_item.html',
            {
                'form': form,
                'type': model_class.__name__,
                'action_url': reverse(f'database:edit_{type}', args=[item_id])
            },
            request
        )
        return JsonResponse({'form_html': form_html})
    
@login_required
@require_http_methods(["DELETE"])
def delete_item(request, model_class, item_id):
    item = get_object_or_404(model_class, id=item_id)
    item.delete()
    return JsonResponse({'success': True})

@login_required
def import_transactions_form(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        brokers = list(Brokers.objects.filter(investor=request.user).values('id', 'name'))
        return JsonResponse({
            'brokers': brokers,
            'CURRENCY_CHOICES': CURRENCY_CHOICES,
        })
    else:
        # If it's not an AJAX request, redirect to a URL
        return redirect('transactions:transactions')

@login_required
def import_transactions(request):
    if request.method == 'POST':
        broker_id = request.POST.get('broker')
        currency = request.POST.get('currency')
        confirm_each = request.POST.get('confirm_each') == 'on'
        import_type = request.POST.get('cash_or_transaction')
        skip_existing = request.POST.get('skip_existing') == 'on'
        file = request.FILES['file']

        user = request.user

        if import_type == 'transaction':

            securities, transactions = parse_excel_file_transactions(file, currency, broker_id)
            
            for security in securities:
                if not Assets.objects.filter(investor=user, name=security['name'], ISIN=security['isin']).exists():
                    return JsonResponse({'status': 'missing_security', 'security': security})
                
        elif import_type == 'cash':
            transactions = parse_broker_cash_flows(file, currency, broker_id)
            print("views. database. 363", transactions)

        return JsonResponse({'status': 'success', 'transactions': transactions, 'confirm_each': confirm_each, 'skip_existing': skip_existing})

    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def process_import_transactions(request):
    if request.method == 'POST':

        # Convert fields to Decimal where applicable, handle invalid values
        def to_decimal(value):
            try:
                return Decimal(value)
            except (InvalidOperation, TypeError, ValueError):
                return None
        
        price = to_decimal(request.POST.get('price'))
        quantity = to_decimal(request.POST.get('quantity'))
        cash_flow = to_decimal(request.POST.get('dividend'))
        commission = to_decimal(request.POST.get('commission'))
            
        if quantity is not None:
            try:
                security = Assets.objects.get(name=request.POST.get('security_name'))
            except Assets.DoesNotExist:
                return JsonResponse({'status': 'error', 'errors': {'security_name': ['Security not found']}}, status=400)
        else:
            security = None

        # Filter out None values to avoid passing invalid data to the filter
        filter_kwargs = {
            'investor': request.user,
            'broker': request.POST.get('broker'),
            'security': security,
            'date': request.POST.get('date'),
            'type': request.POST.get('type'),
            'currency': request.POST.get('currency'),
        }

        if price is not None:
            filter_kwargs['price'] = price
        if quantity is not None:
            filter_kwargs['quantity'] = quantity
        if cash_flow is not None:
            filter_kwargs['cash_flow'] = cash_flow
        if commission is not None:
            filter_kwargs['commission'] = commission

        existing_transactions = Transactions.objects.filter(**filter_kwargs)
        # print("views. database. line 403", existing_transactions)

        # If there are any matching transactions, return 'check_required'
        if existing_transactions.exists():
            if request.POST.get('skip_existing'):
                return JsonResponse({'status': 'success'})
            else:
                return JsonResponse({'status': 'check_required'})

        # Prepare form data with security id
        form_data = request.POST.dict()
        if quantity is not None:
            form_data['security'] = security.id

        form = TransactionForm(form_data, investor=request.user.id)

        if form.is_valid():
            transaction = form.save(commit=False)  # Don't save to the database yet
            transaction.investor = request.user     # Set the investor field
            transaction.save()
            
            # When adding new transaction update FX rates from Yahoo
            # FX.update_fx_rate(transaction.date, request.user)

            if quantity is not None:
                price_instance = Prices(
                    date=transaction.date,
                    security=transaction.security,
                    price=transaction.price,
                )
                price_instance.save()

            return JsonResponse({'status': 'success'})
        else:
            print("Form errors. database. 398", form.errors)
            return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    return JsonResponse({'error': 'Invalid request method'}, status=400)

def update_FX(request):
    if request.method == 'POST':
        date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d')
        if date:
            FX.update_fx_rate(date, request.user)
            return JsonResponse({'success': True})
        return JsonResponse({'error': 'Date not provided'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)
    
def get_update_fx_dates(request):
    if request.method == 'GET':
        dates = Transactions.objects.filter(investor=request.user).values_list('date', flat=True).distinct()
        return JsonResponse({'success': True, 'dates': list(dates)})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)