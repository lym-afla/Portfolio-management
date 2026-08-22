"""get_currencies must list only cash currencies (fiat + stablecoins).

Crypto coins appear as Transactions.currency on transfer legs (by design —
currency=coin prevents transfers leaking into USD cash columns). The
Transaction page builds its Cash flow / Balance column groups from
get_currencies, so non-cash coins must be filtered out there too, mirroring
BalanceTracker's CASH_CURRENCIES filter.
"""
from datetime import datetime

import pytest

from common.models import Accounts, Assets, Transactions
from services.accounts import get_currencies


@pytest.mark.django_db
def test_get_currencies_excludes_non_cash_coins(user, broker):
    account = Accounts.objects.create(broker=broker, name="OKX Funding", native_id="funding")
    btc = Assets.objects.create(name="BTC", ISIN="CRYPTO:BTC", type="Crypto")
    trump = Assets.objects.create(name="TRUMP", ISIN="CRYPTO:TRUMP", type="Crypto")

    Transactions.objects.create(  # USD cash row
        investor=user, account=account, type="Cash in", currency="USD",
        date=datetime(2026, 6, 22, 12, 0), cash_flow=100,
    )
    Transactions.objects.create(  # USDT stablecoin cash row
        investor=user, account=account, type="Cash in", currency="USDT",
        date=datetime(2026, 6, 22, 12, 1), cash_flow=100,
    )
    Transactions.objects.create(  # BTC transfer leg (currency=coin by design)
        investor=user, account=account, security=btc, type="Crypto transfer in",
        currency="BTC", date=datetime(2026, 6, 22, 12, 2), quantity=1,
    )
    Transactions.objects.create(  # TRUMP transfer leg
        investor=user, account=account, security=trump, type="Crypto transfer out",
        currency="TRUMP", date=datetime(2026, 6, 22, 12, 3), quantity=-1,
    )

    assert get_currencies(account) == {"USD", "USDT"}


@pytest.mark.django_db
def test_get_currencies_empty_account(user, broker):
    account = Accounts.objects.create(broker=broker, name="Empty", native_id=None)
    assert get_currencies(account) == set()
