# C2 typed chart adapters and lifecycle implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. GLM-5.3 is the selected executor on another machine.

**Goal:** Put a validated, exact chart-v2 boundary and shared request lifecycle behind the existing dashboard NAV chart, ready for the separate C3 renderer pilot.

**Architecture:** Read the merged C1 wire contract as unknown, validate into typed documents, and preserve exact decimal/display/status data. Reuse `usePortfolioRequest` (which owns `useLatestRequest`) and DashboardPage's existing refresh ownership. Chart.js receives only the validated legacy payload; no renderer migration occurs here.

**Tech Stack:** Existing Vue/TypeScript/Pinia/Vuetify, injected Axios transport, Vitest and agent-browser. Node 24.20.0 (`>=24.20.0 <25`); backend uv project environment.

**Spec:** [Chart plan, C1/C2](2026-09-08-chart-correctness-echarts.md), [master plan](2026-09-08-frontend-modernization.md), [progress tracker](2026-09-30-frontend-modernization-progress.md). This handoff resolves source drift in the older C2 instructions; preserve their financial contract and acceptance criteria.

## Global constraints and checkpoint

- Start from latest `origin/codex/frontend-modernization`, containing D4 merge `297fb95c73124a9e05c103a4df8e1ed3eaa87286` (PR #51, 2 October 2026). Pull the subsequent handoff commit too. Create `codex/chart-adapters-c2`; draft PR targets `codex/frontend-modernization`.
- Read AGENTS.md, `.memory-bank/index.md`, Rules for AI Coding Agent.md and the three authoritative NAV/calculation/FX documents before implementation. Treat merged C1 source/tests as the wire authority.
- C2 only. No ECharts dependencies/options, renderer switch, allocation pies, security-page migration, D5 rollout, backend changes, formulas, schema, or deployment. Three solid allocation pies remain C4; both IRRs and accessible NAV inspection remain C3.
- Decimal strings remain strings through validation/state/adapters. Do not parse display labels, formatted money, or N/A/N/R into numbers; no frontend financial arithmetic. Number conversion of backend plotValue belongs at the later plotting boundary.
- Preserve existing NAV interactions, chart parameters, two IRR lines, first-point horizon, Chart.js props/events and per-widget retries. Missing/partial v2 values must never become complete zero values.
- Use current files/interfaces below, not a second request manager, transport instance, auth implementation or store. No new dependency is necessary.
- Every implementation task requires observed failing regressions, minimal implementation, passing focused checks and a scoped commit. Capture actual command exit codes. No weakening lint/type/test gates.

## Review focus

1. Historical chart end date differs from the app's effective date: valid historical ranges must still be accepted (task 3).
2. Malformed v2 coexists with plausible legacy data: fail explicitly, never silently downgrade or issue a legacy retry (tasks 1/3).
3. A stale mismatch/error arrives after a newer query or logout: it cannot reconcile context, replace data, or clear the newer loading state (task 4).
4. Repeated labels/dates, unknown categories and partial values: preserve server identity/status without inferred dates, zero filling or sums (tasks 1/2).
5. The chart renderer mutates datasets: immutable request/validated state must survive, with a fresh compatibility copy at the renderer boundary if needed (task 5).

## Source map and resolved decisions

| File | Responsibility / allowed change |
|---|---|
| `frontend/src/features/charts/contracts.ts` | ChartDocument/ChartValue/ChartPeriod/ChartSeries/ChartUnit/ChartErrorBody, NavQuery/LegacyNav/NavResult types from C1/C2 |
| `frontend/src/features/charts/parseChartEnvelope.ts` | Pure runtime validation; export parseChartDocument and parseNavEnvelope |
| `frontend/src/features/charts/adaptLegacyNav.ts` | Legacy shape validation and lossless compatibility payload |
| `frontend/src/features/charts/chartApi.ts` | Opt-in NAV transport, typed error envelope, response/query context check |
| `frontend/src/features/charts/useNavChart.ts` | Ready-context validation, immutable query snapshot and shared lifecycle wrapper |
| `frontend/src/features/charts/tsconfig.json` | Strict feature and test checking; package script type-check:charts |
| `frontend/src/features/charts/__tests__/` | fixtures.ts, contracts.spec.ts, chartApi.spec.ts, requestLifecycle.spec.ts, dashboardIntegration.spec.ts |
| `frontend/src/views/DashboardPage.vue` | Replace NAV request wiring only; compatibility notice; retain sole refresh watcher |
| `frontend/src/services/api.ts` | Preserve public legacy getNAVChartData signature/shape for remaining callers/tests; remove its Dashboard import, avoid feature imports from this broad facade |
| `frontend/tests/browser/{fixtures.mjs,fixture-server.mjs,run-smoke.mjs}` | Synthetic opt-in fixtures and focused C2 browser case; existing cases stay valid |
| `frontend/tests/browser/charts-c2.mjs` (new) | Capability/error/retry/context rendered acceptance |
| `frontend/package.json` | Add strict chart check only; no chart dependency changes |
| `docs/design/frontend-workspace.md`, progress tracker | Evidence, limitations, PR status, next C3 assignment |

- Live NAV endpoint: `/dashboard/api/get-nav-chart-data/`, GET with `chart_contract=2`, `breakdown`, `frequency`, `dateFrom`, `dateTo`. Current facade is `frontend/src/services/api.ts: getNAVChartData`; extracted dashboard summary transport is `services/api/dashboard.ts` (not a domains folder).
- `backend/dashboard/views.py` passes **dateTo** into `_chart_context(... effective_date ...)`. Thus NAV `document.context.effectiveDate` must equal `query.toDate`, NOT necessarily `query.context.effectiveCurrentDate`. The committed effective date/revision still controls readiness and request invalidation. Do not modify the backend to match the old plan wording.
- `context.canRead` is the current readiness gate. `usePortfolioRequest` synchronously invalidates on revision/readiness changes and delegates generation/disposal to `useLatestRequest`. Reuse it rather than installing duplicate watchers. DashboardPage's current watcher owns initial/context/dataRefreshTrigger requests; NAV child events own parameter changes. `useNavChart` does not add a second automatic fetching watcher.
- C1 allocation envelope contains `chartV2.assetType`, `.assetClass`, `.currency`; security envelopes are `{legacy, chartV2}`. C2 validates their ChartDocuments with pure fixtures only; their live transports/renderers remain C4.
- Generated `api.d.ts` is not a complete chart-v2 schema. This feature boundary is handwritten and runtime checked. Do not edit generated types or expand backend OpenAPI scope.

## Task 1: Exact contract, legacy capability and NAV parser

**Files:** contracts.ts, adaptLegacyNav.ts, parseChartEnvelope.ts, __tests__/fixtures.ts, __tests__/contracts.spec.ts, tsconfig.json, package.json.

**Interfaces:** Copy the C1 ChartDocument family and C2 NavQuery/ReadyChartContext/LegacyNav/NavResult interfaces from the accepted chart plan, checking against merged C1 serializers. Export `adaptLegacyNav(input: unknown): LegacyNav`, `parseChartDocument(input: unknown): ChartDocument`, `parseNavEnvelope(input: unknown): NavResult`. Use `NavResult`'s `v2`/`legacy_only` discriminant; no unchecked assertion from unknown to DTO.

- [ ] Add fresh synthetic fixtures grounded in `backend/tests/integration/api/test_chart_contract_v2.py` and `backend/tests/unit/services/test_chart_contract_values.py`; check their actual paths if needed. Include the accepted plan's NAV example: raw `'100000'`, plot `'100'`, display `'USD 100,000.00'`, both initial IRRs `'0.1234'`, period endpoint `'2026-01-31'`. Multi-period fixtures must give interval IRR a genuinely distinct value/horizon.
- [ ] Write RED tests: preserve raw/plot/display strings (including `'9007199254740993.123456789'`); repeated display labels allowed with distinct period keys; valid zero observed and zero_exposure; absent category unknown; partial with knownSubtotal; both IRR statuses/horizons; empty document. Reject absent/duplicate IDs, impossible dates (`2026-02-30`), malformed decimal strings (`NaN`, `Infinity`, exponent syntax), numeric v2 monetary values, mismatched point/totals lengths, invalid enums and non-ok plot values.
- [ ] Validate exact calendar ISO dates in UTC, unique server keys, context shape, units and per-kind relationships. Status ok requires decimal-string value/plotValue; non-ok requires both null; knownSubtotal only for partial. Do not require dates themselves to be unique for security event rows; keys must be unique. Validate interval end equals period end and start does not follow end, preserving inception/null semantics.
- [ ] Implement legacy validation preserving dataset styling/extra fields, numeric/string/null data and unavailable markers. HTTP 200 with chartV2 absent yields legacy_only. A present null/invalid/unsupported chartV2 is a contract error. Never generate modern IDs or dates from legacy labels. Validate length/shape without coercing legacy values or dropping fields such as empty.
- [ ] Add `type-check:charts` = `vue-tsc --noEmit -p src/features/charts/tsconfig.json`; extend `../../../tsconfig.json`, enable strict/checkJs:false, references:[], and include feature source/tests plus needed env types. Keep runtime imports out of the broad legacy api/config cycles. Run focused contracts tests and strict check; commit.

## Task 2: Allocation and security validation without rollout

**Files:** parseChartEnvelope.ts, contracts.ts, __tests__/fixtures.ts, __tests__/contracts.spec.ts.

**Interfaces:** Extend the same `parseChartDocument(unknown): ChartDocument`; no new fetchers or UI.

- [ ] Write RED cases for all three allocation dimensions, missing denominator, unknown/duplicate series references, invalid ranks, incompatible currency/unit, and eligible+partial/noncomplete contradictions. Accept signed/nonpositive/incomplete/nonpartitioning explanatory documents without transforming their values. Pin fixture amounts `'25'`/`'75'`, shares `'0.25'`/`'0.75'`, denominator `'100'`, totalShare `'1'`; never sum/recalculate in the adapter.
- [ ] Validate required allocationSummary/allocations and certified eligibility structurally. Require complete partition and ok contributing values for eligible claims. Keep backend ownership of arithmetic certification; reject contradictory metadata without repairing it.
- [ ] Write RED price/position cases: security ID/type required; bond price `'98.500000'` with percent_of_nominal unit, quantity `'0.123456789'`, repeated event dates with distinct keys, empty histories and unavailable values. Check kind/metric/axis/unit combinations against actual C1 output.
- [ ] Implement, run the contract suite/strict check and commit. No allocation or security API migration in this task.

## Task 3: Opt-in transport and explicit context/errors

**Files:** chartApi.ts, contracts.ts, __tests__/chartApi.spec.ts.

**Interfaces:** `fetchNavChart(query: Readonly<NavQuery>, options: {signal: AbortSignal}): Promise<NavResult>`. Export typed errors preserving code/status/retryable and a discriminable local context-mismatch error; use the existing ApiError sanitization without losing C1's nested `error` object.

- [ ] Write RED transport tests with injected Axios transport: exact single GET/query/AbortSignal, no import from api.ts or direct axiosConfig, nullable dateFrom preserved, all supported modes/frequencies. Test HTTP 200 legacy_only, valid v2, malformed v2, both C1 400/500 envelopes, malformed error body and abort. Assert exactly one network request in every failure case: no fallback retry.
- [ ] Validate returned account selection, reporting currency and digits against captured context; compare effectiveDate to **query.toDate**. Validate authorized accountIds shape but do not reconstruct broker/group membership. Add explicit valid historical range: committed effective date `'2026-09-30'`, chart toDate and response effectiveDate `'2026-01-31'`; it succeeds. Wrong response date/currency/selector/digits fails locally.
- [ ] Implement through `getApiTransport()` from `services/http/client.ts`; preserve initialized auth interceptors and AbortSignal. No state changes or reconciliation inside the transport. Keep opaque legacy-only context limitations explicit rather than pretending v2 certification occurred.
- [ ] Run transport/contracts/strict tests; commit.

## Task 4: Shared lifecycle and immutable inputs

**Files:** useNavChart.ts, __tests__/requestLifecycle.spec.ts.

**Interfaces:** `requireReadyChartContext(context: PortfolioContext): ReadyChartContext`; `snapshotNavQuery(query: NavQuery): Readonly<NavQuery>`; `useNavChart()` exposes the existing runner's data/error/loading/run/invalidate contract over NavQuery/NavResult. Reuse exported context types and `usePortfolioRequest(fetchNavChart, snapshotNavQuery)`; it already wraps useLatestRequest. No competing data/loading refs or generation counters.

- [ ] Write RED tests using real runner/context and deferred promises in a mounted Vue scope. B wins over A even if A ignores abort; test late failure, error-then-success, invalidation, logout, unmount and run-after-disposal. Mutate nested caller input after run and assert transport observes a detached recursively frozen snapshot.
- [ ] Pin same-context refresh retaining prior data while loading and clearing errors on success; context transition clears old data before new labels apply. No query runs while canRead is false or required date/currency is absent.
- [ ] Test context mismatch side effects: only a current failed result may trigger the existing store's reconciliation. Check failed result identity still equals the runner's current error, readiness/revision still belongs to the captured request, and component is active before reconciliation. An old mismatch after B, unmount or logout does nothing. Do not introduce an automatic reconciliation/retry loop.
- [ ] Implement snapshot by detached clone plus recursive freeze and runtime readiness checks. Keep fetching event ownership in DashboardPage. Run lifecycle/transport/strict tests; commit.

## Task 5: Dashboard compatibility wiring and review evidence

**Files:** DashboardPage.vue, __tests__/dashboardIntegration.spec.ts, browser fixture/server/runner plus charts-c2.mjs, design evidence and progress tracker.

**Interfaces:** Map existing `NavChartParams` into NavQuery (breakdown -> mode, dateFrom -> fromDate, dateTo -> toDate). Feed `NavResult.legacy` to current NAVChart; retain validated document for C3. Preserve the existing single dashboard refresh watcher and child update-params event.

- [ ] Write RED integration tests for initial/context/explicit refresh and parameter event issuing one request each; incumbent labels/datasets/IRRs remain deeply equal; all other dashboard widgets remain independent. Render a concise compatibility notice only for legacy_only. Invalid v2 surfaces an error, not a capability notice. Preserve retry behaviour, honoring non-retryable C1 errors without an automatic retry.
- [ ] Protect typed state from renderer mutation: inspect incumbent NAVChart/Chart.js ownership; use a fresh display copy where mutation is required. Test a renderer-side dataset mutation cannot alter retained validated state or source fixtures. No conversion/scaling or changed missing-value semantics.
- [ ] Wire the page, remove its unsafe NAV payload cast/import, and retain public legacy facade compatibility for other callers. Update existing dashboard request/recovery mocks to the new boundary without weakening their request-count or stale-response assertions.
- [ ] Add `--case charts-c2` to the synthetic browser harness. Assert v2 negotiation/legacy Chart.js visibility, capability notice for a server omitting chartV2, malformed v2 failure with no legacy retry, same-context retained chart, successful retry, and current/stale context mismatch behaviour. Cover desktop/mobile and preserve the full existing matrix. Register every session (including screenshots) before launch; guaranteed cleanup must finish without manual closure.
- [ ] Run all gates below. Record actual exits, counts, any environmental failures/reruns, and what was independently checked. Update tracker C2 as implemented/pending review, not merged. Open one draft PR from `codex/chart-adapters-c2` to `codex/frontend-modernization`, then stop for review; C3 is next only after integration.

## Gates and completion boundary

From frontend with Node 24.20.0: focused feature tests; `npm run test:unit`; `npm run type-check:charts`; `npm run type-check`; `npm run type-check:reliability`; `npm run lint`; `npm run api:types:check`; `npm run build`; `npm run test:browser -- --case charts-c2`; full `npm run test:browser` and affected request/context/recovery cases. Vitest uses `vite.config.js` and discovers feature tests; verify they appear in the reported count. Do not hide npm exit status through output pipes.

From backend with `DJANGO_SETTINGS_MODULE=portfolio_management.test_settings` and live integrations disabled: `uv run python -m pytest`. Backend is unchanged; failures are reported, not fixed by broadening C2.

Merged D4 executor baseline: 371 frontend tests, 35 lint warnings, 1386 backend passed/10 skipped, 72 route profiles. Root independently verified the final D4 correction with 26 focused tests, both type checks, lint and build; these are different scopes. Establish the baseline on the executor machine and distinguish new results from inherited evidence.

Completion means validated exact documents, honest legacy-only capability, no duplicate/stale reads or side effects, strict checks and regression evidence, working incumbent chart and draft PR. It does not mean ECharts, the three pies, main merge or deployment are complete.
