from datetime import datetime, timedelta, date
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from decimal import Decimal, InvalidOperation
import json
import logging
from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from django.db import OperationalError
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.db.models import Q, F
from django.db.models.functions import Lower
from django.utils.formats import date_format
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
from core.securities_utils import get_securities_table_api, get_security_detail, get_security_transactions
from core.formatting_utils import format_table_data
from core.pagination_utils import paginate_table
from core.sorting_utils import sort_entries
from core.database_utils import save_or_update_annual_broker_performance
from core.date_utils import get_start_date

from .forms import BrokerForm, BrokerPerformanceForm, FXTransactionForm, PriceForm, PriceImportForm, SecurityForm, TransactionForm
from utils import Irr_old_structure, NAV_at_date_old_structure, broker_group_to_ids_old_approach, currency_format_dict_values, currency_format_old_structure, format_percentage_old_structure, get_last_exit_date_for_brokers_old_approach, parse_broker_cash_flows, parse_excel_file_transactions, save_or_update_annual_broker_performance_old
from core.portfolio_utils import broker_group_to_ids, get_last_exit_date_for_brokers

logger = logging.getLogger(__name__)

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

    
def get_broker_securities(request):
    broker_id = request.GET.get('broker_id')
    if broker_id:
        broker = get_object_or_404(Brokers, id=broker_id, investor=request.user)
        securities = broker.securities.values_list('id', flat=True)
        return JsonResponse({'securities': list(securities)})
    return JsonResponse({'securities': []})

from .serializers import BrokerPerformanceSerializer, FXRateSerializer, FXSerializer, PriceImportSerializer, BrokerSerializer, TransactionSerializer


from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework import status, viewsets

from django.core.paginator import Paginator

@api_view(['GET'])
def api_get_asset_types(request):
    asset_types = [{'value': value, 'text': text} for value, text in ASSET_TYPE_CHOICES]
    return Response(asset_types)

# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def api_get_brokers(request):
#     user = request.user
#     brokers = Brokers.objects.filter(investor=user).order_by('name').values('id', 'name')
#     return Response(list(brokers))

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

    securities = securities.order_by(Lower('name')).values('id', 'name', 'type')
    return Response(list(securities))

@api_view(['GET'])
def api_get_security_detail(request, security_id):
    return Response(get_security_detail(request, security_id))

@api_view(['GET'])
def api_get_security_price_history(request, security_id):
    try:
        security = Assets.objects.get(id=security_id)
        period = request.GET.get('period', '1Y')
        effective_current_date = request.session.get('effective_current_date', datetime.now().date().isoformat())
        
        start_date = get_start_date(effective_current_date, period)

        print(f"Start date for {security.name} is {start_date}")
        
        prices = Prices.objects.filter(
            security=security,
            date__lte=effective_current_date
        ).order_by('date')

        if start_date:
            prices = prices.filter(date__gte=start_date)
        
        price_history = [{'date': price.date.strftime('%Y-%m-%d'), 'price': float(price.price)} for price in prices]
        return JsonResponse(price_history, safe=False)
    except Assets.DoesNotExist:
        return JsonResponse({'error': 'Security not found'}, status=404)

@api_view(['GET'])
def api_get_security_position_history(request, security_id):
    try:
        security = Assets.objects.get(id=security_id)
        period = request.GET.get('period', '1Y')
        effective_current_date = request.session.get('effective_current_date', datetime.now().date().isoformat())
        
        start_date = get_start_date(effective_current_date, period)
        
        transactions = Transactions.objects.filter(
            security=security,
            investor=request.user,
            date__lte=effective_current_date
        ).order_by('date')

        if start_date:
            transactions = transactions.filter(date__gt=start_date)
            current_position = security.position(start_date)
            position_history = [{'date': start_date, 'position': current_position}]
        else:
            current_position = 0
            position_history = []    
        
        logger.info(f"Current position for {security.name} as of {start_date} is {current_position}")
        # print(f"Current position for {security.name} as of {start_date} is {current_position}")
        for transaction in transactions:
            if transaction.type == 'Buy':
                current_position += transaction.quantity
            elif transaction.type == 'Sell':
                current_position += transaction.quantity
            position_history.append({'date': transaction.date.strftime('%Y-%m-%d'), 'position': current_position})
        
        return JsonResponse(position_history, safe=False)
    except Assets.DoesNotExist:
        return JsonResponse({'error': 'Security not found'}, status=404)

@api_view(['GET'])
def api_get_security_transactions(request, security_id):
    try:
        effective_current_date = request.session.get('effective_current_date', datetime.now().date().isoformat())
        period = request.GET.get('period', '1Y')
        start_date = get_start_date(effective_current_date, period)

        transactions = Transactions.objects.filter(security__id=security_id, investor=request.user).order_by('date')

        if start_date:
            transactions = transactions.filter(date__gt=start_date)

        # Pagination
        page = int(request.GET.get('page', 1))
        items_per_page = int(request.GET.get('itemsPerPage', 10))

        paginated_transactions, pagination_data = paginate_table(transactions, page, items_per_page)
        logger.info(f"Paginated transactions for {security_id}: {paginated_transactions}")
        
        # Serialize the transactions
        serializer = TransactionSerializer(paginated_transactions, many=True, context={'digits': request.user.digits})
        serialized_transactions = serializer.data
        
        return Response({
            'transactions': serialized_transactions,
            'total_items': pagination_data['total_items'],
            'current_page': pagination_data['current_page'],
            'total_pages': pagination_data['total_pages'],
        })
    except Assets.DoesNotExist:
        return Response({'error': 'Security not found'}, status=404)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_get_prices_table(request):
    return Response(get_prices_table_api(request))

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def api_get_brokers_table(request):
#     return Response(get_brokers_table_api(request))

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_get_securities_table(request):
    return Response(get_securities_table_api(request))

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_security_form_structure(request):
    investor = request.user
    form = SecurityForm(investor=investor)
    structure = {
        'fields': []
    }

    for field_name, field in form.fields.items():
        field_data = {
            'name': field_name,
            'label': field.label,
            'type': field.widget.__class__.__name__.lower(),
            'required': field.required,
            'choices': None,
            'initial': field.initial,
            'help_text': field.help_text,
        }

        if hasattr(field, 'choices'):
            if field_name == 'custom_brokers':
                field_data['choices'] = [{'value': broker.id, 'text': broker.name} for broker in Brokers.objects.filter(investor=investor).order_by('name')]
            else:
                field_data['choices'] = [{'value': choice[0], 'text': choice[1]} for choice in field.choices]
        
        if field_name == 'type':
            field_data['choices'] = [{'value': choice[0], 'text': choice[0]} for choice in Assets._meta.get_field('type').choices if choice[0]]
        
        if field_name == 'data_source':
            field_data['choices'] = [{'value': '', 'text': 'None'}] + [{'value': choice[0], 'text': choice[1]} for choice in Assets.DATA_SOURCE_CHOICES]
        
        # Handle specific widget types
        if isinstance(field.widget, forms.CheckboxInput):
            field_data['type'] = 'checkbox'
        elif isinstance(field.widget, forms.Textarea):
            field_data['type'] = 'textarea'
        elif isinstance(field.widget, forms.URLInput):
            field_data['type'] = 'url'
        
        structure['fields'].append(field_data)
    
    return Response(structure)            

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_create_security(request):
    form = SecurityForm(request.data, investor=request.user)
    if form.is_valid():
        security = form.save(commit=False)
        security.investor = request.user
        security.save()
        
        # Handle custom_brokers (many-to-many relationship)
        custom_brokers = form.cleaned_data.get('custom_brokers')
        if custom_brokers:
            security.brokers.set(custom_brokers)
        
        return Response({
            'success': True,
            'message': 'Security created successfully',
            'id': security.id,
            'name': security.name
        }, status=status.HTTP_201_CREATED)
    return Response({
        'success': False,
        'errors': form.errors
    }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_security_details_for_editing(request, security_id):
    security = get_object_or_404(Assets, id=security_id, investor=request.user)
    return Response({
        'id': security.id,
        'name': security.name,
        'ISIN': security.ISIN,
        'type': security.type,
        'currency': security.currency,
        'exposure': security.exposure,
        'restricted': security.restricted,
        'custom_brokers': list(security.brokers.values_list('id', flat=True)),
        'data_source': security.data_source,
        'yahoo_symbol': security.yahoo_symbol,
        'update_link': security.update_link,
        'comment': security.comment,
    })

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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_add_price(request):
    form = PriceForm(request.data, investor=request.user)
    if form.is_valid():
        price = form.save()
        return Response({'success': True, 'message': 'Price added successfully', 'id': price.id}, status=status.HTTP_201_CREATED)
    return Response({'success': False, 'errors': form.errors}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_delete_price(request, price_id):
    try:
        price = Prices.objects.get(id=price_id)
    except Prices.DoesNotExist:
        return Response({'message': 'Price not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        price.delete()
        return Response({'message': 'Price deleted successfully'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_price_details(request, price_id):
    price = get_object_or_404(Prices, id=price_id, security__investor=request.user)
    return Response({
        'id': price.id,
        'date': price.date.isoformat(),
        'security': price.security.id,
        'price': str(price.price),  # Convert Decimal to string to preserve precision
    })

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def api_update_price(request, price_id):
    price = get_object_or_404(Prices, id=price_id, security__investor=request.user)
    form = PriceForm(request.data, instance=price, investor=request.user)
    if form.is_valid():
        updated_price = form.save()
        return Response({
            'id': updated_price.id,
            'date': updated_price.date.isoformat(),
            'security__name': updated_price.security.name,
            'security__type': updated_price.security.type,
            'security__currency': updated_price.security.currency,
            'price': str(updated_price.price),
        })
    else:
        print("Price update form errors:", form.errors)
        return Response({'errors': form.errors}, status=status.HTTP_400_BAD_REQUEST)

from channels.db import database_sync_to_async
import asyncio

class PriceImportView(APIView):
    def get(self, request):
        user = request.user
        securities = Assets.objects.filter(investor=user)
        brokers = Brokers.objects.filter(investor=user)
        
        serializer = PriceImportSerializer()
        frequency_choices = dict(serializer.fields['frequency'].choices)
        
        return Response({
            'securities': [{'id': s.id, 'name': s.name} for s in securities],
            'brokers': [{'id': b.id, 'name': b.name} for b in brokers],
            'frequency_choices': [{'value': k, 'text': v} for k, v in frequency_choices.items()],
        })

    # def post(self, request):
    #     serializer = PriceImportSerializer(data=request.data, context={'request': request})
    #     if serializer.is_valid():
    #         return StreamingHttpResponse(
    #             self.import_prices(serializer.validated_data),
    #             content_type='text/event-stream'
    #         )
    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # async def import_prices(self, data, user):
    #     securities = data.get('securities', [])
    #     broker = data.get('broker')
    #     start_date = data.get('start_date')
    #     end_date = data.get('end_date')
    #     frequency = data.get('frequency')
    #     single_date = data.get('single_date')
    #     effective_current_date = parse_date(data.get('effective_current_date'))

    #     if not effective_current_date:
    #         raise ValueError("Invalid or missing effective_current_date")

    #     if single_date:
    #         dates = [single_date]
    #         start_date = end_date = single_date
    #         frequency = 'single'
    #     else:
    #         dates = await database_sync_to_async(generate_dates)(start_date, end_date, frequency)

    #     if broker:
    #         all_securities = await database_sync_to_async(broker.securities.filter)(investor=user)
    #         securities = [
    #             security for security in all_securities
    #             if await database_sync_to_async(security.position)(effective_current_date) > 0
    #         ]

    #     total_securities = len(securities)
    #     total_dates = len(dates)
    #     total_operations = total_securities * total_dates
    #     current_operation = 0
    #     results = []

    #     for security in securities:
    #         try:
    #             security = await database_sync_to_async(Assets.objects.get)(id=security.id, investor=user)
                
    #             if security.data_source == 'FT' and security.update_link:
    #                 price_generator = import_security_prices_from_ft(security, dates)
    #             elif security.data_source == 'YAHOO' and security.yahoo_symbol:
    #                 price_generator = import_security_prices_from_yahoo(security, dates)
    #             else:
    #                 error_message = f"No valid data source or update information for {security.name}"
    #                 results.append({
    #                     "security_name": security.name,
    #                     "status": "skipped",
    #                     "message": error_message
    #                 })
                    
    #                 yield self.format_progress('error', current_operation, total_operations, security.name, message=error_message)
    #                 current_operation += len(dates)
    #                 continue

    #             security_result = {
    #                 "security_name": security.name,
    #                 "updated_dates": [],
    #                 "skipped_dates": [],
    #                 "errors": []
    #             }

    #             async for result in self.async_generator(price_generator):
    #                 current_operation += 1

    #                 if result["status"] == "updated":
    #                     security_result["updated_dates"].append(result["date"])
    #                 elif result["status"] == "skipped":
    #                     security_result["skipped_dates"].append(result["date"])
    #                 elif result["status"] == "error":
    #                     security_result["errors"].append(f"{result['date']}: {result['message']}")

    #                 yield self.format_progress('progress', current_operation, total_operations, security.name, date=result["date"], result=result["status"])

    #             results.append(security_result)

    #         except Assets.DoesNotExist:
    #             error_message = f"Security with ID {security.id} not found"
    #             results.append(error_message)
    #             yield self.format_progress('error', current_operation, total_operations, message=error_message)
    #             current_operation += len(dates)
    #         except Exception as e:
    #             error_message = f"Error updating prices for security {security.id}: {str(e)}"
    #             results.append(error_message)
    #             yield self.format_progress('error', current_operation, total_operations, message=error_message)
    #             current_operation += len(dates)

    #     yield self.format_progress('complete', current_operation, total_operations,
    #                                message='Price import process completed',
    #                                details=results,
    #                                start_date=start_date.strftime('%Y-%m-%d'),
    #                                end_date=end_date.strftime('%Y-%m-%d'),
    #                                frequency=frequency,
    #                                total_dates=len(dates))
        
    # @staticmethod
    # def format_progress(status, current, total, security_name=None, date=None, result=None, message=None, **kwargs):
    #     progress_data = {
    #         'status': status,
    #         'current': current,
    #         'total': total,
    #         'progress': (current / total) * 100,
    #     }
    #     if security_name:
    #         progress_data['security_name'] = security_name
    #     if date:
    #         progress_data['date'] = date
    #     if result:
    #         progress_data['result'] = result
    #     if message:
    #         progress_data['message'] = message
    #     progress_data.update(kwargs)
    #     return json.dumps(progress_data) + '\n'

    # @staticmethod
    # async def async_generator(sync_generator):
    #     for item in sync_generator:
    #         yield item
    #         await asyncio.sleep(0)  # Allow other coroutines to run
            
        
class BrokerViewSet(viewsets.ModelViewSet):
    serializer_class = BrokerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Brokers.objects.filter(investor=self.request.user).order_by('name')

    def perform_create(self, serializer):
        serializer.save(investor=self.request.user)

    @action(detail=False, methods=['POST'])
    def list_brokers(self, request, *args, **kwargs):
        return Response(get_brokers_table_api(request))
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        data = queryset.values('id', 'name')
        return Response(list(data))

    @action(detail=False, methods=['GET'])
    def form_structure(self, request):
        return Response({
            'fields': [
                {
                    'name': 'name',
                    'label': 'Name',
                    'type': 'textinput',
                    'required': True,
                },
                {
                    'name': 'country',
                    'label': 'Country',
                    'type': 'textinput',
                    'required': True,
                },
                {
                    'name': 'restricted',
                    'label': 'Restricted',
                    'type': 'checkbox',
                    'required': False,
                },
                {
                    'name': 'comment',
                    'label': 'Comment',
                    'type': 'textarea',
                    'required': False,
                },
            ]
        })
        
class UpdateBrokerPerformanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = BrokerPerformanceSerializer(investor=request.user)
        form_data = serializer.get_form_data()
        return Response(form_data)

    # def post(self, request):
    #     form = BrokerPerformanceForm(request.data, investor=request.user)
    #     if form.is_valid():
    #         effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    #         broker_or_group = form.cleaned_data['broker_or_group']
    #         currency = form.cleaned_data['currency']
    #         is_restricted_str = form.cleaned_data['is_restricted']
    #         skip_existing_years = form.cleaned_data['skip_existing_years']
    #         user = request.user

    #         if is_restricted_str == 'None':
    #             is_restricted_list = [None]  # This will be used to indicate both restricted and unrestricted
    #         elif is_restricted_str == 'True':
    #             is_restricted_list = [True]
    #         elif is_restricted_str == 'False':
    #             is_restricted_list = [False]
    #         elif is_restricted_str == 'All':
    #             is_restricted_list = [None, TrFue, False]
    #         else:
    #             return JsonResponse({'error': 'Invalid "is_restricted" value'}, status=400)
            
    #         def generate_progress():
    #             currencies = [currency] if currency != 'All' else [choice[0] for choice in CURRENCY_CHOICES]
    #             total_operations = len(currencies) * len(is_restricted_list) * _get_years_count(user, effective_current_date, broker_or_group)

    #             # Send initial progress event
    #             yield json.dumps({
    #                 'status': 'initializing',
    #                 'total': total_operations
    #             }) + '\n'

    #             current_operation = 0

    #             try:
    #                 for curr in currencies:
    #                     for is_restricted in is_restricted_list:
    #                         for progress_data in save_or_update_annual_broker_performance(user, effective_current_date, broker_or_group, curr, is_restricted, skip_existing_years):
    #                             logger.info(f"Progress data: {progress_data}")
    #                             if progress_data['status'] == 'progress':
    #                                 current_operation += 1
    #                                 progress = (current_operation / total_operations) * 100
    #                                 event = {
    #                                     'status': 'progress',
    #                                     'current': current_operation,
    #                                     # 'total': total_operations,
    #                                     'progress': progress,
    #                                     'year': progress_data['year'],
    #                                     'currency': curr,
    #                                     'is_restricted': str(is_restricted)
    #                                 }
    #                                 yield json.dumps(event) + '\n'
    #                             elif progress_data['status'] == 'error':
    #                                 yield json.dumps(progress_data) + '\n'
    #                             elif progress_data['status'] == 'complete':
    #                                 pass  # We'll yield the complete status at the end

    #                 yield f"data: {json.dumps({'status': 'complete'})}\n\n"

    #             except OperationalError as e:
    #                 yield json.dumps({'status': 'error', 'message': f"Database error: {str(e)}"}) + '\n'
    #             except Exception as e:
    #                 yield json.dumps({'status': 'error', 'message': str(e)}) + '\n'

    #         # response = StreamingHttpResponse(generate_progress(), content_type='text/event-stream')
    #         # response['Cache-Control'] = 'no-cache'
    #         # response['X-Accel-Buffering'] = 'no'  # Disable buffering for Nginx
    #         # return response
    #         return StreamingHttpResponse(generate_progress(), content_type='text/event-stream')
    #     else:
    #         return JsonResponse({'error': 'Invalid form data', 'errors': form.errors}, status=400)

class FXViewSet(viewsets.ModelViewSet):
    serializer_class = FXSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'  # Use 'id' instead of 'date' for lookups

    def get_queryset(self):
        return FX.objects.filter(investors=self.request.user).order_by('-date')

    def perform_create(self, serializer):
        instance = serializer.save()
        instance.investors.add(self.request.user)

    def get_object(self):
        fx_id = self.kwargs.get('id')
        try:
            return FX.objects.filter(investors=self.request.user).get(id=fx_id)
        except FX.DoesNotExist:
            raise NotFound(f"FX rate with id {fx_id} not found.")

    @action(detail=False, methods=['POST'])
    def get_rate(self, request):
        serializer = FXRateSerializer(data=request.data)
        if serializer.is_valid():
            source = serializer.validated_data['source']
            target = serializer.validated_data['target']
            date = serializer.validated_data['date']
            
            try:
                rate = FX.get_rate(source, target, date, self.request.user)
                return Response(rate)
            except ValueError as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['POST'])
    def list_fx(self, request):
        # Extract parameters from request data
        start_date = request.data.get('startDate')
        end_date = request.data.get('endDate')
        page = int(request.data.get('page', 1))
        items_per_page = int(request.data.get('itemsPerPage', 10))
        sort_by = request.data.get('sortBy')
        search = request.data.get('search', '')

        # Filter queryset
        queryset = self.get_queryset()
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        # Apply search
        if search:
            queryset = queryset.filter(
                Q(date__icontains=search) |
                Q(USDEUR__icontains=search) |
                Q(USDGBP__icontains=search) |
                Q(CHFGBP__icontains=search) |
                Q(RUBUSD__icontains=search) |
                Q(PLNUSD__icontains=search)
            )

        # Convert queryset to list of dictionaries
        fx_data = list(queryset.values('id', 'date', 'USDEUR', 'USDGBP', 'CHFGBP', 'RUBUSD', 'PLNUSD'))

        # Apply sorting
        fx_data = sort_entries(fx_data, sort_by)

        # Paginate results
        paginated_fx_data, pagination_info = paginate_table(fx_data, page, items_per_page)

        # Format the data
        formatted_fx_data = format_table_data(paginated_fx_data, currency_target=None, number_of_digits=4)  # Assuming USD as base currency and 4 decimal places

        response_data = {
            'results': formatted_fx_data,
            'count': pagination_info['total_items'],
            'current_page': pagination_info['current_page'],
            'total_pages': pagination_info['total_pages'],
            'currencies': ['USDEUR', 'USDGBP', 'CHFGBP', 'RUBUSD', 'PLNUSD']
        }

        return Response(response_data)

    @action(detail=False, methods=['GET'])
    def form_structure(self, request):
        return Response({
            'fields': [
                {
                    'name': 'date',
                    'label': 'Date',
                    'type': 'datepicker',
                    'required': True,
                },
                {
                    'name': 'USDEUR',
                    'label': 'USD/EUR',
                    'type': 'number',
                    'required': True,
                },
                {
                    'name': 'USDGBP',
                    'label': 'USD/GBP',
                    'type': 'number',
                    'required': True,
                },
                {
                    'name': 'CHFGBP',
                    'label': 'CHF/GBP',
                    'type': 'number',
                    'required': True,
                },
                {
                    'name': 'RUBUSD',
                    'label': 'RUB/USD',
                    'type': 'number',
                    'required': True,
                },
                {
                    'name': 'PLNUSD',
                    'label': 'PLN/USD',
                    'type': 'number',
                    'required': True,
                },
            ]
        })
    
    @action(detail=False, methods=['GET'])
    def import_stats(self, request):
        user = request.user
        transaction_dates = Transactions.objects.filter(investor=user).values('date').distinct()
        total_dates = transaction_dates.count()
        
        fx_instances = FX.objects.filter(investors=user, date__in=transaction_dates.values('date'))
        missing_instances = total_dates - fx_instances.count()
        
        incomplete_instances = fx_instances.filter(
            Q(USDEUR__isnull=True) | Q(USDGBP__isnull=True) | Q(CHFGBP__isnull=True) |
            Q(RUBUSD__isnull=True) | Q(PLNUSD__isnull=True)
        ).count()

        stats = {
            'total_dates': total_dates,
            'missing_instances': missing_instances,
            'incomplete_instances': incomplete_instances
        }
        logger.info(f"FX import stats for user {user.id}: {stats}")
        return Response(stats)
    
    # @action(detail=False, methods=['POST'])
    # def import_fx_rates(self, request):
    #     import_option = request.data.get('import_option')
    #     user = request.user
    #     import_id = f"fx_import_{user.id}"
    #     cache.set(import_id, "running", timeout=3600)  # Set a running flag with 1 hour timeout

    #     def generate_progress():
    #         transaction_dates = Transactions.objects.filter(investor=user).values_list('date', flat=True).distinct()
            
    #         # Pre-filter dates based on import_option
    #         dates_to_update = []
    #         for date in transaction_dates:
    #             fx_instance = FX.objects.filter(date=date).first()
    #             if import_option in ['missing', 'both'] and (not fx_instance or user not in fx_instance.investors.all()):
    #                 dates_to_update.append(date)
    #             elif import_option in ['incomplete', 'both'] and fx_instance and any(getattr(fx_instance, field) is None for field in ['USDEUR', 'USDGBP', 'CHFGBP', 'RUBUSD', 'PLNUSD']):
    #                 dates_to_update.append(date)

    #         total_dates = len(dates_to_update)
            
    #         missing_filled = 0
    #         incomplete_updated = 0
    #         existing_linked = 0

    #         yield f"data: {json.dumps({'status': 'checking', 'message': 'Checking database for existing FX rates'})}\n\n"

    #         for i, date in enumerate(dates_to_update):
    #             if cache.get(import_id) != "running":
    #                 yield f"data: {json.dumps({'status': 'cancelled'})}\n\n"
    #                 break

    #             fx_instance = FX.objects.filter(date=date).first()
    #             if not fx_instance:
    #                 yield f"data: {json.dumps({'status': 'updating', 'message': f'Updating FX rates for {date}'})}\n\n"
    #                 FX.update_fx_rate(date, user)
    #                 missing_filled += 1
    #                 action = "Added"
    #             elif user not in fx_instance.investors.all():
    #                 fx_instance.investors.add(user)
    #                 existing_linked += 1
    #                 action = "Linked existing"
    #             elif any(getattr(fx_instance, field) is None for field in ['USDEUR', 'USDGBP', 'CHFGBP', 'RUBUSD', 'PLNUSD']):
    #                 yield f"data: {json.dumps({'status': 'updating', 'message': f'Updating incomplete FX rates for {date}'})}\n\n"
    #                 FX.update_fx_rate(date, user)
    #                 incomplete_updated += 1
    #                 action = "Updated"
    #             else:
    #                 action = "Skipped"
                
    #             progress = (i + 1) / total_dates * 100
    #             formatted_date = date_format(date, "F j, Y")  # Format date as "Month Day, Year"
    #             message = f"{action} FX rates for {formatted_date}"
    #             yield f"data: {json.dumps({'progress': progress, 'current': i + 1, 'total': total_dates, 'message': message})}\n\n"

    #         if cache.get(import_id) == "running":
    #             stats = {
    #                 'totalImported': missing_filled + incomplete_updated + existing_linked,
    #                 'missingFilled': missing_filled,
    #                 'incompleteUpdated': incomplete_updated,
    #                 'existingLinked': existing_linked
    #             }
    #             yield f"data: {json.dumps({'status': 'completed', 'stats': stats})}\n\n"

    #         cache.delete(import_id)  # Clean up the cache entry

    #     return StreamingHttpResponse(generate_progress(), content_type='text/event-stream')
    
    @action(detail=False, methods=['POST'])
    def cancel_import(self, request):
        user = request.user
        import_id = f"fx_import_{user.id}"
        cache.delete(import_id)  # This will cause the import to stop
        return JsonResponse({"status": "Import cancelled"})


