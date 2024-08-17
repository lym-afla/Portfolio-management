from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from typing import Dict, List, Any, Optional, Union

from django.http import HttpRequest

from common.models import Brokers
from constants import ALL_TIME, YTD
from users.models import CustomUser
from .asset_utils import filter_assets
from .tables_utils import calculate_table_output
from .date_utils import get_date_range
from .formatting_utils import currency_format, format_table_data
from .pagination_utils import paginate_table
from .portfolio_utils import broker_group_to_ids

def get_positions_table_api(request: HttpRequest, is_closed: bool) -> Dict[str, Any]:
    """
    Get positions table data for API response.

    :param request: The request object
    :param is_closed: Boolean indicating if the positions are closed
    :return: Dictionary containing formatted portfolio data
    """
    data = request.data
    timespan = data.get('timespan', '')
    page = int(data.get('page', 1))
    items_per_page = int(data.get('items_per_page', 25))
    search = data.get('search', '')
    sort_by = data.get('sort_by', {})

    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()

    currency_target = user.default_currency
    number_of_digits = user.digits
    use_default_currency = user.use_default_currency_where_relevant
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    start_date, end_date = get_date_range(timespan, effective_current_date)

    assets = filter_assets(user, end_date, selected_brokers, is_closed, search)
    categories = _get_categories(is_closed)

    portfolio, portfolio_totals = calculate_table_output(
        user.id, assets, end_date, categories, use_default_currency,
        currency_target, selected_brokers, start_date, is_closed
    )

    portfolio = _sort_portfolio(portfolio, sort_by)
    paginated_portfolio, pagination_data = paginate_table(portfolio, page, items_per_page)

    formatted_portfolio = format_table_data(paginated_portfolio, currency_target, number_of_digits)
    formatted_totals = format_table_data(portfolio_totals, currency_target, number_of_digits)

    cash_balances = _get_cash_balances_for_api(user, timespan, effective_current_date) if not is_closed else None

    return {
        f'portfolio_{"closed" if is_closed else "open"}': formatted_portfolio,
        f'portfolio_{"closed" if is_closed else "open"}_totals': formatted_totals,
        'total_items': pagination_data['total_items'],
        'current_page': pagination_data['current_page'],
        'total_pages': pagination_data['total_pages'],
        'cash_balances': cash_balances,
    }


def _get_categories(is_closed: bool) -> List[str]:
    """
    Get the list of categories based on whether the position is closed or open.

    :param is_closed: Boolean indicating whether the position is closed
    :return: List of category names
    """
    common_categories = ['investment_date', 'realized_gl', 'capital_distribution', 'commission']
    closed_specific = ['exit_date']
    open_specific = ['current_value', 'unrealized_gl']
    return common_categories + (closed_specific if is_closed else open_specific)

def _sort_portfolio(portfolio: List[Dict[str, Any]], sort_by: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
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
            portfolio.sort(key=lambda x: get_sort_value(x, key), reverse=reverse)
    else:
        # Default sorting
        portfolio.sort(key=lambda x: get_sort_value(x, 'exit_date' if 'exit_date' in x else 'investment_date'), reverse=True)
    return portfolio

def _get_cash_balances_for_api(user: CustomUser, timespan: str, target_date: date) -> Dict[str, str]:
    """
    Get cash balances for API response.

    :param user: The user object
    :param timespan: The timespan for which to get balances
    :param date: The effective current date
    :return: Dictionary of formatted cash balances
    """
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    print("positions_utils 112", timespan)
    
    balance_date = target_date if timespan in (YTD, ALL_TIME) else date(int(timespan), 12, 31)
    
    aggregated_balances = defaultdict(Decimal)

    for broker_id in selected_brokers:
        try:
            broker = Brokers.objects.get(id=broker_id, investor=user)
            for currency, balance in broker.balance(balance_date).items():
                aggregated_balances[currency] += balance
        except Brokers.DoesNotExist:
            continue

    return {
        currency_format('', currency, 0): currency_format(balance, currency, user.digits)
        for currency, balance in aggregated_balances.items()
    }

def get_sort_value(item: Dict[str, Any], key: str) -> Union[Decimal, date, datetime, str]:
    """
    Get a comparable value for sorting based on the item and key.

    :param item: Dictionary containing the item data
    :param key: The key to sort by
    :return: A value that can be used for sorting
    """
    value = item.get(key)
    
    if value == 'N/R':
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
