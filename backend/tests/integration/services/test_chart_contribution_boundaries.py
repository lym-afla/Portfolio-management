"""Canonical transaction interval regressions; NAV/IRR pinned only for classification."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from django.conf import settings

from common.models import Transactions
from services import charts

pytestmark = pytest.mark.django_db


def flow(user, account, when, amount):
    amount = Decimal(amount)
    return Transactions.objects.create(
        investor=user,
        account=account,
        type="Cash in" if amount >= 0 else "Cash out",
        currency="USD",
        date=when,
        cash_flow=amount,
    )


def pin_chart_inputs(monkeypatch, values):
    calls = []
    monkeypatch.setattr(
        charts, "NAV_at_date", lambda uid, ids, day, cur, breakdown: {"Total NAV": values[day]}
    )

    def pinned_irr(uid, day, cur, **kwargs):
        calls.append((day, kwargs))
        return Decimal("0.0000")

    monkeypatch.setattr(charts, "IRR", pinned_irr)
    return calls


def test_february_first_deposit_is_contribution_not_return(user, account, monkeypatch):
    for day, amount in [(date(2026, 1, 31), "1000"), (date(2026, 2, 1), "100")]:
        flow(user, account, datetime.combine(day, time(12), timezone.utc), amount)
    calls = pin_chart_inputs(
        monkeypatch, {date(2026, 1, 31): Decimal("1000"), date(2026, 2, 28): Decimal("1100")}
    )
    result = charts.get_nav_chart_data(
        user.id,
        (account.id,),
        "M",
        date(2026, 1, 31),
        date(2026, 2, 28),
        "USD",
        "value_contributions",
    )
    series = {item["label"]: item["data"] for item in result["datasets"]}
    assert series["Previous NAV"][1] == Decimal("1")
    assert series["Contributions"][1] == Decimal("0.1")
    assert series["Return"][1] == Decimal("0")
    assert sum(series[name][1] for name in ["Previous NAV", "Contributions", "Return"]) == Decimal(
        "1.1"
    )
    assert [kwargs.get("start_date") for _, kwargs in calls] == [None, None, None, date(2026, 2, 1)]
    assert [kwargs["cached_nav"] for _, kwargs in calls] == [Decimal("1000")] * 2 + [
        Decimal("1100")
    ] * 2


@pytest.mark.parametrize("frequency", ["D", "M"])
@pytest.mark.parametrize("sign", [Decimal("1"), Decimal("-1")], ids=["cash-in", "cash-out"])
def test_adjacent_intervals_include_first_and_last_days_exactly_once(
    user, account, monkeypatch, frequency, sign
):
    endpoints = (
        [date(2026, 1, 31), date(2026, 2, 1), date(2026, 2, 2)]
        if frequency == "D"
        else [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    )
    flow(user, account, datetime.combine(endpoints[0], time(12)), "1000")
    for previous, endpoint in zip(endpoints, endpoints[1:]):
        flow(
            user,
            account,
            datetime.combine(previous + timedelta(days=1), time.min),
            sign * Decimal("100"),
        )
        flow(user, account, datetime.combine(endpoint, time(23, 59, 59)), sign * Decimal("50"))
    values = {
        day: Decimal("1000") + index * sign * Decimal("150") for index, day in enumerate(endpoints)
    }
    calls = pin_chart_inputs(monkeypatch, values)
    result = charts.get_nav_chart_data(
        user.id, (account.id,), frequency, endpoints[0], endpoints[-1], "USD", "value_contributions"
    )
    series = {item["label"]: item["data"] for item in result["datasets"]}
    assert series["Contributions"] == [Decimal("1"), sign * Decimal("0.15"), sign * Decimal("0.15")]
    assert series["Return"] == [Decimal("0")] * 3
    assert series["Previous NAV"] == [
        Decimal("0"),
        values[endpoints[0]] / Decimal("1000"),
        values[endpoints[1]] / Decimal("1000"),
    ]
    for index, day in enumerate(endpoints):
        assert sum(
            series[name][index] for name in ["Previous NAV", "Contributions", "Return"]
        ) == values[day] / Decimal("1000")
    assert [kwargs.get("start_date") for _, kwargs in calls[1::2]] == [
        None,
        endpoints[0] + timedelta(days=1),
        endpoints[1] + timedelta(days=1),
    ]


def test_midnight_follows_existing_naive_wall_date_storage(user, account):
    assert settings.USE_TZ is False
    assert settings.TIME_ZONE == "UTC"
    plus_three = timezone(timedelta(hours=3))
    flow(user, account, datetime(2026, 1, 31, 23, 59, 59, tzinfo=plus_three), "999")
    first = flow(user, account, datetime(2026, 2, 1, 0, 0, tzinfo=plus_three), "100")
    flow(user, account, datetime(2026, 2, 28, 23, 59, 59, tzinfo=plus_three), "25")
    flow(user, account, datetime(2026, 3, 1, 0, 0, tzinfo=plus_three), "888")
    first.refresh_from_db()
    assert first.date == datetime(2026, 2, 1, 0, 0)
    assert charts._calculate_contributions(
        user.id, (account.id,), date(2026, 2, 28), date(2026, 2, 1), "USD"
    ) == Decimal("0.125")


def test_cumulative_chart_keeps_all_history_before_the_requested_range(user, account, monkeypatch):
    for when, amount in [
        (datetime(2025, 12, 31), "500"),
        (datetime(2026, 1, 31), "500"),
        (datetime(2026, 2, 1), "100"),
        (datetime(2026, 3, 1), "-25"),
    ]:
        flow(user, account, when, amount)
    values = {
        date(2026, 1, 31): Decimal("1000"),
        date(2026, 2, 28): Decimal("1100"),
        date(2026, 3, 31): Decimal("1075"),
    }
    pin_chart_inputs(monkeypatch, values)
    result = charts.get_nav_chart_data(
        user.id,
        (account.id,),
        "M",
        date(2026, 1, 31),
        date(2026, 3, 31),
        "USD",
        "value_contributions_cumulative",
    )
    series = {item["label"]: item["data"] for item in result["datasets"]}
    assert series["Net Investments"] == [Decimal("1"), Decimal("1.1"), Decimal("1.075")]
    assert series["Return"] == [Decimal("0")] * 3
    # The uncached cumulative helper must retain the same all-history membership.
    assert charts._calculate_contributions(
        user.id, (account.id,), date(2026, 3, 31), None, "USD", cumulative=True
    ) == Decimal("1.075")


def test_contributions_keep_account_selection_and_end_date_boundaries(user, account, account_uk):
    flow(user, account, datetime(2026, 2, 1), "100")
    flow(user, account, datetime(2026, 2, 28, 23, 59, 59), "50")
    flow(user, account, datetime(2026, 1, 31, 23, 59, 59), "999")
    flow(user, account, datetime(2026, 3, 1), "888")
    flow(user, account_uk, datetime(2026, 2, 1), "777")
    assert charts._calculate_contributions(
        user.id, (account.id,), date(2026, 2, 28), date(2026, 2, 1), "USD"
    ) == Decimal("0.15")
