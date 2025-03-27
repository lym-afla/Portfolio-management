import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from django.db.models import Min

from common.models import Transactions
from core.portfolio_utils import IRR, NAV_at_date, get_fx_rate

logger = logging.getLogger("dashboard")


def get_nav_chart_data(user_id, account_ids, frequency, from_date, to_date, currency, breakdown):
    # Ensure dates are date objects first
    from_date = date.fromisoformat(from_date) if isinstance(from_date, str) else from_date
    to_date = date.fromisoformat(to_date) if isinstance(to_date, str) else to_date

    # Only get earliest date if from_date is None
    if from_date is None:
        earliest_date = _get_earliest_date_for_accounts(user_id, account_ids)
        if not earliest_date:
            return {"labels": [], "datasets": [], "currency": currency + "k", "empty": True}
        from_date = earliest_date

    # Validate dates
    if not from_date or not to_date or from_date > to_date:
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
                "Previous NAV", [], "rgba(75, 192, 192, 0.7)", "bar", "y", stack="combined"
            ),
            _create_dataset(
                "Contributions", [], "rgba(153, 102, 255, 0.7)", "bar", "y", stack="combined"
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
            date__lte=to_date,
        )
        chart_data["datasets"] = [
            _create_dataset(
                "Net Investments", [], "rgba(75, 192, 192, 0.7)", "bar", "y", stack="combined"
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

    for d in dates:
        NAV_data = NAV_at_date(
            user_id,
            tuple(account_ids),
            d,
            currency,
            tuple([breakdown])
            if breakdown not in ["none", "value_contributions", "value_contributions_cumulative"]
            else (),
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

        if breakdown == "none":
            _add_no_breakdown_data(chart_data, NAV, IRR_value, IRR_rolling)
        elif breakdown == "value_contributions":
            if NAV_previous_date is None:
                # Dummy assignment. Need to calculate NAV at the start of the period.
                NAV_previous_date = 0

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
            )
        elif breakdown == "value_contributions_cumulative":
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
            )
        else:
            breakdown_data = NAV_data.get(breakdown, {})
            add_breakdown_data(chart_data, IRR_value, IRR_rolling, breakdown_data, categories, d)

        NAV_previous_date = NAV
        previous_date = d + timedelta(days=1)

    # Fill in missing historical data for categories
    fill_missing_historical_data(chart_data, categories, frequency)

    return chart_data


def _add_no_breakdown_data(chart_data, NAV, IRR, IRR_rolling):
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
):
    contributions = _calculate_contributions(user_id, account_ids, d, previous_date, currency)
    return_amount = NAV - NAV_previous_date - contributions

    chart_data["datasets"][0]["data"].append(NAV_previous_date)
    chart_data["datasets"][1]["data"].append(contributions)
    chart_data["datasets"][2]["data"].append(return_amount)
    chart_data["datasets"][3]["data"].append(IRR)
    chart_data["datasets"][4]["data"].append(IRR_rolling)


def add_breakdown_data(chart_data, IRR, IRR_rolling, breakdown_data, categories, current_date):
    for key, value in breakdown_data.items():
        if key not in categories:
            categories[key] = current_date
            chart_data["datasets"].insert(
                -2,
                _create_dataset(key, [], get_color(len(categories)), "bar", "y", stack="combined"),
            )

        dataset_index = next(
            i for i, dataset in enumerate(chart_data["datasets"]) if dataset["label"] == key
        )
        chart_data["datasets"][dataset_index]["data"].append(value / 1000)

    # Add IRR data
    chart_data["datasets"][-2]["data"].append(IRR)
    chart_data["datasets"][-1]["data"].append(IRR_rolling)


def fill_missing_historical_data(chart_data, categories, frequency):
    for dataset in chart_data["datasets"][:-2]:  # Exclude IRR datasets
        label = dataset["label"]
        if label in categories:
            first_data_index = find_first_data_index(
                chart_data["labels"], categories[label], frequency
            )
            dataset["data"] = [None] * first_data_index + dataset["data"]

    # Ensure all datasets have the same length
    max_length = len(chart_data["labels"])
    for dataset in chart_data["datasets"]:
        dataset["data"] += [None] * (max_length - len(dataset["data"]))


def find_first_data_index(labels, category_date, frequency):
    for index, label in enumerate(labels):
        if compare_dates(label, category_date, frequency):
            return index
    return 0  # Return 0 if no match found


def compare_dates(label, category_date, frequency):
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
            return (label_date.year, label_date.month) >= (category_date.year, category_date.month)
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
):
    if cumulative:
        if cached_transactions is None:
            # If no cache provided, fetch all transactions up to this date
            filter_conditions = {
                "investor__id": user_id,
                "account_id__in": account_ids,
                "type__in": ["Cash in", "Cash out"],
                "date__lte": d,
            }
            transactions = Transactions.objects.filter(**filter_conditions)
        else:
            # Use cached transactions and filter by date
            transactions = [t for t in cached_transactions if t.date <= d]
    else:
        # Original period-specific logic
        filter_conditions = {
            "investor__id": user_id,
            "account_id__in": account_ids,
            "type__in": ["Cash in", "Cash out"],
            "date__lte": d,
        }
        if previous_date is not None:
            filter_conditions["date__gt"] = previous_date
        transactions = Transactions.objects.filter(**filter_conditions)

    total_contributions = Decimal(0)

    for transaction in transactions:
        transaction_currency = transaction.currency
        transaction_date = transaction.date
        fx_rate = get_fx_rate(transaction_currency, target_currency, transaction_date)

        converted_amount = transaction.cash_flow * fx_rate
        total_contributions += converted_amount

    return total_contributions / 1000  # Convert to thousands


def _add_cumulative_contributions_data(
    chart_data, user_id, account_ids, d, IRR, IRR_rolling, NAV, currency, cached_transactions=None
):
    # Calculate cumulative contributions to date
    cumulative_contributions = _calculate_contributions(
        user_id,
        account_ids,
        d,
        None,
        currency,
        cumulative=True,
        cached_transactions=cached_transactions,
    )

    # Calculate cumulative return (NAV minus total contributions)
    return_amount = NAV - cumulative_contributions

    chart_data["datasets"][0]["data"].append(cumulative_contributions)
    chart_data["datasets"][1]["data"].append(return_amount)
    chart_data["datasets"][2]["data"].append(IRR)
    chart_data["datasets"][3]["data"].append(IRR_rolling)


# Collect chart dates
def _chart_dates(start_date, end_date, freq):
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
    if frequency in ("D", "W"):
        return [d.strftime("%d-%b-%y") for d in dates]
    if frequency == "M":
        return [d.strftime("%b-%y") for d in dates]
    if frequency == "Q":
        return [f'Q{(d.month - 1) // 3 + 1} {d.strftime("%y")}' for d in dates]
    if frequency == "Y":
        return [d.strftime("%Y") for d in dates]


def _get_earliest_date_for_accounts(user_id, account_ids):
    try:
        earliest_date = Transactions.objects.filter(
            investor__id=user_id, account_id__in=account_ids
        ).aggregate(Min("date"))["date__min"]

        return earliest_date or None
    except Exception as e:
        logger.error(f"Error getting earliest date: {e}")
        return None
