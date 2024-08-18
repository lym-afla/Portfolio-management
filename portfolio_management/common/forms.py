from django import forms
from common.models import Brokers
from constants import BROKER_GROUPS
from users.models import CustomUser

import logging

logger = logging.getLogger(__name__)

class GroupedSelect(forms.Select):
    def optgroups(self, name, value, attrs=None):
        groups = []
        has_selected = False

        for index, (group_name, group_choices) in enumerate(self.choices):
            if group_choices == '__SEPARATOR__':
                continue
            subgroup = []
            for option_value, option_label in group_choices:
                selected = self.check_selected(option_value, value)
                if selected:
                    has_selected = True
                selected = has_selected and option_value in value
                subgroup.append(self.create_option(name, option_value, option_label, selected, index, attrs=attrs))
            groups.append((group_name, subgroup, index))

        return groups

    # def render_options(self, *args):
    #     output = super().render_options(*args)
    #     return output.replace('&lt;hr&gt;', '<hr>')
    
    def check_selected(self, option_value, value):
        if isinstance(value, (list, tuple)):
            return option_value in value
        return option_value == value
    
class DashboardForm_old_setup(forms.ModelForm):

    custom_brokers = forms.ChoiceField(
        choices=[],
        widget=GroupedSelect(attrs={'class': 'form-select', 'id': 'inputDashboardBrokers'}),
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
            initial_value = user.custom_brokers
            
            # Check if the initial value is in the choices
            all_choices = [choice[0] for group, choices in broker_choices for choice in choices if choices != '__SEPARATOR__']
            if initial_value in all_choices:
                self.fields['custom_brokers'].initial = initial_value
            else:
                logger.warning(f"Dashboard form. Initial value '{initial_value}' not found in choices. Defaulting to 'All'.")
                self.fields['custom_brokers'].initial = 'All'

    def clean_custom_brokers(self):
        value = self.cleaned_data['custom_brokers']
        logger.debug(f"Cleaned value for custom_brokers: {value}")
        return value


class DashboardForm(forms.ModelForm):
    table_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label='Date'
    )

    class Meta:
        model = CustomUser
        fields = ['default_currency', 'digits']
        labels = {
            'default_currency': 'Currency',
            'digits': 'Number of digits',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['default_currency'].choices = [(choice[0], f"{choice[1]} ({choice[0]})") for choice in CustomUser._meta.get_field('default_currency').choices if choice[0]]