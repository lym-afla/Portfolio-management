from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging
from django import forms
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.db.models.functions import Lower

from common.models import FX, Assets, Brokers, Prices, Transactions
from constants import ASSET_TYPE_CHOICES
from core.price_utils import get_prices_table_api
from core.brokers_utils import get_brokers_table_api
from core.securities_utils import get_securities_table_api, get_security_detail
from core.formatting_utils import format_table_data
from core.pagination_utils import paginate_table
from core.sorting_utils import sort_entries
from core.date_utils import get_start_date

from .forms import PriceForm, SecurityForm, TransactionForm
from utils import parse_broker_cash_flows, parse_excel_file_transactions

logger = logging.getLogger(__name__)

# @login_required
# def import_transactions(request):
#     if request.method == 'POST':
#         broker_id = request.POST.get('broker')
#         currency = request.POST.get('currency')
#         confirm_each = request.POST.get('confirm_each') == 'on'
#         import_type = request.POST.get('cash_or_transaction')
#         skip_existing = request.POST.get('skip_existing') == 'on'
#         file = request.FILES['file']

#         user = request.user

#         if import_type == 'transaction':

#             securities, transactions = parse_excel_file_transactions(file, currency, broker_id)
            
#             for security in securities:
#                 if not Assets.objects.filter(investors=user, name=security['name'], ISIN=security['isin']).exists():
#                     return JsonResponse({'status': 'missing_security', 'security': security})
                
#         elif import_type == 'cash':
#             transactions = parse_broker_cash_flows(file, currency, broker_id)

#         return JsonResponse({'status': 'success', 'transactions': transactions, 'confirm_each': confirm_each, 'skip_existing': skip_existing})

#     return JsonResponse({'error': 'Invalid request method'}, status=400)

# @login_required
# def process_import_transactions(request):
#     if request.method == 'POST':

#         # Convert fields to Decimal where applicable, handle invalid values
#         def to_decimal(value):
#             try:
#                 return Decimal(value)
#             except (InvalidOperation, TypeError, ValueError):
#                 return None
        
#         price = to_decimal(request.POST.get('price'))
#         quantity = to_decimal(request.POST.get('quantity'))
#         cash_flow = to_decimal(request.POST.get('dividend'))
#         commission = to_decimal(request.POST.get('commission'))
            
#         if quantity is not None or request.POST.get('type') == 'Dividend':
#             try:
#                 security = Assets.objects.get(name=request.POST.get('security_name'), investors=request.user)
#             except Assets.DoesNotExist:
#                 return JsonResponse({'status': 'error', 'errors': {'security_name': ['Security not found']}}, status=400)
#         else:
#             security = None

#         # Filter out None values to avoid passing invalid data to the filter
#         filter_kwargs = {
#             'investor': request.user,
#             'broker': request.POST.get('broker'),
#             'security': security,
#             'date': request.POST.get('date'),
#             'type': request.POST.get('type'),
#             'currency': request.POST.get('currency'),
#         }

#         if price is not None:
#             filter_kwargs['price'] = price
#         if quantity is not None:
#             filter_kwargs['quantity'] = quantity
#         if cash_flow is not None:
#             filter_kwargs['cash_flow'] = cash_flow
#         if commission is not None:
#             filter_kwargs['commission'] = commission

#         existing_transactions = Transactions.objects.filter(**filter_kwargs)
#         # print("views. database. line 445", existing_transactions)

#         # If there are any matching transactions, return 'check_required'
#         if existing_transactions.exists():
#             if request.POST.get('skip_existing'):
#                 return JsonResponse({'status': 'success'})
#             else:
#                 return JsonResponse({'status': 'check_required'})

#         # Prepare form data with security id
#         form_data = request.POST.dict()
#         if quantity is not None:
#             form_data['security'] = security.id

#         form = TransactionForm(form_data, investor=request.user.id)

#         if form.is_valid():
#             transaction = form.save(commit=False)  # Don't save to the database yet
#             transaction.investor = request.user     # Set the investor field
#             transaction.save()
            
#             # When adding new transaction update FX rates from Yahoo
#             # FX.update_fx_rate(transaction.date, request.user)

#             if quantity is not None:
#                 price_instance = Prices(
#                     date=transaction.date,
#                     security=transaction.security,
#                     price=transaction.price,
#                 )
#                 price_instance.save()

#             return JsonResponse({'status': 'success'})
#         else:
#             print("Form errors. database. 479", form.errors)
#             return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

#     return JsonResponse({'error': 'Invalid request method'}, status=400)

# def update_FX(request):
#     if request.method == 'POST':
#         date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d')
#         if date:
#             FX.update_fx_rate(date, request.user)
#             return JsonResponse({'success': True})
#         return JsonResponse({'error': 'Date not provided'}, status=400)
#     else:
#         return JsonResponse({'error': 'Invalid request method'}, status=400)
    
# def get_update_fx_dates(request):
#     if request.method == 'GET':
#         dates = Transactions.objects.filter(investor=request.user).values_list('date', flat=True).distinct()
#         return JsonResponse({'success': True, 'dates': list(dates)})
#     else:
#         return JsonResponse({'error': 'Invalid request method'}, status=400)

    
# def get_broker_securities(request):
#     broker_id = request.GET.get('broker_id')
#     if broker_id:
#         broker = get_object_or_404(Brokers, id=broker_id, investor=request.user)
#         securities = broker.securities.values_list('id', flat=True)
#         return JsonResponse({'securities': list(securities)})
#     return JsonResponse({'securities': []})

from .serializers import BrokerPerformanceSerializer, FXRateSerializer, FXSerializer, PriceImportSerializer, BrokerSerializer, TransactionSerializer


from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from rest_framework import status, viewsets

@api_view(['GET'])
def api_get_asset_types(request):
    asset_types = [{'value': value, 'text': text} for value, text in ASSET_TYPE_CHOICES]
    return Response(asset_types)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_securities(request):
    user = request.user
    asset_types = request.GET.get('asset_types', '').split(',')
    broker_id = request.GET.get('broker_id')

    securities = Assets.objects.filter(investors=user)

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
        security = Assets.objects.get(id=security_id, investors=request.user)
        period = request.GET.get('period', '1Y')
        effective_current_date = request.session.get('effective_current_date', datetime.now().date().isoformat())
        
        start_date = get_start_date(effective_current_date, period)
        
        transactions = Transactions.objects.filter(
            security=security,
            investor=request.user,
            date__lte=effective_current_date,
            quantity__isnull=False
        ).order_by('date')

        if start_date:
            transactions = transactions.filter(date__gt=start_date)
            current_position = security.position(start_date, request.user)
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
        # First save the security to get an ID
        security.save()
        
        # Now add the many-to-many relationships
        security.investors.add(request.user)
        
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
    security = get_object_or_404(Assets, id=security_id, investors=request.user)
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
        security = Assets.objects.get(id=security_id, investors=request.user)
    except Assets.DoesNotExist:
        return Response({'error': 'Security not found'}, status=status.HTTP_404_NOT_FOUND)

    # Handle broker updates separately
    custom_brokers = request.data.get('custom_brokers', [])
    
    # Remove custom_brokers from request.data to avoid direct attribute setting
    data_to_update = {k: v for k, v in request.data.items() if k != 'custom_brokers'}
    
    # Update regular fields
    for key, value in data_to_update.items():
        setattr(security, key, value)
    
    # Save the security first
    security.save()
    
    # Update brokers relationship
    if custom_brokers:
        security.brokers.set(custom_brokers)  # This replaces all existing brokers
    
    logger.debug(f"Security updated. {security} with brokers {custom_brokers}")
    
    return Response({
        'success': True,
        'message': 'Security updated successfully',
        'id': security.id,
        'name': security.name
    })

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_delete_security(request, security_id):
    try:
        security = Assets.objects.get(id=security_id, investors=request.user)
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

class PriceImportView(APIView):
    def get(self, request):
        user = request.user
        securities = Assets.objects.filter(investors=user)
        brokers = Brokers.objects.filter(investor=user)
        
        serializer = PriceImportSerializer()
        frequency_choices = dict(serializer.fields['frequency'].choices)
        
        return Response({
            'securities': [{'id': s.id, 'name': s.name} for s in securities],
            'brokers': [{'id': b.id, 'name': b.name} for b in brokers],
            'frequency_choices': [{'value': k, 'text': v} for k, v in frequency_choices.items()],
        })  
        
class BrokerViewSet(viewsets.ModelViewSet):
    serializer_class = BrokerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Brokers.objects.filter(investor=self.request.user).order_by('name')

    def perform_create(self, serializer):
        serializer.save(investor=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['POST'])
    def list_brokers(self, request, *args, **kwargs):
        return Response(get_brokers_table_api(request))

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


