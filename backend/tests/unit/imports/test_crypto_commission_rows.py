"""Tests for _spot_legs real-price model + separate commission rows (spec §5).

The reverted model (spec §5.3 / §5.5, design doc 2026-08-06):
- Trades store the REAL fill price (price comes from the CSV's fillPx, never
  folded with the fee).
- A fee whose currency is the QUOTE of a stablecoin-quote trade (same-currency)
  folds into the settlement via the persisted ``commission`` field — it does NOT
  inflate the stored price. Downstream ``total_cash_flow`` reconstructs the net
  settlement as ``-qty * price + commission``.
- A fee whose currency is the QUOTE of a crypto-crypto pair (same-currency)
  folds into the quote leg's quantity (the quote is itself a priced asset here,
  not cash), again leaving the base price at the real fill.
- A fee whose currency is NEITHER base NOR quote relative to the settlement
  (cross-currency — e.g. a BTC fee on a BTC-USDT trade, where BTC is the base
  and USDT is the settlement currency) becomes a SEPARATE ``role="commission"``
  leg.

NOTE on brief deviations: the task-5 brief's test expectations and the brief's
implementation both still folded the fee into the derived price (effective price
60010/60020 for the stablecoin case, and a fee-adjusted base price for the
crypto-crypto case), and its ``is_same_currency_fee`` predicate treated a
base-asset fee on a stablecoin-quote trade as same-currency. Those contradict
spec §5 ("real fill price") and §5.3 ("cross-currency commissions are separate
rows"). The expectations below follow the spec; see task-5-report.md for the
full hand-trace.
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
    # No separate commission leg for same-currency fee.
    assert not any(leg.get("role") == "commission" for leg in legs)


def test_cross_currency_fee_emits_separate_commission_leg():
    """BTC-fee on a BTC-USDT buy: fee is a separate BTC commission leg, real price kept.

    Buy 1 BTC @ 60000 USDT, fee -0.001 BTC. BTC is the base and USDT is the
    settlement currency, so a BTC fee is CROSS-currency relative to the USDT
    settlement. The base leg carries the REAL fill price (60000) and the REAL
    quantity (1, NOT netted with the fee); the fee becomes its own commission leg.
    """
    legs = _spot_legs(
        side="buy", base="BTC", quote="USDT",
        qty=Decimal("1"), price=Decimal("60000"),
        fee_delta=Decimal("-0.001"), fee_asset="BTC",
        quote_cash_amount=Decimal("-60000"),
    )
    # Base leg with REAL fill price (not adjusted for the cross-currency fee).
    base_leg = next(leg for leg in legs if leg.get("role") != "commission" and leg["asset"] == "BTC")
    assert base_leg["quantity"] == Decimal("1")  # NOT netted (no +fee into qty)
    assert base_leg["price"] == Decimal("60000")  # real fill price

    # Separate commission leg in BTC (the cross-currency fee asset).
    commission_leg = next(leg for leg in legs if leg.get("role") == "commission")
    assert commission_leg["asset"] == "BTC"
    assert commission_leg["quantity"] == Decimal("-0.001")
    assert commission_leg["instrument"] == "coin"


def test_crypto_crypto_pair_keeps_two_leg_model():
    """ETH/BTC pair: two-leg model with real price; BTC-fee folds into quote qty.

    Buy 1 ETH @ 0.016 BTC, fee -0.00001 BTC. BTC is the QUOTE here, so the BTC
    fee is same-currency and folds into the BTC quote leg's quantity (BTC is a
    priced asset in a crypto-crypto pair, not cash). The base (ETH) leg keeps
    the REAL fill price (0.016). No separate commission leg.
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
    # BTC is the quote, so the BTC fee folds into the quote settlement quantity.
    assert not any(leg.get("role") == "commission" for leg in legs)
    # Quote leg settlement includes the fee (principal + fee both leave the account).
    assert quote_leg["quantity"] == Decimal("-0.016") + Decimal("-0.00001")
