"""Regression test for KeyError on the accounts page.

Reproduces the original crash: an account whose transactions all have
zero cash flow (e.g. crypto transfer/reward types) produced
``account_balance(...) == {}`` while ``get_currencies(account) == {'USD'}``,
so ``account_balance(...)[currency]`` raised ``KeyError('USD')`` in
``_get_accounts_data``.

The fix uses ``.get(currency, Decimal(0))`` so a missing currency-key
yields 0 (displayed as a dash) rather than crashing.
"""
from datetime import date
from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, CustomUser, Transactions
from constants import TRANSACTION_TYPE_CRYPTO_REWARD, TRANSACTION_TYPE_CRYPTO_TRANSFER_IN
from core.accounts_utils import _get_accounts_data


@pytest.fixture
def crypto_account(user):
    """An account with only zero-cash-flow crypto transactions."""
    broker = Brokers.objects.create(investor=user, name="Test Crypto Broker", country="Crypto")
    account = Accounts.objects.create(broker=broker, name="Crypto Main")
    # Crypto transfer/reward types have cash_flow == 0, so account_balance
    # returns {} (it skips zero-cash-flow crypto types), but get_currencies
    # returns {'USD'} (the transaction.currency of these rows).
    Transactions.objects.create(
        investor=user,
        account=account,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        date=date(2025, 1, 1),
        quantity=Decimal("1.0"),
        price=Decimal("1"),
    )
    Transactions.objects.create(
        investor=user,
        account=account,
        currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_REWARD,
        date=date(2025, 1, 2),
        quantity=Decimal("0.1"),
        price=Decimal("1"),
    )
    return account


@pytest.mark.django_db
def test_get_accounts_data_does_not_crash_on_zero_cashflow_account(user, crypto_account):
    """Reproduces the KeyError('USD') crash from the accounts page.

    Before the fix: account_balance() returned {} for this account (all
    transactions are zero-cash-flow crypto types), but get_currencies()
    returned {'USD'}, so balance[currency] raised KeyError.
    """
    data = _get_accounts_data(
        user,
        Accounts.objects.filter(id=crypto_account.id),
        date.today(),
        "USD",
    )

    assert len(data) == 1
    account_row = data[0]
    # The cash dict must contain the USD key (no KeyError), mapped to a
    # formatted zero-ish value. The exact display string depends on
    # currency_format, so just assert the key is present and is a string.
    assert "USD" in account_row["cash"]
    assert isinstance(account_row["cash"]["USD"], str)


@pytest.mark.django_db
def test_get_accounts_data_handles_account_with_no_transactions(user):
    """An account with no transactions at all: get_currencies() is empty,
    so the cash dict comprehension produces {}. Must not crash."""
    broker = Brokers.objects.create(investor=user, name="Empty Broker", country="X")
    account = Accounts.objects.create(broker=broker, name="Empty")

    data = _get_accounts_data(
        user,
        Accounts.objects.filter(id=account.id),
        date.today(),
        "USD",
    )

    assert len(data) == 1
    assert data[0]["cash"] == {}
