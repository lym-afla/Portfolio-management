from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from common.models import Accounts, Assets, Brokers, OptionMetadata, Prices, Transactions
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_INTEREST_INCOME,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
)
from services.crypto_exchange import (
    CryptoExchangeEvent,
    persist_crypto_exchange_event,
)
from services.accounts import balance as account_balance
from services.transactions import total_cash_flow


def _crypto_event(**overrides):
    # Mirrors what _spot_legs now emits for a BTC/USDT spot trade: a SINGLE
    # base leg (USDT is cash, not a separate asset) carrying the actual fill
    # quantity/price and a cash_flow of the total USDT spent/received.
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
                "price_asset": "USD",
                "role": "base",
                "cash_flow": Decimal("-6003"),
            }
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

    # Stablecoin-quote spot trades now persist as ONE transaction (the base
    # asset) with cash_flow set, instead of a separate USDT quote leg.
    assert len(created) == 1
    assert persist_crypto_exchange_event(_crypto_event(), user, crypto_account) == []
    assert Transactions.objects.filter(import_group_id="order-1").count() == 1

    btc = Assets.objects.get(ISIN="CRYPTO:BTC", currency="USD")
    assert btc.type == ASSET_TYPE_CRYPTO
    assert btc.ticker == "BTC"
    assert btc.exposure == "Commodity"
    assert user in btc.investors.all()
    # No CRYPTO:USDT asset row is created for a stablecoin-quote spot trade.
    assert not Assets.objects.filter(ISIN="CRYPTO:USDT", currency="USD").exists()

    btc_tx = Transactions.objects.get(security=btc)
    assert btc_tx.type == TRANSACTION_TYPE_CRYPTO_TRADE_IN
    assert btc_tx.quantity == Decimal("0.100000000")
    assert btc_tx.price == Decimal("60000.000000000")
    assert btc_tx.currency == "USD"
    assert btc_tx.cash_flow == Decimal("-6003.00")
    assert btc_tx.import_provider == "bybit"
    assert btc_tx.import_account_id == "bybit-main"
    assert btc_tx.import_event_id == "exec-1:0"
    assert btc_tx.import_group_id == "order-1"
    assert btc_tx.import_event_type == "trade"


@pytest.mark.django_db
def test_crypto_crypto_pair_uses_quote_asset_fiat_price(user, crypto_account):
    btc = Assets.objects.create(
        type=ASSET_TYPE_CRYPTO,
        ISIN="CRYPTO:BTC",
        name="Bitcoin",
        ticker="BTC",
        currency="USD",
        exposure="Commodity",
    )
    btc.investors.add(user)
    Prices.objects.create(security=btc, date=date(2026, 1, 1), price=Decimal("60000"))

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

    created = persist_crypto_exchange_event(event, user, crypto_account)

    eth_tx = Transactions.objects.get(security__ticker="ETH")
    btc_tx = Transactions.objects.get(security=btc)
    assert len(created) == 2
    assert eth_tx.type == TRANSACTION_TYPE_CRYPTO_TRADE_IN
    assert eth_tx.quantity == Decimal("1.500000000")
    assert eth_tx.price == Decimal("3000.000000000")
    assert btc_tx.type == TRANSACTION_TYPE_CRYPTO_TRADE_OUT
    assert btc_tx.quantity == Decimal("-0.075000000")
    assert btc_tx.price == Decimal("60000.000000000")


@pytest.mark.django_db
def test_crypto_crypto_pair_requires_quote_asset_fiat_price(user, crypto_account):
    event = _crypto_event(
        provider_event_id="exec-missing-price",
        group_id="order-missing-price",
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

    with patch(
        "services.crypto_exchange.fetch_crypto_usd_price_from_yahoo",
        return_value=None,
        create=True,
    ):
        with pytest.raises(ValueError, match="Could not import fiat price for quote asset BTC"):
            persist_crypto_exchange_event(event, user, crypto_account)

    assert Transactions.objects.filter(import_group_id="order-missing-price").count() == 0


@pytest.mark.django_db
def test_crypto_crypto_pair_imports_missing_btc_usd_price_from_yahoo(user, crypto_account):
    event = _crypto_event(
        provider_event_id="exec-auto-btc-price",
        group_id="order-auto-btc-price",
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

    with patch(
        "services.crypto_exchange.fetch_crypto_usd_price_from_yahoo",
        return_value=Decimal("61000.123456789"),
        create=True,
    ) as fetch_price:
        created = persist_crypto_exchange_event(event, user, crypto_account)

    btc = Assets.objects.get(ISIN="CRYPTO:BTC", currency="USD")
    eth_tx = Transactions.objects.get(security__ticker="ETH")
    btc_tx = Transactions.objects.get(security=btc)
    btc_price = Prices.objects.get(security=btc, date=date(2026, 1, 1))

    assert len(created) == 2
    fetch_price.assert_called_once_with("BTC", date(2026, 1, 1))
    assert btc_price.price == Decimal("61000.123457")
    assert eth_tx.price == Decimal("3050.006172850")
    assert btc_tx.price == Decimal("61000.123457000")


@pytest.mark.django_db
def test_auto_imported_btc_price_rolls_back_when_event_validation_fails(user, crypto_account):
    event = _crypto_event(
        provider_event_id="exec-auto-btc-price-bad-leg",
        group_id="order-auto-btc-price-bad-leg",
        legs=[
            {
                "asset": "ETH",
                "quantity": Decimal("1.5"),
                "price": Decimal("0.05"),
                "price_asset": "BTC",
                "role": "base",
            },
            {
                "asset": "SOL",
                "quantity": Decimal("2"),
                "price": None,
                "price_asset": "USDT",
                "role": "base",
            },
        ],
        fee=None,
    )

    with patch(
        "services.crypto_exchange.fetch_crypto_usd_price_from_yahoo",
        return_value=Decimal("61000.123456789"),
        create=True,
    ):
        with pytest.raises(ValueError, match="without fiat-denominated price"):
            persist_crypto_exchange_event(event, user, crypto_account)

    assert not Assets.objects.filter(ISIN="CRYPTO:BTC", currency="USD").exists()
    assert not Prices.objects.filter(date=date(2026, 1, 1)).exists()
    assert Transactions.objects.filter(import_group_id="order-auto-btc-price-bad-leg").count() == 0


@pytest.mark.django_db
def test_stablecoin_deposit_import_creates_cash_in_without_crypto_asset(user, crypto_account):
    # Phase 4: a standalone USDT deposit is re-routed to a Cash in transaction
    # in the USDT currency, rather than a Crypto transfer against a CRYPTO:USDT
    # asset with no cost basis or cash balance.
    event = _crypto_event(
        provider_event_id="deposit-usdt-in",
        group_id="deposit-usdt-in",
        category="deposit",
        raw_type="deposit",
        legs=[
            {
                "asset": "USDT",
                "quantity": Decimal("500"),
                "price": Decimal("1"),
                "price_asset": "USDT",
                "role": "base",
                "instrument": "coin",
            }
        ],
        fee=None,
    )

    created = persist_crypto_exchange_event(event, user, crypto_account)

    assert len(created) == 1
    tx = created[0]
    assert tx.type == TRANSACTION_TYPE_CASH_IN
    assert tx.currency == "USDT"
    assert tx.security is None
    assert tx.price is None
    assert tx.quantity is None
    assert tx.cash_flow == Decimal("500.00")
    # The stablecoin is the user's cash, so it now contributes to the USDT
    # balance rather than disappearing into a zero-cash crypto transfer.
    assert total_cash_flow(tx) == Decimal("500.00")
    assert account_balance(crypto_account, date(2026, 1, 1)) == {"USDT": Decimal("500.00")}
    # No CRYPTO:USDT asset row is created for standalone stablecoin events.
    assert not Assets.objects.filter(ISIN="CRYPTO:USDT", currency="USD").exists()
    # Idempotency: re-importing the same event does not duplicate the row.
    assert persist_crypto_exchange_event(event, user, crypto_account) == []


@pytest.mark.django_db
def test_stablecoin_withdrawal_import_creates_cash_out(user, crypto_account):
    event = _crypto_event(
        provider_event_id="withdrawal-usdt-out",
        group_id="withdrawal-usdt-out",
        category="withdrawal",
        raw_type="withdrawal",
        legs=[
            {
                "asset": "USDT",
                "quantity": Decimal("-250"),
                "price": Decimal("1"),
                "price_asset": "USDT",
                "role": "base",
                "instrument": "coin",
            }
        ],
        fee=None,
    )

    created = persist_crypto_exchange_event(event, user, crypto_account)

    assert len(created) == 1
    tx = created[0]
    assert tx.type == TRANSACTION_TYPE_CASH_OUT
    assert tx.currency == "USDT"
    assert tx.security is None
    assert tx.price is None
    assert tx.quantity is None
    # Withdrawals are outbound: cash_flow is the negative quantity.
    assert tx.cash_flow == Decimal("-250.00")
    assert total_cash_flow(tx) == Decimal("-250.00")
    assert account_balance(crypto_account, date(2026, 1, 1)) == {"USDT": Decimal("-250.00")}
    assert not Assets.objects.filter(ISIN="CRYPTO:USDT", currency="USD").exists()


@pytest.mark.django_db
def test_stablecoin_reward_import_creates_interest_income(user, crypto_account):
    event = _crypto_event(
        provider_event_id="reward-usdt-earn",
        group_id="reward-usdt-earn",
        category="reward",
        raw_type="earn",
        legs=[
            {
                "asset": "USDT",
                "quantity": Decimal("1.25"),
                "price": Decimal("1"),
                "price_asset": "USDT",
                "role": "base",
                "instrument": "coin",
            }
        ],
        fee=None,
    )

    created = persist_crypto_exchange_event(event, user, crypto_account)

    assert len(created) == 1
    tx = created[0]
    assert tx.type == TRANSACTION_TYPE_INTEREST_INCOME
    assert tx.currency == "USDT"
    assert tx.security is None
    assert tx.price is None
    assert tx.quantity is None
    # Rewards are inbound accruals: positive cash_flow.
    assert tx.cash_flow == Decimal("1.25")
    assert total_cash_flow(tx) == Decimal("1.25")
    assert account_balance(crypto_account, date(2026, 1, 1)) == {"USDT": Decimal("1.25")}
    assert not Assets.objects.filter(ISIN="CRYPTO:USDT", currency="USD").exists()


@pytest.mark.django_db
def test_non_stablecoin_deposit_still_uses_crypto_resolver(user, crypto_account):
    # Regression guard: a non-stablecoin (BTC) deposit must keep the existing
    # behavior (Crypto transfer in against the CRYPTO:BTC asset, USD-priced).
    event = _crypto_event(
        provider_event_id="deposit-btc-in",
        group_id="deposit-btc-in",
        category="deposit",
        raw_type="deposit",
        legs=[
            {
                "asset": "BTC",
                "quantity": Decimal("0.05"),
                "price": Decimal("1"),
                "price_asset": "BTC",
                "role": "base",
                "instrument": "coin",
            }
        ],
        fee=None,
    )

    created = persist_crypto_exchange_event(event, user, crypto_account)

    assert len(created) == 1
    tx = created[0]
    assert tx.type == TRANSACTION_TYPE_CRYPTO_TRANSFER_IN
    assert tx.currency == "USD"
    btc = Assets.objects.get(ISIN="CRYPTO:BTC", currency="USD")
    assert tx.security == btc
    assert tx.quantity == Decimal("0.050000000")
    # Deposits have no external cash impact; cash_flow stays zero.
    assert total_cash_flow(tx) == Decimal("0")


@pytest.mark.django_db
def test_spot_trade_stablecoin_quote_carries_cash_flow_on_base_leg(user, crypto_account):
    # Regression guard: a BTC/USDT spot trade no longer emits a separate USDT
    # quote leg. Instead the single BTC base leg carries the total USDT
    # spent/received in its cash_flow, and no CRYPTO:USDT asset or standalone
    # cash transaction is created.
    created = persist_crypto_exchange_event(_crypto_event(), user, crypto_account)

    assert len(created) == 1
    assert not Assets.objects.filter(ISIN="CRYPTO:USDT", currency="USD").exists()
    btc_tx = created[0]
    assert btc_tx.type == TRANSACTION_TYPE_CRYPTO_TRADE_IN
    assert btc_tx.security.ticker == "BTC"
    # The USDT movement rides on the base leg as cash_flow, not a second row.
    assert btc_tx.cash_flow == Decimal("-6003.00")


@pytest.mark.django_db
def test_stablecoin_internal_transfer_still_uses_crypto_transfer(user, crypto_account):
    # Internal stablecoin ``transfer`` events are NOT external cash movements,
    # so they keep the existing crypto-transfer treatment (not re-routed to
    # Cash in/out).
    event = _crypto_event(
        provider_event_id="transfer-usdt-internal",
        group_id="transfer-usdt-internal",
        category="transfer",
        raw_type="transfer",
        legs=[
            {
                "asset": "USDT",
                "quantity": Decimal("250.123456789"),
                "price": Decimal("1"),
                "price_asset": "USDT",
                "role": "transfer",
                "instrument": "coin",
            }
        ],
        fee=None,
    )

    created = persist_crypto_exchange_event(event, user, crypto_account)

    assert len(created) == 1
    tx = created[0]
    assert tx.type == TRANSACTION_TYPE_CRYPTO_TRANSFER_IN
    usdt = Assets.objects.get(ISIN="CRYPTO:USDT", currency="USD")
    assert tx.security == usdt
    assert tx.quantity == Decimal("250.123456789")
    assert total_cash_flow(tx) == Decimal("0")
    assert account_balance(crypto_account, date(2026, 1, 1)) == {}


@pytest.mark.django_db
def test_resolved_crypto_asset_identifier_fits_model_field_for_long_symbols(user, crypto_account):
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

    # One transaction (single base leg); fee metadata still lands in its comment.
    assert Transactions.objects.filter(import_group_id="order-1").count() == 1
    comments = list(
        Transactions.objects.filter(import_group_id="order-1").values_list("comment", flat=True)
    )
    assert all("fee_asset=USDT" in comment for comment in comments)
    assert all("fee_quantity=-3" in comment for comment in comments)
    assert all("fee_is_rebate=False" in comment for comment in comments)


@pytest.mark.django_db
def test_fee_role_leg_is_not_persisted_as_position_change(user, crypto_account):
    event = _crypto_event(
        provider_event_id="exec-third-fee",
        group_id="order-third-fee",
        legs=[
            {
                "asset": "ETH",
                "quantity": Decimal("2"),
                "price": Decimal("3000"),
                "price_asset": "USD",
                "role": "base",
                "cash_flow": Decimal("-6000"),
            },
            {
                "asset": "BNB",
                "quantity": Decimal("-1"),
                "price": Decimal("0"),
                "price_asset": "BNB",
                "role": "fee",
            },
        ],
        fee={"asset": "BNB", "quantity": Decimal("-1"), "is_rebate": False},
    )

    persist_crypto_exchange_event(event, user, crypto_account)

    # The fee-role BNB leg is skipped; only the single ETH base leg persists.
    assert Transactions.objects.filter(import_group_id="order-third-fee").count() == 1
    assert not Assets.objects.filter(name="BNB").exists()
    comments = list(
        Transactions.objects.filter(import_group_id="order-third-fee").values_list(
            "comment", flat=True
        )
    )
    assert all("fee_asset=BNB" in comment for comment in comments)


@pytest.mark.django_db
def test_crypto_persistence_normalizes_model_decimal_fields(user, crypto_account):
    event = _crypto_event(
        provider_event_id="exec-precision",
        group_id="order-precision",
        legs=[
            {
                "asset": "BTC",
                "quantity": Decimal("0.1234567894"),
                "price": Decimal("60000.1234567894"),
                "price_asset": "USDT",
                "role": "base",
            }
        ],
        fee=None,
    )

    created = persist_crypto_exchange_event(event, user, crypto_account)

    assert created[0].quantity == Decimal("0.123456789")
    assert created[0].price == Decimal("60000.123456789")


def _deposit_event(**overrides):
    data = {
        "provider": "bybit",
        "provider_event_id": "dep-1",
        "group_id": "dep-1",
        "timestamp_ms": 1700000000000,
        "category": "deposit",
        "raw_type": "deposit",
        "legs": [
            {
                "asset": "USDT",
                "quantity": Decimal("500"),
                "price": Decimal("1"),
                "price_asset": "USDT",
                "role": "base",
                "instrument": "coin",
            }
        ],
        "fee": None,
    }
    data.update(overrides)
    return CryptoExchangeEvent(**data)


@pytest.mark.django_db
def test_persist_stablecoin_deposit_creates_cash_in_row(user, crypto_account):
    # Phase 4: a standalone USDT deposit now becomes a Cash in row (not a
    # Crypto transfer in), in the USDT currency, with cash_flow set.
    created = persist_crypto_exchange_event(_deposit_event(), user, crypto_account)

    assert len(created) == 1
    tx = created[0]
    assert tx.type == TRANSACTION_TYPE_CASH_IN
    assert tx.currency == "USDT"
    assert tx.security is None
    assert tx.cash_flow == Decimal("500.00")
    assert persist_crypto_exchange_event(_deposit_event(), user, crypto_account) == []


def _option_premium_event(**overrides):
    data = {
        "provider": "bybit",
        "provider_event_id": "opt-ex-1",
        "group_id": "opt-order-1",
        "timestamp_ms": 1700000008000,
        "category": "trade",
        "raw_type": "option_execution",
        "legs": [
            {
                "asset": "BTC-27JUN26-100000-C",
                "quantity": Decimal("2"),
                "price": Decimal("500"),
                "price_asset": "USDT",
                "role": "base",
                "instrument": "option",
            }
        ],
        "fee": {"asset": "USDT", "quantity": Decimal("-1"), "is_rebate": False},
    }
    data.update(overrides)
    return CryptoExchangeEvent(**data)


@pytest.mark.django_db
def test_persist_option_premium_creates_option_asset_with_metadata(user, crypto_account):
    created = persist_crypto_exchange_event(_option_premium_event(), user, crypto_account)

    assert len(created) == 1
    tx = created[0]
    assert tx.type == TRANSACTION_TYPE_CRYPTO_TRADE_IN
    assert tx.security.type == "Option"
    meta = OptionMetadata.objects.get(asset=tx.security)
    assert meta.strike_price == Decimal("100000")
    assert meta.option_type == "CALL"
    assert meta.expiration_date.isoformat() == "2026-06-27"


def _option_settlement_event(**overrides):
    data = {
        "provider": "bybit",
        "provider_event_id": "settle-1",
        "group_id": "opt-order-1",
        "timestamp_ms": 1700000010000,
        "category": "settlement",
        "raw_type": "option_delivery",
        "legs": [
            {
                "asset": "BTC",
                "quantity": Decimal("0.5"),
                "price": Decimal("65000"),
                "price_asset": "BTC",
                "role": "base",
                "instrument": "coin",
            }
        ],
        "fee": None,
    }
    data.update(overrides)
    return CryptoExchangeEvent(**data)


@pytest.mark.django_db
def test_persist_option_settlement_uses_option_settlement_type(user, crypto_account):
    created = persist_crypto_exchange_event(_option_settlement_event(), user, crypto_account)

    assert len(created) == 1
    assert created[0].type == TRANSACTION_TYPE_OPTION_SETTLEMENT


@pytest.mark.django_db
def test_persist_coin_leg_still_uses_crypto_resolver(user, crypto_account):
    # Regression: existing spot-trade path must still resolve as Crypto asset.
    created = persist_crypto_exchange_event(_crypto_event(), user, crypto_account)

    assert all(c.security.type == ASSET_TYPE_CRYPTO for c in created)


@pytest.mark.django_db
def test_persist_deposit_via_normalizer_closes_seam(user, crypto_account):
    # Regression: a real normalizer output must round-trip through persistence
    # without crashing. Closes the seam between normalization and persistence so
    # a None-price default in _single_leg can never silently break deposits.
    # Phase 4: a USDT deposit normalizes to a stablecoin leg that persistence
    # re-routes to a Cash in row (currency=USDT, cash_flow set).
    from services.crypto_exchange import normalize_bybit_deposit

    event = normalize_bybit_deposit(
        {
            "coin": "USDT",
            "amount": "500",
            "txID": "dep-seam-1",
            "successAt": "1700000000000",
            "status": "SUCCESS",
        }
    )
    created = persist_crypto_exchange_event(event, user, crypto_account)

    assert len(created) == 1
    assert created[0].type == TRANSACTION_TYPE_CASH_IN
    assert created[0].currency == "USDT"
    assert created[0].security is None
    assert created[0].cash_flow == Decimal("500.00")
