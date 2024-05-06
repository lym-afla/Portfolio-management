from django import template

register = template.Library()

# Implement formatting for currencies
# @register.filter(name='currency_format')
# def currency_format(value, currency_digits):
#     """Format value as CUR."""
#     currency, digits = currency_digits.split(',')
#     match currency.upper():
#         case 'USD':
#             cur = '$'
#         case 'EUR':
#             cur = '€'
#         case 'GBP':
#             cur = '£'
#         case 'RUB':            
#             cur = '₽'
#         case default:
#             cur = currency.upper()
#     # digits = int(digits2)
#     if value < 0:
#         return f"({cur}{-value:,.{int(digits)}f})"
#     elif value == 0:
#         return "–"
#     else:
#         return f"{cur}{value:,.{int(digits)}f}"

@register.filter(name='mul')
def mul(value, arg):
    """Multiplies the arg and the value"""
    if isinstance(value, (int, float)) and isinstance(arg, (int, float)):
        return value * arg
    else:
        return value

# Getting items by key for Django template. Important for keys with spaces
@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter(name='format')
def format(value, format_string):
    """Formats the value by the provided format string."""
    return format_string.format(value)

@register.filter(name='div')
def div(value, arg):
    """Divides the value by the arg."""
    return value / arg