from datetime import timedelta, date
from decimal import Decimal
import time
from typing import List, Dict, Any, Union, Tuple, Optional

from core.formatting_utils import currency_format
from core.portfolio_utils import IRR, NAV_at_date, calculate_portfolio_cash, get_fx_rate

def calculate_positions_table_output(
    user_id: int,
    assets: List[Any],
    end_date: date,
    categories: List[str],
    use_default_currency: bool,
    currency_target: str,
    selected_brokers: List[int],
    start_date: Union[date, None],
    is_closed: bool
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Wrapper function to compile either closed or open positions.

    """
    if is_closed:
        return calculate_closed_table_output_for_api(
            user_id, assets, end_date, categories, use_default_currency,
            currency_target, selected_brokers, start_date
        )
    else:
        return calculate_open_table_output_for_api(
            user_id, assets, end_date, categories, use_default_currency,
            currency_target, selected_brokers, start_date
        )

def calculate_closed_table_output_for_api(
    user_id: int,
    portfolio: List[Any],
    end_date: date,
    categories: List[str],
    use_default_currency: bool,
    currency_target: str,
    selected_brokers: List[int],
    start_date: Optional[date] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Calculate table output for closed positions.

    :param user_id: The ID of the user
    :param portfolio: List of asset objects
    :param end_date: The end date for calculations
    :param categories: List of categories to include in the output
    :param use_default_currency: Whether to use the default currency
    :param currency_target: The target currency for calculations
    :param selected_brokers: List of selected broker IDs
    :param start_date: The start date for calculations (optional)
    :return: A tuple containing a list of closed position dictionaries and a dictionary of totals
    """
    closed_positions = []
    totals = ['entry_value', 'current_value', 'realized_gl', 'capital_distribution', 'commission']
    portfolio_closed_totals = {}
    
    for asset in portfolio:
        
        exit_dates = list(asset.exit_dates(end_date, selected_brokers, start_date))
        entry_dates = list(asset.entry_dates(end_date, selected_brokers))
        
        for i, exit_date in enumerate(exit_dates):
            currency_used = None if use_default_currency else currency_target
            
            # Has to be defined here to accomodate different closed positions of same asset as separate rows
            position = {
                'id': asset.id,
                'type': asset.type,
                'name': asset.name,
                'currency': currency_format(None, asset.currency),
                'exit_date': exit_date
            }

            # Determine entry_date
            first_entry_date = asset.entry_dates(exit_date, selected_brokers)[-1]
            entry_date = start_date if start_date and start_date >= first_entry_date else first_entry_date
            position['investment_date'] = entry_date

            # Determine next_entry_date (or end_date if there's no next entry)
            next_entry_date = entry_dates[entry_dates.index(entry_date) + 1] if entry_date in entry_dates and entry_dates.index(entry_date) < len(entry_dates) - 1 else end_date

            asset_transactions = asset.transactions.filter(
                investor__id=user_id,
                date__gte=entry_date,
                date__lte=exit_date,
                broker__in=selected_brokers,
                quantity__isnull=False
            ).order_by('-date')

            # Determine if it's a long or short position
            is_long_position = asset_transactions.first().quantity < 0 # if asset_transactions.exists() else True

            if is_long_position:
                entry_transactions = asset_transactions.filter(quantity__gt=0)
                exit_transactions = asset_transactions.filter(quantity__lt=0)
            else:
                entry_transactions = asset_transactions.filter(quantity__lt=0)
                exit_transactions = asset_transactions.filter(quantity__gt=0)

            # Calculate entry value and quantity
            if start_date is not None:
                entry_quantity = asset.position(entry_date - timedelta(days=1), selected_brokers)
                entry_value = asset.price_at_date(entry_date - timedelta(days=1), currency_used).price * entry_quantity
            else:
                entry_value = Decimal(0)
                entry_quantity = Decimal(0)
            
            for transaction in entry_transactions:
                fx_rate = get_fx_rate(transaction.currency, currency_used, transaction.date) if currency_used else 1
                entry_value += transaction.price * abs(transaction.quantity) * fx_rate
                entry_quantity += abs(transaction.quantity)

            position['entry_value'] = Decimal(entry_value)

            # Calculate exit value and quantity
            exit_value = Decimal(0)
            for transaction in exit_transactions:
                fx_rate = get_fx_rate(transaction.currency, currency_used, transaction.date) if currency_used else 1
                exit_value += transaction.price * abs(transaction.quantity) * fx_rate

            position['exit_value'] = Decimal(exit_value)

            # Calculate realized gain/loss
            if 'realized_gl' in categories:
                position['realized_gl'] = exit_value - entry_value
            else:
                position['realized_gl'] = Decimal(0)

            position['price_change_percentage'] = (position['realized_gl']) / position['entry_value'] if position['entry_value'] > 0 else 'N/R'

            # Calculate capital distribution including dividends after exit_date but before next_entry_date
            if 'capital_distribution' in categories:
                position['capital_distribution'] = (
                    asset.get_capital_distribution(exit_date, currency_used, selected_brokers, entry_date) +
                    asset.get_capital_distribution(next_entry_date, currency_used, selected_brokers, exit_date + timedelta(days=1))
                )
                position['capital_distribution_percentage'] = Decimal(position['capital_distribution'] / position['entry_value']) if position['entry_value'] > 0 else 'N/R'
            else:
                position['capital_distribution'] = Decimal(0)

            if 'commission' in categories:
                position['commission'] = asset.get_commission(exit_date, currency_used, selected_brokers, entry_date)
                position['commission_percentage'] = position['commission'] / position['entry_value'] if position['entry_value'] > 0 else 'N/R'
            else:
                position['commission'] = Decimal(0)

            position['total_return_amount'] = position['realized_gl'] + position['capital_distribution'] + position['commission']
            position['total_return_percentage'] = position['total_return_amount'] / position['entry_value'] if position['entry_value'] > 0 else 'N/R'

            # Calculate IRR
            currency_used = asset.currency if use_default_currency else currency_target
            position['irr'] = IRR(user_id, exit_date, currency_used, asset_id=asset.id, broker_id_list=selected_brokers, start_date=entry_date)

            closed_positions.append(position)
            
            # Update portfolio totals
            for key in list((set(totals) & set(categories)) | {'entry_value', 'exit_value', 'total_return_amount', 'price_change_percentage', 'capital_distribution_percentage', 'commission_percentage', 'total_return_percentage'}):
                if key in position:
                    portfolio_closed_totals[key] = portfolio_closed_totals.get(key, Decimal(0)) + position[key]
    
    # Calculate percentage totals
    if portfolio_closed_totals.get('entry_value', Decimal(0)) != 0:
        portfolio_closed_totals['price_change_percentage'] = (portfolio_closed_totals.get('realized_gl', Decimal(0)) + portfolio_closed_totals.get('unrealized_gl', Decimal(0))) / abs(portfolio_closed_totals['entry_value'])
        if 'capital_distribution' in categories:
            portfolio_closed_totals['capital_distribution_percentage'] = portfolio_closed_totals['capital_distribution'] / portfolio_closed_totals['entry_value']
        if 'commission' in categories:
            portfolio_closed_totals['commission_percentage'] = portfolio_closed_totals['commission'] / portfolio_closed_totals['entry_value']
        portfolio_closed_totals['total_return_percentage'] = portfolio_closed_totals['total_return_amount'] / abs(portfolio_closed_totals['entry_value'])
    
    return closed_positions, portfolio_closed_totals

def calculate_open_table_output_for_api(
    user_id: int,
    portfolio: List[Any],
    end_date: date,
    categories: List[str],
    use_default_currency: bool,
    currency_target: str,
    selected_brokers: List[int],
    start_date: Optional[date] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Calculate table output for open positions.

    :param user_id: The ID of the user
    :param portfolio: List of asset objects
    :param end_date: The end date for calculations
    :param categories: List of categories to include in the output
    :param use_default_currency: Whether to use the default currency
    :param currency_target: The target currency for calculations
    :param selected_brokers: List of selected broker IDs
    :param start_date: The start date for calculations (optional)
    :return: A tuple containing a list of open position dictionaries and a dictionary of totals
    """
    start_time = time.time()  # Start timing the overall function
    portfolio_NAV = NAV_at_date(user_id, tuple(selected_brokers), end_date, currency_target)['Total NAV']
    portfolio_cash = calculate_portfolio_cash(user_id, selected_brokers, end_date, currency_target)
    
    totals = ['entry_value', 'current_value', 'realized_gl', 'unrealized_gl', 'capital_distribution', 'commission']
    open_positions = []
    portfolio_open_totals = {
        'all_assets_share_of_portfolio_percentage': Decimal(0)
    }

    total_irr_start_date = start_date  # Not to be overwritten by asset start date if start date is not defined
    
    for asset in portfolio:
        asset_start_time = time.time()  # Start timing for each asset
        currency_used = None if use_default_currency else currency_target

        position = {
            'id': asset.id,
            'type': asset.type,
            'name': asset.name,
            'currency': currency_format(None, asset.currency)
        }

        position['current_position'] = asset.position(end_date, selected_brokers)

        if position['current_position'] == 0:
            print(f"The position is zero for {asset.name}. Skipping this asset.")
            continue

        position_entry_date = asset.entry_dates(end_date, selected_brokers)[-1]
        if 'investment_date' in categories:
            position['investment_date'] = position_entry_date

        asset_start_date = start_date if start_date is not None else position_entry_date
            
        position['entry_price'] = asset.calculate_buy_in_price(end_date, currency_used, selected_brokers, asset_start_date)
        if position['entry_price'] == 0:
            position['entry_price'] = asset.calculate_buy_in_price(end_date, currency_used, selected_brokers)
        position['entry_value'] = Decimal(position['entry_price'] * position['current_position'])
        
        if 'current_value' in categories:
            if asset.price_at_date(end_date, currency_used) is not None:
                position['current_price'] = asset.price_at_date(end_date, currency_used).price
            else:
                position['current_price'] = position['entry_price']
            position['current_value'] = Decimal(position['current_price'] * position['current_position'])
            position['share_of_portfolio'] = position['current_value'] / portfolio_NAV

            portfolio_open_totals['all_assets_share_of_portfolio_percentage'] += position['share_of_portfolio']
        
        if 'realized_gl' in categories:
            position['realized_gl'] = asset.realized_gain_loss(end_date, currency_used, selected_brokers, asset_start_date)['current_position']['total']
        else:
            position['realized_gl'] = Decimal(0)

        if 'unrealized_gl' in categories:
            position['unrealized_gl'] = asset.unrealized_gain_loss(end_date, currency_used, selected_brokers, asset_start_date)['total']
        else:
            position['unrealized_gl'] = Decimal(0)
        
        position['price_change_percentage'] = (position['realized_gl'] + position['unrealized_gl']) / position['entry_value'] if position['entry_value'] > 0 else 'N/R'
        
        if 'capital_distribution' in categories:
            position['capital_distribution'] = asset.get_capital_distribution(end_date, currency_used, selected_brokers, asset_start_date)
            position['capital_distribution_percentage'] = position['capital_distribution'] / position['entry_value'] if position['entry_value'] > 0 else 'N/R'
        else:
            position['capital_distribution'] = Decimal(0)

        if 'commission' in categories:
            position['commission'] = asset.get_commission(end_date, currency_used, selected_brokers, asset_start_date)
            position['commission_percentage'] = position['commission'] / position['entry_value'] if position['entry_value'] > 0 else 'N/R'
        else:
            position['commission'] = Decimal(0)
            
        position['total_return_amount'] = position['realized_gl'] + position['unrealized_gl'] + position['capital_distribution'] + position['commission']
        position['total_return_percentage'] = position['total_return_amount'] / position['entry_value'] if position['entry_value'] > 0 else 'N/R'
        
        # Calculate IRR for security
        currency_used = asset.currency if use_default_currency else currency_target
        position['irr'] = IRR(user_id, end_date, currency_used, asset_id=asset.id, broker_id_list=selected_brokers, start_date=asset_start_date)

        # Log time taken for processing the asset
        asset_duration = time.time() - asset_start_time
        print(f"Processing asset {asset.name} took {asset_duration:.4f} seconds.")
        
        # Calculating totals
        for key in (['entry_value', 'total_return_amount'] + list(set(totals) & set(categories))):
            if not use_default_currency:
                addition = position[key]
            else:
                if key == 'entry_value':
                    addition = position['entry_value']
                elif key == 'total_return_amount':
                    addition = position['total_return_amount']
                elif key == 'current_value':
                    addition = position['current_value']
                elif key == 'realized_gl':
                    addition = asset.realized_gain_loss(end_date, currency_target, selected_brokers, asset_start_date)['current_position']['total']
                elif key == 'unrealized_gl':
                    addition = asset.unrealized_gain_loss(end_date, currency_target, selected_brokers, asset_start_date)['total']
                elif key == 'capital_distribution':
                    addition = asset.get_capital_distribution(end_date, currency_target, selected_brokers, asset_start_date)
                elif key == 'commission':
                    addition = asset.get_commission(end_date, currency_target, selected_brokers, asset_start_date)
                else:
                    addition = Decimal(0)

            portfolio_open_totals[key] = portfolio_open_totals.get(key, Decimal(0)) + addition

        open_positions.append(position)

    if 'entry_value' in portfolio_open_totals and portfolio_open_totals['entry_value'] != 0:
        abs_entry_value = abs(portfolio_open_totals['entry_value'])
        portfolio_open_totals['price_change_percentage'] = (
            portfolio_open_totals.get('realized_gl', Decimal(0)) +
            portfolio_open_totals.get('unrealized_gl', Decimal(0))
        ) / abs_entry_value
        
        if 'capital_distribution' in categories:
            portfolio_open_totals['capital_distribution_percentage'] = portfolio_open_totals['capital_distribution'] / abs_entry_value
        
        if 'commission' in categories:
            portfolio_open_totals['commission_percentage'] = portfolio_open_totals['commission'] / abs_entry_value
        
        portfolio_open_totals['total_return_percentage'] = portfolio_open_totals['total_return_amount'] / abs_entry_value
        portfolio_open_totals['share_of_portfolio'] = portfolio_open_totals['current_value'] / portfolio_NAV

    portfolio_open_totals['cash'] = portfolio_cash
    portfolio_open_totals['total_nav'] = portfolio_NAV
    portfolio_open_totals['irr'] = IRR(user_id, end_date, currency_target, asset_id=None, broker_id_list=selected_brokers, start_date=total_irr_start_date)

    if portfolio_NAV == 0:
        portfolio_open_totals['cash_share_of_portfolio'] = 'N/A'
        portfolio_open_totals['all_assets_share_of_portfolio_percentage'] = 'N/A'
    else:
        portfolio_open_totals['cash_share_of_portfolio'] = portfolio_cash / portfolio_NAV

    total_duration = time.time() - start_time
    print(f"Total processing time for calculate_open_table_output_for_api: {total_duration:.4f} seconds.")
    
    return open_positions, portfolio_open_totals

