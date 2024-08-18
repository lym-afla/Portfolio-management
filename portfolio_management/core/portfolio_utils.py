from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from django.db.models import Sum, QuerySet
from pyxirr import xirr
from common.models import FX, Assets, Brokers, Transactions
from constants import BROKER_GROUPS

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Union
import logging

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
        investor__id=user_id,
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
def get_fx_rate(currency: str, target_currency: str, date: date) -> Decimal:
    return FX.get_rate(currency, target_currency, date)['FX']

# Create one dictionary from two. And add values for respective keys if keys present on both dictionaries
def merge_dictionaries(dict_1: dict, dict_2: dict) -> dict:
    dict_3 = dict_1.copy()  # Create a copy of dict_1
    for key, value in dict_2.items():
        dict_3[key] = dict_3.get(key, 0) + value  # Add values for common keys or set new values if key is not in dict_3
    return dict_3


# Calculate NAV breakdown for selected brokers at certain date and in selected currency
def NAV_at_date(user_id: int, broker_ids: List[int], date: date, target_currency: str, breakdown: List[str] = ['Asset type', 'Currency', 'Asset class', 'Broker']) -> Dict:
    portfolio = portfolio_at_date(user_id, date, broker_ids)
    portfolio_brokers = Brokers.objects.filter(investor__id=user_id, id__in=broker_ids)
    analysis = defaultdict(lambda: defaultdict(Decimal))
    analysis['Total NAV'] = Decimal(0)
    item_type = {'Asset type': 'type', 'Currency': 'currency', 'Asset class': 'exposure'}

    for security in portfolio:
        current_value = Decimal(security.position(date, broker_ids) * security.price_at_date(date, target_currency).price)
        analysis['Total NAV'] += current_value

        for breakdown_type in breakdown:
            if breakdown_type == 'Broker':
                for broker in get_brokers_for_security(user_id, security.id):
                    analysis['Broker'][broker.name] += current_value
            else:
                key = getattr(security, item_type[breakdown_type])
                analysis[breakdown_type][key] += current_value

    cash = Decimal(0)
    for broker in portfolio_brokers:
        broker_balance = broker.balance(date)
        for currency, balance in broker_balance.items():
            fx_rate = get_fx_rate(currency, target_currency, date)
            converted_balance = balance * fx_rate
            cash += converted_balance
            analysis['Broker'][broker.name] += converted_balance
            analysis['Currency'][currency] += converted_balance

    if 'Asset type' in breakdown:
        analysis['Asset type']['Cash'] += cash
    if 'Asset class' in breakdown:
        analysis['Asset class']['Cash'] += cash

    analysis['Total NAV'] += cash

    # Remove keys with zero values
    analysis = {k: {sk: sv for sk, sv in v.items() if sv != 0} if isinstance(v, dict) else v for k, v in analysis.items()}

    return dict(analysis)

# Helper for IRR calculation
def calculate_portfolio_value(user_id: int, date: date, currency: Optional[str] = None, asset_id: Optional[int] = None, broker_id_list: Optional[List[int]] = None) -> Decimal:

    if asset_id is None:
        portfolio_value = NAV_at_date(user_id, broker_id_list, date, currency, [])['Total NAV']
    else:
        asset = Assets.objects.get(id=asset_id)
        try:
            portfolio_value = Decimal(asset.price_at_date(date, currency).price * asset.position(date, broker_id_list))
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
        broker_id_list: Optional[List[int]] = None, start_date: Optional[date] = None) -> Union[Decimal, str]:
    """
    Calculate the Internal Rate of Return (IRR) for a given portfolio or asset.

    :param user_id: The ID of the user
    :param date: The end date for IRR calculation
    :param currency: The currency to use for calculations (optional)
    :param asset_id: The ID of the specific asset to calculate IRR for (optional)
    :param broker_id_list: List of broker IDs to include in the calculation (optional)
    :param start_date: The start date for IRR calculation (optional)
    :return: The calculated IRR as a Decimal, or 'N/R' if not relevant, or 'N/A' if calculation fails
    """
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
        return -transaction.cash_flow
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
        elif brokers_or_group in BROKER_GROUPS:
            group_brokers = set(BROKER_GROUPS[brokers_or_group])
            return list(group_brokers & user_brokers)
        else:
            # It might be an individual broker name
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
    else:
        raise ValueError(f"Invalid input type for brokers_or_group: {type(brokers_or_group)}")