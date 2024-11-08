from common.models import BrokerAccounts, Transactions
from .portfolio_utils import IRR, NAV_at_date
from .sorting_utils import sort_entries
from .pagination_utils import paginate_table
from .formatting_utils import currency_format, format_table_data
from datetime import datetime
from django.db import models

def get_accounts_table_api(request):
    data = request.data
    
    page = int(data.get('page'))
    items_per_page = int(data.get('itemsPerPage'))
    search = data.get('search', '')
    sort_by = data.get('sortBy', {})

    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    currency_target = user.default_currency
    number_of_digits = user.digits
    
    accounts_data = _filter_broker_accounts(user, search)
    accounts_data = _get_broker_accounts_data(user, accounts_data, effective_current_date, currency_target)
    accounts_data = sort_entries(accounts_data, sort_by)
    paginated_accounts, pagination_data = paginate_table(accounts_data, page, items_per_page)
    formatted_accounts = format_table_data(paginated_accounts, currency_target, number_of_digits)

    totals = _calculate_totals(accounts_data, user, effective_current_date, currency_target)
    totals = format_table_data(totals, currency_target, number_of_digits)

    return {
        'accounts': formatted_accounts,
        'totals': totals,
        'total_items': pagination_data['total_items'],
        'current_page': pagination_data['current_page'],
        'total_pages': pagination_data['total_pages'],
    }

def _filter_broker_accounts(user, search):
    accounts = BrokerAccounts.objects.filter(broker__investor=user, is_active=True)
    if search:
        accounts = accounts.filter(
            models.Q(name__icontains=search) |
            models.Q(broker__name__icontains=search)
        )
    return accounts

def _get_broker_accounts_data(user, accounts, effective_current_date, currency_target):
    accounts_data = []
    for account in accounts:
        account_data = {
            'id': account.id,
            'name': account.name,
            'broker_name': account.broker.name,
            'country': account.broker.country,
            'currencies': ', '.join(account.get_currencies()),
            'no_of_securities': sum(1 for security in account.securities.filter(investors=user) 
                                  if security.position(effective_current_date, user, [account.id]) != 0),
            'first_investment': Transactions.objects.filter(
                broker_account=account,
                broker_account__broker__investor=user
            ).order_by('date').values_list('date', flat=True).first() or 'None',
            'nav': NAV_at_date(user.id, tuple([account.id]), effective_current_date, currency_target)['Total NAV'],
            'cash': {currency: currency_format(account.balance(effective_current_date)[currency], currency, digits=0) 
                    for currency in account.get_currencies()},
            'irr': IRR(user.id, effective_current_date, currency_target, asset_id=None, broker_account_ids=[account.id])
        }
        accounts_data.append(account_data)
    return accounts_data

def _calculate_totals(accounts_data, user, effective_current_date, currency_target):
    totals = {
        'no_of_securities': sum(account['no_of_securities'] for account in accounts_data),
        'nav': sum(account['nav'] for account in accounts_data),
        'irr': IRR(user.id, effective_current_date, currency_target, asset_id=None, 
                  broker_account_ids=[account['id'] for account in accounts_data])
    }
    return totals