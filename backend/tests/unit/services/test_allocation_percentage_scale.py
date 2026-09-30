"""Synthetic allocation shares characterize the current helper and dashboard API."""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from core.formatting_utils import format_percentage
from dashboard import views
from services.performance import calculate_percentage_shares


def test_quarter_allocation_is_twenty_five_percent():
    data = {
        "Total NAV": Decimal("100"),
        "asset_type": {"Stock": Decimal("25"), "Cash": Decimal("75")},
    }
    assert Decimal("25") / Decimal("100") == Decimal("0.25")
    assert format_percentage(Decimal("0.25"), digits=1) == "25.0%"
    calculate_percentage_shares(data, ["asset_type"])
    assert data["asset_type_percentage"] == {"Stock": "25.0%", "Cash": "75.0%"}


@pytest.mark.parametrize("total", [Decimal("0"), Decimal("-100")])
def test_nonpositive_total_keeps_unavailable_shares(total):
    data = {"Total NAV": total, "asset_type": {"Stock": Decimal("25"), "Cash": Decimal("-25")}}
    calculate_percentage_shares(data, ["asset_type"])
    assert data["asset_type_percentage"] == {"Stock": "–", "Cash": "–"}


def test_signed_and_zero_shares_keep_existing_formatter_display_policy():
    data = {
        "Total NAV": Decimal("100"),
        "asset_type": {"Short": Decimal("-25"), "Cash": Decimal("125"), "Zero": Decimal("0")},
    }
    calculate_percentage_shares(data, ["asset_type"])
    assert data["asset_type_percentage"] == {"Short": "(25.0%)", "Cash": "125.0%", "Zero": "–"}


def test_other_percentage_formatter_callers_keep_the_ratio_contract():
    assert format_percentage(Decimal("0.01"), digits=1) == "1.0%"
    assert format_percentage(Decimal("-0.25"), digits=1) == "(25.0%)"
    assert format_percentage(Decimal("1"), digits=1) == "100.0%"


def test_dashboard_api_preserves_response_shape_and_correct_share_scale(monkeypatch):
    user = SimpleNamespace(
        id=1,
        default_currency="USD",
        digits=2,
        selected_account_type="all",
        selected_account_id=None,
        is_authenticated=True,
    )
    user.default_currency = "USD"
    user.digits = 2
    fixture = {
        "Total NAV": Decimal("100"),
        "asset_type": {"Stock": Decimal("25"), "Cash": Decimal("75")},
        "asset_class": {"Equity": Decimal("25"), "Cash": Decimal("75")},
        "currency": {"USD": Decimal("100")},
    }
    monkeypatch.setattr(views, "NAV_at_date", lambda *args: deepcopy(fixture))
    monkeypatch.setattr(views, "get_selected_account_ids", lambda *args: (2,))
    request = APIRequestFactory().get("/dashboard/api/get-breakdown/")
    request.effective_current_date = "2026-09-08"
    force_authenticate(request, user=user)
    response = views.get_dashboard_breakdown_api(request)
    assert response.status_code == 200
    assert set(response.data) == {"assetType", "assetClass", "currency", "totalNAV"}
    assert response.data["assetType"]["percentage"] == {"Stock": "25.0%", "Cash": "75.0%"}
    assert response.data["assetClass"]["percentage"] == {"Equity": "25.0%", "Cash": "75.0%"}
    assert response.data["currency"]["percentage"] == {"USD": "100.0%"}
    assert response.data["assetType"]["data"] == {"Stock": "$25.00", "Cash": "$75.00"}
    assert response.data["totalNAV"] == "$100.00"


def test_missing_total_nav_keeps_shares_unavailable():
    data = {"asset_type": {"Stock": Decimal("25")}}
    calculate_percentage_shares(data, ["asset_type"])
    assert data["asset_type_percentage"] == {"Stock": "–"}


def test_empty_analysis_remains_empty():
    data = {}
    assert calculate_percentage_shares(data, ["asset_type"]) is None
    assert data == {}
