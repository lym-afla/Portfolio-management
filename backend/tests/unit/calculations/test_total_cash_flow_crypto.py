"""Tests for total_cash_flow on crypto trades under the embedded-fee model.

Under the embedded multi-currency commission model (revert of spec §5.3's
separate commission row, design doc 2026-08-06), cross-currency fees attach to
the trade row's ``commission``/``commission_currency`` fields regardless of
currency. ``total_cash_flow`` therefore restores the cross-currency exclusion
guard: a commission whose currency differs from the trade's currency is NOT
folded into the trade's primary-currency cash flow (it depletes a different
currency's balance, handled by ``services.positions.position``). Same-currency
commissions (or legacy rows with no ``commission_currency``) are still applied.
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
def test_cross_currency_fee_excluded_from_trade_cash_flow(crypto_setup):
    """Embedded model: a cross-currency fee LIVES on the trade row but is EXCLUDED.

    A BTC fee on a BTC-USDT trade attaches to the trade row as
    ``commission=-0.00006684``, ``commission_currency="BTC"``. The trade's own
    currency is USDT, so ``total_cash_flow`` must NOT fold the BTC commission
    into the USDT cash flow (it would mix BTC units into a USDT amount). The
    fee depletes the BTC position separately via ``position()``. The trade's
    cash flow is therefore exactly ``-(price*quantity)``.
    """
    _, account = crypto_setup
    qty = Decimal("0.06677357")
    price = Decimal("74837.4")
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=qty, price=price,
        # Cross-currency commission present on the trade row but excluded.
        commission=Decimal("-0.00006684"), commission_currency="BTC",
    )
    cf = total_cash_flow(tx)
    expected = (-(price * qty)).quantize(Decimal("0.00000001"))
    assert cf == expected, (
        f"total_cash_flow={cf!r}; expected {expected!r} (exactly -qty*price, "
        f"cross-currency BTC fee must NOT be folded into USDT cash flow)"
    )


@pytest.mark.django_db
def test_null_commission_currency_includes_commission(crypto_setup):
    """Legacy rows with NULL commission_currency still apply commission.

    A row with no ``commission_currency`` is treated as same-currency (the fee
    is in the trade's own currency), so the commission is applied.
    """
    _, account = crypto_setup
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=Decimal("2"), price=Decimal("50"),
        commission=Decimal("-1.25"), commission_currency=None,
    )
    cf = total_cash_flow(tx)
    # -(50*2) + (-1.25) = -101.25
    assert cf == Decimal("-101.25")


@pytest.mark.django_db
def test_empty_commission_currency_includes_commission(crypto_setup):
    """An empty-string commission_currency is treated as same-currency."""
    _, account = crypto_setup
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=Decimal("1"), price=Decimal("100"),
        commission=Decimal("-0.5"), commission_currency="",
    )
    cf = total_cash_flow(tx)
    # -(100*1) + (-0.5) = -100.5
    assert cf == Decimal("-100.5")
