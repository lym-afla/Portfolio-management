"""Tests for nav.py _calculate_cash_flow on crypto trades (IRR path).

IRR treats crypto trades as asset cash flows: buys are negative, sells are
positive. The cash flow must include commission and round to the broker's
cash_precision, mirroring ``services.transactions.total_cash_flow`` so the two
paths stay consistent.

Under the embedded multi-currency commission model (revert of spec §5.3's
separate commission row, design doc 2026-08-06), cross-currency fees attach to
the trade row's ``commission``/``commission_currency``. ``_calculate_cash_flow``
therefore restores the cross-currency exclusion guard: a commission whose
currency differs from the trade's currency is NOT folded into the trade's
primary-currency cash flow (it depletes a different currency's balance, handled
by ``services.positions.position``). Same-currency commissions (or legacy rows
with no ``commission_currency``) are still applied.
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
    """Legacy rows with NULL commission_currency still apply commission (mirrors total_cash_flow)."""
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
def test_nav_crypto_cross_currency_fee_excluded_from_trade_cash_flow(crypto_setup):
    """Embedded model: a cross-currency fee is EXCLUDED from the trade's cash flow.

    A BTC fee on a BTC-USDT trade attaches to the trade row as
    ``commission=-0.00006684``, ``commission_currency="BTC"``. The trade's own
    currency is USDT, so the IRR cash flow must NOT fold the BTC commission
    into the USDT cash flow (it would mix BTC units into a USDT amount). The
    fee depletes the BTC position separately via ``position()``. The trade's
    IRR cash flow is therefore exactly ``-(price*quantity)``.
    """
    _, account = crypto_setup
    qty = Decimal("0.06677357")
    price = Decimal("74837.4")
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=qty, price=price,
        commission=Decimal("-0.00006684"), commission_currency="BTC",
    )
    cf = _calculate_cash_flow(tx)
    expected = (-(price * qty)).quantize(Decimal("0.00000001"))
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
