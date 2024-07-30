from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from constants import BROKER_GROUPS, CURRENCY_CHOICES, NAV_BARCHART_CHOICES
from common.models import Brokers
from common.forms import GroupedSelect
from users.models import CustomUser

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
    # custom_brokers = forms.MultipleChoiceField(
    #     choices=[],
    #     widget=forms.SelectMultiple(attrs={'class': 'selectpicker show-tick', 'data-actions-box': 'true', 'data-width': '100%', 'title': 'Choose broker', 'data-selected-text-format': 'count', 'id': 'inputBrokers'}),
    #     label='Brokers'
    # )

    custom_brokers = forms.ChoiceField(
        choices=[],
        widget=GroupedSelect(attrs={'class': 'form-select', 'id': 'inputBrokers'}),
        label='Brokers',
    )
    
    class Meta:
        model = CustomUser
        fields = ['custom_brokers', 'default_currency', 'use_default_currency_where_relevant', 'chart_frequency', 'chart_timeline', 'digits', 'NAV_barchart_default_breakdown']
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
        # Set choices dynamically for broker, security, and type fields
        # Initialize broker choices
        broker_choices = [
            ('General', (('All brokers', 'All brokers'),)),
            ('__SEPARATOR__', '__SEPARATOR__'),
        ]
        
        if user is not None:
            brokers = Brokers.objects.filter(investor=user).order_by('name')
            user_brokers = [(broker.name, broker.name) for broker in brokers]
            if user_brokers:
                broker_choices.append(('Your Brokers', tuple(user_brokers)))
                broker_choices.append(('__SEPARATOR__', '__SEPARATOR__'))
        
        # Add BROKER_GROUPS keys
        broker_choices.append(('Broker Groups', tuple((group, group) for group in BROKER_GROUPS.keys())))

        self.fields['custom_brokers'].choices = broker_choices
        
        if user is not None:
            self.fields['custom_brokers'].initial = user.custom_brokers

    def clean_digits(self):
        digits = self.cleaned_data.get('digits')
        if digits > 6:
            raise forms.ValidationError('The value for digits must be less than or equal to 6.')
        return digits