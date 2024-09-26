import json
import logging
import traceback
from datetime import date
from django.db import transaction

from core.portfolio_utils import broker_group_to_ids
from common.models import Transactions, AnnualPerformance
from core.portfolio_utils import get_last_exit_date_for_brokers, calculate_performance

logger = logging.getLogger(__name__)

def save_or_update_annual_broker_performance(user, effective_date, brokers_or_group, currency_target, is_restricted=None, skip_existing_years=False):
    logger.info(f"Starting save_or_update_annual_broker_performance for {brokers_or_group}, {currency_target}, is_restricted={is_restricted}")
    try:
        selected_brokers_ids = broker_group_to_ids(brokers_or_group, user)

        # Determine the starting year
        first_transaction = Transactions.objects.filter(broker_id__in=selected_brokers_ids, date__lte=effective_date).order_by('date').first()
        if not first_transaction:
            error_msg = 'No transactions found'
            logger.error(error_msg)
            yield json.dumps({'status': 'error', 'message': error_msg}) + '\n'
            return
        
        start_year = first_transaction.date.year

        # Determine the ending year
        last_exit_date = get_last_exit_date_for_brokers(selected_brokers_ids, effective_date)
        last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_date.year else effective_date.year - 1
        years = list(range(start_year, last_year + 1))

        logger.info(f"Calculating performance for {len(years)} years. First transaction: {first_transaction.date}, last exit date: {last_exit_date}")

        total_years = len(years)
        for i, year in enumerate(years, 1):
            if skip_existing_years and AnnualPerformance.objects.filter(investor=user, broker_group=brokers_or_group, year=year, currency=currency_target, restricted=is_restricted).exists():
                logger.info(f"Skipping existing year {year}")
                continue

            try:
                with transaction.atomic():
                    performance_data = calculate_performance(user, date(year, 1, 1), date(year, 12, 31), selected_brokers_ids, currency_target, is_restricted)
                    
                    performance, created = AnnualPerformance.objects.update_or_create(
                        investor=user,
                        broker_group=brokers_or_group,
                        year=year,
                        currency=currency_target,
                        restricted=is_restricted,
                        defaults=performance_data
                    )

                progress_data = {
                    'status': 'progress',
                    'current': i,
                    'total': total_years,
                    'progress': (i / total_years) * 100,
                    'year': year
                }
                logger.info(f"Progress: {json.dumps(progress_data)}")
                logger.info(f"Created: {created}")
                logger.info(f"Performance: {performance}")
                yield json.dumps(progress_data) + '\n'
            except Exception as e:
                error_msg = f"Error processing year {year}: {str(e)}"
                logger.error(error_msg)
                logger.error(traceback.format_exc())
                yield json.dumps({'status': 'error', 'message': error_msg}) + '\n'

        logger.info("Finishing save_or_update_annual_broker_performance")
        yield json.dumps({'status': 'complete'}) + '\n'

    except Exception as e:
        error_msg = f"Unexpected error in save_or_update_annual_broker_performance: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        yield json.dumps({'status': 'error', 'message': error_msg}) + '\n'
