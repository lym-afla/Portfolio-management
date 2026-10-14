"""Phase C review round: holdings candidate discovery must cover the SAME
sources as canonical position(), and quantities must carry an exact grouped
display alongside the raw string.

Finding 1: position() for Crypto assets also includes commissions paid in
that coin (recorded on OTHER securities' transactions) and coin-settled
option cashflows. An account whose coin position comes only from those
indirect sources was invisible to "Currently held with". Discovery must
cover the same sources, investor and historical cutoff — without changing
position()'s formulas. A dividend-only or zero-quantity record must NOT
falsely establish "Previously held" when no holding ever existed.

Finding 4: quantities render with thousands separators via an exact grouped
display (no Number conversion, no precision loss); the raw string stays.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from django.test import RequestFactory

from common.models import Accounts, Assets, Brokers, Transactions
from services.positions import get_account_holdings
from services.securities import get_security_detail


@pytest.fixture
def coin(user):
    asset = Assets.objects.create(
        type="Crypto", ISIN="CRYPTO:BTC", name="BTC", currency="USD"
    )
    asset.investors.add(user)
    return asset


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


def _row(user, account, security, when, price=Decimal("10"), **fields):
    return Transactions.objects.create(
        investor=user,
        account=account,
        security=security,
        currency=fields.pop("currency", security.currency),
        type=fields.pop("type", "Buy"),
        date=datetime(when.year, when.month, when.day, tzinfo=timezone.utc),
        price=price,
        **fields,
    )


@pytest.mark.django_db
class TestIndirectCryptoSources:
    def test_commission_only_coin_account_is_discovered(self, user, coin, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        usdt = Assets.objects.create(
            type="Crypto", ISIN="CRYPTO:USDT", name="USDT", currency="USD"
        )
        usdt.investors.add(user)
        # A BTC fee recorded on a USDT trade: canonical position() depletes the
        # BTC holding by the signed commission even though BTC has no direct
        # transaction in this account.
        _row(user, main, usdt, date(2026, 1, 5),
             quantity=Decimal("100"), commission_currency="BTC",
             commission=Decimal("-0.5"))
        holdings = get_account_holdings(coin, date(2026, 2, 1), user)
        assert [row["account_id"] for row in holdings] == [main.id]
        # Canonical position: +1 buy on USDT adds nothing to BTC; the -0.5 BTC
        # commission depletes. Wait — no BTC buy exists, so the commission sum
        # IS the whole position: -0.5.
        assert holdings[0]["quantity"] == "-0.500000"
        assert holdings[0]["status"] == "open"

    def test_option_cashflow_only_coin_account_is_discovered(self, user, coin, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        opt = Assets.objects.create(
            type="Option", ISIN="CRYPTO:OPT:X", name="BTC-OPT", currency="BTC"
        )
        opt.investors.add(user)
        # A coin-settled option payout: cash_flow in BTC recorded against the
        # OPTION security. Canonical position() adds it for the coin.
        _row(user, main, opt, date(2026, 1, 5),
             currency="BTC", cash_flow=Decimal("0.25"))
        holdings = get_account_holdings(coin, date(2026, 2, 1), user)
        assert [row["account_id"] for row in holdings] == [main.id]
        assert holdings[0]["quantity"] == "0.250000"
        assert holdings[0]["status"] == "open"

    def test_non_crypto_ignores_commission_source(self, user, stock, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        other = Assets.objects.create(
            type="Stock", ISIN="US0000000009", name="Otherco", currency="USD"
        )
        other.investors.add(user)
        # For NON-crypto assets canonical position() ignores commissions and
        # option cashflows — discovery must mirror that gate.
        _row(user, main, other, date(2026, 1, 5),
             quantity=Decimal("10"), commission_currency="Testco",
             commission=Decimal("-1"))
        assert get_account_holdings(stock, date(2026, 2, 1), user) == []

    def test_zero_commission_and_zero_cashflow_establish_nothing(self, user, coin, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        usdt = Assets.objects.create(
            type="Crypto", ISIN="CRYPTO:USDT", name="USDT", currency="USD"
        )
        usdt.investors.add(user)
        opt = Assets.objects.create(
            type="Option", ISIN="CRYPTO:OPT:X", name="BTC-OPT", currency="BTC"
        )
        opt.investors.add(user)
        _row(user, main, usdt, date(2026, 1, 5),
             quantity=Decimal("100"), commission_currency="BTC",
             commission=Decimal("0"))
        _row(user, main, opt, date(2026, 1, 6),
             currency="BTC", cash_flow=Decimal("0"))
        # Zero contributions establish no position (canonical position()
        # ignores them) — the account must not appear as "Previously held".
        assert get_account_holdings(coin, date(2026, 2, 1), user) == []

    def test_dividend_only_zero_quantity_establishes_nothing(self, user, stock, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        _row(user, main, stock, date(2026, 1, 5),
             type="Dividend", quantity=Decimal("0"))
        # No holding ever existed: neither "Currently" nor "Previously held".
        assert get_account_holdings(stock, date(2026, 2, 1), user) == []

    def test_null_quantity_record_establishes_nothing(self, user, stock, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        _row(user, main, stock, date(2026, 1, 5), type="Dividend", quantity=None)
        assert get_account_holdings(stock, date(2026, 2, 1), user) == []

    def test_zero_then_real_buy_is_open(self, user, stock, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        _row(user, main, stock, date(2026, 1, 5), quantity=Decimal("0"))
        _row(user, main, stock, date(2026, 1, 10), quantity=Decimal("5"))
        holdings = get_account_holdings(stock, date(2026, 2, 1), user)
        assert [row["status"] for row in holdings] == ["open"]

    def test_investor_isolation(self, user, stock, brokers, django_user_model):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        other_user = django_user_model.objects.create_user(
            username="other", email="other@example.com", password="x"
        )
        _row(other_user, main, stock, date(2026, 1, 5), quantity=Decimal("5"))
        assert get_account_holdings(stock, date(2026, 2, 1), user) == []

    def test_cutoff_isolation(self, user, stock, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        usdt = Assets.objects.create(
            type="Crypto", ISIN="CRYPTO:USDT", name="USDT", currency="USD"
        )
        usdt.investors.add(user)
        _row(user, main, stock, date(2026, 3, 1), quantity=Decimal("5"))
        _row(user, main, usdt, date(2026, 3, 2),
             quantity=Decimal("100"), commission_currency="Testco",
             commission=Decimal("-1"))
        # Both the direct row and the indirect row sit after the cutoff.
        assert get_account_holdings(stock, date(2026, 2, 1), user) == []


@pytest.mark.django_db
class TestHoldingsGroupedDisplay:
    def test_detail_supplies_exact_grouped_display(self, user, stock, brokers):
        ibkr, _tink = brokers
        main = Accounts.objects.create(broker=ibkr, name="Main")
        _row(user, main, stock, date(2026, 1, 5), quantity=Decimal("10000"))
        Transactions.objects.create(
            investor=user,
            account=Accounts.objects.create(broker=ibkr, name="Short"),
            security=stock,
            currency="USD",
            type="Sell",
            date=datetime(2026, 1, 6, tzinfo=timezone.utc),
            quantity=Decimal("-1234.5"),
            price=Decimal("10"),
        )
        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        request.effective_current_date = "2026-03-01"

        detail = get_security_detail(request, stock.id)
        by_account = {row["account_id"]: row for row in detail["holdings"]}
        # Raw string stays exact; the display groups the integer part only.
        assert by_account[main.id]["quantity"] == "10000.000000"
        assert by_account[main.id]["quantity_display"] == "10,000.000000"
        negative = by_account[
            [row["account_id"] for row in detail["holdings"] if row["quantity"].startswith("-")][0]
        ]
        assert negative["quantity"] == "-1234.500000"
        assert negative["quantity_display"] == "-1,234.500000"
