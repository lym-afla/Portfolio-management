# C5a chart cutover implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Prepare a reviewable default-on ECharts release candidate for all six live chart views, with independently reversible gates and a genuinely lazy Chart.js compatibility fallback.

**Architecture:** Retain the accepted v2 transports, exact-value documents and single request owners. Move legacy renderer runtime imports behind asynchronous component boundaries, then change the three release defaults with explicit rollback overrides. C5a ends at a draft PR; C5b dependency removal requires a separately accepted release validation cycle and removal approval.

**Tech stack:** Existing Vue/Vuetify/TypeScript/Vite, ECharts 6.1.0, vue-echarts 8.3.1, retained Chart.js dependencies; Node >=24.20.0 <25, uv backend environment.

**Spec:** [Chart correctness and ECharts plan, C5](2026-09-08-chart-correctness-echarts.md), [master plan](2026-09-08-frontend-modernization.md), [progress tracker](2026-09-30-frontend-modernization-progress.md).

## Starting point and authority

- PR #59 is merged into `codex/frontend-modernization` at `671171be`; final C4 implementation is `4feb48d4`. Start from the latest remote modernization tip including this handoff, not main or an old executor checkout.
- Create `codex/chart-cutover-c5` in a dedicated worktree. Do not switch, reset, stash or modify another executor's checkout. Record clean base SHA and all later tested SHAs.
- Read AGENTS.md, `.memory-bank/index.md`, `.memory-bank/Rules for AI Coding Agent.md`, the three authoritative NAV/calculation/FX documents, and C3/C4 evidence before implementation.
- C4 is integrated, not deployed. The modernization branch is not main. Do not merge, deploy, create release tags or remove Chart.js in this assignment.
- The owner removed dedicated screen-reader work/AT audits on 5 October. Preserve keyboard/focus, readable labels, contrast, semantic markup, exact tables, responsive layouts and native 200% zoom.

## Global constraints

- No backend, protected financial logic, API schema, financial formula, precision, dates or account-selection changes. No new chart library or dependency upgrades. Preserve decimal strings and comma-grouped server displays; convert only at the existing geometry boundary.
- Six live views: NAV, Asset Type pie, Asset Class pie, Currency pie, security price and security position. Three allocation charts remain solid pies when certified eligible; every ineligible state retains its complete signed/status table and declared full-NAV denominator.
- Preserve both independent annualized IRRs and their different horizons; no viewport rebasing. Preserve bond percent-of-nominal units, duplicate-date events, quantity precision, annotated carry-forward and observed-only tables.
- One request owner per resource. Legacy-only compatibility and renderer retry/fallback use the same accepted response, never an extra request or reinterpretation of malformed v2.
- Preserve C4 accountIds checks, independent section loading, shared plotted-axis zoom keys, null-document reset and genuine compatible-refresh retention. Preserve D6/D7 lifecycle and credential fixes.

## Review focus

1. Missing/false/malformed flags: independent deterministic selection and reproducible rollback builds (task 2).
2. Failed async renderer imports and explicit fallback: usable retry, exact accepted data, no request loops or silent downgrade (task 1).
3. Zoomed charts during refresh, context reset, route replacement and logout: retained compatible state, reset incompatible state, no stale callbacks/null crashes (task 3).
4. All modern views active together: full cold-route cost, no eager legacy runtime or chart imports on unrelated routes (tasks 1 and 3).
5. Overlay transitions and fixed headers: genuinely hittable recovery controls and tooltips at mobile/native zoom (tasks 0 and 3).

## File map

- Policy: `frontend/src/features/charts/rendererPolicy.ts`; create `__tests__/rendererPolicy.spec.ts` there.
- NAV shell/fallback: `frontend/src/components/dashboard/NAVChart.vue`, `frontend/src/components/charts/StackedBarLineChart.vue`, `frontend/src/features/charts/NavChartPanel.vue`, `ChartHost.vue`.
- Allocation shell/fallback: `frontend/src/components/dashboard/BreakdownChart.vue`; create `frontend/src/components/charts/LegacyAllocationChart.vue` for the incumbent Bar, registration and datalabel plugin only.
- Security fallback: `frontend/src/views/database/SecurityDetailPage.vue`, `frontend/src/components/charts/LineChart.vue`. Move runtime registration/date-adapter side effects into the lazy legacy leaf. Preserve existing option factories and their behavior.
- Shared audit: `frontend/src/config/chartConfig.js`, `frontend/src/features/securities/useSecurityDetail.ts`, `frontend/vite.config.js`, all chart importers and `frontend/package.json`/lockfile (audit only; no removal).
- Verification: existing chart feature suites, `frontend/tests/browser/run-smoke.mjs`, `recovery.mjs`, `fixture-server.mjs`, C3/C4 cases; create `frontend/tests/browser/charts-c5.mjs` and register `charts-c5`.
- Evidence: create `docs/design/frontend-chart-cutover.md`; update progress tracker and `.memory-bank/Tech details/frontend.md` and `NAV Function and FX Flow.md` only to describe accepted frontend boundaries, not financial behavior.

## Task 0 — Establish release baseline and close inherited recovery exceptions

- [ ] Install from lockfiles in the isolated worktree. Record Node/browser versions, base SHA, three actual build flag values, baseline tests, lint and route delivery. Current historical reference: executor 974 units, lint 0 errors/8 warnings; backend 1386 passed/10 skipped. These are not target counts or current verification.
- [ ] Inventory every live and dormant Chart.js reference, transitive registration/plugin/date-adapter import, and six-view fallback. Include `PriceChart.vue` even if unused. Record licenses from installed packages and retained date-fns non-chart consumers. Do not delete audit candidates now.
- [ ] Reproduce `recovery` and `dialog-recovery` individually on the pristine base. C4 recorded overlay-scrim Retry races; the full route matrix did not close these exceptions. If still present, record the covering element and fix the bounded harness synchronization when it is a harness defect: await the real overlay transition and verify Retry is visible/hittable, without force clicks or dropping assertions. If application behavior is defective, make the minimal recovery fix with a RED regression. Do not relabel a genuine failure environmental based on another green case.
- [ ] Rerun both exact scenarios and commit any bounded repair separately. If a release-blocking issue cannot be resolved within scope, finish independent work and document the blocked gate; do not declare default-on readiness.

## Task 1 — Make legacy fallback genuinely lazy

**Interface:** retain all existing props/events/slots and detached legacy copies. Only mounted legacy renderer leaves import Chart.js/vue-chartjs/plugins/date adapter; shell components and modern paths must not.

- [ ] Write failing delivery tests: on a clean all-modern v2 route, no Chart.js runtime modules are loaded; invoking user-chosen fallback loads the legacy runtime and renders the same response, with zero additional API calls. Test genuine legacy-only responses and explicit flag-off routes too.
- [ ] Extract the allocation legacy leaf and asynchronously load existing NAV/security legacy leaves. Remove eager side-effect imports/registration from shells; keep correct registration in lazy leaves. Audit shared helpers for transitive eager imports. Avoid a broad config rewrite or removal of dormant components.
- [ ] Test a rejected lazy chunk load, explicit Retry and recovery; errors must remain visible and recoverable, not an empty-success chart or infinite load loop. Distinguish data/contract errors from renderer errors. Preserve exact table access and honest legacy-only notices.
- [ ] Prove flag-off builds load no ECharts runtime and flag-on v2 paths load no Chart.js runtime until fallback. Test mixed families: activating the NAV fallback must not switch allocation/security policy or trigger refetches. Run focused unit/integration/delivery tests and commit.

## Task 2 — Deterministic default-on release policy

**Interface:** preserve `pilotRequested()`, `allocationEchartsRequested()`, `securityEchartsRequested()` and `resolveRenderer`. Use one small pure flag parser: absent (`undefined`) => true for the reviewed candidate; exact `'true'` => true; exact `'false'` => false; any other supplied string, including empty, => false. Document this conservative malformed-value behavior. This deliberately supersedes C3/C4 opt-in defaults only in this C5 candidate.

- [ ] RED policy tests cover undefined/true/false/empty/uppercase/whitespace/other values for each independent flag, every capability outcome and null data. Present-invalid v2 never becomes a successful legacy response.
- [ ] First verify a NAV-only artifact (NAV true, allocation/security false), then the all-modern candidate after that passes. These are local release-candidate stages, not permission to deploy. Keep the three existing environment names and document that Vite flags require rebuild/redeploy; they are not runtime kill switches.
- [ ] Change the three missing-flag defaults only after task 1 and baseline gates are ready. Explicit false must restore the corresponding legacy family, with allocations clearly documented as transitional bars. Do not change deployment configuration or install a release on a server.
- [ ] Update older pilot tests and harness builds to explicitly set false when testing rollback; do not remove flag-off assertions or replace them with weaker defaults. Test all eight boolean flag combinations at policy level and rendered independence for each single-family plus all-on/all-off artifacts. Commit policy separately from lazy extraction.

## Task 3 — Combined release-candidate acceptance and measured delivery

- [ ] Add `charts-c5`: build clean artifacts with explicit flags and also test the no-flags candidate. Verify all six views together, three solid pies, both independent IRRs/horizons, unit labels, exact comma-grouped values, large quantities, statuses/known subtotals, signed/incomplete/nonpartitioning/nonpositive allocations, empty documents and legacy-only notices.
- [ ] Test malformed-v2/API error without downgrade, renderer failure/retry/user-chosen fallback, context mismatches and bounded reconciliation. Assert request counts and immutable accepted data. Repeat actual compatible refresh after zoom; park responses during period changes; reset context/logout and switch security after zoom, including carry-forward-only ranges. No null crashes or cross-context zoom leakage.
- [ ] Exercise normal pointer and keyboard entry as well as deterministic showTip geometry probes. A programmatic tooltip hook alone does not prove ordinary hover works. Test legend/table controls, long tooltip content at both edges and several scroll positions below fixed headers, desktop-to-390-to-desktop, native 200% zoom with DPR verified and reset.
- [ ] Measure COMPLETE cold-route JS+CSS gzip and loaded module graphs for login, profile, transactions, dashboard and security detail: modern default, NAV-only, all-off rollback and fallback activated. Use fresh sessions/artifacts; report bytes, uncompressed totals, timing environment and fonts separately, with exclusions explicit. No chart runtime on login/profile/transactions. Distinguish emitted chunks from actually fetched modules.
- [ ] Compare all-modern dashboard against the saved approximately 535 kB cutover target (and historical approximately 401 kB pre-chart target). C4 dashboard allocation-on measurement was 549,104 bytes gzip and was not combined all-on acceptance. Reduce needless eager loading first. Do not silently raise budgets or omit modules; if target is missed, record exact bytes, cause and tradeoff for review, keep readiness pending. Runtime timings on loopback are not production latency evidence.
- [ ] Capture synthetic all-modern dashboard, both IRR controls/table, ineligible allocation table, bond/crypto security histories, mobile tooltip and native zoom. Verify images themselves and record SHA/viewport/flags/geometry. Do not rewrite unrelated historical captures.

## Task 4 — Final gates, rollback rehearsal and handoff

- [ ] Run heavy gates sequentially on the final committed implementation: frontend `npm run test:unit`, `type-check`, `type-check:reliability`, `type-check:charts`, `api:types:check`, `lint`, `build`, `test:browser`, `test:delivery`; new `test:browser -- --case charts-c5`; existing focused `charts-c2`, `charts-c3`, `charts-c4`, `brokers-security-d7`, `imports-d6`, `layout`, `context`, `dates`, `requests`, `recovery`, `dialogs`, `dialog-recovery`, `d4`, `d5`, `settings-account`. Capture each actual exit code, not a piped summary. Do not weaken lint/type scopes or skip stale baseline diagnostics.
- [ ] Backend from `backend/`: `uv run python -m pytest` with repository test settings and coverage intact. Backend code remains untouched. Re-run only gates affected by subsequent changes, and clearly identify exactly which committed tree the full matrix covered.
- [ ] Rehearse rebuilding with each family false and all false, test accepted-payload fallback and record rollback artifact identity/checksum locally. Document the precise prior dual-renderer commit (`671171be` is the merged C4 source baseline), required build settings and restoration procedure. A commit alone is not a deployed/tagged rollback release; do not claim it is.
- [ ] Write acceptance matrix tracing F1/F2 approval and F3 resolution to existing records, C1/C2 contracts, C3 NAV 7-mode x 5-frequency coverage (read authoritative lists), C4 six views, races, exact values, keyboard/responsive evidence, measurements, licenses and remaining exceptions. Do not rerun financial investigations or invent prior approvals.
- [ ] Update tracker as C5a implemented/pending review, not C5 complete. Push `codex/chart-cutover-c5`; open one draft PR into `codex/frontend-modernization` with tested head, real gate outcomes, captures, delivery tradeoffs and rollback instructions. Stop for review. No main merge, deploy, dependency removal or D8 implementation.

## C5b and release boundary (not part of executor assignment)

The owner must review the candidate and accept a complete release validation cycle covering ordinary refresh, context changes and all six views before approving removal. Synthetic local tests are release-candidate evidence, not proof of an observed production cycle. C5b will separately audit remaining references, decide legacy-only behavior after removal, remove obsolete wrappers/dependencies with package/lockfile changes, prove no Chart.js remains and retain the prior dual-renderer release as rollback. Keep date-fns where non-chart code uses it. D8 remains final application-wide QA; C5 stays incomplete until its release/removal obligations are resolved.
