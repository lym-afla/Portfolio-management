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
    _single_leg,
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
def test_crypto_asset_transfer_without_price_persists_unpriced(user, crypto_account):
    """Regression for OKX CSV Bug 1: a non-stablecoin asset transfer (e.g.
    TRUMP) where no fiat price is available must NOT crash the import. It
    persists as an unpriced Crypto transfer in/out (price=None) so the quantity
    movement is still recorded. Only transfers/deposits/withdrawals are exempt;
    trades (test above) still require a price."""
    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv_transfer:trump-1",
        group_id="trump-transfer",
        timestamp_ms=1737337200000,  # 2025-01-20
        category="transfer",
        raw_type="transfer",
        legs=_single_leg("TRUMP", Decimal("0.67986040"), "TRUMP"),
        fee=None,
    )

    with patch(
        "services.crypto_exchange.fetch_crypto_usd_price_from_yahoo",
        return_value=None,
        create=True,
    ):
        created = persist_crypto_exchange_event(event, user, crypto_account)

    # Persisted as a single unpriced Crypto transfer in leg.
    assert len(created) == 1
    tx = created[0]
    assert tx.type == "Crypto transfer in"
    assert tx.quantity == Decimal("0.67986040")
    assert tx.price is None  # unpriced — no crash


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


@pytest.mark.django_db
def test_stablecoin_quote_spot_trade_records_currency_as_stablecoin(user, crypto_account):
    """A BTC-USDT buy must persist currency='USDT' (the actual quote/cash
    currency), not 'USD'. Regression for OKX CSV issue #3."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:trade-1",
        group_id="order-1",
        timestamp_ms=1767225600000,
        category="trade",
        raw_type="spot_fill",
        legs=[
            {
                "asset": "BTC",
                "quantity": Decimal("0.001"),
                "price": Decimal("96058"),
                "price_asset": "USD",
                "role": "base",
                "cash_flow": Decimal("-96.058"),
                "quote_currency": "USDT",
            }
        ],
        fee={"asset": "BTC", "quantity": Decimal("0"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)

    tx = Transactions.objects.get(investor=user, account=crypto_account)
    assert tx.currency == "USDT"


@pytest.mark.django_db
def test_stablecoin_quote_spot_buy_uses_crypto_trade_type(user, crypto_account):
    """Stablecoin-quote spot trades persist as 'Crypto trade in/out' (NOT
    Buy/Sell). The calc layer (total_cash_flow, realized.py) dispatches on type:
    Crypto trade in/out uses the persisted cash_flow field (USDT incl. fee),
    whereas Buy/Sell recomputes -quantity*price + commission and would mix BTC
    fee units into a USDT cash flow. The display goal is solved on the frontend
    instead. Regression for OKX issue #4 / final-review C1."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:trade-buy",
        group_id="order-buy",
        timestamp_ms=1767225600000,
        category="trade",
        raw_type="spot_fill",
        legs=[{
            "asset": "TRUMP", "quantity": Decimal("0.6803"),
            "price": Decimal("73.209"), "price_asset": "USD", "role": "base",
            "cash_flow": Decimal("-49.81"), "quote_currency": "USDT",
        }],
        fee={"asset": "TRUMP", "quantity": Decimal("-0.0006803"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    tx = Transactions.objects.get(investor=user, account=crypto_account)
    assert tx.type == TRANSACTION_TYPE_CRYPTO_TRADE_IN


@pytest.mark.django_db
def test_crypto_crypto_trade_keeps_crypto_trade_type(user, crypto_account):
    """Crypto-crypto pairs (two legs, no quote_currency) stay 'Crypto trade
    in/out'. Confirms the crypto-crypto path is unaffected by the stablecoin
    type handling (now reverted to Crypto trade in/out for all spot trades)."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    event = CryptoExchangeEvent(
        provider="bybit",
        provider_event_id="exec-cc",
        group_id="order-cc",
        timestamp_ms=1767225600000,
        category="trade",
        raw_type="spot_execution",
        legs=[
            {"asset": "ETH", "quantity": Decimal("0.1"), "price": Decimal("0.0016"),
             "price_asset": "BTC", "role": "base"},
            {"asset": "BTC", "quantity": Decimal("-0.00016"), "price": Decimal("1"),
             "price_asset": "BTC", "role": "quote"},
        ],
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    types = {t.type for t in Transactions.objects.filter(investor=user, account=crypto_account)}
    assert types == {"Crypto trade in", "Crypto trade out"}


@pytest.mark.django_db
def test_stablecoin_quote_spot_trade_records_commission(user, crypto_account):
    """The CSV Fee must land in the commission field, not be silently dropped.
    Regression for OKX issue #6."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:trade-fee",
        group_id="order-fee",
        timestamp_ms=1767225600000,
        category="trade",
        raw_type="spot_fill",
        legs=[{
            "asset": "TRUMP", "quantity": Decimal("0.6803"),
            "price": Decimal("73.209"), "price_asset": "USD", "role": "base",
            "cash_flow": Decimal("-49.81"), "quote_currency": "USDT",
        }],
        fee={"asset": "TRUMP", "quantity": Decimal("-0.0006803"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    tx = Transactions.objects.get(investor=user, account=crypto_account)
    assert tx.commission == Decimal("-0.0006803")


@pytest.mark.django_db
def test_option_sell_and_otm_expiry_persist_correctly(user, crypto_account):
    """OKX issue #8: selling a BTC call + OTM expiry. The sell is an option leg
    (-7 contracts @ 0.0022 BTC premium); the expiry releases collateral
    (+0.00716211 BTC settlement). Premium must resolve to fiat via BTC/USD."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    # Seed a BTC USD price on/before the sell date so premium fiat-resolves.
    # NOTE: Assets.investors is M2M (not FK); match the existing fixture pattern
    # in test_crypto_crypto_pair_uses_quote_asset_fiat_price rather than the
    # brief's `investor=user` literal (which would fail on the model).
    btc = Assets.objects.create(
        type=ASSET_TYPE_CRYPTO,
        ISIN="CRYPTO:BTC",
        name="Bitcoin",
        ticker="BTC",
        currency="USD",
        exposure="Commodity",
    )
    btc.investors.add(user)
    Prices.objects.create(security=btc, date=date(2026, 5, 27), price=Decimal("105000"))

    # Option SELL: -7 contracts @ 0.0022 BTC, fee in BTC.
    sell_event = CryptoExchangeEvent(
        provider="okx_csv", provider_event_id="csv:opt-sell",
        group_id="opt-order", timestamp_ms=1779916514000,  # 2026-05-27 21:15:14 UTC
        category="trade", raw_type="option_fill",
        legs=[{
            "asset": "BTC-USD-260605-80000-C", "quantity": Decimal("-7"),
            "price": Decimal("0.0022"), "price_asset": "BTC", "role": "base",
            "instrument": "option",
        }],
        fee={"asset": "BTC", "quantity": Decimal("-0.00001078"), "is_rebate": False},
    )
    persist_crypto_exchange_event(sell_event, user, crypto_account)

    sell_tx = Transactions.objects.get(
        investor=user, account=crypto_account, type=TRANSACTION_TYPE_CRYPTO_TRADE_OUT
    )
    assert sell_tx.quantity == Decimal("-7")
    # price_asset="BTC" so _leg_fiat_price multiplies 0.0022 * BTC_USD_price
    # (~105000) to fiat-resolve the BTC-denominated premium. The raw 0.0022
    # does NOT survive; assert only sign per the brief's verified fact #3.
    assert sell_tx.price is not None and sell_tx.price > 0

    # OTM EXPIRY: collateral released (+0.00716211 BTC).
    settle_event = CryptoExchangeEvent(
        provider="okx_csv", provider_event_id="csv:opt-settle",
        group_id="opt-order", timestamp_ms=1780646434000,  # 2026-06-05 08:00:34 UTC
        category="settlement", raw_type="option_delivery",
        legs=[{
            "asset": "BTC", "quantity": Decimal("0.00716211"),
            "price": Decimal("62703.94333408"), "price_asset": "USD", "role": "base",
        }],
    )
    persist_crypto_exchange_event(settle_event, user, crypto_account)

    settle_tx = Transactions.objects.get(
        investor=user, account=crypto_account, type=TRANSACTION_TYPE_OPTION_SETTLEMENT
    )
    # Positive: collateral came back.
    assert settle_tx.quantity == Decimal("0.00716211")


@pytest.mark.django_db
def test_base_fee_trade_persists_commission_currency(user, crypto_account):
    """The fee asset is persisted to commission_currency (issue #30) so the
    frontend can show '|| Fee: BTC0.000000012'."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:ccy-1",
        group_id="order-ccy",
        timestamp_ms=1738454400000,
        category="trade",
        raw_type="spot_fill",
        legs=[
            {
                "asset": "BTC",
                "quantity": Decimal("0.00099988"),
                "price": Decimal("96058"),
                "price_asset": "USD",
                "role": "base",
                "cash_flow": Decimal("-96.058"),
                "quote_currency": "USDT",
                "fee_asset": "BTC",
            }
        ],
        fee={"asset": "BTC", "quantity": Decimal("-0.00000012"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    tx = Transactions.objects.get(investor=user, account=crypto_account)
    assert tx.commission_currency == "BTC"


def test_spot_legs_quote_fee_effective_price_excludes_commission():
    """Quote-fee buy: price = (settlement + commission) / qty. The commission
    (negative) is subtracted from the settlement before deriving price, so
    p*q excludes the fee (commission enters calc separately). cash_flow is
    NOT on the leg (it will be computed by total_cash_flow from p*q later)."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        "buy", "ETH", "USDT", Decimal("1"), Decimal("100"),
        Decimal("-0.5"), "USDT", quote_cash_amount=Decimal("100.5"),
    )
    leg = legs[0]
    assert leg["quantity"] == Decimal("1")
    # price = (settlement + commission) / qty = (100.5 + (-0.5)) / 1 = 100.0
    assert leg["price"] == Decimal("100")
    assert "cash_flow" not in leg


def test_spot_legs_base_fee_effective_price_includes_fee_in_qty():
    """Base-fee buy: price = settlement / net_qty (commission different currency,
    not subtracted from settlement). Settlement = gross trade value, fee is
    already netted into quantity."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        "buy", "BTC", "USDT", Decimal("0.06684041"), Decimal("74837.4"),
        Decimal("-0.00006684"), "BTC", quote_cash_amount=Decimal("5002.16249933"),
    )
    leg = legs[0]
    # Net quantity: 0.06684041 + (-0.00006684) = 0.06677357
    assert leg["quantity"] == Decimal("0.06677357")
    assert "cash_flow" not in leg
    # price = settlement / net_qty (settlement NOT reduced by fee — different ccy).
    assert leg["price"] == Decimal("5002.16249933") / Decimal("0.06677357")


def test_spot_legs_no_fee_price_is_fill():
    """No-fee buy: price = settlement / qty = fill price."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        "buy", "BTC", "USDT", Decimal("0.001"), Decimal("96058"),
        Decimal("0"), "", quote_cash_amount=Decimal("96.058"),
    )
    leg = legs[0]
    assert leg["price"] == Decimal("96058")
    assert "cash_flow" not in leg


def test_spot_legs_sell_quote_fee():
    """Quote-fee sell: price excludes commission; qty is gross (negative)."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        "sell", "BTC", "USDT", Decimal("0.2"), Decimal("70000"),
        Decimal("-0.5"), "USDT", quote_cash_amount=Decimal("13999.5"),
    )
    leg = legs[0]
    assert leg["quantity"] == Decimal("-0.2")
    # price = (settlement + commission) / |qty| = (13999.5 + (-0.5)) / 0.2 = 69995
    assert leg["price"] == Decimal("69995")
    assert "cash_flow" not in leg


def test_spot_legs_nets_base_fee_into_quantity():
    """_spot_legs stablecoin branch: a base-asset fee is netted into the base
    quantity; the effective price reproduces the gross settlement. cash_flow is
    NOT on the leg (computed later from p*q)."""
    from services.crypto_exchange import _spot_legs

    # BTC-USDT buy: qty=0.001, price=96058, fee=-0.00000012 BTC (base).
    legs = _spot_legs(
        side="buy",
        base="BTC",
        quote="USDT",
        qty=Decimal("0.001"),
        price=Decimal("96058"),
        fee_delta=Decimal("-0.00000012"),
        fee_asset="BTC",
    )
    assert len(legs) == 1
    leg = legs[0]
    # Net quantity: 0.001 + (-0.00000012) = 0.00099988
    assert leg["quantity"] == Decimal("0.00099988")
    # No cash_flow on the leg (computed by total_cash_flow from p*q later).
    assert "cash_flow" not in leg
    # Base-fee: effective price = settlement / net_qty. settlement = qty*price
    # = 96.058 (no fee subtraction — fee is a different currency). So the fee is
    # baked into the per-unit price via the reduced quantity.
    assert leg["price"] == Decimal("96.058") / Decimal("0.00099988")
    # Invariant: |price * net_qty| reproduces the gross settlement (96.058).
    assert abs(leg["price"] * leg["quantity"]) == Decimal("96.058")
    assert leg["quote_currency"] == "USDT"
    assert leg["fee_asset"] == "BTC"


def test_spot_legs_quote_fee_folded_into_effective_price():
    """_spot_legs stablecoin branch: a quote-asset fee (e.g. USDT fee) is
    excluded from the effective price (settlement + commission)/qty so that
    |price*qty| reproduces the net-of-fee trade value; commission enters calc
    separately. cash_flow is NOT on the leg."""
    from services.crypto_exchange import _spot_legs

    # TRUMP-USDT sell: qty=0.6798, price=16.557, fee=-0.01125545 USDT (quote).
    legs = _spot_legs(
        side="sell",
        base="TRUMP",
        quote="USDT",
        qty=Decimal("0.6798"),
        price=Decimal("16.557"),
        fee_delta=Decimal("-0.01125545"),
        fee_asset="USDT",
    )
    assert len(legs) == 1
    leg = legs[0]
    # Quantity is gross (the fee is in quote, not base).
    assert leg["quantity"] == Decimal("-0.6798")
    assert "cash_flow" not in leg
    # Effective price excludes the commission (same currency, subtracted first):
    # settlement = qty*price = 11.2566486; priced_settlement = 11.2566486 - 0.01125545.
    priced_settlement = Decimal("0.6798") * Decimal("16.557") + Decimal("-0.01125545")
    assert leg["price"] == priced_settlement / Decimal("0.6798")
    # Invariant: |price * qty| reproduces the net-of-fee settlement.
    assert abs(leg["price"] * leg["quantity"]) == priced_settlement
    assert leg["fee_asset"] == "USDT"


def test_spot_legs_zero_fee_no_fee_asset_key():
    """_spot_legs stablecoin branch: zero fee -> effective price equals the
    fill price; cash_flow is NOT on the leg."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="buy",
        base="BTC",
        quote="USDT",
        qty=Decimal("0.001"),
        price=Decimal("96058"),
        fee_delta=Decimal("0"),
        fee_asset="",
    )
    leg = legs[0]
    assert leg["quantity"] == Decimal("0.001")
    assert "cash_flow" not in leg
    # No fee: price = settlement / qty = fill price.
    assert leg["price"] == Decimal("96058")
    assert leg["fee_asset"] == ""


def test_spot_legs_buy_base_fee_adjusts_price_for_fee_inclusive_basis():
    """A buy with a base-asset fee uses an effective price so that
    |quantity * price| == gross settlement (the fee is baked in via the netted
    quantity). cash_flow is NOT on the leg. Makes get_economic_basis correct
    without calc-layer changes (#30)."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="buy", base="BTC", quote="USDT",
        qty=Decimal("0.001"), price=Decimal("96058"),
        fee_delta=Decimal("-0.00000012"), fee_asset="BTC",
    )
    leg = legs[0]
    # quantity is net (PR #31); no cash_flow on the leg.
    assert leg["quantity"] == Decimal("0.00099988")
    assert "cash_flow" not in leg
    # Effective price = settlement / net_qty. settlement = qty*price = 96.058
    # (base fee is a different currency, NOT subtracted).
    # NOTE: Python Decimal division produces the full-precision non-terminating
    # expansion 96069.52834340120814497739729. A 6dp rounding BREAKS the
    # invariant below (qty*6dp_price != 96.058), so the exact quotient is the
    # only value consistent with both the implementation and the invariant.
    expected_effective_price = Decimal("96.058") / Decimal("0.00099988")
    assert leg["price"] == expected_effective_price
    # The invariant: |quantity * price| reproduces the gross settlement (96.058).
    assert abs(leg["quantity"] * leg["price"]) == Decimal("96.058")


def test_spot_legs_buy_quote_fee_excludes_commission_from_price():
    """A buy with a QUOTE-ASSET fee uses an effective price that EXCLUDES the
    commission: price = (settlement + fee_delta) / qty. The commission is a
    same-currency cost, subtracted from the settlement before deriving the
    price, so |price*qty| reproduces the net-of-fee trade value and the
    commission enters calc separately (commission field). Issue #32."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="buy", base="ETH", quote="USDT",
        qty=Decimal("1"), price=Decimal("100"),
        fee_delta=Decimal("-0.5"), fee_asset="USDT",
    )
    leg = legs[0]
    # quantity stays gross (quote-fee doesn't net into qty); no cash_flow on leg.
    assert leg["quantity"] == Decimal("1")
    assert "cash_flow" not in leg
    # Effective price EXCLUDES the commission: settlement=100 (qty*price),
    # priced_settlement = 100 + (-0.5) = 99.5; price = 99.5 / 1.
    assert leg["price"] == Decimal("99.5")
    # |price * qty| reproduces the net-of-fee settlement (99.5), NOT the gross
    # 100 — the 0.5 commission is excluded from the per-unit basis.
    assert abs(leg["quantity"] * leg["price"]) == Decimal("99.5")


def test_spot_legs_buy_no_fee_keeps_raw_fill_price():
    """A buy with no fee keeps the raw fill price (no adjustment needed)."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="buy", base="BTC", quote="USDT",
        qty=Decimal("0.001"), price=Decimal("96058"),
        fee_delta=Decimal("0"), fee_asset="",
    )
    leg = legs[0]
    assert leg["price"] == Decimal("96058")  # unchanged
    assert leg["quantity"] * leg["price"] == Decimal("96.058")


def test_spot_legs_quote_cash_amount_overrides_qty_price():
    """When quote_cash_amount is provided (the CSV's actual quote-leg Balance
    Change), it replaces qty*price as the settlement for the effective price.
    This prevents floating-point-like noise from the multiplication (e.g.
    0.06684041 * 74837.4 = 5002.162499334 vs the real 5002.16249933). Issue #32."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="buy", base="BTC", quote="USDT",
        qty=Decimal("0.06684041"), price=Decimal("74837.4"),
        fee_delta=Decimal("-0.00006684"), fee_asset="BTC",
        quote_cash_amount=Decimal("5002.16249933"),
    )
    leg = legs[0]
    assert "cash_flow" not in leg
    # Net quantity: 0.06684041 + (-0.00006684) = 0.06677357 (base fee netted).
    assert leg["quantity"] == Decimal("0.06677357")
    # Effective price = exact settlement / net_qty (NOT qty*price, which would
    # produce a spurious 9th digit).
    assert leg["price"] == Decimal("5002.16249933") / Decimal("0.06677357")
    # Invariant: |price * net_qty| reproduces the exact settlement.
    assert abs(leg["price"] * leg["quantity"]) == Decimal("5002.16249933")


def test_spot_legs_sell_base_fee_uses_effective_price():
    """A base-asset-fee sell uses an effective price so |price*qty| reproduces
    the gross settlement (the fee is baked in via the netted quantity, not the
    per-unit price). cash_flow is NOT on the leg."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="sell", base="BTC", quote="USDT",
        qty=Decimal("0.2"), price=Decimal("70000"),
        fee_delta=Decimal("-0.0001"), fee_asset="BTC",
    )
    leg = legs[0]
    assert "cash_flow" not in leg
    assert leg["quantity"] == Decimal("-0.2001")  # net of fee (PR #31)
    # Effective price = settlement / |net_qty| = 14000 / 0.2001.
    assert leg["price"] == Decimal("14000") / Decimal("0.2001")
    # Invariant: |price * net_qty| reproduces the gross settlement (14000).
    assert abs(leg["price"] * leg["quantity"]) == Decimal("14000")


@pytest.mark.django_db
def test_buy_with_fee_has_fee_inclusive_cost_basis(user, crypto_account):
    """Proof that get_economic_basis includes the fee: persist a base-fee buy,
    then call get_economic_basis and assert the basis == cash actually paid
    (NOT cash_paid minus fee*price). This holds with ZERO calc-layer changes
    because the stored price is the effective (fee-inclusive) price.

    Note: the price field is a DecimalField(18, 9), so the full-precision
    effective price 7000/0.0999 = 70070.07007007... is rounded to 9dp on save,
    making basis = 6999.9999999999930 (within 7e-12 of 7000) rather than
    exactly 7000. The assertion tolerates this model-rounding artifact but
    still proves the fee is INCLUDED (basis ≈ 7000, NOT 6993 = 7000 - fee)."""
    from datetime import datetime, timezone
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event
    from services.realized import get_economic_basis

    # BTC-USDT buy: 0.1 @ 70000, fee -0.0001 BTC (base asset).
    # net qty = 0.0999; cash paid = 0.1*70000 = 7000; effective price = 7000/0.0999.
    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:basis-1",
        group_id="order-basis",
        timestamp_ms=1769472000000,  # 2026-01-27
        category="trade",
        raw_type="spot_fill",
        legs=[{
            "asset": "BTC",
            "quantity": Decimal("0.0999"),  # net of fee
            "price": Decimal("7000") / Decimal("0.0999"),  # effective price
            "price_asset": "USD",
            "role": "base",
            "cash_flow": Decimal("-7000"),
            "quote_currency": "USDT",
            "fee_asset": "BTC",
        }],
        fee={"asset": "BTC", "quantity": Decimal("-0.0001"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)

    btc = Transactions.objects.get(investor=user, account=crypto_account).security
    basis = get_economic_basis(btc, datetime(2026, 1, 28, tzinfo=timezone.utc), user, "USD")
    # Basis == cash paid (7000), NOT 7000 - fee*price (which would be 6993).
    # Tolerate the 9dp price-field rounding artifact (basis is within 7e-12 of 7000).
    assert abs(basis - Decimal("7000")) < Decimal("0.01"), (
        f"basis={basis!r}; expected ~7000 (cash paid, fee included), "
        f"NOT 6993 (cash paid minus fee*price)"
    )
    # Hard lower bound: a basis below 6996 would mean the fee was NOT included
    # (the no-fee-inclusive basis would be 7000 - 0.0001*70000 = 6993).
    assert basis > Decimal("6996"), (
        f"basis={basis!r} is too low — the fee is NOT included in the cost basis"
    )


@pytest.mark.django_db
def test_cash_flow_preserves_full_precision(user, crypto_account):
    """Regression for issue #32: cash_flow must preserve 8dp stablecoin amounts
    (not truncate to 2dp), so symmetric in/out flows net to exactly zero."""
    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:cf-precision",
        group_id="cf-precision",
        timestamp_ms=1738454400000,
        category="deposit",
        raw_type="transfer",
        legs=_single_leg("USDT", Decimal("99.69064956"), "USDT"),
        fee=None,
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    tx = Transactions.objects.get(investor=user, account=crypto_account)
    # Full 8dp preserved — NOT truncated to 99.69.
    assert tx.cash_flow == Decimal("99.69064956")
