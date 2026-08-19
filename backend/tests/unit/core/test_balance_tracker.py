"""Tests for core/balance_tracker.py — cash-currency column filtering.

Commodity crypto coins (BTC, TRUMP) are Crypto-class assets, not cash — they
should not appear as columns in the Transactions-page Cash flow/Balance table.
Only fiat + stablecoins (USDT/USDC) are tracked as cash columns.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Transactions
from core.balance_tracker import BalanceTracker


@pytest.mark.django_db
class TestBalanceTrackerCashColumns:
    def test_btc_transaction_does_not_create_btc_column(self, user):
        """A BTC-denominated transaction must NOT register BTC as a balance column.
        BTC is a commodity crypto coin, not cash."""
        broker = Brokers.objects.create(investor=user, name="OKX-BT", country="Crypto", cash_precision=8)
        account = Accounts.objects.create(broker=broker, name="Trading")
        btc = Assets.objects.create(
            type="Crypto", ISIN="CRYPTO:BTCBT", name="BTCBT",
            currency="USD", exposure="Commodity",
        )
        btc.investors.add(user)
        tx = Transactions.objects.create(
            investor=user, account=account, security=btc, currency="BTC",
            type="Crypto transfer out",
            date=datetime(2026, 6, 8, tzinfo=timezone.utc),
            quantity=Decimal("-0.02"),
        )
        bt = BalanceTracker(number_of_digits=8)
        bt.update(tx)
        currencies = bt.get_currencies()
        assert "BTC" not in currencies, f"BTC should not be a cash column; got {currencies}"

    def test_usdt_transaction_creates_usdt_column(self, user):
        """A USDT Cash in must register USDT as a balance column (stablecoin = cash)."""
        broker = Brokers.objects.create(investor=user, name="OKX-USDT", country="Crypto", cash_precision=8)
        account = Accounts.objects.create(broker=broker, name="Trading")
        tx = Transactions.objects.create(
            investor=user, account=account, security=None, currency="USDT",
            type="Cash in",
            date=datetime(2026, 6, 8, tzinfo=timezone.utc),
            cash_flow=Decimal("100"),
        )
        bt = BalanceTracker(number_of_digits=8)
        bt.update(tx)
        assert "USDT" in bt.get_currencies()

    def test_usd_transaction_creates_usd_column(self, user):
        """A USD Cash in must register USD as a balance column (fiat = cash)."""
        broker = Brokers.objects.create(investor=user, name="OKX-USD", country="Crypto", cash_precision=8)
        account = Accounts.objects.create(broker=broker, name="Trading")
        tx = Transactions.objects.create(
            investor=user, account=account, security=None, currency="USD",
            type="Cash in",
            date=datetime(2026, 6, 8, tzinfo=timezone.utc),
            cash_flow=Decimal("100"),
        )
        bt = BalanceTracker(number_of_digits=8)
        bt.update(tx)
        assert "USD" in bt.get_currencies()
