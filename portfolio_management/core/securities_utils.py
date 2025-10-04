from datetime import datetime

from django.db.models import Q
from django.shortcuts import get_object_or_404

from common.models import Assets
from core.portfolio_utils import IRR

from .formatting_utils import format_table_data, format_value
from .pagination_utils import paginate_table
from .sorting_utils import sort_entries


def get_securities_table_api(request):
    data = request.data
    page = int(data.get("page"))
    items_per_page = int(data.get("itemsPerPage"))
    search = data.get("search", "")
    sort_by = data.get("sortBy", {})

    user = request.user
    effective_current_date = datetime.strptime(
        request.session["effective_current_date"], "%Y-%m-%d"
    ).date()
    number_of_digits = user.digits

    securities_data = _filter_securities(user, search)
    securities_data = _get_securities_data(user, securities_data, effective_current_date)
    securities_data = sort_entries(securities_data, sort_by)
    paginated_securities, pagination_data = paginate_table(securities_data, page, items_per_page)
    formatted_securities = [
        {k: format_value(v, k, position["currency"], number_of_digits) for k, v in position.items()}
        for position in paginated_securities.object_list
    ]

    return {
        "securities": formatted_securities,
        "total_items": pagination_data["total_items"],
        "current_page": pagination_data["current_page"],
        "total_pages": pagination_data["total_pages"],
    }


def _filter_securities(user, search):
    securities = Assets.objects.filter(investors__id=user.id)
    if search:
        # Create Q objects for each field we want to search
        search_query = (
            Q(name__icontains=search) | Q(ISIN__icontains=search) | Q(currency__icontains=search)
        )

        securities = securities.filter(search_query)

    return securities


def _get_securities_data(user, securities, effective_current_date):
    securities_data = []
    for security in securities:
        security_data = {
            "id": security.id,
            "type": security.type,
            "ISIN": security.ISIN,
            "name": security.name,
            "first_investment": security.investment_date(user) or "None",
            "currency": security.currency,
            "open_position": security.position(effective_current_date, user),
            "current_value": security.calculate_value_at_date(
                effective_current_date, user, security.currency
            ),
            "realized": security.realized_gain_loss(effective_current_date, user)["all_time"][
                "total"
            ],
            "unrealized": security.unrealized_gain_loss(effective_current_date, user)["total"],
            "capital_distribution": security.get_capital_distribution(effective_current_date, user),
            "irr": IRR(user.id, effective_current_date, security.currency, asset_id=security.id),
        }

        securities_data.append(security_data)
    return securities_data


def get_security_detail(request, security_id):
    user = request.user
    effective_current_date = datetime.strptime(
        request.session["effective_current_date"], "%Y-%m-%d"
    ).date()
    number_of_digits = user.digits

    security = get_object_or_404(Assets, id=security_id, investors__id=user.id)

    security_data = {
        "id": security.id,
        "type": security.type,
        "ISIN": security.ISIN,
        "name": security.name,
        "first_investment": security.investment_date(user) or "None",
        "currency": security.currency,
        "open_position": security.position(effective_current_date, user),
        "current_value": security.calculate_value_at_date(
            effective_current_date, user, security.currency
        ),
        "realized": security.realized_gain_loss(effective_current_date, user)["all_time"]["total"],
        "unrealized": security.unrealized_gain_loss(effective_current_date, user)["total"],
        "capital_distribution": security.get_capital_distribution(effective_current_date, user),
        "irr": IRR(user.id, effective_current_date, security.currency, asset_id=security.id),
        "data_source": security.data_source,
        "update_link": security.update_link,
        "yahoo_symbol": security.yahoo_symbol,
        "comment": security.comment,
    }

    return format_table_data([security_data], security.currency, number_of_digits)[0]


def get_security_transactions(request, security_id):
    # Implement logic to fetch and return recent transactions data
    pass
