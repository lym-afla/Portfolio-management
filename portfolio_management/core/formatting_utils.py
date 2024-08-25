import datetime
from decimal import Decimal
from typing import Union, Dict, List, Any
from django.core.paginator import Page
from babel.numbers import get_currency_symbol
from constants import CURRENCY_CHOICES

NOT_RELEVANT = 'N/R'

def format_table_data(data: Union[List[Dict[str, Any]], Dict[str, Any], Page], currency_target: str, number_of_digits: int) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Format table data based on the input type.

    :param data: Input data to be formatted
    :param currency_target: Target currency for formatting
    :param number_of_digits: Number of digits for rounding
    :return: Formatted data
    """
    if isinstance(data, list):
        return [
            {k: format_value(v, k, currency_target, number_of_digits) for k, v in position.items()}
            for position in data
        ]
    elif isinstance(data, dict):
        return {
            k: format_value(v, k, currency_target, number_of_digits)
            for k, v in data.items()
        }
    elif isinstance(data, Page):
        return [
            {k: format_value(v, k, currency_target, number_of_digits) for k, v in position.items()}
            for position in data.object_list
        ]
    else:
        raise ValueError(f"Input data must be either a list of dictionaries, a single dictionary, or a Page object. We have got: {type(data)}")

def format_value(value: Any, key: str, currency: str, digits: int) -> Any:
    """
    Format a single value based on its key and type.

    :param value: Value to be formatted
    :param key: Key associated with the value
    :param currency: Currency for formatting
    :param digits: Number of digits for rounding
    :return: Formatted value
    """
    if value == NOT_RELEVANT:
        return value
    if isinstance(value, dict):
        return {k: format_value(v, k, currency, digits) for k, v in value.items()}
    if 'date' in key or key == 'first_investment' and isinstance(value, datetime.date):
        return value.strftime('%d-%b-%y') if value else None
    elif 'percentage' in key or 'share' in key or 'irr' in key:
        return format_percentage(value, digits)
    elif key in ['current_position', 'open_position', 'quantity']:
        return f"{value:,.{digits}f}"
    elif key in ['id', 'no_of_securities']:
        return value
    elif isinstance(value, (Decimal, float, int)):
        return currency_format(value, currency, digits)
    else:
        return value

def currency_format(value: Union[Decimal, float, int, None] = None, currency: str = None, digits: int = 2) -> str:
    """
    Format value as currency or return currency symbol.
    If only currency is provided, return the currency symbol.

    :param value: Value to be formatted
    :param currency: Currency code
    :param digits: Number of digits for rounding
    :return: Formatted currency string or symbol
    """
    if currency is None:
        return "N/A"

    # Get the currency symbol using Babel first
    symbol = get_currency_symbol(currency.upper(), locale='en_US')
    
    # If the symbol is the same as the currency code, it means the currency was not recognized by Babel
    if symbol == currency.upper():
        # Fall back to CURRENCY_CHOICES
        symbol = dict(CURRENCY_CHOICES).get(currency.upper(), currency.upper())

    # If no value is provided, return only the symbol
    if value is None:
        return symbol

    try:
        value = Decimal(value)
        if value < 0:
            return f"({symbol}{abs(value):,.{digits}f})"
        elif value == 0:
            return "–"
        else:
            return f"{symbol}{value:,.{digits}f}"
    except:
        return symbol

def format_percentage(value: Union[float, int, None], digits: int = 0) -> str:
    """
    Format a value as a percentage.

    :param value: Value to be formatted as percentage
    :param digits: Number of digits for rounding
    :return: Formatted percentage string
    """
    if value is None:
        return "NA"
    
    try:
        if value < 0:
            return f"({float(-value * 100):.{int(digits)}f}%)"
        elif value == 0:
            return "–"
        else:
            return f"{float(value * 100):.{int(digits)}f}%"
    except (TypeError, ValueError):
        return str(value)