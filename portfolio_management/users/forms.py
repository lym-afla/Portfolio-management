from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from constants import CURRENCY_CHOICES, NAV_BARCHART_CHOICES
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
    # use_default_currency_for_all_data = forms.BooleanField(
    #     widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    #     label='Use default currency for data where relevant?',
    #     required=False
    # )
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
    digits = forms.IntegerField(
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        label='Digits for tables'
    )
    NAV_barchart_default_breakdown = forms.ChoiceField(
        choices=NAV_BARCHART_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Default NAV timeline breakdown'
    )
    
    class Meta:
        model = CustomUser
        fields = ['default_currency', 'use_default_currency_where_relevant', 'chart_frequency', 'chart_timeline', 'digits', 'NAV_barchart_default_breakdown']
        widgets = {
            'use_default_currency_where_relevant': forms.CheckboxInput(attrs={'class': 'form-check-input ml-0'}),
            # 'chart_frequency': forms.Select(attrs={'class': 'form-select'}),
        #     'chart_timeline': forms.Select(attrs={'class': 'form-select'})
        }
        labels = {
            'digits': 'Number of digits',
        #     'chart_frequency': 'Chart frequency:',
        #     'chart_timeline': 'Chart timeline:',
        }

    def clean_digits(self):
        digits = self.cleaned_data.get('digits')
        if digits > 6:
            raise forms.ValidationError('The value for digits must be less than or equal to 6.')
        return digits