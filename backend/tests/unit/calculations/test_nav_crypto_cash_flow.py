"""Tests for nav.py _calculate_cash_flow on crypto trades (IRR path).

IRR treats crypto trades as asset cash flows: buys are negative, sells are
positive. The cash flow must include commission (when denominated in the
trade's quote currency) and round to the broker's cash_precision, mirroring
``services.transactions.total_cash_flow`` so the two paths stay consistent.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, Transactions
from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN
from services.nav import _calculate_cash_flow


@pytest.fixture
def crypto_setup(user):
    broker = Brokers.objects.create(
        investor=user, name="OKX Test", country="Crypto", cash_precision=8
    )
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="okx-test")
    return broker, account


@pytest.mark.django_db
def test_nav_crypto_quote_fee_includes_commission(crypto_setup):
    """IRR cash flow for a quote-fee crypto buy includes commission."""
    _, account = crypto_setup
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=Decimal("1"), price=Decimal("100"),
        commission=Decimal("-0.5"), commission_currency="USDT",
    )
    cf = _calculate_cash_flow(tx)
    # -(100*1) + (-0.5) = -100.5
    assert cf == Decimal("-100.5")


@pytest.mark.django_db
def test_nav_crypto_legacy_null_commission_currency_includes_commission(crypto_setup):
    """Legacy rows with NULL commission_currency still apply commission (mirrors Task 4)."""
    _, account = crypto_setup
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=Decimal("2"), price=Decimal("50"),
        commission=Decimal("-1.25"), commission_currency=None,
    )
    cf = _calculate_cash_flow(tx)
    # -(50*2) + (-1.25) = -101.25
    assert cf == Decimal("-101.25")


@pytest.mark.django_db
def test_nav_crypto_base_fee_excludes_commission(crypto_setup):
    """Base-asset fee (different currency) is display-only, excluded from cash flow."""
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
    cf = _calculate_cash_flow(tx)
    expected = (-(eff_price * net_qty)).quantize(Decimal("0.00000001"))
    assert cf == expected


@pytest.mark.django_db
def test_nav_crypto_rounds_to_broker_cash_precision(crypto_setup):
    """IRR cash flow is rounded to the broker's cash_precision (here 8)."""
    _, account = crypto_setup
    # 1/3 price residual at storage precision must round to 8 decimals.
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=Decimal("1"), price=Decimal("100.000000001"),
        commission=Decimal("0"), commission_currency="USDT",
    )
    cf = _calculate_cash_flow(tx)
    # -100.000000001 rounded to 8 decimals == -100.00000000
    assert cf == Decimal("-100.00000000")
    assert cf.as_tuple().exponent == -8
