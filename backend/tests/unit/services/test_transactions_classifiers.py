"""Tests for transaction classifiers in services/transactions.py."""
from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, Transactions
from constants import (
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
    TRANSACTION_TYPE_SELL,
)
from services.transactions import (
    is_disposal_transaction,
    is_neutral_transfer_transaction,
    is_paid_entry_transaction,
    total_cash_flow,
)


@pytest.fixture
def crypto_account(user):
    """Crypto broker/account so cash_flow precision (8dp) is preserved.

    The default conftest ``broker`` uses ``cash_precision=2`` (traditional),
    which would round the BTC settlement payout in
    :func:`services.transactions.total_cash_flow`. Option settlements are
    crypto-account events and need full precision.
    """
    broker = Brokers.objects.create(
        investor=user, name="OKX Test", country="Crypto", cash_precision=8
    )
    return Accounts.objects.create(broker=broker, name="Unified", native_id="okx-test")


@pytest.mark.django_db
class TestOptionSettlementClassifier:
    def test_option_settlement_is_disposal(self, user, account):
        tx = Transactions(investor=user, account=account, type=TRANSACTION_TYPE_OPTION_SETTLEMENT)
        assert is_disposal_transaction(tx) is True

    def test_crypto_trade_out_still_disposal(self, user, account):
        tx = Transactions(investor=user, account=account, type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT)
        assert is_disposal_transaction(tx) is True

    def test_crypto_trade_in_not_disposal(self, user, account):
        tx = Transactions(investor=user, account=account, type=TRANSACTION_TYPE_CRYPTO_TRADE_IN)
        assert is_disposal_transaction(tx) is False

    def test_transfer_not_disposal(self, user, account):
        tx = Transactions(investor=user, account=account, type=TRANSACTION_TYPE_CRYPTO_TRANSFER_IN)
        assert is_disposal_transaction(tx) is False


@pytest.mark.django_db
class TestTotalCashFlowOptionSettlement:
    def test_option_settlement_honors_cash_flow(self, user, crypto_account):
        """total_cash_flow must return the stored cash_flow for Option settlement."""
        tx = Transactions.objects.create(
            investor=user, account=crypto_account, security=None, currency="BTC",
            type=TRANSACTION_TYPE_OPTION_SETTLEMENT,
            date=datetime(2026, 6, 5, 11, 0),
            quantity=Decimal("7"), price=Decimal("0"),
            cash_flow=Decimal("-0.00411765"),  # ITM writer payout
        )
        assert total_cash_flow(tx) == Decimal("-0.00411765")

    def test_option_settlement_zero_cash_flow(self, user, crypto_account):
        tx = Transactions.objects.create(
            investor=user, account=crypto_account, security=None, currency="BTC",
            type=TRANSACTION_TYPE_OPTION_SETTLEMENT,
            date=datetime(2026, 6, 5, 11, 0),
            quantity=Decimal("7"), price=Decimal("0"),
            cash_flow=Decimal("0"),
        )
        assert total_cash_flow(tx) == Decimal("0")
