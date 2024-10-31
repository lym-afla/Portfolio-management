from datetime import date, datetime
from decimal import Decimal
from collections import defaultdict
from typing import Dict, List, Any

from django.http import HttpRequest
from django.db.models import Q, Sum
from django.db.models.functions import Abs

from common.models import Brokers, Assets
from constants import ALL_TIME, YTD
from users.models import CustomUser
from .sorting_utils import sort_entries
from .tables_utils import calculate_positions_table_output
from .date_utils import get_date_range
from .formatting_utils import currency_format, format_table_data
from .pagination_utils import paginate_table
from .portfolio_utils import broker_group_to_ids
import logging

from constants import TOLERANCE

import time

logger = logging.getLogger(__name__)

def get_positions_table_api(request: HttpRequest, is_closed: bool) -> Dict[str, Any]:
    """
    Get positions table data for API response.

    :param request: The request object
    :param is_closed: Boolean indicating if the positions are closed
    :return: Dictionary containing formatted portfolio data
    """
    start_time = time.time()  # Start timing

    data = request.data
    # timespan = data.get('timespan', '')
    start_date = datetime.strptime(data.get('dateFrom', None), '%Y-%m-%d').date() if data.get('dateFrom') else None
    end_date = datetime.strptime(data.get('dateTo', None), '%Y-%m-%d').date() if data.get('dateTo') else None
    page = int(data.get('page'))
    print("positions_utils. 39", data.get('itemsPerPage'))
    items_per_page = int(data.get('itemsPerPage', 25))
    search = data.get('search', '')
    sort_by = data.get('sortBy', {})

    logging.info("positions_utils. 43", start_date, end_date, page, items_per_page, search, sort_by)

    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()

    currency_target = user.default_currency
    number_of_digits = user.digits
    use_default_currency = user.use_default_currency_where_relevant
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    # Handle empty dates
    if not end_date:
        end_date = effective_current_date

    # if not start_date:
    #     start_date = date(end_date.year, 1, 1)  # Set start date to the beginning of the current year

    # print("positions_utils. 53", start_date, end_date)

    # start_date, end_date = get_date_range(timespan, effective_current_date)
    # print("positions_utils. 58", start_date, end_date)

    # Timing the asset filtering
    filter_start_time = time.time()
    assets = _filter_assets(user, end_date, selected_brokers, is_closed, search)
    filter_duration = time.time() - filter_start_time
    print(f"Asset filtering took {filter_duration:.4f} seconds")

    categories = _get_categories(is_closed)

    # Timing the portfolio calculation
    calculation_start_time = time.time()
    portfolio, portfolio_totals = calculate_positions_table_output(
        user.id, assets, end_date, categories, use_default_currency,
        currency_target, selected_brokers, start_date, is_closed
    )
    calculation_duration = time.time() - calculation_start_time
    print(f"Portfolio calculation took {calculation_duration:.4f} seconds")

    portfolio = sort_entries(portfolio, sort_by)
    paginated_portfolio, pagination_data = paginate_table(portfolio, page, items_per_page)

    formatted_portfolio = format_table_data(paginated_portfolio, currency_target, number_of_digits)
    formatted_totals = format_table_data(portfolio_totals, currency_target, number_of_digits)

    cash_balances = _get_cash_balances_for_api(user, end_date) if not is_closed else None
    
    total_duration = time.time() - start_time
    print(f"Total processing time for get_positions_table_api: {total_duration:.4f} seconds")

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

def _get_cash_balances_for_api(user: CustomUser, target_date: date, selected_brokers: List[int] = None) -> Dict[str, str]:
    """
    Get cash balances for API response.

    :param user: The user object
    :param timespan: The timespan for which to get balances
    :param date: The effective current date
    :return: Dictionary of formatted cash balances
    """
    selected_brokers = selected_brokers or broker_group_to_ids(user.custom_brokers, user)

    logger.info(f"Getting cash balances for {selected_brokers} on {target_date} for {user}")
    
    aggregated_balances = defaultdict(Decimal)
    logger.debug(f"Aggregated balances: {aggregated_balances}")

    for broker_id in selected_brokers:
        try:
            broker = Brokers.objects.get(id=broker_id, investor=user)
            logger.debug(f"Broker balances: {broker.balance(target_date)}")
            for currency, balance in broker.balance(target_date).items():
                aggregated_balances[currency] += balance
            logger.debug(f"Aggregated balances after adding {broker.name}: {aggregated_balances}")
        except Brokers.DoesNotExist:
            continue
    logger.debug(f"Final aggregated balances: {aggregated_balances}")

    return {
        currency_format('', currency, 0): currency_format(balance, currency, user.digits)
        for currency, balance in aggregated_balances.items()
    }

def _filter_assets(user, end_date, selected_brokers, is_closed: bool, search: str) -> List[Assets]:
    """
    Filter assets based on user, date, brokers, closed status, and search query.

    :param user: The user whose assets to filter
    :param end_date: The end date for transactions
    :param selected_brokers: List of broker IDs to filter by
    :param is_closed: Boolean indicating whether to filter for closed positions
    :param search: Search string for asset name or type
    :return: List of filtered Asset objects
    """
    assets = Assets.objects.filter(
        investors__id=user.id,
        transactions__date__lte=end_date,
        transactions__broker_id__in=selected_brokers,
        transactions__quantity__isnull=False
    ).distinct()

    if search:
        assets = assets.filter(Q(name__icontains=search) | Q(type__icontains=search))

    if is_closed:
        return [asset for asset in assets if len(asset.exit_dates(end_date, user)) != 0]
    else:
        return assets.annotate(
            abs_total_quantity=Abs(Sum('transactions__quantity'))
        ).exclude(
            abs_total_quantity__lt=TOLERANCE
        )
