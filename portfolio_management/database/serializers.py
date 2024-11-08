from rest_framework import serializers
from common.models import Assets, BrokerAccounts, FX, Brokers, Transactions
from users.models import AccountGroup
from constants import CURRENCY_CHOICES
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

    def to_representation(self, instance):
        # For GET requests, include the formatted broker data
        data = super().to_representation(instance)
        return data

    def to_internal_value(self, data):
        # For POST/PUT requests, handle the broker ID
        internal_data = super().to_internal_value(data)
        broker_id = data.get('broker')
        if broker_id:
            try:
                broker = Brokers.objects.get(id=broker_id)
                internal_data['broker'] = broker
            except Brokers.DoesNotExist:
                raise serializers.ValidationError({'broker': 'Invalid broker ID'})
        return internal_data

class AccountPerformanceSerializer(serializers.Serializer):
    account_or_group = serializers.ChoiceField(choices=[])
    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES + (('All', 'All Currencies'),))
    is_restricted = serializers.ChoiceField(choices=[
        ('All', 'All'),
        ('None', 'No flag'),
        ('True', 'Restricted'),
        ('False', 'Not restricted')
    ])
    skip_existing_years = serializers.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)

        account_choices = [
            ('All accounts', 'All accounts'),
            ('__SEPARATOR_1__', '__SEPARATOR__'),
        ]
        
        if investor is not None:
            accounts = BrokerAccounts.objects.filter(broker__investor=investor).order_by('name')
            user_accounts = [(account.name, account.name) for account in accounts]
            if user_accounts:
                account_choices.extend(user_accounts)
                account_choices.append(('__SEPARATOR_2__', '__SEPARATOR__'))
            
            user_groups = AccountGroup.objects.filter(user=investor).order_by('name')
            group_choices = [(group.name, group.name) for group in user_groups]
            if group_choices:
                account_choices.extend(group_choices)

        self.fields['account_or_group'].choices = account_choices

    def get_form_data(self):
        return {
            'account_choices': self.fields['account_or_group'].choices,
            'currency_choices': self.fields['currency'].choices,
            'is_restricted_choices': self.fields['is_restricted'].choices,
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
