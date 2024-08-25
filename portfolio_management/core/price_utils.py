from datetime import datetime
from django.db.models import Q
from common.models import Prices, Assets
from core.pagination_utils import paginate_table
from core.sorting_utils import sort_entries
from core.formatting_utils import format_table_data, currency_format

def get_prices_table_api(request):
    data = request.data
    start_date = data.get('startDate')
    end_date = data.get('endDate')
    page = int(data.get('page', 1))
    items_per_page = int(data.get('itemsPerPage', 25))
    search = data.get('search', '')
    sort_by = data.get('sortBy', {})
    selected_asset_types = data.get('assetTypes', [])
    selected_broker = data.get('broker')
    selected_securities = data.get('securities', [])

    user = request.user
    currency_target = user.default_currency
    number_of_digits = user.digits

    prices = _filter_prices(user, start_date, end_date, selected_asset_types, selected_broker, selected_securities, search)
    
    prices_data = [
        {
            'id': price.id,
            'date': price.date,
            'security__name': price.security.name,
            'security__type': price.security.type,
            'security__currency': price.security.currency,
            'price': f"{price.price:,.{2}f}"
        }
        for price in prices
    ]

    sorted_prices = sort_entries(prices_data, sort_by)
    paginated_prices, pagination_data = paginate_table(sorted_prices, page, items_per_page)
    formatted_prices = format_table_data(paginated_prices, currency_target, number_of_digits)
    
    return {
        'prices': formatted_prices,
        'total_items': pagination_data['total_items'],
        'current_page': pagination_data['current_page'],
        'total_pages': pagination_data['total_pages'],
    }

def _filter_prices(user, start_date, end_date, selected_asset_types, selected_broker, selected_securities, search):
    prices_query = Prices.objects.filter(security__investor=user).select_related('security')

    if start_date:
        prices_query = prices_query.filter(date__gte=start_date)
    if end_date:
        prices_query = prices_query.filter(date__lte=end_date)
    if selected_asset_types:
        prices_query = prices_query.filter(security__type__in=selected_asset_types)
    if selected_broker:
        prices_query = prices_query.filter(security__brokers__id=selected_broker)
    if selected_securities:
        prices_query = prices_query.filter(security__id__in=selected_securities)
    if search:
        prices_query = prices_query.filter(
            Q(security__name__icontains=search) | 
            Q(security__type__icontains=search)
        )

    return prices_query.order_by('date')