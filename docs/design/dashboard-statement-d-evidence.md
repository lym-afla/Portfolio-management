# Phase D reconciled dashboard statement — evidence record

Branch: `codex/dashboard-reconciled-statement-d` (worktree
`Portfolio-management-dashboard-d`), based on `origin/codex/frontend-modernization`
at `efca731d`. Design/contract: `docs/design/dashboard-reconciled-statement-d.md`.
Plan: `docs/superpowers/plans/2026-10-15-dashboard-reconciled-statement-d.md`.
Status: **draft, needs-approval** — financial review and design review pending;
no merge authorized.

## Tested commits (all gates on committed code)

| Commit | Content |
|---|---|
| `88f6ff87` | backend read model + opt-in `summary_contract=2` + schema |
| `e42cb1e2` | typed boundary + `PortfolioValueStatement.vue` + wiring |
| `f75f7755` | `dashboard-statement-d` browser case + fixture modes |
| `bbb2ec5a` | browser-case corrections (capture path, request deltas, zoom scroll, tablet) |
| `1da17090` | this phase's captures (only `dashboard-summary-d` assets retaken) |

Gate results (exit codes are the actual process exit codes):

| Gate | Result |
|---|---|
| Backend `uv run python -m pytest` (test settings) | **exit 0** — 1450 passed, 10 skipped, coverage 84.14% (≥80% gate) |
| New backend suites | `test_dashboard_summary_reconciliation.py` 28 scenarios + `test_dashboard_summary_contract_v2.py` 4 tests — 34 passed |
| `npm run test:unit` | **exit 0** — 119 files, 1145 tests (clean-machine rerun; the marathon run had 1 unrelated `ProfileRoutes` load flake, and one contaminated post-cleanup run with leaked-process fallout — both superseded by the clean rerun) |
| `npm run type-check` | **exit 0** |
| `npm run type-check:charts` | **exit 0** |
| `npm run type-check:reliability` | **exit 0** |
| `npm run lint` (strict baseline) | **exit 0** (0 errors, 8 baseline warnings; baseline re-pinned for 3 line-shifted `api.ts` entries after the additive type re-export) |
| `npm run api:types:check` | **exit 0** |
| `npm run build` | **exit 0** (2.4s) |
| Browser `dashboard-statement-d` | **exit 0** — desktop 1440×1000, tablet 1024×768, mobile 390×844; approved composition, expanded/collapsed (mouse + real Enter), one-owner summary request deltas (`summary_contract=2` on every request), partial/unreconciled/legacy-only/malformed states, long-amount elementFromPoint containment, desktop→mobile→desktop, native 200% zoom (DPR 2 verified, reset to 1) |
| Browser context / dates / recovery / requests | **exit 0** ×4 |
| Browser charts-c2 / charts-c3 / charts-c4 / charts-c5 / charts-c | **exit 0** ×5 (charts-c additionally log-verified below) |
| Browser delivery / layout | **exit 0** ×2 |
| Browser FULL route matrix | **exit 0** — all 18 routes × 4 viewports, 0 failures, 0 fixture mismatches |
| Browser final-qa-d8 | **exit 1 — one failing workflow, PRE-EXISTING**: `chart-acceptance: price table keeps exact dollar displays` fails identically on the untouched base `efca731d` (comparison run recorded in `temp_files/gate-finalqa-BASE.log`). Everything else in the D8 default-on pass is green: 90 probes, 37 workflows, 3 rollback spot checks, 35 captures, dashboard gzip 490,527 < 535k budget. All 90 default-on probes also pass on this branch. |
| Browser charts-c exit-code anomaly | two runs produced **clean PASS logs** (`PASS desktop /dashboard`, `PASS charts c flow`, zero route failures/mismatches) with an anomalous process exit (127 once, an exit-wedge once) — the known agent-browser exit-wedge family on this case; the PASS evidence is in `temp_files/gate-browser-charts-c*.log` and the FULL matrix covers the same surface green |

Perf record (plan Task 1, synthetic multi-account fixture: 3 accounts × 2 assets
× ~34 rows): **247 queries, 0.155 s** (`test_multi_account_query_count_is_recorded_and_bounded`,
`DASHBOARD-STATEMENT-PERF`).

## Real-data validation (disposable copy, read-only probes)

Method: copied `backend/db.sqlite3` into the worktree (original never opened
for write), backend served from the worktree on :8000, frontend built with
`VITE_API_URL=http://127.0.0.1:8000` and served on :8080, a SimpleJWT pair
minted against the copy. Completed checks:

- Multi-account (All accounts, 8 accounts across ByBit/Charles Stanley/IB/OKX/Tinkoff):
  statement renders the real API document verbatim (invested $200,821.03 /
  cash out ($46,294.53) / net capital $154,526.50 / net result ($18,434.47)
  with the `(partial)` flag), charts and allocation coexist, amounts contained.
- Single crypto account (OKX Trading, fully liquidated): control ($40,068.24)
  vs attributed ($27.34) → unexplained ($40,040.90) with `reconciliation:
  incomplete`, reasons exactly `crypto_coin_fee_not_attributed` +
  `in_kind_flows_unclassified`, 7 unmatched transfer-outs counted. The legacy
  page shows only "(98.3%)" with no explanation; the statement names the gap.
- Account switch via the header arrows re-renders the per-account statement.
- Historical-date and currency contexts were exercised in the synthetic
  browser matrix (dates case + statement case); the real-data session covered
  the account axis only before the disposable environment was torn down.
- Legacy parity on real data: the five legacy fields are byte-identical with
  and without the negotiation parameter (same endpoint, same handler).

## Review round - 15 October 2026 (PR #65 corrections before financial approval)

All five review findings verified against the head and corrected RED-first on the
same branch (`fadc0f60`, `9d057b44`); labels unchanged (`needs-approval`,
`area:calculations`, `risk:high`).

| Finding | Resolution | Regressions |
|---|---|---|
| 1. Display rounding vs reconciliation | The rounding note is gated on backend certification (status complete, reconciliation reconciled, nav/controlTotal and every component + fxDetail amount `ok`) AND a raw-level check that the unexplained difference is within tolerance. `N/A`/`NA`/`N/R` parse as MISSING (null), never zero - only the en-dash zero marker maps to zero. Incomplete and unreconciled statements surface their actual material unexplained difference (raw vs tolerance, BigInt-scaled) in the status line, which stays visible while the detail is collapsed. | material difference on incomplete; missing component never yields a rounding note; genuine small rounding difference still noted |
| 2. Historical cash-flow FX completeness | Certified cash FX requires BOTH own-date flow conversions (ledger) and ending-balance valuation; failures make `fxDetail.cashFlows` and the fx component UNKNOWN (`raw` null, `partial`, `missing_fx`) instead of a fabricated difference; ledger completeness joined `dependencies_complete`; in-kind FMV conversion failures mark the diagnostic `fmvKnown: false`, drop `signedFmv`, and surface `missing_fx`. | missing historical trade/FX-leg conversion (coin leg at a date with no coin price while ending-date FX exists - deterministic crypto-lookup boundary; the arithmetic closing still reports `incomplete`); in-kind FMV conversion failure |
| 3. Response context validation | `getDashboardSummaryV2(captured, options)` validates the document context against the captured request context - selection identity, effective date, currency, digits - with `SummaryContextMismatchError` (the chart-convention class); the page feeds the captured context through the existing request owner, discards the content, and triggers one bounded `reconcileContext()` per mismatch episode. | wrong-context 200 through the mounted page renders nothing and shows the typed failure; boundary cases for each mismatched field |
| 4. Refresh loading/error visibility | Retained statements/legacy metrics stay mounted with an explicit stale/busy marker (`summary-updating`) while a refresh parks, and their own failure alert + Retry when it rejects - inside both the v2 and legacy-only branches; the skeleton/error branch now only serves the no-data cases. No additional requests. | successful load -> parked refresh -> rejected refresh -> successful retry; legacy-only cycle; mismatch case |
| 5. Validator hardening | Rejects non-fixed-notation or non-finite decimals (`1e5`, `NaN`, `Infinity`, `abc`), impossible/non-ISO dates, fractional/negative account ids and digits, string digits, unsupported selection shapes, `knownSubtotal` on ok amounts, ok amounts with null raw, unavailable amounts with raw, ok returns with null values, terminal returns with values, complete/unreconciled and reconciled/partial incoherence, fractional in-kind counts, and malformed notes (no silent filtering). High-precision raw strings pass verbatim. | 24 boundary cases in `DashboardStatement.boundary.spec.ts` |

Gates on the review head (actual exit codes): backend `uv run python -m pytest`
**0** - 1455 passed / 10 skipped, coverage 84.23%; new backend suites 35 scenarios;
unit **0** - 119 files; type-check / type-check:charts / type-check:reliability /
api:types:check / lint / build all **0**; browser `dashboard-statement-d` **0**
(3 viewports; the status-line and stale-marker changes covered by the mounted
specs). The pre-existing final-qa-d8 failure (base-reproduced) is unchanged.

### RUB-bond discrepancy - reduced to two exact engine boundaries

Sanitized, hand-derived dataset (three pinned regressions in
`test_dashboard_summary_reconciliation.py`): 10 RUB bonds, par 1,000, bought at
95% for 9,500 RUB, funded by 20,000 RUB; RUB->USD 0.0100 at entry and 0.0125 at
the effective date; price 100. **Correct statement**: bond value 125 + cash
131.25 = NAV 256.25; control 56.25 = unrealized price 6.25 + certified FX
23.75 (= 9,500 RUB basis x 0.0025 drift) + cash FX 26.25 -> reconciled.

- **Boundary 1 (dimensional)** - `services/realized.py unrealized_gain_loss`,
  bond branch: the FX term multiplies the bond's LOCAL-currency notional by
  TARGET-currency prices (`notional_lcl x (price_target - buy_in_target) x pos
  / 100`; buy_in_target is the % converted by entry FX while price_target is
  not). Sanitized effect: 1,000 x (100 - 0.95) x 10 / 100 = 9,905 -> "FX"
  9,898.75. This term IS the real-data +$421k (RUB par presented as USD).
- **Boundary 2 (currency)** - `services/bonds.py get_current_notional`,
  transactions-fallback branch: `return current_notional` without the
  `* fx_rate` the other two branches apply -> an amortizing bond without
  NotionalHistory is valued at RUB-par as USD (sanitized NAV $10,131.25 for a
  $256 portfolio).
- **Interaction**: with boundary 2 active, boundary 1's garbage FX exactly
  cancels the inflated NAV -> the statement closes and reports
  complete/reconciled for a portfolio valued 40x too high
  (`test_rub_bond_fallback_notional_currency_error_falsely_reconciles`). With
  boundary 1 alone the statement honestly refuses (unreconciled -9,875 /
  -7,900). Both tests pin CURRENT behavior as engine-defect documentation;
  correcting either is a protected-code decision (expected numeric results in
  the test docstrings: fx_security 23.75, reconciled at 56.25).

### Missing information vs reproducible engine defects

- **Missing information (no policy invented; statement goes incomplete):**
  external (unmatched) crypto transfer-outs book no realized result and
  transfer-ins enter at zero basis - nothing in the recorded data supports
  attribution; counted diagnostically (`unclassifiedInKindFlows`).
- **Reproducible engine defects (sanitized regressions, engine-side fixes
  require separate review):** the two bond boundaries above; the same-day
  disposal+reacquisition buy-in wrap (basis -0, overstates unrealized);
  coin-denominated fees invisible to the unrealized engine (raw quantity sum
  vs fee-depleted `position()`). None of them is relabelled; each surfaces as
  an explicit partial/unreconciled state with its reason.

## Unresolved reconciliation cases (acceptance gaps for financial review)

1. **RUB bonds: REDUCED to two exact engine boundaries (see the review-round
   section above).** The real-data fxSecurity ≈ $421,815 is the dimensional
   defect in `unrealized_gain_loss`'s bond FX term (local notional x target
   prices); the unexplained ($426,569.74) mixes it with the unconverted
   fallback notional in `get_current_notional`. This branch surfaces both
   verbatim; the corrections are protected-code decisions documented with
   expected numeric results (sanitized: fx_security 23.75, reconciled 56.25).
2. **Coin-denominated crypto fees** (e.g. BTC fee on a BTC-USDT trade): the
   unrealized engine values the raw quantity sum while NAV uses the
   fee-depleted `position()`; the fee burn is unattributed by the engine
   (unit-pinned; reason `crypto_coin_fee_not_attributed`).
3. **Unmatched external crypto transfers**: transfer-outs book no realized
   result (transfer types are not disposals); transfer-ins enter at zero
   basis. No in-kind policy is invented — flows are counted diagnostically
   (`unclassifiedInKindFlows`) and the statement stays incomplete.
4. **Same-day disposal + reacquisition** degenerates the weighted-average
   buy-in walk (basis −0) and overstates unrealized; pinned as an honest
   `unreconciled` regression.
5. **Amortizing bonds**: the engine's redemption basis uses sell-date
   notional; notional drift between buy and sell lands in the unexplained
   difference. No amortizing-bond reconciliation is claimed.
6. **pre-existing final-qa-d8 failure** (above) — owned by the D8 workstream,
   not this branch (base-reproduction evidence recorded).

## Review callouts (from the design doc, §6)

1. Income is gross of tax (diverges from `get_capital_distribution`, which
   nets `Tax` rows — reusing it would double-count taxes with the Taxes row).
2. Crypto reward income converts the USD-denominated reward value with
   USD→target FX (the existing distribution helper's coin-rate conversion
   over-scales coin-currency reward rows).
3. Certified FX = engine security FX + independently derived cash-flow FX
   (`cash at EOP rates − the same flows at own-date rates`); the residual FX
   in `services/performance.py` is not reused and that surface is unchanged.
4. Total return keeps the incumbent formula with signed cash-out — this is
   exactly the approved mock's arithmetic (17.50% for the mock example).
