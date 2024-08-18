from datetime import date
from typing import Optional, Tuple

def get_date_range(timespan: str, to_date: date) -> Tuple[Optional[date], date]:
    """
    Get the date range based on the given timespan and end date.

    :param timespan: A string representing the timespan ('YTD', 'All-time', or a year as string)
    :param to_date: The end date of the range
    :return: A tuple containing the start date (or None for 'All-time') and the end date
    :raises ValueError: If an invalid timespan is provided
    """
    if timespan == 'YTD':
        return date(to_date.year, 1, 1), to_date
    elif timespan == 'All-time':
        return None, to_date
    else:
        try:
            year = int(timespan)
            return date(year, 1, 1), date(year, 12, 31)
        except ValueError:
            raise ValueError(f"Invalid timespan: {timespan}. Expected 'YTD', 'All-time', or a valid year.")