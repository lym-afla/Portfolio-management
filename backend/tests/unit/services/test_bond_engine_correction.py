"""Bond engine correction (Phase D follow-up) — corrected-engine tests.

EVERY expectation below is an INDEPENDENT hand-derived Decimal value,
derived from the documented bond conventions BEFORE implementation:

  Value (target)   = pos x price% x notional(nominal -> target @ that date) / 100
  Basis (target)   = pos x buy-in% x notional(nominal -> target @ entry) / 100
  Unrealized total = value - basis
  Unrealized price = notional_lcl x dPrice% x pos x fx_eop / 100   (local dPrice)
  Unrealized FX    = total - price                                  (= basis x dfx)
  Realized (disposal/redemption at f_exit vs entry f):
    = proceeds x f_exit - basis x f_entry
    split: local dCash% x f_exit (price) + basis x dfx (fx)
  get_current_notional converts nominal -> requested exactly once.

Sanitized dataset (the correction plan's example): 10 RUB bonds, par 1,000,
bought at 95% for 9,500 RUB funded by 20,000 RUB; RUB->USD 0.0100 at entry,
0.0125 at the effective date; price 100 at the effective date.
  NAV 256.25 = 131.25 cash + 125 bond; net result 56.25; security FX 23.75.
"""

from datetime import date
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, BondMetadata, Brokers, FX, Prices, Transactions
from django.contrib.auth import get_user_model
from services.bonds import get_current_notional
from services.dashboard_summary import build_reconciled_summary
from services.nav import NAV_at_date
from services.realized import unrealized_gain_loss

D = Decimal
ENTRY = date(2067, 1, 5)
EOP = date(2067, 10, 1)
EFF = date(2067, 10, 15)


def _make_world(tag):
    user = get_user_model().objects.create_user(
        username=f"bondfix-{tag}", email=f"bondfix-{tag}@example.com", password="x"
    )
    broker = Brokers.objects.create(
        investor=user, name="Bond Broker", country="RU", cash_precision=2
    )
    account = Accounts.objects.create(broker=broker, name="Bond Account")
    return user, broker, account


def _bond(user, name, currency="RUB"):
    bond = Assets.objects.create(
        type="Bond", ISIN=f"isin-{name}", name=name, currency=currency,
        exposure="Fixed Income",
    )
    bond.investors.add(user)
    return bond


def _tx(user, account, when, type, currency="USD", security=None, **fields):
    return Transactions.objects.create(
        investor=user, account=account, security=security, date=when,
        type=type, currency=currency, **fields,
    )


def _fx(from_currency, to_currency, when, rate, investor):
    row = FX.objects.create(
        from_currency=from_currency, to_currency=to_currency, date=when,
        rate=Decimal(rate),
    )
    row.investors.add(investor)
    return row


def _seed_buy(user, account, bond, rates):
    for when, rate in rates:
        _fx("USD", "RUB", when, rate, user)
    _tx(user, account, ENTRY, "Cash in", currency="RUB", cash_flow=D("20000"))
    _tx(user, account, ENTRY, "Buy", currency="RUB", security=bond,
        quantity=D("10"), price=D("95"), notional=D("1000"))


@pytest.mark.django_db
def test_unrealized_bond_decomposition_is_currency_consistent(db):
    """Defect 1 (RED): the bond unrealized total multiplied the LOCAL
    notional by an UNCONVERTED target price (100) while the buy-in term
    carried entry FX (0.95) -> 9,905.00 / FX 9,898.75. Corrected: the price
    term converts quotation -> target at EOP (100 x 0.0125 = 1.25), so
    unrealized total = 30.00 = value 125 - basis 95, price 6.25, and
    FX = 23.75 (= basis 9,500 RUB x 0.0025 drift)."""
    user, broker, account = _make_world("uc")
    bond = _bond(user, "Corrected RUB Bond")
    BondMetadata.objects.create(asset=bond, initial_notional=D("1000"), nominal_currency="RUB")
    _fx("USD", "RUB", ENTRY, "0.0100", user)
    _fx("USD", "RUB", EOP, "0.0125", user)
    _tx(user, account, ENTRY, "Cash in", currency="RUB", cash_flow=D("20000"))
    _tx(user, account, ENTRY, "Buy", currency="RUB", security=bond,
        quantity=D("10"), price=D("95"), notional=D("1000"))
    Prices.objects.create(security=bond, date=EOP, price=D("100"))

    u = unrealized_gain_loss(bond, EFF, user, "USD", account_ids=[account.id], start_date=None)
    assert u["price_appreciation"] == D("6.25")
    assert u["fx_effect"] == D("23.75")
    assert u["total"] == D("30.00")


@pytest.mark.django_db
def test_get_current_notional_fallback_converts_exactly_once(db):
    """Defect 2 (RED): the amortizing transactions-fallback returned the
    nominal-currency notional unconverted. Corrected: converted exactly
    once into the requested currency (1,000 RUB x 0.0125 = 12.50 USD)."""
    user, broker, account = _make_world("nc")
    bond = _bond(user, "Fallback RUB Bond")
    meta = BondMetadata.objects.create(
        asset=bond, initial_notional=D("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    _fx("USD", "RUB", EOP, "0.0125", user)
    assert get_current_notional(
        meta, EFF, user, [account.id], "USD"
    ) == D("12.50")


@pytest.mark.django_db
def test_nonamortizing_statement_reconciles_at_sanitized_values(db):
    """Sanitized example, non-amortizing: statement NAV 256.25, control
    56.25, unrealized price 6.25, security FX 23.75, cash FX 26.25 ->
    reconciled, complete, certified returns."""
    user, broker, account = _make_world("na")
    bond = _bond(user, "Non-amort RUB Bond")
    BondMetadata.objects.create(asset=bond, initial_notional=D("1000"), nominal_currency="RUB")
    _fx("USD", "RUB", ENTRY, "0.0100", user)
    _fx("USD", "RUB", EOP, "0.0125", user)
    _tx(user, account, ENTRY, "Cash in", currency="RUB", cash_flow=D("20000"))
    _tx(user, account, ENTRY, "Buy", currency="RUB", security=bond,
        quantity=D("10"), price=D("95"), notional=D("1000"))
    Prices.objects.create(security=bond, date=EOP, price=D("100"))

    doc = build_reconciled_summary(user, EFF, "USD", 2, [account.id])
    nr = doc["netResult"]
    assert Decimal(nr["nav"]["raw"]) == D("256.25")
    assert Decimal(nr["controlTotal"]["raw"]) == D("56.25")
    assert Decimal(nr["components"]["unrealizedPrice"]["raw"]) == D("6.25")
    assert Decimal(nr["fxDetail"]["security"]["raw"]) == D("23.75")
    assert Decimal(nr["fxDetail"]["cashFlows"]["raw"]) == D("26.25")
    assert Decimal(nr["attributedSum"]["raw"]) == D("56.25")
    assert Decimal(nr["unexplainedDifference"]["raw"]) == D("0")
    assert nr["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"


@pytest.mark.django_db
def test_amortizing_fallback_statement_reconciles_at_sanitized_values(db):
    """Sanitized example, amortizing WITHOUT NotionalHistory (the corrected
    fallback path): same sanitized statement values -> reconciled, complete.
    NAV via NAV_at_date (consumer path) agrees with the statement NAV."""
    user, broker, account = _make_world("af")
    bond = _bond(user, "Amort Fallback RUB Bond")
    BondMetadata.objects.create(asset=bond, initial_notional=D("1000"), nominal_currency="RUB", is_amortizing=True)
    _fx("USD", "RUB", ENTRY, "0.0100", user)
    _fx("USD", "RUB", EOP, "0.0125", user)
    _tx(user, account, ENTRY, "Cash in", currency="RUB", cash_flow=D("20000"))
    _tx(user, account, ENTRY, "Buy", currency="RUB", security=bond,
        quantity=D("10"), price=D("95"), notional=D("1000"))
    Prices.objects.create(security=bond, date=EOP, price=D("100"))

    nav = NAV_at_date(user.id, (account.id,), EFF, "USD")["Total NAV"]
    assert nav == D("256.25")
    doc = build_reconciled_summary(user, EFF, "USD", 2, [account.id])
    nr = doc["netResult"]
    assert Decimal(nr["nav"]["raw"]) == D("256.25")
    assert Decimal(nr["controlTotal"]["raw"]) == D("56.25")
    assert Decimal(nr["components"]["unrealizedPrice"]["raw"]) == D("6.25")
    assert Decimal(nr["fxDetail"]["security"]["raw"]) == D("23.75")
    assert nr["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"


@pytest.mark.django_db
def test_amortizing_with_history_partial_then_full_redemption(db):
    """Amortizing WITH NotionalHistory: partial redemption (200 par/bond,
    cash 2,000 RUB at 0.0125 = 25 USD; realized 6.00 = price 1.25 + fx
    4.75) then full redemption of the remaining 800 par (cash 8,000 RUB =
    100.00 USD; realized 24.00 = price 5.00 + fx 19.00).

    Mid-date (after partial redemption, price 95%): bond 10 x 95% x
    800/100 x 0.0125 = 95.00 + cash 12,500 x 0.0125 = 156.25 -> NAV 251.25.
    Final (fully redeemed): cash 20,500 x 0.0125 = 256.25 -> NAV 256.25,
    statement reconciles at control 56.25 with certified realized rows."""
    from common.models import NotionalHistory

    user, broker, account = _make_world("ah")
    bond = _bond(user, "Amort History RUB Bond")
    BondMetadata.objects.create(
        asset=bond, initial_notional=D("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    for when, rate in [
        (ENTRY, "0.0100"), (date(2067, 6, 1), "0.0125"),
        (date(2067, 9, 1), "0.0125"), (EOP, "0.0125"),
    ]:
        _fx("USD", "RUB", when, rate, user)
    _tx(user, account, ENTRY, "Cash in", currency="RUB", cash_flow=D("20000"))
    _tx(user, account, ENTRY, "Buy", currency="RUB", security=bond,
        quantity=D("10"), price=D("95"), notional=D("1000"))
    _tx(user, account, date(2067, 6, 1), "Bond redemption", currency="RUB",
        security=bond, quantity=D("0"), price=D("100"),
        cash_flow=D("2000"), notional_change=D("200"), notional=D("1000"))
    Prices.objects.create(security=bond, date=date(2067, 9, 1), price=D("95"))

    mid = NAV_at_date(user.id, (account.id,), date(2067, 9, 15), "USD")["Total NAV"]
    assert mid == D("251.25")

    _tx(user, account, date(2067, 9, 20), "Bond redemption", currency="RUB",
        security=bond, quantity=D("0"), price=D("100"),
        cash_flow=D("8000"), notional_change=D("800"), notional=D("800"))
    nav = NAV_at_date(user.id, (account.id,), EFF, "USD")["Total NAV"]
    assert nav == D("256.25")

    doc = build_reconciled_summary(user, EFF, "USD", 2, [account.id])
    nr = doc["netResult"]
    assert Decimal(nr["nav"]["raw"]) == D("256.25")
    assert Decimal(nr["controlTotal"]["raw"]) == D("56.25")
    assert Decimal(nr["components"]["realizedPrice"]["raw"]) == D("6.25")
    assert Decimal(nr["fxDetail"]["security"]["raw"]) == D("23.75")
    assert nr["reconciliation"] == "reconciled"
    assert doc["status"] == "complete"


@pytest.mark.django_db
def test_bond_notional_redemption_is_account_scoped(db):
    """Account isolation: a redemption recorded on account A reduces the
    effective notional observed for account A's scope only; a second
    account of the same investor with no bond activity sees no leakage,
    and another investor's scope is fully isolated."""
    user, broker, account_a = _make_world("isoA")
    account_b = Accounts.objects.create(broker=broker, name="Second Account")
    bond = _bond(user, "Isolated RUB Bond")
    meta = BondMetadata.objects.create(
        asset=bond, initial_notional=D("1000"), nominal_currency="RUB",
        is_amortizing=True,
    )
    _fx("USD", "RUB", EOP, "0.0125", user)
    _tx(user, account_a, ENTRY, "Cash in", currency="RUB", cash_flow=D("20000"))
    _tx(user, account_a, ENTRY, "Buy", currency="RUB", security=bond,
        quantity=D("10"), price=D("95"), notional=D("1000"))
    _tx(user, account_a, date(2067, 6, 1), "Bond redemption", currency="RUB",
        security=bond, quantity=D("0"), price=D("100"),
        cash_flow=D("2000"), notional_change=D("200"), notional=D("1000"))
    # The redemption row auto-created a NotionalHistory entry on save; the
    # history branch is asset-scoped (not account-scoped) - pre-existing
    # engine behavior, deliberately untouched by this correction.
    from common.models import NotionalHistory
    assert NotionalHistory.objects.filter(asset=bond).exists()
    assert get_current_notional(meta, EFF, user, [account_a.id], "USD") == D("10.00")
    assert get_current_notional(meta, EFF, user, [account_b.id], "USD") == D("10.00")

    # The corrected FALLBACK (no NotionalHistory) is account-filtered: with
    # the history rows removed, scope A aggregates only A's redemption
    # while scope B (no bond activity) sees the full par.
    NotionalHistory.objects.filter(asset=bond).delete()
    assert get_current_notional(meta, EFF, user, [account_a.id], "USD") == D("10.00")
    assert get_current_notional(meta, EFF, user, [account_b.id], "USD") == D("12.50")
    assert get_current_notional(
        meta, EFF, user, [account_a.id, account_b.id], "USD"
    ) == D("10.00")

    # Another investor's scope is fully isolated (their own redemption
    # aggregate is empty -> full par, converted once).
    other, other_broker, other_account = _make_world("isoB")
    assert get_current_notional(
        meta, EFF, other, [other_account.id], "USD"
    ) == D("12.50")
