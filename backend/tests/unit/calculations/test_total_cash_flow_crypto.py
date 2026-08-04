"""Tests for total_cash_flow on crypto trades under the unified model.

Crypto trades no longer store cash_flow; total_cash_flow computes
-(price*quantity) + commission (when commission is in the trade currency),
rounded to the broker's cash_precision.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, Transactions
from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN
from services.transactions import total_cash_flow


@pytest.fixture
def crypto_setup(user):
    broker = Brokers.objects.create(investor=user, name="OKX Test", country="Crypto", cash_precision=8)
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="okx-test")
    return broker, account


@pytest.mark.django_db
def test_quote_fee_buy_cash_flow_equals_settlement(crypto_setup):
    """Quote-fee buy: total_cash_flow = -(p*q) + commission == -settlement."""
    _, account = crypto_setup
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=Decimal("1"), price=Decimal("100"),
        commission=Decimal("-0.5"), commission_currency="USDT",
    )
    cf = total_cash_flow(tx)
    # -(100*1) + (-0.5) = -100.5
    assert cf == Decimal("-100.5")


@pytest.mark.django_db
def test_base_fee_buy_cash_flow_no_commission_term(crypto_setup):
    """Base-fee buy: commission in BTC (different currency) — not subtracted."""
    _, account = crypto_setup
    net_qty = Decimal("0.06677357")
    eff_price = Decimal("5002.16249933") / net_qty
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=net_qty, price=eff_price,
        commission=Decimal("-0.00006684"), commission_currency="BTC",
    )
    cf = total_cash_flow(tx)
    # -(p*q) with no commission term (different currency).
    expected = (-(eff_price * net_qty)).quantize(Decimal("0.00000001"))
    assert cf == expected
