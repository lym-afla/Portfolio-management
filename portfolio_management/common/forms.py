import logging

from django import forms

from users.models import CustomUser

logger = logging.getLogger(__name__)


class GroupedSelect(forms.Select):
    def optgroups(self, name, value, attrs=None):
        groups = []
        has_selected = False

        for index, (group_name, group_choices) in enumerate(self.choices):
            if group_choices == "__SEPARATOR__":
                continue
            subgroup = []
            for option_value, option_label in group_choices:
                selected = self.check_selected(option_value, value)
                if selected:
                    has_selected = True
                selected = has_selected and option_value in value
                subgroup.append(
                    self.create_option(
                        name, option_value, option_label, selected, index, attrs=attrs
                    )
                )
            groups.append((group_name, subgroup, index))

        return groups

    # def render_options(self, *args):
    #     output = super().render_options(*args)
    #     return output.replace('&lt;hr&gt;', '<hr>')

    def check_selected(self, option_value, value):
        if isinstance(value, (list, tuple)):
            return option_value in value
        return option_value == value


class DashboardForm(forms.ModelForm):
    table_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), label="Date")

    class Meta:
        model = CustomUser
        fields = ["default_currency", "digits"]
        labels = {
            "default_currency": "Currency",
            "digits": "Number of digits",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_currency"].choices = [
            (choice[0], f"{choice[1]} ({choice[0]})")
            for choice in CustomUser._meta.get_field("default_currency").choices
            if choice[0]
        ]
