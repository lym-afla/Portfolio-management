from datetime import datetime
from decimal import Decimal
from itertools import chain
from operator import attrgetter
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from common.models import Brokers, FXTransaction, Transactions
from common.forms import DashboardForm_old_setup
from constants import CURRENCY_CHOICES
from .serializers import TransactionFormSerializer, FXTransactionFormSerializer
from utils import broker_group_to_ids_old_approach, currency_format_old_structure
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound
from rest_framework import status, viewsets
from core.transactions_utils import get_transactions_table_api

@login_required
def transactions(request):

    user = request.user

    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()

    currency_target = user.default_currency
    number_of_digits = user.digits
    selected_brokers = broker_group_to_ids_old_approach(user.custom_brokers, user)

    sidebar_padding = 0
    sidebar_width = 0
    brokers = Brokers.objects.filter(investor=user, id__in=selected_brokers).all()

    sidebar_width = request.GET.get("width")
    sidebar_padding = request.GET.get("padding")

    initial_data = {
        'selected_brokers': selected_brokers,
        'default_currency': currency_target,
        'table_date': effective_current_date,
        'digits': number_of_digits
    }
    dashboard_form = DashboardForm_old_setup(instance=user, initial=initial_data)

    currencies = set()
    for broker in brokers:
        currencies.update(broker.get_currencies())
        
    # Fetch regular transactions
    transactions = Transactions.objects.filter(
        investor=user,
        date__lte=effective_current_date,
        broker_id__in=selected_brokers
    ).select_related('broker', 'security').order_by('date').all()

    # Fetch FX transactions
    fx_transactions = FXTransaction.objects.filter(
        investor=user,
        date__lte=effective_current_date,
        broker_id__in=selected_brokers
    ).select_related('broker').order_by('date').all()

    # Merge and sort all transactions
    all_transactions = sorted(
        chain(transactions, fx_transactions),
        key=attrgetter('date')
    )

    balance = {currency: Decimal(0) for currency in currencies}

    for transaction in all_transactions:
        transaction.balances = {}

        if isinstance(transaction, Transactions):
            # for currency in currencies:
            #     if transaction.currency == currency:
            balance[transaction.currency] = balance.get(transaction.currency, Decimal(0)) - Decimal((transaction.price or 0) * Decimal(transaction.quantity or 0) \
                - Decimal(transaction.cash_flow or 0) \
                - Decimal(transaction.commission or 0))
                # else:
                #     balance[currency] = balance.get(currency, Decimal(0))
            for currency in currencies:
                transaction.balances[currency] = currency_format_old_structure(balance[currency], currency, number_of_digits)

            # Prepare data for passing to the front-end
            if transaction.quantity:
                transaction.value = currency_format_old_structure(-round(Decimal(transaction.quantity * transaction.price), 2) + (transaction.commission or 0), transaction.currency, number_of_digits)
                transaction.price = currency_format_old_structure(transaction.price, transaction.currency, number_of_digits)
                transaction.quantity = abs(round(transaction.quantity, 0))
            if transaction.cash_flow:
                transaction.cash_flow = currency_format_old_structure(transaction.cash_flow, transaction.currency, number_of_digits)
            if transaction.commission:
                transaction.commission = currency_format_old_structure(-transaction.commission, transaction.currency, number_of_digits)
           
        elif isinstance(transaction, FXTransaction):
            # FX transaction

            transaction.type = 'FX'

            balance[transaction.from_currency] -= transaction.from_amount
            balance[transaction.to_currency] += transaction.to_amount
            if transaction.commission:
                balance[transaction.from_currency] -= transaction.commission

            for currency in currencies:
                transaction.balances[currency] = currency_format_old_structure(balance[currency], currency, number_of_digits)

            # Prepare FX transaction data for front-end
            transaction.from_amount = currency_format_old_structure(-transaction.from_amount, transaction.from_currency, number_of_digits)
            transaction.to_amount = currency_format_old_structure(transaction.to_amount, transaction.to_currency, number_of_digits)
            if transaction.commission:
                transaction.commission = currency_format_old_structure(-transaction.commission, transaction.from_currency, number_of_digits)

        transaction.date = str(transaction.date.strftime('%d-%b-%y'))
                
    buttons = ['transaction', 'fx_transaction', 'settings', 'import', 'edit', 'delete']
    print("views. 113", [transaction.exchange_rate for transaction in all_transactions if transaction.type == 'FX'])

    return render(request, 'transactions.html', {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'transactions': all_transactions,
        'brokers': Brokers.objects.filter(investor=user).all(),
        'currencies': currencies,
        'currency': currency_target,
        'table_date': effective_current_date,
        'number_of_digits': number_of_digits,
        'selectedBrokers': user.custom_brokers,
        'dashboardForm': dashboard_form,
        'buttons': buttons,
    })

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def compile_transactions_table_api(request):
#     return Response(get_transactions_table_api(request))

class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionFormSerializer
    queryset = Transactions.objects.all()

    def get_queryset(self):
        return self.queryset.filter(investor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(investor=self.request.user)

    def get_object(self):
        transaction_id = self.kwargs.get('pk')
        try:
            return Transactions.objects.get(id=transaction_id, investor=self.request.user)
        except Transactions.DoesNotExist:
            raise NotFound(f"Transaction with id {transaction_id} not found.")

    @action(detail=False, methods=['POST'])    
    def get_transactions_table(self, request):
        return Response(get_transactions_table_api(request))

    @action(detail=False, methods=['GET'])
    def form_structure(self, request):
        form_serializer = TransactionFormSerializer()
        return Response({
            'fields': [
                {
                    'name': 'id',
                    'label': 'ID',
                    'type': 'hidden',
                    'required': False,
                },
                {
                    'name': 'date',
                    'label': 'Date',
                    'type': 'datepicker',
                    'required': True,
                },
                {
                    'name': 'broker',
                    'label': 'Broker',
                    'type': 'select',
                    'required': True,
                    'choices': form_serializer.get_broker_choices(request.user)
                },
                {
                    'name': 'security',
                    'label': 'Select Security',
                    'type': 'select',
                    'required': False,
                    'choices': form_serializer.get_security_choices(request.user)
                },
                {
                    'name': 'currency',
                    'label': 'Currency',
                    'type': 'select',
                    'required': True,
                    'choices': [{'value': currency[0], 'text': f"{currency[1]} ({currency[0]})"} for currency in CURRENCY_CHOICES]
                },
                {
                    'name': 'type',
                    'label': 'Type',
                    'type': 'select',
                    'required': True,
                    'choices': [{'value': type[0], 'text': type[0]} for type in Transactions._meta.get_field('type').choices if type[0]]
                },
                {
                    'name': 'quantity',
                    'label': 'Quantity',
                    'type': 'number',
                    'required': False,
                },
                {
                    'name': 'price',
                    'label': 'Price',
                    'type': 'number',
                    'required': False,
                },
                {
                    'name': 'cash_flow',
                    'label': 'Cash Flow',
                    'type': 'number',
                    'required': False,
                },
                {
                    'name': 'commission',
                    'label': 'Commission',
                    'type': 'number',
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

class FXTransactionViewSet(viewsets.ModelViewSet):
    serializer_class = FXTransactionFormSerializer
    queryset = FXTransaction.objects.all()

    def get_queryset(self):
        return self.queryset.filter(investor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(investor=self.request.user)

    @action(detail=False, methods=['POST'])
    def create_fx_transaction(self, request):
        print("Received data:", request.data)  # Debug print
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        print("Serializer errors:", serializer.errors)  # Debug print
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET'])
    def form_structure(self, request):
        form_serializer = FXTransactionFormSerializer()
        
        return Response({
            'fields': [
                {
                    'name': 'date',
                    'label': 'Date',
                    'type': 'datepicker',
                    'required': True,
                },
                {
                    'name': 'broker',
                    'label': 'Broker',
                    'type': 'select',
                    'required': True,
                    'choices': form_serializer.get_broker_choices(request.user)
                },
                {
                    'name': 'from_currency',
                    'label': 'From Currency',
                    'type': 'select',
                    'required': True,
                    'choices': form_serializer.get_currency_choices()
                },
                {
                    'name': 'to_currency',
                    'label': 'To Currency',
                    'type': 'select',
                    'required': True,
                    'choices': form_serializer.get_currency_choices()
                },
                {
                    'name': 'from_amount',
                    'label': 'From Amount',
                    'type': 'number',
                    'required': True,
                },
                {
                    'name': 'to_amount',
                    'label': 'To Amount',
                    'type': 'number',
                    'required': True,
                },
                {
                    'name': 'commission',
                    'label': 'Commission',
                    'type': 'number',
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

    # def create(self, request, *args, **kwargs):
    #     serializer = FXTransactionFormSerializer(data=request.data)
    #     if serializer.is_valid():
    #         self.perform_create(serializer)
    #         headers = self.get_success_headers(serializer.data)
    #         return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # def update(self, request, *args, **kwargs):
    #     partial = kwargs.pop('partial', False)
    #     instance = self.get_object()
    #     serializer = FXTransactionFormSerializer(instance, data=request.data, partial=partial)
    #     if serializer.is_valid():
    #         self.perform_update(serializer)
    #         return Response(serializer.data)
    #     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)