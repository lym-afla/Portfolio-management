"""Calc-layer proof for the embedded multi-currency commission model (#28/#30).

After a base-asset-fee spot buy is persisted with the GROSS quantity and the
fee attached to ``commission``/``commission_currency``, position() must return
the net (gross + signed commission) quantity. This proves the cross-currency
commission subtraction in position() picks up the fee outflow automatically.
"""

from datetime import date
from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, Transactions
from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event
from services.positions import position


@pytest.fixture
def crypto_account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    return Accounts.objects.create(broker=broker, name="Unified", native_id="okx-main")


@pytest.mark.django_db
def test_position_returns_netted_quantity_after_base_fee_buy(user, crypto_account):
    """A BTC-USDT buy with a BTC fee persists GROSS quantity + embedded commission;
    position() returns the net (gross + signed commission).

    Under the embedded multi-currency model the base leg carries the GROSS fill
    quantity (0.1) and the BTC fee attaches to the trade row's
    ``commission``/``commission_currency`` (commission=-0.0001). position()
    subtracts the cross-currency commission from the BTC holding, so net BTC =
    0.1 (qty) + (-0.0001) (commission) = 0.0999. The fee magnitude is chosen so
    the net (0.0999) survives position()'s 6dp rounding and is distinguishable
    from the gross (0.1) — a sub-bps fee like 0.00000012 BTC would round back to
    the gross and could not prove the invariant.
    """
    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:pos-1",
        group_id="order-pos",
        timestamp_ms=1738454400000,  # 2025-02-02 00:00:00 UTC
        category="trade",
        raw_type="spot_fill",
        legs=[
            {
                "asset": "BTC",
                "quantity": Decimal("0.1"),  # GROSS fill quantity (NOT netted)
                "price": Decimal("96058"),
                "price_asset": "USD",
                "role": "base",
                "cash_flow": Decimal("-9605.8"),  # pure trade value, no fee conversion
                "quote_currency": "USDT",
                "fee_asset": "BTC",
            }
        ],
        fee={"asset": "BTC", "quantity": Decimal("-0.0001"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)

    tx = Transactions.objects.get(investor=user, account=crypto_account)
    btc_asset = tx.security
    # The fee is embedded on the trade row's commission/commission_currency.
    assert tx.quantity == Decimal("0.100000000")  # gross
    assert tx.commission == Decimal("-0.000100000")
    assert tx.commission_currency == "BTC"
    # position() filters transactions by date__date__lte, so query at/after the
    # tx's own date (derived from timestamp_ms = 2025-02-02 00:00 UTC). Asserting
    # the persisted date and querying at tx.date keeps the proof robust to
    # timestamp tweaks and isolates it to the calc-layer invariant under test.
    assert tx.date.date() == date(2025, 2, 2)
    held = position(btc_asset, tx.date, user)
    # Net = 0.1 (gross qty) + (-0.0001) (commission) = 0.0999, rounded to 6dp.
    assert held == Decimal("0.099900")
    assert held != Decimal("0.100000")  # would be true if the fee were NOT subtracted
