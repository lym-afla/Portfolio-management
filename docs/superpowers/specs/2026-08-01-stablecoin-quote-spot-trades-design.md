# Stablecoin-Quote Spot Trades as Single Transactions — Design

**Date:** 2026-08-01
**Status:** Approved (brainstorming complete)
**Depends on:** Stablecoins-as-currency (Phases 1-5, all merged)

## Problem

When a BTC/USDT spot trade is imported, the current code creates TWO transactions:
1. `Crypto trade in` on `CRYPTO:BTC` (the base leg) — quantity, fee-adjusted price.
2. `Crypto trade out` on `CRYPTO:USDT` (the quote leg) — USDT quantity at price 1.

This is wrong now that USDT is a currency (not an asset). It causes:
- USDT showing as a position in open-positions (the `CRYPTO:USDT` asset).
- USDT cash balance not decreasing after BTC purchases (the quote leg is `Crypto trade out`, not `Cash out`).
- The displayed price being fee-inflated (effective price, not the actual fill price).
- Two rows per trade in the transactions table instead of one.

## Design

When the quote currency of a spot trade is a stablecoin (`USDT`/`USDC`), `_spot_legs` emits **ONE leg** (the base asset). The quote-side USDT becomes the transaction's `cash_flow`. Crypto-crypto pairs (e.g. ETH/BTC) are unchanged — they keep the two-leg model.

### `_spot_legs` changes (`services/crypto_exchange.py`)

Add a check at the top: if `quote in STABLECOIN_CURRENCIES`, return a single base leg with:
- `asset`: the base (e.g. "BTC")
- `quantity`: the actual fill quantity (`qty`), signed by side (positive for buy, negative for sell). NOT fee-adjusted.
- `price`: the actual fill price from the exchange (`price` parameter). NOT the fee-adjusted effective price.
- `price_asset`: "USD" (the price is already fiat — USDT ≈ USD at 1.0).
- `role`: "base"
- `cash_flow`: the total USDT spent/received, signed (negative for buy = cash out, positive for sell = cash in). Computed as `qty * price + fee_in_quote_terms` (the fee converted to USDT at the fill price if it was paid in the base asset).

For the `cash_flow` computation:
- Buy: `cash_flow = -(qty * price + abs(fee_delta) * price_if_fee_in_base)` — total USDT leaving the account.
- Sell: `cash_flow = +(qty * price - abs(fee_delta) * price_if_fee_in_base)` — total USDT received minus fee.

If the fee was paid in the quote currency (USDT): `fee_in_quote = fee_delta`. If paid in base (BTC): `fee_in_quote = abs(fee_delta) * price`. This preserves the total cost.

### `persist_crypto_exchange_event` changes

For legs that carry a `cash_flow` field (from the stablecoin-quote path):
- Write `cash_flow` to the `Transactions` row alongside `quantity` and `price`.
- The `currency` is "USD" (the base asset's currency, matching existing behavior).
- The `type` is `Crypto trade in/out` (existing mapping, unchanged).
- `_normalize_model_decimal` is applied to `cash_flow` (it's a `DecimalField(10,2)` — same precision as other cash flows).

For legs WITHOUT `cash_flow` (crypto-crypto pairs, standalone events): existing behavior unchanged.

### Fee handling

The fee is NOT baked into the price or quantity. Instead:
- The `comment` field shows the fee details (already present via `_event_comment`: `fee_asset=BTC; fee_quantity=-0.00006685`).
- The fee's cost IS included in `cash_flow` (the total USDT spent accounts for the fee).
- The `quantity` is the actual fill quantity (e.g. 0.06684041 BTC, not 0.06677356 after fee deduction).
- The `price` is the actual fill price (e.g. 74,837.4, not the fee-inflated 74,912.31).

### What this fixes

- **USDT cash balance decreases after BTC purchases**: the `cash_flow` on the buy transaction reduces the USDT currency balance via `total_cash_flow`.
- **No `CRYPTO:USDT` asset created**: the quote leg no longer exists, so `resolve_crypto_asset("USDT")` is never called for spot trades.
- **Transactions table shows one row per trade**: "Crypto trade in 0.0668 BTC @$74,837.40" with the cash_flow visible.
- **Actual fill price displayed**: not the fee-inflated effective price.

## Scope

**Changed:** `services/crypto_exchange.py` (`_spot_legs`, `persist_crypto_exchange_event`).
**Unchanged:** all calc code, all other normalizers, all other services, no schema/migration.
**Tests:** update existing two-leg spot trade tests to assert single-leg for stablecoin quotes; keep two-leg tests for crypto-crypto quotes.
**Data cleanup:** delete existing OKX transactions + the re-created `CRYPTO:USDT` asset; re-import with the new code.

## Out of scope

- Crypto-crypto pairs (ETH/BTC) — unchanged, still two-leg.
- The `calculate_buy_in_price` None issue for non-stablecoin crypto with no buy trades — separate follow-up.
- Historical price display in the transactions table (whether to show "$74,837.40" or "74,837.40 USDT") — cosmetic; the value is correct via the 1.0 peg.
