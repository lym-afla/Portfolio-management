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

### Round 3 - bounded corrections (PR #65, pre-financial-approval)

Four bounded corrections, RED-first, on the same branch (head includes
`72fc8a1c`); draft status and labels unchanged.

1. **False certification prevented.** Amortizing bonds whose effective
   notional resolves through `get_current_notional`'s UNCONVERTED
   transactions-fallback (no NotionalHistory on/before the effective date;
   converted branches untouched - never classified indiscriminately) are
   detected per asset: NAV stays canonical but marked partial with reason
   `bond_notional_fallback_unconverted`, the affected assets are listed in
   `diagnostics.affectedNotionalFallbacks`, reconciliation goes incomplete,
   and dependent returns report partial or visibly failed - even though the
   raw pieces cancel to zero. The engine characterization remains split out
   (direct `get_current_notional`/`unrealized_gain_loss` assertions).
   Regressions: `test_rub_bond_fallback_notional_stays_uncertified_in_statement`
   + the split characterization test.
2. **Unknown attribution in aggregates.** When cash FX is unknown,
   `attributedSum` and `unexplainedDifference` are UNKNOWN (`raw` null,
   `partial`, `missing_fx`) instead of exact values computed from missing
   inputs; the known share is exposed as an explicitly labelled
   `knownSubtotal` distinct from certified totals. Rendered regression: the
   partial fixture's unknown cash FX renders as `N/A (partial)` with no
   exact difference claimed.
3. **Account-scope validation completed.** For `account` selections the
   resolved set must be exactly that account, once: sibling, superset and
   duplicate sets are `SummaryContextMismatchError`. Duplicates/invalid ids
   are structurally invalid on any shape. For `all`/`group`/`broker`
   selections only the selection token and document shape are checkable
   client-side - membership cannot be reconstructed from the token
   (documented limitation, not a proof). Tested through the request-owning
   path (mounted page) and the boundary.
4. **Cross-document status validation completed.** Complete/reconciled
   documents with any partial/unavailable monetary dependency (nav,
   control total, attributed, unexplained, fxDetail, components, capital),
   omitted valuations, declared unclassified in-kind dependencies, remaining
   reasons, or a negative tolerance bound are rejected (zero stays valid); partial/
   unavailable amounts require a non-empty reason. Legitimate unavailable
   returns (IRR on zero capital) stay distinct from monetary completeness.

Gates on the round-3 head (actual exit codes): backend **0** (35 statement
scenarios incl. the split characterization + guard + aggregate-unknown),
unit **0** (119 files; boundary spec 41 cases), type-check/charts/reliability
**0**, api:types **0**, lint **0**, build **0**, browser `dashboard-statement-d`
**0** (3 viewports, incl. the FX-row N/A regression). The pre-existing
final-qa-d8 failure remains recorded (base-reproduced).

**Phase D is NOT financially accepted because the guard works**: the two bond
engine defects are open; their correction is planned separately in
[bond-engine-correction-plan.md](bond-engine-correction-plan.md) (protected
code - currency-consistent unrealized decomposition, fallback-branch FX
conversion, full bond-kind/event/currency/scope matrix with independent
Decimal expectations - NAV 256.25, net result 56.25, security FX 23.75 for
the sanitized example - and cross-consumer integration checks).

## Round 4 - bounded corrections (PR #65, pre-financial-approval)

Head includes the round-4 commits; draft status and labels unchanged.

1. **Bond guard refined to actual affected dependencies.** The fallback-path
   detection now branches on the OUTPUTS the asset feeds:
   - same nominal/reporting currency: the omitted conversion is x1.0 - a
     no-op; the asset keeps fully certified, fully computed attribution
     (no warning);
   - foreign currency with an OPEN position: NAV partial + unrealized
     partial + realized warned (prior disposals may share the path);
   - foreign currency FULLY CLOSED: NAV stays ok (the asset is not in
     today's valuation) and only the historical realized attribution is
     warned - the realized bond path is internally consistent (both terms
     convert), so total return stays certified; the aggregates still go
     unknown (complete attribution is required for an exact difference).
   Regressions: same-currency no-op (reconciled, complete, no reason);
   closed-foreign (NAV ok 256.25, realized partial, aggregates unknown with
   labelled known subtotal 56.25); the open-position case keeps its
   existing guard assertions.
2. **Aggregates from ALL dependencies.** attributedSum/unexplainedDifference
   are certified only when NAV, capital, every attribution component and
   cash FX are all complete (control total + full attribution). Otherwise
   they are unknown (partial, reason = the first failed dependency) with
   the known share labelled. The option-gap and incomplete cases now show
   unknown instead of provisional numbers presented as ok.
3. **Bond diagnostic understandable + accurately labelled.** The UI explains
   `bond_notional_fallback_unconverted` in plain language ("a known bond
   currency-conversion issue can affect the displayed NAV and returns"),
   visible while the breakdown is collapsed. The partial NAV no longer
   carries `knownSubtotal` when the reason is the bond defect - the
   included value is known-DEFECTIVE, not a genuinely known subtotal
   (omission-driven partials keep theirs). Backend assertion added.
4. **Validator/evidence correction.** The validator rejects NEGATIVE
   tolerance only; ZERO is and remains valid (exact or empty calculation).
   A boundary case now pins zero-tolerance acceptance, and the earlier
   evidence wording ("non-positive") is corrected to "negative".
   Also fixed this round: the endpoint contract test silently depended on
   "today == 2026-10-15" (the JWT middleware reads the effective date from
   the token claim, not the test session); the token is now minted with the
   claim, making the test date-independent.

Gates on the round-4 head (actual exit codes): backend **0** (1456 passed /
10 skipped, coverage 84.23%; 37 statement scenarios), unit **0** idle-machine
(119 files; one concurrent-load run hit 2 chart-spec flakes - documented
family), type-check/charts/reliability **0**, api:types **0**, lint **0**,
build **0**, browser `dashboard-statement-d` **0** (3 viewports).

## Round 5 - bounded corrections (PR #65, pre-financial-approval)

Two corrections, RED-first on the same branch (`097214c7`).

1. **Bond guard matches the actual notional source currency.**
   `get_current_notional` denominates the notional in
   `nominal_currency or asset.currency` and converts source -> target; the
   guard previously compared the quotation (`asset.currency`) with the
   reporting currency. It now compares the SOURCE currency:
   - quotation matches reporting, nominal differs (USD quotation, RUB
     nominal, USD reporting): the fallback returns the RUB-par notional as
     USD (NAV 20,500 for a 12.5-USD-scale position) - the defect is live
     and detection no longer escapes. Regression RED under the old guard.
   - nominal matches reporting, quotation differs (USD nominal, EUR
     quotation, USD reporting): the omitted conversion is fx(USD->USD) = 1
     - a no-op; the statement reconciles completely and no false bond
     warning is raised. Regression RED under the old guard.
   Open/closed and historical realized/unrealized distinctions are
   preserved; `diagnostics.affectedNotionalFallbacks` entries now carry the
   nominal and source currencies for review.
2. **Known subtotals exclude defective contributions.** Affected bonds'
   realized/unrealized contributions are routed to explicitly provisional
   accumulators (exposed as
   `diagnostics.affectedProvisionalAttribution`) instead of the certified
   components, so they can never enter `attributedSum.knownSubtotal` or
   the component-level known subtotals (which now label every partial
   component's reliable included value). Mixed-asset wire regression:
   defective RUB bond + reliable USD stock -> `attributedSum` unknown
   (`raw` null) with `knownSubtotal` = 126.25 (stock 100 + cash FX 26.25),
   `unrealizedPrice.knownSubtotal` = 100 (reliable stock portion only),
   the bond's 6.25 / 9,898.75 excluded, and the provisional amounts
   exposed in diagnostics. The closed-foreign case's known subtotal is
   correspondingly cash-FX-only (26.25 - the warned realized attribution
   is provisional, not certified knowledge).

Gates on the round-5 head (actual exit codes): backend **0** (1460 passed /
10 skipped; 40 statement scenarios), unit **0** idle-machine (119 files;
one run hit the documented single chart-spec timeout flake, green on
focused + immediate full rerun), type-check/charts/reliability **0**,
api:types **0**, lint **0**, build **0**, browser `dashboard-statement-d`
**0** (3 viewports). Pre-existing final-qa-d8 failure unchanged
(base-reproduced).

## Round 6 - bounded correction (PR #65, pre-financial-approval)

One status-propagation defect corrected RED-first (head includes the round-6
fix; draft status and labels unchanged).

**Defect.** For a foreign affected bond with an OPEN position, the guard
marked only the unrealized components partial while `bond_defective` routed
the asset's REALIZED contributions into the provisional accumulators. A
partially disposed, still-open affected bond therefore had its realized
result omitted while `realizedPrice`/`realizedFx` stayed status `ok` -
silently certifying an excluded contribution as zero.
`realized_bond_affected` was assigned but never consumed.

**Fix.** The open branch now fails `realizedPrice`/`realizedFx` (with the
closed branch, they already failed); the unused flag was removed
(`grep` count 0). Reliable included values remain labelled: partial
components carry `knownSubtotal` = their reliable included portion (zero
for fully-routed bond components; the reliable asset's contribution stays
in the component value and its known subtotal), and
`diagnostics.affectedProvisionalAttribution` exposes the excluded amounts.

**Regressions** (both wire-boundary, hand-derived):

- Partial disposal, open position: affected bond, partial disposal of 4 of
  10 @ par, remaining 6. Provisional (excluded) amounts: realized 2.50 /
  fx 9.50; unrealized 3.75 / fx 5,939.25 (the dimensional defect scales
  with the remaining position). NAV 6,181.25 (canonical, partial, no
  knownSubtotal); realized + unrealized components partial with the bond
  reason; aggregate unknown; returns uncertified.
- Mixed-asset wire regression: the same bond plus a reliable USD stock
  (realized 50 on a partial sale; unrealized 50). After the fix:
  `realizedPrice` partial with `raw` 50.00 and `knownSubtotal` 50.00 (the
  reliable stock realized stays labelled), security FX pair partial with
  raw/knownSubtotal 0.00 (bond provisional routed), `attributedSum`
  unknown with `knownSubtotal` = 126.25 (50 + 0 + 50 + 0 + cash FX 26.25),
  provisional diagnostics expose the four bond amounts, reconciliation
  incomplete, returns uncertified.

Gates on the round-6 head (actual exit codes): backend **0** (1462 passed /
10 skipped, coverage 84.23%; 42 statement scenarios), unit **0** (119
files - three consecutive failing runs traced to a POISONED vitest/vite
transform cache, not code: the frontend tree is byte-identical to the
round-5 green run, the same specs failed in isolation, and clearing
`node_modules/.vite` + full-suite rerun went green), type-check
/charts/reliability **0**, api:types **0**, lint **0**, build **0**, browser
`dashboard-statement-d` **0** (3 viewports). Pre-existing final-qa-d8
failure unchanged (base-reproduced).

## Missing information vs reproducible engine defects

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

## Bond-engine correction - separate stacked branch (post-round-6)

Implemented on `codex/bond-engine-correction` (worktree
`Portfolio-management-bondfix`, stacked on this branch at `5cbc4d0b`; separate
draft PR targeting this branch; needs-approval). Both documented boundaries
are corrected in protected code, RED-first:

1. **Unrealized bond decomposition (currency-consistent).**
   `unrealized_gain_loss`'s bond branch now converts the price percentage
   quotation -> target at EOP: `unrealized = notional_lcl x (price_target x
   fx_eop - buy_in_target) x pos / 100`. Corrected sanitized values:
   unrealized total 30.00 (was 9,905.00), price 6.25, FX 23.75 (= basis
   9,500 RUB x 0.0025 drift).
2. **Fallback notional converts exactly once.**
   `get_current_notional`'s transactions-fallback returns
   `current_notional * fx_rate` (1,000 RUB x 0.0125 = 12.50 USD instead of
   the raw 1,000).

Statement flips (all hand-derived): the sanitized example reconciles at NAV
256.25 / net result 56.25 / security FX 23.75 (complete); the amortizing
with-history redemption case reconciles at NAV 251.25 / control 51.25
(realized 1.25 + 4.75, unrealized 0 + 19.00, cash 26.25); the partial-
disposal open case certifies at 56.25 (realized 12.00, unrealized 3.75 +
14.25, cash 26.25); the mixed bond+stock case certifies at 1,356.25 /
156.25; the closed-foreign case certifies at 56.25 (realized 30.00, cash
26.25). The temporary statement guard (`bond_notional_fallback_unconverted`),
its knownSubtotal suppression, and the provisional diagnostics are RETIRED -
regressions prove valid certification, and the genuinely-incomplete cases
(option gap, coin fees, in-kind transfers, missing price/FX, same-day wrap)
keep their honest partial/unreconciled states.

Consumer-path agreement: NAV_at_date totals == statement NAV == per-position
values on the sanitized datasets (asserted in
`test_amortizing_fallback_statement_reconciles_at_sanitized_values`,
`test_amortizing_with_history_partial_then_full_redemption`, and the
partial-disposal regression). Account and investor isolation asserted for
the corrected fallback and history branches (redemption aggregates are
account-filtered; NotionalHistory is asset-scoped - pre-existing behavior,
documented, untouched).

Real-data validation (disposable DB copy, uncorrected vs corrected on the
identical dataset): All-accounts security FX moved from +$424,971.47
(RUB-par-as-USD defect) to -$424.04 (plausible RUB drift on remaining
holdings); the unexplained residual dropped from -$426,569.74 to
-$1,174.22. Per-account sweep: accounts 17/1/10/14 reconcile (sub-cent
residuals); account 2 unreconciled at -14.50 (small residual, documented);
accounts 18/20 incomplete with honest coin-fee and in-kind reasons (their
+39,998.85 / -40,040.90 residuals nearly cancel - in-kind transfers between
the OKX funding/trading accounts); account 15 unreconciled at -1,117.63
(remaining real-data residual, documented for review - not forced).

Gates on the correction head: backend **0** (1468 passed / 10 skipped incl.
the new correction suite; full suite green means no other consumer depended
on the defective values), frontend unit **0** (119 files; the recurring
chart-spec timeouts are the documented machine-degradation family - the
frontend tree is byte-identical to PR #65's green run, failing specs pass on
focused rerun, and a control run in the PR #65 worktree fails identically),
type-check/charts/reliability **0**, api:types **0**, lint **0**, build
**0**. PR #65's branch and worktree are unchanged (the corrections were
developed in the bondfix worktree; the PR #65 worktree was restored clean
after an accidental in-place edit was moved over).
