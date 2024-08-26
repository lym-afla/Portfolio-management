from common.models import Brokers, Transactions
from .portfolio_utils import IRR, NAV_at_date
from .sorting_utils import sort_entries
from .pagination_utils import paginate_table
from .formatting_utils import currency_format, format_table_data
from datetime import datetime

def get_brokers_table_api(request):
    
    data = request.data
    page = int(data.get('page'))
    items_per_page = int(data.get('itemsPerPage'))
    search = data.get('search', '')
    sort_by = data.get('sortBy', {})

    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    # use_default_currency = user.use_default_currency_where_relevant
    # currency_target = None if use_default_currency else user.default_currency
    currency_target = user.default_currency
    number_of_digits = user.digits
    
    brokers_data = _filter_brokers(user, search)
    brokers_data = _get_brokers_data(user, brokers_data, effective_current_date, currency_target)
    brokers_data = sort_entries(brokers_data, sort_by)
    paginated_brokers, pagination_data = paginate_table(brokers_data, page, items_per_page)
    formatted_brokers = format_table_data(paginated_brokers, currency_target, number_of_digits)

    totals = _calculate_totals(brokers_data, user, effective_current_date, currency_target)
    totals = format_table_data(totals, currency_target, number_of_digits)

    return {
        'brokers': formatted_brokers,
        'totals': totals,
        'total_items': pagination_data['total_items'],
        'current_page': pagination_data['current_page'],
        'total_pages': pagination_data['total_pages'],
    }

def _filter_brokers(user, search):
    brokers = Brokers.objects.filter(investor=user)
    if search:
        brokers = brokers.filter(name__icontains=search)
    return brokers

def _get_brokers_data(user, brokers, effective_current_date, currency_target):
    brokers_data = []
    for broker in brokers:
        broker_data = {
            'id': broker.id,
            'name': broker.name,
            'country': broker.country,
            'currencies': ', '.join(broker.get_currencies()),
            'no_of_securities': sum(1 for security in broker.securities.filter(investor=user) if security.position(effective_current_date, [broker.id]) != 0),
            'first_investment': Transactions.objects.filter(investor=user, broker=broker).order_by('date').values_list('date', flat=True).first() or 'None',
            'nav': NAV_at_date(user.id, [broker.id], effective_current_date, currency_target, [])['Total NAV'],
            'cash_old': broker.balance(effective_current_date),
            'cash': {currency: currency_format(broker.balance(effective_current_date)[currency], currency, digits=0) for currency in broker.get_currencies()},
            'irr': IRR(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=[broker.id])
        }
        brokers_data.append(broker_data)
    return brokers_data

def _calculate_totals(brokers_data, user, effective_current_date, currency_target):
    totals = {
        'no_of_securities': sum(broker['no_of_securities'] for broker in brokers_data),
        'nav': sum(broker['nav'] for broker in brokers_data),
        'irr': IRR(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=[broker['id'] for broker in brokers_data])
    }
    return totals