"""Normalize crypto exchange payloads into portfolio import events."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple


SUPPORTED_QUOTE_SUFFIXES = ("USDT", "USDC", "USD", "BTC", "ETH")

MONTH_NUMBERS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


@dataclass
class CryptoExchangeEvent:
    provider: str
    provider_event_id: str
    group_id: str
    timestamp_ms: int
    category: str
    raw_type: str
    legs: List[Dict[str, Any]]
    fee: Optional[Dict[str, Any]] = None


def _split_symbol(symbol: str) -> Tuple[str, str]:
    for quote in SUPPORTED_QUOTE_SUFFIXES:
        if symbol.endswith(quote) and symbol != quote:
            return symbol[: -len(quote)], quote
    raise ValueError(f"Cannot split crypto symbol: {symbol}")


def _spot_legs(
    side: str,
    base: str,
    quote: str,
    qty: Decimal,
    price: Decimal,
    fee_delta: Decimal,
    fee_asset: str,
) -> List[Dict[str, Any]]:
    value = qty * price
    quote_fee_delta = fee_delta if fee_asset == quote else Decimal("0")
    base_fee_delta = fee_delta if fee_asset == base else Decimal("0")

    if side.lower() == "buy":
        legs = [
            {
                "asset": base,
                "quantity": qty + base_fee_delta,
                "price": price,
                "price_asset": quote,
                "role": "base",
            },
            {
                "asset": quote,
                "quantity": -value + quote_fee_delta,
                "price": Decimal("1"),
                "price_asset": quote,
                "role": "quote",
            },
        ]
    elif side.lower() == "sell":
        legs = [
            {
                "asset": base,
                "quantity": -qty + base_fee_delta,
                "price": price,
                "price_asset": quote,
                "role": "base",
            },
            {
                "asset": quote,
                "quantity": value + quote_fee_delta,
                "price": Decimal("1"),
                "price_asset": quote,
                "role": "quote",
            },
        ]
    else:
        raise ValueError(f"Unsupported spot side: {side}")

    if fee_delta and fee_asset not in {base, quote}:
        legs.append(
            {
                "asset": fee_asset,
                "quantity": fee_delta,
                "price": Decimal("0"),
                "price_asset": fee_asset,
                "role": "fee",
            }
        )

    return legs


def normalize_bybit_spot_execution(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    base, quote = _split_symbol(payload["symbol"])
    qty = Decimal(payload["execQty"])
    price = Decimal(payload["execPrice"])
    fee_delta = -abs(Decimal(payload.get("execFee") or "0"))
    fee_asset = payload.get("feeCurrency") or quote

    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["execId"],
        group_id=payload.get("orderId") or payload["execId"],
        timestamp_ms=int(payload["execTime"]),
        category="trade",
        raw_type="spot_execution",
        legs=_spot_legs(payload["side"], base, quote, qty, price, fee_delta, fee_asset),
        fee={
            "asset": fee_asset,
            "quantity": fee_delta,
            "is_rebate": fee_delta > 0,
        },
    )


def normalize_okx_spot_fill(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    parts = payload["instId"].split("-")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"Cannot split OKX spot instrument: {payload['instId']}")

    base, quote = parts
    qty = Decimal(payload["fillSz"])
    price = Decimal(payload["fillPx"])
    fee_delta = Decimal(payload.get("fee") or "0")
    fee_asset = payload.get("feeCcy") or quote

    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=payload["tradeId"],
        group_id=payload.get("ordId") or payload["tradeId"],
        timestamp_ms=int(payload["fillTime"]),
        category="trade",
        raw_type="spot_fill",
        legs=_spot_legs(payload["side"], base, quote, qty, price, fee_delta, fee_asset),
        fee={
            "asset": fee_asset,
            "quantity": fee_delta,
            "is_rebate": fee_delta > 0,
        },
    )


def parse_option_symbol(symbol: str) -> Dict[str, Any]:
    parts = symbol.split("-")
    if len(parts) not in (4, 5):
        raise ValueError(f"Malformed option symbol: {symbol}")

    underlying, expiry_token, strike, option_side = parts[:4]
    settlement_asset = parts[4] if len(parts) == 5 else None
    if not underlying:
        raise ValueError(f"Malformed option symbol: {symbol}")
    if settlement_asset == "":
        raise ValueError(f"Malformed option settlement asset: {symbol}")
    if len(expiry_token) != 7:
        raise ValueError(f"Malformed option expiration: {expiry_token}")

    try:
        day = int(expiry_token[:2])
        month = MONTH_NUMBERS[expiry_token[2:5].upper()]
        year = 2000 + int(expiry_token[5:])
        expiration_date = date(year, month, day)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Malformed option expiration: {expiry_token}") from exc

    option_type_by_side = {
        "C": "CALL",
        "P": "PUT",
    }
    try:
        option_type = option_type_by_side[option_side.upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown option side: {option_side}") from exc

    try:
        strike_price = Decimal(strike)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Malformed option strike: {strike}") from exc
    if not strike_price.is_finite():
        raise ValueError(f"Malformed option strike: {strike}")

    parsed = {
        "underlying": underlying,
        "expiration_date": expiration_date,
        "strike_price": strike_price,
        "option_type": option_type,
    }
    if settlement_asset:
        parsed["settlement_asset"] = settlement_asset
    return parsed
