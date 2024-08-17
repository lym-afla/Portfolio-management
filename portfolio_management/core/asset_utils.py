from django.db.models import Q, Sum
from django.db.models.functions import Abs
from typing import List

from common.models import Assets
from constants import TOLERANCE

def filter_assets(user, end_date, selected_brokers, is_closed: bool, search: str) -> List[Assets]:
    """
    Filter assets based on user, date, brokers, closed status, and search query.

    :param user: The user whose assets to filter
    :param end_date: The end date for transactions
    :param selected_brokers: List of broker IDs to filter by
    :param is_closed: Boolean indicating whether to filter for closed positions
    :param search: Search string for asset name or type
    :return: List of filtered Asset objects
    """
    assets = Assets.objects.filter(
        investor=user,
        transactions__date__lte=end_date,
        transactions__broker_id__in=selected_brokers,
        transactions__quantity__isnull=False
    ).distinct()

    if search:
        assets = assets.filter(Q(name__icontains=search) | Q(type__icontains=search))

    if is_closed:
        return [asset for asset in assets if len(asset.exit_dates(end_date)) != 0]
    else:
        return assets.annotate(
            abs_total_quantity=Abs(Sum('transactions__quantity'))
        ).exclude(
            abs_total_quantity__lt=TOLERANCE
        )
