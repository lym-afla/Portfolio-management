from datetime import date, datetime
from decimal import Decimal
import logging
from collections import defaultdict

from django.db import DatabaseError
from django.db.models import Sum

from common.models import AnnualPerformance, Transactions, FX
from core.formatting_utils import currency_format, format_percentage, format_table_data
from core.portfolio_utils import IRR, NAV_at_date, broker_group_to_ids, calculate_percentage_shares, calculate_performance, get_last_exit_date_for_brokers
from core.chart_utils import get_nav_chart_data

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_summary_api(request):
    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    summary = {}

    # Calculate NAV
    summary['Current NAV'] = NAV_at_date(user.id, tuple(selected_brokers), effective_current_date, currency_target)['Total NAV']

    # Calculate Invested and Cash-out
    summary['Invested'] = Decimal(0)
    summary['Cash-out'] = Decimal(0)

    transactions = Transactions.objects.filter(
        investor=user,
        broker__in=selected_brokers,
        date__lte=effective_current_date,
        type__in=['Cash in', 'Cash out']
    ).values('currency', 'type', 'cash_flow', 'date').annotate(
        total=Sum('cash_flow')
    )

    for transaction in transactions:
        fx_rate = FX.get_rate(transaction['currency'], currency_target, transaction['date'], user)['FX']
        if transaction['type'] == 'Cash in':
            summary['Invested'] += Decimal(transaction['total']) * Decimal(fx_rate)
        else:
            summary['Cash-out'] += Decimal(transaction['total']) * Decimal(fx_rate)

    # Calculate IRR and Return
    try:
        summary['total_return'] = (summary['Current NAV'] - summary['Cash-out']) / summary['Invested'] - 1
    except ZeroDivisionError:
        summary['total_return'] = None

    summary['irr'] = IRR(user.id, effective_current_date, currency_target, asset_id=None, broker_id_list=selected_brokers)

    summary = format_table_data(summary, currency_target, number_of_digits)
    
    return Response(summary)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_breakdown_api(request):
    user = request.user
    effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
    
    currency_target = user.default_currency
    number_of_digits = user.digits
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)

    analysis = NAV_at_date(user.id, tuple(selected_brokers), effective_current_date, currency_target, tuple(['asset_type', 'currency', 'asset_class']))
    
    # Remove 'Total NAV' from the analysis
    total_nav = analysis.pop('Total NAV', None)
    
    # Calculate percentage breakdowns
    calculate_percentage_shares(analysis, ['asset_type', 'currency', 'asset_class'])
    
    # Format the values
    analysis = format_table_data(analysis, currency_target, number_of_digits)
    
    return Response({
        'assetType': {
            'data': analysis['asset_type'],
            'percentage': analysis['asset_type_percentage']
        },
        'currency': {
            'data': analysis['currency'],
            'percentage': analysis['currency_percentage']
        },
        'assetClass': {
            'data': analysis['asset_class'],
            'percentage': analysis['asset_class_percentage']
        },
        'totalNAV': currency_format(total_nav, currency_target, number_of_digits)
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_summary_over_time_api(request):
    try:
        user = request.user
        effective_current_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date()
        
        currency_target = user.default_currency
        selected_brokers = broker_group_to_ids(user.custom_brokers, user)

        # Determine the starting year
        stored_data = AnnualPerformance.objects.select_related('investor').filter(
            investor=user,
            broker_group=user.custom_brokers,
            currency=currency_target,
            restricted=None
        )

        first_entry = stored_data.order_by('year').first()
        if not first_entry:
            return Response({"message": "No data available for the selected period."}, status=status.HTTP_404_NOT_FOUND)
        
        start_year = first_entry.year
        last_exit_date = get_last_exit_date_for_brokers(selected_brokers, effective_current_date)
        last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_current_date.year else effective_current_date.year - 1
        years = list(range(start_year, last_year + 1))

        line_names = [
            "BoP NAV", "Invested", "Cash out", "Price change", "Capital distribution",
            "Commission", "Tax", "FX", "EoP NAV", "TSR"
        ]
        
        lines = defaultdict(lambda: {"name": "", "data": {}})
        for name in line_names:
            lines[name]["name"] = name
        
        # Fetch stored data
        stored_data = stored_data.filter(year__in=years).values_list('year', *[name.lower().replace(' ', '_') for name in line_names])

        # Process stored data
        processed_data = {
            entry[0]: {line_names[i]: entry[i+1] for i in range(len(line_names))}
            for entry in stored_data
        }

        for line_name in line_names:
            lines[line_name]['data'] = {year: processed_data[year][line_name] for year in processed_data}

        # Calculate YTD for the current year
        current_year = effective_current_date.year
        ytd_data = calculate_performance(user, date(current_year, 1, 1), effective_current_date, selected_brokers, currency_target)

        for line_name in line_names:
            ytd_field_name = line_name.lower().replace(' ', '_')
            lines[line_name]["data"]["YTD"] = ytd_data[ytd_field_name]

        # Calculate All-time data
        for line_name, line_data in lines.items():
            if line_name != 'TSR':
                line_data["data"]["All-time"] = sum(value for year, value in line_data["data"].items() if year != "All-time")

        lines['TSR']["data"]["All-time"] = format_percentage(IRR(user.id, effective_current_date, currency_target, broker_id_list=selected_brokers), digits=1)
        lines['BoP NAV']['data']['All-time'] = Decimal(0)
        lines['EoP NAV']["data"]["All-time"] = lines['EoP NAV']["data"].get("YTD", Decimal(0))

        # Format the data
        format_funcs = {
            Decimal: lambda v: currency_format(v, currency_target, user.digits),
            float: lambda v: f"{v:.2%}"
        }

        for line in lines.values():
            line['data'] = {
                year: format_funcs.get(type(value), str)(value)
                for year, value in line['data'].items()
            }

        return Response({
            "years": years,
            "lines": list(lines.values()),
            "currentYear": str(current_year)
        }, status=status.HTTP_200_OK)
    
    except AnnualPerformance.DoesNotExist:
        return Response({"error": "No annual performance data found."}, status=status.HTTP_404_NOT_FOUND)
    except DatabaseError:
        return Response({"error": "Database error occurred while fetching data"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except KeyError:
        return Response({"error": "Invalid session data"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_nav_chart_data(request):
    user = request.user
    frequency = request.GET.get('frequency')
    from_date = request.GET.get('dateFrom')
    to_date = request.GET.get('dateTo')
    breakdown = request.GET.get('breakdown')
    currency = user.default_currency
    brokers = broker_group_to_ids(user.custom_brokers, user)

    # If to_date is not provided, use the effective current date
    if not to_date:
        to_date = datetime.strptime(request.session['effective_current_date'], '%Y-%m-%d').date().isoformat()

    # from_date can be None, it will be handled in get_nav_chart_data
    
    logger.info(f"Received request for NAV chart data with frequency: {frequency}, from date: {from_date}, to date: {to_date}, breakdown: {breakdown}, currency: {currency}, brokers: {user.custom_brokers}")

    # try:
    chart_data = get_nav_chart_data(user.id, brokers, frequency, from_date, to_date, currency, breakdown)
    return Response(chart_data)
    # except ValueError as e:
    #     return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    # except Exception as e:
    #     return Response({'error': 'An unexpected error occurred: ' + str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)