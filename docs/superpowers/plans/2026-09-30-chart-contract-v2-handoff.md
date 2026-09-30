# Exact Chart Contract C1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This handoff selects inline execution; do not dispatch implementers unless the user explicitly requests delegation. If these skills are unavailable in the GLM environment, follow the written sequence and project rules directly.

**Goal:** Complete master task 11/C1: add an explicitly negotiated chart contract with exact raw values, dates, identity, units, completeness and errors while preserving legacy responses and calculations.

**Architecture:** Keep current endpoints and their legacy payloads. Capture metadata alongside the existing Decimal calculation loop before formatting/float serialization. Add only optional omission diagnostics to NAV and additive v2 presentation metadata. The frontend continues to use Chart.js unchanged.

**Tech Stack:** Existing Django/DRF, Decimal, pytest and uv project mode. No new production dependencies.

**Spec:** Accepted [chart workstream C1](2026-09-08-chart-correctness-echarts.md#task-c1-add-an-opt-in-exact-chart-contract-without-removing-legacy-responses), [master plan](2026-09-08-frontend-modernization.md), [frontend audit](../../audits/2026-09-08-frontend-audit.md), and [table/pie follow-up](../../audits/2026-09-08-grouped-tables-and-allocation-pies.md). The C1 specification is embedded below so this handoff does not depend on an ignored ledger.

## Global Constraints

- Base on `origin/codex/frontend-modernization`, verified code checkpoint `9b32d3d9dbe0e8f46b7f37786e5da2bd8b79f5ae`, not main or any deleted F1/F2/F3 branch. Check for later remote updates before choosing the final base.
- Create `codex/chart-contract-v2` for this isolated proposal. Do not reset/discard user changes or merge into main. Pull the latest implementation branch so the committed handoff documents are included in the C1 proposal branch; preserve any other user changes.
- F1/F2/F3 are merged; do not reimplement their fixes or reopen their deleted branches. Verify their regression tests in the combined baseline before adding C1.
- Read `AGENTS.md`, `.memory-bank/index.md`, `.memory-bank/Rules for AI Coding Agent.md`, and the three authoritative NAV/calculation/FX documents listed there. Current code is the authority for function signatures/caches/paths when older notes differ; record discrepancies.
- `NAV_at_date` in `backend/services/nav.py` is protected by its function name. This is a new protected metadata proposal: separate draft PR to `codex/frontend-modernization`, `needs-approval`, human financial approval before merge. No formula, migration, model, valuation fallback, economic grouping or persistence change.
- All money/price/ratio metadata originates from Decimal values; never parse formatted strings, reconstruct dates from labels, or calculate money with float. Preserve internal price >=6dp and quantity/FX >=9dp; ROUND_HALF_UP display policy and user digits remain authoritative.
- Absent `chart_contract`: preserve existing keys, types, grouping, HTTP behavior and numeric outputs. `chart_contract=2`: follow the exact envelope below. Unsupported explicitly requested versions fail rather than pretending to be v2.
- Preserve both IRR horizons: since inception and actual sample interval, including the existing first-point inception behavior. Neither is trailing-twelve-month IRR.
- Unknown is not zero. Known subtotals are not complete NAV. No balancing category, absolute-valued negative exposure or renormalized allocation shares. Backend metadata certifies safe pie presentation; it does not change amounts.
- C1 contains no ECharts dependency, chart renderer, pie, dashboard/table redesign, route migration, import/broker extraction or Chart.js removal. Those remain separate tasks.
- The examples use Windows/PowerShell; adapt checkout paths and shell syntax to the executor machine, with explicit UTF-8 reads/writes. Run backend commands from `backend/` using `uv run`; use the ASGI launcher only if a server is needed. Do not use manage.py runserver, system Python, requirements files or production account data.

## Review Focus

1. Duplicate account names/renamed labels and unauthorized account membership: keep legacy grouping, derive IDs from authorized sources and never broaden selection.
2. Missing price/FX, option/crypto omission and nonpartitioning totals: conservative explicit statuses, no full pie or complete IRR based on a partial terminal value.
3. Partial calendar buckets, leap/year boundaries and repeated same-day events: emit real endpoints and unique source period keys; do not invent dates or sum separate events.
4. Empty results versus invalid query versus calculation failure: deliberate v2 status/code contract, generic errors, unchanged legacy behavior.
5. Optional diagnostics/default-off calls and installed caching: identical legacy output, no mutable-default leakage, no unhashable cache parameter or repeated valuation pass.

## File responsibilities

| Path | Responsibility |
|---|---|
| `backend/services/charts.py` | Decimal chart-value helpers and NAV v2 metadata at the existing sample loop |
| `backend/services/nav.py` | Minimum optional keyword-only omission diagnostics; default output unchanged |
| `backend/dashboard/views.py` | Explicit v2 negotiation, NAV/allocation envelopes, query/error handling |
| `backend/database/views.py` | Opt-in security price/position metadata with unchanged legacy arrays |
| `backend/tests/integration/api/test_chart_contract_v2.py` | Endpoint parity, contexts/identity/units/periods/status/errors |
| `backend/tests/unit/services/test_chart_contract_values.py` (new) | Exact Decimal serializers, null/partial cases, fixed notation/rounding |
| Existing calculation fixtures or new focused diagnostic test file | Protected default-off/default-on NAV output equivalence |
| `.memory-bank/Tech details/NAV Function and FX Flow.md` | Document only the implemented diagnostics/contract flow in the final proposal |
| Status tracker and this plan | Completion/evidence and deviations |

Line numbers in the older specification are pointers, not authority. Inspect the merged source before patching. Keep typed-client schema changes out of handwritten frontend logic; if OpenAPI generation changes, regenerate `frontend/src/types/api.d.ts` using the established generator and prove compatibility.

## Execution tasks

### 1. Establish the combined baseline and compatibility fixtures

- [ ] Confirm clean/preserved working tree, remote branch and merged fixes. Record exact base commit and create the isolated branch. Do not cherry-pick the fixes again.
- [ ] Run the three merged regression files from backend:

```powershell
$env:DJANGO_SETTINGS_MODULE = 'portfolio_management.test_settings'
$env:UV_CACHE_DIR = Join-Path (Get-Location).Path '../temp_files/uv-cache'
uv run python -m pytest tests/unit/services/test_chart_alignment.py tests/integration/services/test_chart_contribution_boundaries.py tests/unit/services/test_allocation_percentage_scale.py -q
uv run python -m pytest
```

Expected: current combined baseline passes. Do not reuse pre-merge counts as current evidence. Diagnose failures before implementation; isolate unrelated defects instead of silently changing financial behavior.

- [ ] Capture legacy NAV (all modes/frequencies), allocation and security endpoint fixtures using deterministic synthetic accounts and Decimal values. Use DRF APIRequestFactory/force_authenticate and actual view names; check request context/effective date setup.
- [ ] Write new opt-in API tests asserting the full contract, including the embedded 100000 / 100 / 0.1234 example and unchanged legacy keys. Run the new API file and watch genuine failures on the merged code. Record RED evidence.

### 2. Implement exact chart values and source identities

- [ ] Write failing unit tests for Decimal-only values, `100000 -> plotValue 100` at divisor 1000, ratio 0.1234 remaining unscaled, explicit Decimal zero, scientific-notation inputs serialized in fixed notation, precision/ROUND_HALF_UP, null/partial/knownSubtotal constraints.
- [ ] Implement the helpers specified below. Reject non-Decimal numeric sources instead of converting floats or formatted strings.
- [ ] Add fixture tests for duplicate-name account grouping and rename-stable membership IDs; enum/currency source codes; invalid/missing identity; selected/authorized account IDs. Keep legacy grouping unchanged.
- [ ] Run focused unit/API tests: serializer cases pass; remaining unimplemented endpoint cases may still fail. Keep output distinctions explicit.

### 3. Add protected omission diagnostics with output equivalence

- [ ] Read the actual NAV branches and caches/call sites. Write diagnostics-on/off equivalence tests against existing option, crypto, bond and ordinary NAV fixtures; test missing FX/price, repeated calls, and explicit zero versus omitted value.
- [ ] Add only keyword-only `diagnostics=None` and source annotations immediately before existing omission branches. No new catches, fallbacks, repeated valuation, new cache policy or return-shape change. Do not add diagnostics when the source does not support a reason.
- [ ] Verify old callers return exactly the same Decimal dictionaries and that diagnostics identify the actual omitted source. Verify absence of state leakage across calls and compatibility with actual caching, if present.
- [ ] Run protected regressions, including `tests/unit/calculations/test_nav_option_paths.py`, `test_irr_option_paths.py`, `test_nav_crypto_cash_flow.py`, `test_nav_crypto_bucket.py`, `test_bond_notional_and_aci.py` and `test_value_and_nav.py`.

### 4. Expose NAV and allocation v2 envelopes

- [ ] Attach NAV metadata at the existing loop before legacy formatting. Test all seven modes and five frequencies, actual sampled endpoints, interval horizons, first-point inception, incomplete calendar buckets, absent categories and partial NAV/IRR.
- [ ] Implement allocations from the same raw authorized valuation result. Test 25/75 against100 (eligible ratios0.25/0.75), -25/125 (signed),25/50 (nonpartitioning), unknown/missing valuation, zero/negative denominator, and deterministic rank.
- [ ] Assert legacy equality with v2 requested, complete denominator ownership, and no added balancing category. Unknown/partial metadata must be conservative.
- [ ] Run NAV/allocation focused tests to GREEN, retaining the remaining security/error tests for the next task.

### 5. Expose security v2 metadata and errors

- [ ] Test price/position negotiation: legacy top-level lists remain lists without v2; v2 uses `{legacy: [...], chartV2: ...}`. Assert Decimal strings before floats, real price/transaction IDs, instrument/context/units and same-day event order.
- [ ] Implement only the metadata/envelope. Bond98.5 remains percent_of_nominal 98.5, quantity keeps exact precision. Preserve legacy event ordering and calculations.
- [ ] Add/test invalid frequency/mode/reversed ranges/version, empty selections/observations, forced calculation exception, generic error messages and existing authorization. No raw exception/account details may leak. Legacy errors keep their incumbent behavior.
- [ ] Run the complete new API/unit suite to GREEN.

### 6. Verify, document and submit the C1 proposal

- [ ] Run the merged F regressions, all new C1 tests, NAV/IRR/option/crypto/bond equivalence regressions and full `uv run python -m pytest` from backend. Capture exact output/exit codes.
- [ ] Measure coverage of changed protected paths/core modules. The project requires >=90% for core calculations. Report inherited whole-module gaps explicitly; do not lower thresholds or imply a changed-lines score satisfies whole-module coverage. A miss remains a review limitation, not a silently waived gate.
- [ ] Run `npm run api:types:check`, `npm run test:unit`, `npm run type-check`, `npm run type-check:reliability`, `npm run lint`, `npm run build` from frontend with the locked Node24 runtime on PATH and workspace UV cache if the generator needs it. If generated types must change, use the generator and rerun the applicable gates; do not edit generated data by hand or add lint debt.
- [ ] Review the final diff for accidental formula/route/grouping/legacy changes. Obtain a scoped technical review; address important findings with regression tests. Do not substitute AI review for human protected-code approval.
- [ ] Update the NAV/FX mapping, durable tracker and C1 checkboxes with exact commit/gate/PR evidence. Record any source/spec conflict and its resolution; no task completion based solely on file presence.
- [ ] Open a draft PR from `codex/chart-contract-v2` into `codex/frontend-modernization` with `needs-approval`. Explain the optional protected diagnostics, golden legacy equivalence, new status presentation and coverage limitations. Include synthetic numeric examples and regression results. Attach the PR to this chat if the executor has that capability.
- [ ] Stop after this independently reviewable proposal. Do not merge, deploy, mark the whole modernization complete or start C2/C3/D3 in this assignment. Report the PR, tests, remaining approval and any unsatisfied acceptance explicitly.

## Completion criteria

C1 implementation is review-ready only with legacy parity, exact raw/date/identity/unit/status/error contract and passing relevant gates. C1 integration is complete only after required human approval and PR integration; main release still waits for the remaining master tasks. Record those two states separately.

## Embedded accepted C1 specification

The following is the accepted C1 section as recorded on 30 September 2026. It contains the complete `ChartDocument`/`ChartValue` schema and numeric/error requirements; implement it, not a reduced substitute. If the source reveals a conflict, record it and preserve the financial invariants before choosing a minimal adaptation.

### C1: Add an opt-in, exact chart contract without removing legacy responses

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
