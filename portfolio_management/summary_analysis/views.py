from datetime import date, datetime
from decimal import Decimal
import logging

from django.http import JsonResponse
from django.shortcuts import render

from common.forms import DashboardForm_old_setup
from common.models import FX, AnnualPerformance, Assets, Brokers, Transactions
from utils import broker_group_to_ids_old_approach, brokers_summary_data_old, currency_format_old_structure, format_percentage_old_structure, get_fx_rate_old_structure, get_last_exit_date_for_brokers_old_approach

logger = logging.getLogger(__name__)

def summary_view(request):
    user = request.user
    
    # global selected_brokers
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    selected_brokers = broker_group_to_ids_old_approach(user.custom_brokers, user)

    sidebar_padding = 0
    sidebar_width = 0

    sidebar_width = request.GET.get("width")
    sidebar_padding = request.GET.get("padding")

    # print("views. dashboard", effective_current_date)

    initial_data = {
        'selected_brokers': selected_brokers,
        'default_currency': currency_target,
        'table_date': effective_current_date,
        'digits': number_of_digits
    }
    dashboard_form = DashboardForm_old_setup(instance=user, initial=initial_data)

    user_brokers = Brokers.objects.filter(investor=user)

    broker_table_contexts = brokers_summary_data_old(user, effective_current_date, user_brokers, currency_target, number_of_digits)

    # exposure_table_contexts = exposure_summary_data(user, effective_current_date, user_brokers, currency_target, number_of_digits)

    first_year = AnnualPerformance.objects.filter(
        investor=user,
        broker__in=user_brokers
    ).order_by('year').first().year
    last_exit_date = get_last_exit_date_for_brokers_old_approach([broker.id for broker in user_brokers], effective_current_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_current_date.year else effective_current_date.year - 1

    exposure_table_years = list(range(first_year, last_year + 1))

    buttons = ['settings']

    context = {
        'sidebar_width': sidebar_width,
        'sidebar_padding': sidebar_padding,
        'currency': currency_format_old_structure('', currency_target, 0),
        'table_date': effective_current_date,
        'brokers': Brokers.objects.filter(investor=user).all(),
        'selectedBrokers': user.custom_brokers,
        'dashboardForm': dashboard_form,
        'buttons': buttons,
        'unrestricted_investments_context': broker_table_contexts['public_markets_context'],
        'restricted_investments_context': broker_table_contexts['restricted_investments_context'],
        'total_context': broker_table_contexts['total_context'],
        'exposure_table_years': exposure_table_years
    }

    return render(request, 'summary.html', context)


def exposure_table_update(request):
    timespan = request.GET.get('timespan', 'YTD')
    
    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    currency_target = user.default_currency
    number_of_digits = user.digits

    broker_ids = Brokers.objects.filter(investor=user).values_list('id', flat=True)
    # transactions = Transactions.objects.filter(investor=user, broker_id__in=broker_ids)
    assets = Assets.objects.filter(investor=user)

    # Process the data based on the timespan
    if timespan == 'YTD':
        start_date = date(effective_current_date.year, 1, 1)
        end_date = effective_current_date
    elif timespan == 'All-time':
        start_date = None
        end_date = effective_current_date
    else:
        start_date = date(int(timespan), 1, 1)
        end_date = date(int(timespan), 12, 31)

    # Initialize dictionaries to store the data for each category
    categories = ['Consolidated', 'Unrestricted', 'Restricted']
    data = {category: {} for category in categories}
    
    for category in categories:
        data[category] = {
            'Equity - Int\'l': {'cost': 0, 'unrealized': 0, 'market_value': 0, 'realized': 0, 'capital_distribution': 0, 'commission': 0},
            'Equity - RU': {'cost': 0, 'unrealized': 0, 'market_value': 0, 'realized': 0, 'capital_distribution': 0, 'commission': 0},
            'Fixed income - Int\'l': {'cost': 0, 'unrealized': 0, 'market_value': 0, 'realized': 0, 'capital_distribution': 0, 'commission': 0},
            'Fixed income - RU': {'cost': 0, 'unrealized': 0, 'market_value': 0, 'realized': 0, 'capital_distribution': 0, 'commission': 0},
            'Options': {'cost': 0, 'unrealized': 0, 'market_value': 0, 'realized': 0, 'capital_distribution': 0, 'commission': 0},
            'Cash': {'market_value': 0, 'commission': 0},
        }

    totals = {category: {'cost': 0, 'unrealized': 0, 'market_value': 0, 'realized': 0, 'capital_distribution': 0, 'commission': 0} for category in categories}

    # Calculate values for each asset
    for asset in assets:
        asset_category = categorize_asset(asset)
        
        # Calculate values
        asset.current_position = asset.position(end_date, broker_ids)
        asset.entry_price = asset.calculate_buy_in_price(end_date, currency_target, broker_ids, start_date) or Decimal(0)
        cost = round(asset.entry_price * asset.current_position, 2)

        asset.current_price = Decimal(getattr(asset.price_at_date(end_date, currency_target), 'price', 0))
        market_value = round(asset.current_price * asset.current_position, 2)
        
        unrealized = asset.unrealized_gain_loss(end_date, currency_target, broker_ids, start_date)

        realized = asset.realized_gain_loss(end_date, currency_target, broker_ids, start_date)['all_time']

        capital_distribution = asset.get_capital_distribution(end_date, currency_target, broker_ids, start_date)

        commission = asset.get_commission(end_date, currency_target, broker_ids, start_date)

        for cat in ['Consolidated', 'Restricted' if asset.restricted else 'Unrestricted']:
            data[cat][asset_category]['cost'] += cost
            data[cat][asset_category]['unrealized'] += unrealized
            data[cat][asset_category]['market_value'] += market_value
            data[cat][asset_category]['realized'] += realized
            data[cat][asset_category]['capital_distribution'] += capital_distribution
            data[cat][asset_category]['commission'] += commission

            totals[cat]['cost'] += cost
            totals[cat]['unrealized'] += unrealized
            totals[cat]['market_value'] += market_value
            totals[cat]['realized'] += realized
            totals[cat]['capital_distribution'] += capital_distribution
            totals[cat]['commission'] += commission

    # Calculate cash for all brokers
    brokers = Brokers.objects.filter(investor=user)
    for broker in brokers:
        category = 'Restricted' if broker.restricted else 'Unrestricted'
        cash_balances = broker.balance(end_date).items()
        for currency, balance in cash_balances:
            # fx_rate = FX.get_rate(currency, currency_target, end_date)['FX']
            fx_rate = get_fx_rate_old_structure(currency, currency_target, end_date, user)
            balance_to_add = Decimal(round(balance * fx_rate, 2))
            for cat in ['Consolidated', category]:
                data[cat]['Cash']['market_value'] += balance_to_add
                totals[cat]['market_value'] += balance_to_add
        
        commission_transactions = Transactions.objects.filter(
            investor=user,
            broker=broker,
            security__isnull=True,
            commission__isnull=False,
            )
        if start_date is not None:
            commission_transactions = commission_transactions.filter(date__range=[start_date, end_date]).values('date', 'currency', 'commission')
        else:
            commission_transactions = commission_transactions.filter(date__lte=end_date).values('date', 'currency', 'commission')

        for transaction in commission_transactions:
            # fx_rate = FX.get_rate(transaction['currency'], currency_target, transaction['date'])['FX']
            fx_rate = get_fx_rate_old_structure(transaction['currency'], currency_target, transaction['date'], user)
            commission_to_add = Decimal(round(transaction['commission'] * fx_rate, 2))
            for cat in ['Consolidated', category]:
                data[cat]['Cash']['commission'] += commission_to_add
                totals[cat]['commission'] += commission_to_add
            # data[category]['Cash']['commission'] += commission_to_add
            # data['Consolidated']['Cash']['commission'] += commission_to_add

    # Prepare context for the template
    context = {
        'consolidated_context': [],
        'unrestricted_context': [],
        'restricted_context': [],
    }

    for category in categories:
        for asset_category, values in data[category].items():
            if asset_category == 'Cash':
                line = {
                'name': asset_category,
                'cost': '',
                'unrealized': '',
                'unrealized_percent': '',
                'market_value': values['market_value'],
                'portfolio_percent': 0,
                'realized': '',
                'realized_percent': '',
                'capital_distribution': '',
                'capital_distribution_percent': '',
                'commission': currency_format_old_structure(values['commission'], currency_target, number_of_digits),
                'commission_percent': '',
                'total': currency_format_old_structure(values['commission'], currency_target, number_of_digits),
                'total_percent': ''
                }
            else:
                # print("views. summary. 187", values)
                line = {
                'name': asset_category,
                'cost': currency_format_old_structure(values['cost'], currency_target, number_of_digits),
                'unrealized': currency_format_old_structure(values['unrealized'], currency_target, number_of_digits),
                'unrealized_percent': format_percentage_old_structure(values['unrealized'] / values['cost'] if values['cost'] else 0, digits=1),
                'market_value': values['market_value'],
                'portfolio_percent': 0,  # We'll calculate this after summing up all market values
                'realized': currency_format_old_structure(values['realized'], currency_target, number_of_digits),
                'realized_percent': format_percentage_old_structure((values['realized'] / values['cost']) if values['cost'] else 0, digits=1),
                'capital_distribution': currency_format_old_structure(values['capital_distribution'], currency_target, number_of_digits),
                'capital_distribution_percent': format_percentage_old_structure(values['capital_distribution'] / values['cost'] if values['cost'] else 0, digits=1),
                'commission': currency_format_old_structure(values['commission'], currency_target, number_of_digits),
                'commission_percent': format_percentage_old_structure(values['commission'] / values['cost'] if values['cost'] else 0, digits=1),
                'total': currency_format_old_structure(values['unrealized'] + values['realized'] + values['capital_distribution'] + values['commission'], currency_target, number_of_digits),
                'total_percent': format_percentage_old_structure((values['unrealized'] + values['realized'] + values['capital_distribution'] - values['commission']) / values['cost'] if values['cost'] else 0, digits=1),
            }
            context[f'{category.lower()}_context'].append(line)

    # Calculate portfolio percentages
    for category in categories:
        total_market_value = sum(line['market_value'] for line in context[f'{category.lower()}_context'])
        for line in context[f'{category.lower()}_context']:
            line['portfolio_percent'] = format_percentage_old_structure(line['market_value'] / total_market_value if total_market_value else 0, digits=1)
            line['market_value'] = currency_format_old_structure(line['market_value'], currency_target, number_of_digits)
    
    # Adding totals to the context
    for category in categories:
        total_line = {
            'name': 'TOTAL',
            'cost': currency_format_old_structure(totals[category]['cost'], currency_target, number_of_digits),
            'unrealized': currency_format_old_structure(totals[category]['unrealized'], currency_target, number_of_digits),
            'unrealized_percent': format_percentage_old_structure(totals[category]['unrealized'] / totals[category]['cost'] if totals[category]['cost'] else 0, digits=1),
            'market_value': currency_format_old_structure(totals[category]['market_value'], currency_target, number_of_digits),
            'portfolio_percent': '',
            'realized': currency_format_old_structure(totals[category]['realized'], currency_target, number_of_digits),
            'realized_percent': format_percentage_old_structure(totals[category]['realized'] / totals[category]['cost'] if totals[category]['cost'] else 0, digits=1),
            'capital_distribution': currency_format_old_structure(totals[category]['capital_distribution'], currency_target, number_of_digits),
            'capital_distribution_percent': format_percentage_old_structure(totals[category]['capital_distribution'] / totals[category]['cost'] if totals[category]['cost'] else 0, digits=1),
            'commission': currency_format_old_structure(totals[category]['commission'], currency_target, number_of_digits),
            'commission_percent': format_percentage_old_structure(totals[category]['commission'] / totals[category]['cost'] if totals[category]['cost'] else 0, digits=1),
            'total': currency_format_old_structure(totals[category]['unrealized'] + totals[category]['realized'] + totals[category]['capital_distribution'] +  totals[category]['commission'], currency_target, number_of_digits),
            'total_percent': format_percentage_old_structure((totals[category]['unrealized'] + totals[category]['realized'] + totals[category]['capital_distribution'] - totals[category]['commission']) / totals[category]['cost'] if totals[category]['cost'] else 0, digits=1),
        }
        context[f'{category.lower()}_context'].append(total_line)

    return JsonResponse(context)

def categorize_asset(asset):
    if asset.exposure == 'Equity':
        return 'Equity - RU' if asset.currency == 'RUB' else 'Equity - Int\'l'
    elif asset.exposure == 'FI':
        return 'Fixed income - RU' if asset.currency == 'RUB' else 'Fixed income - Int\'l'
    elif asset.exposure == 'Options':
        return 'Options'
    else:
        return 'Other'  # Just in case there are any assets that don't fit the above categories
    

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from datetime import datetime
# from utils import brokers_summary_data
from core.formatting_utils import format_table_data
from core.summary_utils import brokers_summary_data

class SummaryViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['GET'])
    def summary_data(self, request):
        user = request.user
        effective_current_date = datetime.strptime(request.session.get('effective_current_date', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d').date()
        currency_target = user.default_currency
        number_of_digits = user.digits
        # selected_brokers = request.GET.get('selected_brokers', user.custom_brokers)

        # user_brokers = Brokers.objects.filter(investor=user)

        summary_data = brokers_summary_data(user, effective_current_date, 'All brokers', currency_target, number_of_digits)
        # logger.info(f"summary_data: {summary_data}")

        # Format the data
        formatted_data = {
            "public_markets_context": format_table_data(summary_data["public_markets_context"], currency_target, number_of_digits),
            "restricted_investments_context": format_table_data(summary_data["restricted_investments_context"], currency_target, number_of_digits),
            "total_context": format_table_data(summary_data["total_context"], currency_target, number_of_digits)
        }

        return Response(formatted_data)