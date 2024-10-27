from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Optional, Tuple
import logging

from constants import YTD, ALL_TIME

logger = logging.getLogger(__name__)

def get_date_range(timespan: str, to_date: date) -> Tuple[Optional[date], date]:
    """
    Get the date range based on the given timespan and end date.

    :param timespan: A string representing the timespan ('YTD', 'All-time', or a year as string)
    :param to_date: The end date of the range
    :return: A tuple containing the start date (or None for 'All-time') and the end date
    :raises ValueError: If an invalid timespan is provided
    """

    if timespan == YTD:
        return date(to_date.year, 1, 1), to_date
    elif timespan == ALL_TIME:
        return None, to_date
    else:
        try:
            year = int(timespan)
            return date(year, 1, 1), date(year, 12, 31)
        except ValueError:
            logger.error(f"Invalid timespan: {timespan}. Expected {YTD}, {ALL_TIME}, or a valid year.")
            # raise ValueError(f"Invalid timespan: {timespan}. Expected {YTD}, {ALL_TIME}, or a valid year.")
            return date(to_date.year, 1, 1), to_date
        
def get_start_date(end_date, period):
    end_date = datetime.strptime(end_date, '%Y-%m-%d').date() if isinstance(end_date, str) else end_date
    if period == '7d':
        return end_date - timedelta(days=7)
    elif period == '1m':
        return end_date - relativedelta(months=1)
    elif period == '3m':
        return end_date - relativedelta(months=3)
    elif period == '6m':
        return end_date - relativedelta(months=6)
    elif period == '1Y':
        return end_date - relativedelta(years=1)
    elif period == '3Y':
        return end_date - relativedelta(years=3)
    elif period == '5Y':
        return end_date - relativedelta(years=5)
    elif period == 'ytd':
        return datetime(end_date.year, 1, 1)
    elif period == 'All':
        return None
    else:
        return end_date - relativedelta(years=1)  # Default to 1Y