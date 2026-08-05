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
from datetime import date, datetime
from decimal import Decimal

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
