from django import forms
from common.models import Assets, Brokers, Prices, Transactions
from constants import CURRENCY_CHOICES

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transactions
        fields = ['date', 'broker', 'type', 'currency', 'security', 'quantity', 'price', 'cash_flow', 'commission', 'comment']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control',
                                           'type': 'date'}),
            'broker': forms.Select(attrs={'class': 'form-select'}),
            'security': forms.Select(attrs={'class': 'form-select'}),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            'cash_flow': forms.NumberInput(attrs={'class': 'form-control'}),
            'commission': forms.NumberInput(attrs={'class': 'form-control'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }
    
    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        # Set choices dynamically for broker, security, and type fields
        if investor is not None:
            self.fields['broker'].choices = [(broker.pk, broker.name) for broker in Brokers.objects.filter(investor=investor).order_by('name')]
            security_choices = [(security.pk, security.name) for security in Assets.objects.filter(investor=investor).order_by('name')]
            # Add empty choice for securities
            security_choices.insert(0, ('', '--- Select Security ---'))
            self.fields['security'].choices = security_choices
        else:
            self.fields['broker'].choices = [(broker.pk, broker.name) for broker in Brokers.objects.order_by('name').all()]
            # security_choices = []

        # self.fields['broker'].choices = broker_choices
        # self.fields['security'].choices = security_choices

        self.fields['type'].choices = [(choice[0], choice[0]) for choice in Transactions._meta.get_field('type').choices if choice[0]]

    def clean(self):
        cleaned_data = super().clean()
        transaction_type = cleaned_data.get('type')
        cash_flow = cleaned_data.get('cash_flow')
        price = cleaned_data.get('price')
        quantity = cleaned_data.get('quantity')
        commission = cleaned_data.get('commission')

        if cash_flow is not None and transaction_type == 'Cash out' and cash_flow >= 0:
            self.add_error('cash_flow', 'Cash flow must be negative for cash-out transactions.')

        if cash_flow is not None and transaction_type == 'Cash in' and cash_flow <= 0:
            self.add_error('cash_flow', 'Cash flow must be positive for cash-in transactions.')
        
        if price is not None and price <= 0:
            self.add_error('price', 'Price must be positive.')
        
        if transaction_type == 'Buy' and quantity is not None and quantity <= 0:
            self.add_error('quantity', 'Quantity must be positive for buy transactions.')
        
        if transaction_type == 'Sell' and quantity is not None and quantity >= 0:
            self.add_error('quantity', 'Quantity must be negative for sell transactions.')
        
        if commission is not None and commission >= 0:
            self.add_error('commission', 'Commission must be negative.')

        return cleaned_data
    
class BrokerForm(forms.ModelForm):
    class Meta:
        model = Brokers
        fields = ['name', 'country', 'restricted', 'comment']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'restricted': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class PriceForm(forms.ModelForm):
    class Meta:
        model = Prices
        fields = '__all__'
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control',
                                           'type': 'date'}),
            'security': forms.Select(attrs={'class': 'form-select'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        # Set choices dynamically for broker, security, and type fields
        self.fields['security'].choices = [(security.pk, security.name) for security in Assets.objects.filter(investor=investor).order_by('name').all()]

class SecurityForm(forms.ModelForm):

    # broker = forms.ModelChoiceField(
    #     queryset=Brokers.objects.none(),  # Use a default empty queryset
    #     widget=forms.Select(attrs={'class': 'form-select'}),
    #     required=True,
    #     label="Broker"
    # )

    custom_brokers = forms.MultipleChoiceField(
        choices=[],  # We'll set choices in the __init__ method
        widget=forms.SelectMultiple(
            attrs={
                'class': 'selectpicker show-tick',
                'data-actions-box': 'true',
                'data-width': '100%',
                'title': 'Choose broker',
                'data-selected-text-format': 'count',
                # 'id': 'inputBrokers'
            }
        ),
        label='Brokers'
    )

    class Meta:
        model = Assets
        fields = ['name', 'ISIN', 'type', 'currency', 'exposure', 'restricted', 'custom_brokers', 'comment']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'ISIN': forms.TextInput(attrs={'class': 'form-control'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'exposure': forms.Select(attrs={'class': 'form-select'}),
            'restricted': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        # Set choices dynamically for broker, security, and type fields
        self.fields['type'].choices = [(choice[0], choice[0]) for choice in Assets._meta.get_field('type').choices if choice[0]]
        
        # Filter brokers based on the investor
        self.fields['custom_brokers'].choices = [(broker.id, broker.name) for broker in Brokers.objects.filter(investor=investor).order_by('name')]
        
        # Set choices dynamically for broker field
        # self.fields['broker'].queryset = Brokers.objects.filter(investor=investor).order_by('name')

        # # If instance exists, pre-select the current brokers
        if self.instance.pk:
            self.fields['custom_brokers'].initial = [broker.id for broker in self.instance.brokers.all()]


EXTENDED_CURRENCY_CHOICES = CURRENCY_CHOICES + (('All', 'All Currencies'),)

class BrokerPerformanceForm(forms.Form):

    brokers = forms.ModelMultipleChoiceField(
        queryset=Brokers.objects.all(),
        widget=forms.SelectMultiple(
            attrs={
                'class': 'selectpicker show-tick',
                'data-actions-box': 'true',
                'data-width': '100%',
                'title': 'Choose broker',
                'data-selected-text-format': 'count',
            })
    )
    currency = forms.ChoiceField(
        choices=EXTENDED_CURRENCY_CHOICES,
        widget=forms.Select(
            attrs={'class': 'form-select'}
        )
    )
    is_restricted = forms.ChoiceField(
        choices=(('All', 'All'), ('None', 'No flag'), ('True', 'Restricted'), ('False', 'Not restricted')),
        widget=forms.Select(
            attrs={'class': 'form-select'}
        )
    )

    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        self.fields['brokers'].choices = [(broker.id, broker.name) for broker in Brokers.objects.filter(investor=investor).order_by('name')]
