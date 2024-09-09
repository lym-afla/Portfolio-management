from rest_framework import serializers
from common.models import Transactions, FXTransaction, Assets, Brokers
from constants import CURRENCY_CHOICES

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transactions
        fields = ['id', 'investor', 'broker', 'security', 'currency', 'type', 'date', 'quantity', 'price', 'cash_flow', 'commission', 'comment']
        read_only_fields = ['id', 'investor']

class TransactionFormSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transactions
        fields = ['id', 'broker', 'security', 'currency', 'type', 'date', 'quantity', 'price', 'cash_flow', 'commission', 'comment']

    def validate(self, data):
        transaction_type = data.get('type')
        cash_flow = data.get('cash_flow')
        price = data.get('price')
        quantity = data.get('quantity')
        commission = data.get('commission')

        if cash_flow is not None and transaction_type == 'Cash out' and cash_flow >= 0:
            raise serializers.ValidationError({'cash_flow': 'Cash flow must be negative for cash-out transactions.'})

        if cash_flow is not None and transaction_type == 'Cash in' and cash_flow <= 0:
            raise serializers.ValidationError({'cash_flow': 'Cash flow must be positive for cash-in transactions.'})
        
        if price is not None and price < 0:
            raise serializers.ValidationError({'price': 'Price must be positive.'})
        
        if transaction_type == 'Buy' and quantity is not None and quantity <= 0:
            raise serializers.ValidationError({'quantity': 'Quantity must be positive for buy transactions.'})
        
        if transaction_type == 'Sell' and quantity is not None and quantity >= 0:
            raise serializers.ValidationError({'quantity': 'Quantity must be negative for sell transactions.'})
        
        if commission is not None and commission >= 0:
            raise serializers.ValidationError({'commission': 'Commission must be negative.'})

        return data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['broker'] = {'id': instance.broker.id, 'name': instance.broker.name}
        if instance.security:
            representation['security'] = {'id': instance.security.id, 'name': instance.security.name}
        return representation

    def get_broker_choices(self, investor):
        return [{'value': str(broker.pk), 'text': broker.name} for broker in Brokers.objects.filter(investor=investor).order_by('name')]

    def get_security_choices(self, investor):
        choices = [{'value': str(security.pk), 'text': security.name} for security in Assets.objects.filter(investor=investor).order_by('name')]
        return choices

class FXTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FXTransaction
        fields = ['id', 'investor', 'broker', 'date', 'from_currency', 'to_currency', 'from_amount', 'to_amount', 'exchange_rate', 'commission', 'comment']
        read_only_fields = ['id', 'investor']

class FXTransactionFormSerializer(serializers.ModelSerializer):
    class Meta:
        model = FXTransaction
        fields = ['id', 'broker', 'date', 'from_currency', 'to_currency', 'from_amount', 'to_amount', 'exchange_rate', 'commission', 'comment']

    def validate(self, data):
        if data.get('from_amount') <= 0:
            raise serializers.ValidationError({'from_amount': 'From amount must be positive.'})
        if data.get('to_amount') <= 0:
            raise serializers.ValidationError({'to_amount': 'To amount must be positive.'})
        if data.get('commission') is not None and data['commission'] >= 0:
            raise serializers.ValidationError({'commission': 'Commission must be negative.'})
        
        # Calculate exchange rate
        from_amount = data.get('from_amount')
        to_amount = data.get('to_amount')
        if from_amount and to_amount:
            data['exchange_rate'] = from_amount / to_amount
        
        return data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['broker'] = {'id': instance.broker.id, 'name': instance.broker.name}
        return representation

    def get_broker_choices(self, investor):
        return [{'value': str(broker.pk), 'text': broker.name} for broker in Brokers.objects.filter(investor=investor).order_by('name')]

    def get_currency_choices(self):
        return [{'value': currency[0], 'text': currency[1]} for currency in CURRENCY_CHOICES]