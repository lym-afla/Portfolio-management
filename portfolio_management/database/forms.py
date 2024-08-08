from django import forms
from common.models import Assets, Brokers, FXTransaction, Prices, Transactions
from constants import BROKER_GROUPS, CURRENCY_CHOICES
from common.forms import GroupedSelect

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
        
        if price is not None and price < 0:
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

    # Included this for generic 'edit' framework to work properly
    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)

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

    custom_brokers = forms.MultipleChoiceField(
        choices=[],  # We'll set choices in the __init__ method
        widget=forms.SelectMultiple(
            attrs={
                'class': 'selectpicker show-tick',
                'data-actions-box': 'true',
                'data-width': '100%',
                'title': 'Choose broker',
                'data-selected-text-format': 'count',
            }
        ),
        label='Brokers'
    )

    class Meta:
        model = Assets
        fields = ['name', 'ISIN', 'type', 'currency', 'exposure', 'restricted', 'custom_brokers', 'data_source', 'yahoo_symbol', 'update_link', 'comment']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'ISIN': forms.TextInput(attrs={'class': 'form-control'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'exposure': forms.Select(attrs={'class': 'form-select'}),
            'restricted': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'data_source': forms.Select(attrs={'class': 'form-select'}),
            'yahoo_symbol': forms.TextInput(attrs={'class': 'form-control'}),
            'update_link': forms.URLInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        # Set choices dynamically for broker, security, and type fields
        self.fields['type'].choices = [(choice[0], choice[0]) for choice in Assets._meta.get_field('type').choices if choice[0]]
        
        # Filter brokers based on the investor
        self.fields['custom_brokers'].choices = [(broker.id, broker.name) for broker in Brokers.objects.filter(investor=investor).order_by('name')]
        
        # self.fields['data_source'].widget = forms.Select(choices=Assets.DATA_SOURCE_CHOICES)
        self.fields['data_source'].choices = [('', 'None')] + Assets.DATA_SOURCE_CHOICES
        self.fields['yahoo_symbol'].required = False
        self.fields['update_link'].required = False

        # If instance exists, pre-select the current brokers
        if self.instance.pk:
            self.fields['custom_brokers'].initial = [broker.id for broker in self.instance.brokers.all()]

    def clean(self):
        cleaned_data = super().clean()
        data_source = cleaned_data.get('data_source')
        yahoo_symbol = cleaned_data.get('yahoo_symbol')
        update_link = cleaned_data.get('update_link')

        if data_source == 'YAHOO' and not yahoo_symbol:
            self.add_error('yahoo_symbol', 'Yahoo symbol is required for Yahoo Finance data source.')
        elif data_source == 'FT' and not update_link:
            self.add_error('update_link', 'Update link is required for Financial Times data source.')

        return cleaned_data


EXTENDED_CURRENCY_CHOICES = CURRENCY_CHOICES + (('All', 'All Currencies'),)

class BrokerPerformanceForm(forms.Form):

    broker_or_group = forms.ChoiceField(
        choices=[],
        widget=GroupedSelect(attrs={'class': 'form-select'}),
        label='Brokers',
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
    skip_existing_years = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Skip existing calculated years'
    )

    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)

        # self.fields['brokers'].choices = [(broker.id, broker.name) for broker in Brokers.objects.filter(investor=investor).order_by('name')]

        # Initialize broker choices
        broker_or_group_choices = [
            ('General', (('All brokers', 'All brokers'),)),
            ('__SEPARATOR__', '__SEPARATOR__'),
        ]
        
        if investor is not None:
            brokers = Brokers.objects.filter(investor=investor).order_by('name')
            user_brokers = [(broker.name, broker.name) for broker in brokers]
            if user_brokers:
                broker_or_group_choices.append(('Your Brokers', tuple(user_brokers)))
                broker_or_group_choices.append(('__SEPARATOR__', '__SEPARATOR__'))
        
        # Add BROKER_GROUPS keys
        broker_or_group_choices.append(('Broker Groups', tuple((group, group) for group in BROKER_GROUPS.keys())))

        self.fields['broker_or_group'].choices = broker_or_group_choices

class FXTransactionForm(forms.ModelForm):
    class Meta:
        model = FXTransaction
        fields = ['broker', 'date', 'from_currency', 'to_currency', 'from_amount', 'to_amount', 'commission', 'comment']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'broker': forms.Select(attrs={'class': 'form-select', 'data-live-search': 'true'}),
            'from_currency': forms.Select(attrs={'class': 'form-select'}),
            'to_currency': forms.Select(attrs={'class': 'form-select'}),
            'from_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'to_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            # 'exchange_rate': forms.NumberInput(attrs={'class': 'form-control'}),
            'commission': forms.NumberInput(attrs={'class': 'form-control'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        # Set choices dynamically for broker, security, and type fields
        if investor is not None:
            self.fields['broker'].choices = [(broker.pk, broker.name) for broker in Brokers.objects.filter(investor=investor).order_by('name')]

    def clean(self):
        cleaned_data = super().clean()
        from_amount = cleaned_data.get('from_amount')
        to_amount = cleaned_data.get('to_amount')
        exchange_rate = cleaned_data.get('exchange_rate')

        if from_amount and to_amount and exchange_rate:
            calculated_rate = from_amount / to_amount
            if abs(calculated_rate - exchange_rate) > 0.0001:
                raise forms.ValidationError("Exchange rate does not match the provided amounts.")

        return cleaned_data

class PriceImportForm(forms.Form):
    securities = forms.ModelMultipleChoiceField(
        queryset=Assets.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control selectpicker', 'data-live-search': 'true'})
    )
    broker = forms.ModelChoiceField(
        queryset=Brokers.objects.all(),
        required=False,
        empty_label="Select Broker",
        widget=forms.Select(attrs={'class': 'form-control selectpicker', 'data-live-search': 'true'})
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    frequency = forms.ChoiceField(
        required=False,
        choices=[('monthly', 'Monthly'), ('quarterly', 'Quarterly'), ('annually', 'Annually')],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    single_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['securities'].queryset = Assets.objects.filter(investor=user).order_by('name')
            self.fields['broker'].queryset = Brokers.objects.filter(investor=user).order_by('name')