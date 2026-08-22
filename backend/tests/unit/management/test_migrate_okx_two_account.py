"""Tests for the migrate_okx_two_account management command (#29)."""
from datetime import datetime

import pytest
from django.core.management import call_command

from common.models import Accounts, Brokers, Transactions


@pytest.fixture
def user(db):
    from common.models import CustomUser

    return CustomUser.objects.create_user(username="bf-user", password="x")


@pytest.fixture
def okx_broker_with_legacy_account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    legacy = Accounts.objects.create(broker=broker, name="Unified", native_id="okx-main")
    return broker, legacy


@pytest.mark.django_db
def test_renames_legacy_to_trading_and_creates_funding(user, okx_broker_with_legacy_account):
    broker, legacy = okx_broker_with_legacy_account
    # One historical transaction on the legacy account (must stay attached).
    Transactions.objects.create(
        investor=user, account=legacy, type="Crypto trade in",
        date=datetime(2026, 1, 1, 0, 0), quantity=1, price=100, currency="USD",
    )

    call_command("migrate_okx_two_account", "OKX")

    accounts = {a.native_id: a for a in Accounts.objects.filter(broker=broker)}
    assert set(accounts) == {"trading", "funding"}
    assert accounts["trading"].name == "OKX Trading"
    assert accounts["funding"].name == "OKX Funding"
    # The legacy row was renamed in place (same pk) -> the tx stays attached.
    assert accounts["trading"].pk == legacy.pk
    assert Transactions.objects.filter(account=accounts["trading"]).count() == 1
    assert Transactions.objects.filter(account=accounts["funding"]).count() == 0


@pytest.mark.django_db
def test_idempotent(okx_broker_with_legacy_account):
    broker, legacy = okx_broker_with_legacy_account
    call_command("migrate_okx_two_account", "OKX")
    call_command("migrate_okx_two_account", "OKX")  # second run is a no-op
    assert Accounts.objects.filter(broker=broker, native_id="trading").count() == 1
    assert Accounts.objects.filter(broker=broker, native_id="funding").count() == 1


@pytest.mark.django_db
def test_dry_run_makes_no_changes(okx_broker_with_legacy_account):
    broker, legacy = okx_broker_with_legacy_account
    call_command("migrate_okx_two_account", "OKX", "--dry-run")
    legacy.refresh_from_db()
    assert legacy.name == "Unified"  # unchanged
    assert Accounts.objects.filter(broker=broker).count() == 1


@pytest.mark.django_db
def test_missing_broker_reports_error(capsys):
    call_command("migrate_okx_two_account", "Nope")
    out = capsys.readouterr().out
    assert "not found" in out.lower()
