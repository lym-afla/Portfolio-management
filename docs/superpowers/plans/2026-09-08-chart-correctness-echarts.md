# Chart Correctness and ECharts Implementation Plan

## Scope amendment — 5 October 2026

The owner has removed dedicated screen-reader support work and real assistive-technology audits (NVDA, JAWS, VoiceOver or equivalent) from the modernization scope. They are not acceptance criteria, release blockers or deferred D8 work. This amendment supersedes earlier screen-reader requirements and historical references assigning their audit to D8, including prior handoffs and evidence records. Past statements that no such audit was performed remain historically accurate; do not present them as outstanding acceptance gaps.

Retain keyboard navigation, focus entry/return, readable labels, contrast, responsive layouts, native 200% zoom, visible/hittable controls, semantic HTML and exact-value chart tables. Preserve existing ARIA/semantic markup and tests; this scope change does not request application-code removal. D8 still verifies visual quality, keyboard usability, responsive behavior and workflow correctness. General accessibility references in these plans apply to those retained checks, not a screen-reader certification or dedicated compatibility project.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the two confirmed chart-data defects in separate financial PRs, establish an exact compatible chart contract, and migrate the six live charts only after an accessible ECharts NAV pilot demonstrates financial and behavioral parity.

**Architecture:** Django retains all financial calculation ownership and adds opt-in versioned metadata beside unchanged legacy fields. A typed feature boundary validates values, dates, identity and status; a replaceable renderer uses the reliability workstream's shared request runner and committed portfolio context. Chart.js remains the default and rollback renderer until the ECharts acceptance gate passes.

**Tech Stack:** Existing Django/DRF, Decimal, uv, pytest, Vue 3.5.11, TypeScript, Pinia, Vuetify, Vitest and Chart.js 4.4.4/vue-chartjs 5.3.1; ECharts/vue-echarts dependencies are proposed only at Task C3 and must be pinned to compatible released versions at execution time.

**Spec:** [Accepted frontend audit](../../audits/2026-09-08-frontend-audit.md). Related existing constraints: [tables and visual redesign](../specs/2026-08-18-tables-visual-redesign-design.md). Supporting audit: ignored `temp_files/frontend-audit/chart-audit-notes.md` (evidence, not a prerequisite for understanding this plan).

## Global Constraints

- "Keep Vue, Vite, Pinia, and Vuetify initially."
- "Chart.js can already render the required charts; migration should earn its cost through better analytical interaction."
- "Any change affecting financial outputs requires the project's numerical regression evidence and human approval."
- "Do authoritative money math with Decimal on the backend; conversion to JavaScript numbers belongs only at the plotting boundary."
- "Missing returns are gaps rather than false zero values or bridged lines."
- "Preserve grouped columns, totals, server-side pagination, sticky identity columns, column selection and chart/table alternatives."
- "Remove old chart dependencies only once all live uses are migrated."
- The user's current choice is three **solid pie charts** titled **Asset Type**, **Asset Class** and **Currency**. This supersedes the earlier horizontal-bar design for these allocation cards. Doughnuts are an optional later design choice. The separate NAV chart keeps its stacked bars and two IRR lines.
- An allocation pie requires a complete, nonnegative partition of a positive reporting NAV. Signed, incomplete, unknown, nonpartitioning or nonpositive-total data uses an explanatory chart state and the full signed/status-aware table. Never take absolute values, drop negative values, invent a residual category or claim a false 100%. The current Chart.js allocation bars remain a transitional rollback path, not fulfillment of the final pie requirement.
- This document is a plan only. Preparing it authorizes no application code, dependency, database, deployment or runtime changes.
- Read AGENTS.md, `.memory-bank/Rules for AI Coding Agent.md`, `Product Overview/Portfolio NAV.md`, `Steerings/Calculation Conventions.md` and `Tech details/NAV Function and FX Flow.md` before execution. Current source locations supersede stale documentation paths.
- Use Decimal, ROUND_HALF_UP and existing precision rules. Preserve IRR calculation, cash-flow membership, FX date choice, NAV valuation, bond/option rules and all-time/first-point behavior. F1 changes point/date alignment and F2 changes the contribution interval inclusion rule; neither changes a valuation or IRR formula. F3 permits a separate financial fix only if its bounded investigation confirms a percentage-scale defect.
- Financial changes, including protected metadata instrumentation, must have a regression fixture and a PR with `needs-approval`; use `area:calculations` and `risk:high` where protected code is touched. Human review/APPROVE is required before merge, not before preparing tests, code for review, or this plan. Do not merge protected changes autonomously.
- Preserve legacy response keys, types, grouping and endpoint defaults. Do not change duplicate-name account aggregation while adding identity metadata.
- Absence does not prove zero exposure. Unknown valuations remain unknown; confirmed zero exposure is an explicit zero. Partial known subtotals must not be advertised as complete NAV.
- Preserve decimal strings through transport, state, adapters, tables and tooltip models. Never reconstruct decimal values from currency-formatted strings, percentages or chart coordinates.
- Do not recover ISO dates from display labels or derive persistent category IDs from label text/index. Missing identity/date information requires the C1 API contract.
- No CSV/image export UI, dark-mode project, i18n project or table redesign is included. Data-table access is mandatory; exact raw/date metadata makes a later export possible. Preserve existing two-row grouped tables and sticky identity behavior.
- Browser automation uses `agent-browser`; run `agent-browser --help` at execution start. Backend commands run from `backend/` with `uv run`; frontend commands below use `npm --prefix ../frontend` from that directory. Use Node 24.20.0 and engine range `>=24.20.0 <25`, as established by reliability Task R1; do not use the audit's failing Node 26 localStorage environment.
- New frontend modules, fixtures and tests in this workstream live under `frontend/src/features/charts/`. New backend files are tests only; keep production additions focused in the existing chart/view modules and the minimum necessary NAV diagnostics surface.

## Dependencies and review boundaries

Eight reviewable tasks: F1, F2, F3, C1, C2, C3, C4, C5. F1/F2/F3 are independent financial review units. C1 depends on the approved F1/F2 corrections for its regression baseline; raw percentage metadata may be prepared while F3 is investigated, but allocation rollout C4 waits for F3's explicit resolution. C2 depends on C1 and the reliability workstream's shared runner/context. C3 builds the NAV pilot, including its mandatory accessible controls and table. C4 migrates allocations to solid pies and migrates security charts. C5 changes defaults, observes the result, and only then considers removal.

The reliability workstream owns these interfaces; consume them, do not implement another request/state stack:

```ts
// frontend/src/composables/useLatestRequest.ts (owned by reliability plan)
import type { Ref, ShallowRef } from 'vue'
export function useLatestRequest<TParams, TData>(
  fetcher: (params: Readonly<TParams>, options: { signal: AbortSignal }) => Promise<TData>,
  snapshot: (params: TParams) => Readonly<TParams>,
): {
  data: Readonly<ShallowRef<TData | null>>
  error: Readonly<ShallowRef<Error | null>>
  loading: Readonly<Ref<boolean>>
  run(params: TParams): Promise<
    | { status: 'accepted'; data: TData }
    | { status: 'discarded' }
    | { status: 'failed'; error: Error }
  >
  invalidate(): void
}
// frontend/src/types/portfolioContext.ts and stores/portfolioContext.ts
// PortfolioContext includes revision, accountSelection (all/account/broker/group),
// effectiveCurrentDate:string|null, currency:string|null and digits.
// Consume its exported type; do not redeclare it here.
// Store exposes committed, isTransitioning, isReady, transitionError,
// changeContext and reconcileContext. Its verified committed state is authoritative.
```

`snapshot` must clone/freeze nested context and arrays. `run` passes AbortSignal and independently guards generations; only `accepted` results may trigger dependent side effects. `invalidate` aborts, advances generation and clears state. Block chart reads until isReady and not isTransitioning; refine nullable date/currency by runtime checks before constructing a query, without non-null assertions. Invalidate on context change and unmount. Mutating charts never changes account/date/currency context directly. R8's injected transport lands after R1 and before new consumers; import getApiTransport from services/http/client, never the legacy axiosConfig/store/router cycle.

## File ownership map

| File | Responsibility / task |
|---|---|
| `backend/services/charts.py` | F1 date index; F2 inclusive period start; C1 compatible chart contract assembly and Decimal formatting helpers |
| `backend/services/nav.py` | C1 optional diagnostics at existing omitted-valuation branches only; no financial formula change |
| `backend/services/performance.py` | F3 investigation, conditional isolated percentage correction if proven |
| `backend/core/formatting_utils.py` | F3 read/investigate caller contract; modify only if separately justified by the confirmed scale defect |
| `backend/dashboard/views.py` | C1 opt-in contract version, raw allocation metadata, explicit v2 errors |
| `backend/database/views.py` | C1 opt-in raw security history envelopes and instrument units |
| `backend/tests/unit/services/test_chart_alignment.py` | F1 Decimal date-gap regression |
| `backend/tests/integration/services/test_chart_contribution_boundaries.py` | F2 actual transaction query and chart decomposition regression |
| `backend/tests/unit/services/test_allocation_percentage_scale.py` | F3 bounded scale investigation and documented resolution |
| `backend/tests/integration/api/test_chart_contract_v2.py` | C1 legacy compatibility, identity, units, diagnostics, dates and errors |
| `frontend/src/features/charts/contracts.ts` | C2 validated chart DTO/model types |
| `frontend/src/features/charts/tsconfig.json` | C2 strict checking of new feature modules/tests |
| `frontend/src/features/charts/parseChartEnvelope.ts` | C2 runtime boundary validation |
| `frontend/src/features/charts/adaptLegacyNav.ts` | C2 typed legacy renderer passthrough; refuses invented identity/dates |
| `frontend/src/features/charts/chartApi.ts` | C2 chart transport using existing axios instance |
| `frontend/src/features/charts/useNavChart.ts` | C2 adapter to shared latest-request runner and committed context |
| `frontend/src/features/charts/renderBoundary.ts` | C3 sole decimal-string to JS-number plotting boundary |
| `frontend/src/features/charts/seriesStyles.ts` | C3 stable categorical/IRR style mapping using shared theme tokens |
| `frontend/src/features/charts/buildNavOption.ts` | C3 pure ECharts option construction |
| `frontend/src/features/charts/ChartHost.vue` | C3 renderer switch, mounted loading, independent fallback/error boundary |
| `frontend/src/features/charts/EChartsNav.vue` | C3 modular ECharts integration, controlled events and final cleanup |
| `frontend/src/features/charts/ChartLegend.vue` | C3 native HTML toggle buttons |
| `frontend/src/features/charts/ChartDataTable.vue` | C3 exact data/status/horizon alternative |
| `frontend/src/features/charts/ChartInspection.vue` | C3 shared tooltip/focus details using server display strings |
| `frontend/src/features/charts/NavChartPanel.vue` | C3 composition with responsive existing controls |
| `frontend/src/features/charts/buildAllocationOption.ts` | C4 allocation rendering from raw metadata |
| `frontend/src/features/charts/buildSecurityOption.ts` | C4 security time/price/quantity rendering |
| `frontend/src/features/charts/useSecurityCharts.ts` | C4 shared latest runner for security histories |
| `frontend/src/features/charts/AllocationChart.vue` / `SecurityHistoryChart.vue` | C4 integrations |
| `frontend/src/features/charts/rendererPolicy.ts` | C3/C5 default-off gates and deterministic rollback |
| `frontend/src/features/charts/__tests__/` | Co-located unit/component tests, fixtures and isolated dev rendering harness |
| Existing `DashboardPage.vue`, `NAVChart.vue`, `BreakdownChart.vue`, `SecurityDetailPage.vue` | Narrow wiring, replaced incrementally in C2-C4; coordinate shared dashboard changes with reliability/design owners |
| `frontend/package.json`, `frontend/package-lock.json` | C3 gated dependency introduction; C5 removal only after live-use audit |

## Task F1: Align category values to the complete sample index

**Status (30 September 2026):** Implemented/reviewed and merged into `codex/frontend-modernization` in PR #46, merge `607f5383`. Historical task steps below retain their specification; current overall progress is in the [durable tracker](2026-09-30-frontend-modernization-progress.md).

**Files:** modify `backend/services/charts.py:133-197,232-282`; create `backend/tests/unit/services/test_chart_alignment.py`.

**Interfaces:** retain `get_nav_chart_data(...)` response shape. Add keyword-only `sample_index: int` to internal `add_breakdown_data(...)` and pass `enumerate(dates)` index. Every new category gets a list of `None` with exactly `len(chart_data['labels'])` entries; assign only its observed index. Explicit Decimal zero remains zero. Existing leading/trailing padding must not prepend a second offset.

- [ ] Add the failing test using the actual helper, not a duplicated algorithm:

```python
from datetime import date
from decimal import Decimal
from services.charts import add_breakdown_data, fill_missing_historical_data

def test_category_reentry_keeps_its_date_and_unknown_gap():
    chart = {
        'labels': ['01-Jan-26', '02-Jan-26', '03-Jan-26'],
        'datasets': [
            {'label': 'IRR (RHS)', 'data': []},
            {'label': 'Rolling IRR (RHS)', 'data': []},
        ],
    }
    categories = {}
    for index, values in enumerate([
        {'Equity': Decimal('1000')}, {}, {'Equity': Decimal('3000')},
    ]):
        add_breakdown_data(
            chart, Decimal('0.1000'), Decimal('0.0200'), values,
            categories, date(2026, 1, index + 1), sample_index=index,
        )
    fill_missing_historical_data(chart, categories, 'D')
    equity = next(s for s in chart['datasets'] if s['label'] == 'Equity')
    assert equity['data'] == [Decimal('1'), None, Decimal('3')]
    assert all(len(s['data']) == 3 for s in chart['datasets'])
```

- [ ] Run `uv run python -m pytest tests/unit/services/test_chart_alignment.py -q`; first failure should be the new keyword interface, then the date-alignment assertion if the old append behavior survives.
- [ ] Implement the minimal indexed assignment:

```python
# Replace the existing category-branch call after enumerating the loop's dates:
add_breakdown_data(
    chart_data, IRR_value, IRR_rolling, breakdown_data, categories, d,
    sample_index=sample_index,
)
# In add_breakdown_data, when adding a category (insert dataset before the IRRs):
dataset = _create_dataset(
    key, [None] * len(chart_data['labels']), get_color(len(categories)),
    'bar', 'y', stack='combined',
)
# After locating the dataset by the current legacy label:
chart_data['datasets'][dataset_index]['data'][sample_index] = value / Decimal('1000')
```

Change the loop header to `for sample_index, d in enumerate(dates):`; preserve the existing NAV/IRR computation body around lines 134-188 apart from that index and call argument. Replace `fill_missing_historical_data`'s leading padding with length validation/trailing completion only; update all internal call sites found by `rg -n 'add_breakdown_data|fill_missing_historical_data' backend`.
- [ ] Add separate cases for late entry, repeated interior absence, explicit zero and negative value. Assert `[None, Decimal('0'), Decimal('-2')]` remains distinct. Missing category provenance is unknown at this stage; do not infer liquidation or missing price from absence.
- [ ] Run the targeted file and existing chart date tests: `uv run python -m pytest tests/unit/services/test_chart_alignment.py tests/unit/utils/test_utils.py -q`, then `uv run python -m pytest` before PR readiness.
- [ ] Prepare one financial PR with before `[1,3,null]`, after `[1,null,3]`, exact date fixture, changed files and checks. Label `needs-approval`; do not merge without human financial approval.

**Acceptance:** identical existing values and IRRs at their correct original sample dates; all arrays match date count; no manufactured zeros. This correction is the new reviewed baseline used by subsequent parity tests.

## Task F2: Include the first contribution day exactly once

**Status (30 September 2026):** Implemented/reviewed and merged into `codex/frontend-modernization` in PR #47, merge `71eaa1d7`. Historical task steps below retain their specification; current overall progress is in the [durable tracker](2026-09-30-frontend-modernization-progress.md).

**Files:** modify `backend/services/charts.py:193-194,414-459`; create `backend/tests/integration/services/test_chart_contribution_boundaries.py`.

**Interfaces:** `previous_date` currently means the next interval's inclusive first day (`previous endpoint + 1 day`). Keep that convention and change the query lower bound to `date__date__gte`. IRR already uses the inclusive start with opening NAV on the previous endpoint; do not change its arguments.

- [ ] Add a DB-backed regression with existing `user`/`account` fixtures. NAV and IRR are pinned only to isolate contribution classification; transaction filtering/FX and chart decomposition execute actual code:

```python
from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from common.models import Transactions
from services import charts

@pytest.mark.django_db
def test_february_first_deposit_is_contribution_not_return(user, account, monkeypatch):
    for day, amount in [(date(2026, 1, 31), '1000'), (date(2026, 2, 1), '100')]:
        Transactions.objects.create(
            investor=user, account=account, type='Cash in', currency='USD',
            date=datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc),
            cash_flow=Decimal(amount),
        )
    monkeypatch.setattr(charts, 'get_fx_rate', lambda *args: Decimal('1'))
    values = {date(2026, 1, 31): Decimal('1000'), date(2026, 2, 28): Decimal('1100')}
    monkeypatch.setattr(charts, 'NAV_at_date', lambda uid, ids, day, cur, breakdown: {'Total NAV': values[day]})
    irr_calls = []
    def pinned_irr(*args, **kwargs):
        irr_calls.append(kwargs.get('start_date'))
        return Decimal('0.0000')
    monkeypatch.setattr(charts, 'IRR', pinned_irr)
    result = charts.get_nav_chart_data(
        user.id, (account.id,), 'M', date(2026, 1, 31), date(2026, 2, 28),
        'USD', 'value_contributions',
    )
    values_by_name = {s['label']: s['data'] for s in result['datasets']}
    assert values_by_name['Previous NAV'][1] == Decimal('1')
    assert values_by_name['Contributions'][1] == Decimal('0.1')
    assert values_by_name['Return'][1] == Decimal('0')
    assert sum(values_by_name[name][1] for name in ['Previous NAV', 'Contributions', 'Return']) == Decimal('1.1')
    assert irr_calls == [None, None, None, date(2026, 2, 1)]
```

- [ ] Run `uv run python -m pytest tests/integration/services/test_chart_contribution_boundaries.py -q`; expect the contribution assertion to show zero instead of 0.1 on the current code.
- [ ] Change only the inclusive lower bound and explanatory naming/comment:

```python
if previous_date is not None:
    # previous_date is the first included day, not the previous sample endpoint.
    filter_conditions['date__date__gte'] = previous_date
```

- [ ] Add parameterized daily/monthly examples, cash-out `Decimal('-100')`, boundary/end-day flows and two adjacent intervals. A flow on each interval's first day and final day is counted exactly once. Add one effective-timezone midnight case using the project's configured date semantics; do not change global timezone rules to make the fixture pass.
- [ ] Run `uv run python -m pytest tests/integration/services/test_chart_contribution_boundaries.py tests/unit/calculations/test_irr_option_paths.py -q`, then `uv run python -m pytest` for the PR gate.
- [ ] Prepare a separate financial PR: NAV unchanged at 1,100; February contribution changes from 0 to 100; residual return changes from 100 to zero. Include fixture and human approval labels. Do not conflate with F1 or ECharts.

**Acceptance:** signed contributions agree with canonical transactions on the full inclusive period, opening NAV and both IRR horizons remain unchanged, cumulative mode still uses its existing all-history rule.

## Task F3: Resolve allocation percentage scale before migration

**Status (30 September 2026):** Implemented/reviewed and merged into `codex/frontend-modernization` in PR #48, merge `9b32d3d9`. Historical task steps below retain their specification; current overall progress is in the [durable tracker](2026-09-30-frontend-modernization-progress.md).

**Files:** inspect `backend/services/performance.py:303-320`, `backend/core/formatting_utils.py:258-280`, `backend/dashboard/views.py:146-166`; create `backend/tests/unit/services/test_allocation_percentage_scale.py`. Modify a production file only in a separate reviewed fix if the investigation confirms the defect.

**Interfaces:** establish one precise scale: raw share ratio `Decimal('0.25')`, display `25.0%` for amount 25 / complete positive NAV 100. Legacy formatted output is evidence to compare, not an authority that can redefine the unit.

Planning risk, not yet classified as a confirmed product defect: `calculate_percentage_shares` multiplies amount/NAV by 100, then calls `format_percentage`, whose documented ratio contract and implementation multiply by 100 again. The current chart also independently recomputes shares, so table/chart agreement must be tested.

- [ ] Add the bounded reproduction:

```python
from decimal import Decimal
from services.performance import calculate_percentage_shares
from core.formatting_utils import format_percentage

def test_quarter_allocation_is_twenty_five_percent():
    data = {'Total NAV': Decimal('100'), 'asset_type': {'Stock': Decimal('25'), 'Cash': Decimal('75')}}
    assert Decimal('25') / Decimal('100') == Decimal('0.25')
    assert format_percentage(Decimal('0.25'), digits=1) == '25.0%'
    calculate_percentage_shares(data, ['asset_type'])
    assert data['asset_type_percentage']['Stock'] == '25.0%'
```

- [ ] Run `uv run python -m pytest tests/unit/services/test_allocation_percentage_scale.py -q`. Record actual helper and API output for the same fixture. If the failure is scale-related, trace callers with `rg -n 'calculate_percentage_shares|format_percentage' backend` before choosing the correction location; do not globally change `format_percentage`'s ratio contract.
- [ ] If confirmed, prepare a separate financial fix retaining a ratio until the existing formatter, with Decimal edge fixtures for zero/nonpositive total and negative share. Preserve the current nonpositive-total unavailable rule unless separately approved. If not confirmed, record the actual tested scale and why the suspected double multiplication is inapplicable; retain the passing regression.

```python
# Conditional fix only if the test/caller audit confirms this caller's extra scale:
percentage = data_dict[key][item] / total_nav
data_dict[percentage_key][item] = format_percentage(percentage, digits=1)
```

- [ ] Run the targeted test and `uv run python -m pytest`; attach before/after display examples and response compatibility analysis to the separate `needs-approval` PR if a fix is needed.
- [ ] Record the approved result in the C4 review checklist. A migration cannot silently choose the chart's recomputation over the table's server value, or bless a known discrepancy as parity.

**Acceptance:** documented, tested raw ratio and percentage display contract, with human financial review for any correction. This is a bounded investigation prerequisite for C4, not permission for broader performance-formula cleanup.

## Task C1: Add an opt-in, exact chart contract without removing legacy responses

**Status (30 September 2026):** Not implemented; dependencies F1/F2/F3 merged. Next executor assignment: [C1 handoff](2026-09-30-chart-contract-v2-handoff.md).

**Files:** modify `backend/services/charts.py`, `backend/services/nav.py` (minimum optional diagnostics), `backend/dashboard/views.py`, `backend/database/views.py:90-178`; create `backend/tests/integration/api/test_chart_contract_v2.py`.

**Interfaces:** `chart_contract=2` requests a v2 envelope. Without it, endpoint keys/types/HTTP behavior remain unchanged during transition. On successful v2 NAV/breakdown responses, retain existing top-level fields and add `chartV2`; on v2 security histories return an object with the unchanged array in `legacy` and the ChartDocument in `chartV2`, because adding fields to a top-level list is incompatible. Client explicitly negotiates v2; no semantic version guessing.

The contract uses exact dates emitted from the actual calculation loop, stable source IDs and Decimal strings, including a pre-scaled plotting value so JavaScript never divides monetary values. Proposed types are implemented verbatim in C2:

```ts
import type { PortfolioContext } from '@/types/portfolioContext'
export type DecimalString = string
export type ISODate = string
export type Frequency = 'D' | 'W' | 'M' | 'Q' | 'Y'
export type NavMode = 'none' | 'account' | 'asset_type' | 'asset_class' | 'currency'
  | 'value_contributions' | 'value_contributions_cumulative'
export type ValueStatus = 'ok' | 'partial' | 'unknown' | 'not_available' | 'not_relevant'
export interface ChartValue {
  value: DecimalString | null       // raw complete value in the stated unit
  plotValue: DecimalString | null   // backend-scaled value; null for non-ok status
  knownSubtotal?: DecimalString     // permitted only for partial; never complete NAV
  status: ValueStatus
  reason: 'observed' | 'zero_exposure' | 'missing_price' | 'missing_fx'
    | 'omitted_valuation' | 'absent_unclassified' | 'solver_unavailable' | 'not_relevant'
  display: string                  // exact user-facing value, not parsed by client
}
export type ChartUnit =
  | { kind: 'money'; currency: string; plotDivisor: '1' | '1000' }
  | { kind: 'ratio'; plotDivisor: '1' }
  | { kind: 'quantity'; plotDivisor: '1' }
  | { kind: 'percent_of_nominal'; plotDivisor: '1' }
export interface ChartPeriod {
  key: string                     // server identity; unique even for repeated display labels
  endDate: ISODate                 // actual sampled endpoint, never reconstructed
  displayLabel: string
  interval: { startDate: ISODate | null; endDate: ISODate; kind: 'inception' | 'sample_interval' }
  partialPeriod: boolean           // calendar bucket incomplete, not valuation completeness
}
export interface ChartSeries {
  id: string                      // server-issued canonical identity
  label: string
  metric: 'nav' | 'category_nav' | 'opening_nav' | 'contributions' | 'return'
    | 'net_investments' | 'irr_inception' | 'irr_interval' | 'price' | 'position'
  role: 'bar' | 'line'             // Cartesian role; allocation slices use allocations below
  axis: 'money' | 'return' | 'price' | 'quantity'
  unit: ChartUnit
  points: readonly ChartValue[]
  category?: {
    kind: 'account_group' | 'asset_type' | 'asset_class' | 'currency'
    code?: string
    memberAccountIds?: readonly number[]
  }
}
export interface ChartDocument {
  version: 2
  kind: 'nav' | 'allocation' | 'price' | 'position'
  outcome: 'ready' | 'empty' | 'partial'
  context: { accountSelection: PortfolioContext['accountSelection']; accountIds: readonly number[];
    effectiveDate: ISODate; currency: string; digits: number }
  security?: { id: number; instrumentType: string } // required for price/position
  periods: readonly ChartPeriod[]
  series: readonly ChartSeries[]
  totals?: readonly ChartValue[]   // full NAV, never a frontend sum of selected bars
  allocations?: readonly { seriesId: string; rank: number; amount: ChartValue; share: ChartValue }[]
  allocationSummary?: {           // required with allocations when kind === 'allocation'
    dimension: 'asset_type' | 'asset_class' | 'currency'
    unit: Extract<ChartUnit, { kind: 'money' }>
    denominator: ChartValue       // full reporting NAV, never a selected/visible subtotal
    totalShare: ChartValue        // ratio 1 only for a known complete positive-NAV partition
    pieEligibility: 'eligible' | 'signed' | 'nonpositive_total' | 'incomplete' | 'nonpartitioning'
  }
  partition: 'complete' | 'legacy_non_partitioning' | 'unknown'
}
export interface ChartErrorBody {
  error: { code: 'INVALID_CHART_QUERY' | 'CHART_CALCULATION_FAILED'; message: string; retryable: boolean }
}
```

Dates and strings above are runtime-validated in C2; these aliases do not themselves validate external input. `ChartPeriod.interval.startDate=null` means the existing first-point inception horizon. Preserve the observed first contribution bar's all-history/zero-opening behavior separately; do not relabel it as a selected-range-only calculation. Allocation amounts and denominator use allocationSummary.unit in the reporting currency; shares are raw ratios with divisor 1, not percentage points. Each allocation references an authoritative category series; its Cartesian role does not create a separate pie. The backend certifies pieEligibility using Decimal values and completeness/partition diagnostics. Eligibility describes safe presentation and must not change any amount, share or denominator.

- [ ] Add compatibility/API tests before changing endpoints. Use DRF APIRequestFactory plus `force_authenticate`, existing user/account fixtures and the named view functions to avoid guessing URL namespaces. Test assertions include:

```python
from datetime import date
from decimal import Decimal

def assert_nav_raw_and_legacy(legacy, modern):
    assert modern['labels'] == legacy['labels']
    assert modern['datasets'] == legacy['datasets']
    assert modern['currency'] == legacy['currency']
    doc = modern['chartV2']
    nav = next(s for s in doc['series'] if s['metric'] == 'nav')
    assert nav['points'][0]['value'] == '100000'
    assert nav['points'][0]['plotValue'] == '100'
    assert Decimal(nav['points'][0]['value']) / Decimal('1000') == Decimal('100')
    irr = next(s for s in doc['series'] if s['metric'] == 'irr_inception')
    assert irr['points'][0]['value'] == '0.1234'
    assert irr['points'][0]['display'] == '12.3%'
    assert doc['periods'][0]['endDate'] == date(2026, 1, 31).isoformat()
```

Build fixtures by pinning NAV/IRR to the stated Decimal values, calling legacy and v2 separately with the same input, and asserting unchanged legacy keys. Additional fixtures must cover two selected accounts with identical names: legacy still has one merged bar; v2 uses `account-group:<ascending IDs joined by comma>` and includes those exact `memberAccountIds`. Renaming a display label without changing membership retains identity. A category label with no authoritative membership/code must cause a v2 contract error; never fabricate an ID.
- [ ] Run `uv run python -m pytest tests/integration/api/test_chart_contract_v2.py -q`; expect v2 metadata/error assertions to fail on the current endpoint.
- [ ] Build metadata at the same points where the Decimal values and exact `d`/previous endpoint already exist. Keep the legacy dictionaries untouched; make Decimal-aware copies before formatting. Add helpers in `services/charts.py`:

```python
def decimal_chart_value(value, *, divisor=Decimal('1'), display, reason='observed'):
    if not isinstance(value, Decimal):
        raise TypeError('Chart raw values must be Decimal')
    return {'value': format(value, 'f'), 'plotValue': format(value / divisor, 'f'),
            'status': 'ok', 'reason': reason, 'display': display}

def unavailable_chart_value(status, reason, display, *, known_subtotal=None):
    result = {'value': None, 'plotValue': None, 'status': status,
              'reason': reason, 'display': display}
    if known_subtotal is not None:
        result['knownSubtotal'] = format(known_subtotal, 'f')
    return result
```

Use `Decimal('1000')` only for money plot scaling; IRRs remain ratios. Emit canonical fixed decimal notation, preserving meaningful precision/trailing zeros and avoiding scientific notation. Format percentage display from `Decimal` with ROUND_HALF_UP once. For allocations, expose the explicitly defined raw ratio amount/complete-positive-NAV, that full reporting NAV as the explicit denominator, a deterministic rank from backend Decimal amount ordering and the stable dimension code. Shares remain unavailable when a complete positive denominator is not established. Preserve legacy formatted fields and gate modern allocation display on F3 resolution. Do not perform source-string parsing to produce raw values.
- [ ] Emit pieEligibility='eligible' only when the denominator is known and positive, every allocation is known and nonnegative, and backend Decimal values establish a complete partition of that denominator. Otherwise emit incomplete, nonpartitioning, nonpositive_total or signed, with incomplete/unknown data taking precedence over other reasons. Keep original signed amounts and available shares in the table contract. Emit totalShare with raw ratio '1' only for a known complete partition of a positive denominator; otherwise use an explicit unavailable status, never an unsupported 100% label. Verify Decimal fixtures: amounts 25 and 75, denominator 100, shares 0.25 and 0.75 are eligible; -25 and 125 against 100 are signed; 25 and 50 against 100 are nonpartitioning; unknown valuation and zero/negative totals are ineligible. No diagnostics path adds a balancing slice or changes legacy values.
- [ ] Source category identity on the backend: selected authorized Accounts queryset gives membership grouped by the exact current `account.name`; keep that group unchanged. Asset-type and asset-class identity uses the raw field codes validated against `constants.ASSET_TYPE_CHOICES`/`EXPOSURE_CHOICES`, plus current explicit Cash bucket. Currency identity uses the actual currency code. Names are labels only. Unknown authoritative enum codes fail v2 validation rather than being silently renamed or hashed.
- [ ] Add the minimum keyword-only `diagnostics: list[dict] | None = None` argument to NAV_at_date. Do not introduce callbacks, alter its default return, repeat financial calculations or move logic. At current valuation-omission branches around nav.py:260-266,289-298,358-366,383-393 append the source IDs/currency/category codes and omission reason before the existing `continue`. This instrumentation is necessary because current return dictionaries discard skipped-valuation provenance. It is protected code and needs an output-equivalence regression across existing option/crypto/bond fixtures.

```python
# At an existing skip branch, immediately before its existing continue:
if diagnostics is not None:
    diagnostics.append({'reason': 'missing_fx', 'account_id': account.id,
                        'asset_id': security.id, 'currency': security.currency})
# Adapt fields for cash/option-flow branches where security/account are not in scope;
# use tx.account_id and tx.security_id or the current cash account's id.
```

Do not catch new exceptions or change current fallback prices/zero marks as part of metadata. Any unobservable completeness issue is `unknown`, not `ok`. If a category/total has an omitted valuation, modern full value and plot value are null; retain the old sum only as `knownSubtotal` with partial status. IRRs calculated against incomplete terminal NAV must be shown as unavailable/partial in v2, while legacy data remains unchanged. Explicit returned Decimal zero remains `ok`; attach `zero_exposure` only when the source actually establishes that fact. An absent indexed category remains `absent_unclassified` until source evidence proves zero.
- [ ] Preserve existing category partition semantics, including crypto branches excluded from some legacy breakdowns. `partition='legacy_non_partitioning'` prevents the UI from claiming that visible categories sum to total NAV and makes the allocation pie ineligible. Do not add omitted categories or rebalance them in this task. Add tests proving totals/legacy data unchanged with diagnostics enabled, missing-price subtotal not zero, and absent versus explicit-zero distinction. A partial/unknown/nonpartitioning result must never become a full 100% circle.
- [ ] Add v2 error behavior: invalid frequency/mode/reversed date range or unsupported contract -> HTTP 400 with `INVALID_CHART_QUERY`; calculation exception -> HTTP 500 with generic `CHART_CALCULATION_FAILED`, retryable true; no accounts/no observations -> HTTP 200 with `outcome='empty'`. Retain old callers' behavior while `chart_contract` is absent. Never transmit raw exception messages or internal account information. V2 failures are not treated as legacy-only capability fallback.
- [ ] Add security v2 metadata directly from `Prices.price` and Decimal position values before current float/JSON serialization; retain original price/position arrays under `legacy`. Include source price row/transaction identity in each period key, instrument id, date and units. Bond price `98.5` is percent_of_nominal, not `0.985` and not currency; price/position calculations are unchanged. Existing multiple position events on one date remain separate ordered entries with server keys; do not invent unique dates or sum them.
- [ ] Run targeted API tests, existing NAV/IRR option regressions and `uv run python -m pytest`. Prepare an independently reviewed protected metadata PR with golden legacy equality and new contract fixtures. Update current NAV/FX mapping documentation as part of this later PR, not during plan preparation.

**Acceptance:** no legacy key/type/grouping regression; exact raw strings, IDs, ISO sample dates, explicit units/status and readable v2 errors; no frontend guessing, no unknown-to-zero conversion and no formula change. Contract output may conservatively display an unavailable result where legacy had an unlabelled partial subtotal; reviewers must see this explicit presentation change.

## Task C2: Establish typed chart adapters and use the shared request lifecycle

**Files:** create feature files `contracts.ts`, `parseChartEnvelope.ts`, `adaptLegacyNav.ts`, `chartApi.ts`, `useNavChart.ts`, `tsconfig.json`; create `__tests__/contracts.spec.ts`, `__tests__/requestLifecycle.spec.ts`, `__tests__/fixtures.ts`; modify only chart wiring in `frontend/src/views/DashboardPage.vue`, chart facade delegation in `frontend/src/services/api.ts` and a strict-check script in `frontend/package.json`.

**Interfaces:** implement the C1 types. Add:

```ts
import type { PortfolioContext } from '@/types/portfolioContext'
export type ReadyChartContext = PortfolioContext & { effectiveCurrentDate: ISODate; currency: string }
export function requireReadyChartContext(context: PortfolioContext): ReadyChartContext {
  const effectiveCurrentDate = context.effectiveCurrentDate
  const currency = context.currency
  if (effectiveCurrentDate === null || currency === null) throw new Error('Portfolio context is not ready')
  return { ...context, effectiveCurrentDate, currency }
}
export interface NavQuery {
  context: ReadyChartContext
  mode: NavMode
  frequency: Frequency
  fromDate: ISODate | null
  toDate: ISODate
}
export interface LegacyNav {
  labels: readonly string[]
  datasets: readonly { label: string; type: 'bar' | 'line'; data: readonly (number | string | null)[];
    [key: string]: unknown }[]
  currency: string
}
export type NavResult =
  | { capability: 'v2'; legacy: LegacyNav; document: ChartDocument }
  | { capability: 'legacy_only'; legacy: LegacyNav }
export function parseNavEnvelope(input: unknown): NavResult
export function adaptLegacyNav(input: unknown): LegacyNav
export function fetchNavChart(query: Readonly<NavQuery>, options: { signal: AbortSignal }): Promise<NavResult>
export function snapshotNavQuery(query: NavQuery): Readonly<NavQuery>
```

The legacy adapter validates/pass-throughs the legacy renderer shape without pretending it has stable metadata. It never gives label-derived IDs or dates to ECharts. For modern calls lacking chartV2 on HTTP 200, return legacy_only and render Chart.js with a capability notice. Invalid v2 is an error, not a silent downgrade. The existing allocation bars are a transitional legacy fallback; missing denominator, identity or eligibility metadata must never be guessed to manufacture a modern pie.

- [ ] Add this complete `navFixture()` factory in `__tests__/fixtures.ts`. Both first-point IRRs are equal, preserving the existing inception horizon. Each call returns new objects; subsequent multi-period fixtures introduce different interval returns explicitly.

```ts
import type { ChartDocument, ChartSeries, ChartValue, LegacyNav } from '../contracts'

function point(value: string, plotValue: string, display: string): ChartValue {
  return { value, plotValue, display, status: 'ok', reason: 'observed' }
}
export function navFixture(): LegacyNav & { chartV2: ChartDocument } {
  const series: ChartSeries[] = [
    { id: 'metric:nav', label: 'NAV', metric: 'nav', role: 'bar', axis: 'money',
      unit: { kind: 'money', currency: 'USD', plotDivisor: '1000' },
      points: [point('100000', '100', 'USD 100,000.00')] },
    { id: 'metric:irr_inception', label: 'Since-inception IRR (annualized)',
      metric: 'irr_inception', role: 'line', axis: 'return',
      unit: { kind: 'ratio', plotDivisor: '1' }, points: [point('0.1234', '0.1234', '12.3%')] },
    { id: 'metric:irr_interval', label: 'Interval IRR (annualized)',
      metric: 'irr_interval', role: 'line', axis: 'return',
      unit: { kind: 'ratio', plotDivisor: '1' }, points: [point('0.1234', '0.1234', '12.3%')] },
  ]
  return {
    labels: ['Jan-26'], currency: 'USDk',
    datasets: [
      { label: 'NAV', type: 'bar', data: [100] },
      { label: 'IRR (RHS)', type: 'line', data: [0.1234] },
      { label: 'Rolling IRR (RHS)', type: 'line', data: [0.1234] },
    ],
    chartV2: {
      version: 2, kind: 'nav', outcome: 'ready', partition: 'complete',
      context: { accountSelection: { type: 'account', id: 7 }, accountIds: [7],
        effectiveDate: '2026-01-31', currency: 'USD', digits: 2 },
      periods: [{ key: 'nav:2026-01-31', endDate: '2026-01-31', displayLabel: 'Jan-26',
        interval: { startDate: null, endDate: '2026-01-31', kind: 'inception' }, partialPeriod: false }],
      series, totals: [point('100000', '100', 'USD 100,000.00')],
    },
  }
}
export function securityFixture(
  kind: 'price' | 'position', unit: 'percent_of_nominal' | 'quantity', value: string,
): ChartDocument {
  const base = navFixture().chartV2
  return { ...base, kind, totals: undefined, security: { id: 9, instrumentType: 'Bond' },
    periods: [{ key: `security:9:${kind}:row:1`, endDate: '2026-01-31', displayLabel: '31 Jan 2026',
      interval: { startDate: '2026-01-31', endDate: '2026-01-31', kind: 'sample_interval' }, partialPeriod: false }],
    series: [{ id: `security:9:${kind}`, label: kind === 'price' ? 'Price' : 'Position',
      metric: kind, role: 'line', axis: kind === 'price' ? 'price' : 'quantity',
      unit: { kind: unit, plotDivisor: '1' },
      points: [point(value, value, unit === 'percent_of_nominal' ? `${value}% of nominal` : value)] }],
  }
}
```

The plain numeric values in the `legacy.datasets` fixture intentionally reproduce the existing visualization-only wire contract. New v2 values and expected financial quantities remain strings; no calculation uses those legacy numbers. Add parser tests:

```ts
it('preserves decimal strings and does not invent modern identity', () => {
  const result = parseNavEnvelope(navFixture())
  expect(result.capability).toBe('v2')
  if (result.capability === 'v2') {
    expect(result.document.series[0].points[0].value).toBe('100000')
    expect(typeof result.document.series[0].points[0].plotValue).toBe('string')
  }
  const legacy = { labels: ['Jan-26'], datasets: [], currency: 'USDk' }
  expect(parseNavEnvelope(legacy)).toEqual({ capability: 'legacy_only', legacy })
})
it('rejects missing IDs, impossible dates and mismatched point counts', () => {
  const noIdentity = navFixture()
  delete (noIdentity.chartV2.series[0] as Partial<ChartSeries>).id
  expect(() => parseNavEnvelope(noIdentity)).toThrow(/identity/i)
  const badDate = navFixture()
  badDate.chartV2.periods[0].endDate = '2026-02-30'
  expect(() => parseNavEnvelope(badDate)).toThrow(/date/i)
})
```

- [ ] Run `npm --prefix ../frontend run test:unit -- src/features/charts/__tests__/contracts.spec.ts`; expect unresolved adapter imports initially.
- [ ] Implement validation for finite decimal syntax without converting to Number, unique series/period IDs, exact calendar-valid ISO dates, known enum/status values, point count, explicit unit, non-ok null plotValue, and context shape. Use an ISO year/month/day round-trip with UTC exclusively for date validation. Never use `new Date(displayLabel)`.
- [ ] For allocation documents require allocations and allocationSummary, validate the dimension code, full denominator/unit/status, totalShare ratio/status, eligibility enum, unique category references and deterministic ranks, and require compatible reporting-money units. An eligible claim requires partition='complete' and ok statuses; reject contradictory metadata. Backend Decimal tests establish arithmetic/positivity eligibility; the adapter does not sum amounts or recalculate percentages. Add rejection tests for missing denominator, unknown category IDs and eligible-with-partial metadata, plus acceptance of valid signed/nonpartitioning documents for explanatory table presentation. Preserve every raw/status field unchanged.

```ts
const decimalPattern = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/
// Non-ok points require plotValue === null. Strings 'N/A'/'N/R' are
// permitted in legacy datasets only; v2 uses explicit status/reason.
```

- [ ] Implement fetch transport through R8's injected `getApiTransport()` from `@/services/http/client` with `{signal, params:{chart_contract:2,breakdown:query.mode,frequency:query.frequency,dateFrom:query.fromDate,dateTo:query.toDate}}`. Validate returned accountSelection/currency/effective date/digits against the committed query context. The backend must authorize/resolve accountIds; the client cannot reconstruct group/broker membership from a selector and must not pretend to compare an unknown list. Context disagreement throws and triggers reconciliation through the reliability store only after the request failure belongs to the accepted current generation, never relabels old data.
- [ ] Implement snapshot with structuredClone and recursive Object.freeze for the entire NavQuery. Instantiate `useLatestRequest<NavQuery,NavResult>(fetchNavChart,snapshotNavQuery)` inside useNavChart. Return the runner state plus its run/invalidate functions; do not copy it into competing refs or define a second generation counter. A watcher on committed context/range calls `run` only when isReady and not isTransitioning. Call invalidate at transitions and on unmount; same-context reload keeps prior data under loading.
- [ ] Add a deferred-promise lifecycle test using the actual shared runner, not a stub that already discards responses. Consume `deferred<T>()` from R5's `frontend/tests/unit/helpers/deferred.ts` and mount a Vue effect scope for the runner. Run queries A then B, resolve B first and A second; assert result statuses accepted/discarded, data is B and loading belongs to B. Repeat with a fetcher that ignores signal, failure followed by success, and mutation of input nested context after run. Successful retry clears local error. Test one v2 error cannot trigger a legacy network retry.
- [ ] Add feature tsconfig.json extending `../../../tsconfig.json` with `strict:true`, `checkJs:false`, and feature TypeScript/Vue/tests in include. Add `type-check:charts` script `vue-tsc --noEmit -p src/features/charts/tsconfig.json`. The transitive graph must remain free of imports from legacy API/config/store cycles; do not suppress strict errors with assertions. Run `npm --prefix ../frontend run test:unit -- src/features/charts/__tests__/contracts.spec.ts src/features/charts/__tests__/requestLifecycle.spec.ts`, `npm --prefix ../frontend run type-check:charts`, global type-check and lint. Coordinate DashboardPage replacement with the reliability owner to avoid duplicate fetch/watchers.
- [ ] Commit one frontend boundary PR. No chart package changes yet; Chart.js stays default. Capture accepted API fixtures in the new feature test folder using synthetic data, never user portfolio records.

**Acceptance:** typed v2 and honest legacy-only paths, immutable latest-request inputs, explicit unavailable/context errors, no data parsing from labels, no side effects from discarded requests, baseline chart remains usable.

## Task C3: Build the gated complex NAV pilot with accessible inspection

**Files:** create `renderBoundary.ts`, `seriesStyles.ts`, `buildNavOption.ts`, `rendererPolicy.ts`, `ChartHost.vue`, `EChartsNav.vue`, `ChartLegend.vue`, `ChartDataTable.vue`, `ChartInspection.vue`, `NavChartPanel.vue`; create `__tests__/navOption.spec.ts`, `__tests__/navAccessibility.spec.ts`, `__tests__/navLifecycle.spec.ts`, `__tests__/render/index.html`, `__tests__/render/main.ts`; modify `NAVChart.vue`/DashboardPage chart wiring and later `frontend/package.json` + lockfile only for this pilot dependency gate.

**Interfaces:**

```ts
export interface ChartInteraction {
  visibleSeriesIds: readonly string[]
  viewport: { firstPeriodKey: string; lastPeriodKey: string } | null
  inspectedPeriodKey: string | null
}
export function toPlotNumber(point: ChartValue): number | null
export function buildNavOption(document: ChartDocument, interaction: ChartInteraction): EChartsOption
export type Renderer = 'chartjs' | 'echarts'
export function resolveRenderer(requested: Renderer, result: NavResult): Renderer
// Vue components use document + interaction props and update:interaction emits.
// ChartHost consumes NavResult, loading, error and requested renderer.
```

EChartsOption is imported from the pinned ECharts package at this task. rendererPolicy defaults to Chart.js; release env `VITE_NAV_ECHARTS_ENABLED` defaults false. Do not enable it globally by installing the package. Feature renderer imports are asynchronous, so baseline users do not download the unused ECharts chunk.

- [ ] Add pure option tests before package/configuration implementation. Generate all seven modes × all five frequencies from explicit synthetic fixture builders; do not infer series semantics from friendly labels. Include two independently identified IRR series in every NAV fixture, signed category values and partial points.

```ts
it('uses raw ratios on the return axis and never plots an unknown as zero', () => {
  const doc = navFixture().chartV2
  const state = { visibleSeriesIds: doc.series.map(s => s.id), viewport: null, inspectedPeriodKey: null }
  const option = buildNavOption(doc, state)
  const series = option.series as Array<{ id: string; yAxisIndex: number; data: unknown[]; connectNulls?: boolean }>
  expect(series.find(s => s.id === 'metric:irr_inception')?.yAxisIndex).toBe(1)
  expect(series.find(s => s.id === 'metric:irr_interval')?.yAxisIndex).toBe(1)
  expect(toPlotNumber(doc.series[0].points[0])).toBe(100)
  expect(toPlotNumber({value:null,plotValue:null,status:'unknown',reason:'missing_price',display:'Unavailable'})).toBeNull()
})
```

- [ ] Run `npm --prefix ../frontend run test:unit -- src/features/charts/__tests__/navOption.spec.ts`; confirm missing functions before writing them. Then check released ECharts/vue-echarts compatibility, license metadata and supported runtime. Add only `echarts` and `vue-echarts` to the frontend dependency/lockfile in this review unit. Do not pick a version from an old README example or add a second money library.
- [ ] Implement the sole plotting boundary:

```ts
export function toPlotNumber(point: ChartValue): number | null {
  if (point.status !== 'ok' || point.plotValue === null) return null
  const value = Number(point.plotValue)
  if (!Number.isFinite(value)) throw new RangeError('Chart value exceeds plotting range')
  return value
}
```

No sums, returns, proportions or monetary unit conversion occur here. Labels/table/inspection consume server `display` or exact raw strings, never rounded chart numbers. Preserve raw value in state if a plotting-range error is shown.
- [ ] Register only required ECharts bar/line, grid, tooltip/axis-pointer, dataZoom and ARIA components plus one renderer. Initial parity uses category periods keyed by server period IDs with displayLabel formatters. Money bars use yAxisIndex 0 and stack `nav`; return lines use yAxisIndex 1, no stack, connectNulls false, smooth false. Stable style mapping uses server IDs and named theme tokens; fixed distinct solid/dashed IRR styles do not change when categories enter. Do not attach a return line to money just because a label changes.

```ts
// Core mapping inside buildNavOption:
const series = document.series.map(s => ({
  id: s.id, name: s.label, type: s.role,
  yAxisIndex: s.axis === 'return' ? 1 : 0,
  stack: s.role === 'bar' ? 'nav' : undefined,
  connectNulls: false, smooth: false,
  data: s.points.map(toPlotNumber),
}))
// Shared tooltip uses axis trigger and server displays/horizon metadata.
// Avoid implicit client sampling/data transforms; zoom changes viewport only.
```

- [ ] Implement an HTML legend with real buttons, accessible labels and aria-pressed. The two return controls read "Since-inception IRR (annualized)" and "Interval IRR (annualized)". They update a controlled set of series IDs, preserve keyboard focus after refresh, and are reflected in rendered series visibility. Disable ECharts built-in canvas legend to avoid conflicting visibility state. Every series remains independently operable.

```vue
<button v-for="series in document.series" :key="series.id" type="button"
  :aria-pressed="interaction.visibleSeriesIds.includes(series.id)"
  @click="toggleSeries(series.id)">
  <span aria-hidden="true" :class="series.metric" />{{ series.label }}
</button>
```

`toggleSeries` produces a new ChartInteraction with one ID added/removed; it never changes values, deletes points or changes dates. Synchronize ECharts with the controlled selection using series identity and explicit update options. Rebuild only when necessary; feed state back after any renderer recreation.
- [ ] Implement ChartDataTable as a horizontally scrollable region with caption, scoped headers, sticky date/period identity and right-aligned tabular values. Each row shows exact endpoint, interval label and every series' server display plus unavailable reason. The first interval explicitly says inception. Include full NAV from document.totals with label "Portfolio NAV (all categories)" independent of hidden bars; do not calculate visible money subtotals on the client. For unknown/partial totals show status/known subtotal text without a total marker on the stack. No export button is added.
- [ ] Implement ChartInspection for pointer and keyboard inspection of one server period key. Shared tooltip presents all selected series, units and actual IRR horizon; keyboard table row focus updates the same inspection model. Do not inject unescaped HTML from account/security names into a tooltip. A native date/range select and Reset zoom button provide keyboard access to viewport changes; the ECharts zoom slider is supplemental. Zoom never changes frequency, requests a new IRR, rebases inception, or averages existing points.
- [ ] Keep ChartHost/EChartsNav mounted for same-context refreshes; overlay loading with aria-busy while retaining prior data's context. On context transition, use the shared runner's invalidate semantics and show the new context loading state; never show stale data under new labels. Reset viewport only when its keys cannot be mapped to new data; preserve surviving series visibility by stable ID. Dispose ECharts and observers on final unmount. Catch rendering failure at ChartHost, show a recoverable chart error and offer the known Chart.js fallback; never swallow transport/data errors into an empty chart.
- [ ] Add component tests asserting two separately named IRR buttons, independent toggle effects, table values for zero/N/A/N/R/partial, preserved focus, retry recovery, state preservation on data/size changes, and disposal once on final unmount. For graph visibility, test resulting rendered series or ECharts actions against ID rather than merely checking that a button emits.
- [ ] Build the isolated dev harness under `__tests__/render/`: index.html mounts main.ts, which mounts NavChartPanel with synthetic fixtures and controls for mode/frequency/loading/invalid/missing values. It has no route/import from the production app. Run `npm --prefix ../frontend run dev -- --host 127.0.0.1`; use `agent-browser open http://127.0.0.1:8080/src/features/charts/__tests__/render/index.html`, `agent-browser snapshot -i`, and current snapshot refs to inspect all modes at 1440×1000 and 390×844. Verify actual geometry: no clipped frequency control, right axis/long legend readable, labels do not cover lines, keyboard table and viewport controls work. Capture reference screenshots under ignored temp_files; no user amounts.
- [ ] Run targeted feature tests, `npm --prefix ../frontend run test:unit`, `npm --prefix ../frontend run type-check:charts`, global type-check, lint, build and `uv run python -m pytest` for release readiness. Record ECharts chunk compressed size and the entire cold-route dependency graph using R7's measurement tool, including immediately loaded lazy chunks, CSS and fonts; measure frontend render timing separately from API time. Do not claim a speed improvement without measurements on identical fixtures.
- [ ] Prepare one pilot PR with the gate false, package/lock changes, new license notices, numerical fixture parity and desktop/mobile/keyboard evidence. Approval of this PR does not automatically authorize default-on rollout.

**Acceptance:** 35 mode/frequency cases plus both IRRs, unknown/signed data, controlled lifecycle and accessible table/legend/viewport all pass; no package removal or global renderer default change.

## Task C4: Migrate allocations to solid pies and security histories after NAV acceptance

**Files:** create `buildAllocationOption.ts`, `buildSecurityOption.ts`, `useSecurityCharts.ts`, `AllocationChart.vue`, `SecurityHistoryChart.vue`; create `__tests__/allocation.spec.ts`, `__tests__/securityHistory.spec.ts`; modify `BreakdownChart.vue`, `SecurityDetailPage.vue` chart sections and existing API facade delegation only. Extend the feature render harness.

**Interfaces:** reuse ChartDocument/ChartValue and shared table/inspection components. Give the HTML legend a highlight/focus mode for allocation slices; NAV retains its independent visibility controls. Add:

```ts
// null means no honest pie is possible; AllocationChart renders the reason and table.
export function buildAllocationOption(document: ChartDocument): EChartsOption | null
export function buildSecurityOption(document: ChartDocument): EChartsOption
export interface SecurityQuery { context: ReadyChartContext; securityId: number; accountId: number | null; period: string }
export function fetchSecurityHistory(query: Readonly<SecurityQuery>, kind: 'price' | 'position', options: {signal:AbortSignal}): Promise<ChartDocument>
```

Use the shared useLatestRequest twice (price and position), with immutable SecurityQuery snapshots and a single shared committed context. Do not issue position requests against a pending account choice. Preserve same-date events by the server period key; ECharts time x-coordinates may coincide, but table rows must not disappear.

- [ ] Confirm F3's documented resolution before modern allocation percentages can be displayed. Add failing allocation tests showing raw amount/ratio strings remain untouched, server percentage is used rather than frontend recomputation, and `[25,75]/100` displays `25.0%/75.0%` only after the reviewed contract is resolved. If F3 is unresolved, keep allocation Chart.js gate false and do not freeze discrepant values as correct.
- [ ] Implement exactly three solid pie cards: Asset Type (asset_type), Asset Class (asset_class), and Currency (currency). Register ECharts PieChart in the allocation renderer's lazy module. Each card has one series of type 'pie' with zero inner radius; its slices come from allocations in server rank order, referencing stable category IDs for labels and colors shared with NAV. Do not create one pie per ChartSeries, sort money with parseFloat or replace the separate NAV stacked bars/two IRR lines. Preserve existing chart/table tabs. Doughnut presentation is optional later scope, not the default required here.
- [ ] Require allocationSummary.pieEligibility='eligible' before building the pie. Use toPlotNumber only for slice geometry; labels, tooltips and the full-NAV denominator use server display/raw metadata with its unit/status. Never show ECharts-derived params.percent as the authoritative percentage. Keep zero-exposure rows in the table without artificial visible slices. For signed exposure, unknown/partial values, incomplete partitions or zero/negative totals, return null, display a concise reason in the chart panel and expose the complete signed/status-aware table. Never use abs, suppress negative rows, normalize a positive subset or invent an Other slice. The table's total percentage is supplied by the backend only when mathematically applicable; remove the current hardcoded 100% behavior from the modern path.
- [ ] Allocation legend buttons highlight/focus a slice and its table row, preserve keyboard focus and announce the server amount/share. They do not hide categories or dispatch legend selection that renormalizes pie geometry. Disable the built-in canvas legend. No legend operation changes the full-NAV denominator, other slice angles, displayed shares or table population. Preserve the existing NAV visibility-control behavior separately.
- [ ] Add a complete allocationFixture() in feature __tests__/fixtures.ts using fresh ChartDocument objects, two authoritative currency-category series, allocations and allocationSummary. Use reporting currency USD, amount strings '25'/'75', shares '0.25'/'0.75', display strings 'USD 25.00'/'USD 75.00' and '25.0%'/'75.0%', denominator '100', totalShare raw ratio '1' with display '100.0%', money plot divisor '1', partition='complete' and pieEligibility='eligible'. This fixture represents the approved F3 ratio contract; it does no frontend financial arithmetic. Add equivalent validated asset-type/asset-class fixtures and these option assertions:

```ts
it('uses one solid pie with two allocation slices and preserves the denominator', () => {
  const doc = allocationFixture()
  const before = structuredClone(doc)
  const option = buildAllocationOption(doc)
  const series = option?.series as Array<{ type: string; radius: [number, string]; data: unknown[] }>
  expect(series).toHaveLength(1)
  expect(series[0].type).toBe('pie')
  expect(series[0].radius[0]).toBe(0)
  expect(series[0].data).toHaveLength(2)
  expect(doc.allocationSummary?.denominator.value).toBe('100')
  expect(doc.allocations?.map(row => row.share.display)).toEqual(['25.0%', '75.0%'])
  expect(doc).toEqual(before)
})
```

Add independent fixtures for -25/125 against 100, 25/50 against 100, missing price/FX, explicit zero exposure, all-zero and negative total. Assert no pie for ineligible fixtures and preserved signed/raw/status rows in the component table. Mount AllocationChart to test keyboard legend focus without changing angles, denominator or shares; assert the chart/table controls work for all three titles and the table never advertises an unsupported 100%.
- [ ] Add security assertions with exact fixtures:

```ts
it('keeps bond percentage and quantity units distinct', () => {
  const bond = securityFixture('price', 'percent_of_nominal', '98.5')
  const position = securityFixture('position', 'quantity', '0.000116590')
  expect(bond.series[0].points[0].value).toBe('98.5')
  expect(bond.series[0].unit.kind).toBe('percent_of_nominal')
  expect(toPlotNumber(bond.series[0].points[0])).toBe(98.5)
  expect(position.series[0].points[0].value).toBe('0.000116590')
})
```

Define securityFixture in feature fixtures.ts with an actual ChartDocument, security ID, server ISO endpoints and a fresh ChartValue; do not use partial untyped objects. Add no-data, duplicate-date transaction rows, missing valuation, last observation exactly on effective date and earlier last observation cases.
- [ ] Implement price y-axis units from metadata: currency for ordinary instruments, percentage of nominal for bonds; never rescale 98.5 to 0.985. Preserve observed points and annotate effective-date carry-forward as display provenance rather than an observed market quote. Only append a carry-forward endpoint when no identical endpoint is present and a known earlier observation exists; never substitute a future quote. Preserve the original observations in the table; any deliberate smoothing/step change must be stated in review. Use an unsmoothed price line and a step-end position display so discrete holdings are not suggested to change gradually; no changes to position arithmetic or event inclusion.
- [ ] Wire period/account changes with useLatestRequest and freeze the entire query, retaining both histories' context. Latest response acceptance, error clearing and unmount cleanup follow C2; do not copy SecurityDetailPage's present unguarded Promise.all ownership. Coordinated separate chart queries can settle independently without one clearing the other's loading.
- [ ] Run `npm --prefix ../frontend run test:unit -- src/features/charts/__tests__/allocation.spec.ts src/features/charts/__tests__/securityHistory.spec.ts`, then type-check/lint/build/full unit tests. Use the isolated harness and agent-browser to inspect the three solid allocation pies and both security graphs on desktop/mobile, chart/table tabs and keyboard flows. Exercise signed/incomplete/nonpartitioning explanatory states, zero exposure, long labels and unchanged NAV bars/two IRRs.
- [ ] Prepare a reviewable migration PR gated separately for allocations and security charts. Retain original wrappers/dependencies for rollback; the current Chart.js horizontal allocation bars are explicitly transitional and do not satisfy final pie acceptance. Dormant PriceChart.vue and commented PricesPage chart do not become new product scope.

**Acceptance:** all six live instances have semantic/unit/status parity and demonstrated interaction improvements. Asset Type, Asset Class and Currency use solid pies for eligible partitions and honest signed/status tables otherwise; each pie has one series, an unchanged full-NAV denominator and non-renormalizing legend interaction. NAV retains stacked bars and two IRRs. No client financial recomputation, table density/identity regression or unresolved percentage disagreement.

## Task C5: Change defaults only after the release gate; remove Chart.js last

**Files:** modify feature `rendererPolicy.ts` and documented release configuration; later modify package/lockfile, existing Chart.js wrapper/config imports and dormant files only after a complete use audit. Create `frontend/src/features/charts/__tests__/rendererPolicy.spec.ts`. Update `.memory-bank/Tech details/frontend.md` and `.memory-bank/Tech details/NAV Function and FX Flow.md` in the implementation PR to describe accepted code and current paths.

**Interfaces:** independent default-off release flags for NAV, allocations and security charts. `resolveRenderer('echarts', legacy_only)` always returns chartjs while compatibility is supported. ECharts option state is not persisted into generic app settings; controlled series/viewport state is renderer-independent and context-scoped.

- [ ] Add policy tests before changing flags:

```ts
it('keeps legacy-only payloads on Chart.js even when pilot requested', () => {
  const legacy = {labels: [], datasets: [], currency: 'USDk'}
  expect(resolveRenderer('echarts', {capability:'legacy_only', legacy})).toBe('chartjs')
})
it('uses Chart.js when the release gate is false', () => {
  expect(defaultRenderer({navEcharts:false})).toBe('chartjs')
})
// defaultRenderer(config:{navEcharts:boolean}):Renderer is defined in rendererPolicy.ts.
```

- [ ] Produce the acceptance matrix in the PR: F1/F2 human financial approvals; F3 resolution; C1 raw/legacy/API errors and unknown diagnostics; 7×5 NAV coverage; two IRRs and horizons; six live chart checks; three named solid allocation pies with one series each, declared denominator and stable slice identity; signed/unknown/nonpartitioning/nonpositive-total table states; no false 100% or legend renormalization; race/retry/context tests; keyboard/table/mobile evidence; performance/bundle measurements; dependency licenses. Unknown data must never be zero-filled to make totals tests pass. Transitional Chart.js allocation bars are rollback evidence only, not accepted final pie behavior.
- [ ] Run the complete gates once on the supported runtime: `uv run python -m pytest`, `npm --prefix ../frontend run test:unit`, `npm --prefix ../frontend run type-check:charts`, `npm --prefix ../frontend run type-check:reliability`, global type-check, lint, build and R1's `npm --prefix ../frontend run test:browser`. Resolve failures before claiming readiness. Repeat only where subsequent changes or new failures justify it. Measure complete cold-route JS+CSS gzip: R7 targets approximately 401 kB for the dashboard before chart migration; chart cutover targets no more than the original approximately 535 kB baseline. Any target miss requires measured tradeoff review, not a false pass. Auth/profile routes must not load chart chunks; report login/dashboard/transactions/security-detail route graphs separately.
- [ ] Enable NAV first in a reviewed release, with Chart.js still bundled through a lazy fallback. Then enable allocations/security after their C4 evidence, including the three solid pies and honest ineligible-data states. A failed current query stays an error; switching renderer is only a visual fallback and cannot fabricate or repair data. Rollback consists of disabling the relevant ECharts flag/redeploying the prior frontend release; allocation rollback temporarily restores the current bars and must be identified as transitional. No DB mutation, financial recomputation or revert of reviewed F1/F2 fixes is required.
- [ ] Keep the fallback for at least one complete accepted release validation cycle covering ordinary refresh, context switch and all six live views. Record actual render errors, context mismatches, responsiveness and size against the baseline; do not invent a fixed improvement threshold. Any observed wrong values/units/dates/status immediately stops rollout of that view.
- [ ] Only after acceptance and removal approval, audit real references with `rg -n 'chart.js|vue-chartjs|chartjs-|StackedBarLineChart|PriceChart|LineChart' frontend/src frontend/tests frontend/package.json`. Remove unused old wrappers/dormant chart code, imports and adapters in a separate cleanup PR. Remove chart.js/vue-chartjs/datalabels/date adapter only if no live use remains. Keep date-fns because non-chart code uses it. Update package and lock together; use build output to prove no Chart.js module remains.
- [ ] After dependency removal, the immediate renderer-switch rollback no longer exists. Preserve the tagged prior dual-renderer release as the concrete rollback artifact and state this changed rollback route in the cleanup PR. Do not delete the only fallback while calling rollback instantaneous.

**Acceptance:** human-reviewed rollout with reversible view-level gates, all live-use parity verified, old dependencies removed only in the final cleanup, and a documented tested prior-release rollback.

## Source-based implementation cautions

- Current all-time NAV uses inception IRR at every endpoint. Interval IRR changes horizon with frequency; first point remains inception. No viewport rebase, percent stacking, averaging IRR or summing NAV snapshots.
- Legacy account categories aggregate account.name. Backend source membership must be emitted, not inferred in an adapter; duplicate names remain one group during this plan.
- Current NAV can skip unpriced crypto/options/cash. Minimum diagnostics are necessary to label partial/unknown results; they are not authorization to change those existing valuation fallback formulas.
- DashboardPage.vue currently defines Asset Type, Asset Class and Currency at lines 243-247 and mounts BreakdownChart for each at lines 43-49. BreakdownChart.vue:13 renders Bar; chartConfig.js:55-58 makes it horizontal, and BreakdownChart.vue:32-35 hardcodes the table total to 100%. C4 deliberately replaces this presentation with solid pies while C1 preserves metrics and exposes when a full-NAV pie would be misleading. Current nav.py:300-306 crypto handling can make breakdowns nonpartitioning, so do not fill an invented residual slice.
- ECharts ARIA/decal support does not establish keyboard access or full WCAG conformance. HTML legend, native viewport controls and the equivalent data table are release requirements.
- Unit conversions use backend Decimal only. Number conversion at renderBoundary is an explicit rendering approximation, not a reusable financial utility.
- Export readiness means exact strings, statuses, IDs and dates; an export button is optional follow-up, not a task acceptance blocker.

## Official references for executors

- ECharts mixed axes/crosshair: https://echarts.apache.org/handbook/en/concepts/axis/
- ECharts stacking: https://echarts.apache.org/handbook/en/how-to/chart-types/bar/stacked-bar/
- ECharts Canvas/SVG: https://echarts.apache.org/handbook/en/best-practices/canvas-vs-svg/
- Vue ECharts update/resize/loading/controlled-state caveats: https://github.com/ecomfe/vue-echarts
- ECharts accessibility: https://echarts.apache.org/handbook/en/best-practices/aria/
- ECharts license: https://github.com/apache/echarts/blob/master/LICENSE
- Chart.js mixed chart baseline: https://www.chartjs.org/docs/latest/charts/mixed.html
- Chart.js canvas accessibility: https://www.chartjs.org/docs/latest/general/accessibility.html
- Highcharts grouping trap (average lines, sum columns): https://www.highcharts.com/docs/stock/data-grouping

## Self-review before handoff

- [x] Confirmed every accepted chart finding is owned above: category/date gap F1, contribution bound F2, scale investigation F3, IDs/dates/partial/error contract C1, request/adapter C2, accessible pilot C3, remaining charts C4, gate/removal C5.
- [x] Checked proposed names against C1/C2 types and shared reliability interfaces; no second request manager, context store or financial calculator is proposed.
- [x] Checked first-point behavior, category partition, account-name grouping, valuation formulas and unknown-to-zero policy; deliberate representation changes are explicit review items.
- [x] Each PR requires failing regression evidence before implementation and passing appropriate gates afterward; no plan test snippet has been claimed as an executed passing test.
- [x] This workstream's actual edits for the planning request are limited to this Markdown file; concurrent master/reliability/design document edits are owned by the other agents.
