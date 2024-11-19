from common.models import Brokers, Assets, Transactions
from .portfolio_utils import IRR, NAV_at_date
from .sorting_utils import sort_entries
from .pagination_utils import paginate_table
from .formatting_utils import format_table_data
from datetime import datetime
from django.db import models
from decimal import Decimal

import logging

logger = logging.getLogger(__name__)

def get_brokers_table_api(request):
    """Get brokers table data with pagination, sorting, and search"""
    data = request.data
    
    page = int(data.get('page'))
    items_per_page = int(data.get('itemsPerPage'))
    search = data.get('search', '')
    sort_by = data.get('sortBy', {})

    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
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
        'items': formatted_brokers,
        'totals': totals,
        'total_items': pagination_data['total_items'],
        'current_page': pagination_data['current_page'],
        'total_pages': pagination_data['total_pages'],
    }

def _filter_brokers(user, search):
    """Filter brokers based on search criteria"""
    brokers = Brokers.objects.filter(investor=user)
    if search:
        brokers = brokers.filter(
            models.Q(name__icontains=search) |
            models.Q(country__icontains=search) |
            models.Q(comment__icontains=search)
        )
    return brokers

def _get_brokers_data(user, brokers, effective_current_date, currency_target):
    """Get detailed data for each broker"""
    brokers_data = []
    
    # Get all broker account IDs upfront
    accounts = {
        broker.id: list(broker.accounts.values_list('id', flat=True))
        for broker in brokers
    }

    # Get all assets with non-zero positions at effective_current_date
    active_assets = Assets.objects.filter(
        transactions__account__in=[
            acc_id for acc_ids in accounts.values() for acc_id in acc_ids
        ],
        transactions__date__lte=effective_current_date
    ).distinct()

    logger.info(f"Active assets: {active_assets}")

    # # Calculate positions for active assets
    # active_assets_with_positions = [
    #     asset for asset in active_assets
    #     if asset.position(effective_current_date, user, account_ids=accounts[asset.account.id]) != 0
    # ]

    # logger.info(f"Active assets with positions: {active_assets_with_positions}")

    for broker in brokers:
        account_ids = accounts[broker.id]
        accounts_count = len(account_ids)

        if accounts_count > 0:
            nav_data = NAV_at_date(
                user.id,
                tuple(account_ids),
                effective_current_date,
                currency_target
            )
            total_nav = nav_data['Total NAV']
            cash = nav_data.get('Cash', {}).get(currency_target, Decimal('0'))
            
            # Count securities with non-zero positions for this broker
            securities_count = sum(
                1 for asset in active_assets
                if asset.transactions.filter(
                    account_id__in=account_ids
                ).exists() and asset.position(
                    effective_current_date,
                    user,
                    account_ids=account_ids
                ) != 0
            )
            
            irr = IRR(
                user.id,
                effective_current_date,
                currency_target,
                account_ids=account_ids
            )
        else:
            total_nav = Decimal('0')
            cash = Decimal('0')
            securities_count = 0
            irr = Decimal('0')

        broker_data = {
            'id': broker.id,
            'name': broker.name,
            'country': broker.country,
            'comment': broker.comment,
            'no_of_accounts': accounts_count,
            'no_of_securities': securities_count,
            'first_investment': Transactions.objects.filter(
                account__in=account_ids,
                investor=user
            ).order_by('date').values_list('date', flat=True).first() or 'None',
            'nav': total_nav,
            'cash': cash,
            'irr': irr
        }
        brokers_data.append(broker_data)
    return brokers_data

def _calculate_totals(brokers_data, user, effective_current_date, currency_target):
    """Calculate totals for all brokers"""
    account_ids = []
    for broker in Brokers.objects.filter(investor=user):
        account_ids.extend(list(broker.accounts.values_list('id', flat=True)))

    # Calculate total NAV and cash
    if account_ids:
        nav_data = NAV_at_date(
            user.id,
            tuple(account_ids),
            effective_current_date,
            currency_target
        )
        total_nav = nav_data['Total NAV']
        total_cash = nav_data.get('Cash', {}).get(currency_target, Decimal('0'))
    else:
        total_nav = Decimal('0')
        total_cash = Decimal('0')

    totals = {
        'no_of_accounts': sum(broker['no_of_accounts'] for broker in brokers_data),
        'nav': total_nav,
        'cash': total_cash,
        'irr': IRR(
            user.id, 
            effective_current_date, 
            currency_target, 
            account_ids=account_ids
        ) if account_ids else Decimal('0')
    }
    return totals