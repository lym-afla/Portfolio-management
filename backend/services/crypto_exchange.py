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
    TRANSACTION_TYPE_CASH_IN,
    TRANSACTION_TYPE_CASH_OUT,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    TRANSACTION_TYPE_INTEREST_INCOME,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
)
from services.asset_resolver import resolve_or_create_asset

SUPPORTED_QUOTE_SUFFIXES = ("USDT", "USDC", "USD", "BTC", "ETH")
STABLECOINS = {"USDT", "USDC", "USD"}
# Stablecoin tickers that represent the user's own cash. Note that "USD" is
# intentionally excluded: it is already a fiat currency tracked as cash by other
# paths. Standalone events in USDT/USDC are re-routed to cash transactions
# (Cash in / Cash out / Interest income) rather than crypto-transfer rows that
# carry no cost basis or cash balance.
STABLECOIN_CURRENCIES = {"USDT", "USDC"}
# Event categories whose standalone stablecoin legs are re-routed to cash
# transactions. "trade" is excluded (spot-trade quote legs stay as trade legs);
# "transfer" is excluded (internal stablecoin moves stay as crypto transfers).
STABLECOIN_CASH_CATEGORIES = {"deposit", "withdrawal", "reward"}
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
    result = resolve_or_create_asset(
        user=user,
        isin=_crypto_asset_identifier(normalized_symbol),
        currency="USD",
        submitted_fields={
            "type": ASSET_TYPE_CRYPTO,
            "name": normalized_symbol,
            "ticker": normalized_symbol[:10],
            "exposure": "FX" if normalized_symbol in STABLECOINS else "Commodity",
        },
        mode="silent",
    )
    return result.asset


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
    result = resolve_or_create_asset(
        user=user,
        isin=_crypto_asset_identifier(f"OPT:{option_symbol}"),
        currency=asset_currency,
        submitted_fields={
            "type": "Option",
            "name": option_symbol,
            "ticker": option_symbol[:10],
            "exposure": "Derivatives",
        },
        mode="silent",
    )
    asset = result.asset
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


def _is_stablecoin_cash_leg(event, leg):
    """Return True for a standalone stablecoin leg that must be re-routed to cash.

    A leg qualifies when its asset is a real stablecoin (USDT/USDC — NOT USD,
    which is already fiat cash) AND the event is not a trade (so spot-trade
    quote legs stay as trade legs) AND the event category is one of the
    external cash-movement categories (deposit/withdrawal/reward). Internal
    stablecoin ``transfer`` events keep their existing crypto-transfer
    treatment.
    """
    category = (event.category or "").lower()
    if category not in STABLECOIN_CASH_CATEGORIES:
        return False
    if leg.get("instrument") == "option":
        return False
    return str(leg.get("asset", "")).upper() in STABLECOIN_CURRENCIES


def _cash_tx_type_for_category(category):
    category = (category or "").lower()
    if category == "deposit":
        return TRANSACTION_TYPE_CASH_IN
    if category == "withdrawal":
        return TRANSACTION_TYPE_CASH_OUT
    # reward / earn accruals land in interest income.
    return TRANSACTION_TYPE_INTEREST_INCOME


def persist_crypto_exchange_event(event, user, account):
    created = []
    event_time = _event_datetime(event)
    import_account_id = _account_import_id(account)
    category = (event.category or "").lower()
    leg_records = []

    with transaction.atomic():
        for index, leg in enumerate(event.legs):
            if leg.get("role") == "fee":
                continue

            quantity = _leg_quantity(leg)
            if quantity == 0:
                continue

            # Standalone stablecoin legs are cash: their value IS the quantity
            # (pegged 1:1 to USD), so no fiat price is resolved and no crypto
            # asset row is created. Trade legs and non-stablecoin legs follow
            # the existing priced-asset path.
            if _is_stablecoin_cash_leg(event, leg):
                leg_records.append((index, leg, quantity, None))
                continue

            # Transfers/deposits/withdrawals of an asset with no available fiat
            # price (e.g. a TRUMP transfer where Yahoo has no quote) must not
            # crash the whole import: persist them unpriced so the quantity
            # movement is still recorded. Trades are NOT exempt — a trade with
            # no price is a genuine error (tested above).
            if category in {"transfer", "deposit", "withdrawal"}:
                try:
                    price = _leg_fiat_price(leg, user, event_time)
                except ValueError:
                    price = None
                if price is None:
                    leg_records.append((index, leg, quantity, None))
                    continue
                leg_records.append((index, leg, quantity, price))
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

            if _is_stablecoin_cash_leg(event, leg):
                # Cash movement in the stablecoin's own currency. The signed
                # quantity (deposits/rewards positive, withdrawals negative)
                # becomes the cash_flow; security and price are not applicable.
                tx_type = _cash_tx_type_for_category(event.category)
                tx_kwargs = dict(
                    investor=user,
                    account=account,
                    security=None,
                    currency=str(leg["asset"]).upper(),
                    type=tx_type,
                    date=event_time,
                    quantity=None,
                    price=None,
                    cash_flow=_normalize_model_decimal(Transactions, "cash_flow", quantity),
                    comment=_event_comment(event, leg),
                    import_provider=event.provider,
                    import_account_id=import_account_id,
                    import_event_id=event_id,
                    import_group_id=event.group_id,
                    import_event_type=event.category,
                )
            else:
                if leg.get("instrument") == "option":
                    asset = resolve_crypto_option_asset(parse_option_symbol(leg["asset"]), user)
                else:
                    asset = resolve_crypto_asset(leg["asset"], user)
                tx_type = _transaction_type_for_event(event, quantity)
                # Stablecoin-quote spot trades carry a cash_flow (the USDT
                # spent/received). Write it so the USDT cash balance updates.
                leg_cash_flow = leg.get("cash_flow")
                tx_kwargs = dict(
                    investor=user,
                    account=account,
                    security=asset,
                    currency=str(leg.get("quote_currency") or "USD").upper(),
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
                # Trade legs no longer carry cash_flow (computed from p*q in
                # total_cash_flow) — EXCEPT option legs, whose quantity is in
                # contracts (not units), so p*q is nonsensical. Option legs
                # carry the actual underlying settlement as cash_flow. #33.
                if leg_cash_flow is not None and (category != "trade" or leg.get("instrument") == "option"):
                    tx_kwargs["cash_flow"] = _normalize_model_decimal(
                        Transactions, "cash_flow", leg_cash_flow
                    )
                if event.fee and event.fee.get("quantity") not in (None, 0, Decimal("0")):
                    tx_kwargs["commission"] = _normalize_model_decimal(
                        Transactions, "commission", event.fee["quantity"]
                    )
                    fee_ccy = str(leg.get("fee_asset") or event.fee.get("asset") or "").upper()
                    if fee_ccy:
                        tx_kwargs["commission_currency"] = fee_ccy
            try:
                with transaction.atomic():
                    created.append(Transactions.objects.create(**tx_kwargs))
            except IntegrityError:
                continue
    return created


def _single_leg(asset, quantity, price_asset, role="base", instrument="coin", price=Decimal("1")):
    """Build a one-element legs list for deposits, withdrawals, rewards, and options.

    ``price`` defaults to ``Decimal("1")`` so single-leg coin events resolve to a
    fiat price through ``_leg_fiat_price``: stablecoin legs short-circuit to 1, and
    crypto-denominated legs (BTC/ETH) hit the ``price == Decimal("1")`` branch and
    resolve via ``_quote_asset_fiat_price``. Callers that need a different price
    (option settlements) override it explicitly.
    """
    return [
        {
            "asset": asset,
            "quantity": quantity,
            "price": price,
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
    quote_cash_amount: Optional[Decimal] = None,
) -> List[Dict[str, Any]]:
    """Build the legs for a spot fill under the real-price commission model (spec §5).

    The REAL fill price is ALWAYS preserved on the base leg — it is never folded
    with the fee. Fee handling depends on the fee currency relative to the
    settlement currency (the quote):

    - SAME-currency fee (fee currency == quote): folds into the settlement
      WITHOUT touching the stored price.
        * Stablecoin-quote trade: the fee lands in the persisted ``commission``
          field (set by ``persist_crypto_exchange_event`` from ``event.fee``);
          ``total_cash_flow`` reconstructs the net settlement as
          ``-qty * price + commission``. The base leg keeps the real fill price.
        * Crypto-crypto pair: the quote is itself a priced asset, so the
          same-currency (quote) fee folds into the quote leg's quantity; the
          base leg keeps the real fill price.
    - CROSS-currency fee (fee currency is neither the base nor the quote
      relative to the settlement — e.g. a BTC fee on a BTC-USDT trade, where
      BTC is the base and USDT is the settlement): emitted as a SEPARATE
      ``role="commission"`` leg moving the fee asset's quantity. The base leg
      carries the real fill price and the real (un-netted) quantity.

    For stablecoin quotes (USDT/USDC) the trade is a SINGLE base leg (the
    stablecoin is cash, Phase 4). For crypto-crypto pairs it's the two-leg
    base+quote model.
    """
    normalized_fee_asset = (fee_asset or "").upper()
    base_u = base.upper()
    quote_u = quote.upper()
    fee_in_base = normalized_fee_asset == base_u
    fee_in_quote = normalized_fee_asset == quote_u

    if side.lower() == "buy":
        base_quantity = qty
    elif side.lower() == "sell":
        base_quantity = -qty
    else:
        raise ValueError(f"Unsupported spot side: {side}")

    if quote_u in STABLECOIN_CURRENCIES:
        # Stablecoin-quote: single base leg (stablecoin is cash). The stored
        # price is the REAL fill price — a same-currency (quote) fee is NOT
        # folded into the price; it flows through the persisted ``commission``
        # field (added back by ``total_cash_flow``). A base-asset fee here is
        # cross-currency relative to the USDT settlement and becomes a separate
        # commission leg below (NOT netted into quantity). Spec §5.5 revert.
        legs = [
            {
                "asset": base,
                "quantity": base_quantity,
                "price": price,
                "price_asset": "USD",
                "role": "base",
                "quote_currency": quote_u,
                "fee_asset": normalized_fee_asset,
            }
        ]
        # For a stablecoin-quote trade the settlement currency is the quote; a
        # fee in the quote is same-currency, anything else (base or third asset)
        # is cross-currency and becomes a separate commission leg.
        same_currency_fee = fee_in_quote
    else:
        # Crypto-crypto pair (e.g. ETH/BTC): two-leg base+quote model, real
        # prices. The quote is itself a priced asset, so a same-currency
        # (quote) fee folds into the quote leg's quantity; a base-asset fee is
        # also same-currency (it nets into the base leg's own quantity); any
        # third-asset fee is cross-currency and becomes a separate commission
        # leg below.
        value = qty * price
        quote_fee_delta = fee_delta if fee_in_quote else Decimal("0")
        base_fee_delta = fee_delta if fee_in_base else Decimal("0")

        if side.lower() == "buy":
            quote_quantity = -value + quote_fee_delta
        else:
            quote_quantity = value + quote_fee_delta
        # Real fill quantity on the base leg; a base-asset fee nets into it.
        base_quantity = base_quantity + base_fee_delta

        legs = [
            {
                "asset": base,
                "quantity": base_quantity,
                "price": price,
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
        # For a crypto-crypto pair either base- or quote-asset fee is
        # same-currency (both legs are priced assets); only a third-asset fee
        # is cross-currency.
        same_currency_fee = fee_in_base or fee_in_quote

    # Cross-currency fee: emit a separate commission leg (spec §5.3/§5.5).
    if (
        fee_delta
        and fee_delta != 0
        and not same_currency_fee
        and normalized_fee_asset
    ):
        legs.append(
            {
                "asset": normalized_fee_asset,
                "quantity": fee_delta,
                "price": Decimal("1"),
                "price_asset": normalized_fee_asset,
                "role": "commission",
                "instrument": "coin",
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
    quote_cash_amount_str = payload.get("quoteCashAmount")
    quote_cash_amount = Decimal(quote_cash_amount_str) if quote_cash_amount_str else None

    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=payload["tradeId"],
        group_id=payload.get("ordId") or payload["tradeId"],
        timestamp_ms=int(payload["fillTime"]),
        category="trade",
        raw_type="spot_fill",
        legs=_spot_legs(payload["side"], base, quote, qty, price, fee_delta, fee_asset, quote_cash_amount),
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
        provider_event_id=payload["withdrawId"],
        group_id=payload["withdrawId"],
        timestamp_ms=int(payload["createTime"]),
        category="withdrawal",
        raw_type="withdrawal",
        legs=_single_leg(coin, amount, coin),
    )


def normalize_okx_deposit(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    # OKX deposit-history (``/api/v5/asset/deposit-history``) returns ``depId``
    # as the per-row id. The delivered amount is unsigned in the payload; deposits
    # are always inbound so the signed leg quantity is positive.
    ccy = payload["ccy"].upper()
    amount = Decimal(payload["amt"])
    dep_id = payload["depId"]
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=f"deposit:{dep_id}",
        group_id=dep_id,
        timestamp_ms=int(payload["ts"]),
        category="deposit",
        raw_type="deposit",
        legs=_single_leg(ccy, amount, ccy),
    )


def normalize_okx_withdrawal(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    # OKX withdrawal-history (``/api/v5/asset/withdrawal-history``) returns
    # ``wdId`` as the per-row id. The amount is unsigned in the payload;
    # withdrawals are always outbound so the signed leg quantity is negative.
    ccy = payload["ccy"].upper()
    amount = -abs(Decimal(payload["amt"]))
    wd_id = payload.get("wdId") or payload.get("clientId") or payload["ts"]
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=f"withdrawal:{wd_id}",
        group_id=wd_id,
        timestamp_ms=int(payload["ts"]),
        category="withdrawal",
        raw_type="withdrawal",
        legs=_single_leg(ccy, amount, ccy),
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
    # The earn-lending endpoint (``/api/v5/finance/savings/lending-history``) does
    # not return a per-row id; ``ts`` is the millisecond accrual timestamp and is
    # unique per row in practice, so it stands in as the event id. The
    # ``subType`` filter is checked defensively (``.get``) because real
    # earn-lending rows do not carry that key, but bills-style payloads routed
    # through this normalizer may.
    if payload.get("subType") in SKIPPED_OKX_INTERNAL_TRANSFER_SUBTYPES:
        return None
    ccy = payload["ccy"].upper()
    amount = Decimal(payload["amt"])
    ts = payload["ts"]
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=f"earn:{ts}",
        group_id=ts,
        timestamp_ms=int(ts),
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
                # The BTC settlement (from the CSV's Balance Change) — persisted
                # as cash_flow so total_cash_flow reads it directly instead of
                # computing the nonsensical contracts × underlying_price. #33.
                "cash_flow": Decimal(payload["cashFlow"]) if payload.get("cashFlow") else None,
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
    # The settlement price is the underlying's price at expiry — already fiat.
    # Set price_asset to "USD" so _leg_fiat_price passes it through without
    # multiplying by the BTC/USD rate again.
    legs = _single_leg(symbol, amount, "USD")
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
    # Real source is ``/api/v5/account/bills-archive`` filtered to
    # ``instType=OPTION``. Settlement rows carry the delivered coin in ``ccy``,
    # the signed delivered amount in ``balChg`` (already signed — passed
    # through unchanged), and the settlement price in ``px``. There is no
    # ``settlCcy``/``settlAmt``/``settlPx``.
    ccy = payload["ccy"].upper()
    amount = Decimal(payload["balChg"])
    settlement_price = Decimal(payload["px"])
    # The settlement price (px) is the underlying's USD price at expiry —
    # already fiat. Set price_asset to "USD" so _leg_fiat_price passes it
    # through without multiplying by the BTC/USD rate again.
    legs = _single_leg(ccy, amount, "USD")
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
