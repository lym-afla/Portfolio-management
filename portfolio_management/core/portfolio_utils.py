from collections import defaultdict
from datetime import date, timedelta
import datetime
from functools import lru_cache
from django.db.models import Sum, QuerySet, Q, Prefetch
from pyxirr import xirr
from common.models import FX, AnnualPerformance, Assets, Transactions, BrokerAccounts, Brokers
from users.models import AccountGroup
from functools import lru_cache

import logging
logger = logging.getLogger('dashboard')

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Tuple, Union
import logging

from core.formatting_utils import format_percentage
from users.models import CustomUser

def _portfolio_at_date(user_id: int, to_date: date, broker_account_ids: List[int]) -> QuerySet[Assets]:
    """
    Get the portfolio assets for a user at a specific date for given broker accounts.

    :param user_id: The ID of the user
    :param to_date: The date to calculate the portfolio for
    :param broker_account_ids: List of broker account IDs to filter by
    :return: QuerySet of Assets with non-zero total quantity
    """
    if not broker_account_ids:
        return Assets.objects.none()
    
    return Assets.objects.filter(
        investors__id=user_id,
        transactions__date__lte=to_date, 
        transactions__broker_account_id__in=broker_account_ids
    ).annotate(
        total_quantity=Sum('transactions__quantity', 
            filter=Q(
                transactions__date__lte=to_date,
                transactions__broker_account_id__in=broker_account_ids
            )
        )
    ).exclude(total_quantity=0).distinct()

# Get all the broker accounts associated with a given security
def get_broker_accounts_for_security(user_id: int, security_id: int) -> QuerySet[BrokerAccounts]:
    """
    Get all broker accounts associated with a given security for a user.

    :param user_id: The ID of the user
    :param security_id: The ID of the security
    :return: QuerySet of BrokerAccounts
    """
    return BrokerAccounts.objects.filter(
        broker__investor__id=user_id,
        transactions__security_id=security_id
    ).distinct()

@lru_cache(maxsize=None)
def get_fx_rate(currency: str, target_currency: str, date: date, user: Optional[int] = None) -> Decimal:
    return FX.get_rate(currency, target_currency, date, user)['FX']

# Create one dictionary from two. And add values for respective keys if keys present on both dictionaries
def merge_dictionaries(dict_1: dict, dict_2: dict) -> dict:
    dict_3 = dict_1.copy()  # Create a copy of dict_1
    for key, value in dict_2.items():
        dict_3[key] = dict_3.get(key, 0) + value  # Add values for common keys or set new values if key is not in dict_3
    return dict_3


# Calculate NAV breakdown for selected broker accounts at certain date and in selected currency
@lru_cache(maxsize=None)
def NAV_at_date(user_id: int, broker_account_ids: Tuple[int], date: date, target_currency: str, breakdown: Tuple[str] = ()) -> Dict:
    broker_account_ids = list(broker_account_ids)  # Convert tuple back to list for internal use
    breakdown = list(breakdown)  # Convert tuple back to list for internal use
    
    # Initialize analysis with default structure
    analysis = defaultdict(lambda: defaultdict(Decimal))
    analysis['Total NAV'] = Decimal(0)
    
    # Initialize breakdown categories even if empty
    if 'asset_type' in breakdown:
        analysis['asset_type'] = defaultdict(Decimal)
    if 'currency' in breakdown:
        analysis['currency'] = defaultdict(Decimal)
    if 'asset_class' in breakdown:
        analysis['asset_class'] = defaultdict(Decimal)
    if 'account' in breakdown:
        analysis['account'] = defaultdict(Decimal)

    # If no broker accounts, return empty structure
    if not broker_account_ids:
        return dict(analysis)

    portfolio = _portfolio_at_date(user_id, date, broker_account_ids)
    portfolio_broker_accounts = BrokerAccounts.objects.filter(
        broker__investor__id=user_id,
        id__in=broker_account_ids
    )

    if not portfolio.exists() and not portfolio_broker_accounts.exists():
        return analysis

    item_type = {'asset_type': 'type', 'currency': 'currency', 'asset_class': 'exposure'}

    for security in portfolio:
        security_price = security.price_at_date(date, target_currency)
        if security_price is not None:
            security_price = security_price.price
        else:
            security_price = security.calculate_buy_in_price(date, user_id, target_currency, broker_account_ids)
        
        for broker_account in portfolio_broker_accounts:
            broker_account_position = security.position(date, user_id, [broker_account.id])
            broker_account_value = Decimal(broker_account_position * security_price)
            analysis['Total NAV'] += broker_account_value

            if 'account' in breakdown:
                analysis['account'][broker_account.name] += broker_account_value
            else:
                for breakdown_type in breakdown:
                    key = getattr(security, item_type[breakdown_type])
                    analysis[breakdown_type][key] += broker_account_value

    # Handle cash balances
    for broker_account in portfolio_broker_accounts:
        broker_balance = broker_account.balance(date)
        for currency, balance in broker_balance.items():
            fx_rate = get_fx_rate(currency, target_currency, date)
            converted_balance = balance * fx_rate
            analysis['Total NAV'] += converted_balance
            
            if 'account' in breakdown:
                analysis['account'][broker_account.name] += converted_balance
            if 'currency' in breakdown:
                analysis['currency'][currency] += converted_balance
            if 'asset_type' in breakdown:
                analysis['asset_type']['Cash'] += converted_balance
            if 'asset_class' in breakdown:
                analysis['asset_class']['Cash'] += converted_balance

    return dict(analysis)

# Helper for IRR calculation
def _calculate_portfolio_value(user_id: int, date: date, currency: Optional[str] = None, 
                            asset_id: Optional[int] = None, broker_account_ids: Optional[List[int]] = None) -> Decimal:
    if asset_id is None:
        portfolio_value = NAV_at_date(user_id, tuple(broker_account_ids), date, currency)['Total NAV']
    else:
        asset = Assets.objects.get(id=asset_id, investors__id=user_id)
        try:
            portfolio_value = Decimal(asset.price_at_date(date, currency).price * 
                                   asset.position(date, user_id, broker_account_ids))
        except:
            portfolio_value = Decimal(0)

    return portfolio_value

def calculate_portfolio_cash(user_id: int, broker_account_ids: List[int], date: date, target_currency: str) -> Decimal:
    """
    Calculate the total cash balance for a user's portfolio across multiple broker accounts.

    :param user_id: The ID of the user
    :param broker_account_ids: List of broker account IDs to include in the calculation
    :param date: The date for which to calculate the cash balance
    :param target_currency: The currency to convert all cash balances to
    :return: The total cash balance as a Decimal
    """
    portfolio_accounts = BrokerAccounts.objects.filter(
        broker__investor__id=user_id,
        id__in=broker_account_ids
    )
    
    cash_balance = {}
    for account in portfolio_accounts:
        cash_balance = merge_dictionaries(cash_balance, account.balance(date))

    cash = sum(
        balance * get_fx_rate(currency, target_currency, date)
        for currency, balance in cash_balance.items()
    )

    return Decimal(cash).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

MAX_IRR = Decimal('2')
IRR_PRECISION = Decimal('0.0001')

def IRR(user_id: int, date: date, currency: Optional[str] = None, asset_id: Optional[int] = None, 
        broker_account_ids: Optional[List[int]] = None, start_date: Optional[date] = None, cached_nav: Optional[Decimal] = None) -> Union[Decimal, str]:
    """
    Calculate the Internal Rate of Return (IRR) for a given portfolio or asset.

    :param user_id: The ID of the user
    :param date: The end date for IRR calculation
    :param currency: The currency to use for calculations (optional)
    :param asset_id: The ID of the specific asset to calculate IRR for (optional)
    :param broker_account_ids: List of broker account IDs to include in the calculation (optional)
    :param start_date: The start date for IRR calculation (optional)
    :param cached_nav: Precalculated NAV value (optional)
    :return: The calculated IRR as a Decimal, or 'N/R' if not relevant, or 'N/A' if calculation fails
    """
    if cached_nav is not None:
        portfolio_value = cached_nav
    else:
        portfolio_value = _calculate_portfolio_value(user_id, date, currency, asset_id, broker_account_ids)

    # Not relevant for short positions
    if portfolio_value < 0:
        return 'N/R'

    cash_flows = []
    transaction_dates = []

    transactions = Transactions.objects.filter(investor__id=user_id, date__lte=date, security_id=asset_id)

    if broker_account_ids is not None:
        transactions = transactions.filter(broker_account_id__in=broker_account_ids)

    if start_date is not None:
        transactions = transactions.filter(date__gte=start_date)

        # Calculate start portfolio value if provided
        initial_value_date = start_date - timedelta(days=1)
        start_portfolio_value = _calculate_portfolio_value(user_id, initial_value_date, currency, asset_id, broker_account_ids)
        
        if asset_id is not None:
            first_transaction = transactions.order_by('date').first()
            first_transaction_quantity = first_transaction.quantity if first_transaction else 0
            if (start_portfolio_value < 0) or (start_portfolio_value == 0 and first_transaction_quantity < 0):
                return 'N/R'

        cash_flows.insert(0, -start_portfolio_value)
        transaction_dates.insert(0, initial_value_date)

    for transaction in transactions:
        cash_flow = _calculate_cash_flow(transaction)
        fx_rate = get_fx_rate(transaction.currency.upper(), currency, transaction.date) if currency else 1
        cash_flows.append(Decimal(cash_flow * fx_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        transaction_dates.append(transaction.date)

    if not transactions.filter(date=date).exists():
        cash_flows.append(portfolio_value)
        transaction_dates.append(date)
    else:
        cash_flows[-1] += portfolio_value

    try:
        irr = Decimal(xirr(transaction_dates, cash_flows)).quantize(IRR_PRECISION, rounding=ROUND_HALF_UP)
        return irr if irr < MAX_IRR else 'N/R'
    except Exception as e:
        print(f"Error calculating IRR: {e}")
        return 'N/A'

def _calculate_cash_flow(transaction: Transactions) -> Decimal:
    if transaction.type in ['Cash in', 'Cash out']:
        return (transaction.cash_flow or 0) * Decimal(-1)
    elif transaction.type in ['Broker commission', 'Tax']:
        return Decimal(0)
    else:
        return transaction.cash_flow or (-transaction.quantity * transaction.price + (transaction.commission or 0))

def get_selected_account_ids(user: CustomUser, selection_type: str, selection_id: Optional[int] = None) -> List[int]:
    """
    Get list of broker account IDs based on selection type and ID.
    
    Args:
        user: CustomUser instance
        selection_type: Type of selection ('all', 'account', 'group', 'broker')
        selection_id: ID of selected item (None for 'all')
    
    Returns:
        List of broker account IDs
    """
    if selection_type == 'all':
        return list(BrokerAccounts.objects.filter(
            broker__investor=user
        ).values_list('id', flat=True))
    
    elif selection_type == 'account':
        return [selection_id] if BrokerAccounts.objects.filter(
            id=selection_id,
            broker__investor=user
        ).exists() else []
    
    elif selection_type == 'group':
        try:
            group = AccountGroup.objects.get(id=selection_id, user=user)
            return list(group.broker_accounts.values_list('id', flat=True))
        except AccountGroup.DoesNotExist:
            return []
    
    elif selection_type == 'broker':
        try:
            broker = Brokers.objects.get(id=selection_id, investor=user)
            return list(BrokerAccounts.objects.filter(
                broker=broker
            ).values_list('id', flat=True))
        except Brokers.DoesNotExist:
            return []
    
    return []

def calculate_performance(user, start_date, end_date, account_group_type, account_group_id, currency_target, is_restricted=None):
    performance_data = defaultdict(Decimal)
    logger.debug(f"Calculating performance for {user.username}, {account_group_type} {account_group_id} from {start_date} to {end_date}, currency {currency_target}, restricted {is_restricted}")

    # Initialize all required fields with Decimal(0)
    for field in ['bop_nav', 'invested', 'cash_out', 'price_change', 'capital_distribution', 'commission', 'tax', 'fx', 'eop_nav', 'tsr']:
        performance_data[field] = Decimal('0')

    alternative_fx_check = Decimal('0')

    selected_account_ids = get_selected_account_ids(user, account_group_type, account_group_id)
    accounts = BrokerAccounts.objects.filter(id__in=selected_account_ids, broker__investor=user).select_related('broker')

    bop_nav = AnnualPerformance.objects.filter(
        investor=user, 
        account_type=account_group_type, 
        account_id=account_group_id,
        year=start_date.year - 1, 
        currency=currency_target
    ).values_list('eop_nav', flat=True).first()

    logger.info(f"BOP NAV: {bop_nav}")
    logger.debug(f"Accounts: {accounts}")

    # bop_nav_dict = {nav['broker']: nav['eop_nav'] for nav in bop_navs}

    for account in accounts:
        # bop_nav = bop_nav_dict.get(broker.id)
        if not bop_nav:
            bop_nav_account = NAV_at_date(user.id, tuple([account.id]), start_date - timedelta(days=1), currency_target)['Total NAV']
            performance_data['bop_nav'] += bop_nav_account

        transactions = Transactions.objects.filter(
            investor=user,
            broker_account=account,
            date__gte=start_date,
            date__lte=end_date,
        )

        if is_restricted is not None:
            restricted_filter = Q(security__isnull=False, security__restricted=is_restricted)
            if not is_restricted:
                restricted_filter |= Q(security__isnull=True)
            transactions = transactions.filter(restricted_filter)

        # Calculate transaction-based metrics
        for transaction in transactions:
            fx_rate = get_fx_rate(transaction.currency, currency_target, transaction.date)
            
            if transaction.cash_flow is not None:
                converted_amount = transaction.cash_flow * fx_rate
                if transaction.type == 'Cash in':
                    performance_data['invested'] += converted_amount
                elif transaction.type == 'Cash out':
                    performance_data['cash_out'] += converted_amount
                elif transaction.type == 'Tax':
                    performance_data['tax'] += converted_amount
            
            performance_data['commission'] += (transaction.commission or 0) * fx_rate

        # Calculate asset-based metrics
        assets = Assets.objects.filter(
            investors__id=user.id,
            transactions__broker_account=account
        ).prefetch_related(
            Prefetch(
                'transactions',
                queryset=Transactions.objects.filter(
                    broker_account=account,
                    date__gte=start_date,
                    date__lte=end_date
                ),
                to_attr='period_transactions'
            )
        ).distinct()
        
        if is_restricted is not None:
            assets = assets.filter(restricted=is_restricted)
            
        logger.debug(f"Assets: {assets}")

        for asset in assets:
            asset_realized_gl = asset.realized_gain_loss(
                end_date, user, currency_target, 
                broker_account_ids=[account.id], 
                start_date=start_date
            )
            asset_unrealized_gl = asset.unrealized_gain_loss(
                end_date, user, currency_target,
                broker_account_ids=[account.id],
                start_date=start_date
            )
    
            performance_data['price_change'] += asset_realized_gl['all_time']['price_appreciation'] if asset_realized_gl else 0
            logger.debug(f"Realized GL for {asset.name}: {asset_realized_gl}")
            alternative_fx_check += asset_realized_gl['all_time']['fx_effect']
            performance_data['price_change'] += asset_unrealized_gl['price_appreciation']
            logger.debug(f"Unrealized GL for {asset.name}: {asset_unrealized_gl}")
            alternative_fx_check += asset_unrealized_gl['fx_effect']
            performance_data['capital_distribution'] += asset.get_capital_distribution(end_date, user, currency_target, broker_account_ids=[account.id], start_date=start_date)
            logger.debug(f"Capital distribution for {asset.name}: {performance_data['capital_distribution']}")

        # Calculate EOP NAV
        eop_nav = NAV_at_date(user.id, tuple([account.id]), end_date, currency_target)['Total NAV']
        performance_data['eop_nav'] += eop_nav

    if bop_nav:
        performance_data['bop_nav'] = bop_nav

    # Calculate FX impact
    components_sum = sum(performance_data[key] for key in ['bop_nav', 'invested', 'cash_out', 'price_change', 'capital_distribution', 'commission', 'tax'])
    performance_data['fx'] += performance_data['eop_nav'] - components_sum

    # Calculate TSR
    performance_data['tsr'] = format_percentage(IRR(user.id, end_date, currency_target, broker_account_ids=selected_account_ids, start_date=start_date), digits=1)

    # Adjust FX for rounding errors
    performance_data['fx'] = Decimal('0') if abs(performance_data['fx']) < 0.1 else performance_data['fx']

    logger.debug(f"Alternative FX check: {alternative_fx_check}")
    logger.debug(f"FX effect: {performance_data['fx']}")

    return dict(performance_data)

# Add percentage shares to the dict
def calculate_percentage_shares(data_dict, selected_keys):
    """Calculate percentage shares for selected breakdown categories."""
    if not data_dict:
        return

    total_nav = data_dict.get('Total NAV', Decimal(0))
    
    for key in selected_keys:
        percentage_key = key + '_percentage'
        data_dict[percentage_key] = {}

        for item in data_dict[key]:
            if total_nav > 0:
                percentage = (data_dict[key][item] / total_nav * 100)
                data_dict[percentage_key][item] = format_percentage(percentage, digits=1)
            else:
                data_dict[percentage_key][item] = "–"

def get_last_exit_date_for_broker_accounts(account_ids: List[int], effective_current_date: date) -> Optional[date]:
    """
    Determines the last relevant date for a set of broker accounts, considering both open positions and transaction history.

    If any account has open positions, returns the effective_current_date.
    If all positions are closed, returns the date of the last transaction.
    If no transactions exist, returns the effective_current_date.

    Args:
        account_ids (List[int]): List of broker account IDs to analyze
        effective_current_date (date): The reference date for position calculations

    Returns:
        Optional[date]: 
            - effective_current_date if any positions are open or no transactions exist
            - date of the last transaction if all positions are closed
    """
    # Ensure date is a date object
    if isinstance(effective_current_date, str):
        effective_current_date = datetime.strptime(effective_current_date, '%Y-%m-%d').date()

    # Step 1: Check for open positions using aggregation
    open_positions = Assets.objects.filter(
        transactions__broker_account_id__in=account_ids,
        transactions__date__lte=effective_current_date
    ).annotate(
        total_quantity=Sum('transactions__quantity',
            filter=Q(
                transactions__date__lte=effective_current_date,
                transactions__broker_account_id__in=account_ids
            )
        )
    ).exclude(
        total_quantity=0
    ).exists()

    if open_positions:
        return effective_current_date

    # Step 2: If no open positions, find the latest transaction date
    latest_transaction_date = Transactions.objects.filter(
        broker_account_id__in=account_ids,
        date__lte=effective_current_date
    ).order_by('-date').values_list(
        'date', flat=True
    ).first()
    
    return latest_transaction_date or effective_current_date
