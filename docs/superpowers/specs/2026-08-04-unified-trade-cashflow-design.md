# Unified Trade Cash-Flow Model — Design

**Date:** 2026-08-04
**Status:** In design (brainstorming complete, awaiting plan)
**Branch:** `fix/unified-effective-price`

## Problem

Crypto trade rows currently store `price`, `quantity`, AND `cash_flow` — three independent values that different calc consumers read differently (`total_cash_flow` reads `cash_flow`; `get_economic_basis` reads `quantity × price`; `nav.py` reads `-quantity × price`). This creates ambiguity: which is the source of truth? When `p × q != cash_flow` (due to fee netting, approximate CONVERT rates, or Decimal multiplication noise), the consumers disagree, producing silent inconsistencies in balance, NAV, and realized gains.

## The unified model

**One invariant for all trade rows:**
```
price × quantity == |settlement|   (the exact CSV/API quote-currency amount)
```
when the commission is in a different currency (base-asset fee), OR:
```
price × quantity - commission == |settlement|
```
when the commission is in the same currency (quote-asset fee).

`cash_flow` is **removed from trade rows** (NULL). It remains on non-trade rows (Cash in/out, Dividends, Interest, etc.).

### Commission sign convention
`commission` is stored **negative** for a cost/fee (matching the model docstring: "negative for outflow"). The `commission_currency` field (added in PR #31) records the fee's native asset.

### Effective price per fee type

The effective price is derived so the invariant holds exactly:

| Fee type | quantity | commission (stored) | settlement (CSV) | effective price |
|---|---|---|---|---|
| **Quote-fee** (fee in quote ccy) | gross qty | `-fee` (negative, same ccy as price) | actual USDT moved (gross ± fee) | `(settlement - commission) / qty` |
| **Base-fee** (fee in base asset) | net qty (gross + fee_delta) | `-fee` (negative, **different** ccy — display only) | gross trade value (no fee conversion) | `settlement / net_qty` |
| **No-fee** | gross qty | `0` | gross trade value | `= fill_price` (exact) |

For sells, quantity is negative and the same formulas apply with signed values.

### Computed cash flow

`total_cash_flow` for a trade row computes:
```
cash_flow = -(price × quantity) + commission   [when commission_currency == trade currency]
cash_flow = -(price × quantity)                [when commission is in a different currency]
```

Verified for all five cases (quote-fee buy/sell, base-fee buy/sell, no-fee) — each exactly reproduces the settlement.

## Components

### Component 1: `_spot_legs` — unified effective price (protected)
- **Quote-fee:** `price = (settlement - commission) / qty`; `quantity = gross`; commission enters the calc.
- **Base-fee:** `price = settlement / net_qty`; `quantity = net`; commission is display-only.
- **No-fee:** `price = fill_price` (unchanged).
- The `quote_cash_amount` parameter (from the CSV's quote-leg `Balance Change`) is the settlement source.
- The leg no longer carries `cash_flow` (it's not written to the trade row).
- The `quote_currency` key stays (for the `currency` field).

### Component 2: Schema — increase `price` field precision
The `price` field is `DecimalField(max_digits=18, decimal_places=6)`. At 6dp, `p × q` cannot reproduce 8dp settlements exactly (gap ~1.8E-8). Increase to `decimal_places=9` (matching `quantity`/`cash_flow`). One `AlterField` migration.

### Component 3: `persist_crypto_exchange_event` — stop writing `cash_flow` on trade legs
Currently writes `tx_kwargs["cash_flow"]` from the leg's `cash_flow` key (PR #27 Task 6). Remove that write for trade-category legs. The `commission` / `commission_currency` writes stay.

### Component 4: `total_cash_flow` — crypto trades move to p×q branch (protected calc)
Currently crypto trades (`CRYPTO_TRADE_IN/OUT`) are in `cash_flow_types` (line 206-207) and read `transaction.cash_flow` directly. Remove them from that list so they fall through to the Buy/Sell-style computation: `-(price × quantity) + commission` (when `commission_currency == transaction.currency`). This is the calc-layer change the design requires.

### Component 5: `nav.py` `_calculate_cash_flow` — add commission (protected calc)
Currently computes `-quantity × price` for crypto trades (line 411) without commission. Add `+ commission` when `commission_currency == transaction.currency`. For base-asset fees (different currency), no commission term.

### Component 6: Regression fixtures
Concrete numeric assertions for all five cases (quote-fee buy/sell, base-fee buy/sell, no-fee) verifying:
- `price × quantity` (± commission) == settlement exactly.
- `total_cash_flow(transaction)` == settlement exactly.
- `get_economic_basis` returns the correct cost basis (`quantity × price`).

## What does NOT change
- `get_economic_basis` (`realized.py`): computes `quantity × price` — unchanged. The effective price makes it correct.
- `position()` (`positions.py`): sums `quantity` — unchanged.
- Non-trade rows (Cash in/out, Dividends, etc.): keep using `cash_flow` directly.

## Calc-layer impact summary
- `total_cash_flow` (`services/transactions.py`): crypto trades move from cash_flow-reading to p×q-computing branch. **Protected, needs regression fixtures.**
- `nav.py:411`: add commission term. **Protected.**
- `realized.py`, `positions.py`: **unchanged.**

## Constraints
- **Decimal only** — never float. `ROUND_HALF_UP`.
- `services/crypto_exchange.py`, `services/transactions.py`, `services/nav.py` are protected — `needs-approval` PR.
- Schema change: `price` field `decimal_places` 6 → 9 (additive migration, no data loss).
- Historical data: existing trade rows have `cash_flow` set and `price` at 6dp. Re-import required for full consistency. The calc-layer change (crypto trades to p×q branch) means old rows with stale `cash_flow` would be ignored (p×q used instead) — so old rows' `price` must be correct for p×q to work. Documented limitation: re-import fixes everything.

## Testing strategy
- Unit: `_spot_legs` produces the correct effective price for all five cases.
- Integration: persist each case, assert `total_cash_flow(tx) == settlement` exactly (after broker-precision rounding).
- Integration: `get_economic_basis` returns correct basis after a base-fee buy.
- Full suite: no regressions (the crypto-trade branch move in `total_cash_flow` is the risk — regression fixtures cover it).

## Broker cash-precision attribute

### Problem
`price@9dp × quantity` has a residual gap of up to ~1E-11 vs the exact settlement. When many trades are summed in a cash balance, these residuals accumulate and the balance no longer matches the exchange's reported balance exactly.

### Solution: `cash_precision` on the Brokers model
Add an `IntegerField(cash_precision)` to `Brokers` — the number of decimal places the broker uses for cash settlement. This is the authoritative rounding applied when computing cash flow from `price × quantity ± commission`.

| Broker type | cash_precision | Rationale |
|---|---|---|
| Traditional (Charles Stanley, TBank) | 2 | Cents |
| Crypto (OKX, Bybit) | 8 | OKX settles to 8dp |

### How it's used
`total_cash_flow` (and `nav.py`'s `_calculate_cash_flow`) round the computed `-(price × quantity) ± commission` to the transaction's broker's `cash_precision` before returning. This absorbs the price-storage residual exactly:
```
cash_flow = round(-(price × quantity) + commission, broker.cash_precision)
```

For trade rows where commission is in a different currency (base-asset fee):
```
cash_flow = round(-(price × quantity), broker.cash_precision)
```

### Default for existing brokers
The migration sets `cash_precision=2` as the default (matching traditional brokers). OKX/Bybit brokers are updated to 8 (either in the migration or manually after).

### Component: Brokers model + migration
- `cash_precision = IntegerField(default=2, validators=[MinValueValidator(0), MaxValueValidator(9)])` on `Brokers`.
- Migration: `AddField` with default=2. A data migration step sets crypto brokers to 8 (by broker name match or a manual step).

### Component: total_cash_flow / nav.py threading
- `total_cash_flow(transaction)` looks up the broker's `cash_precision` via `transaction.account.broker.cash_precision` and rounds the result.
- `nav.py`'s `_calculate_cash_flow` does the same.
- This replaces the removed `round(..., 2)` (PR #35) with a broker-aware rounding.
