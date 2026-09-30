"""Decimal regressions for chart sample/category alignment (synthetic values)."""

from datetime import date
from decimal import Decimal

import pytest

from services import charts


def build_category_chart(values):
    chart = {
        "labels": [f"0{index + 1}-Jan-26" for index in range(len(values))],
        "datasets": [
            {"label": "IRR (RHS)", "data": []},
            {"label": "Rolling IRR (RHS)", "data": []},
        ],
    }
    categories = {}
    for index, breakdown in enumerate(values):
        charts.add_breakdown_data(
            chart,
            Decimal("0.1000"),
            Decimal("0.0200"),
            breakdown,
            categories,
            date(2026, 1, index + 1),
            sample_index=index,
        )
    charts.fill_missing_historical_data(chart, categories, "D")
    return chart


@pytest.mark.parametrize(
    "values, expected",
    [
        (
            [{"Equity": Decimal("1000")}, {}, {"Equity": Decimal("3000")}],
            [Decimal("1"), None, Decimal("3")],
        ),
        (
            [{}, {"Equity": Decimal("1000")}, {"Equity": Decimal("2000")}],
            [None, Decimal("1"), Decimal("2")],
        ),
        (
            [{"Equity": Decimal("1000")}, {}, {}, {"Equity": Decimal("4000")}],
            [Decimal("1"), None, None, Decimal("4")],
        ),
        (
            [{}, {"Equity": Decimal("0")}, {"Equity": Decimal("-2000")}],
            [None, Decimal("0"), Decimal("-2")],
        ),
        ([{"Equity": Decimal("1000")}, {}, {}], [Decimal("1"), None, None]),
    ],
    ids=["reentry", "late-entry", "interior-absence", "zero-and-negative", "trailing-absence"],
)
def test_category_keeps_its_sample_index_and_unknown_gaps(values, expected):
    chart = build_category_chart(values)
    equity = next(series for series in chart["datasets"] if series["label"] == "Equity")
    assert equity["data"] == expected
    assert all(len(series["data"]) == len(values) for series in chart["datasets"])
    assert chart["datasets"][-2]["data"] == [Decimal("0.1000")] * len(values)
    assert chart["datasets"][-1]["data"] == [Decimal("0.0200")] * len(values)


def test_multiple_categories_align_independently():
    chart = build_category_chart(
        [
            {"Equity": Decimal("1000")},
            {"Bond": Decimal("2000")},
            {"Equity": Decimal("3000"), "Bond": Decimal("0")},
        ]
    )
    assert [series["data"] for series in chart["datasets"][:-2]] == [
        [Decimal("1"), None, Decimal("3")],
        [None, Decimal("2"), Decimal("0")],
    ]


def test_full_nav_loader_passes_original_sample_index_without_changing_irr_calls(monkeypatch):
    dates = [date(2026, 1, day) for day in [1, 2, 3]]
    values = [
        {"Total NAV": Decimal("1000"), "asset_type": {"Equity": Decimal("1000")}},
        {"Total NAV": Decimal("0"), "asset_type": {}},
        {"Total NAV": Decimal("3000"), "asset_type": {"Equity": Decimal("3000")}},
    ]
    calls = []
    monkeypatch.setattr(charts, "_chart_dates", lambda *_: dates)
    monkeypatch.setattr(
        charts, "NAV_at_date", lambda _user, _accounts, day, *_: values[dates.index(day)]
    )

    def irr(_user, day, currency, **kwargs):
        calls.append((day, currency, kwargs))
        return Decimal("0.1000") if "start_date" not in kwargs else Decimal("0.0200")

    monkeypatch.setattr(charts, "IRR", irr)
    chart = charts.get_nav_chart_data(1, (2,), "D", dates[0], dates[-1], "USD", "asset_type")
    assert chart["labels"] == ["01-Jan-26", "02-Jan-26", "03-Jan-26"]
    assert chart["datasets"][0]["data"] == [Decimal("1"), None, Decimal("3")]
    assert [series["data"] for series in chart["datasets"][-2:]] == [
        [Decimal("0.1000")] * 3,
        [Decimal("0.0200")] * 3,
    ]
    assert [call[2].get("start_date") for call in calls[1::2]] == [
        None,
        date(2026, 1, 2),
        date(2026, 1, 3),
    ]
    assert [call[2]["cached_nav"] for call in calls[::2]] == [
        Decimal("1000"),
        Decimal("0"),
        Decimal("3000"),
    ]


@pytest.mark.parametrize("index", [-1, 3])
def test_category_index_must_belong_to_the_sample_sequence(index):
    chart = {
        "labels": ["a", "b", "c"],
        "datasets": [
            {"label": "IRR (RHS)", "data": []},
            {"label": "Rolling IRR (RHS)", "data": []},
        ],
    }
    with pytest.raises(ValueError, match="sample index"):
        charts.add_breakdown_data(
            chart,
            Decimal("0"),
            Decimal("0"),
            {"Equity": Decimal("1000")},
            {},
            date(2026, 1, 1),
            sample_index=index,
        )
    assert all(series["data"] == [] for series in chart["datasets"])


def test_series_longer_than_labels_is_rejected_instead_of_silently_retained():
    chart = {"labels": ["a"], "datasets": [{"label": "NAV", "data": [Decimal("1"), Decimal("2")]}]}
    with pytest.raises(ValueError, match="more values than sample labels"):
        charts.fill_missing_historical_data(chart, {}, "D")


def test_short_series_completes_with_unknown_values_without_shifting():
    chart = {"labels": ["a", "b", "c"], "datasets": [{"label": "NAV", "data": [Decimal("1")]}]}
    charts.fill_missing_historical_data(chart, {}, "D")
    assert chart["datasets"][0]["data"] == [Decimal("1"), None, None]
