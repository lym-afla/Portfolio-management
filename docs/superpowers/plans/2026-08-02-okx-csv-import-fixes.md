# OKX CSV Import — 8 Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix 8 issues identified during live testing of the OKX Trading History CSV import.

**Architecture:** Changes span the CSV adapter (`services/importer.py`), the crypto normalizers/persistence (`services/crypto_exchange.py`), the display layer (`core/formatting_utils.py`, frontend), and the option settlement handling.

## Global Constraints
- `Decimal` only. NO schema/migration changes. NO changes to `common/models.py` or calc-layer services.

---

## Task 1: Include stablecoin transfers as Cash in/out

**Problem:** Transfers (funding↔trading account) are skipped. The first USDT `Transfer in` (357.14) is the initial cash deposit and must be imported.

**Files:** `services/importer.py` (the CSV adapter/parsing logic)

**Change:** In the CSV adapter, for rows with `Trade Type=Transfer`:
- If `Action=Transfer in` AND the currency (from `Balance Unit`) is a stablecoin (USDT/USDC): create a `Cash in` event. `provider_event_id = "csv_transfer_in:{id}"`, `cash_flow = +Amount`, `currency = Balance Unit`.
- If `Action=Transfer out` AND stablecoin: create a `Cash out` event. `cash_flow = -Amount`.
- If non-stablecoin (BTC/ETH transfers to funding for staking): still skip (these are internal asset moves, not cash).
- Use `_single_leg` + a synthetic `CryptoExchangeEvent` with `category="deposit"` (for Cash in) or `category="withdrawal"` (for Cash out), so the existing stablecoin-cash routing in `persist_crypto_exchange_event` handles it.

**Note:** The CSV's `Transfer in` rows show `Amount=0` with the actual amount in `Balance Change`. Parse from `Balance Change` (signed: positive for in, negative for out), not `Amount`.

---

## Task 2: USDT↔USDC conversion as FX transaction

**Problem:** `USDC-USDT-CONVERT` trades are skipped. They should be FX transactions (currency conversion), not spot trades.

**Files:** `services/importer.py` (CSV adapter), possibly `services/crypto_exchange.py` if a new event type is needed.

**Change:** In the CSV adapter, detect `*-CONVERT` symbols:
- Parse the two currencies from the symbol (e.g. `USDC-USDT-CONVERT` → from=USDC, to=USDT).
- Yield a status dict that creates an `FXTransaction` (not a `Transactions` row) via the existing `save_single_transaction` path — OR skip the crypto-event pipeline entirely and yield a raw `transaction_data` dict with `type="FX"` fields. The existing `FXTransaction` model has `from_currency`, `to_currency`, `from_amount`, `to_amount`, `rate`.
- Use the two CSV rows (one per side, same `Order id`) to get the amounts: `from_amount` from one leg, `to_amount` from the other, `rate = Filled Price`.

---

## Task 3: Fix currency display (USDC shown as USD)

**Problem:** Stablecoin-quote trades show `currency="USD"` instead of the actual stablecoin code.

**Files:** `services/crypto_exchange.py` (`persist_crypto_exchange_event`)

**Change:** The `currency` field on the transaction should be the actual quote currency (USDT, USDC), not "USD". The persist code currently sets `currency=leg_currency if leg_cash_flow is not None else "USD"` — verify `leg_currency` (from `leg.get("quote_currency", "USD")`) is correctly propagated from the CSV adapter. If the CSV adapter doesn't set `quote_currency` on the leg, add it.

---

## Task 4: Use Buy/Sell types for stablecoin-quote trades, Crypto trade for crypto-crypto

**Problem:** All spot trades are `Crypto trade in/out`. Stablecoin-quote trades should be `Buy`/`Sell` (since they behave like cash purchases). Crypto-crypto pairs keep `Crypto trade in/out`.

**Files:** `services/crypto_exchange.py` (`_transaction_type_for_event` or the persist branch)

**Change:** For stablecoin-quote single-leg trades (where `cash_flow` is set), the transaction type should be `TRANSACTION_TYPE_BUY` (for positive quantity) or `TRANSACTION_TYPE_SELL` (for negative), NOT `Crypto trade in/out`. This makes them display and behave like stock purchases. For crypto-crypto pairs (two-leg), keep `Crypto trade in/out`.

---

## Task 5: Transaction display format (Buy/Sell + asset link + fee)

**Problem:** Crypto trades don't display in the "Buy 0.7 @$73.2 of TRUMP" format with fee and asset links.

**Files:** `frontend/src/components/transactions/TransactionDescription.vue` (or similar), `frontend/src/components/transactions/TransactionRow.vue`

**Change:** This may already work if Task 4 changes the type to `Buy`/`Sell` — the existing transaction-description component likely has a format for `Buy`/`Sell` that includes quantity, price, and asset name with a link. Verify by reading the component. If the `Buy`/`Sell` format exists, this is automatically fixed by Task 4. If not, add crypto-asset support to the description component.

---

## Task 6: Fees missing from CSV import

**Problem:** The `commission` field is None despite the CSV having Fee/Fee Unit columns.

**Files:** `services/importer.py` (CSV adapter)

**Change:** The adapter maps CSV `Fee` and `Fee Unit` to the payload's `fee`/`feeCcy` fields. Verify the adapter correctly extracts the fee value (it may be on the base leg or the quote leg — check both rows in the pair). The `persist_crypto_exchange_event` code should write it to the `commission` field. Trace the fee from CSV → payload → normalizer → event → persist → transaction row and fix the broken link.

---

## Task 7: Decimal places in transaction display

**Problem:** Quantities should show: if >1, use global digits setting; if <1, show first significant digit.

**Files:** `frontend/src/composables/` or `frontend/src/utils/` (number formatting)

**Change:** Frontend formatting function. For the quantity display in transaction descriptions: if `abs(qty) >= 1`, format with the user's `digits` setting; if `abs(qty) < 1`, format with `toPrecision(1)` or equivalent (show the first significant digit: 0.6803 → "0.7", 0.00011659 → "0.0001"). This is a display-only change.

---

## Task 8: Options mechanics analysis

**Problem:** The user sold a BTC call, OKX blocked collateral, at expiry the collateral was released. The premium is missing from the import.

**Files:** Analysis only first, then fix.

**Analysis from the CSV:**
- `2026-05-27`: Sell 7 contracts of `BTC-USD-260605-80000-C` at `0.0022` (premium in BTC). `Balance Change: -0.00701889 BTC` — this is the NET after OKX's margin/collateral blocking. `Fee: -0.00001078 BTC`.
- `2026-06-05`: `Expired OTM` (the call expired worthless since BTC was at $62,703, below the $80,000 strike). `Position Change: -0.00716211 BTC`, `Balance Change: +0.00716211 BTC` — the collateral was RELEASED back.

**What actually happened:** The user SOLD a call (collected premium). OKX blocked some BTC as margin. At expiry (OTM), the option expired worthless, the premium was already received, and the margin was released. The CSV shows the balance changes but NOT the premium receipt explicitly — it's embedded in the `Balance Change` of the sell row.

**The CSV row for the sell:**
- `Amount=7, Filled Price=0.0022, Balance Change=-0.00701889 BTC`
- The premium received = `7 × 0.0022 = 0.0154 BTC` (7 contracts at 0.0022 BTC each).
- The `Balance Change=-0.00702` suggests OKX blocked ~0.0154 BTC premium minus fees plus some margin, netting to -0.00702 outflow.

**Fix approach:** The option SELL should be imported as a crypto trade (selling the option contract). The option EXPIRATION should import the collateral release. The `normalize_okx_option_settlement` already handles the bills-archive shape — verify it maps the CSV's `Position Change` → `balChg` correctly. The premium trade should use `normalize_okx_option_fill` with `side=sell`.

**Key concern:** the CSV's option rows have a different structure than the API's bills-archive. The CSV has `Symbol=BTC-USD-260605-80000-C`, `Action=Sell`, `Amount=7`, `Filled Price=0.0022` for the trade, and `Action=Expired OTM`, `Position Change=-0.00716211` for the settlement. The adapter needs to handle these differently.

---

## Sequencing

| Task | Risk | Depends on |
|---|---|---|
| 1 (transfers) | Low | nothing |
| 3 (currency fix) | Low | nothing |
| 6 (fees) | Low | nothing |
| 4 (Buy/Sell types) | Medium | 3 |
| 2 (FX for CONVERT) | Medium | nothing |
| 5 (display format) | Low | 4 |
| 7 (decimal places) | Low | nothing (frontend) |
| 8 (options) | High | analysis first |
