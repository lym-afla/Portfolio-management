"""Dashboard views."""

import decimal
import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from django.db import DatabaseError
from django.db.models import Sum
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.models import AnnualPerformance, Transactions
from common.schema_serializers import (
    DashboardBreakdownResponseSerializer,
    DashboardSummaryOverTimeResponseSerializer,
    DashboardSummaryResponseSerializer,
    MessageResponseSerializer,
    NavChartDataResponseSerializer,
)
from services.charts import (
    CHART_CONTRACT_VERSION,
    CHART_FREQUENCIES,
    CHART_NAV_MODES,
    build_allocation_document,
    chart_error_body,
    get_nav_chart_data,
)
from core.formatting_utils import currency_format, format_percentage, format_table_data
from services.fx import get_rate as fx_get_rate
from services.nav import IRR, NAV_at_date
from services.performance import (
    calculate_percentage_shares,
    calculate_performance,
    get_last_exit_date_for_accounts,
    get_selected_account_ids,
)

logger = logging.getLogger(__name__)


def _requested_chart_contract(request):
    """Parse the explicit chart contract negotiation parameter.

    Returns ``(version, error_response)`` — exactly one is None. Absent means
    legacy; anything other than the supported version is an explicit client
    error, never a silent downgrade to legacy.
    """
    raw = request.GET.get("chart_contract")
    if raw is None:
        return None, None
    if raw != str(CHART_CONTRACT_VERSION):
        return None, Response(
            chart_error_body(
                "INVALID_CHART_QUERY",
                "Unsupported chart contract version; this server serves version "
                f"{CHART_CONTRACT_VERSION}.",
                False,
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )
    return CHART_CONTRACT_VERSION, None


def _chart_context(user, account_selection_type, account_selection_id, account_ids,
                   effective_date, currency, digits):
    return {
        "accountSelection": {"type": account_selection_type, "id": account_selection_id},
        "accountIds": list(account_ids),
        "effectiveDate": effective_date,
        "currency": currency,
        "digits": digits,
    }


@extend_schema(
    responses={
        200: DashboardSummaryResponseSerializer,
        500: MessageResponseSerializer,
    }
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_dashboard_summary_api(request):
    """Get dashboard summary API."""
    user = request.user
    # Use JWT middleware instead of session
    effective_current_date_str = getattr(
        request, "effective_current_date", datetime.now().date().isoformat()
    )
    effective_current_date = datetime.strptime(effective_current_date_str, "%Y-%m-%d").date()

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

    query_effective_current_date = effective_current_date
    transactions = (
        Transactions.objects.filter(
            investor=user,
            account_id__in=selected_account_ids,
            date__date__lte=query_effective_current_date,
            type__in=["Cash in", "Cash out"],
        )
        .values("currency", "type", "cash_flow", "date")
        .annotate(total=Sum("cash_flow"))
    )

    for transaction in transactions:
        fx_rate = fx_get_rate(transaction["currency"], currency_target, transaction["date"], user)[
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
    """Get dashboard breakdown API."""
    user = request.user
    contract_version, contract_error = _requested_chart_contract(request)
    if contract_error is not None:
        return contract_error
    # Use JWT middleware instead of session
    effective_current_date_str = getattr(
        request, "effective_current_date", datetime.now().date().isoformat()
    )
    effective_current_date = datetime.strptime(effective_current_date_str, "%Y-%m-%d").date()

    currency_target = user.default_currency
    number_of_digits = user.digits
    selected_account_ids = get_selected_account_ids(
        user, user.selected_account_type, user.selected_account_id
    )

    breakdown_diagnostics = [] if contract_version is not None else None
    nav_kwargs = {"diagnostics": breakdown_diagnostics} if contract_version is not None else {}
    analysis = NAV_at_date(
        user.id,
        tuple(selected_account_ids),
        effective_current_date,
        currency_target,
        tuple(["asset_type", "currency", "asset_class"]),
        **nav_kwargs,
    )

    if contract_version is not None:
        context = _chart_context(
            user,
            user.selected_account_type,
            user.selected_account_id,
            selected_account_ids,
            effective_current_date_str,
            currency_target,
            number_of_digits,
        )
        dimensions = {"assetType": "asset_type", "assetClass": "asset_class",
                      "currency": "currency"}
        chart_v2 = {
            key: build_allocation_document(
                dimension,
                analysis,
                currency=currency_target,
                digits=number_of_digits,
                diagnostics=breakdown_diagnostics,
                effective_date=effective_current_date,
                context=context,
            )
            for key, dimension in dimensions.items()
        }
    else:
        chart_v2 = None

    print(f"Analysis: {analysis}")
    # Extract 'Total NAV' from the analysis
    total_nav = analysis.get("Total NAV", None)

    # Calculate percentage breakdowns
    calculate_percentage_shares(analysis, ["asset_type", "currency", "asset_class"])

    # Format the values
    analysis = format_table_data(analysis, currency_target, number_of_digits)

    payload = {
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
    if chart_v2 is not None:
        payload["chartV2"] = chart_v2
    return Response(payload)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_dashboard_summary_over_time_api(request):
    """Get dashboard summary over time API."""
    try:
        user = request.user
        effective_current_date_str = getattr(
            request, "effective_current_date", datetime.now().date().isoformat()
        )
        effective_current_date = datetime.strptime(effective_current_date_str, "%Y-%m-%d").date()

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
            IRR(
                user.id,
                effective_current_date,
                currency_target,
                account_ids=selected_account_ids,
            ),
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
            {
                "years": years,
                "lines": list(lines.values()),
                "currentYear": str(current_year),
            },
            status=status.HTTP_200_OK,
        )

    except AnnualPerformance.DoesNotExist:
        return Response(
            {"error": "No annual performance data found."},
            status=status.HTTP_404_NOT_FOUND,
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
    """Prepare API nav chart data."""
    currency = None  # bound on the legacy error path below
    contract_version = None
    try:
        user = request.user
        frequency = request.GET.get("frequency")
        from_date = request.GET.get("dateFrom")
        to_date = request.GET.get("dateTo")
        breakdown = request.GET.get("breakdown")
        currency = user.default_currency
        contract_version, contract_error = _requested_chart_contract(request)
        if contract_error is not None:
            return contract_error
        selected_account_ids = get_selected_account_ids(
            user, user.selected_account_type, user.selected_account_id
        )

        if not to_date:
            # Use JWT middleware instead of session
            effective_current_date_str = getattr(
                request, "effective_current_date", datetime.now().date().isoformat()
            )
            to_date = datetime.strptime(effective_current_date_str, "%Y-%m-%d").date().isoformat()

        if contract_version is not None:
            # v2 validates the query explicitly instead of returning an empty
            # legacy payload for invalid inputs.
            if frequency not in CHART_FREQUENCIES:
                return Response(
                    chart_error_body(
                        "INVALID_CHART_QUERY", "Unsupported chart frequency.", False
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if breakdown not in CHART_NAV_MODES:
                return Response(
                    chart_error_body(
                        "INVALID_CHART_QUERY", "Unsupported chart breakdown mode.", False
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                parsed_from = date.fromisoformat(from_date) if from_date else None
                parsed_to = date.fromisoformat(to_date)
            except (TypeError, ValueError):
                return Response(
                    chart_error_body(
                        "INVALID_CHART_QUERY", "Chart dates must be ISO dates.", False
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if parsed_from is not None and parsed_from > parsed_to:
                return Response(
                    chart_error_body(
                        "INVALID_CHART_QUERY",
                        "Chart start date must not be after the end date.",
                        False,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Handle case where no accounts are selected
        if not selected_account_ids:
            payload = {
                "labels": [],
                "datasets": [],
                "currency": currency + "k",
                "empty": True,
            }
            if contract_version is not None:
                payload["chartV2"] = {
                    "version": 2,
                    "kind": "nav",
                    "outcome": "empty",
                    "context": _chart_context(
                        user,
                        user.selected_account_type,
                        user.selected_account_id,
                        [],
                        to_date,
                        currency,
                        user.digits,
                    ),
                    "periods": [],
                    "series": [],
                    "totals": [],
                    "partition": "complete",
                }
            return Response(payload)

        chart_v2 = None
        if contract_version is not None:
            chart_v2 = {
                "version": 2,
                "kind": "nav",
                "context": _chart_context(
                    user,
                    user.selected_account_type,
                    user.selected_account_id,
                    selected_account_ids,
                    to_date,
                    currency,
                    user.digits,
                ),
            }

        # from_date can be None, it will be handled in get_nav_chart_data
        try:
            chart_data = get_nav_chart_data(
                user.id,
                selected_account_ids,
                frequency,
                from_date,
                to_date,
                currency,
                breakdown,
                chart_v2=chart_v2,
                display_digits=user.digits,
            )
        except ValueError as identity_error:
            if contract_version is not None:
                logger.error(f"Chart category identity failure: {identity_error}")
                return Response(
                    chart_error_body(
                        "CHART_CALCULATION_FAILED",
                        "Chart data could not be certified for this selection.",
                        False,
                    ),
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            raise
        if contract_version is not None:
            chart_data["chartV2"] = chart_v2
        return Response(chart_data)

    except Exception as e:
        if contract_version is not None:
            logger.error(f"Error generating NAV chart data: {e}")
            return Response(
                chart_error_body(
                    "CHART_CALCULATION_FAILED",
                    "Chart data could not be calculated. Please try again.",
                    True,
                ),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        logger.error(f"Error generating NAV chart data: {e}")
        return Response({"labels": [], "datasets": [], "currency": currency + "k", "empty": True})
