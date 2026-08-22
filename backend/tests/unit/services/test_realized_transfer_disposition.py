"""The earn-token discriminator keeps earn crypto legs neutral even when
TRANSFER_DISPOSITION_ENABLED is True and the leg is unmatched."""
from datetime import date, datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, CustomUser, Transactions
from django.db.models import Sum
from services import realized as realized_mod
from services.realized import get_economic_basis, realized_gain_loss


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(username="disc-user", password="x")


@pytest.fixture
def btc(user):
    # NOTE: real Assets field names are ``type`` (not ``asset_type``) and
    # ``ISIN`` (uppercase). ASSET_TYPE_CRYPTO == "Crypto" (capital C).
    return Assets.objects.create(name="BTC", ISIN="BTC", type="Crypto")


@pytest.fixture
def account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    return Accounts.objects.create(broker=broker, name="OKX Funding", native_id="funding")


def _tx(user, account, btc, qty, event_type, tx_type="Crypto transfer out",
        date=None):
    return Transactions.objects.create(
        investor=user, account=account, security=btc, currency="USD",
        type=tx_type, date=date or datetime(2026, 6, 22, 20, 0, 0),
        quantity=Decimal(qty),
        price=Decimal("100"), import_provider="okx_csv", import_account_id="funding",
        import_event_id=f"e-{event_type}-{qty}", import_group_id=f"g-{event_type}-{qty}",
        import_event_type=event_type,
    )


@pytest.mark.django_db(transaction=True)
def test_earn_subscription_stays_neutral_when_flag_on(user, account, btc, monkeypatch):
    # Open a long BTC position, then an earn subscription OUT (no partner leg).
    Transactions.objects.create(investor=user, account=account, security=btc, currency="USD",
        type="Crypto trade in", date=datetime(2026, 6, 20, 20, 0, 0),
        quantity=Decimal("1"), price=Decimal("100"))
    _tx(user, account, btc, "-0.5", "okx_earn_subscription")
    monkeypatch.setattr(realized_mod, "TRANSFER_DISPOSITION_ENABLED", True)

    result = realized_gain_loss(btc, date(2026, 7, 1), user)
    # Earn subscription is unconditionally neutral -> no realized G/L.
    assert result["all_time"]["total"] == Decimal("0")


@pytest.mark.django_db
def test_external_deposit_unmatched_realizes_zero_basis_when_flag_on(user, account, btc, monkeypatch):
    # An external crypto IN (unmatched, disposition-eligible) opens a zero-basis lot.
    _tx(user, account, btc, "0.5", "okx_external_deposit", tx_type="Crypto transfer in")
    # Then sell half.
    Transactions.objects.create(investor=user, account=account, security=btc, currency="USD",
        type="Crypto trade out", date=datetime(2026, 6, 23, 20, 0, 0),
        quantity=Decimal("-0.25"), price=Decimal("200"), cash_flow=Decimal("50"))
    monkeypatch.setattr(realized_mod, "TRANSFER_DISPOSITION_ENABLED", True)

    result = realized_gain_loss(btc, date(2026, 7, 1), user)
    # Zero-basis lot (0.25 @ 0) sold for 50 -> realized = 50.
    assert result["all_time"]["total"] == Decimal("50")


@pytest.mark.django_db
def test_earn_roundtrip_preserves_basis_when_flag_on(user, account, btc, monkeypatch):
    """subscribe 0.5 BTC out, redeem 0.5 BTC back -> basis unchanged (100).

    The subscribe and redeem legs carry DIFFERENT import_group_id values, so
    they do NOT pair via carried_basis_by_group. Without the earn-neutrality
    guard in get_economic_basis, the OUT debits 50 basis into a group bucket
    that the IN never reclaims -> basis collapses to 50. With the guard, both
    legs are neutral and the original 100 basis is preserved.
    """
    # Open 1 BTC @ 100.
    Transactions.objects.create(investor=user, account=account, security=btc, currency="USD",
        type="Crypto trade in", date=datetime(2026, 6, 20, 20, 0, 0),
        quantity=Decimal("1"), price=Decimal("100"))
    # Earn subscribe 0.5 OUT (group_id g-okx_earn_subscription--0.5).
    _tx(user, account, btc, "-0.5", "okx_earn_subscription",
        date=datetime(2026, 6, 22, 20, 0, 0))
    # Earn redeem 0.5 IN (group_id g-okx_earn_redemption-0.5 -> different).
    _tx(user, account, btc, "0.5", "okx_earn_redemption", tx_type="Crypto transfer in",
        date=datetime(2026, 6, 23, 20, 0, 0))
    monkeypatch.setattr(realized_mod, "TRANSFER_DISPOSITION_ENABLED", True)

    cutoff = datetime(2026, 6, 24, 0, 0, 0)
    # get_economic_basis returns a single Decimal (the public signature does
    # not expose return_state); derive quantity separately via a Sum.
    basis = get_economic_basis(btc, cutoff, user, rounded=False)
    qty = btc.transactions.filter(
        investor=user, quantity__isnull=False, date__lte=cutoff,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0")

    assert qty == Decimal("1")
    # Round trip must preserve original basis (100), not collapse to 50.
    assert basis == Decimal("100")
