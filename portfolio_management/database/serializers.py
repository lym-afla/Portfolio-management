from rest_framework import serializers
from common.models import Assets, Brokers

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