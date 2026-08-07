"""Option-economics helpers (sub-project 4 of the crypto-modeling program).

Centralizes every option-calculation concern so the importer and the calc
layers (realized / NAV) never branch on ``type == "Option"`` or recompute
premium/intrinsic ad hoc. Mirrors the role of ``services/crypto.py`` for the
crypto class.

All money/price math uses Decimal (per AGENTS.md numeric-safety rules).

Conventions for OKX/Bybit crypto options (the only options this module
serves today):
  - USD-strike, coin-settled (inverse style). Premium and payout settle in
    the underlying coin (BTC for BTC-USD options), read from the CSV's
    ``Balance Unit`` — never defaulted.
  - European cash-settled at expiry.
  - ``contract_size`` scales one contract to its coin notional (0.01 BTC for
    BTC options, 0.1 ETH for ETH options).
"""
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from common.models import Assets, Prices
from constants import ASSET_TYPE_OPTION

logger = logging.getLogger(__name__)


# OKX/Bybit option contract sizes by underlying coin (coin notional per contract).
# Add entries here as new underlyings are supported.
OKX_CONTRACT_SIZES = {
    "BTC": Decimal("0.01"),
    "ETH": Decimal("0.1"),
}


def is_option_asset(asset) -> bool:
    """Return True when the asset is an option contract (type == "Option")."""
    return getattr(asset, "type", None) == ASSET_TYPE_OPTION


def contract_size_for_underlying(coin_code: str) -> Decimal:
    """Return the OKX/Bybit option contract size for the underlying coin.

    BTC -> 0.01, ETH -> 0.1. Unknown coins default to Decimal("1") with a
    warning (so the import does not crash, but the basis math is flagged as
    approximate until the size is confirmed and added to the table).
    """
    key = (coin_code or "").upper()
    size = OKX_CONTRACT_SIZES.get(key)
    if size is None:
        logger.warning(
            "Unknown option underlying %r; defaulting contract_size to 1.0 "
            "(add it to options.OKX_CONTRACT_SIZES when confirmed).",
            coin_code,
        )
        return Decimal("1")
    return size


def gross_premium(quantity: Decimal, fill_price: Decimal, contract_size: Decimal) -> Decimal:
    """Return the gross option premium = quantity × fill_price × contract_size.

    Unsigned magnitude. Sign (received for sell / paid for buy) is applied by
    the caller when storing on the transaction row.
    """
    return Decimal(quantity) * Decimal(fill_price) * Decimal(contract_size)


def intrinsic_price(option_meta, spot: Decimal, contract_size: Decimal) -> Decimal:
    """Per-contract intrinsic value at expiry, in the settlement coin.

    For USD-strike / coin-settled options (OKX/Bybit crypto style):
        call = contract_size × max(spot − strike, 0) / spot
        put  = contract_size × max(strike − spot, 0) / spot
    ``contract_size`` scales one contract to its coin notional; ``/ spot``
    converts the USD-denominated intrinsic into the settlement coin.

    Returns 0 when OTM (or exactly at strike). Raises ``ValueError`` when
    strike/option_type is missing (cannot compute intrinsic).
    """
    strike = getattr(option_meta, "strike_price", None)
    option_type = getattr(option_meta, "option_type", None)
    if strike is None or option_type is None:
        raise ValueError(
            "OptionMetadata missing strike_price/option_type; cannot compute intrinsic"
        )
    spot = Decimal(spot)
    if spot == 0:
        return Decimal(0)
    if option_type == "CALL":
        usd_intrinsic = (Decimal(contract_size)
                         * max(spot - Decimal(strike), Decimal(0)))
    elif option_type == "PUT":
        usd_intrinsic = (Decimal(contract_size)
                         * max(Decimal(strike) - spot, Decimal(0)))
    else:
        raise ValueError(f"Unknown option_type {option_type!r}")
    # Convert USD intrinsic to settlement coin via the spot price.
    return (usd_intrinsic / spot).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def option_mark_for_nav(option_asset, date, investor=None) -> Optional[Decimal]:
    """Return the manual MTM mark for an option at ``date`` if a Prices row exists.

    NAV policy (spec §5.4): a short option is valued at entry cost (premium)
    by default — NAV-neutral at open. If the user has entered a manual option
    price into the Prices table, NAV marks to it instead (on-demand MTM).
    Returns None when no Prices row exists; the caller falls back to entry cost.
    """
    from services.pricing import price_at_date as _price_at_date
    try:
        return _price_at_date(option_asset, date, investor=investor)
    except (ValueError, TypeError):
        return None


def derive_collateral(
    *, balance_change_signed: Decimal, premium: Decimal, fee_signed: Decimal
) -> Decimal:
    """Derive the SELL-leg collateral magnitude from the CSV's signed balance change.

    For an option SELL, the OKX Balance Change decomposes as:
        BC_sell = +premium + fee_signed − collateral
    where ``fee_signed`` is the CSV's signed fee (a negative number, since fees
    are outflows). Solving for the (non-negative) collateral magnitude:
        collateral = premium + fee_signed − BC_signed

    This helper is meaningful for SELL legs only — writers post collateral;
    option buyers pay premium and post no collateral (collateral = 0 for buys
    is handled by the caller, e.g. ``decompose_option_fill``).

    Returns the non-negative collateral magnitude, quantized to 8 dp.
    """
    bc = Decimal(balance_change_signed)
    prem = Decimal(premium)
    fee = Decimal(fee_signed)
    # BC_sell = +premium + fee_signed − collateral  →  collateral = premium + fee_signed − BC
    collateral = prem + fee - bc
    # collateral is a magnitude; clamp to >= 0 (a sell with no collateral -> 0).
    if collateral < 0:
        collateral = Decimal(0)
    return collateral.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def decompose_option_fill(
    *,
    side: str,
    fill_qty: Decimal,
    fill_price: Decimal,
    fee: Decimal,
    fee_ccy: str,
    settle_ccy: str,
    underlying: str,
    balance_change_signed: Decimal,
) -> dict:
    """Decompose an OKX/Bybit option fill into a single option leg's fields.

    Returns a dict ready for the normalizer to assemble into a leg:
      quantity      = signed contracts (sell -> negative, buy -> positive)
      price         = real fill price per contract (in settle_ccy)
      currency      = settle_ccy (from CSV Balance Unit, never defaulted)
      cash_flow     = signed premium (+ received for sell / - paid for buy)
      commission    = fee (signed, as-is from CSV)
      commission_currency = fee_ccy
      contract_size = per-underlying size
      collateral    = non-negative magnitude (for the comment, NOT a leg)

    Sign convention (spec §3.3):
      SELL -> writer RECEIVES premium (cash_flow POSITIVE), qty NEGATIVE.
      BUY  -> buyer PAYS premium   (cash_flow NEGATIVE), qty POSITIVE.

    Collateral is SELL-only — option writers post collateral, buyers do not.
    For a BUY this returns ``collateral = Decimal(0)``; ``derive_collateral`` is
    NOT called for buys (it is meaningful only on the sell-side decomposition
    ``BC_sell = +premium + fee_signed - collateral``). The collateral is
    recorded in the transaction's comment by the importer; it does NOT become a
    position leg (spec §3.3 — avoids NAV step-changes).
    """
    csize = contract_size_for_underlying(underlying)
    qty = Decimal(fill_qty)
    prem = gross_premium(qty, Decimal(fill_price), csize)
    is_sell = (side or "").lower() == "sell"
    signed_qty = -qty if is_sell else qty
    signed_premium = prem if is_sell else -prem
    collateral = (
        derive_collateral(
            balance_change_signed=Decimal(balance_change_signed),
            premium=prem,
            fee_signed=Decimal(fee),
        )
        if is_sell
        else Decimal(0)
    )
    return {
        "quantity": signed_qty,
        "price": Decimal(fill_price),
        "currency": str(settle_ccy).upper(),
        "cash_flow": signed_premium,
        "commission": Decimal(fee),
        "commission_currency": str(fee_ccy).upper(),
        "contract_size": csize,
        "collateral": collateral,
    }
