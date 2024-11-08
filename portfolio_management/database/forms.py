from django import forms
from common.models import Assets, BrokerAccounts, FXTransaction, Prices
from users.models import AccountGroup
from constants import CURRENCY_CHOICES
from common.forms import GroupedSelect
    
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
        self.fields['security'].choices = [(security.pk, security.name) for security in Assets.objects.filter(investors__id=investor.id).order_by('name').all()]

class SecurityForm(forms.ModelForm):

    broker_accounts = forms.MultipleChoiceField(
        choices=[],
        widget=forms.SelectMultiple(
            attrs={
                'class': 'selectpicker show-tick',
                'data-actions-box': 'true',
                'data-width': '100%',
                'title': 'Choose broker account',
                'data-selected-text-format': 'count',
            }
        ),
        label='Broker Accounts'
    )

    update_link = forms.URLField(required=False, assume_scheme='http')  # Specify the default scheme

    class Meta:
        model = Assets
        fields = ['name', 'ISIN', 'type', 'currency', 'exposure', 'restricted', 'broker_accounts', 'data_source', 'yahoo_symbol', 'update_link', 'secid', 'fund_fee', 'comment']
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
            'secid': forms.TextInput(attrs={'class': 'form-control'}),
            'fund_fee': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        # Set choices dynamically for broker, security, and type fields
        self.fields['type'].choices = [(choice[0], choice[0]) for choice in Assets._meta.get_field('type').choices if choice[0]]
        
        # Filter broker accounts based on the investor
        self.fields['broker_accounts'].choices = [
            (account.id, account.name) 
            for account in BrokerAccounts.objects.filter(broker__investor=investor).order_by('name')
        ]
        
        # self.fields['data_source'].widget = forms.Select(choices=Assets.DATA_SOURCE_CHOICES)
        self.fields['data_source'].choices = [('', 'None')] + Assets.DATA_SOURCE_CHOICES
        self.fields['yahoo_symbol'].required = False
        self.fields['update_link'].required = False
        self.fields['fund_fee'].required = False
        self.fields['secid'].required = False

        # If instance exists, pre-select the current broker accounts
        if self.instance.pk:
            self.fields['broker_accounts'].initial = [
                account.id for account in self.instance.broker_accounts.all()
            ]

    def clean(self):
        cleaned_data = super().clean()
        data_source = cleaned_data.get('data_source')
        yahoo_symbol = cleaned_data.get('yahoo_symbol')
        update_link = cleaned_data.get('update_link')
        secid = cleaned_data.get('secid')

        if data_source == 'YAHOO' and not yahoo_symbol:
            self.add_error('yahoo_symbol', 'Yahoo symbol is required for Yahoo Finance data source.')
        elif data_source == 'FT' and not update_link:
            self.add_error('update_link', 'Update link is required for Financial Times data source.')
        elif data_source == 'MICEX' and not secid:
            self.add_error('secid', 'Secid is required for MICEX data source.')

        return cleaned_data


EXTENDED_CURRENCY_CHOICES = CURRENCY_CHOICES + (('All', 'All Currencies'),)

class AccountPerformanceForm(forms.Form):

    account_or_group = forms.ChoiceField(
        choices=[],
        widget=GroupedSelect(attrs={'class': 'form-select'}),
        label='Broker Accounts',
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

        account_or_group_choices = [
            ('General', (('All accounts', 'All accounts'),)),
            ('__SEPARATOR__', '__SEPARATOR__'),
        ]
        
        if investor is not None:
            # Add individual broker accounts
            accounts = BrokerAccounts.objects.filter(broker__investor=investor).order_by('name')
            user_accounts = [(account.name, account.name) for account in accounts]
            if user_accounts:
                account_or_group_choices.append(('Your Accounts', tuple(user_accounts)))
                account_or_group_choices.append(('__SEPARATOR__', '__SEPARATOR__'))
            
            # Add user's account groups
            user_groups = AccountGroup.objects.filter(user=investor).order_by('name')
            group_choices = [(group.name, group.name) for group in user_groups]
            if group_choices:
                account_or_group_choices.append(('Account Groups', tuple(group_choices)))

        self.fields['account_or_group'].choices = account_or_group_choices

class FXTransactionForm(forms.ModelForm):
    class Meta:
        model = FXTransaction
        fields = ['broker_account', 'date', 'from_currency', 'to_currency', 'commission_currency', 'from_amount', 'to_amount', 'commission', 'comment']
        widgets = {
            'broker_account': forms.Select(attrs={'class': 'form-select', 'data-live-search': 'true'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'from_currency': forms.Select(attrs={'class': 'form-select'}),
            'to_currency': forms.Select(attrs={'class': 'form-select'}),
            'from_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'to_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            # 'exchange_rate': forms.NumberInput(attrs={'class': 'form-control'}),
            'commission': forms.NumberInput(attrs={'class': 'form-control'}),
            'commission_currency': forms.Select(attrs={'class': 'form-select'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        # Set choices dynamically for broker, security, and type fields
        if investor is not None:
            self.fields['broker_account'].choices = [
                (account.pk, account.name) 
                for account in BrokerAccounts.objects.filter(broker__investor=investor).order_by('name')
            ]

class PriceImportForm(forms.Form):
    securities = forms.ModelMultipleChoiceField(
        queryset=Assets.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control selectpicker', 'data-live-search': 'true'})
    )
    broker_account = forms.ModelChoiceField(
        queryset=BrokerAccounts.objects.all(),
        required=False,
        empty_label="Select Broker Account",
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
            self.fields['securities'].queryset = Assets.objects.filter(investors=user).order_by('name')
            self.fields['broker_account'].queryset = BrokerAccounts.objects.filter(broker__investor=user).order_by('name')