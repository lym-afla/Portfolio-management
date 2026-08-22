"""CryptoExchangeEvent.event_type flows to Transactions.import_event_type."""
from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, CustomUser, Transactions
from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event, _single_leg


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(username="evt-type-user", password="x")


@pytest.fixture
def account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    return Accounts.objects.create(broker=broker, name="Funding", native_id="okx-fund")


def _event(category, event_type=None):
    return CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv_fund:1",
        group_id="g1",
        timestamp_ms=1750000000000,
        category=category,
        raw_type="funding",
        event_type=event_type,
        legs=_single_leg("BTC", Decimal("0.5"), "BTC"),
    )


@pytest.mark.django_db(transaction=True)
def test_event_type_overrides_category_when_set(user, account):
    persist_crypto_exchange_event(_event("transfer", event_type="okx_internal_transfer"), user, account)
    tx = Transactions.objects.get()
    assert tx.import_event_type == "okx_internal_transfer"


@pytest.mark.django_db(transaction=True)
def test_falls_back_to_category_when_event_type_unset(user, account):
    persist_crypto_exchange_event(_event("transfer"), user, account)
    tx = Transactions.objects.get()
    assert tx.import_event_type == "transfer"
