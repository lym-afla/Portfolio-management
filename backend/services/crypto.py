"""Crypto-class helpers — what is a crypto coin and what's it worth.

Crypto coins are ``Assets`` rows with ``type="Crypto"`` (see spec §4.1). This
module is the rigorous class boundary: it centralizes every "is this crypto?"
check and every "what's this coin worth in USD / target currency" lookup so
the rest of the codebase never branches on ``type == "Crypto"`` ad hoc.

Coins are USD-priced by convention (``Assets.currency == "USD"`` for crypto);
the USD price lives in the ``Prices`` table. FX conversion to a non-USD target
chains through the existing fiat FX graph (spec §4.5, decision 2a).

Numeric safety: ``Decimal`` everywhere. Never ``float``.
"""

import logging
from decimal import Decimal
from typing import Optional

from common.models import Assets, Prices

logger = logging.getLogger(__name__)


def is_crypto(asset) -> bool:
    """Return True iff ``asset`` is a Crypto-class instrument."""
    return getattr(asset, "type", None) == "Crypto"


def is_crypto_code(code: str, date_as_of=None) -> bool:
    """Return True iff a Crypto-class ``Assets`` row exists for ``code``.

    ``code`` is the coin symbol (e.g. ``"BTC"``). The asset's ISIN follows the
    ``CRYPTO:<code>`` convention (see ``_crypto_asset_identifier`` in
    ``services.crypto_exchange``); we resolve both the direct and hashed forms
    by matching the asset's ``name`` (the coin symbol) for robustness.
    """
    if not code:
        return False
    symbol = str(code).upper().strip()
    return Assets.objects.filter(type="Crypto", name=symbol).exists()


def crypto_usd_price(code: str, date_as_of, investor=None) -> Decimal:
    """Return the USD price of ``code`` on/before ``date_as_of``.

    Sources the latest ``Prices`` row for the coin on or before the date.
    Raises ``ValueError`` when no price is available (the coin is unpriced).
    """
    symbol = str(code).upper().strip()
    asset = Assets.objects.filter(type="Crypto", name=symbol).first()
    if asset is None:
        raise ValueError(f"No crypto asset for code {code}")
    quote = (
        Prices.objects.filter(security=asset, date__lte=date_as_of).order_by("-date").first()
    )
    if quote is None:
        raise ValueError(f"No USD price for {code} on or before {date_as_of}")
    return Decimal(quote.price)


def crypto_fx_rate(code: str, target: str, date_as_of, investor=None) -> Decimal:
    """Return the 'multiply ``code`` -> ``target``' FX rate for a crypto coin.

    Resolves ``code -> USD`` from the coin's ``Prices`` row (the BTC-USD price
    IS the BTC->USD rate), then ``USD -> target`` via the existing fiat FX
    graph. For ``target == "USD"`` the price itself is returned (no graph hop).
    """
    target = (target or "").upper().strip()
    code = (code or "").upper().strip()
    if code == target:
        return Decimal("1")

    usd_price = crypto_usd_price(code, date_as_of, investor)
    if target == "USD":
        return usd_price

    # Lazy import avoids a circular load (services.fx imports common.models at
    # top level; this module imports common.models at top level — safe either
    # way, but the lazy form keeps the dependency direction explicit).
    from services.fx import get_rate as fx_get_rate

    usd_to_target = fx_get_rate("USD", target, date_as_of, investor)["FX"]
    return (usd_price * usd_to_target).quantize(Decimal("0.000001"))


def crypto_usd_price_with_fallback(code: str, date_as_of, investor=None) -> Optional[Decimal]:
    """Resolve a coin's USD price, falling back to the last transaction price.

    Tier 1: latest ``Prices`` row on/before ``date_as_of`` (the live market
    price) — via ``crypto_usd_price``.
    Tier 2: the asset's most recent ``Crypto trade in/out`` price (as USD),
    if that trade's currency is USD/USDT/USDC, or convertible via FX.
    Tier 3: ``None`` (unpriced — caller skips with warning).
    """
    # Tier 1
    try:
        return crypto_usd_price(code, date_as_of, investor)
    except ValueError:
        pass
    # Tier 2: last transaction price
    from common.models import Transactions
    from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN, TRANSACTION_TYPE_CRYPTO_TRADE_OUT
    asset = Assets.objects.filter(type="Crypto", name=str(code).upper().strip()).first()
    if asset is None:
        return None
    last_trade = (
        Transactions.objects.filter(
            security=asset, investor=investor,
            type__in=[TRANSACTION_TYPE_CRYPTO_TRADE_IN, TRANSACTION_TYPE_CRYPTO_TRADE_OUT],
            price__isnull=False,
            date__date__lte=date_as_of,
        ).order_by("-date", "-id").first()
    )
    if last_trade is None or last_trade.price in (None, 0):
        return None
    if (last_trade.currency or "").upper() in ("USD", "USDT", "USDC"):
        return Decimal(last_trade.price)
    try:
        from services.fx import get_rate
        return Decimal(last_trade.price) * get_rate(last_trade.currency, "USD", last_trade.date)["FX"]
    except ValueError:
        return None


def safe_crypto_fx_rate(code: str, target: str, date_as_of, investor=None) -> Optional[Decimal]:
    """Like ``crypto_fx_rate``, but returns ``None`` (with a warning) when the
    coin is unpriced (both market and last-trade fallbacks miss), instead of
    raising ``ValueError``.

    Callers that need graceful degradation (realized/IRR/tables) use this;
    strict callers (NAV spot-crypto, which has its own try/except) keep
    ``crypto_fx_rate``.
    """
    code = (code or "").upper().strip()
    target = (target or "").upper().strip()
    if code == target:
        return Decimal("1")
    try:
        return crypto_fx_rate(code, target, date_as_of, investor)
    except ValueError:
        usd_price = crypto_usd_price_with_fallback(code, date_as_of, investor)
        if usd_price is None:
            logger.warning(
                "No USD price for %s on or before %s (market + last-trade) — skipping",
                code, date_as_of,
            )
            return None
        logger.info("Using last-trade price for %s as of %s", code, date_as_of)
        if target == "USD":
            return usd_price
        try:
            from services.fx import get_rate
            return (usd_price * get_rate("USD", target, date_as_of)["FX"]).quantize(
                Decimal("0.000001")
            )
        except ValueError:
            return None
