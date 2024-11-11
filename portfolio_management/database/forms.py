from django import forms
from common.models import Assets, BrokerAccounts, FXTransaction, Prices
from users.models import AccountGroup
from constants import CURRENCY_CHOICES
from common.forms import GroupedSelect
from constants import ACCOUNT_TYPE_CHOICES, ACCOUNT_TYPE_ALL
from core.user_utils import prepare_account_choices
    
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

    # broker_accounts = forms.MultipleChoiceField(
    #     choices=[],
    #     widget=forms.SelectMultiple(
    #         attrs={
    #             'class': 'selectpicker show-tick',
    #             'data-actions-box': 'true',
    #             'data-width': '100%',
    #             'title': 'Choose broker account',
    #             'data-selected-text-format': 'count',
    #         }
    #     ),
    #     label='Broker Accounts'
    # )

    update_link = forms.URLField(required=False, assume_scheme='http')  # Specify the default scheme

    class Meta:
        model = Assets
        fields = ['name', 'ISIN', 'type', 'currency', 'exposure', 'restricted', 'data_source', 'yahoo_symbol', 'update_link', 'secid', 'fund_fee', 'comment']
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
        # investor = kwargs.pop('investor', None)
        super().__init__(*args, **kwargs)
        # Set choices dynamically for broker, security, and type fields
        self.fields['type'].choices = [(choice[0], choice[0]) for choice in Assets._meta.get_field('type').choices if choice[0]]
        
        # # Filter broker accounts based on the investor
        # self.fields['broker_accounts'].choices = [
        #     (account.id, account.name) 
        #     for account in BrokerAccounts.objects.filter(broker__investor=investor).order_by('name')
        # ]
        
        # self.fields['data_source'].widget = forms.Select(choices=Assets.DATA_SOURCE_CHOICES)
        self.fields['data_source'].choices = [('', 'None')] + Assets.DATA_SOURCE_CHOICES
        self.fields['yahoo_symbol'].required = False
        self.fields['update_link'].required = False
        self.fields['fund_fee'].required = False
        self.fields['secid'].required = False

        self.fields['update_link'].label = 'Update link (Financial Times)'

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
    selection_account_type = forms.CharField(widget=forms.HiddenInput(), required=False)
    selection_account_id = forms.IntegerField(widget=forms.HiddenInput(), required=False)
    
    account_selection = forms.ChoiceField(
        choices=[],
        widget=GroupedSelect(attrs={'class': 'form-select'}),
        label='Account Selection',
    )
    
    currency = forms.ChoiceField(
        choices=EXTENDED_CURRENCY_CHOICES,
        widget=forms.Select(
            attrs={'class': 'form-select'}
        )
    )
    
    is_restricted = forms.ChoiceField(
        choices=(
            ('All', 'All'),
            ('None', 'No flag'),
            ('True', 'Restricted'),
            ('False', 'Not restricted')
        ),
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

        if investor is not None:
            # Get structured account choices
            choices_data = prepare_account_choices(investor)
            
            # Convert the structured choices to form choices format
            account_choices = []
            for section, items in choices_data['options']:
                if section == '__SEPARATOR__':
                    account_choices.append(('__SEPARATOR__', '__SEPARATOR__'))
                else:
                    formatted_items = []
                    for item_label, item_data in items:
                        # Create a composite value that can be parsed later
                        value = f"{item_data['type']}:{item_data.get('id', '')}"
                        formatted_items.append((value, item_label))
                    account_choices.append((section, tuple(formatted_items)))
            
            self.fields['account_selection'].choices = account_choices

    def clean(self):
        cleaned_data = super().clean()
        account_selection = cleaned_data.get('account_selection')

        if account_selection:
            try:
                selection_type, selection_id = account_selection.split(':')
                cleaned_data['selection_type'] = selection_type
                cleaned_data['selection_id'] = int(selection_id) if selection_id else None
            except ValueError:
                raise forms.ValidationError('Invalid account selection format')

        return cleaned_data

    def get_selection_data(self):
        """
        Returns the cleaned selection type and ID for use in queries
        """
        if self.is_valid():
            return {
                'selection_type': self.cleaned_data['selection_type'],
                'selection_id': self.cleaned_data['selection_id']
            }
        return None

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