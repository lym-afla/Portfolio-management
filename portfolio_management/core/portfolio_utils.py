from collections import defaultdict
from datetime import date, timedelta
import datetime
from functools import lru_cache
from django.db.models import Sum, QuerySet, Case, When, F, DecimalField, Q
from django.db.models.functions import Coalesce
import pandas as pd
from pyxirr import xirr
from common.models import FX, AnnualPerformance, Assets, Brokers, Transactions
# from constants import BROKER_GROUPS
from functools import lru_cache

import logging
logger = logging.getLogger('dashboard')

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Tuple, Union
import logging

from core.formatting_utils import format_percentage

def portfolio_at_date(user_id: int, to_date: date, brokers: List[int]) -> QuerySet[Assets]:
    """
    Get the portfolio assets for a user at a specific date for given brokers.

    :param user_id: The ID of the user
    :param to_date: The date to calculate the portfolio for
    :param brokers: List of broker IDs to filter by
    :return: QuerySet of Assets with non-zero total quantity
    """
    if not brokers:
        return Assets.objects.none()
    
    return Assets.objects.filter(
        investors__id=user_id,
        transactions__date__lte=to_date, 
        transactions__broker_id__in=brokers
    ).annotate(
        total_quantity=Sum('transactions__quantity')
    ).exclude(total_quantity=0).distinct()

# Get all the brokers associated with a given security
def get_brokers_for_security(user_id: int, security_id: int) -> QuerySet[Brokers]:
    """
    Get all brokers associated with a given security for a user.

    :param user_id: The ID of the user
    :param security_id: The ID of the security
    :return: QuerySet of Brokers
    """
    return Brokers.objects.filter(
        investor__id=user_id,
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


# Calculate NAV breakdown for selected brokers at certain date and in selected currency
@lru_cache(maxsize=None)
def NAV_at_date(user_id: int, broker_ids: Tuple[int], date: date, target_currency: str, breakdown: Tuple[str] = ()) -> Dict:
    broker_ids = list(broker_ids)  # Convert tuple back to list for internal use
    breakdown = list(breakdown)  # Convert tuple back to list for internal use
    
    portfolio = portfolio_at_date(user_id, date, broker_ids)
    portfolio_brokers = Brokers.objects.filter(investor__id=user_id, id__in=broker_ids)
    analysis = defaultdict(lambda: defaultdict(Decimal))
    analysis['Total NAV'] = Decimal(0)
    item_type = {'asset_type': 'type', 'currency': 'currency', 'asset_class': 'exposure'}

    for security in portfolio:
        security_price = security.price_at_date(date, target_currency)
        if security_price is not None:
            security_price = security_price.price
        else:
            security_price = security.calculate_buy_in_price(date, user_id, target_currency, broker_ids)
        
        for broker in portfolio_brokers:
            broker_position = security.position(date, user_id, [broker.id])
            broker_value = Decimal(broker_position * security_price)
            analysis['Total NAV'] += broker_value

            if 'broker' in breakdown:
                analysis['broker'][broker.name] += broker_value
            else:

                for breakdown_type in breakdown:
                    key = getattr(security, item_type[breakdown_type])
                    analysis[breakdown_type][key] += broker_value

    # Handle cash balances
    for broker in portfolio_brokers:
        broker_balance = broker.balance(date)
        for currency, balance in broker_balance.items():
            fx_rate = get_fx_rate(currency, target_currency, date)
            converted_balance = balance * fx_rate
            analysis['Total NAV'] += converted_balance
            
            if 'broker' in breakdown:
                analysis['broker'][broker.name] += converted_balance
            if 'currency' in breakdown:
                analysis['currency'][currency] += converted_balance
            if 'asset_type' in breakdown:
                analysis['asset_type']['Cash'] += converted_balance
            if 'asset_class' in breakdown:
                analysis['asset_class']['Cash'] += converted_balance

    return dict(analysis)

# Helper for IRR calculation
def calculate_portfolio_value(user_id: int, date: date, currency: Optional[str] = None, asset_id: Optional[int] = None, broker_id_list: Optional[List[int]] = None) -> Decimal:
    if asset_id is None:
        portfolio_value = NAV_at_date(user_id, tuple(broker_id_list), date, currency)['Total NAV']
    else:
        asset = Assets.objects.get(id=asset_id, investors__id=user_id)
        try:
            portfolio_value = Decimal(asset.price_at_date(date, currency).price * asset.position(date, user_id, broker_id_list))
        except:
            portfolio_value = Decimal(0)

    return portfolio_value

def calculate_portfolio_cash(user_id: int, broker_ids: List[int], date: date, target_currency: str) -> Decimal:
    """
    Calculate the total cash balance for a user's portfolio across multiple brokers.

    :param user_id: The ID of the user
    :param broker_ids: List of broker IDs to include in the calculation
    :param date: The date for which to calculate the cash balance
    :param target_currency: The currency to convert all cash balances to
    :return: The total cash balance as a Decimal
    """
    portfolio_brokers = Brokers.objects.filter(investor__id=user_id, id__in=broker_ids)
    
    cash_balance = {}
    for broker in portfolio_brokers:
        cash_balance = merge_dictionaries(cash_balance, broker.balance(date))

    cash = sum(
        balance * get_fx_rate(currency, target_currency, date)
        for currency, balance in cash_balance.items()
    )

    return Decimal(cash).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

MAX_IRR = Decimal('2')
IRR_PRECISION = Decimal('0.0001')

def IRR(user_id: int, date: date, currency: Optional[str] = None, asset_id: Optional[int] = None, 
        broker_id_list: Optional[List[int]] = None, start_date: Optional[date] = None, cached_nav: Optional[Decimal] = None) -> Union[Decimal, str]:
    """
    Calculate the Internal Rate of Return (IRR) for a given portfolio or asset.

    :param user_id: The ID of the user
    :param date: The end date for IRR calculation
    :param currency: The currency to use for calculations (optional)
    :param asset_id: The ID of the specific asset to calculate IRR for (optional)
    :param broker_id_list: List of broker IDs to include in the calculation (optional)
    :param start_date: The start date for IRR calculation (optional)
    :param cached_nav: Precalculated NAV value (optional)
    :return: The calculated IRR as a Decimal, or 'N/R' if not relevant, or 'N/A' if calculation fails
    """
    if cached_nav is not None:
        portfolio_value = cached_nav
    else:
        portfolio_value = calculate_portfolio_value(user_id, date, currency, asset_id, broker_id_list)

    # Not relevant for short positions
    if portfolio_value < 0:
        return 'N/R'

    cash_flows = []
    transaction_dates = []

    transactions = Transactions.objects.filter(investor__id=user_id, date__lte=date, security_id=asset_id)

    if broker_id_list is not None:
        transactions = transactions.filter(broker_id__in=broker_id_list)

    if start_date is not None:
        transactions = transactions.filter(date__gte=start_date)

        # Calculate start portfolio value if provided
        initial_value_date = start_date - timedelta(days=1)
        start_portfolio_value = calculate_portfolio_value(user_id, initial_value_date, currency, asset_id, broker_id_list)
        
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

def broker_group_to_ids(brokers_or_group: Union[str, List[int]], user) -> List[int]:
    """
    Convert a broker group name, individual broker name, or list of broker IDs to a list of broker IDs for a user.

    :param brokers_or_group: A string (group name or individual broker name) or list of broker IDs
    :param user: The user object
    :return: A list of broker IDs
    """
    user_brokers = set(Brokers.objects.filter(investor=user).values_list('id', flat=True))

    if isinstance(brokers_or_group, str):
        if brokers_or_group == 'All brokers':
            return list(user_brokers)
        else:
            # Check if it's a broker group name
            try:
                from users.models import BrokerGroup
                group = BrokerGroup.objects.get(user=user, name=brokers_or_group)
                group_brokers = set(group.brokers.values_list('id', flat=True))
                return list(group_brokers & user_brokers)
            except BrokerGroup.DoesNotExist:
                # If not a group, try individual broker name
                try:
                    broker = Brokers.objects.get(investor=user, name=brokers_or_group)
                    return [broker.id]
                except Brokers.DoesNotExist:
                    raise ValueError(f"Invalid broker or group name: {brokers_or_group}")
    elif isinstance(brokers_or_group, list):
        selected_brokers = set(brokers_or_group)
        if not selected_brokers.issubset(user_brokers):
            logging.warning("Some of the provided broker IDs do not belong to the user")
        return list(selected_brokers & user_brokers)

def calculate_performance(user, start_date, end_date, brokers_or_group, currency_target, is_restricted=None):
    performance_data = defaultdict(Decimal)

    # Initialize all required fields with Decimal(0)
    for field in ['bop_nav', 'invested', 'cash_out', 'price_change', 'capital_distribution', 'commission', 'tax', 'fx', 'eop_nav', 'tsr']:
        performance_data[field] = Decimal('0')

    alternative_fx_check = Decimal('0')

    selected_brokers_ids = broker_group_to_ids(brokers_or_group, user)
    
    brokers = Brokers.objects.filter(id__in=selected_brokers_ids, investor=user).select_related('investor')

    bop_nav = AnnualPerformance.objects.filter(
        investor=user, 
        broker_group=brokers_or_group, 
        year=start_date.year - 1, 
        currency=currency_target
    ).values_list('eop_nav', flat=True).first()

    logging.info(f"BOP NAV: {bop_nav}")

    # bop_nav_dict = {nav['broker']: nav['eop_nav'] for nav in bop_navs}

    for broker in brokers:
        # bop_nav = bop_nav_dict.get(broker.id)
        if not bop_nav:
            bop_nav_broker = NAV_at_date(user.id, tuple([broker.id]), start_date - timedelta(days=1), currency_target)['Total NAV']
            performance_data['bop_nav'] += bop_nav_broker

        transactions = Transactions.objects.filter(
            investor=user,
            broker_id=broker.id,
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
        assets = Assets.objects.filter(investors__id=user.id, brokers=broker).prefetch_related('transactions')
        if is_restricted is not None:
            assets = assets.filter(restricted=is_restricted)
            
        for asset in assets:
            asset_realized_gl = asset.realized_gain_loss(end_date, user, currency_target, broker_id_list=[broker.id], start_date=start_date)
            asset_unrealized_gl = asset.unrealized_gain_loss(end_date, user, currency_target, broker_id_list=[broker.id], start_date=start_date)
    
            performance_data['price_change'] += asset_realized_gl['all_time']['price_appreciation'] if asset_realized_gl else 0
            alternative_fx_check += asset_realized_gl['all_time']['fx_effect']
            performance_data['price_change'] += asset_unrealized_gl['price_appreciation']
            alternative_fx_check += asset_unrealized_gl['fx_effect']
            performance_data['capital_distribution'] += asset.get_capital_distribution(end_date, user, currency_target, broker_id_list=[broker.id], start_date=start_date)

        # Calculate EOP NAV
        eop_nav = NAV_at_date(user.id, tuple([broker.id]), end_date, currency_target)['Total NAV']
        performance_data['eop_nav'] += eop_nav

    if bop_nav:
        performance_data['bop_nav'] = bop_nav

    # Calculate FX impact
    components_sum = sum(performance_data[key] for key in ['bop_nav', 'invested', 'cash_out', 'price_change', 'capital_distribution', 'commission', 'tax'])
    performance_data['fx'] += performance_data['eop_nav'] - components_sum

    # Calculate TSR
    performance_data['tsr'] = format_percentage(IRR(user.id, end_date, currency_target, broker_id_list=selected_brokers_ids, start_date=start_date), digits=1)

    # Adjust FX for rounding errors
    performance_data['fx'] = Decimal('0') if abs(performance_data['fx']) < 0.1 else performance_data['fx']

    logger.info(f"Alternative FX check: {alternative_fx_check}")
    logger.info(f"FX effect: {performance_data['fx']}")

    return dict(performance_data)

# Add percentage shares to the dict
def calculate_percentage_shares(data_dict, selected_keys):

    # Calculate Total NAV based on one of the categories
    total = sum(data_dict[selected_keys[0]].values())
    
    # Add new dictionaries with percentage shares for selected categories
    for category in selected_keys:
        percentage_key = category + '_percentage'
        data_dict[percentage_key] = {}
        for key, value in data_dict[category].items():
            try:
                data_dict[percentage_key][key] = str(round(Decimal(value / total * 100), 1)) + '%'
            except ZeroDivisionError or DecimalInvalidOperation:
                data_dict[percentage_key][key] = '–'

def get_last_exit_date_for_brokers(selected_brokers, date):
    """
    Calculate the last date after which all activities ended and no asset was opened for the selected brokers.

    Args:
        selected_brokers (list): List of broker IDs to include in the calculation.
        date (date or str): The current date to use as a reference.

    Returns:
        date: The last date after which all activities ended and no asset was opened for the selected brokers.
    """
    # Ensure date is a date object
    if isinstance(date, str):
        date = datetime.strptime(date, '%Y-%m-%d').date()

    # Step 1: Check the position of each security at the current date
    for broker in Brokers.objects.filter(id__in=selected_brokers):
        for security in broker.securities.all():
            if security.position(date, broker.investor, [broker.id]) != 0:
                return date

    # Step 2: If positions for all securities at the current date are zero, find the latest transaction date
    latest_transaction_date = Transactions.objects.filter(broker_id__in=selected_brokers, date__lte=date).order_by('-date').values_list('date', flat=True).first()
    
    if latest_transaction_date is None:
        return date
    
    return latest_transaction_date
