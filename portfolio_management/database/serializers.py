from rest_framework import serializers
from common.models import Assets, BrokerAccounts, FX, Brokers, Transactions, Prices
from core.user_utils import prepare_account_choices
from users.models import AccountGroup
from constants import CURRENCY_CHOICES, ACCOUNT_TYPE_ALL, ACCOUNT_TYPE_INDIVIDUAL, ACCOUNT_TYPE_GROUP, ACCOUNT_TYPE_BROKER
from decimal import Decimal

from core.formatting_utils import format_value

class PriceImportSerializer(serializers.Serializer):
    securities = serializers.PrimaryKeyRelatedField(
        queryset=Assets.objects.all(),
        many=True,
        required=False
    )
    broker_accounts = serializers.PrimaryKeyRelatedField(
        queryset=BrokerAccounts.objects.all(),
        many=True,
        required=False
    )
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    frequency = serializers.ChoiceField(
        choices=[('weekly', 'Weekly'), ('monthly', 'Monthly'), ('quarterly', 'Quarterly'), ('yearly', 'Yearly')],
        required=False,
        allow_null=True
    )
    single_date = serializers.DateField(required=False, input_formats=['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%d'])

    def validate(self, data):
        print("Received data:", data)
        if not data.get('securities') and not data.get('broker_accounts'):
            raise serializers.ValidationError(f"Either securities or broker accounts must be selected.")
        
        if data.get('securities') and data.get('broker_accounts'):
            raise serializers.ValidationError("Only one of securities or broker accounts can be selected.")
        
        if (data.get('start_date') or data.get('end_date') or data.get('frequency')) and data.get('single_date'):
            raise serializers.ValidationError("Either date range or single date should be provided, not both.")
        
        if (data.get('start_date') or data.get('end_date')):
            if not data.get('frequency'):
                raise serializers.ValidationError("Frequency must be provided with date range.")
            if not (data.get('start_date') and data.get('end_date')):
                raise serializers.ValidationError("Both start date and end date must be provided for date range.")
        
        if not (data.get('start_date') and data.get('end_date') and data.get('frequency')) and not data.get('single_date'):
            raise serializers.ValidationError("Either date range with frequency or single date must be provided.")

        return data
    
class BrokerAccountSerializer(serializers.ModelSerializer):
    broker = serializers.SerializerMethodField()

    class Meta:
        model = BrokerAccounts
        fields = ['id', 'name', 'broker', 'restricted', 'comment']

    def get_broker(self, obj):
        if obj.broker:
            return {
                'value': obj.broker.id,
                'text': obj.broker.name
            }
        return None

    def to_internal_value(self, data):
        internal_data = super().to_internal_value(data)
        
        # Handle broker field consistently
        broker_data = data.get('broker')
        broker_id = None
        
        if isinstance(broker_data, dict):
            broker_id = broker_data.get('value')
        elif isinstance(broker_data, (int, str)):
            broker_id = int(broker_data)
            
        if broker_id:
            try:
                broker = Brokers.objects.get(id=broker_id)
                internal_data['broker'] = broker
            except Brokers.DoesNotExist:
                raise serializers.ValidationError({'broker': 'Invalid broker ID'})
        
        return internal_data

class AccountPerformanceSerializer(serializers.Serializer):
    selection_account_type = serializers.ChoiceField(
        choices=[ACCOUNT_TYPE_ALL, ACCOUNT_TYPE_INDIVIDUAL, ACCOUNT_TYPE_GROUP, ACCOUNT_TYPE_BROKER]
    )
    selection_account_id = serializers.IntegerField(required=False, allow_null=True)
    currency = serializers.ChoiceField(
        choices=CURRENCY_CHOICES + (('All', 'All Currencies'),)
    )
    is_restricted = serializers.ChoiceField(
        choices=[
            ('All', 'All'),
            ('None', 'No flag'),
            ('True', 'Restricted'),
            ('False', 'Not restricted')
        ]
    )
    skip_existing_years = serializers.BooleanField(required=False, default=False)
    effective_current_date = serializers.DateField(required=True)

    def __init__(self, *args, **kwargs):
        self.investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        
        # Get choices data using prepare_account_choices
        choices_data = prepare_account_choices(self.investor)
        self.choices_data = choices_data['options']

    def validate(self, data):
        """
        Validate the complete data set.
        Called after individual field validation and only if all fields are valid.
        """
        account_type = data.get('selection_account_type')
        account_id = data.get('selection_account_id')

        # Special case for 'all' type
        if account_type == 'all':
            if account_id is not None:
                raise serializers.ValidationError({
                    'selection_account_id': 'Should be null when type is "all"'
                })
            return data

        # For other types, account_id is required
        if account_id is None:
            raise serializers.ValidationError({
                'selection_account_id': 'Required when type is not "all"'
            })

        # Check if the account type and ID combination exists in choices_data
        valid_selection = False
        for section, items in self.choices_data:
            if section != '__SEPARATOR__':
                for _, item_data in items:
                    if (item_data['type'] == account_type and 
                        item_data.get('id') == account_id):
                        valid_selection = True
                        break

        if not valid_selection:
            raise serializers.ValidationError({
                'selection_account_type': 'Invalid account selection'
            })

        return data

    def get_form_data(self):
        """Return the form structure for frontend"""
        return {
            'account_choices': self.choices_data,
            'currency_choices': dict(self.fields['currency'].choices),
            'is_restricted_choices': dict(self.fields['is_restricted'].choices),
        }

class FXSerializer(serializers.ModelSerializer):
    class Meta:
        model = FX
        fields = ['id', 'date', 'USDEUR', 'USDGBP', 'CHFGBP', 'RUBUSD', 'PLNUSD']
        read_only_fields = ['id']  # Remove 'investor' from read_only_fields

class FXRateSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=3)
    target = serializers.CharField(max_length=3)
    date = serializers.DateField()

class TransactionSerializer(serializers.ModelSerializer):
    date = serializers.SerializerMethodField()
    type = serializers.CharField()
    quantity = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    value = serializers.SerializerMethodField()
    cash_flow = serializers.SerializerMethodField()
    commission = serializers.SerializerMethodField()
    currency = serializers.CharField()
    security_name = serializers.SerializerMethodField()
    security_id = serializers.SerializerMethodField()
    broker_account = serializers.SerializerMethodField()

    class Meta:
        model = Transactions
        fields = ['date', 'type', 'quantity', 'price', 'value', 'cash_flow', 'commission', 'currency', 'security_name', 'security_id', 'broker_account']

    def get_digits(self):
        return self.context.get('digits', 2)  # Default to 2 if not provided

    def get_date(self, obj):
        return format_value(obj.date, 'date', None, None)

    def get_quantity(self, obj):
        quantity = abs(obj.quantity) if obj.quantity else None
        return format_value(quantity, 'quantity', None, 0)

    def get_price(self, obj):
        return format_value(obj.price, 'price', obj.currency, self.get_digits())

    def get_value(self, obj):
        if obj.quantity and obj.price:
            value = -Decimal(obj.quantity) * Decimal(obj.price)
            return format_value(value, 'value', obj.currency, self.get_digits())
        return None

    def get_cash_flow(self, obj):
        return format_value(obj.cash_flow, 'cash_flow', obj.currency, self.get_digits())

    def get_commission(self, obj):
        return format_value(obj.commission, 'commission', obj.currency, self.get_digits())

    def get_security_name(self, obj):
        return obj.security.name if obj.security else None

    def get_security_id(self, obj):
        return obj.security.id if obj.security else None

    def get_broker_account(self, obj):
        return {
            'id': obj.broker_account.id,
            'name': obj.broker_account.name
        } if obj.broker_account else None

class BrokerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brokers
        fields = ['id', 'name', 'country', 'comment']

class PriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prices
        fields = ['id', 'date', 'security', 'price']

    def __init__(self, *args, **kwargs):
        self.investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        
        if self.investor:
            # Filter securities by investor and order by name
            self.fields['security'].queryset = Assets.objects.filter(
                investors__id=self.investor.id
            ).order_by('name')
