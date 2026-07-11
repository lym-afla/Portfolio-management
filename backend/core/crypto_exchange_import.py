"""Normalize crypto exchange payloads into portfolio import events."""

import heapq
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import blake2s
from typing import Any, Dict, List, Optional, Tuple

import yfinance as yf
from django.db import IntegrityError, transaction

from common.models import Assets, OptionMetadata, Prices, Transactions
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
)

SUPPORTED_QUOTE_SUFFIXES = ("USDT", "USDC", "USD", "BTC", "ETH")
STABLECOINS = {"USDT", "USDC", "USD"}
SKIPPED_BYBIT_INTERNAL_TRANSFER_TYPES = {"InternalTransfer", "Transfer"}
SKIPPED_OKX_INTERNAL_TRANSFER_SUBTYPES = {"1", "128", "129"}
OPTION_SETTLEMENT_COINS = {"USD", "USDT", "USDC"}
YAHOO_USD_PRICE_SYMBOLS = {"BTC": "BTC-USD"}
logger = logging.getLogger(__name__)

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


def _merge_sorted_events(*iterables):
    """K-way merge of CryptoExchangeEvent streams by timestamp_ms (stable).

    Ties are broken by source-stream order (earlier positional arg first),
    then by original position within that stream.
    """
    counters = [0] * len(iterables)
    heap = []
    for stream_idx, it in enumerate(iterables):
        try:
            event = next(it)
            heapq.heappush(heap, (event.timestamp_ms, stream_idx, counters[stream_idx], event))
            counters[stream_idx] += 1
        except StopIteration:
            pass

    while heap:
        _, stream_idx, _, event = heapq.heappop(heap)
        yield event
        try:
            nxt = next(iterables[stream_idx])
            heapq.heappush(heap, (nxt.timestamp_ms, stream_idx, counters[stream_idx], nxt))
            counters[stream_idx] += 1
        except StopIteration:
            pass


def resolve_crypto_asset(symbol, user):
    normalized_symbol = str(symbol).upper()
    asset, _ = Assets.objects.get_or_create(
        ISIN=_crypto_asset_identifier(normalized_symbol),
        currency="USD",
        defaults={
            "type": ASSET_TYPE_CRYPTO,
            "name": normalized_symbol,
            "ticker": normalized_symbol[:10],
            "exposure": "FX" if normalized_symbol in STABLECOINS else "Commodity",
        },
    )
    asset.investors.add(user)
    return asset


def resolve_crypto_option_asset(parsed_option, user):
    underlying = resolve_crypto_asset(parsed_option["underlying"], user)
    settlement_asset = parsed_option.get("settlement_asset") or "USD"
    asset_currency = (
        settlement_asset
        if settlement_asset in {"USD", "EUR", "GBP", "RUB", "CHF", "CNY"}
        else "USD"
    )
    option_symbol = (
        f"{parsed_option['underlying']}-"
        f"{parsed_option['expiration_date'].strftime('%d%b%y').upper()}-"
        f"{parsed_option['strike_price']}-{parsed_option['option_type'][0]}"
    )
    asset, _ = Assets.objects.get_or_create(
        ISIN=_crypto_asset_identifier(f"OPT:{option_symbol}"),
        currency=asset_currency,
        defaults={
            "type": "Option",
            "name": option_symbol,
            "ticker": option_symbol[:10],
            "exposure": "Derivatives",
        },
    )
    asset.investors.add(user)
    OptionMetadata.objects.get_or_create(
        asset=asset,
        defaults={
            "underlying_asset": underlying,
            "strike_price": parsed_option["strike_price"],
            "expiration_date": parsed_option["expiration_date"],
            "option_type": parsed_option["option_type"],
            "contract_size": Decimal("1"),
        },
    )
    return asset


def _crypto_asset_identifier(symbol):
    readable_identifier = f"CRYPTO:{symbol}"
    if len(readable_identifier) <= Assets._meta.get_field("ISIN").max_length:
        return readable_identifier
    digest = blake2s(symbol.encode(), digest_size=5).hexdigest().upper()
    return f"CR{digest}"


def _event_datetime(event):
    return datetime.fromtimestamp(event.timestamp_ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def _account_import_id(account):
    return account.native_id or str(account.id)


def _leg_quantity(leg):
    quantity = leg.get("quantity", Decimal("0"))
    return quantity if isinstance(quantity, Decimal) else Decimal(str(quantity))


def _leg_raw_price(leg):
    price = leg.get("price")
    if price is None:
        return None

    return price if isinstance(price, Decimal) else Decimal(str(price))


def _quote_asset_fiat_price(price_asset, user, event_date):
    quote_asset_symbol = str(price_asset).upper()
    quote_asset = resolve_crypto_asset(quote_asset_symbol, user)
    quote = (
        Prices.objects.filter(security=quote_asset, date__lte=event_date.date())
        .order_by("-date")
        .first()
    )
    if quote is None:
        imported_price = fetch_crypto_usd_price_from_yahoo(quote_asset_symbol, event_date.date())
        if imported_price is None:
            raise ValueError(
                f"Could not import fiat price for quote asset {quote_asset_symbol} "
                f"on or before {event_date.date()}"
            )
        quote, _ = Prices.objects.update_or_create(
            security=quote_asset,
            date=event_date.date(),
            defaults={
                "price": _normalize_model_decimal(Prices, "price", imported_price),
            },
        )
    return Decimal(quote.price)


def fetch_crypto_usd_price_from_yahoo(symbol, price_date):
    """Fetch a USD crypto close price from Yahoo Finance for import-time valuation."""
    yahoo_symbol = YAHOO_USD_PRICE_SYMBOLS.get(str(symbol).upper())
    if yahoo_symbol is None:
        return None

    start_date = price_date - timedelta(days=6)
    end_date = price_date + timedelta(days=1)
    try:
        history = yf.Ticker(yahoo_symbol).history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            auto_adjust=False,
        )
    except Exception as exc:
        logger.warning("Could not fetch %s price from Yahoo: %s", yahoo_symbol, exc)
        return None

    if history.empty or history["Close"].isnull().all():
        logger.warning("Yahoo returned no close price data for %s", yahoo_symbol)
        return None
    requested_date_rows = history[history.index.date == price_date]
    close_values = requested_date_rows["Close"].dropna()
    if close_values.empty:
        logger.warning(
            "Yahoo returned no close price for %s on %s",
            yahoo_symbol,
            price_date,
        )
        return None
    close = close_values.iloc[-1]
    return Decimal(str(close))


def _leg_fiat_price(leg, user, event_date):
    price = _leg_raw_price(leg)
    if price is None:
        return None

    asset_symbol = str(leg.get("asset", "")).upper()
    price_asset = leg.get("price_asset")
    normalized_price_asset = str(price_asset).upper() if price_asset else None

    if normalized_price_asset in (None, *STABLECOINS):
        return price
    if asset_symbol in STABLECOINS and price == Decimal("1"):
        return price

    quote_asset_price = _quote_asset_fiat_price(
        normalized_price_asset,
        user,
        event_date,
    )
    if asset_symbol == normalized_price_asset and price == Decimal("1"):
        return quote_asset_price
    return price * quote_asset_price


def _normalize_model_decimal(model, field_name, value):
    if value is None:
        return None

    field = model._meta.get_field(field_name)
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    abs_value = abs(decimal_value)
    int_digits = 1 if abs_value == 0 else len(str(int(abs_value)))
    max_decimal_places = min(field.decimal_places, field.max_digits - int_digits)
    if max_decimal_places < 0:
        raise ValueError(f"{field_name}={decimal_value} exceeds max_digits={field.max_digits}")
    quantizer = Decimal("0.1") ** max_decimal_places
    return decimal_value.quantize(quantizer, rounding=ROUND_HALF_UP)


def _event_comment(event, leg):
    parts = [
        f"provider={event.provider}",
        f"raw_type={event.raw_type}",
        f"group_id={event.group_id}",
        f"role={leg.get('role')}",
        f"price_asset={leg.get('price_asset')}",
    ]
    if event.fee:
        parts.extend(
            [
                f"fee_asset={event.fee.get('asset')}",
                f"fee_quantity={event.fee.get('quantity')}",
                f"fee_is_rebate={event.fee.get('is_rebate')}",
            ]
        )
    return "; ".join(parts)


def _transaction_type_for_event(event, quantity):
    category = (event.category or "").lower()
    raw_type = (event.raw_type or "").lower()
    if category == "reward":
        return TRANSACTION_TYPE_CRYPTO_REWARD
    if category == "settlement":
        return TRANSACTION_TYPE_OPTION_SETTLEMENT
    if category in {"transfer", "deposit", "withdrawal"} or raw_type in {
        "deposit",
        "withdrawal",
        "transfer",
    }:
        return (
            TRANSACTION_TYPE_CRYPTO_TRANSFER_IN
            if quantity > 0
            else TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT
        )
    return TRANSACTION_TYPE_CRYPTO_TRADE_IN if quantity > 0 else TRANSACTION_TYPE_CRYPTO_TRADE_OUT


def persist_crypto_exchange_event(event, user, account):
    created = []
    event_time = _event_datetime(event)
    import_account_id = _account_import_id(account)
    leg_records = []

    with transaction.atomic():
        for index, leg in enumerate(event.legs):
            if leg.get("role") == "fee":
                continue

            quantity = _leg_quantity(leg)
            if quantity == 0:
                continue

            price = _leg_fiat_price(leg, user, event_time)
            if price is None:
                raise ValueError(
                    "Cannot persist crypto exchange event without fiat-denominated "
                    f"price for {leg.get('asset')} leg priced in {leg.get('price_asset')}"
                )
            leg_records.append((index, leg, quantity, price))

        for index, leg, quantity, price in leg_records:
            event_id = f"{event.provider_event_id}:{index}"
            if Transactions.objects.filter(
                investor=user,
                account=account,
                import_provider=event.provider,
                import_account_id=import_account_id,
                import_event_id=event_id,
            ).exists():
                continue

            if leg.get("instrument") == "option":
                asset = resolve_crypto_option_asset(parse_option_symbol(leg["asset"]), user)
            else:
                asset = resolve_crypto_asset(leg["asset"], user)
            tx_type = _transaction_type_for_event(event, quantity)
            try:
                with transaction.atomic():
                    created.append(
                        Transactions.objects.create(
                            investor=user,
                            account=account,
                            security=asset,
                            currency="USD",
                            type=tx_type,
                            date=event_time,
                            quantity=_normalize_model_decimal(Transactions, "quantity", quantity),
                            price=_normalize_model_decimal(Transactions, "price", price),
                            comment=_event_comment(event, leg),
                            import_provider=event.provider,
                            import_account_id=import_account_id,
                            import_event_id=event_id,
                            import_group_id=event.group_id,
                            import_event_type=event.category,
                        )
                    )
            except IntegrityError:
                continue
    return created


def _single_leg(asset, quantity, price_asset, role="base", instrument="coin"):
    """Build a one-element legs list for deposits, withdrawals, rewards, and options."""
    return [
        {
            "asset": asset,
            "quantity": quantity,
            "price": None,
            "price_asset": price_asset,
            "role": role,
            "instrument": instrument,
        }
    ]


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
        base_quantity = qty + base_fee_delta
        quote_quantity = -value + quote_fee_delta
        base_price = abs(quote_quantity / base_quantity) if base_quantity else price
        legs = [
            {
                "asset": base,
                "quantity": base_quantity,
                "price": base_price,
                "price_asset": quote,
                "role": "base",
            },
            {
                "asset": quote,
                "quantity": quote_quantity,
                "price": Decimal("1"),
                "price_asset": quote,
                "role": "quote",
            },
        ]
    elif side.lower() == "sell":
        base_quantity = -qty + base_fee_delta
        quote_quantity = value + quote_fee_delta
        base_price = abs(quote_quantity / base_quantity) if base_quantity else price
        legs = [
            {
                "asset": base,
                "quantity": base_quantity,
                "price": base_price,
                "price_asset": quote,
                "role": "base",
            },
            {
                "asset": quote,
                "quantity": quote_quantity,
                "price": Decimal("1"),
                "price_asset": quote,
                "role": "quote",
            },
        ]
    else:
        raise ValueError(f"Unsupported spot side: {side}")

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


def normalize_bybit_deposit(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    coin = payload["coin"].upper()
    amount = Decimal(payload["amount"])
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["txID"],
        group_id=payload["txID"],
        timestamp_ms=int(payload["successAt"]),
        category="deposit",
        raw_type="deposit",
        legs=_single_leg(coin, amount, coin),
    )


def normalize_bybit_withdrawal(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    coin = payload["coin"].upper()
    amount = -abs(Decimal(payload["amount"]))
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["id"],
        group_id=payload["id"],
        timestamp_ms=int(payload["createdAt"]),
        category="withdrawal",
        raw_type="withdrawal",
        legs=_single_leg(coin, amount, coin),
    )


def normalize_okx_deposit_withdrawal(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    ccy = payload["ccy"].upper()
    amount = Decimal(payload["amt"])
    direction = payload["type"].lower()
    if direction not in {"deposit", "withdrawal"}:
        raise ValueError(f"Unknown OKX asset movement type: {payload['type']}")
    signed_amount = amount if direction == "deposit" else -abs(amount)
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=f"{direction}:{payload['billId']}",
        group_id=payload["billId"],
        timestamp_ms=int(payload["ts"]),
        category=direction,
        raw_type=direction,
        legs=_single_leg(ccy, signed_amount, ccy),
    )


def normalize_bybit_reward(payload: Dict[str, Any]) -> Optional[CryptoExchangeEvent]:
    tx_type = payload.get("type", "")
    if tx_type in SKIPPED_BYBIT_INTERNAL_TRANSFER_TYPES:
        return None
    symbol = payload["symbol"].upper()
    amount = Decimal(payload["change"])
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["id"],
        group_id=payload["id"],
        timestamp_ms=int(payload["transactionTime"]),
        category="reward",
        raw_type="earn",
        legs=_single_leg(symbol, amount, symbol),
    )


def normalize_okx_reward(payload: Dict[str, Any]) -> Optional[CryptoExchangeEvent]:
    if payload.get("subType") in SKIPPED_OKX_INTERNAL_TRANSFER_SUBTYPES:
        return None
    ccy = payload["ccy"].upper()
    amount = Decimal(payload["amt"])
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=payload["billId"],
        group_id=payload["billId"],
        timestamp_ms=int(payload["ts"]),
        category="reward",
        raw_type="earn",
        legs=_single_leg(ccy, amount, ccy),
    )


def normalize_bybit_option_execution(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    symbol = payload["symbol"]
    qty = Decimal(payload["execQty"])
    price = Decimal(payload["execPrice"])
    fee_currency = payload.get("feeCurrency") or "USD"
    signed_qty = qty if payload["side"].lower() == "buy" else -qty
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["execId"],
        group_id=payload.get("orderId") or payload["execId"],
        timestamp_ms=int(payload["execTime"]),
        category="trade",
        raw_type="option_execution",
        legs=[
            {
                "asset": symbol,
                "quantity": signed_qty,
                "price": price,
                "price_asset": fee_currency,
                "role": "base",
                "instrument": "option",
            }
        ],
        fee={
            "asset": fee_currency,
            "quantity": -abs(Decimal(payload.get("execFee") or "0")),
            "is_rebate": False,
        },
    )


def normalize_okx_option_fill(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    symbol = payload["instId"]
    qty = Decimal(payload["fillSz"])
    price = Decimal(payload["fillPx"])
    fee_ccy = payload.get("feeCcy") or "USD"
    signed_qty = qty if payload["side"].lower() == "buy" else -qty
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=payload["tradeId"],
        group_id=payload.get("ordId") or payload["tradeId"],
        timestamp_ms=int(payload["fillTime"]),
        category="trade",
        raw_type="option_fill",
        legs=[
            {
                "asset": symbol,
                "quantity": signed_qty,
                "price": price,
                "price_asset": fee_ccy,
                "role": "base",
                "instrument": "option",
            }
        ],
        fee={
            "asset": fee_ccy,
            "quantity": Decimal(payload.get("fee") or "0"),
            "is_rebate": False,
        },
    )


def normalize_bybit_option_settlement(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    symbol = payload["symbol"].upper()
    amount = Decimal(payload["change"])
    settlement_price = Decimal(payload["newWalletBalance"])
    legs = _single_leg(symbol, amount, symbol)
    legs[0]["price"] = settlement_price
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["id"],
        group_id=payload.get("orderLinkId") or payload["id"],
        timestamp_ms=int(payload["transactionTime"]),
        category="settlement",
        raw_type="option_delivery",
        legs=legs,
    )


def normalize_okx_option_settlement(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    ccy = payload["settlCcy"].upper()
    amount = Decimal(payload["settlAmt"])
    settlement_price = Decimal(payload["settlPx"])
    legs = _single_leg(ccy, amount, ccy)
    legs[0]["price"] = settlement_price
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=payload["billId"],
        group_id=payload.get("ordId") or payload["billId"],
        timestamp_ms=int(payload["ts"]),
        category="settlement",
        raw_type="option_delivery",
        legs=legs,
    )


def parse_option_symbol(symbol: str) -> Dict[str, Any]:
    parts = symbol.split("-")
    if len(parts) not in (4, 5):
        raise ValueError(f"Malformed option symbol: {symbol}")

    segment_two = parts[1].upper()
    if segment_two in OPTION_SETTLEMENT_COINS:
        return _parse_okx_option_symbol(parts, symbol)
    return _parse_bybit_option_symbol(parts, symbol)


def _parse_bybit_option_symbol(parts, symbol):
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

    option_type_by_side = {"C": "CALL", "P": "PUT"}
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


def _parse_okx_option_symbol(parts, symbol):
    underlying, settlement_asset, expiry_token, strike, option_side = parts[:5]
    if len(parts) != 5:
        raise ValueError(f"OKX option symbol requires settlement segment: {symbol}")
    if not underlying or not settlement_asset:
        raise ValueError(f"Malformed option symbol: {symbol}")
    if len(expiry_token) != 6:
        raise ValueError(f"Malformed OKX option expiration: {expiry_token}")

    try:
        year = 2000 + int(expiry_token[:2])
        month = int(expiry_token[2:4])
        day = int(expiry_token[4:6])
        expiration_date = date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"Malformed OKX option expiration: {expiry_token}") from exc

    option_type_by_side = {"C": "CALL", "P": "PUT"}
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

    return {
        "underlying": underlying,
        "expiration_date": expiration_date,
        "strike_price": strike_price,
        "option_type": option_type,
        "settlement_asset": settlement_asset.upper(),
    }
