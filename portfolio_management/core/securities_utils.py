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
    securities_data = _get_securities_data(user, securities_data, effective_current_date, currency_target)
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
    securities = Assets.objects.filter(investor=user)
    if search:
        securities = securities.filter(name__icontains=search)
    return securities

def _get_securities_data(user, securities, effective_current_date, currency_target):
    securities_data = []
    for security in securities:
        security_data = {
            'id': security.id,
            'type': security.type,
            'ISIN': security.ISIN,
            'name': security.name,
            'first_investment': security.investment_date() or 'None',
            'currency': security.currency,
            'open_position': security.position(effective_current_date),
            'current_value': None,
            'realized': security.realized_gain_loss(effective_current_date)['all_time'],
            'unrealized': security.unrealized_gain_loss(effective_current_date),
            'capital_distribution': security.get_capital_distribution(effective_current_date),
            'irr': None
        }

        # Calculate current value and IRR if price is available
        price = security.price_at_date(effective_current_date)
        if price is not None:
            security_data['current_value'] = security_data['open_position'] * price.price
            security_data['irr'] = IRR(user.id, effective_current_date, security.currency, asset_id=security.id)

        securities_data.append(security_data)
    return securities_data

def _calculate_totals(securities_data, user, effective_current_date, currency_target):
    totals = {
        'current_value': sum(security['current_value'] for security in securities_data if security['current_value'] is not None),
        'realized': sum(security['realized'] for security in securities_data),
        'unrealized': sum(security['unrealized'] for security in securities_data),
        'capital_distribution': sum(security['capital_distribution'] for security in securities_data),
        'irr': IRR(user.id, effective_current_date, currency_target, asset_id=None)
    }
    return totals