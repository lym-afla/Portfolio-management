from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from constants import CURRENCY_CHOICES, NAV_BARCHART_CHOICES
from core.user_utils import FREQUENCY_CHOICES, TIMELINE_CHOICES
from users.models import InteractiveBrokersApiToken, TinkoffApiToken, AccountGroup
from common.models import BrokerAccounts

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'password2', 'first_name', 'last_name')
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password']
        )
        return user

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')
        read_only_fields = ('username',)

class UserSettingsSerializer(serializers.ModelSerializer):

    default_currency = serializers.ChoiceField(choices=CURRENCY_CHOICES)
    chart_frequency = serializers.ChoiceField(choices=FREQUENCY_CHOICES)
    chart_timeline = serializers.ChoiceField(choices=TIMELINE_CHOICES)
    NAV_barchart_default_breakdown = serializers.ChoiceField(choices=NAV_BARCHART_CHOICES)
    custom_broker_accounts = serializers.CharField(required=False)

    class Meta:
        model = User
        fields = ['default_currency', 'use_default_currency_where_relevant', 'chart_frequency', 
                  'chart_timeline', 'NAV_barchart_default_breakdown', 'digits', 'custom_broker_accounts']

    def validate_digits(self, value):
        if value > 6:
            raise serializers.ValidationError('The value for digits must be less than or equal to 6.')
        return value

    def validate_custom_broker_accounts(self, value):
        if value:
            user = self.context.get('request').user
            if not value.startswith(('All', 'group_')):
                try:
                    BrokerAccounts.objects.get(id=value, broker__investor=user)
                except BrokerAccounts.DoesNotExist:
                    raise serializers.ValidationError('Invalid broker account selected.')
        return value

class BrokerAccountChoiceSerializer(serializers.Serializer):
    def to_representation(self, instance):
        if instance[0] == '__SEPARATOR__':
            return ['__SEPARATOR__', '__SEPARATOR__']
        elif isinstance(instance[1], (list, tuple)):
            return [instance[0], [list(subitem) for subitem in instance[1]]]
        else:
            return list(instance)

class UserSettingsChoicesSerializer(serializers.Serializer):
    currency_choices = serializers.ListField(child=serializers.ListField(child=serializers.CharField()))
    frequency_choices = serializers.ListField(child=serializers.ListField(child=serializers.CharField()))
    timeline_choices = serializers.ListField(child=serializers.ListField(child=serializers.CharField()))
    nav_breakdown_choices = serializers.ListField(child=serializers.ListField(child=serializers.CharField()))
    account_choices = BrokerAccountChoiceSerializer(many=True)

class DashboardSettingsSerializer(serializers.ModelSerializer):
    table_date = serializers.DateField(default=timezone.now().date())

    class Meta:
        model = User
        fields = ['default_currency', 'digits', 'table_date']
        extra_kwargs = {
            'default_currency': {'label': 'Currency'},
            'digits': {'label': 'Number of digits'},
        }

class DashboardSettingsChoicesSerializer(serializers.Serializer):
    default_currency = serializers.ListField(child=serializers.ListField(child=serializers.CharField()))

# Add new serializers for token management
class BaseApiTokenSerializer(serializers.ModelSerializer):
    token = serializers.CharField(write_only=True)

    class Meta:
        abstract = True
        fields = ['id', 'token']
        read_only_fields = ['id']

    def create(self, validated_data):
        token = validated_data.pop('token')
        user = validated_data.get('user')
        instance = super().create(validated_data)
        instance.set_token(token, user)
        return instance

    def update(self, instance, validated_data):
        if 'token' in validated_data:
            token = validated_data.pop('token')
            user = validated_data.get('user')
            instance = super().update(instance, validated_data)
            instance.set_token(token, user)
            return instance
        return super().update(instance, validated_data)

class TinkoffApiTokenSerializer(BaseApiTokenSerializer):
    token_type = serializers.ChoiceField(choices=[
        ('read_only', 'Read Only'),
        ('full_access', 'Full Access'),
    ])
    sandbox_mode = serializers.BooleanField(default=False)
    is_active = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta(BaseApiTokenSerializer.Meta):
        model = TinkoffApiToken
        fields = BaseApiTokenSerializer.Meta.fields + [
            'token_type', 
            'sandbox_mode', 
            'is_active',
            'created_at', 
            'updated_at'
        ]

class InteractiveBrokersApiTokenSerializer(BaseApiTokenSerializer):
    class Meta(BaseApiTokenSerializer.Meta):
        model = InteractiveBrokersApiToken
        fields = BaseApiTokenSerializer.Meta.fields

class AccountGroupSerializer(serializers.ModelSerializer):
    broker_accounts = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=BrokerAccounts.objects.all()
    )

    class Meta:
        model = AccountGroup
        fields = ['id', 'name', 'broker_accounts', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        # Ensure user can only add their own broker accounts to groups
        request = self.context.get('request')
        if request and request.user:
            user_accounts = BrokerAccounts.objects.filter(broker__investor=request.user)
            invalid_accounts = set(data['broker_accounts']) - set(user_accounts)
            
            if invalid_accounts:
                raise serializers.ValidationError({
                    'broker_accounts': 'You can only add your own broker accounts to groups'
                })
        
        return data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Add broker account details to the response
        representation['broker_accounts'] = [{
            'id': account.id,
            'name': account.name,
        } for account in instance.broker_accounts.all()]
        return representation

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)