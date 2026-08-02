"""Tests for core/formatting_utils.py.

Covers format_quantity_adaptive (the adaptive decimal-place rule for quantity
display) and the format_value dispatch for the "quantity" key.
"""

from decimal import Decimal

from core.formatting_utils import format_quantity_adaptive, format_value


# ---------------------------------------------------------------------------
# format_quantity_adaptive
# ---------------------------------------------------------------------------


def test_quantity_at_or_above_one_uses_digits_setting():
    assert format_quantity_adaptive(Decimal("12.94056"), 2) == "12.94"
    assert format_quantity_adaptive(Decimal("12.94056"), 4) == "12.9406"
    assert format_quantity_adaptive(Decimal("12.94056"), 0) == "13"
    assert format_quantity_adaptive(Decimal("100"), 2) == "100.00"


def test_quantity_sub_one_respects_digits_when_precise_enough():
    # 0.6803 at digits=2 keeps two decimals (0.68); no precision lost.
    assert format_quantity_adaptive(Decimal("0.680300000"), 2) == "0.68"


def test_quantity_sub_one_expands_to_first_significant_digit_when_digits_too_few():
    # 0.00011659 at digits=2 would round to "0.00" (precision lost); expand to
    # the first significant digit instead.
    assert format_quantity_adaptive(Decimal("0.000116590"), 2) == "0.0001"
    # Same value at digits=0 also expands (digits < first-significant position).
    assert format_quantity_adaptive(Decimal("0.000116590"), 0) == "0.0001"


def test_quantity_sub_one_at_digits_zero_shows_first_significant_digit():
    # 0.6803 at digits=0 -> first significant digit -> "0.7".
    assert format_quantity_adaptive(Decimal("0.680300000"), 0) == "0.7"


def test_quantity_clamps_sub_one_at_unit_boundary():
    # 0.99 must never round up to "1"; the clamp adds decimals until < 1.
    assert format_quantity_adaptive(Decimal("0.99"), 2) == "0.99"
    assert format_quantity_adaptive(Decimal("0.99"), 0) == "0.99"
    assert format_quantity_adaptive(Decimal("0.9999"), 2) == "0.9999"
    assert format_quantity_adaptive(Decimal("-0.99"), 2) == "-0.99"


def test_quantity_none_and_zero_return_dash():
    assert format_quantity_adaptive(None, 2) == "–"
    assert format_quantity_adaptive(Decimal("0"), 2) == "–"
    assert format_quantity_adaptive("", 2) == "–"


def test_quantity_accepts_numeric_string():
    assert format_quantity_adaptive("0.6803", 2) == "0.68"


# ---------------------------------------------------------------------------
# format_value dispatch (the "quantity" key routes to the adaptive formatter)
# ---------------------------------------------------------------------------


def test_format_value_quantity_uses_adaptive_formatter():
    # Regression for OKX live-test: crypto quantity 0.6803 was rendered as "1"
    # because format_value hardcoded quantity to digits=0 (integer). Now it
    # respects the digits setting and adapts for small values.
    assert format_value(Decimal("0.6803"), "quantity", "USD", 2) == "0.68"
    assert format_value(Decimal("0.00011659"), "quantity", "USD", 2) == "0.0001"
    # Integer quantity still renders cleanly.
    assert format_value(Decimal("100"), "quantity", "USD", 2) == "100.00"
    # current_position / open_position share the same adaptive path.
    assert format_value(Decimal("0.6803"), "current_position", "USD", 2) == "0.68"
