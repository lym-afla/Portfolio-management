"""Endpoint contract tests for the dashboard summary statement (Phase D).

Pins:
- the legacy five-field response WITHOUT ``summary_contract`` stays
  byte-identical (no ``summaryV2`` key, exact legacy formatting);
- ``summary_contract=2`` adds the opt-in ``summaryV2`` document on the SAME
  response without touching the legacy keys;
- unsupported contract versions are an explicit 400, never a downgrade.
"""

from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from common.models import Prices, Transactions
from users.models import CustomUser


def seed_approved_example(user, account):
    """The hand-derived approved-example dataset (see the service test suite
    for the full arithmetic): NAV 117,500; net capital 100,000."""
    stock_a = common_asset(user, "Alpha")
    stock_b = common_asset(user, "Beta")
    d1 = date(2026, 1, 5)
    Transactions.objects.create(
        investor=user, account=account, security=None, date=d1,
        type="Cash in", currency="USD", cash_flow=Decimal("105000"),
    )
    Transactions.objects.create(
        investor=user, account=account, security=None, date=d1,
        type="Cash out", currency="USD", cash_flow=Decimal("-5000"),
    )
    Transactions.objects.create(
        investor=user, account=account, security=stock_a, date=d1,
        type="Buy", currency="USD", quantity=Decimal("500"),
        price=Decimal("100"), commission=Decimal("-1000"),
    )
    Transactions.objects.create(
        investor=user, account=account, security=stock_b, date=d1,
        type="Buy", currency="USD", quantity=Decimal("400"), price=Decimal("150"),
    )
    Transactions.objects.create(
        investor=user, account=account, security=stock_a, date=date(2026, 1, 20),
        type="Dividend", currency="USD", cash_flow=Decimal("3500"),
    )
    Transactions.objects.create(
        investor=user, account=account, security=stock_a, date=date(2026, 1, 20),
        type="Tax", currency="USD", cash_flow=Decimal("-500"),
    )
    Transactions.objects.create(
        investor=user, account=account, security=stock_a, date=date(2026, 2, 10),
        type="Sell", currency="USD", quantity=Decimal("-500"), price=Decimal("116"),
    )
    Prices.objects.create(
        security=stock_b, date=date(2026, 10, 1), price=Decimal("168.75")
    )


def common_asset(user, name):
    from common.models import Assets

    asset = Assets.objects.create(
        type="Stock", ISIN=f"isin-{name}", name=name, currency="USD",
        exposure="Equity",
    )
    asset.investors.add(user)
    return asset


class DashboardSummaryContractV2Tests(APITestCase):
    """Negotiation and legacy parity on /dashboard/api/get-summary/."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="summary-contract-user",
            email="summary-contract@example.com",
            password="testpass123",
        )
        self.user.default_currency = "USD"
        self.user.digits = 2
        self.user.save()
        from common.models import Accounts, Brokers

        broker = Brokers.objects.create(
            investor=self.user, name="Broker", country="US", cash_precision=2
        )
        self.account = Accounts.objects.create(broker=broker, name="Main")
        seed_approved_example(self.user, self.account)
        # The JWT middleware reads the effective date from the token claim
        # (session/database are fallbacks for the live flow only) — mint the
        # token with the claim so the test does not silently depend on today.
        token = RefreshToken.for_user(self.user)
        token["effective_current_date"] = "2026-10-15"
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {str(token.access_token)}"

    def test_legacy_response_is_unchanged_without_the_parameter(self):
        response = self.client.get("/dashboard/api/get-summary/")
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {
            "Current NAV", "Invested", "Cash-out", "total_return", "irr",
        }
        assert data["Current NAV"] == "$117,500.00"
        assert data["Invested"] == "$105,000.00"
        assert data["Cash-out"] == "($5,000.00)"
        assert data["total_return"] == "16.7%"
        assert isinstance(data["irr"], str)

    def test_v2_adds_summary_document_without_touching_legacy_keys(self):
        response = self.client.get(
            "/dashboard/api/get-summary/", {"summary_contract": "2"}
        )
        assert response.status_code == 200
        data = response.json()
        # The legacy keys are identical to the legacy-only response.
        assert data["Current NAV"] == "$117,500.00"
        assert data["Invested"] == "$105,000.00"
        assert data["Cash-out"] == "($5,000.00)"
        statement = data["summaryV2"]
        assert statement["version"] == 2
        assert statement["kind"] == "statement"
        assert statement["context"]["effectiveDate"] == "2026-10-15"
        assert statement["context"]["currency"] == "USD"
        assert statement["context"]["accountIds"] == [self.account.id]
        assert Decimal(statement["capital"]["invested"]["raw"]) == Decimal("105000")
        assert Decimal(statement["capital"]["cashOut"]["raw"]) == Decimal("-5000")
        assert Decimal(statement["capital"]["netInvestedCapital"]["raw"]) == Decimal("100000")
        assert Decimal(statement["netResult"]["nav"]["raw"]) == Decimal("117500")
        assert Decimal(statement["netResult"]["controlTotal"]["raw"]) == Decimal("17500")
        assert statement["netResult"]["reconciliation"] == "reconciled"
        assert statement["status"] == "complete"
        returns = statement["returns"]
        assert Decimal(returns["totalReturn"]["value"]) == (
            (Decimal("117500") + Decimal("5000")) / Decimal("105000") - 1
        )
        assert returns["irr"]["display"].endswith("%")

    def test_unsupported_contract_version_is_an_explicit_400(self):
        response = self.client.get(
            "/dashboard/api/get-summary/", {"summary_contract": "3"}
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "INVALID_SUMMARY_QUERY"
        assert body["error"]["retryable"] is False

    def test_statement_rows_carry_display_and_status(self):
        response = self.client.get(
            "/dashboard/api/get-summary/", {"summary_contract": "2"}
        )
        data = response.json()
        components = data["summaryV2"]["netResult"]["components"]
        assert components["realizedPrice"]["display"] == "$8,000.00"
        assert components["fees"]["display"] == "($1,000.00)"
        assert components["taxes"]["status"] == "ok"
        assert components["fx"]["display"] == "–"
