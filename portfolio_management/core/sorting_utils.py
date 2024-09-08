from typing import List, Dict, Any, Optional, Union
from decimal import Decimal, InvalidOperation
from datetime import date, datetime

def sort_entries(portfolio: List[Dict[str, Any]], sort_by: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    Sort the portfolio based on the given sort criteria.

    :param portfolio: List of portfolio items to sort
    :param sort_by: Dictionary containing 'key' and 'order' for sorting
    :return: Sorted list of portfolio items
    """
    if sort_by:
        key = sort_by.get('key')
        order = sort_by.get('order')
        
        if key:
            reverse = order == 'desc'
            portfolio.sort(key=lambda x: _get_sort_value(x, key), reverse=reverse)
    else:
        # Check if portfolio exists and has elements
        if portfolio and len(portfolio) > 0:
            # Default sorting
            for key in portfolio[0].keys():
                if 'date' in key:
                    portfolio.sort(key=lambda x: _get_sort_value(x, key), reverse=False)
                    return portfolio  # Return immediately after sorting by the first date key found
    return portfolio

def _get_sort_value(item: Dict[str, Any], key: str) -> Union[Decimal, date, datetime, str]:
    """
    Get a comparable value for sorting based on the item and key.

    :param item: Dictionary containing the item data
    :param key: The key to sort by
    :return: A value that can be used for sorting
    """
    value = item.get(key)
    
    if value == 'N/R' or value is None:
        return Decimal('-Infinity')
    elif 'date' in key:
        return value if isinstance(value, (date, datetime)) else datetime.min
    elif isinstance(value, (int, float, Decimal)):
        return Decimal(value)
    elif isinstance(value, str):
        try:
            return Decimal(value.replace(',', ''))
        except InvalidOperation:
            return value.lower()
    else:
        return str(value).lower()

