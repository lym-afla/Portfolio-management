from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, Transactions
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
)
from core.crypto_exchange_import import CryptoExchangeEvent, persist_crypto_exchange_event


def _crypto_event(**overrides):
    data = {
        "provider": "bybit",
        "provider_event_id": "exec-1",
        "group_id": "order-1",
        "timestamp_ms": 1767225600000,
        "category": "trade",
        "raw_type": "spot_execution",
        "legs": [
            {
                "asset": "BTC",
                "quantity": Decimal("0.1"),
                "price": Decimal("60000"),
                "price_asset": "USDT",
                "role": "base",
            },
            {
                "asset": "USDT",
                "quantity": Decimal("-6003"),
                "price": Decimal("1"),
                "price_asset": "USDT",
                "role": "quote",
            },
        ],
        "fee": {"asset": "USDT", "quantity": Decimal("-3"), "is_rebate": False},
    }
    data.update(overrides)
    return CryptoExchangeEvent(**data)


@pytest.fixture
def crypto_account(user):
    broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    return Accounts.objects.create(broker=broker, name="Unified", native_id="bybit-main")


@pytest.mark.django_db
def test_persist_crypto_trade_event_creates_linked_asset_legs(user, crypto_account):
    created = persist_crypto_exchange_event(_crypto_event(), user, crypto_account)

    assert len(created) == 2
    assert persist_crypto_exchange_event(_crypto_event(), user, crypto_account) == []
    assert Transactions.objects.filter(import_group_id="order-1").count() == 2

    btc = Assets.objects.get(ISIN="CRYPTO:BTC", currency="USD")
    usdt = Assets.objects.get(ISIN="CRYPTO:USDT", currency="USD")
    assert btc.type == ASSET_TYPE_CRYPTO
    assert btc.ticker == "BTC"
    assert btc.exposure == "Commodity"
    assert user in btc.investors.all()
    assert usdt.type == ASSET_TYPE_CRYPTO
    assert usdt.exposure == "FX"
    assert user in usdt.investors.all()

    btc_tx = Transactions.objects.get(security=btc)
    usdt_tx = Transactions.objects.get(security=usdt)
    assert btc_tx.type == TRANSACTION_TYPE_CRYPTO_TRADE_IN
    assert btc_tx.quantity == Decimal("0.100000000")
    assert btc_tx.price == Decimal("60000.000000000")
    assert btc_tx.currency == "USD"
    assert btc_tx.import_provider == "bybit"
    assert btc_tx.import_account_id == "bybit-main"
    assert btc_tx.import_event_id == "exec-1:0"
    assert btc_tx.import_group_id == "order-1"
    assert btc_tx.import_event_type == "trade"
    assert usdt_tx.type == TRANSACTION_TYPE_CRYPTO_TRADE_OUT
    assert usdt_tx.quantity == Decimal("-6003.000000000")
    assert usdt_tx.price == Decimal("1.000000000")
    assert usdt_tx.import_event_id == "exec-1:1"


@pytest.mark.django_db
def test_non_usd_quote_pair_does_not_store_btc_denominated_price_as_usd(
    user, crypto_account
):
    event = _crypto_event(
        provider_event_id="exec-ethbtc",
        group_id="order-ethbtc",
        legs=[
            {
                "asset": "ETH",
                "quantity": Decimal("1.5"),
                "price": Decimal("0.05"),
                "price_asset": "BTC",
                "role": "base",
            },
            {
                "asset": "BTC",
                "quantity": Decimal("-0.075"),
                "price": Decimal("1"),
                "price_asset": "BTC",
                "role": "quote",
            },
        ],
        fee=None,
    )

    persist_crypto_exchange_event(event, user, crypto_account)

    eth_tx = Transactions.objects.get(security__ticker="ETH")
    assert eth_tx.price is None
    assert "price_asset=BTC" in eth_tx.comment
    assert "role=base" in eth_tx.comment


@pytest.mark.django_db
def test_resolved_crypto_asset_identifier_fits_model_field_for_long_symbols(
    user, crypto_account
):
    event = _crypto_event(
        provider_event_id="exec-long",
        group_id="order-long",
        legs=[
            {
                "asset": "SUPERLONGCOIN",
                "quantity": Decimal("1"),
                "price": Decimal("2"),
                "price_asset": "USDT",
                "role": "base",
            }
        ],
        fee=None,
    )

    persist_crypto_exchange_event(event, user, crypto_account)

    asset = Assets.objects.get(name="SUPERLONGCOIN", currency="USD")
    assert len(asset.ISIN) <= Assets._meta.get_field("ISIN").max_length
    assert asset.ticker == "SUPERLONGC"


@pytest.mark.django_db
def test_fee_info_appears_in_comments_without_extra_rows(user, crypto_account):
    persist_crypto_exchange_event(_crypto_event(), user, crypto_account)

    assert Transactions.objects.filter(import_group_id="order-1").count() == 2
    comments = list(
        Transactions.objects.filter(import_group_id="order-1").values_list("comment", flat=True)
    )
    assert all("fee_asset=USDT" in comment for comment in comments)
    assert all("fee_quantity=-3" in comment for comment in comments)
    assert all("fee_is_rebate=False" in comment for comment in comments)
