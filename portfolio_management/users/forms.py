from django import forms
from django.contrib.auth.forms import UserCreationForm

from constants import CURRENCY_CHOICES, NAV_BARCHART_CHOICES
from common.models import BrokerAccounts
from common.forms import GroupedSelect
from users.models import CustomUser, AccountGroup

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password1', 'password2')

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'})
        }
        labels = {
            'username': 'Username:',
            'first_name': 'First Name:',
            'last_name': 'Last Name:',
            'email': 'Email:',
        }

class UserSettingsForm(forms.ModelForm):
    FREQUENCY_CHOICES = [
        ('D', 'Daily'),
        ('W', 'Weekly'),
        ('M', 'Monthly'),
        ('Q', 'Quarterly'),
        ('Y', 'Yearly'),
    ]

    TIMELINE_CHOICES = [
        ('YTD', 'Year to Date'),
        ('3m', 'Last 3 months'),
        ('6m', 'Last 6 months'),
        ('12m', 'Last 12 months'),
        ('3Y', 'Last 3 years'),
        ('5Y', 'Last 5 years'),
        ('All', 'All history'),
        ('Custom', 'Custom'),
    ]
    
    default_currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Default currency'
    )
    chart_frequency = forms.ChoiceField(
        choices=FREQUENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Chart frequency'
    )
    chart_timeline = forms.ChoiceField(
        choices=TIMELINE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Chart timeline'
    )
    NAV_barchart_default_breakdown = forms.ChoiceField(
        choices=NAV_BARCHART_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Default NAV timeline breakdown'
    )

    custom_broker_accounts = forms.ChoiceField(
        choices=[],
        widget=GroupedSelect(attrs={'class': 'form-select', 'id': 'inputBrokerAccounts'}),
        label='Broker Accounts',
    )
    
    class Meta:
        model = CustomUser
        fields = ['custom_broker_accounts', 'default_currency', 'use_default_currency_where_relevant', 'chart_frequency', 'chart_timeline', 'digits', 'NAV_barchart_default_breakdown']
        widgets = {
            'use_default_currency_where_relevant': forms.CheckboxInput(attrs={'class': 'form-check-input ml-0'}),
            'digits': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'digits': 'Number of digits',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        self.fields['custom_broker_accounts'].choices = self.get_broker_account_choices(user)
        
        if user is not None:
            self.fields['custom_broker_accounts'].initial = user.custom_broker_accounts

    def get_broker_account_choices(self, user):
        account_choices = [
            ('General', (('All accounts', 'All accounts'),)),
            ('__SEPARATOR__', '__SEPARATOR__'),
        ]
        
        if user is not None:
            accounts = BrokerAccounts.objects.filter(broker__investor=user).order_by('name')
            user_accounts = [(account.name, account.name) for account in accounts]
            if user_accounts:
                account_choices.append(('Your Accounts', tuple(user_accounts)))
                account_choices.append(('__SEPARATOR__', '__SEPARATOR__'))
            
            user_groups = AccountGroup.objects.filter(user=user).order_by('name')
            group_choices = [(group.name, group.name) for group in user_groups]
            if group_choices:
                account_choices.append(('Account Groups', tuple(group_choices)))

        return account_choices

    def clean_digits(self):
        digits = self.cleaned_data.get('digits')
        if digits > 6:
            raise forms.ValidationError('The value for digits must be less than or equal to 6.')
        return digits

    def clean_custom_broker_accounts(self):
        accounts = self.cleaned_data.get('custom_broker_accounts')
        if accounts and not accounts.startswith(('All', 'group_')):
            try:
                BrokerAccounts.objects.get(id=accounts, broker__investor=self.instance)
            except BrokerAccounts.DoesNotExist:
                raise forms.ValidationError('Invalid broker account selected.')
        return accounts