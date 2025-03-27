import decimal
import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from django.db import DatabaseError
from django.db.models import Sum
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.models import FX, AnnualPerformance, Transactions
from core.chart_utils import get_nav_chart_data
from core.formatting_utils import currency_format, format_percentage, format_table_data
from core.portfolio_utils import (
    IRR,
    NAV_at_date,
    calculate_percentage_shares,
    calculate_performance,
    get_last_exit_date_for_accounts,
    get_selected_account_ids,
)

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_dashboard_summary_api(request):
    user = request.user
    effective_current_date = datetime.strptime(
        request.session["effective_current_date"], "%Y-%m-%d"
    ).date()

    currency_target = user.default_currency
    number_of_digits = user.digits

    selected_account_ids = get_selected_account_ids(
        user, user.selected_account_type, user.selected_account_id
    )

    summary = {}

    # Calculate NAV
    summary["Current NAV"] = NAV_at_date(
        user.id, tuple(selected_account_ids), effective_current_date, currency_target
    )["Total NAV"]

    # Calculate Invested and Cash-out
    summary["Invested"] = Decimal(0)
    summary["Cash-out"] = Decimal(0)

    transactions = (
        Transactions.objects.filter(
            investor=user,
            account_id__in=selected_account_ids,
            date__lte=effective_current_date,
            type__in=["Cash in", "Cash out"],
        )
        .values("currency", "type", "cash_flow", "date")
        .annotate(total=Sum("cash_flow"))
    )

    for transaction in transactions:
        fx_rate = FX.get_rate(transaction["currency"], currency_target, transaction["date"], user)[
            "FX"
        ]
        if transaction["type"] == "Cash in":
            summary["Invested"] += Decimal(transaction["total"]) * Decimal(fx_rate)
        else:
            summary["Cash-out"] += Decimal(transaction["total"]) * Decimal(fx_rate)

    # Calculate IRR and Return
    try:
        if summary["Invested"] == 0:
            summary["total_return"] = None
        else:
            summary["total_return"] = (summary["Current NAV"] - summary["Cash-out"]) / summary[
                "Invested"
            ] - 1
    except (ZeroDivisionError, decimal.InvalidOperation):
        summary["total_return"] = None

    summary["irr"] = IRR(
        user.id,
        effective_current_date,
        currency_target,
        asset_id=None,
        account_ids=selected_account_ids,
    )

    summary = format_table_data(summary, currency_target, number_of_digits)
    return Response(summary)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_dashboard_breakdown_api(request):
    user = request.user
    effective_current_date = datetime.strptime(
        request.session["effective_current_date"], "%Y-%m-%d"
    ).date()

    currency_target = user.default_currency
    number_of_digits = user.digits
    selected_account_ids = get_selected_account_ids(
        user, user.selected_account_type, user.selected_account_id
    )

    analysis = NAV_at_date(
        user.id,
        tuple(selected_account_ids),
        effective_current_date,
        currency_target,
        tuple(["asset_type", "currency", "asset_class"]),
    )
    print(f"Analysis: {analysis}")
    # Extract 'Total NAV' from the analysis
    total_nav = analysis.get("Total NAV", None)

    # Calculate percentage breakdowns
    calculate_percentage_shares(analysis, ["asset_type", "currency", "asset_class"])

    # Format the values
    analysis = format_table_data(analysis, currency_target, number_of_digits)

    return Response(
        {
            "assetType": {
                "data": analysis["asset_type"],
                "percentage": analysis["asset_type_percentage"],
            },
            "currency": {
                "data": analysis["currency"],
                "percentage": analysis["currency_percentage"],
            },
            "assetClass": {
                "data": analysis["asset_class"],
                "percentage": analysis["asset_class_percentage"],
            },
            "totalNAV": currency_format(total_nav, currency_target, number_of_digits),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_dashboard_summary_over_time_api(request):
    try:
        user = request.user
        effective_current_date = datetime.strptime(
            request.session["effective_current_date"], "%Y-%m-%d"
        ).date()

        currency_target = user.default_currency
        selected_account_ids = get_selected_account_ids(
            user, user.selected_account_type, user.selected_account_id
        )

        # Determine the starting year
        stored_data = AnnualPerformance.objects.select_related("investor").filter(
            investor=user,
            account_type=user.selected_account_type,
            account_id=user.selected_account_id,
            currency=currency_target,
            restricted=None,
        )

        first_entry = stored_data.order_by("year").first()
        if not first_entry:
            return Response(
                {"message": "No data available for the selected period."},
                status=status.HTTP_404_NOT_FOUND,
            )

        start_year = first_entry.year
        last_exit_date = get_last_exit_date_for_accounts(
            selected_account_ids, effective_current_date
        )
        last_year = (
            last_exit_date.year
            if last_exit_date and last_exit_date.year < effective_current_date.year
            else effective_current_date.year - 1
        )
        years = list(range(start_year, last_year + 1))

        line_names = [
            "BoP NAV",
            "Invested",
            "Cash out",
            "Price change",
            "Capital distribution",
            "Commission",
            "Tax",
            "FX",
            "EoP NAV",
            "TSR",
        ]

        lines = defaultdict(lambda: {"name": "", "data": {}})
        for name in line_names:
            lines[name]["name"] = name

        # Fetch stored data
        stored_data = stored_data.filter(year__in=years).values_list(
            "year", *[name.lower().replace(" ", "_") for name in line_names]
        )

        # Process stored data
        processed_data = {
            entry[0]: {line_names[i]: entry[i + 1] for i in range(len(line_names))}
            for entry in stored_data
        }

        for line_name in line_names:
            lines[line_name]["data"] = {
                year: processed_data[year][line_name] for year in processed_data
            }

        # Calculate YTD for the current year
        current_year = effective_current_date.year
        ytd_data = calculate_performance(
            user,
            date(current_year, 1, 1),
            effective_current_date,
            user.selected_account_type,
            user.selected_account_id,
            currency_target,
        )

        for line_name in line_names:
            ytd_field_name = line_name.lower().replace(" ", "_")
            lines[line_name]["data"]["YTD"] = ytd_data[ytd_field_name]

        # Calculate All-time data
        for line_name, line_data in lines.items():
            if line_name != "TSR":
                line_data["data"]["All-time"] = sum(
                    value for year, value in line_data["data"].items() if year != "All-time"
                )

        lines["TSR"]["data"]["All-time"] = format_percentage(
            IRR(user.id, effective_current_date, currency_target, account_ids=selected_account_ids),
            digits=1,
        )
        lines["BoP NAV"]["data"]["All-time"] = Decimal(0)
        lines["EoP NAV"]["data"]["All-time"] = lines["EoP NAV"]["data"].get("YTD", Decimal(0))

        # Format the data
        format_funcs = {
            Decimal: lambda v: currency_format(v, currency_target, user.digits),
            float: lambda v: f"{v:.2%}",
        }

        for line in lines.values():
            line["data"] = {
                year: format_funcs.get(type(value), str)(value)
                for year, value in line["data"].items()
            }

        return Response(
            {"years": years, "lines": list(lines.values()), "currentYear": str(current_year)},
            status=status.HTTP_200_OK,
        )

    except AnnualPerformance.DoesNotExist:
        return Response(
            {"error": "No annual performance data found."}, status=status.HTTP_404_NOT_FOUND
        )
    except DatabaseError:
        return Response(
            {"error": "Database error occurred while fetching data"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except KeyError:
        return Response({"error": "Invalid session data"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response(
            {"error": f"An unexpected error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_nav_chart_data(request):
    try:
        user = request.user
        frequency = request.GET.get("frequency")
        from_date = request.GET.get("dateFrom")
        to_date = request.GET.get("dateTo")
        breakdown = request.GET.get("breakdown")
        currency = user.default_currency
        selected_account_ids = get_selected_account_ids(
            user, user.selected_account_type, user.selected_account_id
        )

        # Handle case where no accounts are selected
        if not selected_account_ids:
            return Response(
                {"labels": [], "datasets": [], "currency": currency + "k", "empty": True}
            )

        if not to_date:
            to_date = (
                datetime.strptime(request.session["effective_current_date"], "%Y-%m-%d")
                .date()
                .isoformat()
            )

        # from_date can be None, it will be handled in get_nav_chart_data
        chart_data = get_nav_chart_data(
            user.id, selected_account_ids, frequency, from_date, to_date, currency, breakdown
        )
        return Response(chart_data)

    except Exception as e:
        logger.error(f"Error generating NAV chart data: {e}")
        return Response({"labels": [], "datasets": [], "currency": currency + "k", "empty": True})
