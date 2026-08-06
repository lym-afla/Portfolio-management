"""Tests for _spot_legs real-price model + embedded cross-currency fee.

The embedded multi-currency commission model (revert of spec §5.3's separate
commission row, design doc 2026-08-06):
- Trades store the REAL fill price (price comes from the CSV's fillPx, never
  folded with the fee).
- A fee whose currency is the QUOTE of a stablecoin-quote trade (same-currency)
  folds into the settlement via the persisted ``commission`` field — it does NOT
  inflate the stored price. Downstream ``total_cash_flow`` reconstructs the net
  settlement as ``-qty * price + commission``.
- Every fee (regardless of currency) attaches to the trade row's
  ``commission``/``commission_currency`` fields and is NEVER folded into a leg's
  quantity. ``services.positions.position`` is the single source of truth for
  depletion: it subtracts the signed commission from the fee-currency asset's
  holding. Folding into quantity AND subtracting via ``position()`` would
  double-count, so legs carry gross (un-netted) quantities throughout.
- A cross-currency fee (e.g. a BTC fee on a BTC-USDT trade, where BTC is the
  base and USDT is the settlement currency) does NOT become a separate leg. It
  attaches to the trade row's ``commission``/``commission_currency`` and
  ``position()`` depletes the BTC holding (+1 qty + (-0.001) commission =
  +0.999). The base leg carries the real fill price and the real (un-netted)
  quantity.
"""
from decimal import Decimal

from services.crypto_exchange import _spot_legs


def test_stablecoin_quote_buy_same_currency_fee_folds_into_settlement():
    """USDT-fee on a BTC-USDT buy: real fill price kept; fee folds via commission.

    Buy 1 BTC @ 60000 USDT, fee -10 USDT. The trader pays 60000 + 10 = 60010
    USDT (settlement = -60010). The fee is same-currency (USDT == quote), so it
    stays folded into the settlement through the persisted ``commission`` field
    (added back by ``total_cash_flow``) — it must NOT inflate the stored price.
    The stored price is the REAL fill (60000); |price * qty| = 60000 reproduces
    the principal, and ``commission`` (-10) carries the fee.
    """
    legs = _spot_legs(
        side="buy", base="BTC", quote="USDT",
        qty=Decimal("1"), price=Decimal("60000"),
        fee_delta=Decimal("-10"), fee_asset="USDT",
        quote_cash_amount=Decimal("-60010"),
    )
    # Single base leg (stablecoin-quote model) at the REAL fill price.
    assert len(legs) == 1
    assert legs[0]["asset"] == "BTC"
    assert legs[0]["quantity"] == Decimal("1")
    # Real fill price — fee is NOT folded into the price (spec §5).
    assert legs[0]["price"] == Decimal("60000")
    # No separate commission leg for any fee currency anymore.
    assert not any(leg.get("role") == "commission" for leg in legs)


def test_cross_currency_fee_attaches_to_trade_row_no_separate_leg():
    """BTC-fee on a BTC-USDT buy: NO separate leg; fee attaches to trade row.

    Buy 1 BTC @ 60000 USDT, fee -0.001 BTC. BTC is the base and USDT is the
    settlement currency, so a BTC fee is CROSS-currency relative to the USDT
    settlement. Under the embedded model the base leg carries the REAL fill
    price (60000) and the REAL quantity (1, NOT netted with the fee); there is
    NO separate commission leg. The fee attaches to the trade row's
    ``commission``/``commission_currency`` (set by
    ``persist_crypto_exchange_event`` from ``event.fee``), and ``position()``
    depletes the BTC holding (+1 qty + (-0.001) commission = +0.999).
    """
    legs = _spot_legs(
        side="buy", base="BTC", quote="USDT",
        qty=Decimal("1"), price=Decimal("60000"),
        fee_delta=Decimal("-0.001"), fee_asset="BTC",
        quote_cash_amount=Decimal("-60000"),
    )
    # Single base leg with REAL fill price (no separate commission leg).
    assert len(legs) == 1
    base_leg = legs[0]
    assert base_leg["asset"] == "BTC"
    assert base_leg["quantity"] == Decimal("1")  # NOT netted (no +fee into qty)
    assert base_leg["price"] == Decimal("60000")  # real fill price
    # No separate commission leg — the fee attaches to the trade row downstream.
    assert not any(leg.get("role") == "commission" for leg in legs)


def test_crypto_crypto_pair_keeps_two_leg_model():
    """ETH/BTC pair: two-leg model with real price; fee attaches as commission.

    Buy 1 ETH @ 0.016 BTC, fee -0.00001 BTC. Under the embedded model the fee
    is NEVER folded into a leg's quantity (that would double-count with
    ``position()``'s commission subtraction). Both legs carry gross quantities;
    the fee attaches to the base leg's ``commission``/``commission_currency``
    downstream, and ``position(btc)`` depletes the BTC holding. The base (ETH)
    leg keeps the REAL fill price (0.016). No separate commission leg.
    """
    legs = _spot_legs(
        side="buy", base="ETH", quote="BTC",
        qty=Decimal("1"), price=Decimal("0.016"),
        fee_delta=Decimal("-0.00001"), fee_asset="BTC",
    )
    base_leg = next(leg for leg in legs if leg["asset"] == "ETH" and leg.get("role") == "base")
    quote_leg = next(leg for leg in legs if leg["asset"] == "BTC" and leg.get("role") == "quote")
    assert base_leg["quantity"] == Decimal("1")
    # Real fill price on the base leg — fee is NOT folded into the price.
    assert base_leg["price"] == Decimal("0.016")
    # No separate commission leg.
    assert not any(leg.get("role") == "commission" for leg in legs)
    # Quote leg carries the GROSS principal (no fee folded in).
    assert quote_leg["quantity"] == Decimal("-0.016")
