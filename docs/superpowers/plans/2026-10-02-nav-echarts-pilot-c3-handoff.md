# C3 gated NAV ECharts pilot implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. GLM-5.3 is the selected executor on another machine.

**Goal:** Render the validated NAV document with an opt-in ECharts pilot, preserving both IRRs and adding accessible, exact-value inspection without changing financial calculations.

**Architecture:** Reuse C2's NavResult and request lifecycle. Keep the existing NAV controls and default Chart.js renderer; a named chart-area slot hosts the lazy pilot. One controlled interaction model owns series visibility, inspected period and viewport, while server decimal strings remain authoritative.

**Tech Stack:** Existing Vue/TypeScript/Pinia/Vuetify, Vitest and agent-browser; narrowly registered ECharts/vue-echarts dependencies verified and pinned during task 1. Node >=24.20.0 <25; backend uv project environment.

**Spec:** [Chart plan, C3](2026-09-08-chart-correctness-echarts.md), [master plan](2026-09-08-frontend-modernization.md), [tracker](2026-09-30-frontend-modernization-progress.md). This handoff resolves integration details against merged C2; retain the chart spec's financial and accessibility requirements.

## Global constraints and checkpoint

- Pull latest `origin/codex/frontend-modernization`, including C2 merge `2424edbf0239f7b3c22dbd34177eb52aa89e77b3` and this subsequent handoff. Create `codex/nav-echarts-pilot-c3`; draft PR targets `codex/frontend-modernization`.
- Read AGENTS.md, `.memory-bank/index.md`, Rules for AI Coding Agent.md, Portfolio NAV.md, Calculation Conventions.md and NAV Function and FX Flow.md. Merged C1 backend and C2 contracts/tests define the wire contract.
- C3 only, plus the explicitly bounded test-only selector repair in task 0. No backend/financial formula/schema changes, allocation/security migration, D5 rollout, default-on cutover, Chart.js removal, merge or deployment. The three solid allocation pies remain C4.
- `VITE_NAV_ECHARTS_ENABLED` defaults false; only the exact string `true` opts in. No committed environment file enables it. Test both flag states with separate builds and clear inherited environment values.
- Keep values/display/knownSubtotal as received. Only `toPlotNumber` converts backend plotValue for drawing; no money sums, rescaling, percentages, IRRs or dates reconstructed from labels. Axis tick formatting is presentation, not a new financial calculation.
- Preserve C2's single request, immutable snapshots, shared cancellation/session invalidation, query.toDate context check, sanitized errors and once-per-mismatch-episode reconciliation. No extra fetch watcher, fallback HTTP request or parallel request manager.
- Observe failing regressions before implementation and commit each bounded task. Capture actual exit codes; do not pipe away a failing npm status, weaken lint baselines or expand type-check exclusions.

## Review focus

1. Same-context refresh, logout and late async renderer imports: retain valid interaction state during refresh; a dead instance must not recreate charts or steal focus (tasks 3/4).
2. Partial valuation, negative bars and repeated labels: keep gaps and exact identities; distinguish a partial calendar period from an incomplete valuation (tasks 1/2).
3. Hidden categories, two independently toggled IRRs and zoom: full NAV and return horizons never change with visibility or viewport (tasks 1/2/5).
4. Plausible legacy payload alongside invalid v2, renderer failure or legacy-only capability: contract errors stay errors; only a rendering failure offers an explicit known-data fallback (tasks 3/4).
5. Async dependency delivery and apparent mobile/zoom visibility: verify actual fetched modules and hit-testing, not just source imports or bounding boxes (task 5).

## Source map and interfaces

Paths below are relative to `frontend/` unless stated otherwise.

| Files | Responsibility |
|---|---|
| `src/features/charts/{contracts,parseChartEnvelope,chartApi,useNavChart}.ts` | Existing authority and lifecycle; consume unchanged unless a demonstrated integration defect requires a narrowly reviewed correction |
| `src/features/charts/{renderBoundary,seriesStyles,buildNavOption,rendererPolicy,interaction}.ts` | Pure plotting conversion, stable styles, options, gate/capability policy and controlled state reconciliation |
| `src/features/charts/{ChartHost,EChartsNav,ChartLegend,ChartDataTable,ChartInspection,NavChartPanel}.vue` | Renderer boundary, lazy chart, accessible controls and panel composition |
| `src/components/dashboard/NAVChart.vue` | Add named `chart` slot around the complete incumbent chart/no-data body; its default content and query controls retain existing behavior |
| `src/views/DashboardPage.vue` | Pass the existing NavResult/loading/error/retry/parameter event into NavChartPanel; retain the sole refresh watcher |
| `src/features/charts/__tests__/{navOption,navAccessibility,navLifecycle,navIntegration}.spec.ts` | Numeric mapping, accessible interaction, instance lifecycle and dashboard request regressions |
| `src/features/charts/__tests__/{navFixtures.ts,render/index.html,render/main.ts}` | Explicit synthetic NAV fixtures and isolated dev-only harness |
| `tests/browser/{requests,dates,charts-c3,fixtures,fixture-server,run-smoke}.mjs` | Bounded selector repair and flag-off/on rendered acceptance |
| `scripts/measure-route-bundles.mjs`, `package.json`, `package-lock.json`, `tsconfig.charts.json` | Delivery evidence, dependency pins and strict new-feature coverage |
| Repository `docs/design/frontend-workspace.md`, `docs/design/assets/frontend-workspace/`, tracker | Portable evidence and honest outstanding acceptance |

Interfaces (add interaction types in `interaction.ts`, reuse C2 types):

```ts
interface ChartInteraction {
  visibleSeriesIds: readonly string[]
  viewport: { firstPeriodKey: string; lastPeriodKey: string } | null
  inspectedPeriodKey: string | null
}
toPlotNumber(point: ChartValue): number | null
buildNavOption(document: ChartDocument, interaction: ChartInteraction): EChartsOption
type Renderer = 'chartjs' | 'echarts'
resolveRenderer(requested: Renderer, result: NavResult): Renderer
reconcileInteraction(previous: ChartDocument, next: ChartDocument, state: ChartInteraction): ChartInteraction
```

NavChartPanel takes `result: NavResult`, `loading`, `error`, existing `initialParams` and `effectiveCurrentDate`; emits `update-params` and `retry`. It wraps NAVChart and supplies its `chart` slot only when policy selects ECharts. Otherwise the incumbent default slot renders Chart.js. ChartHost consumes result/loading/error/requested renderer and emits `fallback` on explicit user choice; panel then returns to the default slot. Child chart/legend/table/inspection components receive document + interaction and emit `update:interaction`. No duplicated query controls. EChartsNav is asynchronously imported behind the eligible slot; all ECharts runtime imports are confined to that lazy dependency graph. Type-only imports elsewhere are safe.

## Task 0: Restore the two inherited browser gates

**Files:** `tests/browser/requests.mjs`, `tests/browser/dates.mjs`; tracker/evidence.

- [ ] Run the existing `requests` and `dates` cases on the synchronized baseline. Record the D4 selector failures separately from application behavior; C2 documented the same failures on pristine `15533ba0`.
- [ ] Update only selectors to the current route-specific accessible controls. `requests.mjs` assumes every route's textbox is exactly `Search`; `dates.mjs` assumes Year is under `.v-data-table .v-toolbar`. Verify current rendered labels/structure before replacing these selectors. Do not select an arbitrary first textbox or weaken any assertion.
- [ ] Run `npm run test:browser -- --case requests` and `npm run test:browser -- --case dates` from frontend. Require exit 0 with old-held/new-accepted/late-response ordering and effective-date/YTD request assertions intact. If behavior still fails, report the concrete defect instead of claiming a selector repair fixed it.
- [ ] Commit the test-only repair separately and record it as closure of the inherited D4 follow-up. Establish current C2 baseline gates before adding dependencies: 468 unit tests, lint 0 errors/35 warnings, all three type checks, API types/build; counts are reference evidence, not permission to skip execution.

## Task 1: Exact plotting boundary and pure NAV options

**Files:** renderBoundary.ts, seriesStyles.ts, buildNavOption.ts, interaction.ts, navFixtures.ts, navOption.spec.ts, package files and root tsconfig.charts.json.

- [ ] Write and run failing option tests (`npm run test:unit -- src/features/charts/__tests__/navOption.spec.ts`). Cover all seven modes × five frequencies with backend-shaped fixtures passing parseChartEnvelope; both IRRs in every nonempty fixture, repeated display labels with distinct keys, signed values, unknown/partial points, calendar partialPeriod, empty documents, and exact large decimal strings.
- [ ] Verify current official package compatibility/peer dependencies/runtime and license metadata for ECharts/vue-echarts against the installed Vue/Vite versions. Record sources, selected exact versions and notices in evidence; pin only these direct runtime additions and their lockfile. Do not assume a version from an old example or upgrade unrelated packages.
- [ ] Implement `toPlotNumber`: return null for status other than ok or null plotValue; otherwise Number(plotValue), throwing RangeError for nonfinite results. Test observed zero -> 0, unknown/partial -> null even with knownSubtotal, huge finite decimal retained verbatim in state, and out-of-range plot values -> recoverable rendering failure. Never divide by plotDivisor again.
- [ ] Map server period keys onto category x-axis, formatting labels with server displayLabel. Money bars use axis 0 and stack `nav`; both raw-ratio IRRs use axis 1, no stack, smooth false and connectNulls false. Use server role/metric/axis, never label heuristics. No sampling, aggregation or transforms. Honor signed stacks without pretending their top equals full NAV when partition is not complete.
- [ ] Map stable server IDs to theme-token colors; fixed distinct solid/dashed styles for inception/interval IRRs. Reordering or adding a category must not recolor surviving series. Test actual options for independent visibility, no zero filling, identical periods/values under zoom, and no document mutation. Example: ratio plotValue `0.1234` remains 0.1234 on return axis; exact display is supplied by server.
- [ ] Pass focused tests and `npm run type-check:charts` with new pure modules/tests inside the strict feature closure; commit.

## Task 2: Accessible legend, exact-value table and shared inspection

**Files:** ChartLegend.vue, ChartDataTable.vue, ChartInspection.vue, interaction.ts, navAccessibility.spec.ts.

- [ ] Add failing component tests for two separate named IRR buttons, independent visibility, keyboard period selection, focus after same-identity refresh, all statuses and viewport controls. Assert resulting controlled state and its actual option-series mapping, not only emitted events.
- [ ] Implement native legend buttons with aria-pressed and stable ID keys. Exact IRR names: `Since-inception IRR (annualized)` and `Interval IRR (annualized)`. Keep each series independently operable; disable competing canvas legend state.
- [ ] Build the scrollable table with caption, scoped headers, sticky period identity and right-aligned tabular values. Include every series, exact server displays, endpoint/interval and reason for unavailable/partial values. Full NAV comes only from document.totals and is labeled `Portfolio NAV (all categories)` regardless of hidden categories. Render knownSubtotal as explicitly incomplete information, never as a complete total marker. No export UI.
- [ ] Use one inspectedPeriodKey for pointer and keyboard/table-row inspection. Show actual units and horizons: first interval is inception, later intervals use interval.startDate/endDate, since-inception always remains inception to that endpoint. Use text rendering for server names/displays, never raw tooltip HTML. Test an HTML-looking account name stays inert text.
- [ ] Add native start/end period selects and Reset zoom. Validate ordered keys; changing viewport changes neither query/frequency nor values/IRR horizons. Reconcile same-context refresh by retaining surviving hidden/visible IDs, showing newly introduced IDs, retaining mapped viewport keys and inspected key, and clearing invalid selections. Use previous and next documents to distinguish a newly introduced ID from a previously hidden one.
- [ ] Pass `navAccessibility.spec.ts`, option tests and strict feature type check; commit.

## Task 3: Lazy ECharts renderer, failure boundary and owned lifecycle

**Files:** rendererPolicy.ts, ChartHost.vue, EChartsNav.vue, navLifecycle.spec.ts.

- [ ] Add failing policy/lifecycle tests: unset/false flag uses Chart.js; true + v2 allows ECharts; legacy_only stays Chart.js; same-context updates preserve interaction; resize does not reset state; repeated mount/unmount disposes exactly once; a late dynamic import/error after disposal cannot resurrect the chart or mutate another instance.
- [ ] Register only bar/line, grid, tooltip/axis-pointer, dataZoom, ARIA and one renderer via modular imports. Let the selected wrapper own initialization/disposal and do not also manually dispose its chart. Own and clean up any additional observer/listener. Feed controlled state back after any necessary recreation and explicitly remove no-longer-visible series rather than leaving merged stale series behind.
- [ ] Keep chart mounted during same-context refresh with aria-busy overlay. Synchronize pointer/zoom events into interaction state by server keys without event/update loops; native controls and ECharts slider must reflect the same viewport. Test actual ECharts options/actions by ID for independent line/bar hiding and stale-series removal.
- [ ] Catch dynamic import, option construction and rendering errors at ChartHost. Show a recoverable error with retry and explicit `Use previous chart` action backed by the same accepted result. Do not silently downgrade on invalid v2 or transport errors; these remain the Dashboard/C2 error state. Do not convert errors into an empty-success chart. Renderer retry must not create an unnecessary API request; data retry retains existing query ownership.
- [ ] Pass lifecycle/options/accessibility tests and strict feature type check; commit. Do not enable the environment flag in repository defaults.

## Task 4: Integrate the pilot into the existing NAV panel

**Files:** NavChartPanel.vue, NAVChart.vue, DashboardPage.vue, navIntegration.spec.ts; existing C2 dashboard integration tests.

- [ ] Write failing integration regressions for both gate states, legacy-only notice, malformed v2 error, historical range accepted, render failure/fallback, initial/same-context loading, logout/context transition, and exactly one request per parameter/context action. Keep the C2 reconciliation-loop regression.
- [ ] Add the named chart slot around NAVChart's complete existing plot/no-data body. Default content remains the incumbent renderer; query controls/store/events remain single-owned and unchanged. Supply the slot only for eligible pilot rendering, including a v2 empty-state panel rather than mounting an empty canvas. A rendering failure fallback removes that slot and displays the legacy body plus a clear notice.
- [ ] Pass existing NavResult to the wrapper; retain fresh detached legacy copies for Chart.js mutation isolation. Keep the Dashboard's sole refresh watcher and existing retry behavior. On context/session invalidation remove old document/interaction before showing new context labels; preserve interaction only for same-context changes. No second capability fetch or renderer-driven data request.
- [ ] Run new and C2 dashboard tests plus existing dashboard request/retry/composition tests, all unit tests, three type checks and lint. Keep new feature components covered by strict checking; the existing legacy integration exclusion is not a license to exclude new pure code/components.
- [ ] Commit integration with the default renderer still Chart.js.

## Task 5: Rendered acceptance, delivery measurements and draft review

**Files:** isolated render harness, charts-c3.mjs and browser support, measurement script only as needed, design evidence/assets and tracker.

- [ ] Add the isolated synthetic harness (no production router import) and focused `charts-c3` browser case before claiming visual acceptance. Include complete/partial/empty/signed data, long and repeated names, both IRRs, mode/frequency controls, renderer failure, legacy-only and invalid-contract cases. Keep the harness out of production route imports/build entries.
- [ ] Run agent-browser against loopback fixture builds with flag off and on. Validate the actual production Dashboard integration as well as the isolated harness. Exercise all 35 mappings; test independent IRR toggles, keyboard/table inspection, viewport reset, no data requests from zoom/legend, retained state across refresh, resize, cancellation/logout, fallback/retry and once-only context reconciliation.
- [ ] Inspect desktop 1440×1000, tablet 1024×768, mobile 390×844 and 768×1024 profiles. Verify geometry AND elementFromPoint hit-testing: all query controls, legend, right axis, table and zoom controls usable with no page overflow. Repeat native 200% zoom using the existing qa-native-zoom.mjs method, verify devicePixelRatio 2 and reset. A reduced viewport alone is not native zoom evidence. Record real screen-reader testing only if performed; D8 owns the final audit.
- [ ] Capture and visually inspect synthetic screenshots as `docs/design/assets/frontend-workspace/c3-nav-{desktop,mobile,partial,keyboard,legacy}.png`. Register every browser session before use and guarantee cleanup on failure; stop only servers started for this run.
- [ ] Measure identical synthetic cold-dashboard runs in both gate states using R7's measurement tool: fetched JS/CSS gzip, ECharts chunk cost, immediately requested lazy assets, and fonts separately (the current helper measures JS/CSS only). Preserve the existing default-off dashboard budget of 401000 gzip JS/CSS bytes; do not raise it. Assert default-off requests/module graph contain no ECharts/vue-echarts runtime, including on login/profile. Report pilot-on cost separately. Measure frontend render timing separately from API time; no unmeasured performance claim.
- [ ] Run the final gate matrix below with actual exit codes; investigate failures and identify baseline-only failures with a clean baseline reproduction rather than waiving them. Repairing assertions/selectors must preserve their behavioral meaning.
- [ ] Update the C3 evidence section and tracker with commits, RED/GREEN evidence, dependency/license decisions, numeric/visual/keyboard parity, delivery measurements, exit codes and any unmet acceptance. Mark implemented/pending review, not merged or complete modernization. Commit, push `codex/nav-echarts-pilot-c3`, open one draft PR into `codex/frontend-modernization`, and stop. Do not start C4 or enable the default.

## Final gate matrix

From `frontend/`, run each command separately and capture its own exit status:

```text
npm run test:unit
npm run type-check:charts
npm run type-check
npm run type-check:reliability
npm run lint
npm run api:types:check
npm run build
npm run test:browser
npm run test:browser -- --case charts-c2
npm run test:browser -- --case charts-c3
npm run test:browser -- --case requests
npm run test:browser -- --case dates
npm run test:browser -- --case context
npm run test:browser -- --case recovery
npm run test:browser -- --case d4
npm run test:delivery
```

Default-off build/full matrix and flag-on focused C3/production-dashboard acceptance are distinct runs; record which artifact each used. The harness must not silently rebuild a flag-on artifact as flag-off. From `backend/`, set `DJANGO_SETTINGS_MODULE=portfolio_management.test_settings` for the process and run `uv run python -m pytest`; reference baseline 1386 passed / 10 skipped. No financial/backend changes are expected.

Acceptance requires the 35 mappings, both independently controlled IRRs, exact display/table/horizon parity, gaps and signed data, lifecycle/error recovery, usable keyboard/mobile/native-zoom interactions and proven lazy default-off delivery. Passing C3 does not approve default-on rollout, the three pies or main/release completion.
