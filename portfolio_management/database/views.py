from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.db.models import Q

from common.models import FX, Assets, Brokers, Prices, Transactions
from common.forms import DashboardForm
from constants import ASSET_TYPE_CHOICES, CURRENCY_CHOICES

from .forms import BrokerForm, BrokerPerformanceForm, FXTransactionForm, PriceForm, SecurityForm, TransactionForm
from utils import Irr, NAV_at_date, currency_format_dict_values, currency_format, format_percentage, parse_broker_cash_flows, parse_excel_file_transactions, save_or_update_annual_broker_performance

logger = logging.getLogger(__name__)

@login_required
def database_brokers(request):
    
    user = request.user
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()

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

    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
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

# @login_required
# def database_prices_old(request):
    
#     user = request.user

#     sidebar_padding = 0
#     sidebar_width = 0

#     sidebar_width = request.GET.get("width")
#     sidebar_padding = request.GET.get("padding")

#     # Calculate price data
#     fx_data = FX.objects.filter(investor=user).order_by('date').all()
#     ETF = create_price_table('ETF', user)
#     mutual_fund = create_price_table('Mutual fund', user)
#     stock = create_price_table('Stock', user)
#     bond = create_price_table('Bond', user)

#     buttons = ['price', 'update_FX', 'edit', 'delete']

#     return render(request, 'prices.html', {
#         'sidebar_width': sidebar_width,
#         'sidebar_padding': sidebar_padding,
#         'fxData': fx_data,
#         'ETF': ETF,
#         'mutualFund': mutual_fund,
#         'stock': stock,
#         'bond': bond,
#         'buttons': buttons,
#     })

@login_required
def database_prices(request):
    
    asset_types = dict(ASSET_TYPE_CHOICES)
    securities = Assets.objects.filter(investor=request.user)
    
    return render(request, 'prices.html', {
        'asset_types': asset_types,
        'securities': securities,
    })

@login_required
def get_price_data_for_table(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    asset_types = request.GET.getlist('asset_types[]')
    securities = request.GET.getlist('securities[]')
    
    query = Q(security__investor=request.user)
    if start_date:
        query &= Q(date__gte=start_date)
    if end_date:
        query &= Q(date__lte=end_date)
    if asset_types:
        query &= Q(security__type__in=asset_types)
    if securities:
        query &= Q(security__id__in=securities)
    
    price_data = Prices.objects.filter(query).select_related('security')
    
    data = []
    for pd in price_data:
        # fx_data = FX.get_rate(pd.security.currency, 'USD', pd.date)
        # usd_price = pd.price * Decimal(str(fx_data['FX']))
        data.append({
            'id': pd.id,
            'date': pd.date,
            'security': pd.security.name,
            'asset_type': pd.security.get_type_display(),
            'currency': pd.security.currency,
            'price': float(pd.price),
            # 'usd_price': float(usd_price),
            # 'fx_rate': float(fx_data['FX']),
        })
    
    return JsonResponse({'data': data})

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

            # Save price to the database if it is a transaction with price assigned
            if transaction.price is not None:
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
        form_html = render_to_string(
            'snippets/handle_database_item.html',
            {
                'form': form,
                'type': 'Transaction',
                'action_url': 'database:add_transaction',
                'modal_title': 'Add New Transaction',
                'modal_id': 'addTransactionModal'
            },
            request
        )
    return JsonResponse({'form_html': form_html})

def add_fx_transaction(request):
    if request.method == 'POST':
        form = FXTransactionForm(request.POST, investor=request.user)
        import_flag = request.POST.get('importing', False)

        if form.is_valid():
            fx_transaction = form.save(commit=False)
            fx_transaction.investor = request.user
            fx_transaction.save()

            # Save or update corresponding FX instance
            fx_date = fx_transaction.date
            from_currency = fx_transaction.from_currency
            to_currency = fx_transaction.to_currency
            exchange_rate = fx_transaction.exchange_rate

            fx_instance, created = FX.objects.get_or_create(
                date=fx_date,
                investor=request.user,
                defaults={}
            )

            # Determine the correct field to update
            currency_pair = f"{from_currency}{to_currency}"
            reverse_pair = f"{to_currency}{from_currency}"

            pairs_list = [field.name for field in FX._meta.get_fields() if (field.name != 'date' and field.name != 'id')]

            if currency_pair in pairs_list:
                current_rate = getattr(fx_instance, currency_pair)
                if current_rate is None:
                    setattr(fx_instance, currency_pair, exchange_rate)
                    fx_instance.save()
                else:
                    logger.info(f"Existing FX rate found for {currency_pair} on {fx_date}. Keeping existing rate.")
            elif reverse_pair in pairs_list:
                current_rate = getattr(fx_instance, reverse_pair)
                if current_rate is None:
                    setattr(fx_instance, reverse_pair, Decimal('1') / exchange_rate)
                    fx_instance.save()
                else:
                    logger.info(f"Existing FX rate found for {currency_pair} on {fx_date}. Keeping existing rate.")
            else:
                # If neither pair exists, log this or handle it differently
                print(f"Warning: No matching field for currency pair {currency_pair}")
        
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
            return JsonResponse(form.errors, status=400)
    else:
        form = FXTransactionForm(investor=request.user)
        form_html = render_to_string(
            'snippets/handle_database_item.html',
            {
                'form': form,
                'type': 'FXTransaction',
                'action_url': 'database:add_fx_transaction',
                'modal_title': 'Add New FX Transaction',
                'modal_id': 'addFXTransactionModal'
            },
            request
        )
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
        form_html = render_to_string(
            'snippets/handle_database_item.html',
            {
                'form': form,
                'type': 'Broker',
                'action_url': 'database:add_broker',
                'modal_title': 'Add New Broker',
                'modal_id': 'addBrokerModal'
            },
            request
        )
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
        form_html = render_to_string(
            'snippets/handle_database_item.html',
            {
                'form': form,
                'type': 'Price',
                'action_url': 'database:add_price',
                'modal_title': 'Add Price',
                'modal_id': 'addPriceModal'
            },
            request
        )
    return JsonResponse({'form_html': form_html})

def add_security(request):
    if request.method == 'POST':
        form = SecurityForm(request.POST, investor=request.user)  # Pass user to form
        import_flag = request.POST.get('importing', False)

        if form.is_valid():
            isin = form.cleaned_data['ISIN']
            brokers = form.cleaned_data['custom_brokers']
            
            # Check if the security already exists
            try:
                security = Assets.objects.get(ISIN=isin, investor=request.user)
                # new_security = False
            except Assets.DoesNotExist:
                security = form.save(commit=False)  # Create new security instance
                security.investor = request.user
                security.save()
                # new_security = True

            # Attach the security to the broker
            for broker_id in brokers:
                broker = Brokers.objects.get(id=broker_id, investor=request.user)
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
        form_html = render_to_string(
            'snippets/handle_database_item.html',
            {
                'form': form,
                'type': 'Security',
                'action_url': 'database:add_security',
                'modal_title': 'Add Security',
                'modal_id': 'addSecurityModal'
            },
            request
        )
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
            'snippets/handle_database_item.html',
            {
                'form': form,
                'type': model_class.__name__,
                'action_url': reverse(f'database:edit_{type}', args=[item_id]),
                'modal_title': f'Edit {type.capitalize()}',
                'modal_id': 'editPriceModal'
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
            
        if quantity is not None or request.POST.get('type') == 'Dividend':
            try:
                security = Assets.objects.get(name=request.POST.get('security_name'), investor=request.user)
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
        # print("views. database. line 445", existing_transactions)

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
            print("Form errors. database. 479", form.errors)
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

def update_broker_performance(request):
    if request.method == 'POST':
        form = BrokerPerformanceForm(request.POST, investor=request.user)
        if form.is_valid():
            effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
            broker_or_group = form.cleaned_data['broker_or_group']
            currency = form.cleaned_data['currency']
            is_restricted_str = form.cleaned_data['is_restricted']
            skip_existing_years = form.cleaned_data['skip_existing_years']  # Read the checkbox value
            user = request.user

            # Convert is_restricted string to appropriate value
            if is_restricted_str == 'None':
                is_restricted_list = [None]  # This will be used to indicate both restricted and unrestricted
            elif is_restricted_str == 'True':
                is_restricted_list = [True]
            elif is_restricted_str == 'False':
                is_restricted_list = [False]
            elif is_restricted_str == 'All':
                is_restricted_list = [None, True, False]
            else:
                return JsonResponse({'error': 'Invalid "is_restricted" value'}, status=400)
            
            try:
                with transaction.atomic():
                    # for broker_id in selected_brokers:
                    for is_restricted in is_restricted_list:
                        if currency == 'All':
                            currencies = [choice[0] for choice in CURRENCY_CHOICES]
                            for curr in currencies:
                                save_or_update_annual_broker_performance(user, effective_current_date, broker_or_group, curr, is_restricted, skip_existing_years)
                        else:
                            save_or_update_annual_broker_performance(user, effective_current_date, broker_or_group, currency, is_restricted, skip_existing_years)

                return JsonResponse({'success': True})

            except IntegrityError as e:
                return JsonResponse({'error': str(e)}, status=400)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)