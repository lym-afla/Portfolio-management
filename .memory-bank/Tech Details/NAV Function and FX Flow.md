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
- **FX Convention**: For each currency pair `CUR1CUR2` in the database, the value represents the number of `CUR1` units per 1 `CUR2` unit. For example, `RUBUSD = 75` means 75 RUB = 1 USD.

## NAV omission diagnostics and the chart contract v2 (C1)

`NAV_at_date` in `backend/services/nav.py` accepts an optional keyword-only
`diagnostics: list | None = None`. When a list is supplied, each valuation
source the function **omits** appends one provenance dict immediately before
the existing `continue`:

- Unpriced crypto coin (USD price unavailable via `price_at_date` FX raise):
  `reason: 'missing_price'`, `account_id`, `asset_id`, `currency`,
  `asset_type`, `asset_class`.
- Option settle coin without an FX rate: `reason: 'missing_fx'` with the same
  source fields.
- Option cash flow in an unconvertible coin (Crypto-bucket routing): `reason:
  'missing_fx'`, `account_id`/`asset_id` from the transaction, `currency`.
- Cash balance currency without an FX rate: `reason: 'missing_fx'`,
  `account_id`, `currency`, `asset_type`/`asset_class` `'Cash'`.

The argument is pure instrumentation: no formula, fallback, cache or
return-shape change, and the default call is output-identical (regressions:
`tests/unit/calculations/test_nav_diagnostics_equivalence.py` plus the
existing option/crypto/bond NAV suites).

The chart endpoints negotiate the opt-in contract via `chart_contract=2`:

- `dashboard/api/get-nav-chart-data/` keeps its legacy payload and adds a
  `chartV2` document (exact Decimal `value`/backend-scaled `plotValue`
  strings, exact sampled ISO periods, stable series identity, units,
  statuses/reasons, display strings). Assembly happens in
  `services/charts.py` (`_NavV2Collector`, `decimal_chart_value`,
  `unavailable_chart_value`); the dashboard view supplies the context and the
  v2 error contract (`400 INVALID_CHART_QUERY`, `500
  CHART_CALCULATION_FAILED`, `200 outcome:'empty'`).
- `dashboard/api/get-breakdown/` adds `chartV2` with one `kind='allocation'`
  document per dimension (`assetType`/`assetClass`/`currency` keys):
  denominator = full reporting NAV, raw-ratio shares, deterministic ranks and
  backend-certified `pieEligibility` (`eligible` only for a known complete
  nonnegative partition of a positive NAV; otherwise `incomplete` >
  `nonpositive_total` > `signed` > `nonpartitioning`).
- Security price/position histories return `{legacy: <unchanged array>,
  chartV2: document}`; the legacy array is wire-identical (positions remain
  Decimal-as-string per `JsonResponse`'s encoder).
- Unknown is never zero: omitted valuations surface as `partial` values with
  `knownSubtotal`, absent categories stay `absent_unclassified`, and IRRs
  against an incomplete terminal NAV are `partial` with null `value`.
- Completeness propagates by dependency, not blanket-flagging: the
  since-inception IRR at a sample depends only on that sample's terminal NAV;
  the interval IRR additionally prices the opening portfolio value at the
  previous endpoint; the contributions-mode opening NAV carries the previous
  endpoint's completeness; the period return prices both endpoints; the
  cumulative return prices only the terminal value; contributions and
  cumulative net investments come from canonical transactions and stay
  observed. Security price/position documents carry `partition: 'complete'`
  (single observed series, no cross-series partition question).

## Performance & scaling notes
- Currently using SQLite: acceptable for local dev, not for production scale. Expect query slowdowns for `_portfolio_at_date` and any annotation queries as transaction counts grow.
- Derived computations (positions, NAV) are computed on-demand: consider materializing some snapshots (e.g., daily NAV snapshots) if UI performance becomes an issue.

## Suggested immediate improvements (non-invasive)
1. Add cache keys / signals to invalidate `NAV_at_date` when relevant models change (Transactions, Prices, FX, NotionalHistory).
2. Add unit tests that assert fallback behavior for `price_at_date` (when no price exists and last transaction exists vs when no transaction exists).
3. Prepare a migration plan to move from SQLite to PostgreSQL before production deployment.

---
