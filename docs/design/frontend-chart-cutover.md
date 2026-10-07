# C5a — chart cutover release candidate: evidence

Status: implemented, awaiting review. Branch `codex/chart-cutover-c5`
(base `a5250250`, latest `origin/codex/frontend-modernization`: PR #59/C4
merged at `671171be` plus this handoff). Draft PR into
`codex/frontend-modernization`; not merged, no deployment. The three release
flags become default-on (missing flag = enabled) in this candidate; explicit
`'false'` restores the corresponding legacy family, and any other supplied
value — including empty — is conservative off.

Sections: [1. Task 0 baseline and inventory](#1-task-0-baseline-and-inventory) ·
[2. Task 0 inherited recovery exceptions](#2-task-0-inherited-recovery-exceptions) ·
[3. Task 1 lazy legacy fallback](#3-task-1-lazy-legacy-fallback) ·
[4. Task 2 release policy](#4-task-2-deterministic-default-on-release-policy) ·
[5. Task 3 combined acceptance and delivery](#5-task-3-combined-acceptance-and-measured-delivery) ·
[6. Task 4 gates, rollback and handoff](#6-task-4-final-gates-rollback-rehearsal-and-handoff) ·
[7. Deviations and limitations](#7-deviations-and-limitations)

## 1. Task 0 baseline and inventory

All references are to base `a5250250` (clean worktree, dedicated worktree on
branch `codex/chart-cutover-c5`; no other checkout touched).

### 1.1 Environment and build flags

- Node v24.20.0 (portable runtime, engine range `>=24.20.0 <25`), npm ci from
  the committed lockfile, Windows/Git Bash.
- Base SHA `a5250250a6932de81d7d7fbaecfe001e51c14137` (clean tree, verified).
- The three build flags at base: `VITE_NAV_ECHARTS_ENABLED`,
  `VITE_ALLOCATION_ECHARTS_ENABLED`, `VITE_SECURITY_ECHARTS_ENABLED` are all
  UNSET (no `.env*` file and no environment defines them; verified), so at
  base every family renders Chart.js through the exact-`'true'` gate
  semantics. Vite reads flag values at build time only: changing a flag
  requires rebuild/redeploy; the flags are not runtime kill switches.

### 1.2 Baseline gates (pristine base, this worktree)

Actual exit codes:

| Gate | Result |
|---|---|
| `npm run test:unit` | exit 0 — 96 files / 974 passed |
| `npm run type-check` | exit 0 |
| `npm run type-check:reliability` | exit 0 |
| `npm run type-check:charts` | exit 0 |
| `npm run api:types:check` | exit 0 |
| `npm run lint` | exit 0 — 0 errors / 8 warnings (unchanged baseline) |
| `npm run build` | exit 0 |
| backend `uv run python -m pytest` (test settings) | exit 0 — 1386 passed / 10 skipped, coverage 83.26% |

(The first unit run in this worktree reported 2 securityHistory timeouts while
backend pytest ran concurrently on the same machine; rerun solo it is green
with the exact C4-recorded 96/974. The concurrency flake is environmental and
already recorded in prior evidence; final gates in this document run
sequentially.)

### 1.3 Live and dormant Chart.js references (audit; nothing deleted)

Runtime Chart.js import sites (production graph):

| Module | Imports | Registration side effect | Reached from |
|---|---|---|---|
| `src/components/charts/StackedBarLineChart.vue` | `chart.js` (Chart, CategoryScale, LinearScale, BarElement, PointElement, LineElement, Title, Tooltip, Legend, BarController, LineController), `chartjs-plugin-datalabels` | `Chart.register(...)` at module scope | EAGERLY imported by `NAVChart.vue` (dashboard default slot; the NAV legacy fallback leaf) |
| `src/components/dashboard/BreakdownChart.vue` | `vue-chartjs` (Bar), `chart.js` (Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale), `chartjs-plugin-datalabels` | `ChartJS.register(...)` at module scope | EAGERLY imported by `DashboardPage.vue` (three allocation cards; chart tab and `#fallback` slot) |
| `src/components/charts/LineChart.vue` | `vue-chartjs` (Line), `chart.js` (Title, Tooltip, Legend, LineElement, LinearScale, PointElement, CategoryScale), `chartjs-plugin-datalabels` | `ChartJS.register(...)` at module scope | EAGERLY imported by `SecurityDetailPage.vue` (price/position fallback + legacy path) |
| `src/views/database/SecurityDetailPage.vue` | `chartjs-adapter-date-fns` (side-effect import), `chart.js` (TimeScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend), `date-fns` (period windows) | `Chart.register(TimeScale, ...)` + `Chart.defaults.locale = 'en-US'` at module scope | the security detail route (time-axis support for the legacy charts) |

Consequences at base: the dashboard eagerly downloads BOTH renderers
(ECharts pilot chunks plus the Chart.js/vue-chartjs/datalabels fallback
runtime) because the legacy leaves are static imports; the security detail
route eagerly downloads Chart.js plus the date adapter. This is the eager
loading C5a removes (task 3) before measuring the combined candidate.

Dormant (audit candidate only, NOT deleted in C5a):

- `src/components/charts/PriceChart.vue` — imports `vue-chartjs` (Line) and
  `chart.js`; zero importers in `src/` (the commented PricesPage chart). Left
  untouched for the C5b removal audit.

Shared helpers audited for transitive eager imports:

- `src/config/chartConfig.js` — pure option/color factory (`vue` nextTick +
  theme palette only; no chart.js import). Not a Chart.js delivery vector;
  unchanged.
- `src/features/securities/useSecurityDetail.ts` — imports `getChartOptions`
  (pure) and the v2 transport; no chart runtime import. Unchanged.
- Modern renderer runtime (`echarts`, `vue-echarts`) lives ONLY inside
  `EChartsNav.vue` / `EChartsAllocation.vue` / `EChartsSecurity.vue`, each
  loaded through `defineAsyncComponent` (C3/C4); the chart shells
  (`ChartHost.vue`, `NavChartPanel.vue`, `AllocationChart.vue`,
  `SecurityHistoryChart.vue`, `ChartLegend.vue`, `ChartDataTable.vue`,
  `ChartInspection.vue`, `AllocationDataTable.vue`, `SecurityDataTable.vue`)
  carry no chart runtime imports.

date-fns non-chart consumers (date-fns is retained in C5a regardless):
`DateRangeSelector.vue`, `DatePicker.vue`, `TransactionImportProgress.vue`,
`dialogs/PriceImportDialog.vue`, `utils/dateUtils.js`,
`utils/dateRangeUtils.js`.

Installed dependency licenses (from `node_modules` package metadata at this
lockfile): `chart.js` 4.4.4 MIT; `vue-chartjs` 5.3.1 MIT;
`chartjs-plugin-datalabels` 2.2.0 MIT; `chartjs-adapter-date-fns` 3.0.0 MIT;
`echarts` 6.1.0 Apache-2.0; `vue-echarts` 8.3.1 MIT; `date-fns` 3.6.0 MIT.
No package added or removed in C5a (frontend/package.json and the lockfile
are audit-only).

### 1.4 Six-view fallback map at base

| View | Modern renderer (gated) | Legacy fallback |
|---|---|---|
| NAV | `EChartsNav` via `ChartHost` in `NavChartPanel`'s `#chart` slot | `NAVChart` default slot → `StackedBarLineChart` |
| Asset Type pie | `AllocationChart` + `EChartsAllocation` | `BreakdownChart` chart tab / `#fallback` slot → Chart.js `Bar` |
| Asset Class pie | same | same |
| Currency pie | same | same |
| Security price | `SecurityHistoryChart` + `EChartsSecurity` | `SecurityDetailPage` `#fallback` / legacy path → `LineChart` |
| Security position | same | same |

Detach rule preserved: legacy leaves always receive a fresh detached copy of
the accepted result (`legacyCopy` in `NavChartPanel`; the C4 legacy
projections for allocation/security), never the retained validated document.

## 2. Task 0 inherited recovery exceptions

### 2.1 Reproduction attempts at the pristine base

C4 recorded (in `docs/design/frontend-charts-c4.md` section 6): `recovery`
and `dialog-recovery` fail on the C4 machine with the identical signature at
base `8f1b0aba` and on the C4 branch — "a Retry click landing while a Vuetify
overlay scrim is still in its leave transition
(`v-overlay__scrim.fade-transition-leave-active` covering the click point)".

Reproduction on the pristine base `a5250250` in this worktree (Node
v24.20.0, agent-browser harness, each case run individually):

| Scenario | Runs | Result |
|---|---|---|
| `--case recovery`, solo | 6 | all exit 0 |
| `--case dialog-recovery`, solo | 6 | all exit 0 |
| `--case dialog-recovery`, under concurrent `vite build` load | 1 | exit 0 |
| `--case recovery`, under concurrent `vite build` load | 1 | exit 0 |

The recorded race did NOT reproduce in 14 runs in this environment,
including under artificial load. Per the plan, a green run must not relabel a
genuine failure environmental — so the recorded mechanism was fixed at the
harness layer instead of being waved away.

### 2.2 Bounded harness repair (harness-only; no application change)

The recorded mechanism is a harness synchronization defect by construction:
both flows issued their Retry/Reload clicks without verifying that the point
was no longer covered by a leaving overlay transition. The repair keeps every
assertion and uses real clicks only (no force clicks, no dropped checks; an
unhittable control still fails the case):

- `tests/browser/recovery.mjs`: before snapshotting the widget's Retry
  button, the flow waits (bounded `wait --fn`, 5 s) until the button is the
  element actually hit at its center point (`elementFromPoint`, size >
  1px) — i.e. the overlay transition has genuinely left — and a refused
  "is covered by" click is retried bounded (12 × 100 ms, re-verifying
  hittability each time), the same accepted pattern the dialogs delivery
  flow has used since D5.
- `tests/browser/dialogs.mjs` (`assertDialogChunkRecovery`): the by-name
  click helper retries a refused covered click bounded; a missing control
  still throws after the bounded attempts (the previous unconditional
  `assert.ok` message is preserved as the recorded error).

Post-repair verification (this worktree, on the task-1 working tree):
`--case recovery` exit 0 (route + all four widgets recovered with exactly one
matching read each) and `--case dialog-recovery` exit 0 (failed chunk visible,
explicit reload, dialog reopens, zero unhandled page errors).

These cases inherit into every future gate run; the exceptions are closed on
this branch and the repair is committed separately as task 0 work.

## 3. Task 1 lazy legacy fallback

RED observed first: the charts-c5 laziness flow failed against the pre-fix
sources (stashed working tree) with "all-modern dashboard must load no
Chart.js runtime module (found chart.js modules in the loaded graph)",
exit 1 — then passed after the extraction.

- `frontend/src/components/charts/LegacyAllocationChart.vue` (new) owns the
  incumbent Bar, its Chart.js component registration and the datalabels
  plugin for the three allocation cards; `BreakdownChart.vue` no longer
  imports any Chart.js module and loads the leaf through an async boundary
  (both the flag-off path and the `#fallback` slot render the same leaf).
- `NAVChart.vue` loads `StackedBarLineChart.vue` (the existing registered
  NAV leaf) asynchronously for its default slot; the modern pilot slot is
  unaffected.
- `SecurityDetailPage.vue` lost its eager `chartjs-adapter-date-fns` import,
  `chart.js` imports, `Chart.register(TimeScale, ...)` and
  `Chart.defaults.locale` side effects: they moved INTO `LineChart.vue`, so
  the lazy legacy leaf carries its own registration and is the only path
  through which the Chart.js runtime reaches the security route. The page's
  option factories (period windows, time-unit config, y-axis titles) are
  untouched.
- `frontend/src/features/charts/lazyRenderer.ts` (new,
  `lazyChartRenderer`): every legacy leaf and every modern ECharts leaf
  loads through it. A rejected dynamic import surfaces as a visible,
  recoverable renderer error owned by the mounting shell — never an
  empty-success chart, never an automatic retry loop. Vue leaves a failed
  async loader's promise pending forever when a user onError neither
  retries nor fails, and the occupied `pendingRequest` would also block any
  remount from re-attempting, so the helper owns the single user-driven
  retry (it clears `pendingRequest` and re-runs the loader; `resolvedComp`
  caching keeps post-success remounts instant). The modern hosts route
  chunk-load failures into their existing failure UIs
  (`chart-render-error`, `allocation-render-error`,
  `security-render-error` — retry plus the user-chosen fallback); the
  legacy shells render their own `*-legacy-load-error` alert with a Retry
  control. Data/contract errors are unchanged: they remain the Dashboard/C2
  error states and never reach the renderer boundaries.
- Detached legacy copies unchanged: `NavChartPanel`'s `legacyCopy`
  (structuredClone of the accepted result) and the C4 legacy projections
  feed the leaves; the retained validated result is never mutated.
- `tests/browser/charts-c5.mjs` phase A (built all-on artifact, real module
  graphs via `.vite/module-membership.json`): the all-modern dashboard
  loads NO chart.js/vue-chartjs/datalabels/adapter module; invoking the
  user-chosen NAV fallback (outrange renderer failure -> "Use previous
  chart") downloads the legacy runtime, renders the SAME accepted response
  with exactly ONE API request attributable to the triggering re-query and
  ZERO additional calls for the fallback itself, and leaves the allocation
  family modern and refetch-free. The run-smoke base artifact now builds
  with an explicit all-false rollback configuration (documented in the
  harness), so every pre-existing flag-off assertion keeps its strength;
  the unflagged candidate is built separately by charts-c5.
- Unit coverage: `lazyRenderer.spec.ts` (loader contract: async resolve,
  visible rejection with onLoadError, deferred retry, no automatic
  retries, NAV async leaf rendering the handed data). The crypto page
  spec's LineChart mock gained `__esModule: true` (Vue unwraps `.default`
  through the async boundary only with the flag).

## 4. Task 2 deterministic default-on release policy

- `rendererPolicy.ts` keeps `pilotRequested()`,
  `allocationEchartsRequested()`, `securityEchartsRequested()` and
  `resolveRenderer` intact and adds the pure parser `chartFlagEnabled`:
  absent (`undefined`) => true for the reviewed candidate; exact `'true'`
  => true; exact `'false'` => false; ANY other supplied value — including
  the empty string, uppercase, whitespace, numeric strings and arbitrary
  words — conservatively false. The file documents that this supersedes
  the C3/C4 opt-in defaults in this candidate only, that the three gates
  stay independent, and that Vite reads the flags at build time only
  (rebuild/redeploy required; they are NOT runtime kill switches). The
  three environment names are unchanged.
- `rendererPolicy.spec.ts` (22 cases, written RED first — unresolved
  `chartFlagEnabled`): the value-class matrix per flag, per-family env
  wiring (each function reads its own variable), all eight boolean flag
  combinations, capability outcomes (legacy-only => chartjs even with
  every gate on; v2 + requested => echarts; null => chartjs), and a
  present-invalid object never reaching the modern renderer nor
  masquerading as a legacy success.
- Release-candidate stages verified locally (never deployed): the NAV-only
  artifact (NAV `'true'`, allocation/security `'false'`) renders the NAV
  pilot with incumbent allocation bars and incumbent security charts and
  loads no ECharts runtime on the security page; the explicit all-on and
  the NO-FLAGS candidate render identically (three pies + NAV pilot +
  modern histories); the explicit all-off rollback renders the incumbent
  app with no ECharts in the dashboard graph (charts-c5 phase B).
- Older pilot tests updated to explicit rollback flags (assertions kept):
  `remainingChartApi.spec.ts` now pins absent => on and explicit
  `'false'` => off (the old default-off pin was superseded, not deleted);
  `remainingChartIntegration.spec.ts` flag-off wiring tests stub `'false'`
  explicitly; the security describe resets the shared VChart mock state
  per test (hygiene the default flip exposed); the dashboard settle loop
  no longer breaks on the capability notice before the async legacy bars
  resolve.

## 5. Task 3 combined acceptance and measured delivery

`charts-c5` (registered in run-smoke; focused case `--case charts-c5`)
builds its own artifacts and drives, in order:

- Phase A — fallback laziness (see task 1).
- Phase B — flag matrix: NAV-only / all-on / no-flags / all-off rendered
  independence with per-artifact module-graph assertions.
- Phase C — combined acceptance on the no-flags candidate: all six views
  together (three solid pies + NAV pilot + stock price/position
  histories); both independent IRR controls with their distinct names;
  legend toggles issue zero requests and hide independently; keyboard
  table row focus drives the shared inspection; native zoom selects move
  and the real frequency refresh afterwards is exactly one request with
  the zoom controls surviving (an incompatible Day document resets the
  window — no leak); a response parked at the fixture server leaves the
  previous chart rendering (never looking current, never an error) until
  the replacement query lands (two requests total); the signed allocation
  state shows the certified negative-exposure reason with the complete
  signed table (`($25.00)`, `-25.0%`, unchanged denominator); malformed
  breakdown v2 is a section error with exactly one request and no retry;
  legacy-only shows the honest notice plus incumbent bars from the lazy
  leaf; stock/bond/crypto histories keep exact displays (`$102.25`,
  `99.875% of nominal`, `0.000216590`); a deterministic security renderer
  failure stays visible through an explicit Retry and recovers through
  the user-chosen fallback; switching from the zoomed stock to the bond
  renders the full new context (bond tooltip = `99.125% of nominal`) with
  zero page errors — no cross-context zoom leakage; 390px: every legend
  button, allocation tab, IRR control and zoom control hit-tested
  (`elementFromPoint`) below the fixed header; the NAV mobile tooltip is
  captured by the C3 CDP pointer-sweep tool with in-flight
  full-visibility verification (`c5-nav-mobile-tooltip.png`); the desktop
  restore re-renders; native 200% zoom is DPR-verified (qa-native-zoom
  script), the pilot and legends still render at the zoomed state
  (`c5-native-zoom.png` captured there), and the DPR reset is verified.
- Phase D — delivery: cold-route JS+CSS over the observed resource graph
  for login/profile/transactions/dashboard/security on the candidate
  build, plus dashboard on the NAV-only build, the all-off rollback build
  and the fallback-activated state; emitted-vs-fetched distinguished
  (`manifestEntries` vs observed assets; per-route file lists in
  `tests/browser/artifacts/charts-c5-delivery.json` with raw and gzip
  bytes); fonts reported separately (system stack, zero font assets);
  loopback timings are explicitly NOT production latency evidence.
  login/profile/transactions assert NO Chart.js AND NO ECharts runtime
  modules.

### Measured delivery (this worktree, Node v24.20.0, loopback, gzip JS+CSS)

| Route / state | gzip bytes |
|---|---|
| Dashboard, modern default (no flags) | **483,951** |
| Dashboard, NAV-only | 543,210 |
| Dashboard, all-off rollback | 345,257 |
| Dashboard, fallback activated | 549,587 |
| Login (candidate) | 236,754 |
| Profile (candidate) | 236,669 |
| Transactions (candidate) | 271,335 |
| Security detail (candidate) | 463,230 |

**Budget: the all-modern dashboard is 483,951 gzip bytes (tested head `9f4d9986`) — 51,055 bytes
under the saved approximately 535 kB cutover target and below the C4
flag-on measurement (549,104).** The reduction comes exactly from task 1's
lazy extraction (Chart.js and its datalabels/adapter runtime left the
eager dashboard graph). The historical pre-chart target (~401 kB) applies
to the chart-less app; the rollback build at 345,263 gzip sits well below
it. No budget was raised and no module was omitted from the measurements.

### Captures

`docs/design/assets/charts-c5/`: `c5-dashboard-modern.png` (1440x1000,
three pies + NAV pilot + legends), `c5-ineligible-table.png`,
`c5-bond-history.png`, `c5-crypto-history.png`,
`c5-nav-mobile-tooltip.png` (500x844, captured by the CDP pointer-sweep
tool at the hover instant), `c5-native-zoom.png` (1440x1000 at native
200%). Each was verified by local PNG decoding (IHDR dimensions +
zlib-inflated pixel statistics: non-trivial colored-pixel percentages and
distinct color buckets — real rendered content, no blank frames), and
`frontend/tests/browser/artifacts/charts-c5-captures.json` (local artifact, gitignored like the C4 delivery records) records SHA-256, byte
size and pixel dimensions for every artifact. All captures are synthetic
fixtures only.

## 6. Task 4 final gates, rollback rehearsal and handoff

Full matrix on the committed implementation head `c4ad77a8` (sequential,
actual exit codes; Node v24.20.0). Two findings were corrected in a
follow-up commit `9f4d9986` (two unused-symbol lint diagnostics in the NEW
harness files) and the affected gates re-verified on that head; everything
else is unchanged by that two-line commit. The evidence/tracker commits
that follow are markdown-only.

| Gate | Result |
|---|---|
| `npm run test:unit` | exit 0 — 98 files / 1002 passed |
| `npm run type-check` | exit 0 |
| `npm run type-check:reliability` | exit 0 |
| `npm run type-check:charts` | exit 0 |
| `npm run api:types:check` | exit 0 |
| `npm run lint` | exit 1 on `c4ad77a8` (two NEW diagnostics in the new harness files: unused `mkdir` import, unused parameter); exit 0 after `9f4d9986` — 0 errors / 8 pre-existing warnings, baseline unchanged |
| `npm run build` | exit 0 |
| focused `charts-c2`, `charts-c3`, `charts-c5`, `brokers-security-d7`, `imports-d6`, `layout`, `context`, `dates`, `requests`, `recovery`, `dialogs`, `dialog-recovery`, `d4`, `d5`, `settings-account` | all exit 0 on `c4ad77a8` — including `recovery` and `dialog-recovery` (the task-0 harness repair holds) and `layout` (the historically flaky Year hit-test passed) |
| focused `charts-c4` | exit 1 on `c4ad77a8`: the pilot flow's signed-state wait timed out after 12 s while its own earlier pie assertions and the immediately following FULL matrix (same artifact config, same fixtures) passed; re-run on `9f4d9986` — see below |
| `npm run test:delivery` | exit 0 (rollback artifact; dashboard below the R7 401 kB pre-chart assertion) |
| FULL `npm run test:browser` | exit 0 — 18 routes x 4 viewports, zero fixture mismatches, zero route failures |
| backend `uv run python -m pytest` (test settings) | exit 0 — 1386 passed / 10 skipped (no backend file touched) |

charts-c4 re-run on `9f4d9986`: exit 0 — the full pilot flow passes
(pies, signed state, malformed, legacy-only, stock/bond/crypto histories,
renderer-failure fallback, mobile hit-tests/tooltips, per-flag delivery),
so the matrix failure was the recorded agent-browser transient class (the
same flow passes in the FULL matrix on `c4ad77a8`, which shares the
artifact configuration and fixtures).
charts-c5 re-run on `9f4d9986`: exit 0 — all phases green; measured
delivery dashboard modern 483,951 / NAV-only 543,210 / all-off 345,257 /
fallback-activated 549,587 gzip bytes (run-to-run deltas are content-hash
noise; the budget assertion holds in every run).
lint re-run on `9f4d9986`: exit 0 (0 errors / 8 pre-existing warnings).

### Rollback rehearsal

`scripts/qa-c5-rollback-rehearsal.mjs` rebuilt the app with each family
flag false individually and all three false; every artifact built cleanly
and its identity is recorded locally in
`tests/browser/artifacts/charts-c5-rollback-rehearsal.json` (gitignored,
like the other local delivery records):

| Artifact | Flags (NAV/allocation/security) | Files | Combined SHA-256 (prefix) |
|---|---|---|---|
| rehearsal-nav-off | false/true/true | 153 | (recorded locally) |
| rehearsal-allocation-off | true/false/true | 153 | (recorded locally) |
| rehearsal-security-off | true/true/false | 153 | (recorded locally) |
| rehearsal-all-off | false/false/false | 153 | (recorded locally) |

Accepted-payload fallback rehearsal: charts-c5 phase A exercises the
accepted-payload fallback end-to-end on a built artifact (renderer failure →
explicit "Use previous chart" → the same accepted response rendered by the
lazily downloaded legacy runtime with zero additional API calls), and phase
B renders the all-off rollback artifact.

**Precise prior dual-renderer baseline:** `671171be` is the merged C4
source (PR #59) — the last commit where all three flags are default-OFF
with opt-in exact-`'true'` semantics and eager legacy leaves; this branch
diverges from it through `a5250250` (handoff docs). Restoring that
behavior requires REBUILDING and REDEPLOYING: either build any C5a-or-later
checkout with `VITE_NAV_ECHARTS_ENABLED=false
VITE_ALLOCATION_ECHARTS_ENABLED=false VITE_SECURITY_ECHARTS_ENABLED=false`
(the all-off rollback artifact, rehearsed above), or build from `671171be`
directly. A commit alone is NOT a deployed or tagged rollback release; no
deployment or release tag was created in this assignment, and only the
owner can perform an actual deployment rollback.

## 7. Deviations and limitations

- The inherited `recovery`/`dialog-recovery` covered-click races did not
  reproduce in 14 runs at the pristine base (including under concurrent
  build load) on this machine; the recorded mechanism (clicking without
  awaiting the overlay transition) was closed with a bounded,
  assertion-preserving harness repair instead of being relabeled
  environmental (section 2).
- Security zoom remains view-only and resets when a replacement document
  arrives (C4 recorded limitation, unchanged); the zoom-reset-on-context
  behavior is pinned by the C4 round-2 unit regression
  (`remainingChartIntegration.spec.ts`) and charts-c5 asserts the
  browser-level invariants (no crash, no cross-security leakage, bond
  context renders fully after a zoomed stock).
- The allocation v2 contract stays all-or-nothing (one negotiated response
  carries all three documents; a malformed document fails the whole
  breakdown section) — the C4 recorded behavior, unchanged.
- showTip/dataZoom acceptance hooks (`__c4DispatchAction`) remain attached
  to the host elements by the ECharts leaf components; they are inert in
  production (never called by app code) and exist so the rendered cases can
  drive the REAL chart instances where headless pointer sweeps are
  unreliable.
- Logout-after-zoom was not driven as a full UI logout/login cycle in
  charts-c5 (the fixture server has no login endpoint); context resets are
  covered by the C4 round-2 mounted-page regressions (null-document reset),
  the context-mismatch/bounded-reconciliation flows in charts-c2/c3, and
  charts-c5's security-switch-after-zoom with zero page errors.
- `tsconfig.charts.json` continues to scope the app-graph integration specs
  out of the strict charts project (documented in the config; they stay
  type-checked by the main tsconfig) — the recorded C2/C4 scoping,
  unchanged.
- Chart.js and its companions are NOT removed: package.json and the
  lockfile are untouched (audit-only in C5a); dormant `PriceChart.vue` is
  untouched. C5b owns removal after the owner's release validation cycle.
- Dedicated screen-reader support work and AT audits are out of scope per
  the owner amendment of 5 October 2026 (not an outstanding gap); the
  retained keyboard/focus/labels/contrast/responsive/native-zoom checks
  are covered above and by the inherited suites.

## 8. Acceptance matrix (traced to existing records; nothing rerun)

| Requirement | Record |
|---|---|
| F1 sample alignment approval | PR #46 merged into `codex/frontend-modernization` (merge `607f5383`) — [tracker](../superpowers/plans/2026-09-30-frontend-modernization-progress.md) task 8 |
| F2 contribution boundary approval | PR #47 merged (`71eaa1d7`) — tracker task 9 |
| F3 allocation scale resolution | PR #48 merged (`9b32d3d9`) — tracker task 10; C4's approved ratio contract is the allocation fixture basis (`allocationFixture`) |
| C1 opt-in exact chart contract | PR #49 merged at `7481e060` (reviewed `213e70bf`): legacy compatibility, identity, units, diagnostics, errors; protected `NAV_at_date` diagnostics reviewed and merged by the owner |
| C2 typed adapters and lifecycle | PR #52 user-merged at `2424edbf` (reviewed `5d4c5a87`): validated documents, request lifecycle, bounded reconciliation |
| C3 NAV pilot, 7 modes x 5 frequencies | PR #53 user-merged at `2e77e5c7` (reviewed through `3cd33c06`). Authoritative lists in `frontend/src/features/charts/contracts.ts`: `NavMode` = none, account, asset_type, asset_class, currency, value_contributions, value_contributions_cumulative (7); `Frequency` = D, W, M, Q, Y (5); `navOption.spec.ts` covers all 35 mappings plus toPlotNumber edges, visibility/zoom immutability; review rounds added tooltip containment/horizons (rounds 1-4 records in the tracker) |
| C4 three solid pies + security histories | PR #59 user-merged at `671171be` (reviewed through `4feb48d4`): one pie series per card, server-certified `pieEligibility`, exact tables, account-scope validation, shared plotted-axis zoom model, null-document reset, loading skeleton |
| Races/exact values/keyboard/responsive evidence | C3/C4 review-round records (tracker) + this branch's charts-c5 phase C (legend toggles zero requests, keyboard inspection, zoom/refresh/park retention, malformed/legacy/no-downgrade, 390px hit-tests, mobile tooltip containment, native 200% DPR-verified zoom) |
| Measurements | Section 5 (this document): modern dashboard 483,960 gzip within the ~535 kB cutover target; per-route and per-flag graphs in the local `charts-c5-delivery.json` |
| Licenses | Section 1.3: chart.js 4.4.4 MIT, vue-chartjs 5.3.1 MIT, chartjs-plugin-datalabels 2.2.0 MIT, chartjs-adapter-date-fns 3.0.0 MIT, echarts 6.1.0 Apache-2.0, vue-echarts 8.3.1 MIT, date-fns 3.6.0 MIT (retained) |
| Remaining exceptions | Section 7 |
| Rollback | Section 6: rehearsed per-family and all-off artifacts with local checksums; prior dual-renderer source baseline `671171be`; restoration requires owner build+deploy |
| C5b boundary | Not part of this assignment: dependency/reference removal needs the owner's accepted release validation cycle; Chart.js remains installed; date-fns retained |
