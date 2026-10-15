"""Phase C Task 7: per-account holdings context for the security detail page.

`get_account_holdings` is the canonical read model: one row per account that
transacted the security up to the valuation date, with the account's
remaining position (services.positions.position — the same canonical sums
the position charts use, never lifetime buys) and an open/closed status as
of THAT date. `get_security_detail` exposes the qualified display rows.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from django.test import RequestFactory

from common.models import Accounts, Assets, Brokers, Transactions
from services.positions import get_account_holdings
from services.securities import get_security_detail


@pytest.fixture
def stock(user):
    asset = Assets.objects.create(
        type="Stock", ISIN="US0000000001", name="Testco", currency="USD"
    )
    asset.investors.add(user)
    return asset


@pytest.fixture
def brokers(user):
    ibkr = Brokers.objects.create(investor=user, name="IBKR", country="US")
    tink = Brokers.objects.create(investor=user, name="Tinkoff", country="RU")
    return ibkr, tink


@pytest.mark.django_db
class TestGetAccountHoldings:
    def _buy(self, user, account, security, quantity, when, price=Decimal("10")):
        Transactions.objects.create(
            investor=user,
            account=account,
            security=security,
            currency=security.currency,
            type="Buy" if quantity > 0 else "Sell",
            date=datetime(when.year, when.month, when.day, tzinfo=timezone.utc),
            quantity=quantity,
            price=price,
        )

    def test_open_and_closed_accounts_at_the_valuation_date(self, user, stock, brokers):
        ibkr, tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        iis = Accounts.objects.create(broker=tink, name="IIS")
        # IBKR Main: partial disposal — still holds 4.
        self._buy(user, main, stock, Decimal("10"), date(2026, 1, 5))
        self._buy(user, main, stock, Decimal("-6"), date(2026, 2, 5))
        # Tinkoff IIS: full disposal — held, now zero.
        self._buy(user, iis, stock, Decimal("3"), date(2026, 1, 10))
        self._buy(user, iis, stock, Decimal("-3"), date(2026, 2, 10))

        holdings = get_account_holdings(stock, date(2026, 3, 1), user)
        by_account = {row["account_id"]: row for row in holdings}
        assert by_account[main.id]["status"] == "open"
        assert by_account[main.id]["quantity"] == "4.000000"
        assert by_account[iis.id]["status"] == "closed"
        assert by_account[iis.id]["quantity"] == "0.000000"

    def test_reopened_holding_is_open_at_the_valuation_date(self, user, stock, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        self._buy(user, main, stock, Decimal("5"), date(2026, 1, 5))
        self._buy(user, main, stock, Decimal("-5"), date(2026, 1, 20))
        self._buy(user, main, stock, Decimal("2"), date(2026, 2, 10))
        holdings = get_account_holdings(stock, date(2026, 3, 1), user)
        assert [row["status"] for row in holdings] == ["open"]
        assert holdings[0]["quantity"] == "2.000000"

    def test_historical_date_ignores_later_transactions(self, user, stock, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        self._buy(user, main, stock, Decimal("5"), date(2026, 1, 5))
        self._buy(user, main, stock, Decimal("-5"), date(2026, 2, 5))
        # As of 2026-01-31 the disposal had not happened yet.
        holdings = get_account_holdings(stock, date(2026, 1, 31), user)
        assert [row["status"] for row in holdings] == ["open"]
        assert holdings[0]["quantity"] == "5.000000"

    def test_multiple_accounts_per_broker_listed_separately(self, user, stock, brokers):
        ibkr, _tink = brokers
        first = Accounts.objects.create(broker=ibkr, name="Margin")
        second = Accounts.objects.create(broker=ibkr, name="Cash")
        self._buy(user, first, stock, Decimal("1"), date(2026, 1, 5))
        self._buy(user, second, stock, Decimal("7"), date(2026, 1, 6))
        holdings = get_account_holdings(stock, date(2026, 2, 1), user)
        quantities = sorted(row["quantity"] for row in holdings)
        assert quantities == ["1.000000", "7.000000"]

    def test_open_rows_precede_closed_rows(self, user, stock, brokers):
        ibkr, tink = brokers
        closed = Accounts.objects.create(broker=ibkr, name="Closed")
        held = Accounts.objects.create(broker=tink, name="Held")
        self._buy(user, closed, stock, Decimal("1"), date(2026, 1, 1))
        self._buy(user, closed, stock, Decimal("-1"), date(2026, 1, 15))
        self._buy(user, held, stock, Decimal("9"), date(2026, 1, 20))
        holdings = get_account_holdings(stock, date(2026, 2, 1), user)
        assert [row["status"] for row in holdings] == ["open", "closed"]

    def test_no_transactions_yields_no_rows(self, user, stock):
        assert get_account_holdings(stock, date(2026, 3, 1), user) == []


@pytest.mark.django_db
class TestSecurityDetailHoldingsContext:
    def test_detail_exposes_qualified_holding_rows(self, user, stock, brokers):
        ibkr, tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        iis = Accounts.objects.create(broker=tink, name="IIS")
        Transactions.objects.create(
            investor=user, account=main, security=stock, currency="USD",
            type="Buy", date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            quantity=Decimal("10"), price=Decimal("10"),
        )
        Transactions.objects.create(
            investor=user, account=iis, security=stock, currency="USD",
            type="Buy", date=datetime(2026, 1, 10, tzinfo=timezone.utc),
            quantity=Decimal("3"), price=Decimal("10"),
        )
        Transactions.objects.create(
            investor=user, account=iis, security=stock, currency="USD",
            type="Sell", date=datetime(2026, 2, 10, tzinfo=timezone.utc),
            quantity=Decimal("-3"), price=Decimal("10"),
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        request.effective_current_date = "2026-03-01"

        detail = get_security_detail(request, stock.id)

        holdings = detail["holdings"]
        assert [row["status"] for row in holdings] == ["open", "closed"]
        assert holdings[0]["display_name"] == "IBKR \u2013 Main"
        assert holdings[0]["broker_name"] == "IBKR"
        assert holdings[0]["account_name"] == "Main"
        assert holdings[0]["quantity"] == "10.000000"
        assert holdings[1]["display_name"] == "Tinkoff \u2013 IIS"
        assert holdings[1]["quantity"] == "0.000000"
