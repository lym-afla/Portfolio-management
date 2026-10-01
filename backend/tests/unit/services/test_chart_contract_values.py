"""C1 chart value serializers: exact Decimal capture, statuses, fixed notation."""

from datetime import date
from decimal import Decimal

import pytest

from services.charts import (
    _category_series_identity,
    _diagnostic_category_key,
    _irr_chart_value,
    _period_label,
    _unit_for,
    decimal_chart_value,
    unavailable_chart_value,
)


class TestDecimalChartValue:
    def test_requires_decimal_source(self):
        with pytest.raises(TypeError):
            decimal_chart_value(100000, display="$100,000.00")
        with pytest.raises(TypeError):
            decimal_chart_value(100000.0, display="$100,000.00")
        with pytest.raises(TypeError):
            decimal_chart_value("100000", display="$100,000.00")
        with pytest.raises(TypeError):
            decimal_chart_value(None, display="N/A")

    def test_divisor_must_be_decimal(self):
        with pytest.raises(TypeError):
            decimal_chart_value(Decimal("100000"), divisor=1000, display="100")

    def test_money_value_and_backend_scaled_plot_value(self):
        point = decimal_chart_value(
            Decimal("100000"), divisor=Decimal("1000"), display="$100,000.00"
        )
        assert point["value"] == "100000"
        assert point["plotValue"] == "100"
        assert Decimal(point["value"]) / Decimal("1000") == Decimal(point["plotValue"])
        assert point["status"] == "ok"
        assert point["reason"] == "observed"

    def test_ratio_remains_unscaled(self):
        point = decimal_chart_value(Decimal("0.1234"), display="12.3%")
        assert point["value"] == "0.1234"
        assert point["plotValue"] == "0.1234"

    def test_explicit_decimal_zero_is_ok_observed(self):
        point = decimal_chart_value(Decimal("0"), display="–")
        assert point["value"] == "0"
        assert point["plotValue"] == "0"
        assert point["status"] == "ok"
        assert point["reason"] == "observed"

    def test_negative_value_preserves_sign(self):
        point = decimal_chart_value(Decimal("-25"), display="($25.00)")
        assert point["value"] == "-25"
        assert point["plotValue"] == "-25"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (Decimal("1E+3"), "1000"),
            (Decimal("1E-7"), "0.0000001"),
            (Decimal("0.000116590"), "0.000116590"),
            (Decimal("1.10"), "1.10"),
            (Decimal("-0E-9"), "-0.000000000"),
        ],
    )
    def test_fixed_notation_preserves_precision_and_trailing_zeros(self, raw, expected):
        assert decimal_chart_value(raw, display="x")["value"] == expected

    def test_reason_is_forwarded(self):
        point = decimal_chart_value(Decimal("0"), display="0", reason="zero_exposure")
        assert point["reason"] == "zero_exposure"


class TestUnavailableChartValue:
    def test_nulls_for_every_unavailable_status(self):
        for status in ("partial", "unknown", "not_available", "not_relevant"):
            point = unavailable_chart_value(status, "missing_price", "Unavailable")
            assert point["value"] is None
            assert point["plotValue"] is None
            assert point["status"] == status
            assert point["reason"] == "missing_price"
            assert point["display"] == "Unavailable"
            assert "knownSubtotal" not in point

    def test_known_subtotal_permitted_only_for_partial(self):
        point = unavailable_chart_value(
            "partial", "missing_price", "$40,000.00", known_subtotal=Decimal("40000")
        )
        assert point["knownSubtotal"] == "40000"
        for status in ("unknown", "not_available", "not_relevant"):
            with pytest.raises(ValueError):
                unavailable_chart_value(
                    status, "missing_price", "x", known_subtotal=Decimal("1")
                )

    def test_known_subtotal_requires_decimal(self):
        with pytest.raises(TypeError):
            unavailable_chart_value(
                "partial", "missing_price", "x", known_subtotal=40000
            )

    def test_known_subtotal_uses_fixed_notation(self):
        point = unavailable_chart_value(
            "partial", "missing_fx", "x", known_subtotal=Decimal("1E+3")
        )
        assert point["knownSubtotal"] == "1000"


class TestIrrChartValue:
    def test_na_maps_to_solver_unavailable(self):
        point = _irr_chart_value("N/A")
        assert point["status"] == "not_available"
        assert point["reason"] == "solver_unavailable"
        assert point["display"] == "N/A"
        assert point["value"] is None

    def test_nr_maps_to_not_relevant(self):
        point = _irr_chart_value("N/R")
        assert point["status"] == "not_relevant"
        assert point["reason"] == "not_relevant"
        assert point["display"] == "N/R"

    def test_unsupported_irr_result_is_rejected(self):
        with pytest.raises(TypeError):
            _irr_chart_value(0.12)

    def test_partial_irr_keeps_display_but_not_value(self):
        point = _irr_chart_value(Decimal("0.1234"), omitted=True, reason="missing_price")
        assert point["status"] == "partial"
        assert point["value"] is None
        assert point["display"] == "12.3%"


class TestUnitAndIdentity:
    def test_money_ratio_and_quantity_units(self):
        assert _unit_for("money", "USD") == {
            "kind": "money", "currency": "USD", "plotDivisor": "1000",
        }
        assert _unit_for("return", "USD") == {"kind": "ratio", "plotDivisor": "1"}
        assert _unit_for("quantity", "USD") == {"kind": "quantity", "plotDivisor": "1"}

    def test_price_and_unknown_axes_are_rejected(self):
        with pytest.raises(ValueError):
            _unit_for("price", "USD")
        with pytest.raises(ValueError):
            _unit_for("velocity", "USD")

    def test_category_identity_uses_dimension_prefix_and_code(self):
        series_id, meta = _category_series_identity("asset_type", "Stock", {})
        assert series_id == "asset_type:Stock"
        assert meta == {"kind": "asset_type", "code": "Stock"}

    def test_unknown_asset_codes_fail_instead_of_being_renamed(self):
        with pytest.raises(ValueError):
            _category_series_identity("asset_type", "Mystery", {})
        with pytest.raises(ValueError):
            _category_series_identity("asset_class", "Weird", {})

    def test_account_group_identity_requires_membership(self):
        series_id, meta = _category_series_identity(
            "account", "Alpha", {"Alpha": [3, 1]}
        )
        assert series_id == "account-group:3,1"
        assert meta == {"kind": "account_group", "memberAccountIds": [3, 1]}
        with pytest.raises(ValueError):
            _category_series_identity("account", "Ghost", {})

    def test_diagnostic_category_key_maps_per_mode_and_skips_crypto(self):
        diagnostic = {
            "asset_type": "Option", "asset_class": "Derivatives",
            "currency": "DOGE", "account_id": 7,
        }
        assert _diagnostic_category_key("asset_type", diagnostic, {}) == "Option"
        assert _diagnostic_category_key("asset_class", diagnostic, {}) == "Derivatives"
        assert _diagnostic_category_key("currency", diagnostic, {}) == "DOGE"
        assert _diagnostic_category_key("none", diagnostic, {}) is None
        assert _diagnostic_category_key(
            "account", diagnostic, {7: "Alpha"}
        ) == "Alpha"
        crypto = dict(diagnostic, asset_type="Crypto")
        for mode in ("asset_type", "asset_class", "currency"):
            assert _diagnostic_category_key(mode, crypto, {7: "Alpha"}) is None

    def test_period_labels_mirror_legacy_formats(self):
        assert _period_label(date(2026, 1, 31), "D") == "31-Jan-26"
        assert _period_label(date(2026, 1, 31), "M") == "Jan-26"
        assert _period_label(date(2026, 3, 31), "Q") == "Q1 26"
        assert _period_label(date(2026, 12, 31), "Y") == "2026"
        assert _period_label(date(2026, 1, 31), "X") == "2026-01-31"


@pytest.mark.django_db
class TestEmptyOutcomeDocument:
    def test_no_observations_produces_empty_v2_document(self, user, account):
        from services.charts import get_nav_chart_data

        chart_v2 = {"version": 2, "kind": "nav", "context": {}}
        result = get_nav_chart_data(
            user.id,
            (account.id,),
            "M",
            None,  # from_date None -> earliest-date lookup finds nothing
            "2026-01-31",
            "USD",
            "none",
            chart_v2=chart_v2,
        )
        assert result["empty"] is True
        assert chart_v2["outcome"] == "empty"
        assert chart_v2["series"] == []
        assert chart_v2["periods"] == []
        assert chart_v2["partition"] == "complete"
