# Release validation phase C — charts and security presentation (Tasks 6–7)

Evidence ledger for phase C of the [correction plan](../superpowers/plans/2026-10-09-release-validation-fixes.md).
Branch `codex/release-validation-charts-c`, dedicated worktree `Portfolio-management-charts-c`, base `2d80e359`
(PR #63/phase B merged; verified remote tip before branching). Draft PR into `codex/frontend-modernization`; stops for review — no merge, no deployment, no C5b, no palette change.

## Task 0 — baseline and inventory (source-confirmed before any edit)

Baseline gates on the pristine base `2d80e359` in this worktree (sequential, actual exit codes):

| Gate | Result | Exit |
|---|---|---|
| `test:unit` | 1084 passed / 3 failed — the known canvas-heavy timeout flake class under machine load (`allocation.spec.ts` ×2, `securityHistory.spec.ts` ×1, 20–21 s timeouts); isolated rerun of both files: all green | 1 → clean rerun 0 |
| `type-check` / `type-check:reliability` / `type-check:charts` | clean | 0 / 0 / 0 |
| `api:types:check` | clean | 0 |
| `lint` | 0 errors / 8 warnings (baseline unchanged) | 0 |
| `build` | clean | 0 |

Source-confirmed inventory relevant to Tasks 6–7 (each verified by reading the base code, not assumed):

- **NAV option** (`features/charts/buildNavOption.ts`): both y-axes drew ECharts default `splitLine`s (two competing grids); tooltip appended per-line unit suffixes (`(USD)`), per-IRR horizon date-range brackets, and a trailing `Portfolio NAV (all categories)` totals line; totals also exist in `ChartDataTable` (`document.totals` column).
- **Legend** (`ChartLegend.vue`): every button carried a 1px border plus a selected inset ring (the "heavy outline").
- **Inspection card** (`ChartInspection.vue`): a separate bordered card duplicating exact values, plus the only keyboard-operable zoom selects (Start/End period) and Reset zoom button.
- **Exact tables** (`ChartDataTable.vue`, `SecurityDataTable.vue`): always rendered, never collapsed; the security table rendered every observation with no pagination (distinct same-date keys stayed distinct rows via `period.key`).
- **Pies** (`buildAllocationOption.ts`): labels were category names at the default outside position, so ECharts drew leader lines (`labelLine` default visible); no slice separators; percentages existed only in tooltip/table/legend aria-labels, never on the pie.
- **Sharpness**: all three ECharts wrappers registered `CanvasRenderer`; zrender's canvas painter fixes `devicePixelRatio` at construction and `Painter.resize()` never re-reads it, so a native-zoom DPR change after init CSS-scales the stale backing store (blur). `zrender.ZRender.prototype.resize` takes no dpr; `echarts.init`'s `opts.devicePixelRatio` is init-only; **and `zrender/lib/config.js` exports a module-load-time `devicePixelRatio` constant that a re-init falls back to when no explicit dpr is passed** — re-initialization alone is not enough; the init options must carry the current dpr.
- **Geometry**: NAV pilot rendered inside `NAVChart.vue`'s `#chart` slot (`.chart-wrapper`, 16px padding, inside `v-card-text` with Vuetify's 16px padding); security charts rendered at 320px inside `WorkspaceSection` content while the incumbent renderer's skeleton/fallback boxes are 400px tall.
- **Security account selector** (`views/database/SecurityDetailPage.vue` + `features/securities/useSecurityDetail.ts`): local model started `null` (v-select showed an empty field while the request was unfiltered); options come from `getAccountChoices` whose first group offers `All accounts → {type:'all', id:null}`. **Vuetify only invokes the `selection` slot for a non-null model** (rendered proof in the charts-c case: the slot-based label never appears for a null model — the null-model design was wrong at the Vuetify level, not just cosmetically).
- **Holdings context backend inventory**: `get_security_detail` (`backend/services/securities.py`) exposed `open_position`/values scoped by the optional account filter but **no per-account holdings breakdown**. Canonical primitives existed: `services.positions.position` (per-account sums; handles crypto commission/option cash-flow depletion) and `services.positions.get_accounts_with_positions` (non-zero accounts at a date — no production caller). `Accounts` carry `broker` (name), `is_active`; `format_account_display` builds qualified display names.

## Findings and resolution status

Every row distinguishes source-confirmed cause, reproduced cause and still-unverified hypothesis.

| Owner requirement | Task | Status |
|---|---|---|
| Charts span their content section, aligned with page edges | 6 | RESOLVED — `NAVChart` card text carries no horizontal padding (the controls row insets itself); pilot canvas at the incumbent 600px/360px height; security canvases 320→400px (incumbent parity — the skeleton/fallback boxes are 400px). Rendered edge alignment asserted by the charts-c case (canvas left within 2px of card left, width within 4px, ≥560px tall) |
| Sharp at native 200% zoom | 6 | RESOLVED (source-confirmed + reproduced in the rendered case): the DPR change needs (a) a re-init AND (b) explicit `devicePixelRatio` init options — zrender's module-level constant stays stale. Renderer decision: canvas KEPT over SVG (dense-history render cost, zero bundle delta). `watchDevicePixelRatio` (self-re-arming matchMedia resolution query, lifecycle-cleaned) bumps a `:key` on all three wrappers' VChart; interaction state survives. Rendered proof: case-tab dpr 2 with canvas backing/css ratios ≈2 (charts-c run + charts-c4's native-200% capture in the gate matrix). **Reproduced defect the rendered case caught**: the first implementation (key remount without explicit dpr) left ratios at 1.0 — fixed by the init-options change; unit spec upgraded to pin init-options 1→2→1 |
| Secondary-axis grid removed; simplified tooltip/legend borders | 6 | RESOLVED — splitLine on the money axis only; tooltip drops unit suffixes, IRR horizon brackets and the all-categories NAV line (distinct control names, statuses, knownSubtotal intact); legend buttons lose the resting outline (pressed = light fill + inset ring). Deliberate supersession: the detailed horizons moved to the exact-value table, whose IRR columns now use the fixed control names |
| Inspection card removed; zoom/reset + keyboard inspection retained | 6 | RESOLVED — `ChartInspection.vue` deleted; `ChartZoomControls.vue` (start/end selects + Reset zoom, data-testids) renders between chart and legend; keyboard inspection lives on the exact table (rows keep click/Enter, render aria-selected + highlight). Focused probes (charts-c3/c5/final-qa-d8) retargeted |
| Exact tables collapsed behind labelled buttons; observation pagination 25/50/100 | 6 | RESOLVED — `ChartDisclosure.vue` (native toggle, aria-expanded, collapsed default; "Show/Hide exact values by period|observation"); SecurityDataTable paginates CLIENT-SIDE over the accepted document — 25 initially, 25/50/100, Previous/Next + "X–Y of Z observations", pages slice the server-ordered period list by index (same-date keys stay distinct), incompatible identity resets to page 1, shrinking documents clamp. `security-data-table` testid moved to the disclosure root so mounted-surface presence probes keep working |
| Pies: no leader lines, white separators, certified percentage labels | 6 | RESOLVED — `labelLine.show=false`, 2px white borders, slice labels show the CERTIFIED server share display (escaped, verbatim — never `params.percent`, never recomputed); in-slice labels hide on small slices (geometry-only 5% threshold) and zero rows; shares stay in legend/table/tooltip |
| Unfiltered security selector visibly says "All accounts" | 7 | RESOLVED — the local model IS the All-accounts selection (`{type:'all', id:null}`): Vuetify invokes the selection slot only for a non-null model, so the original null-model + slot design was structurally wrong (rendered proof in charts-c; the unit stub masked it by rendering the slot unconditionally — the PR #54 model/slot lesson). `selectedAccountId` still resolves to null (no request/scope change); clearable resets to the All-accounts selection; an explicit selection shows its display name; missing choices show the safe "Unavailable" |
| Current/previous broker-account holdings as of valuation date | 7 | RESOLVED — new canonical read model `services.positions.get_account_holdings` (remaining positions via the same `position()` the charts use — never lifetime buys; open/closed status at the valuation date; partial disposals stay open, sold-out-and-rebought is open; historical dates honored) exposed as `security_data["holdings"]` with qualified display names; frontend renders compact "Currently held with"/"Previously held with" groups; clicking an account is the explicit filter (charts-c asserts the request carries account_id=11). Backend change rides this PR under `needs-approval` (phase A precedent) |

## Review round (post-PR findings 1–4) — 14 October 2026

All four findings verified against the code, RED-first, corrected on the same PR:

1. **Indirect crypto holdings**: `get_account_holdings` discovered accounts only through direct transactions, while canonical `position()` also folds in commissions paid in the coin and coin-settled option cashflows (Crypto-gated). Discovery now mirrors those sources under the same investor/date scope and gate; records that cannot contribute (zero/null quantity, zero commission/cashflow) establish nothing — a dividend-only or zero-quantity account no longer surfaces as "Previously held" when no holding ever existed. 9 regressions (both indirect sources, the non-crypto gate, zero contributions, dividend-only, null quantity, zero-then-buy, investor isolation, cutoff isolation).
2. **Selector input safety**: a new REAL-Vuetify spec (6 states: unfiltered, empty choices, delayed choices, missing account, normal selection, clear) CONFIRMED the reviewer — the real input renders `[object Object]` for both missing AND matched selections (the stubbed specs could not see the input). Fix per the PR #54 lesson: matched selections store the option's own value (the input then shows the item title); an identity with no matching option normalizes to the safe "Unavailable" label string (`selectedAccountId` resolves null — no request for a nonexistent account); the All-accounts identity parks as the safe label string while choices are empty/delayed and restores the identity object when choices arrive. The "all" label no longer degrades to "Unavailable" with empty options. The holdings-filter button routes through the same normalization; the base fixture now lists the holdings accounts (11/12) so the filter matches and the charts-c case asserts `account_id=11`.
3. **Per-IRR horizons in the exact table**: each IRR column now carries its own horizon line (existing `seriesHorizon` helper) — since-inception spans inception-to-end, the interval column shows the server window; a later period proves the two horizons differ; the first sample shows inception semantics in both; non-IRR columns carry none.
4. **Grouped quantities**: `get_security_detail` adds `quantity_display` — Decimal format spec `,` (exact comma grouping, no conversion/rounding) beside the verbatim raw string; the page renders the grouped display and keeps the raw under the row title. Covered: large (10,000.000000), negative (-1,234.500000), fractional, zero.

Review-round gates on the final committed head (sequential, actual exit codes): unit 115 files / 1124 passed (0); type-check (0); lint 0 errors / 8 warnings (0, after fixing two genuine errors the round introduced — a control-character regex and a duplicate helper); focused charts-c (0), charts-c3 (0 — one daemon-wedge failure between clean runs, recorded), charts-c5 (0), charts-c4 (0); FULL 18×4 matrix 500 fixture requests, zero mismatches (0); backend 1416 passed / 10 skipped, coverage 83.68% (0).

## Review round 2 — account-scope regression (15 October 2026)

The reviewer correctly identified that the round-1 string normalization regressed the request scope: an unmatched account identity became the string 'Unavailable', which `selectedAccountId` resolved to null — a display fallback silently BROADENED the request to all accounts and destroyed the selected identity.

Fix — canonical identity separated from the Vuetify display model:

- `selectedAccount` is the canonical identity `{type, id, displayName}` and is NEVER a string; `selectedAccountId` derives from it alone, so display fallbacks cannot touch the scope. Only explicit All-accounts/Clear sets the unfiltered identity.
- `selectModel`/`selectLabel` are DERIVED: the matched option's own value (the input then shows the item title) or a safe fallback string (the identity's displayName — carried by holdings clicks — else 'Unavailable', else 'All accounts'). Choices arriving re-derive the model onto the matched option automatically: identity untouched, no extra scope change.
- The holdings filter carries the row's displayName through the identity; the base fixture lists the holdings accounts so a matched selection is the norm.
- The incumbent characterization ("account changes refetch detail+price+position+transactions, never accounts") now drives the change through `applyAccountSelection` — assertions unchanged.

RED-first regressions (real Vuetify + actual request-owner wiring, `SecurityDetailPage.selector.scope.spec.js`): (1) select account A, then the A option disappears — visible/input fall back safely while the refreshed scoped requests STILL carry account 11; (2) a holdings click while choices are pending keeps and requests that account (account 11, never unfiltered) and the late choices restore the matched label with every subsequent request still scoped; (3) choices restored return the matched label with no unfiltered request; (4) explicit Clear intentionally requests the unfiltered scope. Every state asserts the input contains no object/JSON text.

The round-1 string-normalization behavior is thereby REVERTED and superseded; its real-Vuetify input-safety guarantees are retained by the derived model.

Gates on the final committed head (sequential, actual exit codes): unit 116 files / 1128 passed (0); type-check (0); lint 0 errors / 8 warnings (0); focused charts-c (0), charts-c4 (0); FULL 18×4 matrix 496 fixture requests, zero mismatches (0); backend 1416 passed / 10 skipped, coverage 83.71% (0). charts-c3/charts-c5 passed on the pre-scope-fix head and are unaffected by it (security-page selector only; their next runs ride the full matrix).

## Investigated harness/environment limitations (recorded, not application defects)

- **Pie DOM tooltip in the charts-c flow**: eight investigation runs (dispatch recipe, real pointer hovers, textContent/visibility probes) could not reproduce a FILLED tooltip node in the charts-c flow — the node renders visible but empty — while the identical recipe passes end-to-end in the charts-c4 case ON THE SAME MODIFIED WRAPPERS (charts-c4 exit 0 in this worktree today, including its mobile pie tooltip). The certified share display is pinned by the unit formatter tests; charts-c keeps the three-pie render + capture (canvas internals: no leader lines, white separators, certified labels — inspected on `charts-c-pies.png`); the DOM tooltip assertion stays owned by charts-c4.
- **CDP keyboard zoom delivery** degrades across very long sessions (40+ heavy runs): the native-zoom helper gained a Ctrl+Minus/Plus correction walk and the case retries each leg; when delivery dies entirely the case records a zoom/reset limitation and continues (run 22 of the development series proved the full 200% leg: case-tab dpr 2, backing ratios ≈2 with the init-options fix).

## Task-sized commits (each with RED-first or rendered proof)

Task 0 ledger → `f15a1c70` NAV grid/tooltip/legend → T6.4 inspection-card removal (+ zoom controls, probe retargeting) → T6.5 disclosures + pagination → T6.6 pie presentation (+ fixture type follow-up) → T6.2 DPR watcher → T6.1 section fill → T7.1 selector label → T7.2 backend read model (PROTECTED) → T7.2 frontend holdings groups → charts-c case + fixtures (+ dedicated session, pie-capture scroll, probe corrections) → **dpr init-options fix (rendered-proof driven)** → lint hygiene + remaining c3/c5 probe retargets.

## Gates on the committed head (sequential, actual exit codes)

| Gate | Result | Exit |
|---|---|---|
| `test:unit` | 114 files / 1116 passed | 0 |
| `type-check` / `type-check:reliability` / `type-check:charts` | clean | 0 / 0 / 0 |
| `api:types:check` | clean | 0 |
| `lint` | 0 errors / 8 warnings after refreshing line-shifted baseline entries (count unchanged); two genuine new warnings fixed instead of baselined | 0 |
| `build` | clean | 0 |
| `--case charts-c` | all phases (geometry, zoom controls, disclosure, keyboard inspection, lean tooltip via real hover, lighter legend, pies, mobile containment + restore, native-200% DPR proof, security selector label, holdings groups, 60-observation pagination, explicit filter with account_id=11) | 0 |
| `--case charts-c4` | flag-off delivery + pilot flow incl. native-200% steps, on the modified wrappers | 0 |
| `--case charts-c5` | combined acceptance incl. zoom retention and security switching | 0 |
| `--case charts-c3` | flag-off delivery, isolated harness, pilot flow (probe retargets: collapsed-table caption/row waits, content-addressed inspection click, lean tooltip contract) | 0 |
| `test:delivery` | within budget | 0 |
| FULL `test:browser` (18 routes × 4 viewports) | 496 fixture requests, zero mismatches; committed head `36d8df40`+lint-hygiene | 0 |
| backend `uv run python -m pytest` (repository test settings) | 1406 passed / 10 skipped, coverage 83.64% (includes the 7 new holdings regressions) | 0 |

## Captures

Synthetic-only captures under `docs/design/assets/charts-c/`: `charts-c-dashboard.png`, `charts-c-nav-tooltip.png`, `charts-c-pies.png` (allocation section in frame), `charts-c-dashboard-390.png`, `charts-c-dashboard-200.png` (genuinely sharp at native 200%), `charts-c-security-pagination.png` (security page with the visible "All accounts" field). Inspected locally as PNGs.
