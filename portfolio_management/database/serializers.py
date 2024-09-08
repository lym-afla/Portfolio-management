from rest_framework import serializers
from common.models import Assets, Brokers, FX
from constants import BROKER_GROUPS, CURRENCY_CHOICES

class PriceImportSerializer(serializers.Serializer):
    securities = serializers.PrimaryKeyRelatedField(
        queryset=Assets.objects.all(),
        many=True,
        required=False
    )
    brokers = serializers.PrimaryKeyRelatedField(
        queryset=Brokers.objects.all(),
        many=True,
        required=False
    )
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    frequency = serializers.ChoiceField(
        choices=[('weekly', 'Weekly'), ('monthly', 'Monthly'), ('quarterly', 'Quarterly'), ('annually', 'Annually')],
        required=False,
        allow_null=True
    )
    single_date = serializers.DateField(required=False, input_formats=['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%d'])

    def validate(self, data):
        print("Received data:", data)
        if not data.get('securities') and not data.get('brokers'):
            raise serializers.ValidationError(f"Either securities or brokers must be selected.")
        
        if data.get('securities') and data.get('brokers'):
            raise serializers.ValidationError("Only one of securities or brokers can be selected.")
        
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
    
class BrokerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brokers
        fields = ['id', 'name', 'country', 'comment', 'restricted']
        read_only_fields = ['id']

class BrokerPerformanceSerializer(serializers.Serializer):
    broker_or_group = serializers.ChoiceField(choices=[])
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

        broker_or_group_choices = [
            ('All brokers', 'All brokers'),
            ('__SEPARATOR_1__', '__SEPARATOR__'),
        ]
        
        if investor is not None:
            brokers = Brokers.objects.filter(investor=investor).order_by('name')
            user_brokers = [(broker.name, broker.name) for broker in brokers]
            if user_brokers:
                broker_or_group_choices.extend(user_brokers)
                broker_or_group_choices.append(('__SEPARATOR_2__', '__SEPARATOR__'))
        
        # Add BROKER_GROUPS keys
        broker_or_group_choices.extend((group, group) for group in BROKER_GROUPS.keys())

        self.fields['broker_or_group'].choices = broker_or_group_choices

    def get_form_data(self):
        return {
            'broker_or_group_choices': self.fields['broker_or_group'].choices,
            'currency_choices': self.fields['currency'].choices,
            'is_restricted_choices': self.fields['is_restricted'].choices,
        }

class FXSerializer(serializers.ModelSerializer):
    class Meta:
        model = FX
        fields = ['date', 'investor', 'USDEUR', 'USDGBP', 'CHFGBP', 'RUBUSD', 'PLNUSD']
        read_only_fields = ['date', 'investor']

class FXRateSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=3)
    target = serializers.CharField(max_length=3)
    date = serializers.DateField()