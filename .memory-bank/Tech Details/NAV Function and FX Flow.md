---
Tech details/NAV Function and FX Flow.md
---

# NAV Function and FX Flow — Technical details

## Purpose
This file documents the concrete implementation of the NAV calculation and related helper functions. It is intended for engineers and AI agents that need to inspect or extend the computation code.

## Key components (mapping to code)
- `NAV_at_date(...)` — universal NAV entry point for computing NAV and breakdowns.
- `_portfolio_at_date(...)` — helper to retrieve assets with non-zero positions as of a date.
- `Assets.price_at_date(...)` — returns the price quote used for valuation; falls back to last transaction price if no price is found.
- `Assets.calculate_value_at_date(...)` — returns market value for an asset on a date; handles bonds specially.
- `Assets.realized_gain_loss(...)` and `Assets.unrealized_gain_loss(...)` — compute realized & unrealized gains and their decomposition into price_appreciation and fx_effect.
- `Assets.calculate_buy_in_price(...)` — implements the average buy-in algorithm used for realized/unrealized calculations.

## NAV_at_date — behavior summary
- Iterates portfolio (assets) and accounts to compute per-account and per-breakdown values.
- Uses `security.position(date, user_id, [account.id])` to get position as of `date` and `security.calculate_value_at_date(...)` to get market value.
- Adds converted cash balances for each account (via `account.balance(date)` and `get_fx_rate(...)`).
- Returns a dictionary with `Total NAV` and breakdown buckets as requested.

## Important implementation notes
- `NAV_at_date` is `lru_cache` decorated. This is helpful for performance but requires cache invalidation strategy when transactions/prices/FX change.
  - **Rule:** Cache must be invalidated on transactions import, price update, FX update, or any data change affecting positions. Prefer a cache key that includes latest-modified timestamps when possible.
- `_portfolio_at_date` uses `annotate(total_quantity=Sum(...))` and `.exclude(total_quantity=0)`. This approach is efficient but watch for DB-side SUM semantics (NULL vs 0) and for very large transaction tables.
- `price_at_date` falls back to last transaction price if no price quote exists. This is intentional but must be explicit in tests.

## FX handling
- FX conversion uses `FX.get_rate(from_cur, to_cur, date)` which returns a dict containing `"FX"` factor.
- When converting prices, the code uses the asset's currency and multiplies price by FX factor (except bonds where FX rate may be handled differently per context).

## Performance & scaling notes
- Currently using SQLite: acceptable for local dev, not for production scale. Expect query slowdowns for `_portfolio_at_date` and any annotation queries as transaction counts grow.
- Derived computations (positions, NAV) are computed on-demand: consider materializing some snapshots (e.g., daily NAV snapshots) if UI performance becomes an issue.

## Suggested immediate improvements (non-invasive)
1. Add cache keys / signals to invalidate `NAV_at_date` when relevant models change (Transactions, Prices, FX, NotionalHistory).
2. Add unit tests that assert fallback behavior for `price_at_date` (when no price exists and last transaction exists vs when no transaction exists).
3. Prepare a migration plan to move from SQLite to PostgreSQL before production deployment.

---
