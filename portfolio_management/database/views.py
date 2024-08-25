from datetime import datetime, timedelta, date
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from decimal import Decimal, InvalidOperation
import json
import logging
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.db.models import Q, F
import pandas as pd
import requests
from requests.exceptions import RequestException
from fake_useragent import UserAgent
from io import StringIO

import yfinance as yf

from common.models import FX, Assets, Brokers, Prices, Transactions
from common.forms import DashboardForm_old_setup
from constants import ASSET_TYPE_CHOICES, CURRENCY_CHOICES, MUTUAL_FUNDS_IN_PENCES
from core.price_utils import get_prices_table_api
from core.brokers_utils import get_brokers_table_api
from core.securities_utils import get_securities_table_api

from .forms import BrokerForm, BrokerPerformanceForm, FXTransactionForm, PriceForm, PriceImportForm, SecurityForm, TransactionForm
from utils import Irr_old_structure, NAV_at_date_old_structure, broker_group_to_ids_old_approach, currency_format_dict_values, currency_format_old_structure, format_percentage_old_structure, get_last_exit_date_for_brokers, parse_broker_cash_flows, parse_excel_file_transactions, save_or_update_annual_broker_performance

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

        dashboard_form = DashboardForm_old_setup(request.POST, instance=user)

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
        dashboard_form = DashboardForm_old_setup(instance=request.user, initial=initial_data)

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

        broker.NAV = NAV_at_date_old_structure(user.id, [broker.id], effective_current_date, currency_target, [])['Total NAV']

        try:
            broker.first_investment = Transactions.objects.\
                filter(investor=user,
                       broker=broker).\
                    order_by('date').first().date
        except:
            broker.first_investment = 'None'        

        broker.cash = broker.balance(effective_current_date)
    
        broker.irr = format_percentage_old_structure(Irr_old_structure(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=[broker.id]))

        # Calculating totals
        for key in totals:
            broker_totals[key] = broker_totals.get(key, 0) + getattr(broker, key)

        # Prepare outputs for the front-end
        broker.NAV = currency_format_old_structure(broker.NAV, currency_target, number_of_digits)
        for currency, value in broker.cash.items():
            broker.cash[currency] = currency_format_old_structure(value, currency, number_of_digits)
    
        # print(f"database. views.py. line 88. {broker.name}")
    
    broker_totals = currency_format_dict_values(broker_totals, currency_target, number_of_digits)
    broker_totals['IRR'] = format_percentage_old_structure(Irr_old_structure(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=[broker.id for broker in brokers]))

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
            security.current_value = currency_format_old_structure(security.open_position * security.price_at_date(effective_current_date).price or 0, security.currency, number_of_digits)
            security.irr = format_percentage_old_structure(Irr_old_structure(user.id, effective_current_date, security.currency, asset_id=security.id))
        
        security.open_position = currency_format_old_structure(security.open_position, '', 0)
        
        security.realised = currency_format_old_structure(security.realized_gain_loss(effective_current_date)['all_time'], security.currency, number_of_digits)
        security.unrealised = currency_format_old_structure(security.unrealized_gain_loss(effective_current_date), security.currency, number_of_digits)
        security.capital_distribution = currency_format_old_structure(security.get_capital_distribution(effective_current_date), security.currency, number_of_digits)
        

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

    asset_types = dict(ASSET_TYPE_CHOICES)
    securities = Assets.objects.filter(investor=user).order_by('name')
    brokers = Brokers.objects.filter(investor=user).order_by('name')
    import_form = PriceImportForm(user=user)
    
    return render(request, 'prices.html', {
        'asset_types': asset_types,
        'securities': securities,
        'brokers': brokers,
        'importForm': import_form,
    })

@login_required
def get_price_data_for_table(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    asset_types = request.GET.getlist('asset_types[]')
    securities = request.GET.getlist('securities[]')
    search_value = request.GET.get('search[value]')  # Get search value

    draw = int(request.GET.get('draw', 1))
    start = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 10))

    # Handle ordering
    order_column = int(request.GET.get('order[0][column]', 0))
    order_dir = request.GET.get('order[0][dir]', 'desc')
    columns = ['date', 'security__name', 'security__type', 'security__currency', 'price']
    order_by = F(columns[order_column]).desc(nulls_last=True) if order_dir == 'desc' else F(columns[order_column]).asc(nulls_last=True)
    
    query = Q(security__investor=request.user)
    if start_date:
        query &= Q(date__gte=start_date)
    if end_date:
        query &= Q(date__lte=end_date)
    if asset_types:
        query &= Q(security__type__in=asset_types)
    if securities:
        query &= Q(security__id__in=securities)
    
    # Apply search
    if search_value:
        query &= (Q(security__name__icontains=search_value) |
                  Q(security__type__icontains=search_value) |
                  Q(security__currency__icontains=search_value) |
                  Q(price__icontains=search_value) |
                  Q(date__icontains=search_value))
    
    total_records = Prices.objects.filter(query).count()
    price_data = Prices.objects.filter(query).select_related('security').order_by(order_by)[start:start+length]
    
    data = []
    for pd in price_data:
        data.append({
            'id': pd.id,
            'date': pd.date,
            'security': pd.security.name,
            'asset_type': pd.security.get_type_display(),
            'currency': pd.security.currency,
            'price': float(pd.price),
        })
    
    return JsonResponse({
        'draw': draw,
        'recordsTotal': total_records,
        'recordsFiltered': total_records,
        'data': data
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
                return JsonResponse({'status': 'exists', 'message': 'Security already exists.'})
            except Assets.DoesNotExist:
                security = form.save(commit=False)  # Create new security instance
                security.investor = request.user
                security.save()

            # Attach the security to the broker
            for broker_id in brokers:
                broker = Brokers.objects.get(id=broker_id, investor=request.user)
                broker.securities.add(security)

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # If it's an AJAX request, return a JSON response with success and redirect_url
                if import_flag:
                    return JsonResponse({'status': 'success', 'message': 'Security added successfully.'})
                else:
                    return JsonResponse({'status': 'success', 'message': 'Security added successfully.', 'redirect_url': reverse('database:securities')})
            else:
                # If it's not an AJAX request, redirect to a URL
                return redirect('database:securities')
        else:
            return JsonResponse({'status': 'error', 'message': 'Form is invalid.', 'errors': form.errors}, status=400)
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
            skip_existing_years = form.cleaned_data['skip_existing_years']
            user = request.user

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
            
            def generate_progress():
                currencies = [currency] if currency != 'All' else [choice[0] for choice in CURRENCY_CHOICES]
                total_operations = 0
                for curr in currencies:
                    for is_restricted in is_restricted_list:
                        total_operations += get_years_count(user, effective_current_date, broker_or_group, curr, is_restricted)

                current_operation = 0

                try:
                    for curr in currencies:
                        for is_restricted in is_restricted_list:
                            for progress_data in save_or_update_annual_broker_performance(user, effective_current_date, broker_or_group, curr, is_restricted, skip_existing_years):
                                progress_info = json.loads(progress_data)
                                if progress_info['status'] == 'progress':
                                    current_operation += 1
                                    progress = (current_operation / total_operations) * 100
                                    yield json.dumps({
                                        'status': 'progress',
                                        'current': current_operation,
                                        'total': total_operations,
                                        'progress': progress,
                                        'year': progress_info['year'],
                                        'currency': curr,
                                        'is_restricted': str(is_restricted)
                                    }) + '\n'
                                else:
                                    yield progress_data

                    yield json.dumps({'status': 'complete'}) + '\n'

                except Exception as e:
                    yield json.dumps({'status': 'error', 'message': str(e)}) + '\n'

            return StreamingHttpResponse(generate_progress(), content_type='text/event-stream')
        else:
            return JsonResponse({'error': 'Invalid form data', 'errors': form.errors}, status=400)

    return JsonResponse({'error': 'Invalid request method'}, status=400)

def get_years_count(user, effective_date, brokers_or_group, currency_target, is_restricted):
    selected_brokers_ids = broker_group_to_ids_old_approach(brokers_or_group, user)
    first_transaction = Transactions.objects.filter(broker_id__in=selected_brokers_ids, date__lte=effective_date).order_by('date').first()
    if not first_transaction:
        return 0
    start_year = first_transaction.date.year
    last_exit_date = get_last_exit_date_for_brokers(selected_brokers_ids, effective_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_date.year else effective_date.year - 1
    return last_year - start_year + 1
from datetime import datetime, timedelta, date
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from decimal import Decimal, InvalidOperation
import json
import logging
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.db.models import Q, F
import pandas as pd
import requests
from requests.exceptions import RequestException
from fake_useragent import UserAgent
from io import StringIO

import yfinance as yf

from common.models import FX, Assets, Brokers, Prices, Transactions
from common.forms import DashboardForm_old_setup
from constants import ASSET_TYPE_CHOICES, CURRENCY_CHOICES, MUTUAL_FUNDS_IN_PENCES

from .forms import BrokerForm, BrokerPerformanceForm, FXTransactionForm, PriceForm, PriceImportForm, SecurityForm, TransactionForm
from utils import Irr_old_structure, NAV_at_date_old_structure, broker_group_to_ids_old_approach, currency_format_dict_values, currency_format_old_structure, format_percentage_old_structure, get_last_exit_date_for_brokers, parse_broker_cash_flows, parse_excel_file_transactions, save_or_update_annual_broker_performance

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

        dashboard_form = DashboardForm_old_setup(request.POST, instance=user)

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
        dashboard_form = DashboardForm_old_setup(instance=request.user, initial=initial_data)

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

        broker.NAV = NAV_at_date_old_structure(user.id, [broker.id], effective_current_date, currency_target, [])['Total NAV']

        try:
            broker.first_investment = Transactions.objects.\
                filter(investor=user,
                       broker=broker).\
                    order_by('date').first().date
        except:
            broker.first_investment = 'None'        

        broker.cash = broker.balance(effective_current_date)
    
        broker.irr = format_percentage_old_structure(Irr_old_structure(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=[broker.id]))

        # Calculating totals
        for key in totals:
            broker_totals[key] = broker_totals.get(key, 0) + getattr(broker, key)

        # Prepare outputs for the front-end
        broker.NAV = currency_format_old_structure(broker.NAV, currency_target, number_of_digits)
        for currency, value in broker.cash.items():
            broker.cash[currency] = currency_format_old_structure(value, currency, number_of_digits)
    
        # print(f"database. views.py. line 88. {broker.name}")
    
    broker_totals = currency_format_dict_values(broker_totals, currency_target, number_of_digits)
    broker_totals['IRR'] = format_percentage_old_structure(Irr_old_structure(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=[broker.id for broker in brokers]))

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
            security.current_value = currency_format_old_structure(security.open_position * security.price_at_date(effective_current_date).price or 0, security.currency, number_of_digits)
            security.irr = format_percentage_old_structure(Irr_old_structure(user.id, effective_current_date, security.currency, asset_id=security.id))
        
        security.open_position = currency_format_old_structure(security.open_position, '', 0)
        
        security.realised = currency_format_old_structure(security.realized_gain_loss(effective_current_date)['all_time'], security.currency, number_of_digits)
        security.unrealised = currency_format_old_structure(security.unrealized_gain_loss(effective_current_date), security.currency, number_of_digits)
        security.capital_distribution = currency_format_old_structure(security.get_capital_distribution(effective_current_date), security.currency, number_of_digits)
        

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

    asset_types = dict(ASSET_TYPE_CHOICES)
    securities = Assets.objects.filter(investor=user).order_by('name')
    brokers = Brokers.objects.filter(investor=user).order_by('name')
    import_form = PriceImportForm(user=user)
    
    return render(request, 'prices.html', {
        'asset_types': asset_types,
        'securities': securities,
        'brokers': brokers,
        'importForm': import_form,
    })

@login_required
def get_price_data_for_table(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    asset_types = request.GET.getlist('asset_types[]')
    securities = request.GET.getlist('securities[]')
    search_value = request.GET.get('search[value]')  # Get search value

    draw = int(request.GET.get('draw', 1))
    start = int(request.GET.get('start', 0))
    length = int(request.GET.get('length', 10))

    # Handle ordering
    order_column = int(request.GET.get('order[0][column]', 0))
    order_dir = request.GET.get('order[0][dir]', 'desc')
    columns = ['date', 'security__name', 'security__type', 'security__currency', 'price']
    order_by = F(columns[order_column]).desc(nulls_last=True) if order_dir == 'desc' else F(columns[order_column]).asc(nulls_last=True)
    
    query = Q(security__investor=request.user)
    if start_date:
        query &= Q(date__gte=start_date)
    if end_date:
        query &= Q(date__lte=end_date)
    if asset_types:
        query &= Q(security__type__in=asset_types)
    if securities:
        query &= Q(security__id__in=securities)
    
    # Apply search
    if search_value:
        query &= (Q(security__name__icontains=search_value) |
                  Q(security__type__icontains=search_value) |
                  Q(security__currency__icontains=search_value) |
                  Q(price__icontains=search_value) |
                  Q(date__icontains=search_value))
    
    total_records = Prices.objects.filter(query).count()
    price_data = Prices.objects.filter(query).select_related('security').order_by(order_by)[start:start+length]
    
    data = []
    for pd in price_data:
        data.append({
            'id': pd.id,
            'date': pd.date,
            'security': pd.security.name,
            'asset_type': pd.security.get_type_display(),
            'currency': pd.security.currency,
            'price': float(pd.price),
        })
    
    return JsonResponse({
        'draw': draw,
        'recordsTotal': total_records,
        'recordsFiltered': total_records,
        'data': data
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
                return JsonResponse({'status': 'exists', 'message': 'Security already exists.'})
            except Assets.DoesNotExist:
                security = form.save(commit=False)  # Create new security instance
                security.investor = request.user
                security.save()

            # Attach the security to the broker
            for broker_id in brokers:
                broker = Brokers.objects.get(id=broker_id, investor=request.user)
                broker.securities.add(security)

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # If it's an AJAX request, return a JSON response with success and redirect_url
                if import_flag:
                    return JsonResponse({'status': 'success', 'message': 'Security added successfully.'})
                else:
                    return JsonResponse({'status': 'success', 'message': 'Security added successfully.', 'redirect_url': reverse('database:securities')})
            else:
                # If it's not an AJAX request, redirect to a URL
                return redirect('database:securities')
        else:
            return JsonResponse({'status': 'error', 'message': 'Form is invalid.', 'errors': form.errors}, status=400)
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
            skip_existing_years = form.cleaned_data['skip_existing_years']
            user = request.user

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
            
            def generate_progress():
                currencies = [currency] if currency != 'All' else [choice[0] for choice in CURRENCY_CHOICES]
                total_operations = 0
                for curr in currencies:
                    for is_restricted in is_restricted_list:
                        total_operations += get_years_count(user, effective_current_date, broker_or_group, curr, is_restricted)

                current_operation = 0

                try:
                    for curr in currencies:
                        for is_restricted in is_restricted_list:
                            for progress_data in save_or_update_annual_broker_performance(user, effective_current_date, broker_or_group, curr, is_restricted, skip_existing_years):
                                progress_info = json.loads(progress_data)
                                if progress_info['status'] == 'progress':
                                    current_operation += 1
                                    progress = (current_operation / total_operations) * 100
                                    yield json.dumps({
                                        'status': 'progress',
                                        'current': current_operation,
                                        'total': total_operations,
                                        'progress': progress,
                                        'year': progress_info['year'],
                                        'currency': curr,
                                        'is_restricted': str(is_restricted)
                                    }) + '\n'
                                else:
                                    yield progress_data

                    yield json.dumps({'status': 'complete'}) + '\n'

                except Exception as e:
                    yield json.dumps({'status': 'error', 'message': str(e)}) + '\n'

            return StreamingHttpResponse(generate_progress(), content_type='text/event-stream')
        else:
            return JsonResponse({'error': 'Invalid form data', 'errors': form.errors}, status=400)

    return JsonResponse({'error': 'Invalid request method'}, status=400)

def get_years_count(user, effective_date, brokers_or_group, currency_target, is_restricted):
    selected_brokers_ids = broker_group_to_ids_old_approach(brokers_or_group, user)
    first_transaction = Transactions.objects.filter(broker_id__in=selected_brokers_ids, date__lte=effective_date).order_by('date').first()
    if not first_transaction:
        return 0
    start_year = first_transaction.date.year
    last_exit_date = get_last_exit_date_for_brokers(selected_brokers_ids, effective_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_date.year else effective_date.year - 1
    return last_year - start_year + 1

def import_prices(request):
    if request.method == 'POST':
        form = PriceImportForm(request.POST, user=request.user)
        if form.is_valid():
            securities = form.cleaned_data.get('securities')
            broker = form.cleaned_data.get('broker')
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')
            frequency = form.cleaned_data.get('frequency')
            single_date = form.cleaned_data.get('single_date')

            if single_date:
                dates = [single_date]
                start_date = end_date = single_date
                frequency = 'single'
            else:
                dates = generate_dates(start_date, end_date, frequency)

            if broker:
                # Get all securities for the broker
                all_securities = broker.securities.filter(investor=request.user)

                # Convert single_date to effective_current_date
                effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
                
                # Filter securities based on non-zero position for the effective date
                securities = [
                    security for security in all_securities
                    if security.position(effective_current_date) > 0
                ]

            def generate_progress():
                results = []
                total_securities = len(securities)
                total_dates = len(dates)
                total_operations = total_securities * total_dates
                current_operation = 0

                for i, security in enumerate(securities, 1):
                    try:
                        security = Assets.objects.get(id=security.id, investor=request.user)
                        
                        if security.data_source == 'FT' and security.update_link:
                            price_generator = import_security_prices_from_ft(security, dates)
                        elif security.data_source == 'YAHOO' and security.yahoo_symbol:
                            price_generator = import_security_prices_from_yahoo(security, dates)
                        else:
                            error_message = f"No valid data source or update information for {security.name}"
                            results.append({
                                "security_name": security.name,
                                "status": "skipped",
                                "message": error_message
                            })
                            yield json.dumps({
                                'status': 'error',
                                'current': current_operation,
                                'total': total_operations,
                                'progress': (current_operation / total_operations) * 100,
                                'security_name': security.name,
                                'message': error_message
                            }) + '\n'
                            current_operation += len(dates)  # Skip all dates for this security
                            continue

                        security_result = {
                            "security_name": security.name,
                            "updated_dates": [],
                            "skipped_dates": [],
                            "errors": []
                        }

                        for result in price_generator:
                            current_operation += 1
                            progress = (current_operation / total_operations) * 100

                            if result["status"] == "updated":
                                security_result["updated_dates"].append(result["date"])
                            elif result["status"] == "skipped":
                                security_result["skipped_dates"].append(result["date"])
                            elif result["status"] == "error":
                                security_result["errors"].append(f"{result['date']}: {result['message']}")

                            yield json.dumps({
                                'status': 'progress',
                                'current': current_operation,
                                'total': total_operations,
                                'progress': progress,
                                'security_name': security.name,
                                'date': result["date"],
                                'result': result["status"]
                            }) + '\n'

                        results.append(security_result)

                    except ObjectDoesNotExist:
                        error_message = f"Security with ID {security.id} not found"
                        results.append(error_message)
                        yield json.dumps({
                            'status': 'error',
                            'current': current_operation,
                            'total': total_operations,
                            'progress': (current_operation / total_operations) * 100,
                            'message': error_message
                        }) + '\n'
                        current_operation += len(dates)  # Skip all dates for this security
                    except Exception as e:
                        error_message = f"Error updating prices for security {security.id}: {str(e)}"
                        results.append(error_message)
                        yield json.dumps({
                            'status': 'error',
                            'current': current_operation,
                            'total': total_operations,
                            'progress': (current_operation / total_operations) * 100,
                            'message': error_message
                        }) + '\n'
                        current_operation += len(dates)  # Skip all dates for this security

                # Send final response
                yield json.dumps({
                    'status': 'complete',
                    'message': 'Price import process completed',
                    'details': results,
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d'),
                    'frequency': frequency,
                    'total_dates': len(dates)
                }) + '\n'

            return StreamingHttpResponse(generate_progress(), content_type='text/event-stream')
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid form data', 'errors': form.errors})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

def generate_dates(start, end, frequency):
    dates = []
    if frequency == 'monthly':
        current = start.replace(day=1) + relativedelta(months=1) - timedelta(days=1)  # Last day of the start month
    elif frequency == 'quarterly':
        quarter_end_month = 3 * ((start.month - 1) // 3 + 1)
        current = date(start.year, quarter_end_month, 1) + relativedelta(months=1, days=-1)
    elif frequency == 'annually':
        current = start.replace(month=12, day=31)  # Last day of the current year
    
    while current <= end:
        dates.append(current)
        if frequency == 'monthly':
            current = (current + relativedelta(months=1)).replace(day=1) + relativedelta(months=1) - timedelta(days=1)
        elif frequency == 'quarterly':
            current = (current + relativedelta(months=3)).replace(day=1) + relativedelta(months=1) - timedelta(days=1)
        elif frequency == 'annually':
            current = (current + relativedelta(years=1)).replace(month=12, day=31)
    return dates

def import_security_prices_from_ft(security, dates):
    url = security.update_link
    user_agent = UserAgent().random
    headers = {'User-Agent': user_agent}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"Error fetching data for {security.name}: {str(e)}"
        }
        return

    soup = BeautifulSoup(response.content, "html.parser")

    elem = soup.find('section', {'class': 'mod-tearsheet-add-to-watchlist'})
    if elem and 'data-mod-config' in elem.attrs:
        data = json.loads(elem['data-mod-config'])
        xid = data['xid']

        for date in dates:
            result = {
                "security_name": security.name,
                "date": date.strftime('%Y-%m-%d'),
                "status": "skipped"
            }

            # Check if a price already exists for this date
            if Prices.objects.filter(security=security, date=date).exists():
                yield result
                continue

            end_date = date.strftime('%Y/%m/%d')
            start_date = (date - timedelta(days=7)).strftime('%Y/%m/%d')

            try:
                r = requests.get(
                    f'https://markets.ft.com/data/equities/ajax/get-historical-prices?startDate={start_date}&endDate={end_date}&symbol={xid}',
                    headers=headers,
                    timeout=10
                )
                r.raise_for_status()
                data = r.json()

                df = pd.read_html(StringIO('<table>' + data['html'] + '</table>'))[0]
                df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
                df['Date'] = pd.to_datetime(df['Date'].apply(lambda x: x.split(',')[-2][1:] + x.split(',')[-1]))

                # Convert 'date' to pandas Timestamp for comparison
                date_as_timestamp = pd.Timestamp(date)

                df = df[df['Date'] <= date_as_timestamp]

                if not df.empty:
                    latest_price = df.iloc[0]['Close']
                    if security.name in MUTUAL_FUNDS_IN_PENCES:
                        latest_price = latest_price / 100
                    Prices.objects.create(security=security, date=date, price=latest_price)
                    result["status"] = "updated"
                else:
                    result["status"] = "error"
                    result["message"] = f"No data found for {date.strftime('%Y-%m-%d')}"
            except Exception as e:
                result["status"] = "error"
                result["message"] = f"Error processing data for {security.name}: {str(e)}"

            yield result

    else:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"No data found for {security.name}"
        }

def import_security_prices_from_yahoo(security, dates):
    if not security.yahoo_symbol:
        yield {
            "security_name": security.name,
            "status": "error",
            "message": f"No Yahoo Finance symbol specified for {security.name}"
        }
        return

    ticker = yf.Ticker(security.yahoo_symbol)

    for date in dates:
        result = {
            "security_name": security.name,
            "date": date.strftime('%Y-%m-%d'),
            "status": "skipped"
        }

        # Check if a price already exists for this date
        if Prices.objects.filter(security=security, date=date).exists():
            yield result
            continue

        end_date = (date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        start_date = (date - pd.Timedelta(days=6)).strftime('%Y-%m-%d')

        try:
            # Set auto_adjust to False to get unadjusted close prices
            history = ticker.history(start=start_date, end=end_date, auto_adjust=False)

            if not history.empty:
                # Use 'Close' for unadjusted close price
                latest_price = history.iloc[-1]['Close']
                Prices.objects.create(security=security, date=date, price=latest_price)
                result["status"] = "updated"
            else:
                result["status"] = "error"
                result["message"] = f"No data found for {date.strftime('%Y-%m-%d')}"
        except RequestException as e:
            logger.error(f"Network error while fetching data for {security.name}: {str(e)}")
            result["status"] = "error"
            result["message"] = f"Network error: {str(e)}"
        except yf.YFinanceException as e:
            logger.error(f"YFinance error for {security.name}: {str(e)}")
            result["status"] = "error"
            result["message"] = f"YFinance error: {str(e)}"
        except pd.errors.EmptyDataError:
            logger.error(f"Empty data received for {security.name}")
            result["status"] = "error"
            result["message"] = "Empty data received from Yahoo Finance"
        except Exception as e:
            logger.exception(f"Unexpected error processing data for {security.name}")
            result["status"] = "error"
            result["message"] = f"Unexpected error: {str(e)}"

        yield result

    
def get_broker_securities(request):
    broker_id = request.GET.get('broker_id')
    if broker_id:
        broker = get_object_or_404(Brokers, id=broker_id, investor=request.user)
        securities = broker.securities.values_list('id', flat=True)
        return JsonResponse({'securities': list(securities)})
    return JsonResponse({'securities': []})

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['GET'])
def api_get_asset_types(request):
    asset_types = [{'value': value, 'text': text} for value, text in ASSET_TYPE_CHOICES]
    return Response(asset_types)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_brokers(request):
    user = request.user
    brokers = Brokers.objects.filter(investor=user).order_by('name').values('id', 'name')
    return Response(list(brokers))

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_securities(request):
    user = request.user
    asset_types = request.GET.get('asset_types', '').split(',')
    broker_id = request.GET.get('broker_id')

    securities = Assets.objects.filter(investor=user)

    if asset_types and asset_types != ['']:
        securities = securities.filter(type__in=asset_types)

    if broker_id:
        broker = get_object_or_404(Brokers, id=broker_id, investor=user)
        securities = securities.filter(brokers=broker)

    securities = securities.order_by('name').values('id', 'name', 'type')
    return Response(list(securities))

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_get_prices_table(request):
    return Response(get_prices_table_api(request))

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_get_brokers_table(request):
    return Response(get_brokers_table_api(request))

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_get_securities_table(request):
    return Response(get_securities_table_api(request))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_create_security(request):
    data = request.data
    data['investor'] = request.user.id
    security = Assets.objects.create(**data)
    return Response({'id': security.id, 'name': security.name}, status=status.HTTP_201_CREATED)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def api_update_security(request, security_id):
    try:
        security = Assets.objects.get(id=security_id, investor=request.user)
    except Assets.DoesNotExist:
        return Response({'error': 'Security not found'}, status=status.HTTP_404_NOT_FOUND)

    for key, value in request.data.items():
        setattr(security, key, value)
    security.save()
    return Response({'id': security.id, 'name': security.name})

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_delete_security(request, security_id):
    try:
        security = Assets.objects.get(id=security_id, investor=request.user)
    except Assets.DoesNotExist:
        return Response({'error': 'Security not found'}, status=status.HTTP_404_NOT_FOUND)

    security.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)