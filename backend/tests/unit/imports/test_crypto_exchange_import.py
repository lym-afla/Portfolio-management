from decimal import Decimal

import pytest

from core.crypto_exchange_import import (
    CryptoExchangeEvent,
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
    assert _leg_quantities(event) == {
        "BTC": Decimal("0.1"),
        "USDT": Decimal("-6003"),
    }
    assert event.legs[0]["price"] == Decimal("60030")
    assert event.fee == {
        "asset": "USDT",
        "quantity": Decimal("-3"),
        "is_rebate": False,
    }
    assert event.legs[0]["role"] == "base"
    assert event.legs[0]["price_asset"] == "USDT"
    assert event.legs[1]["role"] == "quote"
    assert event.legs[1]["price_asset"] == "USDT"


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
    assert _leg_quantities(event) == {
        "BTC": Decimal("-0.2502"),
        "USDT": Decimal("15250.00"),
    }
    assert event.legs[0]["price"] == Decimal("15250.00") / Decimal("0.2502")
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

    assert _leg_quantities(event) == {
        "BTC": Decimal("0.1"),
        "USDT": Decimal("-6003"),
    }


def test_normalize_bybit_spot_execution_keeps_third_asset_fee_in_metadata_only():
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
    assert _leg_quantities(event) == {
        "ETH": Decimal("2"),
        "USDT": Decimal("-6000"),
    }
    assert len(event.legs) == 2
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
    assert _leg_quantities(event) == {
        "BTC": Decimal("-0.2001"),
        "USDT": Decimal("14000.0"),
    }
    assert event.legs[0]["price"] == Decimal("14000.0") / Decimal("0.2001")
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
    assert _leg_quantities(event) == {
        "BTC": Decimal("0.5"),
        "USDT": Decimal("-35005.0"),
    }
    assert event.legs[0]["price"] == Decimal("70010")
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

    assert _leg_quantities(event) == {
        "BTC": Decimal("-0.1999"),
        "USDT": Decimal("14000.0"),
    }
    assert event.legs[0]["price"] == Decimal("14000.0") / Decimal("0.1999")
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
