from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.views.decorators.csrf import ensure_csrf_cookie
from datetime import datetime
from constants import YTD, ALL_TIME
from core.portfolio_utils import broker_group_to_ids, get_last_exit_date_for_brokers
from utils import broker_group_to_ids_old_approach, get_last_exit_date_for_brokers_old_approach
from common.models import Transactions

@api_view(['GET'])
@permission_classes([IsAuthenticated])
# @ensure_csrf_cookie
def get_year_options_api(request):
    user = request.user
    selected_brokers = broker_group_to_ids(user.custom_brokers, user)
    effective_current_date_str = request.session.get('effective_current_date')
    print(f"views. common. 16. Effective current date from session: {effective_current_date_str}")
    
    # Convert effective_current_date from string to date object
    effective_current_date = datetime.strptime(effective_current_date_str, '%Y-%m-%d').date() if effective_current_date_str else datetime.now().date()

    first_year = Transactions.objects.filter(
        investor=user,
        broker__in=selected_brokers
    ).order_by('date').first()
    
    if first_year:
        first_year = first_year.date.year

    last_exit_date = get_last_exit_date_for_brokers(selected_brokers, effective_current_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_current_date.year else effective_current_date.year - 1

    if first_year is not None:
        table_years = list(range(first_year, last_year + 1))
    else:
        table_years = []

    # Convert years to strings
    table_years = [{'text': str(year), 'value': str(year)} for year in table_years]

    # Add special options with a divider
    table_years.extend([
        {'divider': True},
        {'text': 'All-time', 'value': ALL_TIME},
        {'text': f'{effective_current_date.year}YTD', 'value': YTD}
    ])

    return Response({
        'table_years': table_years,
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_effective_current_date(request):
    effective_current_date = request.session.get('effective_current_date', datetime.now().date().isoformat())
    return Response({
        'effective_current_date': effective_current_date
    })