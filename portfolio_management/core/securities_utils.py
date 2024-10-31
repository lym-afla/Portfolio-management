from decimal import Decimal

from django.shortcuts import get_object_or_404
from common.models import Assets
from core.portfolio_utils import IRR
from .sorting_utils import sort_entries
from .pagination_utils import paginate_table
from .formatting_utils import format_table_data
from datetime import datetime

def get_securities_table_api(request):
    data = request.data
    page = int(data.get('page'))
    items_per_page = int(data.get('itemsPerPage'))
    search = data.get('search', '')
    sort_by = data.get('sortBy', {})

    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    currency_target = user.default_currency
    number_of_digits = user.digits
    
    securities_data = _filter_securities(user, search)
    securities_data = _get_securities_data(user, securities_data, effective_current_date)
    securities_data = sort_entries(securities_data, sort_by)
    paginated_securities, pagination_data = paginate_table(securities_data, page, items_per_page)
    formatted_securities = format_table_data(paginated_securities, currency_target, number_of_digits)

    # totals = _calculate_totals(securities_data, user, effective_current_date, currency_target)
    # totals = format_table_data(totals, currency_target, number_of_digits)

    return {
        'securities': formatted_securities,
        # 'totals': totals,
        'total_items': pagination_data['total_items'],
        'current_page': pagination_data['current_page'],
        'total_pages': pagination_data['total_pages'],
    }

def _filter_securities(user, search):
    securities = Assets.objects.filter(investors__id=user.id)
    if search:
        securities = securities.filter(name__icontains=search)
    return securities

def _get_securities_data(user, securities, effective_current_date):
    securities_data = []
    for security in securities:
        security_data = {
            'id': security.id,
            'type': security.type,
            'ISIN': security.ISIN,
            'name': security.name,
            'first_investment': security.investment_date(user) or 'None',
            'currency': security.currency,
            'open_position': security.position(effective_current_date, user),
            'current_value': Decimal(0),
            'realized': security.realized_gain_loss(effective_current_date, user)['all_time']['total'],
            'unrealized': security.unrealized_gain_loss(effective_current_date, user)['total'],
            'capital_distribution': security.get_capital_distribution(effective_current_date, user),
            'irr': None
        }

        # Calculate current value and IRR if price is available
        price = security.price_at_date(effective_current_date)
        if price is not None:
            security_data['current_value'] = security_data['open_position'] * price.price
            security_data['irr'] = IRR(user.id, effective_current_date, security.currency, asset_id=security.id)

        securities_data.append(security_data)
    return securities_data

def get_security_detail(request, security_id):
    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    currency_target = user.default_currency
    number_of_digits = user.digits

    security = get_object_or_404(Assets, id=security_id, investors__id=user.id)
    
    security_data = {
        'id': security.id,
        'type': security.type,
        'ISIN': security.ISIN,
        'name': security.name,
        'first_investment': security.investment_date(user) or 'None',
        'currency': security.currency,
        'open_position': security.position(effective_current_date, user),
        'current_value': Decimal(0),
        'realized': security.realized_gain_loss(effective_current_date, user)['all_time']['total'],
        'unrealized': security.unrealized_gain_loss(effective_current_date, user)['total'],
        'capital_distribution': security.get_capital_distribution(effective_current_date, user),
        'irr': None,
        'data_source': security.data_source,
        'update_link': security.update_link,
        'yahoo_symbol': security.yahoo_symbol,
        'comment': security.comment,
    }

    # Calculate current value and IRR if price is available
    price = security.price_at_date(effective_current_date)
    if price is not None:
        security_data['current_value'] = security_data['open_position'] * price.price
        security_data['irr'] = IRR(user.id, effective_current_date, security.currency, asset_id=security.id)

    return format_table_data([security_data], currency_target, number_of_digits)[0]

def get_security_transactions(request, security_id):
    # Implement logic to fetch and return recent transactions data
    pass