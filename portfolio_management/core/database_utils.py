import logging
from datetime import date, datetime
from django.db import OperationalError, transaction
import asyncio
from channels.db import database_sync_to_async

from core.portfolio_utils import get_selected_account_ids
from common.models import Transactions, AnnualPerformance
from core.portfolio_utils import get_last_exit_date_for_broker_accounts, calculate_performance

logger = logging.getLogger(__name__)

async def save_or_update_annual_broker_performance(user, effective_date, account_group_type, account_group_id, currency_target, is_restricted=None, skip_existing_years=False):
    logger.info(f"Starting performance calculation for {account_group_type}, {account_group_id}, {currency_target}, is_restricted={is_restricted}, skip_existing_years={skip_existing_years}")
    
    selected_account_ids = await database_sync_to_async(get_selected_account_ids)(user, account_group_type, account_group_id)
    
    # Determine the starting year
    first_transaction = await database_sync_to_async(lambda: Transactions.objects.filter(
        broker_account_id__in=selected_account_ids, 
        date__lte=effective_date
    ).order_by('date').first())()
    
    if not first_transaction:
        error_msg = 'No transactions found'
        logger.error(error_msg)
        yield {'status': 'error', 'message': error_msg, 'timestamp': datetime.now().isoformat()}
        return
    
    start_year = first_transaction.date.year
    last_exit_date = await database_sync_to_async(get_last_exit_date_for_broker_accounts)(selected_account_ids, effective_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_date.year else effective_date.year - 1
    years = list(range(start_year, last_year + 1))

    logger.info(f"Calculating performance for {len(years)} years. First transaction: {first_transaction.date}, last exit date: {last_exit_date}")

    for i, year in enumerate(years, 1):
        if skip_existing_years:
            exists = await database_sync_to_async(lambda: AnnualPerformance.objects.filter(
                investor=user, 
                account_type=account_group_type,
                account_id=account_group_id,
                year=year, 
                currency=currency_target, 
                restricted=is_restricted
            ).exists())()
            
            if exists:
                logger.info(f"Skipping existing year {year}")
                continue

        try:
            performance_data = await database_sync_to_async(calculate_performance)(
                user, 
                date(year, 1, 1), 
                date(year, 12, 31), 
                account_group_type, 
                account_group_id, 
                currency_target, 
                is_restricted
            )
            
            # Use a separate function to save the data
            await save_annual_performance(user, account_group_type, account_group_id, year, currency_target, is_restricted, performance_data)
            
            yield {
                'status': 'progress',
                'year': year,
                'timestamp': datetime.now().isoformat()
            }
        except ValueError as e:
            if "No FX rate found" in str(e):
                error_msg = f"Missing FX rate processing year {year}: {str(e)}"
                logger.error(error_msg)
                yield {'status': 'error', 'message': error_msg, 'timestamp': datetime.now().isoformat()}
            else:
                raise

    yield {'status': 'complete', 'timestamp': datetime.now().isoformat()}

async def save_annual_performance(user, account_group_type, account_group_id, year, currency_target, is_restricted, performance_data):
    max_retries = 3
    retry_delay = 1  # second

    @database_sync_to_async
    def update_or_create():
        with transaction.atomic():
            AnnualPerformance.objects.update_or_create(
                investor=user,
                account_type=account_group_type,
                account_id=account_group_id,
                year=year,
                currency=currency_target,
                restricted=is_restricted,
                defaults=performance_data
            )

    for attempt in range(max_retries):
        try:
            await update_or_create()
            logger.info(f"AnnualPerformance saved for year {year}")
            return
        except OperationalError as e:
            if 'database is locked' in str(e) and attempt < max_retries - 1:
                logger.warning(f"Database locked, retrying in {retry_delay} seconds (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(retry_delay)
            else:
                raise

    logger.error(f"Failed to save AnnualPerformance for year {year} after {max_retries} attempts")
    raise OperationalError(f"Database locked, unable to save data for year {year}")

def get_years_count(user, effective_date, account_group_type, account_group_id):
    selected_account_ids = get_selected_account_ids(
        user,
        account_group_type,
        account_group_id,
    )
    first_transaction = Transactions.objects.filter(
        broker_account_id__in=selected_account_ids, 
        date__lte=effective_date
    ).order_by('date').first()
    
    if not first_transaction:
        return 0
        
    start_year = first_transaction.date.year
    last_exit_date = get_last_exit_date_for_broker_accounts(selected_account_ids, effective_date)
    last_year = last_exit_date.year if last_exit_date and last_exit_date.year < effective_date.year else effective_date.year - 1
    
    return last_year - start_year + 1