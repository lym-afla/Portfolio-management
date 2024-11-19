from datetime import date, datetime
from decimal import Decimal
from collections import defaultdict
from typing import Dict, List, Any

from django.http import HttpRequest
from django.db.models import Q, Sum
from django.db.models.query import QuerySet

from common.models import Accounts, Assets
from users.models import CustomUser
from .sorting_utils import sort_entries
from .tables_utils import calculate_positions_table_output
from .formatting_utils import currency_format, format_table_data
from .pagination_utils import paginate_table
from .portfolio_utils import get_selected_account_ids

import logging
logger = logging.getLogger(__name__)

def get_positions_table_api(request: HttpRequest, is_closed: bool) -> Dict[str, Any]:
    """
    Get positions table data for API response.

    :param request: The request object
    :param is_closed: Boolean indicating if the positions are closed
    :return: Dictionary containing formatted portfolio data
    """
    data = request.data
    start_date = datetime.strptime(data.get('dateFrom', None), '%Y-%m-%d').date() if data.get('dateFrom') else None
    end_date = datetime.strptime(data.get('dateTo', None), '%Y-%m-%d').date() if data.get('dateTo') else None
    page = int(data.get('page'))
    items_per_page = int(data.get('itemsPerPage', 25))
    search = data.get('search', '')
    sort_by = data.get('sortBy', {})

    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    currency_target = user.default_currency
    number_of_digits = user.digits
    use_default_currency = user.use_default_currency_where_relevant
    selected_account_ids = get_selected_account_ids(
        user,
        user.selected_account_type,
        user.selected_account_id
    )

    # Handle empty dates
    if not end_date:
        end_date = effective_current_date

    assets = _filter_assets(user, end_date, selected_account_ids, is_closed, search)
    categories = _get_categories(is_closed)

    portfolio, portfolio_totals = calculate_positions_table_output(
        user.id, assets, end_date, categories, use_default_currency,
        currency_target, selected_account_ids, start_date, is_closed
    )

    portfolio = sort_entries(portfolio, sort_by)
    paginated_portfolio, pagination_data = paginate_table(portfolio, page, items_per_page)

    formatted_portfolio = format_table_data(paginated_portfolio, currency_target, number_of_digits)
    formatted_totals = format_table_data(portfolio_totals, currency_target, number_of_digits)

    cash_balances = _get_cash_balances_for_api(user, end_date) if not is_closed else None

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

def _get_cash_balances_for_api(user: CustomUser, target_date: date, selected_account_ids: List[int] = None) -> Dict[str, str]:
    """
    Get cash balances for API response.

    :param user: The user object
    :param target_date: The date for which to get balances
    :param selected_account_ids: The list of selected account IDs
    :return: Dictionary of formatted cash balances
    """
    selected_account_ids = (
        selected_account_ids
        or get_selected_account_ids(user, user.selected_account_type, user.selected_account_id)
    )
    logger.debug(f"Getting cash balances for accounts {selected_account_ids} on {target_date} for {user}")
    
    aggregated_balances = defaultdict(Decimal)
    
    for account_id in selected_account_ids:
        try:
            account = Accounts.objects.get(id=account_id, broker__investor=user)
            for currency, balance in account.balance(target_date).items():
                aggregated_balances[currency] += balance
            logger.debug(f"Aggregated balances after adding {account.name}: {aggregated_balances}")
        except Accounts.DoesNotExist:
            continue

    return {
        currency_format('', currency, 0): currency_format(balance, currency, user.digits)
        for currency, balance in aggregated_balances.items()
    }

def _filter_assets(user: CustomUser, end_date: date, selected_account_ids: List[int], 
                  is_closed: bool, search: str) -> QuerySet[Assets]:
    """
    Filter assets based on user, date, broker accounts, closed status, and search query.

    :param user: The user whose assets to filter
    :param end_date: The end date for transactions
    :param selected_account_ids: List of broker account IDs to filter by
    :param is_closed: Boolean indicating whether to filter for closed positions
    :param search: Search string for asset name or type
    :return: QuerySet of filtered Asset objects
    """
    base_query = Assets.objects.filter(
        investors__id=user.id,
        transactions__date__lte=end_date,
        transactions__account__id__in=selected_account_ids,
    ).annotate(
        total_quantity=Sum('transactions__quantity',
            filter=Q(
                transactions__date__lte=end_date,
                transactions__account__id__in=selected_account_ids
            )
        )
    ).distinct()

    if search:
        base_query = base_query.filter(Q(name__icontains=search) | Q(type__icontains=search))

    # Get all assets that match our base criteria
    assets = list(base_query)
    
    if is_closed:
        # Return assets that have at least one exit date and zero current position
        return [
            asset for asset in assets 
            if len(asset.exit_dates(end_date, user, selected_account_ids)) > 0 
            and asset.total_quantity == 0
        ]
    else:
        # Return assets with non-zero positions
        return [asset for asset in assets if asset.total_quantity != 0]
