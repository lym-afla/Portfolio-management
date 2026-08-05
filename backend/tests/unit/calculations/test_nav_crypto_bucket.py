"""NAV regression: BTC counts once, in a Crypto bucket (spec §4.3).

Spec intent: ``NAV_at_date`` reports a three-class NAV model — Cash, Crypto,
Securities. Crypto assets (``Assets.type == "Crypto"``) live in their own
top-level ``result["Crypto"]`` bucket and MUST NOT bleed into the
securities-side breakdowns (``asset_type`` / ``asset_class`` / ``account``).
Securities (Stock / Bond / ...) keep the existing breakdown behaviour.
"""
from datetime import date
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Prices, Transactions
from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN
from services.nav import NAV_at_date


@pytest.fixture
def crypto_portfolio(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto", cash_precision=8)
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="okx-1")

    btc = Assets.objects.create(
        type="Crypto", ISIN="CRYPTO:BTC", name="BTC",
        currency="USD", exposure="Commodity", yahoo_symbol="BTC-USD",
    )
    btc.investors.add(user)
    Prices.objects.create(security=btc, date=date(2026, 1, 1), price=Decimal("60000"))

    stock = Assets.objects.create(
        type="Stock", ISIN="US0000000001", name="AAPL",
        currency="USD", exposure="Equity", yahoo_symbol="AAPL",
    )
    stock.investors.add(user)
    Prices.objects.create(security=stock, date=date(2026, 1, 1), price=Decimal("150"))

    # 0.5 BTC @ 60000 = 30000 in Crypto. Crypto trades settle in their own
    # bucket; explicit cash_flow=0 keeps the fiat balance untouched (the
    # crypto branch in services.transactions.total_cash_flow honours this).
    Transactions.objects.create(
        investor=user, account=account, security=btc, currency="USD",
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, date=date(2026, 1, 1),
        quantity=Decimal("0.5"), price=Decimal("60000"),
        cash_flow=Decimal("0"),
    )
    # 10 AAPL @ 150 = 1500 in Securities. The stock Buy infers a -1500 fiat
    # outflow via total_cash_flow (price * quantity), depleting cash.
    Transactions.objects.create(
        investor=user, account=account, security=stock, currency="USD",
        type="Buy", date=date(2026, 1, 1),
        quantity=Decimal("10"), price=Decimal("150"),
    )
    # 2500 USD cash in. Net cash after the AAPL buy = 2500 - 1500 = 1000.
    Transactions.objects.create(
        investor=user, account=account, security=None, currency="USD",
        type="Cash in", date=date(2026, 1, 1),
        quantity=None, price=None, cash_flow=Decimal("2500"),
    )
    return user, account


@pytest.mark.django_db
def test_nav_three_buckets_counted_once(crypto_portfolio):
    """BTC counts ONCE, in a separate Crypto bucket — never under asset_type."""
    user, account = crypto_portfolio
    result = NAV_at_date(
        user.id, (account.id,), date(2026, 1, 1), "USD",
        breakdown=("asset_type",),
    )
    # Total = 30000 (BTC) + 1500 (AAPL) + 1000 (cash) = 32500
    assert result["Total NAV"] == Decimal("32500")
    # BTC counted ONCE, in its own Crypto bucket — not under asset_type.
    assert result["Crypto"]["__total__"] == Decimal("30000")
    assert result["Crypto"]["BTC"] == Decimal("30000")
    # Securities-side asset_type holds only Stock (1500) and Cash (1000).
    assert result["asset_type"]["Stock"] == Decimal("1500")
    assert result["asset_type"]["Cash"] == Decimal("1000")
    # Crypto must NOT appear under asset_type after the split.
    assert "Crypto" not in result["asset_type"]


@pytest.mark.django_db
def test_nav_no_crypto_in_securities_breakdown(crypto_portfolio):
    """A portfolio with crypto must NOT also count it under security types.

    The securities-side asset_type keys are Stock/Bond/etc. Crypto has its
    own top-level bucket. After the split, scanning asset_type for any
    crypto-flavoured key must find nothing.
    """
    user, account = crypto_portfolio
    result = NAV_at_date(
        user.id, (account.id,), date(2026, 1, 1), "USD",
        breakdown=("asset_type",),
    )
    # No key under asset_type should mention Crypto or the coin symbol BTC.
    crypto_keys = [
        k for k in result["asset_type"] if "Crypto" in str(k) or "BTC" in str(k)
    ]
    assert crypto_keys == []
    # And the crypto value lives only in the top-level Crypto bucket.
    assert result["Crypto"]["BTC"] == Decimal("30000")
