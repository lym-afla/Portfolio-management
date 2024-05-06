from django import forms
from common.models import Brokers
from users.models import CustomUser

class DashboardForm(forms.ModelForm):
    selected_brokers = forms.ModelMultipleChoiceField(
        queryset=Brokers.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'selectpicker show-tick', 'data-actions-box': 'true', 'data-width': '100%', 'title': 'Choose broker', 'data-selected-text-format': 'count', 'id': 'inputBrokers'}),
        label='Brokers'
    )

    table_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'id': 'inputTableDate'}),
        label='Date'
    )

    class Meta:
        model = CustomUser
        fields = ['selected_brokers', 'default_currency', 'table_date', 'digits']
        labels = {
            'default_currency': 'Currency',
            'digits': 'Number of digits',
        }
        widgets = {
            'default_currency': forms.Select(attrs={'class': 'form-select', 'id': 'inputCurrency'}),
            'digits': forms.NumberInput(attrs={'class': 'form-control', 'id': 'numberOfDigits'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Retrieve the currency choices from the model and exclude the empty option
        self.fields['default_currency'].choices = [(choice[0], choice[0]) for choice in CustomUser._meta.get_field('default_currency').choices if choice[0]]

    # currency_choices = [
    #     ('USD', 'USD'),
    #     ('EUR', 'EUR'),
    #     ('GBP', 'GBP'),
    #     ('RUB', 'RUB'),
    # ]

    # table_currency = forms.ChoiceField(
    #     choices=currency_choices,
    #     widget=forms.Select(attrs={'class': 'form-select', 'id': 'inputCurrency'}),
    #     label='Currency'
    # )

    # number_of_digits = forms.IntegerField(
    #     widget=forms.NumberInput(attrs={'class': 'form-control', 'id': 'numberOfDigits'}),
    #     label='Number of digits'
    # )