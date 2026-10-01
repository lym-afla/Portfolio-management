"""
Utility functions for generating chart data and visualizations.

This module provides functions to calculate and format data for various charts
including NAV (Net Asset Value) charts, performance charts, and other visualizations.

The chart contract v2 (C1) adds opt-in exact metadata beside the legacy
payloads: raw Decimal strings, backend-scaled plot values, exact sampled ISO
dates, stable source identities, explicit units/statuses and readable errors.
Legacy responses are untouched unless a caller explicitly negotiates v2.
"""

import calendar
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from django.db.models import Min

from common.models import Accounts, Transactions
from constants import ASSET_TYPE_CHOICES, EXPOSURE_CHOICES
from core.formatting_utils import currency_format, format_percentage
from services.nav import IRR, NAV_at_date, get_fx_rate

logger = logging.getLogger("dashboard")

CHART_CONTRACT_VERSION = 2
CHART_FREQUENCIES = ("D", "W", "M", "Q", "Y")
CHART_NAV_MODES = (
    "none",
    "account",
    "asset_type",
    "asset_class",
    "currency",
    "value_contributions",
    "value_contributions_cumulative",
)
CHART_CATEGORY_MODES = ("account", "asset_type", "asset_class", "currency")

_VALID_ASSET_TYPE_CODES = {code for code, _ in ASSET_TYPE_CHOICES} | {"Cash"}
_VALID_ASSET_CLASS_CODES = (
    {code for code, _ in EXPOSURE_CHOICES}
    | {label for _, label in EXPOSURE_CHOICES}
    | {"Cash"}
)


def chart_error_body(code, message, retryable):
    """Build the v2 chart error envelope shared by the chart endpoints."""
    return {"error": {"code": code, "message": message, "retryable": retryable}}


# ---------------------------------------------------------------------------
# Chart contract v2: exact Decimal chart values (C1)
# ---------------------------------------------------------------------------


def decimal_chart_value(value, *, divisor=Decimal("1"), display, reason="observed"):
    """Capture an exact Decimal chart value with a backend-scaled plot value.

    ``value`` is the raw complete value in the series' stated unit;
    ``plotValue`` is the same value pre-scaled (``value / divisor``) so the
    frontend never divides monetary values. Both are emitted in canonical
    fixed decimal notation (never scientific), preserving meaningful
    precision and trailing zeros.
    """
    if not isinstance(value, Decimal):
        raise TypeError("Chart raw values must be Decimal")
    if not isinstance(divisor, Decimal):
        raise TypeError("Chart plot divisor must be Decimal")
    return {
        "value": format(value, "f"),
        "plotValue": format(value / divisor, "f"),
        "status": "ok",
        "reason": reason,
        "display": display,
    }


def unavailable_chart_value(status, reason, display, *, known_subtotal=None):
    """Build a non-ok chart value: unknown is never converted to zero."""
    result = {
        "value": None,
        "plotValue": None,
        "status": status,
        "reason": reason,
        "display": display,
    }
    if known_subtotal is not None:
        if status != "partial":
            raise ValueError("knownSubtotal is permitted only for partial values")
        if not isinstance(known_subtotal, Decimal):
            raise TypeError("Chart known subtotals must be Decimal")
        result["knownSubtotal"] = format(known_subtotal, "f")
    return result


def _unit_for(axis, currency, *, plot_divisor="1000"):
    if axis == "money":
        return {"kind": "money", "currency": currency, "plotDivisor": plot_divisor}
    if axis == "return":
        return {"kind": "ratio", "plotDivisor": "1"}
    if axis == "price":
        raise ValueError("price axis units are instrument-specific")
    if axis == "quantity":
        return {"kind": "quantity", "plotDivisor": "1"}
    raise ValueError(f"Unknown chart axis {axis!r}")


def _irr_chart_value(irr_result, *, omitted=False, reason="omitted_valuation"):
    """Map an IRR result (Decimal, 'N/A', 'N/R') to a chart value.

    An IRR computed against an incomplete terminal NAV is partial: the exact
    value cannot be certified, so ``value``/``plotValue`` stay null while the
    legacy-derived display string is preserved for the status-aware table.
    """
    if isinstance(irr_result, Decimal):
        display = format_percentage(irr_result, digits=1)
        if omitted:
            return unavailable_chart_value("partial", reason, display)
        return decimal_chart_value(irr_result, display=display)
    if irr_result == "N/A":
        return unavailable_chart_value("not_available", "solver_unavailable", "N/A")
    if irr_result == "N/R":
        return unavailable_chart_value("not_relevant", "not_relevant", "N/R")
    raise TypeError(f"Unsupported IRR result {irr_result!r}")


def _is_frequency_bucket_end(d, frequency):
    """Whether ``d`` is a complete calendar bucket end for ``frequency``."""
    if frequency == "D":
        return True
    if frequency == "W":
        return d.weekday() == 5  # W-SAT anchors
    if frequency == "M":
        return d.day == calendar.monthrange(d.year, d.month)[1]
    if frequency == "Q":
        return (
            d.month in (3, 6, 9, 12)
            and d.day == calendar.monthrange(d.year, d.month)[1]
        )
    if frequency == "Y":
        return d.month == 12 and d.day == 31
    return False


def _period_label(d, frequency):
    if frequency in ("D", "W"):
        return d.strftime("%d-%b-%y")
    if frequency == "M":
        return d.strftime("%b-%y")
    if frequency == "Q":
        return f'Q{(d.month - 1) // 3 + 1} {d.strftime("%y")}'
    if frequency == "Y":
        return d.strftime("%Y")
    return d.isoformat()


def _category_series_identity(mode, key, account_name_ids):
    """Resolve an authoritative breakdown key to a stable v2 series identity.

    Account groups derive their ID from the authorized account membership
    grouped by the exact current account name (legacy grouping preserved).
    Asset-type / asset-class codes are validated against the authoritative
    enums plus the explicit Cash bucket; unknown codes fail the contract
    rather than being renamed or hashed.
    """
    if mode == "account":
        member_ids = account_name_ids.get(key)
        if not member_ids:
            raise ValueError(
                f"No authorized account group matches breakdown label {key!r}"
            )
        return (
            "account-group:" + ",".join(str(i) for i in member_ids),
            {"kind": "account_group", "memberAccountIds": list(member_ids)},
        )
    if mode == "asset_type" and key not in _VALID_ASSET_TYPE_CODES:
        raise ValueError(f"Unknown asset type category {key!r}")
    if mode == "asset_class" and key not in _VALID_ASSET_CLASS_CODES:
        raise ValueError(f"Unknown asset class category {key!r}")
    return f"{mode}:{key}", {"kind": mode, "code": key}


def _diagnostic_category_key(mode, diagnostic, account_id_to_name):
    """Breakdown category affected by a NAV omission diagnostic, if any.

    Crypto-bucket omissions never map to a securities-side category (crypto
    is excluded from those breakdowns); they still make the total partial.
    """
    if diagnostic.get("asset_type") == "Crypto":
        return None
    if mode == "account":
        return account_id_to_name.get(diagnostic.get("account_id"))
    if mode == "asset_type":
        return diagnostic.get("asset_type")
    if mode == "asset_class":
        return diagnostic.get("asset_class")
    if mode == "currency":
        return diagnostic.get("currency")
    return None


_ABSENT_POINT = dict(
    value=None, plotValue=None, status="unknown",
    reason="absent_unclassified", display="–",
)


class _NavV2Collector:
    """Accumulates the v2 NAV chart contract beside the legacy sample loop."""

    _IRR_SERIES = (
        ("metric:irr_inception", "IRR (RHS)", "irr_inception", "line", "return"),
        ("metric:irr_interval", "Rolling IRR (RHS)", "irr_interval", "line", "return"),
    )
    _MODE_SERIES = {
        "none": (("metric:nav", "NAV", "nav", "bar", "money"),) + _IRR_SERIES,
        "value_contributions": (
            ("metric:opening_nav", "Previous NAV", "opening_nav", "bar", "money"),
            ("metric:contributions", "Contributions", "contributions", "bar", "money"),
            ("metric:return", "Return", "return", "bar", "money"),
        )
        + _IRR_SERIES,
        "value_contributions_cumulative": (
            ("metric:net_investments", "Net Investments", "net_investments", "bar", "money"),
            ("metric:return", "Return", "return", "bar", "money"),
        )
        + _IRR_SERIES,
    }

    def __init__(self, mode, currency, digits):
        self.mode = mode
        self.currency = currency
        self.digits = digits
        self.periods = []
        self.series = []
        self.series_by_id = {}
        self.totals = []
        self.outcome = "ready"
        self._nonpartitioning = False
        self._unknown = False
        for spec in self._MODE_SERIES.get(mode, ()):
            self._fixed_series(*spec)
        if "metric:irr_inception" not in self.series_by_id:
            for spec in self._IRR_SERIES:
                self._fixed_series(*spec)

    # -- series management --------------------------------------------------

    def _fixed_series(self, series_id, label, metric, role, axis):
        series = {
            "id": series_id,
            "label": label,
            "metric": metric,
            "role": role,
            "axis": axis,
            "unit": _unit_for(axis, self.currency),
            "points": [],
        }
        self.series.append(series)
        self.series_by_id[series_id] = series

    def category_series(self, key, identity):
        series_id, category_meta = identity
        series = self.series_by_id.get(series_id)
        if series is None:
            series = {
                "id": series_id,
                "label": key,
                "metric": "category_nav",
                "role": "bar",
                "axis": "money",
                "unit": _unit_for("money", self.currency),
                "points": [dict(_ABSENT_POINT) for _ in range(len(self.periods) - 1)],
                "category": category_meta,
            }
            # Keep the IRR series last, mirroring legacy dataset order.
            self.series.insert(len(self.series) - len(self._IRR_SERIES), series)
            self.series_by_id[series_id] = series
        return series

    # -- per-sample recording ------------------------------------------------

    def record_period(self, d, frequency, interval_start):
        iso = d.isoformat()
        self.periods.append(
            {
                "key": f"nav:{iso}",
                "endDate": iso,
                "displayLabel": _period_label(d, frequency),
                "interval": {
                    "startDate": interval_start.isoformat() if interval_start else None,
                    "endDate": iso,
                    "kind": "inception" if interval_start is None else "sample_interval",
                },
                "partialPeriod": not _is_frequency_bucket_end(d, frequency),
            }
        )

    def money_point(self, raw, *, omitted_reason=None):
        display = currency_format(raw, self.currency, self.digits)
        if omitted_reason:
            return unavailable_chart_value(
                "partial", omitted_reason, display, known_subtotal=raw
            )
        return decimal_chart_value(raw, divisor=Decimal("1000"), display=display)

    def record_total(self, raw_total, omitted_reason=None):
        self.totals.append(self.money_point(raw_total, omitted_reason=omitted_reason))
        if omitted_reason:
            self._unknown = True

    def record_money_series(self, series_id, raw, *, omitted_reason=None):
        self.series_by_id[series_id]["points"].append(
            self.money_point(raw, omitted_reason=omitted_reason)
        )

    def record_irrs(self, irr_inception, irr_interval, *, omitted=False, reason="omitted_valuation"):
        self.series_by_id["metric:irr_inception"]["points"].append(
            _irr_chart_value(irr_inception, omitted=omitted, reason=reason)
        )
        self.series_by_id["metric:irr_interval"]["points"].append(
            _irr_chart_value(irr_interval, omitted=omitted, reason=reason)
        )

    def record_absent(self, series_id):
        self.series_by_id[series_id]["points"].append(dict(_ABSENT_POINT))

    def record_category_sample(self, breakdown_data, affected):
        """Record this date's points for every known category series.

        ``affected`` maps category key -> omission reason for categories whose
        valuation was partially omitted; the legacy sum survives only as a
        partial knownSubtotal. Categories absent from this sample remain
        absent-unclassified, never zero.
        """
        for series in list(self.series):
            if series["metric"] != "category_nav":
                continue
            key = series["label"]
            if key in affected:
                reason = affected[key]
                self.series_by_id[series["id"]]["points"].append(
                    self.money_point(breakdown_data.get(key, Decimal(0)), omitted_reason=reason)
                )
            elif key in breakdown_data:
                self.record_money_series(series["id"], breakdown_data[key])
            else:
                self.record_absent(series["id"])

    def note_partition(self, covered, total):
        if covered != total:
            self._nonpartitioning = True

    def finish(self):
        if self._unknown:
            partition = "unknown"
        elif self._nonpartitioning:
            partition = "legacy_non_partitioning"
        else:
            partition = "complete"
        has_non_ok = any(
            point["status"] != "ok"
            for series in self.series
            for point in series["points"]
        ) or any(point["status"] != "ok" for point in self.totals)
        if self.outcome != "empty" and has_non_ok:
            self.outcome = "partial"
        return {
            "outcome": self.outcome,
            "periods": self.periods,
            "series": self.series,
            "totals": self.totals,
            "partition": partition,
        }


def get_nav_chart_data(
    user_id,
    account_ids,
    frequency,
    from_date,
    to_date,
    currency,
    breakdown,
    *,
    chart_v2=None,
    display_digits=2,
):
    """Calculate NAV chart data for a given user and date range.

    Args:
        user_id: The ID of the user to calculate NAV for.
        account_ids: Tuple of account IDs to include in calculation.
        frequency: The frequency of data points ('daily', 'weekly', 'monthly').
        from_date: Start date for the chart data.
        to_date: End date for the chart data.
        currency: Target currency for NAV calculations.
        breakdown: Whether to breakdown by asset type.
        chart_v2: Optional dict that receives the v2 chart contract document
            (everything except the ``version``/``kind``/``context`` the caller
            pre-filled): exact periods, series, totals, partition and outcome.
            When None, behavior and output are byte-identical to legacy.
        display_digits: User digit preference for v2 display strings.

    Returns:
        dict: Dictionary containing chart data with dates and NAV values.
    """
    # Ensure dates are date objects first
    from_date = date.fromisoformat(from_date) if isinstance(from_date, str) else from_date
    to_date = date.fromisoformat(to_date) if isinstance(to_date, str) else to_date

    collector = None
    if chart_v2 is not None:
        collector = _NavV2Collector(breakdown, currency, display_digits)
        if breakdown == "account":
            collector._account_name_ids = {}
            collector._account_id_to_name = {}
            for account in Accounts.objects.filter(
                id__in=account_ids, broker__investor__id=user_id
            ).order_by("id"):
                collector._account_id_to_name[account.id] = account.name
                collector._account_name_ids.setdefault(account.name, []).append(account.id)
        else:
            collector._account_name_ids = {}
            collector._account_id_to_name = {}

    def _v2_finalize_empty():
        if collector is not None:
            collector.outcome = "empty"
            collector.series = []
            collector.series_by_id = {}
            collector.totals = []
            collector.periods = []
            chart_v2.update(collector.finish())

    # Only get earliest date if from_date is None
    if from_date is None:
        earliest_date = _get_earliest_date_for_accounts(user_id, account_ids)
        if not earliest_date:
            _v2_finalize_empty()
            return {
                "labels": [],
                "datasets": [],
                "currency": currency + "k",
                "empty": True,
            }
        from_date = earliest_date

    # Validate dates
    if not from_date or not to_date or from_date > to_date:
        _v2_finalize_empty()
        return {"labels": [], "datasets": [], "currency": currency + "k", "empty": True}

    dates = _chart_dates(from_date, to_date, frequency)

    # logger.info(f"Chart dates: {dates}")
    # logger.info(f"Breakdown: {breakdown}")

    chart_data = {
        "labels": _chart_labels(dates, frequency),
        "datasets": [],
        "currency": currency + "k",
    }

    previous_date = None
    NAV_previous_date = None
    raw_nav_previous = None
    categories = {}

    # Initialize datasets based on breakdown type
    if breakdown == "none":
        chart_data["datasets"] = [
            _create_dataset("NAV", [], "rgba(75, 192, 192, 0.7)", "bar", "y"),
            _create_dataset("IRR (RHS)", [], "rgba(153, 102, 255, 1)", "line", "y1"),
            _create_dataset("Rolling IRR (RHS)", [], "rgba(255, 159, 64, 1)", "line", "y1"),
        ]
    elif breakdown == "value_contributions":
        chart_data["datasets"] = [
            _create_dataset(
                "Previous NAV",
                [],
                "rgba(75, 192, 192, 0.7)",
                "bar",
                "y",
                stack="combined",
            ),
            _create_dataset(
                "Contributions",
                [],
                "rgba(153, 102, 255, 0.7)",
                "bar",
                "y",
                stack="combined",
            ),
            _create_dataset("Return", [], "rgba(255, 159, 64, 0.7)", "bar", "y", stack="combined"),
            _create_dataset("IRR (RHS)", [], "rgba(75, 192, 192, 1)", "line", "y1"),
            _create_dataset("Rolling IRR (RHS)", [], "rgba(153, 102, 255, 1)", "line", "y1"),
        ]
    elif breakdown == "value_contributions_cumulative":
        # Fetch all transactions once at the beginning for cumulative calculations
        all_transactions = Transactions.objects.filter(
            investor__id=user_id,
            account_id__in=account_ids,
            type__in=["Cash in", "Cash out"],
            date__date__lte=to_date,
        )
        chart_data["datasets"] = [
            _create_dataset(
                "Net Investments",
                [],
                "rgba(75, 192, 192, 0.7)",
                "bar",
                "y",
                stack="combined",
            ),
            _create_dataset("Return", [], "rgba(255, 159, 64, 0.7)", "bar", "y", stack="combined"),
            _create_dataset("IRR (RHS)", [], "rgba(75, 192, 192, 1)", "line", "y1"),
            _create_dataset("Rolling IRR (RHS)", [], "rgba(153, 102, 255, 1)", "line", "y1"),
        ]
    else:
        chart_data["datasets"].extend(
            [
                _create_dataset("IRR (RHS)", [], "rgba(75, 192, 192, 1)", "line", "y1"),
                _create_dataset("Rolling IRR (RHS)", [], "rgba(153, 102, 255, 1)", "line", "y1"),
            ]
        )

    for sample_index, d in enumerate(dates):
        day_diagnostics = [] if collector is not None else None
        if collector is not None:
            NAV_data = NAV_at_date(
                user_id,
                tuple(account_ids),
                d,
                currency,
                (
                    tuple([breakdown])
                    if breakdown
                    not in ["none", "value_contributions", "value_contributions_cumulative"]
                    else ()
                ),
                diagnostics=day_diagnostics,
            )
        else:
            NAV_data = NAV_at_date(
                user_id,
                tuple(account_ids),
                d,
                currency,
                (
                    tuple([breakdown])
                    if breakdown
                    not in ["none", "value_contributions", "value_contributions_cumulative"]
                    else ()
                ),
            )
        NAV = NAV_data["Total NAV"] / 1000

        IRR_value = IRR(user_id, d, currency, account_ids=account_ids, cached_nav=NAV * 1000)
        IRR_rolling = IRR(
            user_id,
            d,
            currency,
            account_ids=account_ids,
            start_date=previous_date,
            cached_nav=NAV * 1000,
        )

        omitted_reason = day_diagnostics[0]["reason"] if day_diagnostics else None

        if collector is not None:
            collector.record_period(d, frequency, previous_date)
            collector.record_total(NAV_data["Total NAV"], omitted_reason=omitted_reason)

        if breakdown == "none":
            _add_no_breakdown_data(chart_data, NAV, IRR_value, IRR_rolling)
            if collector is not None:
                collector.record_money_series(
                    "metric:nav", NAV_data["Total NAV"], omitted_reason=omitted_reason
                )
        elif breakdown == "value_contributions":
            if NAV_previous_date is None:
                # Dummy assignment. Need to calculate NAV at the start of the period.
                NAV_previous_date = 0

            contributions_raw = (
                _calculate_contributions(
                    user_id, account_ids, d, previous_date, currency, as_raw=True
                )
                if collector is not None
                else None
            )
            _add_contributions_data(
                chart_data,
                user_id,
                account_ids,
                d,
                IRR_value,
                IRR_rolling,
                NAV,
                NAV_previous_date,
                previous_date,
                currency,
                contributions_raw=contributions_raw,
            )
            if collector is not None:
                opening_raw = Decimal(0) if raw_nav_previous is None else raw_nav_previous
                return_raw = NAV_data["Total NAV"] - opening_raw - contributions_raw
                collector.record_money_series("metric:opening_nav", opening_raw)
                collector.record_money_series("metric:contributions", contributions_raw)
                collector.record_money_series("metric:return", return_raw)
        elif breakdown == "value_contributions_cumulative":
            cumulative_raw = (
                _calculate_contributions(
                    user_id,
                    account_ids,
                    d,
                    None,
                    currency,
                    cumulative=True,
                    cached_transactions=all_transactions,
                    as_raw=True,
                )
                if collector is not None
                else None
            )
            _add_cumulative_contributions_data(
                chart_data,
                user_id,
                account_ids,
                d,
                IRR_value,
                IRR_rolling,
                NAV,
                currency,
                cached_transactions=all_transactions,
                cumulative_raw=cumulative_raw,
            )
            if collector is not None:
                return_raw = NAV_data["Total NAV"] - cumulative_raw
                collector.record_money_series("metric:net_investments", cumulative_raw)
                collector.record_money_series("metric:return", return_raw)
        else:
            breakdown_data = NAV_data.get(breakdown, {})
            add_breakdown_data(
                chart_data,
                IRR_value,
                IRR_rolling,
                breakdown_data,
                categories,
                d,
                sample_index=sample_index,
            )
            if collector is not None:
                affected = {}
                for diagnostic in day_diagnostics:
                    category_key = _diagnostic_category_key(
                        breakdown, diagnostic, collector._account_id_to_name
                    )
                    if category_key is not None:
                        affected.setdefault(category_key, diagnostic["reason"])
                for key, value in breakdown_data.items():
                    identity = _category_series_identity(
                        breakdown, key, collector._account_name_ids
                    )
                    collector.category_series(key, identity)
                collector.record_category_sample(breakdown_data, affected)
                collector.note_partition(
                    sum(breakdown_data.values()), NAV_data["Total NAV"]
                )

        if collector is not None:
            collector.record_irrs(
                IRR_value,
                IRR_rolling,
                omitted=bool(day_diagnostics),
                reason=omitted_reason or "omitted_valuation",
            )

        NAV_previous_date = NAV
        raw_nav_previous = NAV_data["Total NAV"]
        previous_date = d + timedelta(days=1)

    # Fill in missing historical data for categories
    fill_missing_historical_data(chart_data, categories, frequency)

    if collector is not None:
        chart_v2.update(collector.finish())

    return chart_data


def _add_no_breakdown_data(chart_data, NAV, IRR, IRR_rolling):
    """Add no breakdown data."""
    chart_data["datasets"][0]["data"].append(NAV)
    chart_data["datasets"][1]["data"].append(IRR)
    chart_data["datasets"][2]["data"].append(IRR_rolling)


def _add_contributions_data(
    chart_data,
    user_id,
    account_ids,
    d,
    IRR,
    IRR_rolling,
    NAV,
    NAV_previous_date,
    previous_date,
    currency,
    *,
    contributions_raw=None,
):
    """Add contributions data."""
    if contributions_raw is None:
        contributions_raw = _calculate_contributions(
            user_id, account_ids, d, previous_date, currency, as_raw=True
        )
    contributions = contributions_raw / 1000
    return_amount = NAV - NAV_previous_date - contributions

    chart_data["datasets"][0]["data"].append(NAV_previous_date)
    chart_data["datasets"][1]["data"].append(contributions)
    chart_data["datasets"][2]["data"].append(return_amount)
    chart_data["datasets"][3]["data"].append(IRR)
    chart_data["datasets"][4]["data"].append(IRR_rolling)


def add_breakdown_data(
    chart_data, IRR, IRR_rolling, breakdown_data, categories, current_date, *, sample_index: int
):
    """Add breakdown data to chart datasets.

    Args:
        chart_data: Dictionary containing chart structure and datasets.
        IRR: Internal Rate of Return value.
        IRR_rolling: Rolling IRR value.
        breakdown_data: Dictionary of category breakdown values.
        categories: Dictionary tracking categories and their first occurrence dates.
        current_date: Current date for the chart data point.
        sample_index: Index into the complete chart sample/label sequence.
    """
    sample_count = len(chart_data["labels"])
    if not 0 <= sample_index < sample_count:
        raise ValueError("Category sample index is outside the chart labels")
    for key, value in breakdown_data.items():
        if key not in categories:
            categories[key] = current_date
            chart_data["datasets"].insert(
                -2,
                _create_dataset(
                    key,
                    [None] * sample_count,
                    get_color(len(categories)),
                    "bar",
                    "y",
                    stack="combined",
                ),
            )

        dataset_index = next(
            i for i, dataset in enumerate(chart_data["datasets"]) if dataset["label"] == key
        )
        chart_data["datasets"][dataset_index]["data"][sample_index] = value / Decimal("1000")

    # Add IRR data
    chart_data["datasets"][-2]["data"].append(IRR)
    chart_data["datasets"][-1]["data"].append(IRR_rolling)


def fill_missing_historical_data(chart_data, categories, frequency):
    """Fill missing historical data points for chart datasets.

    Args:
        chart_data: Dictionary containing chart structure and datasets.
        categories: Dictionary tracking categories and their first occurrence dates.
        frequency: The frequency of data points.
    """
    # Category series already occupy their exact sample indices. Leading padding
    # would shift late-entry categories a second time; only complete short series.
    sample_count = len(chart_data["labels"])
    for dataset in chart_data["datasets"]:
        if len(dataset["data"]) > sample_count:
            raise ValueError("Chart series has more values than sample labels")
        dataset["data"] += [None] * (sample_count - len(dataset["data"]))


def find_first_data_index(labels, category_date, frequency):
    """Find the first data index for a category based on its start date.

    Args:
        labels: List of date labels for the chart.
        category_date: The date when the category first appeared.
        frequency: The frequency of data points ('daily', 'weekly', 'monthly').

    Returns:
        int: The index where the category data should start.
    """
    for index, label in enumerate(labels):
        if compare_dates(label, category_date, frequency):
            return index
    return 0  # Return 0 if no match found


def compare_dates(label, category_date, frequency):
    """Compare a chart label date with a category date based on frequency.

    Args:
        label: The chart label string to compare.
        category_date: The category date to compare against.
        frequency: The frequency of data points.

    Returns:
        bool: True if label date is >= category date, False otherwise.
    """
    # Handle None cases
    if not label or not category_date:
        return False

    try:
        label_date = parse_label_date(label, frequency)
        if not label_date:
            return False

        if frequency == "D":
            return label_date >= category_date
        elif frequency == "W":
            return label_date.isocalendar()[:2] >= category_date.isocalendar()[:2]
        elif frequency == "M":
            return (label_date.year, label_date.month) >= (
                category_date.year,
                category_date.month,
            )
        elif frequency == "Q":
            return (label_date.year, (label_date.month - 1) // 3) >= (
                category_date.year,
                (category_date.month - 1) // 3,
            )
        elif frequency == "Y":
            return label_date.year >= category_date.year
    except Exception as e:
        logger.error(f"Error comparing dates: {e}")
        return False


def parse_label_date(label, frequency):
    """Parse a chart label into a date object based on frequency.

    Args:
        label: The chart label string to parse.
        frequency: The frequency of data points ('daily', 'weekly', 'monthly', etc.).

    Returns:
        date: The parsed date object, or None if parsing fails.
    """
    if frequency == "D" or frequency == "W":
        return datetime.strptime(label, "%d-%b-%y").date()
    elif frequency == "M":
        return datetime.strptime(label, "%b-%y").date()
    elif frequency == "Q":
        quarter, year = label.split()
        month = (int(quarter[1]) - 1) * 3 + 1
        return date(int("20" + year), month, 1)
    elif frequency == "Y":
        return date(int(label), 1, 1)


def _create_dataset(label, data, color, chart_type, axis_id, stack=None):
    """Create a dataset configuration for a chart.

    Args:
        label: The label for the dataset.
        data: List of data points for the dataset.
        color: The color to use for the dataset.
        chart_type: The type of chart ('line', 'bar', etc.).
        axis_id: The Y-axis ID to use for this dataset.
        stack: The stack group ID (optional).

    Returns:
        dict: Dataset configuration dictionary.
    """
    dataset = {
        "label": label,
        "data": data,
        "backgroundColor": color,
        "borderColor": color,
        "type": chart_type,
        "yAxisID": axis_id,
        "datalabels": {"display": "true"},
    }
    if stack:
        dataset["stack"] = stack
    if chart_type == "line":
        dataset["fill"] = False
    return dataset


def get_color(index):
    """Get a color from a predefined color palette.

    Args:
        index: The index of the color to retrieve.

    Returns:
        str: RGBA color string.
    """
    colors = [
        "rgba(54, 162, 235, 0.7)",
        "rgba(255, 206, 86, 0.7)",
        "rgba(75, 192, 192, 0.7)",
        "rgba(153, 102, 255, 0.7)",
        "rgba(255, 159, 64, 0.7)",
    ]
    return colors[index % len(colors)]


def _calculate_contributions(
    user_id,
    account_ids,
    d,
    previous_date,
    target_currency,
    cumulative=False,
    cached_transactions=None,
    *,
    as_raw=False,
):
    """Calculate contributions.

    Returns the total converted contributions. By default the value is
    expressed in thousands (the legacy chart unit); ``as_raw=True`` returns
    the exact amount in the target currency so the v2 contract never has to
    multiply a scaled value back.
    """
    if cumulative:
        if cached_transactions is None:
            # If no cache provided, fetch all transactions up to this date
            filter_conditions = {
                "investor__id": user_id,
                "account_id__in": account_ids,
                "type__in": ["Cash in", "Cash out"],
                "date__date__lte": d,
            }
            transactions = Transactions.objects.filter(**filter_conditions)
        else:
            # Use cached transactions and filter by date
            transactions = [t for t in cached_transactions if t.date.date() <= d]
    else:
        # Original period-specific logic
        filter_conditions = {
            "investor__id": user_id,
            "account_id__in": account_ids,
            "type__in": ["Cash in", "Cash out"],
            "date__date__lte": d,
        }
        if previous_date is not None:
            # previous_date is the first included day, not the previous sample endpoint.
            filter_conditions["date__date__gte"] = previous_date
        transactions = Transactions.objects.filter(**filter_conditions)

    total_contributions = Decimal(0)

    for transaction in transactions:
        transaction_currency = transaction.currency
        transaction_date = transaction.date
        fx_rate = get_fx_rate(transaction_currency, target_currency, transaction_date)

        converted_amount = transaction.cash_flow * fx_rate
        total_contributions += converted_amount

    if as_raw:
        return total_contributions
    return total_contributions / 1000  # Convert to thousands


def _add_cumulative_contributions_data(
    chart_data,
    user_id,
    account_ids,
    d,
    IRR,
    IRR_rolling,
    NAV,
    currency,
    cached_transactions=None,
    *,
    cumulative_raw=None,
):
    """Add cumulative contributions data."""
    # Calculate cumulative contributions to date
    if cumulative_raw is None:
        cumulative_raw = _calculate_contributions(
            user_id,
            account_ids,
            d,
            None,
            currency,
            cumulative=True,
            cached_transactions=cached_transactions,
            as_raw=True,
        )
    cumulative_contributions = cumulative_raw / 1000

    # Calculate cumulative return (NAV minus total contributions)
    return_amount = NAV - cumulative_contributions

    chart_data["datasets"][0]["data"].append(cumulative_contributions)
    chart_data["datasets"][1]["data"].append(return_amount)
    chart_data["datasets"][2]["data"].append(IRR)
    chart_data["datasets"][3]["data"].append(IRR_rolling)


# Collect chart dates
def _chart_dates(start_date, end_date, freq):
    """Create chart dates."""
    # Create matching table for pandas
    frequency = {"D": "D", "W": "W-SAT", "M": "ME", "Q": "QE", "Y": "YE"}

    start_date = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    end_date = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date

    if start_date >= end_date:
        return np.array([start_date])

    if freq == "W":
        start_date += timedelta(days=(5 - start_date.weekday() + 7) % 7)
    elif freq == "M":
        start_date = start_date.replace(day=1) + relativedelta(months=1, days=-1)
    elif freq == "Q":
        start_date = start_date.replace(
            day=1, month=((start_date.month - 1) // 3 * 3 + 3)
        ) + relativedelta(days=-1)
    elif freq == "Y":
        start_date = start_date.replace(month=12, day=31)

    # Get list of dates from pandas
    date_range = pd.date_range(start=start_date, end=end_date, freq=frequency[freq]).date

    # Handle case where end_date is before or equal to start_date
    if len(date_range) == 0:
        return np.array([min(start_date, end_date)])

    # Ensure the last date is included
    if date_range[-1] != end_date:
        date_range = np.append(date_range, end_date)

    return date_range


# Create labels according to dates
def _chart_labels(dates, frequency):
    """Create chart labels."""
    if frequency in ("D", "W"):
        return [d.strftime("%d-%b-%y") for d in dates]
    if frequency == "M":
        return [d.strftime("%b-%y") for d in dates]
    if frequency == "Q":
        return [f'Q{(d.month - 1) // 3 + 1} {d.strftime("%y")}' for d in dates]
    if frequency == "Y":
        return [d.strftime("%Y") for d in dates]


def _get_earliest_date_for_accounts(user_id, account_ids):
    """Get earliest date for accounts."""
    try:
        earliest_date = Transactions.objects.filter(
            investor__id=user_id, account_id__in=account_ids
        ).aggregate(Min("date"))["date__min"]

        return earliest_date or None
    except Exception as e:
        logger.error(f"Error getting earliest date: {e}")
        return None


# ---------------------------------------------------------------------------
# Chart contract v2: allocation and security documents (C1)
# ---------------------------------------------------------------------------


def _allocation_amounts(dimension, analysis):
    """Raw Decimal amounts for a dimension, validating category identity."""
    amounts = {}
    for key, value in analysis.get(dimension, {}).items():
        _category_series_identity(dimension, key, {})
        amounts[key] = value
    return amounts


def build_allocation_document(
    dimension,
    analysis,
    *,
    currency,
    digits,
    diagnostics,
    effective_date,
    context,
):
    """Build one ``kind='allocation'`` chart document from a raw NAV analysis.

    ``analysis`` is the raw Decimal NAV_at_date result BEFORE percentage and
    display formatting. The denominator is the full reporting NAV; shares are
    raw ratios (not percentage points); ranks are deterministic from Decimal
    amount ordering. ``pieEligibility`` certifies safe pie presentation only —
    it never changes an amount, share or the denominator.
    """
    amounts = _allocation_amounts(dimension, analysis)
    total = analysis.get("Total NAV", Decimal(0))
    affected = {}
    for diagnostic in diagnostics:
        key = _diagnostic_category_key(dimension, diagnostic, {})
        if key is not None:
            affected.setdefault(key, diagnostic["reason"])
    omitted_reason = diagnostics[0]["reason"] if diagnostics else None

    money_unit = {"kind": "money", "currency": currency, "plotDivisor": "1"}

    def money_display(value):
        return currency_format(value, currency, digits)

    def amount_value(key, amount):
        reason = affected.get(key)
        if reason is not None:
            return unavailable_chart_value(
                "partial", reason, money_display(amount), known_subtotal=amount
            )
        return decimal_chart_value(amount, display=money_display(amount))

    denominator = (
        unavailable_chart_value(
            "partial",
            omitted_reason,
            money_display(total),
            known_subtotal=total,
        )
        if omitted_reason
        else decimal_chart_value(total, display=money_display(total))
    )

    ranked_keys = sorted(amounts, key=lambda k: (-amounts[k], k))
    allocations = []
    series = []
    for rank, key in enumerate(ranked_keys, start=1):
        amount = amounts[key]
        amount_point = amount_value(key, amount)
        if denominator["status"] == "ok" and total > 0:
            share_point = decimal_chart_value(
                amount / total, display=format_percentage(amount / total, digits=1)
            )
        elif denominator["status"] == "partial":
            share_point = unavailable_chart_value("unknown", omitted_reason, "–")
        else:
            share_point = unavailable_chart_value("not_available", "not_relevant", "–")
        series_id = f"{dimension}:{key}"
        allocations.append(
            {"seriesId": series_id, "rank": rank, "amount": amount_point, "share": share_point}
        )
        series.append(
            {
                "id": series_id,
                "label": key,
                "metric": "category_nav",
                "role": "bar",
                "axis": "money",
                "unit": money_unit,
                "points": [amount_point],
                "category": {"kind": dimension, "code": key},
            }
        )

    covered = sum(amounts.values())
    if denominator["status"] != "ok" or affected:
        pie_eligibility = "incomplete"
        partition = "unknown"
        total_share = unavailable_chart_value("unknown", omitted_reason, "–")
    elif total <= 0:
        pie_eligibility = "nonpositive_total"
        partition = "complete" if covered == total else "legacy_non_partitioning"
        total_share = unavailable_chart_value("not_available", "not_relevant", "–")
    elif any(amount < 0 for amount in amounts.values()):
        pie_eligibility = "signed"
        partition = "complete" if covered == total else "legacy_non_partitioning"
        total_share = (
            decimal_chart_value(Decimal("1"), display="100.0%")
            if covered == total
            else unavailable_chart_value("not_available", "omitted_valuation", "–")
        )
    elif covered != total:
        pie_eligibility = "nonpartitioning"
        partition = "legacy_non_partitioning"
        total_share = unavailable_chart_value("not_available", "omitted_valuation", "–")
    else:
        pie_eligibility = "eligible"
        partition = "complete"
        total_share = decimal_chart_value(Decimal("1"), display="100.0%")

    iso = effective_date.isoformat()
    return {
        "version": 2,
        "kind": "allocation",
        "outcome": "empty" if not amounts else ("partial" if diagnostics else "ready"),
        "context": context,
        "periods": [
            {
                "key": f"allocation:{dimension}:{iso}",
                "endDate": iso,
                "displayLabel": effective_date.strftime("%d %b %Y"),
                "interval": {"startDate": iso, "endDate": iso, "kind": "sample_interval"},
                "partialPeriod": False,
            }
        ],
        "series": series,
        "totals": [denominator],
        "allocations": allocations,
        "allocationSummary": {
            "dimension": dimension,
            "unit": money_unit,
            "denominator": denominator,
            "totalShare": total_share,
            "pieEligibility": pie_eligibility,
        },
        "partition": partition,
    }


def build_security_price_document(
    security,
    prices,
    *,
    digits,
    context,
):
    """Build the ``kind='price'`` chart document from raw ``Prices`` rows.

    Values are captured from ``Prices.price`` Decimals before the legacy float
    serialization; a bond price 98.5 stays percent-of-nominal 98.5. Each
    period key carries the source price row identity.
    """
    if security.type == "Bond":
        unit = {"kind": "percent_of_nominal", "plotDivisor": "1"}

        def display(price):
            # Display drops the storage-scale trailing zeros (98.500000 -> 98.5);
            # the exact value/plotValue strings keep the full stored scale.
            normalized = price.normalize()
            if normalized.as_tuple().exponent < 0:
                text = format(normalized, "f")
            else:
                text = format(normalized.quantize(Decimal(1)), "f")
            return f"{text}% of nominal"

    else:
        unit = {"kind": "money", "currency": security.currency, "plotDivisor": "1"}

        def display(price):
            return currency_format(price, security.currency, digits)

    periods = []
    points = []
    for price in prices:
        iso = price.date.isoformat()
        periods.append(
            {
                "key": f"security:{security.id}:price:row:{price.pk}",
                "endDate": iso,
                "displayLabel": price.date.strftime("%d %b %Y"),
                "interval": {"startDate": iso, "endDate": iso, "kind": "sample_interval"},
                "partialPeriod": False,
            }
        )
        points.append(decimal_chart_value(price.price, display=display(price.price)))
    return {
        "version": 2,
        "kind": "price",
        "outcome": "ready" if points else "empty",
        "context": context,
        "security": {"id": security.id, "instrumentType": security.type},
        "periods": periods,
        "series": [
            {
                "id": f"security:{security.id}:price",
                "label": "Price",
                "metric": "price",
                "role": "line",
                "axis": "price",
                "unit": unit,
                "points": points,
            }
        ],
    }


def build_security_position_document(
    security,
    rows,
    *,
    context,
):
    """Build the ``kind='position'`` chart document from ordered position rows.

    ``rows`` is a list of ``(source_key, date, Decimal position)`` in the
    legacy order; same-date events stay separate ordered entries keyed by
    their source identity (transaction pk, or the opening snapshot date).
    Quantities keep their exact stored precision.
    """
    periods = []
    points = []
    for source_key, when, quantity in rows:
        iso = when.isoformat()
        periods.append(
            {
                "key": source_key,
                "endDate": iso,
                "displayLabel": when.strftime("%d %b %Y"),
                "interval": {"startDate": iso, "endDate": iso, "kind": "sample_interval"},
                "partialPeriod": False,
            }
        )
        points.append(
            decimal_chart_value(quantity, display=format(quantity, "f"))
        )
    return {
        "version": 2,
        "kind": "position",
        "outcome": "ready" if points else "empty",
        "context": context,
        "security": {"id": security.id, "instrumentType": security.type},
        "periods": periods,
        "series": [
            {
                "id": f"security:{security.id}:position",
                "label": "Position",
                "metric": "position",
                "role": "line",
                "axis": "quantity",
                "unit": {"kind": "quantity", "plotDivisor": "1"},
                "points": points,
            }
        ],
    }
