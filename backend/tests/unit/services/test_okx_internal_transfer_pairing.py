"""Matched internal funding<->trading transfers carry basis cross-account
in both portfolio-wide and per-account realized-walker modes (#29).

These are regression tests for machinery that already spans accounts:
``_transfer_is_matched`` and ``lookup_group_transfer_basis`` query
investor-wide (no account filter), so a funding OUT and a trading IN that
share a synthesized ``import_group_id`` pair regardless of which account
each leg lives on. The tests lock that invariant.
"""
from datetime import datetime
from decimal import Decimal

import pytest
from django.db.models import Sum

from common.models import Accounts, Assets, Brokers, CustomUser, Transactions
from services import realized as realized_mod
from services.realized import get_economic_basis, _transfer_is_matched


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(username="pair-user", password="x")


@pytest.fixture
def broker(user):
    return Brokers.objects.create(investor=user, name="OKX", country="Crypto")


@pytest.fixture
def funding(user, broker):
    return Accounts.objects.create(broker=broker, name="OKX Funding", native_id="funding")


@pytest.fixture
def trading(user, broker):
    return Accounts.objects.create(broker=broker, name="OKX Trading", native_id="trading")


@pytest.fixture
def btc(user):
    # Real Assets field names: ``type`` (not asset_type), ``ISIN`` (uppercase).
    # ASSET_TYPE_CRYPTO == "Crypto".
    return Assets.objects.create(name="BTC", ISIN="BTC", type="Crypto")


def _buy(user, account, btc, qty, price, when, group):
    Transactions.objects.create(
        investor=user, account=account, security=btc, currency="USD",
        type="Crypto trade in", date=when, quantity=Decimal(qty), price=Decimal(price),
        import_provider="okx_csv", import_account_id=account.native_id,
        import_event_id=f"buy-{account.id}-{group}", import_group_id=group,
        import_event_type="trade",
    )


def _xfer(user, account, btc, qty, when, group, direction):
    tx_type = "Crypto transfer in" if direction == "in" else "Crypto transfer out"
    Transactions.objects.create(
        investor=user, account=account, security=btc, currency="USD",
        type=tx_type, date=when, quantity=Decimal(qty), price=None,
        import_provider="okx_csv", import_account_id=account.native_id,
        import_event_id=f"xfer-{account.id}-{group}", import_group_id=group,
        import_event_type="okx_internal_transfer",
    )


def _basis_and_qty(btc, cutoff, user, account_ids):
    """get_economic_basis returns a single Decimal (basis); derive qty separately.

    When ``account_ids`` is provided, scope the quantity Sum to that set so the
    per-account qty reflects only the queried account(s).
    """
    basis = get_economic_basis(btc, cutoff, user, account_ids=account_ids, rounded=False)
    qs = btc.transactions.filter(
        investor=user, quantity__isnull=False, date__lte=cutoff
    )
    if account_ids is not None:
        qs = qs.filter(account_id__in=account_ids)
    qty = qs.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    return basis, qty


# A shared synthesized group id (the trading CSV's Transfer leg and the funding
# CSV's From/To unified trading account leg both compute this same string).
GROUP = "okx_xfer:btc:0.5:1750000000"


@pytest.mark.django_db
def test_legs_are_mutually_matched_across_accounts(user, funding, trading, btc):
    """The funding IN and trading OUT share import_group_id -> each reports the
    other as a matched partner via _transfer_is_matched (investor-scoped query)."""
    _xfer(user, funding, btc, "0.5", datetime(2026, 6, 22, 20, 0, 0), GROUP, "in")
    _xfer(user, trading, btc, "-0.5", datetime(2026, 6, 22, 20, 0, 1), GROUP, "out")

    funding_in = btc.transactions.get(account=funding, type="Crypto transfer in")
    trading_out = btc.transactions.get(account=trading, type="Crypto transfer out")
    assert _transfer_is_matched(funding_in, user) is True
    assert _transfer_is_matched(trading_out, user) is True


@pytest.mark.django_db
def test_basis_carries_portfolio_wide(user, funding, trading, btc, monkeypatch):
    """Portfolio-wide walker (account_ids=None): funding OUT + trading IN replay
    in one pass; in-memory carried_basis_by_group moves the funding cost to the
    trading leg. Total basis across both accounts is preserved (100, not 50)."""
    monkeypatch.setattr(realized_mod, "TRANSFER_DISPOSITION_ENABLED", True)
    _buy(user, funding, btc, "1", "100", datetime(2026, 6, 20, 20, 0, 0), "b1")
    _xfer(user, funding, btc, "-0.5", datetime(2026, 6, 22, 20, 0, 0), GROUP, "out")
    _xfer(user, trading, btc, "0.5", datetime(2026, 6, 22, 20, 0, 1), GROUP, "in")

    cutoff = datetime(2026, 6, 23, 0, 0, 0)
    basis, qty = _basis_and_qty(btc, cutoff, user, account_ids=None)
    # Funding holds 0.5 @ 50 + trading holds 0.5 @ 50 => 1.0 BTC @ 100 total.
    assert qty == Decimal("1")
    assert basis == Decimal("100")


@pytest.mark.django_db
def test_basis_carries_per_account_via_recursive_lookup(user, funding, trading, btc, monkeypatch):
    """Per-account walker (account_ids=[trading]) does NOT replay the funding OUT,
    so in-memory carry is empty; the recursive ``lookup_group_transfer_basis``
    fallback must span accounts to recover the funding-side basis (50)."""
    monkeypatch.setattr(realized_mod, "TRANSFER_DISPOSITION_ENABLED", True)
    _buy(user, funding, btc, "1", "100", datetime(2026, 6, 20, 20, 0, 0), "b1")
    _xfer(user, funding, btc, "-0.5", datetime(2026, 6, 22, 20, 0, 0), GROUP, "out")
    _xfer(user, trading, btc, "0.5", datetime(2026, 6, 22, 20, 0, 1), GROUP, "in")

    cutoff = datetime(2026, 6, 23, 0, 0, 0)
    basis, qty = _basis_and_qty(btc, cutoff, user, account_ids=[trading.id])
    # Trading alone: 0.5 BTC whose basis was carried from funding (0.5 * 100 = 50).
    assert qty == Decimal("0.5")
    assert basis == Decimal("50")
