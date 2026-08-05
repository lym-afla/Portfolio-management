from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from services.crypto_exchange import (
    CryptoExchangeEvent,
    fetch_crypto_usd_price_from_yahoo,
    normalize_bybit_spot_execution,
    normalize_okx_spot_fill,
    parse_option_symbol,
)


def _leg_quantities(event):
    return {leg["asset"]: leg["quantity"] for leg in event.legs}


def test_normalize_bybit_spot_execution_buy_btc_usdt_with_quote_fee():
    event = normalize_bybit_spot_execution(
        {
            "execId": "exec-1",
            "orderId": "order-1",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "execQty": "0.1",
            "execPrice": "60000",
            "execFee": "3",
            "feeCurrency": "USDT",
            "execTime": "1767225600000",
        }
    )

    assert isinstance(event, CryptoExchangeEvent)
    assert event.provider == "bybit"
    assert event.provider_event_id == "exec-1"
    assert event.group_id == "order-1"
    assert event.timestamp_ms == 1767225600000
    assert event.category == "trade"
    assert event.raw_type == "spot_execution"
    # Stablecoin-quote spot trades emit a SINGLE base leg (USDT is cash, not a
    # separate asset): actual fill quantity, with an effective price so that
    # |price*qty| reproduces the net-of-fee settlement. cash_flow is NOT on the
    # leg (computed later from p*q).
    assert _leg_quantities(event) == {"BTC": Decimal("0.1")}
    assert len(event.legs) == 1
    assert "cash_flow" not in event.legs[0]
    # No quote_cash_amount -> settlement = qty*price (principal) -> price = fill.
    assert event.legs[0]["price"] == Decimal("60000")
    assert event.fee == {
        "asset": "USDT",
        "quantity": Decimal("-3"),
        "is_rebate": False,
    }
    assert event.legs[0]["role"] == "base"
    assert event.legs[0]["price_asset"] == "USD"


def test_normalize_bybit_spot_execution_sell_with_base_fee():
    event = normalize_bybit_spot_execution(
        {
            "execId": "exec-2",
            "orderId": "",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "execQty": "0.25",
            "execPrice": "61000",
            "execFee": "0.0002",
            "feeCurrency": "BTC",
            "execTime": "1767225600001",
        }
    )

    assert event.group_id == "exec-2"
    # BTC fee on a BTC-USDT sell: BTC is the base and USDT is the settlement, so
    # the BTC fee is CROSS-currency. Under the new real-price model (spec §5.3)
    # it becomes a separate ``role="commission"`` leg; the base leg keeps the
    # REAL fill price (61000) and the REAL (un-netted) quantity. cash_flow is
    # NOT on either leg.
    assert len(event.legs) == 2
    base_leg = next(leg for leg in event.legs if leg.get("role") == "base")
    commission_leg = next(leg for leg in event.legs if leg.get("role") == "commission")
    assert base_leg["asset"] == "BTC"
    assert base_leg["quantity"] == Decimal("-0.25")
    assert "cash_flow" not in base_leg
    assert base_leg["price"] == Decimal("61000")
    assert commission_leg["asset"] == "BTC"
    assert commission_leg["quantity"] == Decimal("-0.0002")
    assert commission_leg["role"] == "commission"
    assert event.fee["asset"] == "BTC"
    assert event.fee["quantity"] == Decimal("-0.0002")


def test_normalize_bybit_spot_execution_treats_negative_fee_as_cost():
    event = normalize_bybit_spot_execution(
        {
            "execId": "exec-negative-fee",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "execQty": "0.1",
            "execPrice": "60000",
            "execFee": "-3",
            "feeCurrency": "USDT",
            "execTime": "1767225600001",
        }
    )

    # Negative fee on the exchange side is normalized to a cost (fee_delta is
    # negated to -abs()), so the buy still pays value + fee in USDT. The
    # effective price excludes the commission: priced_settlement = 6000 + (-3).
    assert _leg_quantities(event) == {"BTC": Decimal("0.1")}
    assert len(event.legs) == 1
    assert "cash_flow" not in event.legs[0]
    # No quote_cash_amount -> price = fill.
    assert event.legs[0]["price"] == Decimal("60000")


def test_normalize_bybit_spot_execution_third_asset_fee_emits_commission_leg():
    event = normalize_bybit_spot_execution(
        {
            "execId": "exec-3",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "execQty": "2",
            "execPrice": "3000",
            "execFee": "1",
            "feeCurrency": "BNB",
            "execTime": "1767225600002",
        }
    )

    assert event.group_id == "exec-3"
    # The BNB fee is neither the base nor the quote, so it is CROSS-currency
    # relative to the USDT settlement. Under the new real-price model (spec
    # §5.3) it is NOT dropped — it becomes a separate ``role="commission"`` leg
    # that moves the BNB quantity. The base leg keeps the REAL fill price and
    # the REAL (un-netted) quantity. cash_flow is NOT on either leg.
    assert len(event.legs) == 2
    base_leg = next(leg for leg in event.legs if leg.get("role") == "base")
    commission_leg = next(leg for leg in event.legs if leg.get("role") == "commission")
    assert base_leg["asset"] == "ETH"
    assert base_leg["quantity"] == Decimal("2")
    assert "cash_flow" not in base_leg
    # Real fill price on the base leg (not adjusted for the cross-currency fee).
    assert base_leg["price"] == Decimal("3000")
    # Separate BNB commission leg moving the fee quantity.
    assert commission_leg["asset"] == "BNB"
    assert commission_leg["quantity"] == Decimal("-1")
    assert commission_leg["role"] == "commission"
    assert event.fee["asset"] == "BNB"
    assert event.fee["quantity"] == Decimal("-1")


def test_normalize_bybit_spot_execution_splits_btc_quote_suffix():
    event = normalize_bybit_spot_execution(
        {
            "execId": "exec-4",
            "symbol": "ETHBTC",
            "side": "Buy",
            "execQty": "1.5",
            "execPrice": "0.05",
            "execFee": "0",
            "feeCurrency": "BTC",
            "execTime": "1767225600003",
        }
    )

    assert _leg_quantities(event) == {
        "ETH": Decimal("1.5"),
        "BTC": Decimal("-0.075"),
    }
    assert event.legs[0]["price"] == Decimal("0.05")
    assert event.legs[0]["price_asset"] == "BTC"
    assert event.legs[1]["price_asset"] == "BTC"


def test_normalize_bybit_spot_execution_rejects_unsupported_quote_suffix():
    with pytest.raises(ValueError, match="Cannot split crypto symbol"):
        normalize_bybit_spot_execution(
            {
                "execId": "exec-5",
                "symbol": "BTCDAI",
                "side": "Buy",
                "execQty": "1",
                "execPrice": "1",
                "execFee": "0",
                "feeCurrency": "DAI",
                "execTime": "1767225600004",
            }
        )


def test_normalize_okx_spot_fill_sell_btc_usdt_with_negative_base_fee():
    event = normalize_okx_spot_fill(
        {
            "tradeId": "trade-1",
            "ordId": "order-1",
            "instId": "BTC-USDT",
            "side": "sell",
            "fillSz": "0.2",
            "fillPx": "70000",
            "fee": "-0.0001",
            "feeCcy": "BTC",
            "fillTime": "1767225600000",
        }
    )

    assert event.provider == "okx"
    assert event.provider_event_id == "trade-1"
    assert event.group_id == "order-1"
    assert event.timestamp_ms == 1767225600000
    assert event.category == "trade"
    assert event.raw_type == "spot_fill"
    # BTC fee on a BTC-USDT sell: BTC is the base and USDT is the settlement, so
    # the BTC fee is CROSS-currency. Under the new real-price model (spec §5.3)
    # it becomes a separate ``role="commission"`` leg; the base leg keeps the
    # REAL fill price (70000) and the REAL (un-netted) quantity. cash_flow is
    # NOT on either leg.
    assert len(event.legs) == 2
    base_leg = next(leg for leg in event.legs if leg.get("role") == "base")
    commission_leg = next(leg for leg in event.legs if leg.get("role") == "commission")
    assert base_leg["asset"] == "BTC"
    assert base_leg["quantity"] == Decimal("-0.2")
    assert "cash_flow" not in base_leg
    assert base_leg["price"] == Decimal("70000")
    assert commission_leg["asset"] == "BTC"
    assert commission_leg["quantity"] == Decimal("-0.0001")
    assert commission_leg["role"] == "commission"
    assert event.fee == {
        "asset": "BTC",
        "quantity": Decimal("-0.0001"),
        "is_rebate": False,
    }


def test_normalize_okx_spot_fill_buy_with_quote_fee():
    event = normalize_okx_spot_fill(
        {
            "tradeId": "trade-2",
            "ordId": "",
            "instId": "BTC-USDT",
            "side": "buy",
            "fillSz": "0.5",
            "fillPx": "70000",
            "fee": "-5",
            "feeCcy": "USDT",
            "fillTime": "1767225600001",
        }
    )

    assert event.group_id == "trade-2"
    # Single base leg: actual fill quantity; effective price reproduces the
    # net-of-fee settlement. cash_flow is NOT on the leg.
    assert _leg_quantities(event) == {"BTC": Decimal("0.5")}
    assert len(event.legs) == 1
    assert "cash_flow" not in event.legs[0]
    # No quote_cash_amount -> settlement = qty*price (principal) -> price = fill.
    assert event.legs[0]["price"] == Decimal("70000")
    assert event.fee["asset"] == "USDT"
    assert event.fee["quantity"] == Decimal("-5")


def test_normalize_okx_spot_fill_positive_fee_is_rebate():
    event = normalize_okx_spot_fill(
        {
            "tradeId": "trade-rebate",
            "ordId": "order-rebate",
            "instId": "BTC-USDT",
            "side": "sell",
            "fillSz": "0.2",
            "fillPx": "70000",
            "fee": "0.0001",
            "feeCcy": "BTC",
            "fillTime": "1767225600002",
        }
    )

    # BTC fee on a BTC-USDT sell: BTC is the base, USDT is the settlement, so a
    # BTC fee is CROSS-currency. The rebate (+0.0001 BTC) becomes a separate
    # ``role="commission"`` leg moving the BTC quantity; the base leg keeps the
    # REAL fill price (70000) and the REAL (un-netted) quantity. cash_flow is
    # NOT on either leg.
    assert len(event.legs) == 2
    base_leg = next(leg for leg in event.legs if leg.get("role") == "base")
    commission_leg = next(leg for leg in event.legs if leg.get("role") == "commission")
    assert base_leg["asset"] == "BTC"
    assert base_leg["quantity"] == Decimal("-0.2")
    assert "cash_flow" not in base_leg
    assert base_leg["price"] == Decimal("70000")
    # The BTC rebate lands in the separate commission leg as a positive BTC delta
    # (it is a rebate — the trader receives it, hence is_rebate=True).
    assert commission_leg["asset"] == "BTC"
    assert commission_leg["quantity"] == Decimal("0.0001")
    assert event.fee == {
        "asset": "BTC",
        "quantity": Decimal("0.0001"),
        "is_rebate": True,
    }


def test_parse_btc_call_option_symbol_with_mixed_case_month():
    parsed = parse_option_symbol("BTC-27jun26-100000-C")

    assert parsed["underlying"] == "BTC"
    assert parsed["expiration_date"].isoformat() == "2026-06-27"
    assert parsed["strike_price"] == Decimal("100000")
    assert parsed["option_type"] == "CALL"


def test_parse_btc_put_option_symbol():
    parsed = parse_option_symbol("BTC-27JUN26-100000-P")

    assert parsed["underlying"] == "BTC"
    assert parsed["expiration_date"].isoformat() == "2026-06-27"
    assert parsed["strike_price"] == Decimal("100000")
    assert parsed["option_type"] == "PUT"


def test_parse_settlement_suffixed_option_symbol():
    parsed = parse_option_symbol("BTC-13FEB25-89000-P-USDT")

    assert parsed["underlying"] == "BTC"
    assert parsed["expiration_date"].isoformat() == "2025-02-13"
    assert parsed["strike_price"] == Decimal("89000")
    assert parsed["option_type"] == "PUT"
    assert parsed["settlement_asset"] == "USDT"


@pytest.mark.parametrize(
    "symbol",
    [
        "BTC-27JUN26-100000",
        "-27JUN26-100000-C",
        "BTC-27JUN26-notnum-C",
        "BTC-27JUN26-NaN-C",
        "BTC-27JUN26-Infinity-C",
        "BTC-27FOO26-100000-C",
        "BTC-27JUN26-100000-X",
        "BTC-13FEB25-89000-P-",
    ],
)
def test_parse_option_symbol_rejects_malformed_symbols(symbol):
    with pytest.raises(ValueError):
        parse_option_symbol(symbol)


def test_parse_okx_option_symbol_call():
    parsed = parse_option_symbol("BTC-USD-240315-50000-C")

    assert parsed["underlying"] == "BTC"
    assert parsed["expiration_date"].isoformat() == "2024-03-15"
    assert parsed["strike_price"] == Decimal("50000")
    assert parsed["option_type"] == "CALL"
    assert parsed["settlement_asset"] == "USD"


def test_parse_okx_option_symbol_put_usdt_settlement():
    parsed = parse_option_symbol("BTC-USDT-240315-50000-P")

    assert parsed["expiration_date"].isoformat() == "2024-03-15"
    assert parsed["option_type"] == "PUT"
    assert parsed["settlement_asset"] == "USDT"


@pytest.mark.parametrize(
    "symbol",
    [
        "BTC-USD-2413-50000-C",      # too-short date
        "BTC-USD-240315-50000",      # missing side
        "BTC-USD-240315-notnum-C",   # bad strike
        "BTC-ETH-240315-50000-C",    # segment 2 not a date or known coin
    ],
)
def test_parse_okx_option_symbol_rejects_malformed(symbol):
    with pytest.raises(ValueError):
        parse_option_symbol(symbol)


@pytest.mark.django_db
def test_fetch_crypto_usd_price_from_yahoo_uses_btc_usd_symbol():
    # Task 8: yahoo_symbol is now read from the Assets row (per-asset), not
    # from a hardcoded dict. The function needs a Crypto asset with name="BTC"
    # and yahoo_symbol="BTC-USD" to proceed.
    from common.models import Assets

    Assets.objects.create(
        type="Crypto",
        ISIN="CRYPTO:BTC",
        name="BTC",
        currency="USD",
        yahoo_symbol="BTC-USD",
    )

    history = pd.DataFrame(
        {"Close": [60000.0, 61000.123456]},
        index=pd.to_datetime(["2025-12-31", "2026-01-01"]),
    )

    with patch("services.crypto_exchange.yf.Ticker") as ticker_class:
        ticker_class.return_value.history.return_value = history

        price = fetch_crypto_usd_price_from_yahoo("BTC", date(2026, 1, 1))

    ticker_class.assert_called_once_with("BTC-USD")
    ticker_class.return_value.history.assert_called_once_with(
        start="2025-12-26",
        end="2026-01-02",
        auto_adjust=False,
    )
    assert price == Decimal("61000.123456")


@pytest.mark.django_db
def test_fetch_crypto_usd_price_from_yahoo_rejects_missing_requested_date():
    from common.models import Assets

    Assets.objects.create(
        type="Crypto",
        ISIN="CRYPTO:BTC",
        name="BTC",
        currency="USD",
        yahoo_symbol="BTC-USD",
    )

    history = pd.DataFrame(
        {"Close": [60000.0]},
        index=pd.to_datetime(["2025-12-31"]),
    )

    with patch("services.crypto_exchange.yf.Ticker") as ticker_class:
        ticker_class.return_value.history.return_value = history

        price = fetch_crypto_usd_price_from_yahoo("BTC", date(2026, 1, 1))

    assert price is None


@pytest.mark.django_db
def test_fetch_crypto_usd_price_from_yahoo_returns_none_for_unsupported_symbol():
    # No ETH Assets row exists in this test's DB → the function returns None
    # without calling yf.Ticker. (Previously: "symbol not in dict"; now:
    # "no asset row / asset has no yahoo_symbol".)
    with patch("services.crypto_exchange.yf.Ticker") as ticker_class:
        price = fetch_crypto_usd_price_from_yahoo("ETH", date(2026, 1, 1))

    ticker_class.assert_not_called()
    assert price is None


@pytest.mark.django_db
def test_fetch_crypto_usd_price_from_yahoo_returns_none_when_asset_has_no_yahoo_symbol():
    # Task 8: a Crypto row that exists but has a blank yahoo_symbol must also
    # short-circuit to None (e.g. a coin Yahoo can't price).
    from common.models import Assets

    Assets.objects.create(
        type="Crypto",
        ISIN="CRYPTO:NOQUOTE",
        name="NOQUOTE",
        currency="USD",
        yahoo_symbol=None,
    )

    with patch("services.crypto_exchange.yf.Ticker") as ticker_class:
        price = fetch_crypto_usd_price_from_yahoo("NOQUOTE", date(2026, 1, 1))

    ticker_class.assert_not_called()
    assert price is None


from services.crypto_exchange import _single_leg


def test_single_leg_builds_one_element_list_with_defaults():
    legs = _single_leg("BTC", Decimal("0.001"), "BTC")

    assert len(legs) == 1
    leg = legs[0]
    assert leg["asset"] == "BTC"
    assert leg["quantity"] == Decimal("0.001")
    assert leg["price"] == Decimal("1")
    assert leg["price_asset"] == "BTC"
    assert leg["role"] == "base"
    assert leg["instrument"] == "coin"


def test_single_leg_accepts_option_instrument():
    legs = _single_leg("BTC-27DEC24-75000-C", Decimal("2"), "USDT", role="base", instrument="option")

    assert legs[0]["instrument"] == "option"
    assert legs[0]["role"] == "base"


from services.crypto_exchange import _merge_sorted_events


def _event(ts, eid):
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=eid,
        group_id=eid,
        timestamp_ms=ts,
        category="trade",
        raw_type="x",
        legs=[],
    )


def test_merge_sorted_events_interleaves_by_timestamp():
    a = [_event(100, "a1"), _event(300, "a3")]
    b = [_event(200, "b2"), _event(400, "b4")]

    result = [e.provider_event_id for e in _merge_sorted_events(iter(a), iter(b))]

    assert result == ["a1", "b2", "a3", "b4"]


def test_merge_sorted_events_preserves_stable_order_on_ties():
    a = [_event(100, "a1")]
    b = [_event(100, "b1")]

    result = [e.provider_event_id for e in _merge_sorted_events(iter(a), iter(b))]

    assert result == ["a1", "b1"]


def test_merge_sorted_events_handles_empty_streams():
    result = list(_merge_sorted_events(iter([]), iter([]), iter([_event(100, "x")])))

    assert [e.provider_event_id for e in result] == ["x"]


def test_merge_sorted_events_handles_all_empty():
    assert list(_merge_sorted_events(iter([]), iter([]))) == []


def test_merge_sorted_events_single_stream():
    a = [_event(100, "a1"), _event(200, "a2")]

    result = [e.provider_event_id for e in _merge_sorted_events(iter(a))]

    assert result == ["a1", "a2"]


from services.crypto_exchange import (
    normalize_bybit_deposit,
    normalize_bybit_withdrawal,
    normalize_okx_deposit,
    normalize_okx_withdrawal,
)


def test_normalize_bybit_deposit_stablecoin():
    event = normalize_bybit_deposit(
        {
            "coin": "USDT",
            "amount": "500",
            "txID": "dep-tx-1",
            "successAt": "1700000000000",
            "status": "SUCCESS",
        }
    )

    assert event.provider == "bybit"
    assert event.provider_event_id == "dep-tx-1"
    assert event.category == "deposit"
    assert event.raw_type == "deposit"
    assert event.timestamp_ms == 1700000000000
    assert event.fee is None
    assert len(event.legs) == 1
    assert event.legs[0]["asset"] == "USDT"
    assert event.legs[0]["quantity"] == Decimal("500")
    assert event.legs[0]["instrument"] == "coin"


def test_normalize_bybit_withdrawal_btc():
    event = normalize_bybit_withdrawal(
        {
            "coin": "BTC",
            "chain": "BTC",
            "amount": "0.05",
            "txID": "0xdeadbeef",
            "status": "success",
            "withdrawId": "wd-1",
            "createTime": "1700000001000",
        }
    )

    assert event.category == "withdrawal"
    assert event.provider_event_id == "wd-1"
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("-0.05")
    assert event.legs[0]["instrument"] == "coin"


def test_normalize_okx_deposit():
    # Real deposit-history row uses ``depId`` as the per-row id; no ``type`` key.
    event = normalize_okx_deposit(
        {
            "depId": "410907740",
            "amt": "29994.781592",
            "ccy": "USDT",
            "ts": "1782146981000",
            "state": "2",
            "chain": "USDT-TRC20",
            "txId": "0xabc",
        }
    )

    assert event.provider == "okx"
    assert event.category == "deposit"
    assert event.raw_type == "deposit"
    assert event.provider_event_id == "deposit:410907740"
    assert event.group_id == "410907740"
    assert event.timestamp_ms == 1782146981000
    assert len(event.legs) == 1
    assert event.legs[0]["asset"] == "USDT"
    assert event.legs[0]["quantity"] == Decimal("29994.781592")
    assert event.legs[0]["instrument"] == "coin"


def test_normalize_okx_withdrawal_direction_prefixed_id():
    # Real withdrawal-history row uses ``wdId`` as the per-row id.
    event = normalize_okx_withdrawal(
        {
            "wdId": "510907741",
            "amt": "0.1",
            "ccy": "BTC",
            "ts": "1782146982000",
            "state": "2",
            "chain": "BTC-Bitcoin",
            "fee": "0.0001",
        }
    )

    assert event.category == "withdrawal"
    assert event.raw_type == "withdrawal"
    assert event.provider_event_id == "withdrawal:510907741"
    assert event.group_id == "510907741"
    assert event.timestamp_ms == 1782146982000
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("-0.1")


def test_normalize_okx_withdrawal_falls_back_to_ts_when_no_wd_id():
    # Per task spec: fall back to ``clientId`` then ``ts`` if ``wdId`` absent.
    event = normalize_okx_withdrawal(
        {
            "clientId": "client-7",
            "amt": "1",
            "ccy": "ETH",
            "ts": "1782146983000",
        }
    )

    assert event.provider_event_id == "withdrawal:client-7"
    assert event.group_id == "client-7"
    assert event.legs[0]["quantity"] == Decimal("-1")


from services.crypto_exchange import (
    normalize_bybit_reward,
    normalize_okx_reward,
)


def test_normalize_bybit_reward_btc():
    event = normalize_bybit_reward(
        {
            "symbol": "BTC",
            "change": "0.001",
            "transactionTime": "1700000004000",
            "type": "Earn",
            "id": "earn-1",
        }
    )

    assert event.category == "reward"
    assert event.raw_type == "earn"
    assert event.provider_event_id == "earn-1"
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("0.001")
    assert event.legs[0]["instrument"] == "coin"


def test_normalize_bybit_reward_skips_internal_transfer():
    event = normalize_bybit_reward(
        {
            "symbol": "USDT",
            "change": "100",
            "transactionTime": "1700000005000",
            "type": "InternalTransfer",
            "id": "tr-1",
        }
    )

    assert event is None


def test_normalize_okx_reward_stablecoin():
    # Real earn-lending row carries no ``billId`` and no ``subType``; ``ts`` is
    # the unique per-row identifier.
    event = normalize_okx_reward(
        {
            "amt": "1.0024773435509866",
            "ccy": "USDT",
            "earnings": "0.00000183",
            "rate": "0.0189",
            "ts": "1785088949000",
        }
    )

    assert event.category == "reward"
    assert event.raw_type == "earn"
    assert event.provider_event_id == "earn:1785088949000"
    assert event.group_id == "1785088949000"
    assert event.timestamp_ms == 1785088949000
    assert event.legs[0]["asset"] == "USDT"
    assert event.legs[0]["quantity"] == Decimal("1.0024773435509866")


def test_normalize_okx_reward_skips_internal_transfer():
    # The ``subType`` filter is checked defensively (``.get``) since real
    # earn-lending rows do not carry it. A payload with a skipped subType must
    # still be filtered out.
    event = normalize_okx_reward(
        {
            "amt": "100",
            "ccy": "USDT",
            "ts": "1700000007000",
            "subType": "1",
        }
    )

    assert event is None


from services.crypto_exchange import (
    normalize_bybit_option_execution,
    normalize_bybit_option_settlement,
    normalize_okx_option_fill,
    normalize_okx_option_settlement,
)


def test_normalize_bybit_option_execution_buy_call():
    event = normalize_bybit_option_execution(
        {
            "symbol": "BTC-27JUN26-100000-C",
            "execId": "opt-ex-1",
            "orderId": "opt-order-1",
            "side": "Buy",
            "execQty": "2",
            "execPrice": "500",
            "execFee": "1",
            "feeCurrency": "USDT",
            "execTime": "1700000008000",
        }
    )

    assert event.category == "trade"
    assert event.raw_type == "option_execution"
    assert event.provider_event_id == "opt-ex-1"
    assert event.group_id == "opt-order-1"
    assert len(event.legs) == 1
    assert event.legs[0]["instrument"] == "option"
    assert event.legs[0]["asset"] == "BTC-27JUN26-100000-C"
    assert event.legs[0]["quantity"] == Decimal("2")
    assert event.legs[0]["price"] == Decimal("500")
    assert event.legs[0]["price_asset"] == "USDT"


def test_normalize_okx_option_fill_sell_put():
    event = normalize_okx_option_fill(
        {
            "instId": "BTC-USD-240315-50000-P",
            "tradeId": "okx-opt-1",
            "ordId": "okx-opt-order-1",
            "side": "sell",
            "fillSz": "1.5",
            "fillPx": "1200",
            "fee": "-1.8",
            "feeCcy": "USDT",
            "fillTime": "1700000009000",
        }
    )

    assert event.category == "trade"
    assert event.raw_type == "option_fill"
    assert event.legs[0]["instrument"] == "option"
    assert event.legs[0]["asset"] == "BTC-USD-240315-50000-P"
    assert event.legs[0]["quantity"] == Decimal("-1.5")
    assert event.legs[0]["price"] == Decimal("1200")


def test_normalize_bybit_option_settlement_exercised():
    event = normalize_bybit_option_settlement(
        {
            "symbol": "BTC",
            "change": "0.5",
            "transactionTime": "1700000010000",
            "type": "Settlement",
            "id": "settle-1",
            "orderLinkId": "opt-order-1",
            "newWalletBalance": "65000",
        }
    )

    assert event.category == "settlement"
    assert event.raw_type == "option_delivery"
    assert event.group_id == "opt-order-1"
    assert event.provider_event_id == "settle-1"
    assert event.legs[0]["instrument"] == "coin"
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("0.5")
    assert event.legs[0]["price"] == Decimal("65000")


def test_normalize_okx_option_settlement():
    # Real bills-archive (OPTION-filtered) row: ``ccy`` is the delivered coin,
    # ``balChg`` the signed delivered amount, ``px`` the settlement price.
    event = normalize_okx_option_settlement(
        {
            "billId": "3628711646064058370",
            "instId": "BTC-USD-260605-80000-C",
            "instType": "OPTION",
            "ccy": "BTC",
            "balChg": "0.0071621135119712",
            "px": "62703.9433340777132648",
            "ts": "1780646434327",
            "subType": "172",
            "type": "3",
            "pnl": "0.000154",
            "ordId": "okx-opt-order-1",
        }
    )

    assert event.category == "settlement"
    assert event.raw_type == "option_delivery"
    assert event.provider_event_id == "3628711646064058370"
    assert event.group_id == "okx-opt-order-1"
    assert event.timestamp_ms == 1780646434327
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("0.0071621135119712")
    assert event.legs[0]["price"] == Decimal("62703.9433340777132648")
