from django import forms
from common.models import Brokers
from users.models import CustomUser

class DashboardForm(forms.ModelForm):
    # selected_brokers = forms.ModelMultipleChoiceField(
    #     queryset=Brokers.objects.none(),
    #     widget=forms.SelectMultiple(attrs={'class': 'selectpicker show-tick', 'data-actions-box': 'true', 'data-width': '100%', 'title': 'Choose broker', 'data-selected-text-format': 'count', 'id': 'inputBrokers'}),
    #     label='Brokers'
    # )

    custom_brokers = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'inputDashboardBrokers'}),
        label='Brokers',
    )

    table_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control',
                                      'id': 'inputTableDate',
                                      'type': 'date'
                                      }),
        label='Date'
    )

    class Meta:
        model = CustomUser
        fields = ['custom_brokers', 'default_currency', 'table_date', 'digits']
        labels = {
            'default_currency': 'Currency',
            'digits': 'Number of digits',
        }
        widgets = {
            'default_currency': forms.Select(attrs={'class': 'form-select', 'id': 'inputCurrency'}),
            'digits': forms.NumberInput(attrs={'class': 'form-control', 'id': 'numberOfDigits'}),
            # 'custom_brokers': forms.Select(attrs={'class': 'form-select', 'id': 'inputBrokers'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        # Retrieve the currency choices from the model and exclude the empty option
        self.fields['default_currency'].choices = [(choice[0], choice[0]) for choice in CustomUser._meta.get_field('default_currency').choices if choice[0]]
        if user is not None:
            brokers = Brokers.objects.filter(investor=user).order_by('name')
            self.fields['custom_brokers'].choices = [(broker.pk, broker.name) for broker in brokers]
            self.fields['custom_brokers'].initial = user.custom_brokers