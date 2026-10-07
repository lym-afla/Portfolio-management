# C4 — allocation pies and security histories: evidence

Status: implemented, awaiting review. Branch `codex/allocation-security-charts-c4`
(base `8f1b0aba`, the PR #58/D7 integration plus this handoff). Draft PR into
`codex/frontend-modernization`; not merged, no deployment. ECharts stays
default-off for NAV, allocations and security histories; C5 owns default-on
rollout and Chart.js removal.

Sections: [1. Task 0 wire inventory](#1-task-0-wire-and-behavior-inventory) ·
[2. Transport and lifecycle](#2-transport-and-lifecycle-task-1) ·
[3. Allocation pies](#3-three-solid-allocation-pies-task-2) ·
[4. Security histories](#4-security-priceposition-histories-task-3) ·
[5. Gates and delivery](#5-gates-lazy-loading-and-rendered-acceptance-task-4) ·
[6. Deviations and limitations](#6-deviations-and-limitations)

## 1. Task 0 wire and behavior inventory

All references are to base `8f1b0aba`. Backend files were read, never modified.

### 1.1 Endpoints and negotiation

| Endpoint | Method | v2 trigger | Legacy shape | v2 shape |
|---|---|---|---|---|
| `/dashboard/api/get-breakdown/` | GET | `chart_contract=2` query param | `{assetType:{data,percentage}, assetClass:{…}, currency:{…}, totalNAV}` | same object plus `chartV2: {assetType, assetClass, currency}` — three allocation documents, one per dimension (`backend/dashboard/views.py:161-282`) |
| `/dashboard/api/get-nav-chart-data/` | GET | `chart_contract=2` | `{labels,datasets,currency,…}` | `{…legacy, chartV2}` (C2/C3, unchanged) |
| `/database/api/securities/<id>/price-history/` | GET | `chart_contract=2`; params `period` (default `"1Y"`); **no `account_id` parameter exists** — the handler never reads one (`backend/database/views.py:136-183`) | bare JSON array `[{date:"YYYY-MM-DD", price:<float>}]` (`JsonResponse`, DjangoJSONEncoder float) | `{"legacy":[<same floats>], "chartV2":<price document>}` (DRF response) |
| `/database/api/securities/<id>/position-history/` | GET | `chart_contract=2`; params `period` (default `"1Y"`), optional `account_id` (single local account filter) | bare JSON array `[{date:"YYYY-MM-DD", position:"<decimal string>"}]` — explicitly stringified pre-response so the DRF encoder cannot emit floats (`backend/database/views.py:267-272`) | `{"legacy":[<same strings>], "chartV2":<position document>}` |

- `_requested_chart_contract` (both `dashboard/views.py:46` and
  `database/views.py:59`): absent → legacy; anything but `"2"` → HTTP 400
  `INVALID_CHART_QUERY`, non-retryable. No silent downgrade server-side.
- Frontend negotiation is one request per fetch with `chart_contract=2`
  always present (matches the C2 NAV precedent). A response without v2 is
  honest `legacy_only`; a present-but-malformed `chartV2` is an error.
- The breakdown v2 map is all-or-nothing: one request yields all three
  documents (`dimensions = {"assetType": "asset_type", "assetClass":
  "asset_class", "currency": "currency"}`, `dashboard/views.py:212-214`).
  The dashboard keeps exactly one breakdown fetch for the three cards.

### 1.2 Document shapes (backend authority `backend/services/charts.py`)

- **Allocation** (`build_allocation_document`, lines 1133-1267): one sampling
  period keyed `allocation:<dimension>:<ISO date>`; one `category_nav` money
  series (reporting currency, `plotDivisor "1"`) per category, id
  `<dimension>:<code>` (asset_type/asset_class codes validated against the
  authoritative enums, `charts.py:162-181`; identity failure is a non-retryable
  500 — `dashboard/views.py:225-238`); `allocations` in deterministic server
  rank order (Decimal amount desc, then key); `allocationSummary` carries
  `dimension`, reporting-money `unit`, `denominator` (full reporting NAV),
  `totalShare` (raw ratio `1` only when mathematically applicable) and
  `pieEligibility` ∈ `eligible | signed | nonpositive_total | incomplete |
  nonpartitioning`; `totals: [denominator]`. Eligibility requires
  partition `complete` plus ok denominator/totalShare/amounts/shares
  (frontend parser re-checks structurally, `parseChartEnvelope.ts:484-496`).
  Eligibility never changes an amount, share or denominator.
- **Price** (`build_security_price_document`, lines 1270-1336): one period per
  `Prices` row keyed `security:<id>:price:row:<pk>` (row identity survives
  same-date prices); single series `security:<id>:price`, metric `price`, axis
  `price`; unit is `percent_of_nominal` for bonds (stored scale preserved:
  value/plotValue `98.500000`, display `98.5% of nominal`) or `money` in the
  **instrument** currency (never the reporting currency; the document parser
  enforces the instrument/reporting distinction by skipping the currency match
  for price/position series, `parseChartEnvelope.ts:179-185`); empty history →
  `outcome:"empty"` with the identified series and zero points.
- **Position** (`build_security_position_document`, lines 1339-1388): one
  period per event keyed `security:<id>:position:opening:<date>` (the
  start-of-window snapshot, present only when a period start exists) or
  `security:<id>:position:row:<transaction pk>`; **same-date transactions stay
  separate ordered entries** under distinct keys; single series
  `security:<id>:position`, metric `position`, axis `quantity`, exact stored
  precision (crypto `0.000116590`); empty history → `outcome:"empty"` with the
  identified zero-point series.
- Context for allocation documents: the requesting user's global selection,
  the resolved account ids, the request's effective date, reporting currency
  and digits (`dashboard/views.py:69-79, 211-220`).
- Context for security documents (`database/views.py:82-97`): the user's
  **global** selection and reporting currency/digits (not the page's local
  account filter or the instrument currency), the request's effective date,
  and `accountIds` = the local filter for position (`[account_id]`/`[]`) and
  `[]` for price. The local account filter and instrument currency are
  therefore request/response semantics that are NOT comparable against the
  committed global context; only selection type/id, date, currency and digits
  are.

### 1.3 Effective-date and period rules

- Breakdown/effective date: the middleware-provided `effective_current_date`
  is the document context date; the allocation period end equals it.
- NAV (unchanged C2/C3): document context date equals the requested `dateTo`
  (historical ranges valid).
- Security histories: the request has `period` (`7d|1m|3m|6m|1Y|3Y|5Y|ytd|All`,
  `TimelineSelector.vue`, `core/date_utils.py:41-71`), never an explicit
  end date; the document context date is the request's effective date. The
  frontend therefore validates `document.context.effectiveDate` against the
  committed effective date captured when the query was issued (NOT the NAV
  `toDate` rule). The v2 price/position period windows match the legacy
  handler's filters exactly (`date__lte` effective date, `date__gte` start).
- Legacy price float: the legacy price history renders
  `float(price.price)` (DjangoJSONEncoder float in a JsonResponse). The v2
  document captures the raw Decimal strings before that float serialization
  (`charts.py:1283-1295`). The C4 legacy projection preserves the float wire.

### 1.4 Incumbent frontend behavior to preserve (characterized)

- `DashboardPage.vue:194-198` one `getDashboardBreakdown` request per
  initial/context/refresh trigger feeding all three cards;
  `BreakdownChart.vue` renders Chart.js horizontal bars sorted descending and
  a table whose total percentage is hardcoded `100%` and whose total NAV cell
  is the legacy `totalNAV` string (`BreakdownChart.vue:32-35`). The incumbent
  presentation is the C4 fallback/rollback path and stays byte-identical when
  the allocation gate is off.
- `useSecurityDetail.ts` (D7 owner): five resources, characterized triggers —
  price+position refetch on `[canRead, refreshTrigger, securityId,
  selectedAccountId, selectedPeriod]`, sync invalidation on route-id change,
  transactions page reset on id/account/period change. The C4 rewiring keeps
  every trigger, the snapshotting and the invalidation untouched; only the two
  history fetchers switch transport (one `chart_contract=2` request each, the
  legacy projection derived from the same response).
- `SecurityDetailPage.vue` chart presentation (Chart.js time axis, per-period
  tick units, y-axis titles `Price (<instrument currency>)` / `Position`,
  carry-forward of the last known point to the effective date,
  `SecurityDetailPage.vue:375-437`) is the incumbent path that stays active by
  default and as the explicit user-chosen fallback.
- Known incumbent quirk kept as-is (recorded, not fixed): the legacy position
  table rows and chart points use the server order without de-duplication —
  same-date events render as separate points at one x coordinate.

### 1.5 Baseline gates (pristine base `8f1b0aba`, this worktree)

Node v24.20.0 portable (ignored `temp_files/` in the main checkout), all exit
codes actual:

| Gate | Result |
|---|---|
| `npm run test:unit` | exit 0 — 92 files / 857 passed |
| `npm run type-check` | exit 0 |
| `npm run type-check:reliability` | exit 0 |
| `npm run type-check:charts` | exit 0 |
| `npm run api:types:check` | exit 0 |
| `npm run lint` | exit 0 (0 errors / 8 warnings, unchanged baseline) |
| `npm run build` | exit 0 |
| backend `uv run python -m pytest` (test settings) | exit 0 — 1386 passed / 10 skipped |

Recorded in this branch's Task 0 commit; the characterization inventory above
is the committed Task 0 deliverable together with the fixtures already merged
in C2 (`frontend/src/features/charts/__tests__/fixtures.ts` allocation and
security documents, extended by the C4 tasks where new states are needed).

## 2. Transport and lifecycle (Task 1)

- `contracts.ts`: `BreakdownQuery`/`AllocationResult` (one request, three documents), `SecurityHistoryQuery`/`LegacySecurityHistory`/`SecurityHistoryResult`. `parseChartEnvelope.ts` gained `parseAllocationEnvelope` (dimension map pinned `assetType→asset_type`, `assetClass→asset_class`, `currency→currency`; missing/extra/wrong dimensions rejected; legacy card fields validated as lossless string records) and `parseSecurityEnvelope` (`{legacy, chartV2}` wrappers; bare arrays stay honest `legacy_only`; per-kind legacy row shapes — price rows carry finite numbers, position rows strings).
- `chartApi.ts`: `fetchBreakdownChart` (one `chart_contract=2` GET of `/dashboard/api/get-breakdown/`) and `fetchSecurityHistory` (one `chart_contract=2` GET per history; the price endpoint never carries an `account_id`, position carries it only when a local filter is set). Security/breakdown documents answer the request's committed effective date and the requested security identity — never the NAV `toDate` rule — while instrument currencies stay untouched by the reporting-currency check.
- `rendererPolicy.ts`: independent default-off gates `VITE_ALLOCATION_ECHARTS_ENABLED` / `VITE_SECURITY_ECHARTS_ENABLED`, enabled only for the exact string `'true'`; the NAV gate is untouched.
- `useBreakdownChart.ts`: the `useNavChart` pattern (shared runner stack, detached frozen snapshots, bounded once-per-episode mismatch reconciliation through the existing reliability store).
- D7's `useSecurityDetail` remains the single owner: the two history fetchers negotiate v2 through the new transport with identical triggers, snapshots and invalidation; the characterized legacy projections (price floats, position strings) come from the same response. A history context mismatch surfaces as the owner error with NO automatic reconcile (D7 behavior preserved, bounded by construction).

## 3. Three solid allocation pies (Task 2)

- `buildAllocationOption.ts`: one pie series (`radius: [0, '68%']`, `selectedMode: false`, no built-in legend) per parser-certified eligible document; slices in server rank order; colors from the stable server-ID hashes shared with NAV category series; `toPlotNumber` only at the geometry boundary; tooltips carry exact amount/share/denominator/totalShare displays (HTML-escaped) and never ECharts' derived percent; ineligible documents return `null` with a reason derived from the server-certified `pieEligibility`.
- `AllocationLegend.vue`: highlight/focus-only HTML buttons (focus, hover and click set `focusedSeriesId`; blur clears); aria labels announce the exact server amount and share; no visibility toggles and no selection — nothing can hide a slice or renormalize geometry.
- `AllocationDataTable.vue`: every server row in rank order (signed, zero, partial and unavailable rows verbatim with status/reason/knownSubtotal), plus a Total row fed only by the backend `denominator`/`totalShare` — no hardcoded 100% on the modern path.
- `AllocationChart.vue` + lazy `EChartsAllocation.vue`: PieChart registration, legend focus → `highlight`/`downplay` dispatch, recoverable rendering failures (retry / explicit user-chosen legacy fallback through the `#fallback` slot backed by the same accepted payload), the certified reason for ineligible documents.
- `BreakdownChart.vue` gained a `chartDocument` prop: non-null switches the card's chart/table tabs to the modern composition; null keeps the incumbent bars and table byte-identical (the rollback path). The DashboardPage wires one `useBreakdownChart` request to all three cards, shows the legacy-only capability notice when the gate is on, and passes per-card documents only while the gate is on and the result is v2.

## 4. Security price/position histories (Task 3)

- `buildSecurityOption.ts`: category axis keyed by server period identity (same-date events stay distinct categories), unsmoothed price lines, step-end position lines, y-axis names from series unit metadata (instrument currency / `% of nominal` / quantity) with values never rescaled (bond 98.5 plots as 98.5, crypto `0.000116590` exactly); positions start at zero (incumbent parity); view-only inside+slider zoom normalized to server period keys (NAV pattern); tooltips render exact displays with status/reason/knownSubtotal (HTML-escaped).
- Effective-date carry-forward is presentation-only: appended only when the last observation is ok and strictly earlier than the request's effective date, axis-labeled `<date> · carried forward`, tooltip-annotated with its source observation date, and never entered into the validated document or the observed-point table (`securityCarryForwardKey` exported for evidence).
- `SecurityDataTable.vue`: every observation row under its server period key — duplicates included — statuses verbatim, no carry-forward rows.
- `SecurityHistoryChart.vue` + lazy `EChartsSecurity.vue`: empty documents show a no-data notice instead of an empty canvas; rendering failures are recoverable (retry / explicit user-chosen fallback through `#fallback`); the page mounts it through the D7 owner's own negotiated results only while `VITE_SECURITY_ECHARTS_ENABLED=true` — legacy_only keeps the incumbent Chart.js charts unchanged, with no new request owners.

## 5. Gates, lazy loading and rendered acceptance (Task 4)

- Unit/regression suites: `remainingChartApi.spec.ts` (40 cases), `remainingChartIntegration.spec.ts` (13 cases — breakdown lifecycle, bounded reconciliation, security owner transport semantics, dashboard and security page wiring under both gate states), `allocation.spec.ts` (32 cases), `securityHistory.spec.ts` (22 cases). D7's `detail.spec.ts`/`incumbent.spec.js`/`DetailRequests.spec.js` pins were re-bound through the new transport with their characterized signatures unchanged. RED was observed for each suite before its implementation (40 transport failures at the pristine base, then module-absent import failures, then 32 and 22 failures).
- `tests/browser/charts-c4.mjs` + a `chartsC4Flow` fixture-server mode (scenario-switchable breakdown/security envelopes: v2, signed, incomplete, legacy, malformed, mismatch; security v2/legacy/malformed-price/outrange-price/empty). The case runs two phases:
  - **Flag-off artifact**: incumbent allocation bars and security charts, no exact tables, and a provably ECharts-free loaded module graph on /dashboard, /database/securities/1 and /login.
  - **Flag-on artifact** (all three gates on): three visible solid pies beside the NAV pilot; per-card exact tables; legend focus issuing zero requests and preserving every table row, share and the denominator byte-for-byte; the signed state (certified reason + complete signed table, parenthesized negative display and -25.0% share verbatim); malformed v2 → section error with exactly one request and no retry; legacy-only → honest notice + incumbent bars; stock/bond/crypto histories with exact tables (duplicate-date position rows included; bond percent-of-nominal displays; crypto 0.000216590 precision); independent price/position settle under a price-only malformed envelope; renderer failure → explicit fallback; mobile 390px legend/tab hit-testing via elementFromPoint; mobile tooltips (allocation + security) hit-tested fully visible below the fixed header; per-route delivery measurements.
- Delivery (gzip JS+CSS over the observed route graph, R7 helper): dashboard flag-off 343,194 / flag-on 549,046 bytes; security detail flag-off 350,606 / flag-on 539,550 bytes (recorded in `tests/browser/artifacts/charts-c4-delivery.json`). The flag-off graphs contain no echarts files; the flag-on graphs do (lazy chunks only).
- Captures under `docs/design/assets/charts-c4/`: `c4-dashboard-pies.png` (three solid pies + legends + NAV pilot alongside), `c4-signed-table.png` (certified ineligible path: complete signed table, no misleading pie), `c4-stock-histories.png` (unsmoothed price line, USD axis name, carry-forward extension), `c4-bond-history.png` (`% of nominal` axis, 99.x values never rescaled), `c4-security-mobile-tooltip.png` (390px: tooltip with exact displays, fully visible below the app bar, exact table beneath). All captured from the synthetic fixtures only; each was opened and inspected.

## 6. Review round (PR #59)

All three reviewer findings were corrected with regressions observed RED first (8 failures across the three suites against the pre-fix sources).

1. **Account-scope validation** (transport): `fetchSecurityHistory` now validates the document's `context.accountIds` against the request's local filter — `[accountId]` for a filtered position query, `[]` for an all-accounts position query and for every price query (the price endpoint has no account parameter). A mismatch is a `ChartContextMismatchError` with exactly one request and no retry. Regressions: a position request for account 5 answering `[7]`, an all-accounts request answering `[7]`, a price document answering `[7]` (all reject), and the answering-`[5]` happy path (accepts).
2. **Zoom axis model + page wiring**: `securityAxisKeys(document)` is now the single source of truth for the plotted axis (observed keys plus the carry-forward endpoint); the option's zoom bounds, the dataZoom event normalization and the interaction reconciliation ALL map over that list, so percentages and axis positions can never disagree about the carry-forward endpoint. `SecurityDetailPage` now owns one interaction per section, passes it down and reconciles it on every document change, so zoom survives compatible refreshes. Regressions: datazoom over a four-key axis maps 50–100% to row 3 + the carry-forward key; a carry-forward viewport survives reconciliation; the page-level emit → state → option round-trip (start ≈ 33.33/end ≈ 66.67) and its persistence across a compatible refresh.
3. **Loading treatment**: the page renders the incumbent skeleton for BOTH renderers whenever the section's history query is pending — a period change can no longer leave the previous period's chart and table looking current. Regression: with the history responses parked, the pending period change shows skeletons and no exact tables; resolving restores them.

Gates after the corrections (actual exit codes, tested head): `test:unit` 96 files/973 passed (0); `type-check`/`type-check:charts`/`type-check:reliability` (0); `api:types:check` (0); `lint` 0 errors/8 warnings (0); `build` (0); `--case charts-c4` (0, captures retaken and re-inspected); `--case brokers-security-d7` (0); FULL `test:browser` 18 routes × 4 viewports, zero mismatches (0). Delivery re-measured: dashboard flag-off 343,262 / flag-on 549,104 bytes gzip; security 350,771 / 539,705.

## 6. Deviations and limitations

- **showTip acceptance hook**: `EChartsAllocation`/`EChartsSecurity` attach a `__c4DispatchAction` function to their host element. The charts-c4 case drives `showTip` through the real instance so the containment probe exercises the production formatter and placement callback; headless pointer sweeps do not reliably trigger the pie/line canvas hit-test. The shared pointer-path machinery is proven by the charts-c3 NAV case. The hook is inert in production (never called by app code).
- **Security zoom is view-only and not persisted**: NAV keeps a controlled viewport across compatible refreshes; the security histories reset the zoom window when a new document arrives (the page does not lift the interaction state). Zoom never issues requests or changes values.
- **Breakdown v2 is all-or-nothing**: one negotiated response carries all three documents; a malformed document fails the whole breakdown section with the C2 error semantics (no silent per-card downgrade). This mirrors the NAV malformed-v2 precedent.
- **tsconfig.charts.json** scopes `remainingChartIntegration.spec.ts` out of the strict charts project (documented in the config): its import graph is the whole legacy app and would drag pre-existing non-strict sources into the strict check. The spec stays type-checked by the main `type-check` via `src/**/*` — the same recorded scoping as the C2/D6 integration specs.
- **Legacy legacy-row validation**: the security envelope parser validates the characterized legacy row shapes (price = finite numbers, position = strings); a deviation from that wire contract is now a loud error instead of silently misleading charts.
- **Inherited focused-case failures (reproduced at the pristine base)**: the `recovery` and `dialog-recovery` browser cases fail on this machine with the same signature at base `8f1b0aba` and on this branch — a Retry click landing while a Vuetify overlay scrim is still in its leave transition (`v-overlay__scrim.fade-transition-leave-active` covering the click point). Both were rerun directly on the branch and at the pristine base in this worktree with identical results, so they are not C4 regressions; they are recorded for the reviewer and left to the harness owners. Every other focused case (charts-c2, charts-c3, charts-c4, brokers-security-d7, imports-d6, layout, context, dates, requests, dialogs, d4, d5, settings-account) and `test:delivery` exit 0.
- **Review round 2 (8 October 2026)**: the reviewer's context-reset crash is fixed — when a context or route event invalidates the histories the page watchers reset the per-section interaction (a null document can no longer reach reconciliation, and zoom cannot leak into the replacement documents); the strengthened refresh regression now triggers a real data refresh, awaits the replacement responses, and asserts the zoom survives on the re-rendered chart. RED observed first (the reviewer's exact `TypeError: Cannot read properties of null (reading 'periods')` through the mounted page). Gates: unit 96 files/974 passed (0), type-checks ×3/api/lint 0/8/build (0), `--case charts-c4` (0), FULL browser 18×4 zero mismatches (0).
- Out of scope, unchanged: backend/financial code, NAV behavior and its flags, D7 broker fixes and mobile pagination, C5 (default-on rollout, Chart.js removal), D8, screen-reader audits (owner amendment of 5 October 2026).
