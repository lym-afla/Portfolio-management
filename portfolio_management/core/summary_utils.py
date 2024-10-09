from decimal import Decimal
from datetime import date
import logging

from common.models import AnnualPerformance, Brokers

from core.portfolio_utils import broker_group_to_ids, get_last_exit_date_for_brokers, calculate_performance, IRR
from core.formatting_utils import currency_format_dict_values

logger = logging.getLogger(__name__)

def brokers_summary_data(user, effective_date, brokers_or_group, currency_target, number_of_digits):
    def initialize_context():
        return {
            'years': [],
            'lines': []
        }

    def initialize_totals(years):
        return {year: {
            'bop_nav': Decimal(0),
            'invested': Decimal(0),
            'cash_out': Decimal(0),
            'price_change': Decimal(0),
            'capital_distribution': Decimal(0),
            'commission': Decimal(0),
            'tax': Decimal(0),
            'fx': Decimal(0),
            'eop_nav': Decimal(0),
            'tsr': Decimal(0)
        } for year in ['YTD'] + years + ['All-time']}

    # if isinstance(brokers_or_group, str):
    #     # It's a group name
    #     group_name = brokers_or_group
    #     selected_brokers_ids = constants.BROKER_GROUPS.get(group_name)
    #     if not selected_brokers_ids:
    #         raise ValueError(f"Invalid group name: {group_name}")
    # else:
    #     # It's a list of broker IDs
    #     selected_brokers_ids = brokers_or_group
    #     group_name = None

    selected_brokers_ids = broker_group_to_ids(brokers_or_group, user)

    public_markets_context = initialize_context()
    restricted_investments_context = initialize_context()
    total_context = initialize_context()
    
    # Determine the starting and ending years
    stored_data = AnnualPerformance.objects.filter(
        investor=user,
        currency=currency_target,
        # broker_group=brokers_or_group
    )

    # logger.info(f"Stored data: {stored_data}")
    # logger.info(f"Selected brokers IDs: {selected_brokers_ids}")
    # logger.info(f"Group name: {brokers_or_group}")

    # if group_name is not None:
    #     stored_data = stored_data.filter(broker_group=group_name)
    # else:
    #     stored_data = stored_data.filter(broker_id__in=selected_brokers_ids)

    # logger.info(f"Stored data after filtering: {stored_data}")

    first_entry = stored_data.order_by('year').first()
    if not first_entry:
        return {
            "public_markets_context": public_markets_context,
            "restricted_investments_context": restricted_investments_context,
            "total_context": total_context
        }
    
    start_year = first_entry.year
    last_exit_date = get_last_exit_date_for_brokers(selected_brokers_ids, effective_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_date.year else effective_date.year - 1
    years = list(range(start_year, last_year + 1))

    stored_data = stored_data.filter(year__in=years).values()
    current_year = effective_date.year

    # logger.info(f"Years: {years}")
    # logger.info(f"Stored data for years: {stored_data}")

    public_totals = initialize_totals(years)
    restricted_totals = initialize_totals(years)

    brokers = Brokers.objects.filter(id__in=selected_brokers_ids, investor=user)

    for restricted in [False, True]:
        context = public_markets_context if not restricted else restricted_investments_context
        totals = public_totals if not restricted else restricted_totals

        brokers_subgroup = brokers.filter(restricted=restricted)

        for broker in brokers_subgroup:
            line_data = {'name': broker.name, 'data': {}}

            # Initialize data for all years
            for year in ['YTD'] + years + ['All-time']:
                line_data['data'][year] = {
                    'bop_nav': Decimal(0),
                    'invested': Decimal(0),
                    'cash_out': Decimal(0),
                    'price_change': Decimal(0),
                    'capital_distribution': Decimal(0),
                    'commission': Decimal(0),
                    'tax': Decimal(0),
                    'fx': Decimal(0),
                    'eop_nav': Decimal(0),
                    'tsr': Decimal(0)
                }
                line_data['data'][year] = compile_summary_data(line_data['data'][year], currency_target, number_of_digits)

            # Add YTD data
            try:
                ytd_data = calculate_performance(user, date(current_year, 1, 1), effective_date, [broker.id], currency_target, is_restricted=restricted)
                compiled_ytd_data = compile_summary_data(ytd_data, currency_target, number_of_digits)
                line_data['data']['YTD'] = compiled_ytd_data

                # Update totals for YTD
                for key, value in ytd_data.items():
                    if isinstance(value, Decimal) and key != 'tsr':
                        totals['YTD'][key] += value
            except Exception as e:
                print(f"Error calculating YTD data for broker {broker.name}: {e}")
            
            # Initialize all-time data
            all_time_data = {key: Decimal(0) for key in totals['All-time'].keys()}

            # Add stored data for each year
            for entry in stored_data:
                if entry['broker_group'] == broker.name and entry['restricted'] == restricted:
                    year_data = {k: v for k, v in entry.items() if k not in ('id', 'broker_id', 'investor_id', 'broker_group')}
                    formatted_year_data = compile_summary_data(year_data, currency_target, number_of_digits)
                    line_data['data'][entry['year']] = formatted_year_data

                    # Update totals for each year
                    for key, value in year_data.items():
                        if isinstance(value, Decimal) and key != 'tsr':
                            totals[entry['year']][key] += value

                    # Accumulate all-time data
                    for key in all_time_data.keys():
                        if key not in ['bop_nav', 'eop_nav', 'tsr']:
                            all_time_data[key] += year_data.get(key, Decimal(0))

            # Add YTD data to all-time
            for key in all_time_data.keys():
                if key not in ['bop_nav', 'eop_nav', 'tsr']:
                    all_time_data[key] += ytd_data.get(key, Decimal(0))

            # Add final year EoP NAV to all-time
            all_time_data['eop_nav'] = ytd_data.get('eop_nav', Decimal(0))

            # Add all-time TSR separately if broker matches the restriction condition
            if broker.restricted == restricted:
                try:
                    all_time_data['tsr'] = IRR(user.id, effective_date, currency_target, broker_id_list=[broker.id])
                except Exception as e:
                    print(f"Error calculating all-time TSR for broker {broker.name}: {e}")
                    all_time_data['tsr'] = 'N/A'
            else:
                all_time_data['tsr'] = 'N/R'

            # Format all-time data
            formatted_all_time_data = compile_summary_data(all_time_data, currency_target, number_of_digits)
            line_data['data']['All-time'] = formatted_all_time_data

            # Update totals for All-time
            for key, value in all_time_data.items():
                if isinstance(value, Decimal) and key != 'tsr':
                    totals['All-time'][key] += value

            context['lines'].append(line_data)

        # Add Sub-totals line
        sub_totals_line = {'name': 'Sub-total', 'data': {}}
        for year in ['YTD'] + years + ['All-time']:
            # try:
            if year == 'YTD':
                totals[year]['tsr'] = IRR(user.id, effective_date, currency_target, broker_id_list=[broker.id for broker in brokers_subgroup], start_date=date(effective_date.year, 1, 1))
            elif year == 'All-time':
                totals[year]['tsr'] = IRR(user.id, effective_date, currency_target, broker_id_list=[broker.id for broker in brokers_subgroup])
            else:
                totals[year]['tsr'] = IRR(user.id, date(year, 12, 31), currency_target, broker_id_list=[broker.id for broker in brokers_subgroup], start_date=date(year, 1, 1))
            # except Exception as e:
            #     print(f"Error calculating TSR for year {year}: {e}")
            #     totals[year]['tsr'] = 'N/R'

            sub_totals_line['data'][year] = compile_summary_data(totals[year], currency_target, number_of_digits)
        
        context['lines'].append(sub_totals_line)

        context['years'] = ['YTD'] + years[::-1] + ['All-time']

    # Add Totals line
    totals_line = {'name': 'TOTAL', 'data': {}}
    for year in ['YTD'] + years + ['All-time']:
        totals_line['data'][year] = {
            'bop_nav': Decimal(0),
            'invested': Decimal(0),
            'cash_out': Decimal(0),
            'price_change': Decimal(0),
            'capital_distribution': Decimal(0),
            'commission': Decimal(0),
            'tax': Decimal(0),
            'fx': Decimal(0),
            'eop_nav': Decimal(0),
            'tsr': Decimal(0)
        }
        
        # Sum up values from both public markets and restricted investments contexts
        for sub_total in [public_totals[year], restricted_totals[year]]:
            for key, value in sub_total.items():
                if key != 'tsr' and isinstance(value, Decimal):
                    totals_line['data'][year][key] += value
        
        try:
            if year == 'YTD':
                totals_line['data'][year]['tsr'] = IRR(user.id, effective_date, currency_target, broker_id_list=[broker.id for broker in brokers], start_date=date(effective_date.year, 1, 1))
            elif year == 'All-time':
                totals_line['data'][year]['tsr'] = IRR(user.id, effective_date, currency_target, broker_id_list=[broker.id for broker in brokers])
            else:
                totals_line['data'][year]['tsr'] = IRR(user.id, date(year, 12, 31), currency_target, broker_id_list=[broker.id for broker in brokers], start_date=date(year, 1, 1))
        except Exception as e:
            print(f"Error calculating TSR for year {year}: {e}")
            totals_line['data'][year]['tsr'] = 'N/R'

        # Calculate fee per AUM
        total_nav = totals_line['data'][year]['eop_nav']
        total_commission = totals_line['data'][year]['commission']
        if total_nav > 0:
            fee_per_aum = -(total_commission / total_nav)  # as a percentage
        else:
            fee_per_aum = Decimal(0)
        
        totals_line['data'][year]['fee_per_aum'] = fee_per_aum
        
        # Compile and format the data
        totals_line['data'][year] = compile_summary_data(totals_line['data'][year], currency_target, number_of_digits)
    
    # Create a new context for the total line
    total_context = {
        'years': ['YTD'] + years[::-1] + ['All-time'],
        'line': totals_line
    }

    return {
        "public_markets_context": public_markets_context,
        "restricted_investments_context": restricted_investments_context,
        "total_context": total_context
    }

def compile_summary_data(data, currency_target, number_of_digits):
    
    bop_nav = data.get('bop_nav', Decimal(0))
    eop_nav = data.get('eop_nav', Decimal(0))
    invested = data.get('invested', Decimal(0))
    cash_out = data.get('cash_out', Decimal(0))
    price_change = data.get('price_change', Decimal(0))
    capital_distribution = data.get('capital_distribution', Decimal(0))
    commission = data.get('commission', Decimal(0))
    tax = data.get('tax', Decimal(0))
    fx = data.get('fx', Decimal(0))
    tsr = data.get('tsr', Decimal(0))

    # Calculate additional metrics
    cash_in_out = invested + cash_out
    return_value = price_change + capital_distribution + commission + tax
    avg_nav = (bop_nav + eop_nav) / 2 if (bop_nav + eop_nav) != 0 else -1  # Avoid division by zero
    fee_per_aum = -(commission / avg_nav) if avg_nav != -1 else Decimal(0)  # Fee per AuM as percentage

    formatted_data = {
        'BoP NAV': round(bop_nav, number_of_digits),
        'Cash-in/out': round(cash_in_out, number_of_digits),
        'Return': round(return_value, number_of_digits),
        'FX': round(fx, number_of_digits),
        'TSR percentage': tsr,
        'EoP NAV': round(eop_nav, number_of_digits),
        'Commission': round(commission, number_of_digits),
        'Fee per AuM (percentage)': fee_per_aum,
    }

    formatted_data = currency_format_dict_values(formatted_data, currency_target, number_of_digits)

    return formatted_data