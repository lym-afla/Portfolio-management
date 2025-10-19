"""Common views."""

from datetime import datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.models import Transactions
from constants import ALL_TIME, YTD
from core.portfolio_utils import (
    get_last_exit_date_for_accounts,
    get_selected_account_ids,
)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_year_options_api(request) -> Response:
    """Get year options API."""
    user = request.user
    selected_account_ids = get_selected_account_ids(
        user, user.selected_account_type, user.selected_account_id
    )

    # Use JWT middleware instead of session
    effective_current_date_str = getattr(request, "effective_current_date", None)

    # Convert effective_current_date from string to date object
    effective_current_date = (
        datetime.strptime(effective_current_date_str, "%Y-%m-%d").date()
        if effective_current_date_str
        else datetime.now().date()
    )

    first_year = (
        Transactions.objects.filter(investor=user, account_id__in=selected_account_ids)
        .order_by("date")
        .first()
    )

    if first_year:
        first_year = first_year.date.year

    last_exit_date = get_last_exit_date_for_accounts(
        selected_account_ids, effective_current_date
    )
    last_year = (
        last_exit_date.year
        if last_exit_date and last_exit_date.year < effective_current_date.year
        else effective_current_date.year - 1
    )

    if first_year is not None:
        table_years = list(range(first_year, last_year + 1))
    else:
        table_years = []

    # Convert years to strings
    table_years = [{"text": str(year), "value": str(year)} for year in table_years]

    # Add special options with a divider
    table_years.extend(
        [
            {"divider": True},
            {"text": "All-time", "value": ALL_TIME},
            {"text": f"{effective_current_date.year}YTD", "value": YTD},
        ]
    )

    return Response(
        {
            "table_years": table_years,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_effective_current_date(request):
    """Get effective current date."""
    import structlog

    logger = structlog.get_logger(__name__)

    # Use JWT middleware instead of session
    effective_current_date = getattr(
        request, "effective_current_date", datetime.now().date().isoformat()
    )

    logger.info(
        "get_effective_current_date called (JWT mode)",
        effective_current_date=effective_current_date,
        has_jwt_middleware=getattr(request, "effective_current_date", None) is not None,
    )

    return Response({"effective_current_date": effective_current_date})
