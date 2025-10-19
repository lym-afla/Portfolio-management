"""Custom filters for templates."""

from django import template

register = template.Library()


@register.filter(name="mul")
def mul(value, arg):
    """Multiplies the arg and the value."""
    if isinstance(value, (int, float)) and isinstance(arg, (int, float)):
        return value * arg
    else:
        return value


# Getting items by key for Django template. Important for keys with spaces
@register.filter
def get_item(dictionary, key):
    """Get item by key for Django template."""
    return dictionary.get(key)


@register.filter(name="format")
def format(value, format_string):
    """Format the value by the provided format string."""
    return format_string.format(value)


@register.filter(name="div")
def div(value, arg):
    """Divides the value by the arg."""
    return value / arg
