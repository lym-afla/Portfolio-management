"""C1 chart contract v2: endpoint parity, identity, units, dates, statuses, errors.

Negotiation is explicit: ``chart_contract=2`` adds ``chartV2`` beside unchanged
legacy payloads (NAV/allocation) or wraps the unchanged array (security
histories). Without the parameter every endpoint keeps its incumbent keys,
types and HTTP behavior. Numeric fixtures pin NAV/IRR only where chart
assembly (not classification) is under test; contributions tests use real
transaction rows, mirroring the F2 regression style.
"""

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from common.models import Accounts, Assets, Brokers, Prices, Transactions
from dashboard import views as dashboard_views
from database import views as database_views
from services import charts

pytestmark = pytest.mark.django_db

JAN_END = "2026-01-31"


def make_account(user, name="Test Account", broker_name="Test Broker"):
    broker = Brokers.objects.create(investor=user, name=broker_name, country="US")
    return Accounts.objects.create(broker=broker, name=name)


def pin_chart(monkeypatch, nav_by_date, irr=Decimal("0.1234"), omissions=()):
    """Pin NAV/IRR to exact Decimal values; emit omissions when asked."""

    def pinned_nav(uid, ids, day, cur, breakdown=(), diagnostics=None):
        if diagnostics is not None:
            diagnostics.extend(omissions)
        return {"Total NAV": nav_by_date.get(day, Decimal("100000"))}

    monkeypatch.setattr(charts, "NAV_at_date", pinned_nav)
    monkeypatch.setattr(charts, "IRR", lambda uid, day, cur, **kwargs: irr)


def call_nav_chart(
    user,
    breakdown="none",
    frequency="M",
    date_from=JAN_END,
    date_to=JAN_END,
    contract=None,
):
    params = {"breakdown": breakdown, "frequency": frequency, "dateTo": date_to}
    if date_from is not None:
        params["dateFrom"] = date_from
    if contract is not None:
        params["chart_contract"] = contract
    request = APIRequestFactory().get("/dashboard/api/get-nav-chart-data/", params)
    request.effective_current_date = date_to
    force_authenticate(request, user=user)
    return dashboard_views.api_nav_chart_data(request)


def call_breakdown(user, contract=None, effective=JAN_END):
    params = {}
    if contract is not None:
        params["chart_contract"] = contract
    request = APIRequestFactory().get("/dashboard/api/get-breakdown/", params)
    request.effective_current_date = effective
    force_authenticate(request, user=user)
    return dashboard_views.get_dashboard_breakdown_api(request)


def call_price_history(user, security_id, contract=None, period="All", effective=JAN_END):
    params = {"period": period}
    if contract is not None:
        params["chart_contract"] = contract
    request = APIRequestFactory().get(
        f"/database/api/security/{security_id}/price-history/", params
    )
    request.effective_current_date = effective
    force_authenticate(request, user=user)
    return database_views.api_get_security_price_history(request, security_id)


def call_position_history(user, security_id, contract=None, period="All", effective=JAN_END):
    params = {"period": period}
    if contract is not None:
        params["chart_contract"] = contract
    request = APIRequestFactory().get(
        f"/database/api/security/{security_id}/position-history/", params
    )
    request.effective_current_date = effective
    force_authenticate(request, user=user)
    return database_views.api_get_security_position_history(request, security_id)


def series_by_metric(doc):
    return {s["metric"]: s for s in doc["series"]}


# ---------------------------------------------------------------------------
# NAV endpoint: parity, exact values, periods
# ---------------------------------------------------------------------------


class TestNavContractV2:
    def test_v2_keeps_legacy_keys_and_exposes_exact_raw_values(self, user, account, monkeypatch):
        user.digits = 2
        user.save()
        pin_chart(monkeypatch, {date(2026, 1, 31): Decimal("100000")})
        legacy = call_nav_chart(user).data
        modern = call_nav_chart(user, contract=2).data
        assert "chartV2" not in legacy
        assert modern["labels"] == legacy["labels"]
        assert modern["datasets"] == legacy["datasets"]
        assert modern["currency"] == legacy["currency"]

        doc = modern["chartV2"]
        assert doc["version"] == 2
        assert doc["kind"] == "nav"
        assert doc["outcome"] == "ready"
        assert doc["partition"] == "complete"
        assert doc["context"] == {
            "accountSelection": {"type": "all", "id": None},
            "accountIds": [account.id],
            "effectiveDate": JAN_END,
            "currency": "USD",
            "digits": 2,
        }

        nav = series_by_metric(doc)["nav"]
        assert nav["id"] == "metric:nav"
        assert nav["role"] == "bar"
        assert nav["axis"] == "money"
        assert nav["unit"] == {"kind": "money", "currency": "USD", "plotDivisor": "1000"}
        assert nav["points"][0]["value"] == "100000"
        assert nav["points"][0]["plotValue"] == "100"
        assert Decimal(nav["points"][0]["value"]) / Decimal("1000") == Decimal("100")
        assert nav["points"][0]["status"] == "ok"
        assert nav["points"][0]["reason"] == "observed"
        assert nav["points"][0]["display"] == "$100,000.00"

        irr = series_by_metric(doc)["irr_inception"]
        assert irr["points"][0]["value"] == "0.1234"
        assert irr["points"][0]["plotValue"] == "0.1234"
        assert irr["points"][0]["display"] == "12.3%"
        assert irr["unit"] == {"kind": "ratio", "plotDivisor": "1"}
        rolling = series_by_metric(doc)["irr_interval"]
        assert rolling["points"][0]["value"] == "0.1234"

        assert doc["periods"][0]["endDate"] == date(2026, 1, 31).isoformat()
        assert doc["periods"][0]["displayLabel"] == "Jan-26"
        assert doc["periods"][0]["interval"] == {
            "startDate": None,
            "endDate": JAN_END,
            "kind": "inception",
        }
        assert doc["periods"][0]["partialPeriod"] is False
        assert len(doc["periods"]) == len(doc["series"][0]["points"])

        assert doc["totals"][0]["value"] == "100000"
        assert doc["totals"][0]["plotValue"] == "100"

    def test_intervals_use_sample_boundaries_and_flag_partial_calendar_buckets(
        self, user, account, monkeypatch
    ):
        values = {
            date(2026, 1, 31): Decimal("100000"),
            date(2026, 2, 28): Decimal("110000"),
            date(2026, 3, 10): Decimal("120000"),
        }
        pin_chart(monkeypatch, values)
        modern = call_nav_chart(
            user, date_from="2026-01-15", date_to="2026-03-10", contract=2
        ).data
        doc = modern["chartV2"]
        assert [p["endDate"] for p in doc["periods"]] == [
            "2026-01-31",
            "2026-02-28",
            "2026-03-10",
        ]
        assert doc["periods"][0]["interval"]["kind"] == "inception"
        assert doc["periods"][0]["interval"]["startDate"] is None
        assert doc["periods"][1]["interval"] == {
            "startDate": "2026-02-01",
            "endDate": "2026-02-28",
            "kind": "sample_interval",
        }
        assert doc["periods"][1]["partialPeriod"] is False
        assert doc["periods"][2]["partialPeriod"] is True  # 10 Mar is mid-month
        keys = [p["key"] for p in doc["periods"]]
        assert len(keys) == len(set(keys))
        assert all(len(s["points"]) == len(doc["periods"]) for s in doc["series"])

    @pytest.mark.parametrize("frequency", ["D", "W", "M", "Q", "Y"])
    @pytest.mark.parametrize(
        "breakdown",
        [
            "none",
            "account",
            "asset_type",
            "asset_class",
            "currency",
            "value_contributions",
            "value_contributions_cumulative",
        ],
    )
    def test_every_mode_and_frequency_emits_aligned_contract(
        self, user, account, monkeypatch, breakdown, frequency
    ):
        Transactions.objects.create(
            investor=user,
            account=account,
            type="Cash in",
            currency="USD",
            date=datetime(2026, 2, 5, 12, tzinfo=timezone.utc),
            cash_flow=Decimal("100"),
        )
        payloads = {
            "account": {account.name: Decimal("100000")},
            "asset_type": {"Stock": Decimal("40000"), "Cash": Decimal("60000")},
            "asset_class": {"Equity": Decimal("40000"), "Cash": Decimal("60000")},
            "currency": {"USD": Decimal("100000")},
        }

        def pinned_nav(uid, ids, day, cur, breakdown=(), diagnostics=None):
            result = {"Total NAV": Decimal("100000")}
            if breakdown:
                result[breakdown[0]] = payloads[breakdown[0]]
            return result

        monkeypatch.setattr(charts, "NAV_at_date", pinned_nav)
        monkeypatch.setattr(
            charts, "IRR", lambda uid, day, cur, **kwargs: Decimal("0.1234")
        )
        modern = call_nav_chart(
            user,
            breakdown=breakdown,
            frequency=frequency,
            date_from="2026-01-01",
            date_to="2026-02-28",
            contract=2,
        ).data
        doc = modern["chartV2"]
        assert doc["kind"] == "nav"
        metrics = set(series_by_metric(doc))
        if breakdown == "none":
            assert metrics == {"nav", "irr_inception", "irr_interval"}
        elif breakdown in ("account", "asset_type", "asset_class", "currency"):
            assert metrics == {"category_nav", "irr_inception", "irr_interval"}
            categories = [s for s in doc["series"] if s["metric"] == "category_nav"]
            # Category values partition the pinned 100000 total exactly.
            assert sum(
                Decimal(s["points"][0]["value"]) for s in categories
            ) == Decimal("100000")
        elif breakdown == "value_contributions":
            assert metrics == {
                "opening_nav",
                "contributions",
                "return",
                "irr_inception",
                "irr_interval",
            }
            contributions = series_by_metric(doc)["contributions"]
            assert any(
                Decimal(p["value"]) == Decimal("100") for p in contributions["points"]
            )
        else:
            assert metrics == {
                "net_investments",
                "return",
                "irr_inception",
                "irr_interval",
            }
            net = series_by_metric(doc)["net_investments"]
            assert Decimal(net["points"][-1]["value"]) == Decimal("100")
        assert all(len(s["points"]) == len(doc["periods"]) for s in doc["series"])
        end_dates = [p["endDate"] for p in doc["periods"]]
        assert end_dates == sorted(end_dates)
        assert len(end_dates) == len(set(end_dates)) == len(modern["labels"])

    def test_duplicate_account_names_merge_legacy_but_keep_group_identity(
        self, user, monkeypatch
    ):
        first = make_account(user, name="Alpha", broker_name="B1")
        second = make_account(user, name="Alpha", broker_name="B2")

        def pinned_nav(uid, ids, day, cur, breakdown=(), diagnostics=None):
            return {"Total NAV": Decimal("100000"), "account": {"Alpha": Decimal("100000")}}

        monkeypatch.setattr(charts, "NAV_at_date", pinned_nav)
        monkeypatch.setattr(
            charts, "IRR", lambda uid, day, cur, **kwargs: Decimal("0.1234")
        )
        legacy = call_nav_chart(user, breakdown="account").data
        modern = call_nav_chart(user, breakdown="account", contract=2).data

        category_labels = [d["label"] for d in legacy["datasets"] if d["label"] == "Alpha"]
        assert len(category_labels) == 1  # legacy single merged bar

        expected_id = f"account-group:{first.id},{second.id}"
        category = next(s for s in modern["chartV2"]["series"] if s["metric"] == "category_nav")
        assert category["id"] == expected_id
        assert category["category"] == {
            "kind": "account_group",
            "memberAccountIds": sorted([first.id, second.id]),
        }

        # Renaming the display label without changing membership retains
        # identity: the breakdown key follows the new name (legacy groups by
        # exact account name), but the v2 ID stays derived from membership.
        first.name = "Alpha Prime"
        second.name = "Alpha Prime"
        first.save()
        second.save()

        def renamed_nav(uid, ids, day, cur, breakdown=(), diagnostics=None):
            return {
                "Total NAV": Decimal("100000"),
                "account": {"Alpha Prime": Decimal("100000")},
            }

        monkeypatch.setattr(charts, "NAV_at_date", renamed_nav)
        renamed = call_nav_chart(user, breakdown="account", contract=2).data
        renamed_category = next(
            s for s in renamed["chartV2"]["series"] if s["metric"] == "category_nav"
        )
        assert renamed_category["id"] == expected_id
        assert renamed_category["label"] == "Alpha Prime"
        assert renamed_category["category"]["memberAccountIds"] == sorted([first.id, second.id])

    def test_unknown_category_code_fails_v2_but_keeps_legacy_bar(
        self, user, account, monkeypatch
    ):
        def pinned_nav(uid, ids, day, cur, breakdown=(), diagnostics=None):
            return {"Total NAV": Decimal("100000"), "asset_type": {"Mystery": Decimal("1")}}

        monkeypatch.setattr(charts, "NAV_at_date", pinned_nav)
        monkeypatch.setattr(
            charts, "IRR", lambda uid, day, cur, **kwargs: Decimal("0.1234")
        )
        legacy = call_nav_chart(user, breakdown="asset_type")
        assert legacy.status_code == 200
        assert any(d["label"] == "Mystery" for d in legacy.data["datasets"])

        modern = call_nav_chart(user, breakdown="asset_type", contract=2)
        assert modern.status_code == 500
        assert modern.data["error"]["code"] == "CHART_CALCULATION_FAILED"

    def test_omitted_valuation_marks_partial_and_known_subtotal(
        self, user, account, monkeypatch
    ):
        omission = [{
            "reason": "missing_price",
            "account_id": account.id,
            "asset_id": 9,
            "currency": "USD",
            "asset_type": "Stock",
        }]

        def pinned_nav(uid, ids, day, cur, breakdown=(), diagnostics=None):
            if diagnostics is not None:
                diagnostics.extend(omission)
            return {
                "Total NAV": Decimal("90000"),
                "asset_type": {"Stock": Decimal("40000"), "Cash": Decimal("50000")},
            }

        monkeypatch.setattr(charts, "NAV_at_date", pinned_nav)
        monkeypatch.setattr(
            charts, "IRR", lambda uid, day, cur, **kwargs: Decimal("0.1234")
        )
        modern = call_nav_chart(user, breakdown="asset_type", contract=2).data
        doc = modern["chartV2"]

        total = doc["totals"][0]
        assert total["status"] == "partial"
        assert total["value"] is None and total["plotValue"] is None
        assert total["knownSubtotal"] == "90000"
        assert total["reason"] == "missing_price"

        stock = next(
            s for s in doc["series"] if s["metric"] == "category_nav" and s["label"] == "Stock"
        )
        assert stock["points"][0]["status"] == "partial"
        assert stock["points"][0]["value"] is None
        assert stock["points"][0]["knownSubtotal"] == "40000"

        cash = next(
            s for s in doc["series"] if s["metric"] == "category_nav" and s["label"] == "Cash"
        )
        assert cash["points"][0]["status"] == "ok"
        assert cash["points"][0]["value"] == "50000"

        for metric in ("irr_inception", "irr_interval"):
            irr = series_by_metric(doc)[metric]
            assert irr["points"][0]["status"] == "partial"
            assert irr["points"][0]["value"] is None
            assert irr["points"][0]["display"] == "12.3%"
        assert doc["partition"] == "unknown"

    def test_crypto_bucket_excluded_from_breakdown_is_nonpartitioning(
        self, user, account, monkeypatch
    ):
        def pinned_nav(uid, ids, day, cur, breakdown=(), diagnostics=None):
            return {
                "Total NAV": Decimal("150000"),
                "asset_type": {"Stock": Decimal("25000"), "Cash": Decimal("75000")},
                "Crypto": {"__total__": Decimal("50000"), "BTC": Decimal("50000")},
            }

        monkeypatch.setattr(charts, "NAV_at_date", pinned_nav)
        monkeypatch.setattr(
            charts, "IRR", lambda uid, day, cur, **kwargs: Decimal("0.1234")
        )
        modern = call_nav_chart(user, breakdown="asset_type", contract=2).data
        doc = modern["chartV2"]
        assert doc["partition"] == "legacy_non_partitioning"
        # Legacy values untouched despite the modern completeness flag.
        assert (
            modern["datasets"]
            == call_nav_chart(user, breakdown="asset_type").data["datasets"]
        )


# ---------------------------------------------------------------------------
# NAV endpoint: v2 errors and emptiness
# ---------------------------------------------------------------------------


class TestNavErrorsV2:
    def test_invalid_frequency_is_400_only_for_v2(self, user, account, monkeypatch):
        pin_chart(monkeypatch, {date(2026, 1, 31): Decimal("100000")})
        legacy = call_nav_chart(user, frequency="X")
        assert legacy.status_code == 200
        assert legacy.data.get("empty") is True

        modern = call_nav_chart(user, frequency="X", contract=2)
        assert modern.status_code == 400
        assert modern.data["error"]["code"] == "INVALID_CHART_QUERY"

    def test_invalid_mode_and_reversed_range_are_400(self, user, account, monkeypatch):
        pin_chart(monkeypatch, {date(2026, 1, 31): Decimal("100000")})
        bogus_mode = call_nav_chart(user, breakdown="bogus", contract=2)
        assert bogus_mode.status_code == 400
        assert bogus_mode.data["error"]["code"] == "INVALID_CHART_QUERY"

        reversed_range = call_nav_chart(
            user, date_from="2026-02-28", date_to="2026-01-31", contract=2
        )
        assert reversed_range.status_code == 400

    def test_unsupported_contract_version_is_400(self, user, account):
        response = call_nav_chart(user, contract=3)
        assert response.status_code == 400
        assert response.data["error"]["code"] == "INVALID_CHART_QUERY"

    def test_calculation_failure_is_generic_500_for_v2_only(
        self, user, account, monkeypatch
    ):
        def explode(*args, **kwargs):
            raise RuntimeError("secret internal detail")

        monkeypatch.setattr(dashboard_views, "get_nav_chart_data", explode)
        legacy = call_nav_chart(user)
        assert legacy.status_code == 200
        assert legacy.data.get("empty") is True

        modern = call_nav_chart(user, contract=2)
        assert modern.status_code == 500
        assert modern.data["error"]["code"] == "CHART_CALCULATION_FAILED"
        assert modern.data["error"]["retryable"] is True
        assert "secret" not in str(modern.data["error"]["message"])

    def test_no_selected_accounts_is_empty_outcome_not_error(self, user, monkeypatch):
        user.selected_account_type = "account"
        user.selected_account_id = 999999
        user.save()
        response = call_nav_chart(user, contract=2)
        assert response.status_code == 200
        assert response.data.get("empty") is True
        assert response.data["chartV2"]["outcome"] == "empty"
        assert response.data["chartV2"]["series"] == []
        assert response.data["chartV2"]["periods"] == []


# ---------------------------------------------------------------------------
# Allocation endpoint (dashboard breakdown)
# ---------------------------------------------------------------------------


def breakdown_fixture(total=Decimal("100"), asset_type=None, asset_class=None, currency=None,
                      diagnostics=(), crypto=None):
    return {
        "Total NAV": total,
        "asset_type": asset_type if asset_type is not None else
        {"Stock": Decimal("25"), "Cash": Decimal("75")},
        "asset_class": asset_class if asset_class is not None else
        {"Equity": Decimal("25"), "Cash": Decimal("75")},
        "currency": currency if currency is not None else {"USD": Decimal("100")},
        "Crypto": crypto if crypto is not None else {},
        "diagnostics": list(diagnostics),
    }


def pin_breakdown(monkeypatch, fixture):
    def pinned_nav(uid, ids, day, cur, breakdown=(), diagnostics=None):
        if diagnostics is not None:
            diagnostics.extend(fixture.get("diagnostics", []))
        return {k: v for k, v in fixture.items() if k != "diagnostics"}

    monkeypatch.setattr(dashboard_views, "NAV_at_date", pinned_nav)


class TestAllocationContractV2:
    def test_eligible_partition_with_exact_ratios_and_ranks(self, user, account, monkeypatch):
        pin_breakdown(monkeypatch, breakdown_fixture())
        legacy = call_breakdown(user).data
        modern = call_breakdown(user, contract=2).data
        assert "chartV2" not in legacy
        for key in ("assetType", "assetClass", "currency", "totalNAV"):
            assert modern[key] == legacy[key]

        doc = modern["chartV2"]["assetType"]
        assert doc["version"] == 2
        assert doc["kind"] == "allocation"
        assert doc["outcome"] == "ready"
        assert doc["partition"] == "complete"
        summary = doc["allocationSummary"]
        assert summary["dimension"] == "asset_type"
        assert summary["unit"] == {"kind": "money", "currency": "USD", "plotDivisor": "1"}
        assert summary["denominator"]["value"] == "100"
        assert summary["denominator"]["status"] == "ok"
        assert summary["totalShare"]["value"] == "1"
        assert summary["totalShare"]["status"] == "ok"
        assert summary["pieEligibility"] == "eligible"

        allocations = doc["allocations"]
        by_series = {a["seriesId"]: a for a in allocations}
        assert by_series["asset_type:Cash"]["rank"] == 1
        assert by_series["asset_type:Cash"]["amount"]["value"] == "75"
        assert by_series["asset_type:Cash"]["share"]["value"] == "0.75"
        assert by_series["asset_type:Cash"]["share"]["display"] == "75.0%"
        assert by_series["asset_type:Stock"]["rank"] == 2
        assert by_series["asset_type:Stock"]["share"]["value"] == "0.25"
        ranks = [a["rank"] for a in allocations]
        assert ranks == sorted(ranks)

        series_ids = {s["id"] for s in doc["series"]}
        assert series_ids == {"asset_type:Cash", "asset_type:Stock"}
        assert all(s["metric"] == "category_nav" for s in doc["series"])

    def test_signed_amounts_are_signed_not_eligible(self, user, account, monkeypatch):
        fixture = breakdown_fixture(
            asset_type={"Option": Decimal("-25"), "Cash": Decimal("125")},
            asset_class={},
            currency={},
        )
        pin_breakdown(monkeypatch, fixture)
        doc = call_breakdown(user, contract=2).data["chartV2"]["assetType"]
        assert doc["allocationSummary"]["pieEligibility"] == "signed"
        signed = next(a for a in doc["allocations"] if a["seriesId"] == "asset_type:Option")
        assert signed["amount"]["value"] == "-25"
        assert signed["share"]["value"] == "-0.25"  # denominator positive: share available

    def test_incomplete_partition_is_not_full_circle(self, user, account, monkeypatch):
        fixture = breakdown_fixture(
            asset_type={"Stock": Decimal("25"), "Cash": Decimal("50")},
            asset_class={},
            currency={},
        )
        pin_breakdown(monkeypatch, fixture)
        doc = call_breakdown(user, contract=2).data["chartV2"]["assetType"]
        assert doc["allocationSummary"]["pieEligibility"] == "nonpartitioning"
        assert doc["allocationSummary"]["totalShare"]["value"] is None
        assert doc["allocationSummary"]["totalShare"]["status"] == "not_available"
        assert doc["partition"] == "legacy_non_partitioning"

    @pytest.mark.parametrize("total", [Decimal("0"), Decimal("-100")])
    def test_nonpositive_totals_are_ineligible_with_unavailable_shares(
        self, user, account, monkeypatch, total
    ):
        fixture = breakdown_fixture(
            total=total, asset_type={"Stock": Decimal("25")}, asset_class={}, currency={}
        )
        pin_breakdown(monkeypatch, fixture)
        doc = call_breakdown(user, contract=2).data["chartV2"]["assetType"]
        assert doc["allocationSummary"]["pieEligibility"] == "nonpositive_total"
        assert doc["allocationSummary"]["denominator"]["value"] == format(total, "f")
        allocation = doc["allocations"][0]
        assert allocation["share"]["value"] is None
        assert allocation["share"]["status"] == "not_available"

    def test_missing_valuation_takes_precedence_and_is_partial(
        self, user, account, monkeypatch
    ):
        fixture = breakdown_fixture(
            diagnostics=[{
                "reason": "missing_price",
                "account_id": account.id,
                "asset_id": 9,
                "currency": "USD",
                "asset_type": "Stock",
            }]
        )
        pin_breakdown(monkeypatch, fixture)
        doc = call_breakdown(user, contract=2).data["chartV2"]["assetType"]
        assert doc["outcome"] == "partial"
        assert doc["allocationSummary"]["pieEligibility"] == "incomplete"
        assert doc["allocationSummary"]["denominator"]["status"] == "partial"
        assert doc["allocationSummary"]["denominator"]["knownSubtotal"] == "100"
        stock = next(a for a in doc["allocations"] if a["seriesId"] == "asset_type:Stock")
        assert stock["amount"]["status"] == "partial"
        assert stock["amount"]["knownSubtotal"] == "25"
        cash = next(a for a in doc["allocations"] if a["seriesId"] == "asset_type:Cash")
        assert cash["amount"]["status"] == "ok"

    def test_crypto_bucket_keeps_legacy_nonpartitioning(self, user, account, monkeypatch):
        fixture = breakdown_fixture(
            total=Decimal("150"),
            crypto={"__total__": Decimal("50"), "BTC": Decimal("50")},
        )
        pin_breakdown(monkeypatch, fixture)
        doc = call_breakdown(user, contract=2).data["chartV2"]["assetType"]
        assert doc["partition"] == "legacy_non_partitioning"
        assert doc["allocationSummary"]["pieEligibility"] == "nonpartitioning"


# ---------------------------------------------------------------------------
# Security history endpoints
# ---------------------------------------------------------------------------


class TestSecurityContractV2:
    def test_bond_price_history_wraps_legacy_and_uses_percent_of_nominal(
        self, user, asset, bond_asset
    ):
        Prices.objects.create(
            security=bond_asset, date=date(2026, 1, 5), price=Decimal("98.5")
        )
        Prices.objects.create(
            security=bond_asset, date=date(2026, 1, 20), price=Decimal("99")
        )
        legacy = call_price_history(user, bond_asset.id)
        assert legacy.status_code == 200
        assert json.loads(legacy.content) == [
            {"date": "2026-01-05", "price": 98.5},
            {"date": "2026-01-20", "price": 99.0},
        ]

        modern = call_price_history(user, bond_asset.id, contract=2)
        assert modern.status_code == 200
        assert modern.data["legacy"] == json.loads(legacy.content)
        doc = modern.data["chartV2"]
        assert doc["kind"] == "price"
        assert doc["security"] == {"id": bond_asset.id, "instrumentType": "Bond"}
        series = doc["series"][0]
        assert series["id"] == f"security:{bond_asset.id}:price"
        assert series["metric"] == "price"
        assert series["axis"] == "price"
        assert series["unit"] == {"kind": "percent_of_nominal", "plotDivisor": "1"}
        # Prices.price is a 6dp column: the exact stored value keeps its scale.
        assert series["points"][0]["value"] == "98.500000"
        assert series["points"][0]["plotValue"] == "98.500000"
        assert series["points"][0]["display"] == "98.5% of nominal"
        first_price = Prices.objects.filter(security=bond_asset).order_by("date").first()
        assert doc["periods"][0]["key"] == f"security:{bond_asset.id}:price:row:{first_price.pk}"
        assert doc["periods"][0]["endDate"] == "2026-01-05"
        assert [p["endDate"] for p in doc["periods"]] == ["2026-01-05", "2026-01-20"]

    def test_stock_price_history_uses_money_unit(self, user, asset):
        Prices.objects.create(security=asset, date=date(2026, 1, 5), price=Decimal("50.25"))
        user.digits = 2
        user.save()
        modern = call_price_history(user, asset.id, contract=2).data["chartV2"]
        series = modern["series"][0]
        assert series["unit"] == {"kind": "money", "currency": "USD", "plotDivisor": "1"}
        assert series["points"][0]["value"] == "50.250000"
        assert series["points"][0]["display"] == "$50.25"

    def test_position_history_preserves_precision_and_same_day_events(
        self, user, asset, account
    ):
        rows = [
            ("Buy", Decimal("0.000116590"), datetime(2026, 1, 5, 10, tzinfo=timezone.utc)),
            ("Sell", Decimal("-0.000016590"), datetime(2026, 1, 10, 10, tzinfo=timezone.utc)),
            ("Buy", Decimal("2"), datetime(2026, 1, 15, 9, tzinfo=timezone.utc)),
            ("Sell", Decimal("-1"), datetime(2026, 1, 15, 16, tzinfo=timezone.utc)),
        ]
        for kind, qty, when in rows:
            Transactions.objects.create(
                investor=user,
                account=account,
                security=asset,
                currency="USD",
                type=kind,
                date=when,
                quantity=qty,
                price=Decimal("1"),
            )
        legacy = call_position_history(user, asset.id)
        assert legacy.status_code == 200
        # JsonResponse's DjangoJSONEncoder renders Decimals as strings; the
        # legacy wire format keeps exact stored precision that way.
        assert json.loads(legacy.content) == [
            {"date": "2026-01-05", "position": "0.000116590"},
            {"date": "2026-01-10", "position": "0.000100000"},
            {"date": "2026-01-15", "position": "2.000100000"},
            {"date": "2026-01-15", "position": "1.000100000"},
        ]

        modern = call_position_history(user, asset.id, contract=2)
        assert modern.data["legacy"] == json.loads(legacy.content)
        doc = modern.data["chartV2"]
        assert doc["kind"] == "position"
        series = doc["series"][0]
        assert series["metric"] == "position"
        assert series["axis"] == "quantity"
        assert series["unit"] == {"kind": "quantity", "plotDivisor": "1"}
        assert series["points"][0]["value"] == "0.000116590"
        assert series["points"][0]["plotValue"] == "0.000116590"
        same_day = [p for p in doc["periods"] if p["endDate"] == "2026-01-15"]
        assert len(same_day) == 2
        keys = [p["key"] for p in doc["periods"]]
        assert len(keys) == len(set(keys))
        transaction_ids = list(
            Transactions.objects.filter(security=asset).order_by("date").values_list(
                "id", flat=True
            )
        )
        assert keys == [f"security:{asset.id}:position:row:{pk}" for pk in transaction_ids]

    def test_empty_security_history_is_empty_outcome(self, user, asset):
        modern = call_price_history(user, asset.id, contract=2)
        assert modern.status_code == 200
        assert modern.data["chartV2"]["outcome"] == "empty"
        assert modern.data["legacy"] == []
