from datetime import date

import pytest

# from utils import chart_dates_old_framework
from core.chart_utils import _chart_dates


@pytest.mark.django_db
@pytest.mark.parametrize(
    "start_date, end_date, freq, expected",
    [
        # Daily frequency
        (
            date(2023, 5, 15),
            date(2023, 5, 20),
            "D",
            [
                date(2023, 5, 15),
                date(2023, 5, 16),
                date(2023, 5, 17),
                date(2023, 5, 18),
                date(2023, 5, 19),
                date(2023, 5, 20),
            ],
        ),
        # Weekly frequency (Saturday as last day of week)
        (
            date(2023, 5, 15),
            date(2023, 6, 10),
            "W",
            [date(2023, 5, 20), date(2023, 5, 27), date(2023, 6, 3), date(2023, 6, 10)],
        ),
        # Monthly frequency
        (
            date(2023, 5, 15),
            date(2023, 8, 20),
            "M",
            [date(2023, 5, 31), date(2023, 6, 30), date(2023, 7, 31), date(2023, 8, 20)],
        ),
        # Quarterly frequency
        (
            date(2023, 5, 15),
            date(2024, 2, 20),
            "Q",
            [date(2023, 6, 30), date(2023, 9, 30), date(2023, 12, 31), date(2024, 2, 20)],
        ),
        # Yearly frequency
        (
            date(2023, 5, 15),
            date(2026, 2, 20),
            "Y",
            [date(2023, 12, 31), date(2024, 12, 31), date(2025, 12, 31), date(2026, 2, 20)],
        ),
        # Another yearly frequency
        (
            date(2019, 8, 5),
            date(2024, 8, 5),
            "Y",
            [
                date(2019, 12, 31),
                date(2020, 12, 31),
                date(2021, 12, 31),
                date(2022, 12, 31),
                date(2023, 12, 31),
                date(2024, 8, 5),
            ],
        ),
        # Edge case: end_date is exactly on period end
        (date(2023, 1, 1), date(2023, 12, 31), "Y", [date(2023, 12, 31)]),
        # Edge case: end_date is before first period end
        (date(2023, 1, 1), date(2023, 6, 30), "Y", [date(2023, 6, 30)]),
    ],
)
def test_chart_dates(start_date, end_date, freq, expected):
    result = _chart_dates(start_date, end_date, freq)
    assert list(result) == expected


@pytest.mark.django_db
def test_chart_dates_with_string_input():
    start_date = "2023-05-15"
    end_date = "2023-05-20"
    freq = "D"
    expected = [
        date(2023, 5, 15),
        date(2023, 5, 16),
        date(2023, 5, 17),
        date(2023, 5, 18),
        date(2023, 5, 19),
        date(2023, 5, 20),
    ]
    result = _chart_dates(start_date, end_date, freq)
    assert list(result) == expected
