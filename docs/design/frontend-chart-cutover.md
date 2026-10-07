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

