from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from constants import CURRENCY_CHOICES, NAV_BARCHART_CHOICES
from core.user_utils import FREQUENCY_CHOICES, TIMELINE_CHOICES

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
    custom_brokers = serializers.CharField(required=False)

    class Meta:
        model = User
        fields = ['default_currency', 'use_default_currency_where_relevant', 'chart_frequency', 
                  'chart_timeline', 'NAV_barchart_default_breakdown', 'digits', 'custom_brokers']

    def validate_digits(self, value):
        if value > 6:
            raise serializers.ValidationError('The value for digits must be less than or equal to 6.')
        return value

class BrokerChoiceSerializer(serializers.Serializer):
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
    broker_choices = BrokerChoiceSerializer(many=True)

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