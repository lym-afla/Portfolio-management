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
