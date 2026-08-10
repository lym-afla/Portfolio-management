"""Shared serializer definitions for drf-spectacular schema generation.

These serializers describe the response shape of function-based API views that
return complex dictionaries. They are used via ``@extend_schema(responses=...)``
so drf-spectacular can emit a usable OpenAPI schema for the frontend
``openapi-typescript`` codegen.

The shapes here are intentionally loose (``DictField``/``ListField``) where the
underlying data is heavily formatted (currency strings, nested aggregation
tables). The goal is a usable top-level contract, not a perfect model of every
nested field.
"""

from rest_framework import serializers


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


class MessageResponseSerializer(serializers.Serializer):
    """Generic ``{"message": ...}`` / ``{"error": ...}`` response."""

    message = serializers.CharField(required=False)
    error = serializers.CharField(required=False)


class SuccessResponseSerializer(serializers.Serializer):
    """Generic ``{"success": bool, "message": str}`` response."""

    success = serializers.BooleanField(required=False)
    message = serializers.CharField(required=False)


class TokenRefreshResponseSerializer(serializers.Serializer):
    """Response of the custom JWT refresh endpoint."""

    access = serializers.CharField(required=False)
    refresh = serializers.CharField(required=False)
    effective_current_date = serializers.CharField(required=False)
    error = serializers.CharField(required=False)


# ---------------------------------------------------------------------------
# Common app
# ---------------------------------------------------------------------------


class EffectiveCurrentDateResponseSerializer(serializers.Serializer):
    """Response of ``api/effective-current-date/``."""

    effective_current_date = serializers.CharField()


class YearOptionsResponseSerializer(serializers.Serializer):
    """Response of ``api/get-year-options/``."""

    table_years = serializers.ListField(child=serializers.DictField())


# ---------------------------------------------------------------------------
# Dashboard app
# ---------------------------------------------------------------------------


class DashboardSummaryResponseSerializer(serializers.Serializer):
    """Response of ``dashboard/api/get-summary/``.

    Keys are dynamic metric names (e.g. ``Current NAV``, ``Invested``) mapped to
    formatted string values.
    """

    metrics = serializers.DictField(child=serializers.CharField(allow_null=True, required=False))


class DashboardBreakdownResponseSerializer(serializers.Serializer):
    """Response of ``dashboard/api/get-breakdown/``."""

    assetType = serializers.DictField()
    currency = serializers.DictField()
    assetClass = serializers.DictField()
    totalNAV = serializers.CharField(allow_null=True)


class DashboardSummaryOverTimeResponseSerializer(serializers.Serializer):
    """Response of ``dashboard/api/get-summary-over-time/``."""

    years = serializers.ListField(child=serializers.IntegerField())
    lines = serializers.ListField(child=serializers.DictField())
    currentYear = serializers.CharField()


class NavChartDataResponseSerializer(serializers.Serializer):
    """Response of ``dashboard/api/get-nav-chart-data/``."""

    labels = serializers.ListField(child=serializers.CharField())
    datasets = serializers.ListField(child=serializers.DictField())
    currency = serializers.CharField(allow_null=True)
    empty = serializers.BooleanField(required=False)


# ---------------------------------------------------------------------------
# Positions (open / closed)
# ---------------------------------------------------------------------------


class PositionsTableResponseSerializer(serializers.Serializer):
    """Response of open/closed positions table endpoints.

    The portfolio payload is a list of row dicts; totals is a single dict.
    Field names differ between open/closed variants, so they are exposed as
    loose dict fields. ``portfolio_open`` / ``portfolio_closed`` keys are
    returned depending on the endpoint.
    """

    portfolio_open = serializers.ListField(child=serializers.DictField(), required=False)
    portfolio_open_totals = serializers.DictField(required=False)
    portfolio_closed = serializers.ListField(child=serializers.DictField(), required=False)
    portfolio_closed_totals = serializers.DictField(required=False)
    total_items = serializers.IntegerField(allow_null=True, required=False)
    current_page = serializers.IntegerField(allow_null=True, required=False)
    total_pages = serializers.IntegerField(allow_null=True, required=False)
    cash_balances = serializers.DictField(allow_null=True, required=False)


# ---------------------------------------------------------------------------
# Summary analysis
# ---------------------------------------------------------------------------


class SummaryDataResponseSerializer(serializers.Serializer):
    """Response of ``summary/api/summary_data/``."""

    public_markets_context = serializers.DictField()
    restricted_investments_context = serializers.DictField()
    total_context = serializers.DictField()
