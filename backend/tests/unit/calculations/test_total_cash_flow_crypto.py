"""Tests for total_cash_flow on crypto trades under the reverted model.

Under the reverted model (spec §5.3), cross-currency fees are persisted as
SEPARATE ``TRANSACTION_TYPE_CRYPTO_COMMISSION`` rows (Task 6). The trade row's
``commission`` field is therefore ALWAYS same-currency by construction, so the
old ``commission_currency != trade_currency`` exclusion has been removed: a
trade row's commission is always applied. Separately, ``Crypto commission``
rows themselves return ``Decimal(0)`` from ``total_cash_flow`` — they move the
fee asset's position via ``quantity``, not cash (the cash effect lives on the
parent trade row's ``-qty*price``).
"""

from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, Transactions
from constants import (
    TRANSACTION_TYPE_CRYPTO_COMMISSION,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
)
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
def test_cross_currency_fee_lives_on_separate_commission_row(crypto_setup):
    """Reverted model (spec §5.3): a cross-currency fee is NOT on the trade row.

    The trade row carries no commission at all (the fee went to a separate
    ``TRANSACTION_TYPE_CRYPTO_COMMISSION`` row from Task 6), so its cash flow is
    just ``-(price*quantity)``. Production never writes a cross-currency
    commission onto the trade row anymore; the legacy guard that excluded it
    has been removed as dead code.
    """
    _, account = crypto_setup
    net_qty = Decimal("0.06677357")
    eff_price = Decimal("5002.16249933") / net_qty
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=net_qty, price=eff_price,
        # No commission here — the BTC fee is a separate Crypto commission row.
        commission=None, commission_currency=None,
    )
    cf = total_cash_flow(tx)
    expected = (-(eff_price * net_qty)).quantize(Decimal("0.00000001"))
    assert cf == expected


@pytest.mark.django_db
def test_crypto_commission_row_returns_zero(crypto_setup):
    """A ``TRANSACTION_TYPE_CRYPTO_COMMISSION`` row moves a position, not cash.

    The fee's cash effect is captured on the parent trade row's
    ``-qty*price`` (+ same-currency commission). The commission row itself
    returns ``Decimal(0)`` from ``total_cash_flow`` so it doesn't pollute the
    cash-balance dict (spec §5.3, Task 7).
    """
    _, account = crypto_setup
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_COMMISSION, currency="BTC",
        date=datetime(2026, 1, 1),
        # The row moves the BTC position via quantity; price/commission are NULL.
        quantity=Decimal("-0.001"), price=None, commission=None,
    )
    assert total_cash_flow(tx) == Decimal("0")


@pytest.mark.django_db
def test_legacy_trade_row_with_cross_currency_commission_now_includes_it(crypto_setup):
    """A hand-built legacy row carrying a cross-currency commission now INCLUDES it.

    Under the old model the ``comm_ccy != trade_ccy`` guard excluded this.
    Under the revert that guard is gone — production never creates such a row
    (cross-currency fees are separate commission rows), but for any legacy /
    hand-built row we now apply the commission unconditionally. This test
    documents that behavior so the removal of the guard is intentional.
    (spec §5.3.)
    """
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
    expected = (
        (-(eff_price * net_qty)) + Decimal("-0.00006684")
    ).quantize(Decimal("0.00000001"))
    assert cf == expected
