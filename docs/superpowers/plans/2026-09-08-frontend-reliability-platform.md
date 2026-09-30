# Frontend Reliability and Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Make portfolio context, query results, retry recovery and page layout trustworthy, then reduce delivery cost and strengthen the frontend's typed boundaries.

**Architecture:** Keep Vue, Pinia, Vuetify and the established routes. Introduce an atomic committed portfolio context and a small latest-request runner; legacy app-store and API exports remain compatibility adapters. Give browser geometry, query ordering and recovery their own regression gates instead of relying on source-string tests.

**Tech Stack:** Existing Vue 3, Vite, Pinia, Vuetify, Axios, Vitest and TypeScript; Node 24.20.0; agent-browser for browser automation. No query-cache library and no new financial calculation library.

**Spec:** [Accepted frontend audit](../../audits/2026-09-08-frontend-audit.md). Also preserve [the approved tables design](../specs/2026-08-18-tables-visual-redesign-design.md).

## Global Constraints

- This document is a plan only. Its creation does not authorize deployments, production access or source changes in this turn.
- The master plan owns rollout sequence, cross-plan dependencies and shared acceptance. R1–R8 below are reviewable PR identifiers, not a mandate to implement in numeric order.
- Pin frontend/.node-version to 24.20.0; package engines are >=24.20.0 <25. Both GitHub workflows use node-version-file: frontend/.node-version. Use the same runtime for development, testing and building; future patch changes receive a maintenance PR. Node 20 is not the target. Source: https://nodejs.org/en/about/previous-releases.
- Read AGENTS.md, .memory-bank/index.md and .memory-bank/Rules for AI Coding Agent.md before implementation. Read the canonical NAV/calculation documents before any change that can affect displayed financial outputs.
- Preserve all existing selection variants: all, account, broker and group. Keep date, currency and digits settings atomic because the existing SettingsDialog persists them together.
- Do not change financial formulas, raw monetary precision, rounding, endpoint semantics, saved user selections, two-row grouped headers, server pagination, totals, sticky identities or chart/table alternatives.
- Every implementation PR runs the full backend command from backend/: uv run python -m pytest. This remains a project rule even for frontend-only changes. Record existing failures explicitly; do not call a failing suite a pass or silently waive this gate.
- Frontend commands below run from frontend/ unless explicitly marked repository root. No command uses the obsolete portfolio-frontend directory.
- No automerge. Use codex/ branches, small commits and reviewed PRs. Changes that affect financial outputs require the project's needs-approval process and explicit human approval before merge; do not edit protected backend files incidentally.
- Browser fixtures live under frontend/tests/browser and use synthetic data, an isolated origin and a dedicated browser session. Do not add a production auth bypass, production fixture route or live-account test credentials.
- New modules use strict TypeScript. Keep the migration bounded; do not mechanically convert all 62 SFCs or add broad type assertions to suppress errors.
- Retain src/services/api.ts named exports when moving implementation into domain modules. New typed modules must not import the legacy router/store/API cycle.
- The audit's measurements are a baseline, not fresh results: build passed in 15.37 seconds; JS 415.12 kB gzip, CSS 119.70 kB gzip; MDI WOFF2 403.21 kB; 85 unit tests passed and 22 failed with undefined localStorage on Node 26.8.1. A runtime-flag rerun had the same result. Do not describe the 22 failures as independently established application bugs.

## File and interface ownership

| PR | Existing files to modify | Proposed files and responsibility |
|---|---|---|
| R1 | frontend/package.json; package-lock.json; vite.config.js; tests/unit/setup.js; .eslintrc.js; .github/workflows/ci.yml; .github/workflows/pr-checks.yml | frontend/.node-version; eslint.config.mjs; tsconfig.reliability.json; tests/unit/helpers/memoryStorage.ts; tests/unit/harness/storage.spec.ts; tests/browser/run-smoke.mjs; tests/browser/fixture-server.mjs; tests/browser/fixtures.mjs; tests/browser/routes.mjs; tests/browser/protocol.mjs; scripts/check-lint-scope.mjs |
| R2 | frontend/src/App.vue; frontend/tests/unit/AppLayout.spec.js | frontend/tests/browser/layout.mjs: actual app-bar/content geometry assertions |
| R3 | frontend/src/stores/app.ts; stores/auth.ts; components/AccountSelection.vue; components/SettingsDialog.vue; config/axiosConfig.ts | frontend/src/types/portfolioContext.ts; stores/portfolioContext.ts; tests/unit/stores/portfolioContext.spec.ts; tests/unit/components/AccountSelection.context.spec.ts; tests/unit/components/SettingsDialog.context.spec.ts |
| R4 | frontend/src/composables/useTableSettings.ts; utils/dateUtils.js; components/PositionsPageBase.vue; views/TransactionsPage.vue; views/database/FXPage.vue; components/SettingsDialog.vue | frontend/tests/unit/composables/useTableSettings.spec.ts |
| R5 | frontend/src/components/PositionsPageBase.vue; views/OpenPositionsPage.vue; views/ClosedPositionsPage.vue; views/TransactionsPage.vue; views/database/FXPage.vue; views/database/PricesPage.vue; views/database/SecuritiesPage.vue; views/database/AccountsPage.vue; views/database/BrokersPage.vue; views/database/SecurityDetailPage.vue; views/SummaryPage.vue; services/api.ts | frontend/src/composables/useLatestRequest.ts; types/query.ts; tests/unit/helpers/deferred.ts; tests/unit/composables/useLatestRequest.spec.ts; tests/unit/components/TableRequests.spec.ts |
| R6 | frontend/src/views/DashboardPage.vue; tests/unit/components/DashboardPage.retry.spec.js; services/api.ts | frontend/tests/unit/components/DashboardPage.requests.spec.ts; tests/browser/recovery.mjs |
| R7 | frontend/src/router/index.js; main.js; package.json; package-lock.json; components/dialogs and callers where on-demand loading applies | frontend/src/plugins/icons.ts; scripts/measure-route-bundles.mjs; tests/browser/delivery.mjs; tests/unit/config/icons.spec.ts |
| R8 | frontend/src/services/api.ts; config/axiosConfig.ts; main.js; tsconfig.json; scripts/generate-api-types.sh | frontend/src/services/http/client.ts; services/http/errors.ts; services/api/context.ts; services/api/portfolio.ts; services/api/transactions.ts; services/api/database.ts; types/portfolioTables.ts; tests/unit/services/apiContracts.spec.ts; tests/unit/services/apiCompatibility.spec.ts |

R8's typed transport foundation can land immediately after R1 and before R3. R3 supplies context to R4/R5/R6 and the design/chart plans. R5 supplies the generic runner to chart consumers; R6 owns the current Dashboard loader integration. Coordinate edits to DashboardPage.vue and App.vue through the master rather than allowing competing simultaneous patches.

### Shared committed context contract

~~~ts
export type AccountSelection =
  | Readonly<{ type: 'all'; id: null }>
  | Readonly<{ type: 'account' | 'broker' | 'group'; id: number }>

export interface PortfolioContext {
  readonly revision: number
  readonly accountSelection: AccountSelection
  readonly effectiveCurrentDate: string | null
  readonly currency: string | null // canonical backend currency code
  readonly digits: number
}

export type ContextPatch =
  | { accountSelection: AccountSelection }
  | { effectiveCurrentDate: string; currency: string; digits: number }

// Pinia store public interface; refs are unwrapped by Pinia.
// committed is replaced atomically, never mutated field by field.
// Expose transitionError as Error|null, not a raw Axios object.
interface PortfolioContextStore {
  committed: Readonly<PortfolioContext>
  isTransitioning: boolean
  isReady: boolean
  transitionError: Error | null
  changeContext(patch: ContextPatch): Promise<void>
  reconcileContext(): Promise<void>
}
~~~

Account labels/symbols remain presentation mappings and do not replace the canonical currency or selection in this contract. Digits is a formatting preference, but its successful mutation is part of the same atomic settings commit.

### Shared request contract

~~~ts
import type { Ref, ShallowRef } from 'vue'

export type LatestResult<T> =
  | { status: 'accepted'; data: T }
  | { status: 'discarded' }
  | { status: 'failed'; error: Error }

export interface LatestRequest<TParams, TData> {
  data: Readonly<ShallowRef<TData | null>>
  error: Readonly<ShallowRef<Error | null>>
  loading: Readonly<Ref<boolean>>
  run(params: TParams): Promise<LatestResult<TData>>
  invalidate(): void
}

export function useLatestRequest<TParams, TData>(
  fetcher: (
    params: Readonly<TParams>,
    options: { signal: AbortSignal }
  ) => Promise<TData>,
  snapshot: (params: TParams) => Readonly<TParams>
): LatestRequest<TParams, TData>
~~~

The snapshot function must copy/freeze nested context, sorting descriptors and arrays. A shallow copy of reactive params is insufficient. run clears the local error and retains same-context data while loading; invalidate aborts and clears data/error/loading. Discarded responses cannot update any dependent totals, legends, cash balances or loading states. Chart consumers can retain a mounted renderer and overlay loading while same-context requests run.

## R1 — Make runtime and verification gates reliable

**Outcome:** The supported runtime has deterministic browser-storage test setup, the entire unit suite runs in CI, and lint genuinely covers Vue and TypeScript.

**Consumes:** Existing scripts and the master Node policy. **Produces:** npm run test:unit, lint, type-check, type-check:reliability, build and test:browser with explicit scope and actionable failures.

- [ ] **1. Characterize the baseline under the pinned runtime.** Inspect package engines/peer dependencies before modifying dev tooling. Run node --version, npm ci, npm run test:unit, npm run type-check and npm run build; retain full logs in PR artifacts. Verify installed CLI commands with agent-browser --help. Do not assume changing Node alone fixes localStorage.
- [ ] **2. Write storage-isolation regressions.**

~~~ts
import { beforeEach, expect, it } from 'vitest'
import { createMemoryStorage } from '../helpers/memoryStorage'

beforeEach(() => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: createMemoryStorage(),
  })
})
it('supports the browser storage API without native Node persistence', () => {
  localStorage.setItem('accountSelection', '{"type":"all","id":null}')
  expect(localStorage.getItem('accountSelection')).toContain('"all"')
  expect(localStorage.length).toBe(1)
  localStorage.removeItem('accountSelection')
  expect(localStorage.getItem('accountSelection')).toBeNull()
})
it('starts each test with empty storage', () => {
  expect(localStorage.length).toBe(0)
})
~~~

Run npm run test:unit -- tests/unit/harness/storage.spec.ts before implementation; expected failure is the absent helper. Existing failure cases in PositionsPageBase and TransactionDescription must then pass without browser-storage flags.

- [ ] **3. Implement the Storage helper and install it before store creation.** Return a Storage-compatible object backed by Map<string,string>: length getter; getItem returns null on absence; setItem stringifies key/value; removeItem, clear and key(index) implement browser behavior. Install a fresh instance in shared setup before each test, including explicit sessionStorage if tests use it. No real token persistence. Keep custom test stubs local to the tests that require them.
- [ ] **4. Replace the ineffective lint scope with explicit Vue/TS parsing.** Remove .eslintrc.js when eslint.config.mjs becomes authoritative. Resolve compatible released versions for ESLint, eslint-plugin-vue and typescript-eslint, inspect peer requirements against Node 24.20.0, then pin exact dev versions and commit package-lock.json. Flat config must use the Vue parser for SFCs and the TypeScript parser inside script blocks. Include src/**/*.{js,ts,vue} and tests/**/*.{js,ts}; include .ts in the format script. Do not disable Vue parsing or type syntax to obtain a green result.

~~~js
// Representative flat-config shape; use installed packages' exported presets.
import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'
export default [
  { ignores: ['dist/**', 'node_modules/**', 'src/types/api.d.ts'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs['flat/essential'],
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
]
~~~

Add browser/Node/Vitest globals in their matching file scopes. Preserve documented unrelated legacy warnings in a checked baseline rather than doing cosmetic cleanup. Zero lint errors in changed/new modules; do not exclude changed paths from enforcement. scripts/check-lint-scope.mjs creates temporary representative .ts and .vue inputs containing undefined identifiers, invokes ESLint with --stdin --stdin-filename, asserts each fails, and removes no source files.

- [ ] **5. Add strict checking for the new dependency-leaf modules.** tsconfig.reliability.json extends the current config with strict: true and checkJs: false, and includes the new context/query/contracts/transport modules and their tests. Keep this strict graph free of legacy store/router/API imports; R8 provides dependency injection and compatibility adapters in the opposite direction. TypeScript includes transitive imports, so a narrow include list alone is not an exemption mechanism. Retain the existing global type-check gate.
- [ ] **6. Establish the real-browser harness.** Pin agent-browser as a dev tool after checking the actual package's Node/browser requirements. Add npm run test:browser that invokes tests/browser/run-smoke.mjs. The runner starts the built app and a test-only fixture origin, invokes the CLI with execFile argument arrays, and always closes its session/servers in finally. protocol.mjs parses --json results according to the installed CLI's actual documented schema; fixture-server rejects unmatched API requests so incomplete fixtures cannot masquerade as product failures.
- [ ] **7. Enumerate every existing route in tests/browser/routes.mjs.** Include login/register; dashboard; open/closed positions; transactions; profile/edit/settings; database and each broker/account/price/security/FX child; a security-detail fixture; summary; root redirect. Synthetic authenticated boot runs before importing the real application, in a test-owned harness only. Add no production test route. Run the desktop/mobile/tablet/zoom matrix from the master; R2/R6 append meaningful assertions.
- [ ] **8. Update both workflows and run final gates.** Use actions/setup-node node-version-file, npm ci, complete unit tests, explicit lint, both type checks, build, CLI browser install and test:browser. Upload test/browser logs and failed screenshots. Preserve existing backend checks and add/retain the complete pytest gate required by the project; do not quietly replace it with the existing focused crypto subset.

**Acceptance:** All tests pass under Node 24.20.0 without native storage flags or skipped failing suites; a deliberate .vue/.ts lint defect is detected; real browser automation fails on unmatched fixture requests; complete pytest passes or the PR clearly remains blocked on a documented existing failure.

**Commit/PR:** codex/frontend-r1-runtime-gates; build: establish complete frontend verification gates. Commit runtime/config, harness tests and workflow changes together. **Rollback:** revert this PR as a unit if tool incompatibility prevents clean install; do not retain a CI configuration that claims coverage while omitting failing commands.

## R2 — Repair the app-bar/main layout contract

**Outcome:** The header does not cover content at scroll position zero on any authenticated route.

**Consumes:** R1 browser harness. **Produces:** Correct Vuetify layout registration; layout.mjs with rectangle assertions. This PR is the basic correctness repair; the design plan owns later shell restructuring.

- [ ] **1. Add the failing browser geometry case.** In layout.mjs, inspect the real rendered Vuetify nodes rather than asserting source strings. Use agent-browser open, snapshot -i and eval in the isolated fixture.

~~~js
// Evaluate in the rendered page; return plain values to the Node assertion.
const bar = document.querySelector('.v-app-bar').getBoundingClientRect()
const content = document.querySelector('[data-testid="route-content"]')
  .getBoundingClientRect()
return { headerBottom: bar.bottom, contentTop: content.top, scrollY }
// Node assertion:
assert.equal(result.scrollY, 0)
assert.ok(result.contentTop >= result.headerBottom - 1)
~~~

Run npm run test:browser -- --case layout; expect failure matching the audited overlap, not a missing selector or incomplete fixture.

- [ ] **2. Check Vuetify's installed app-bar layout registration and replace height="auto" with a finite supported value.** Preserve v-app/v-main ownership and remove no established table styles. Prefer a supported intrinsic/extended toolbar layout if it represents the existing two rows. If the wrapped account/title rows remain variable-height, measure the intrinsic content wrapper and pass its numeric height to Vuetify:

~~~vue
<v-app-bar :height="appBarHeight">
  <div ref="appBarContent" style="width: 100%; height: max-content">
    <!-- Existing title, account selection and settings content moves here. -->
  </div>
</v-app-bar>
~~~

~~~ts
const appBarHeight = ref(144) // startup fallback only, never v-main padding
const appBarContent = ref<HTMLElement | null>(null)
let observer: ResizeObserver | null = null
watch(appBarContent, (element) => {
  observer?.disconnect()
  if (!element) return
  const measure = () => {
    const height = Math.ceil(element.getBoundingClientRect().height)
    if (height > 0 && height !== appBarHeight.value) appBarHeight.value = height
  }
  observer = new ResizeObserver(measure)
  observer.observe(element)
  measure()
}, { flush: 'post' })
onUnmounted(() => observer?.disconnect())
~~~

The fallback is not a hardcoded content offset. Avoid a ResizeObserver feedback loop by measuring the intrinsic child rather than the fixed-height toolbar itself. No route-specific padding compensation.

- [ ] **3. Replace the source-string-only layout acceptance test.** Keep useful source hygiene assertions only as secondary tests. Give the route content wrapper a stable test ID. Verify actual height changes after title/account wrapping, settings-only routes and route transitions.
- [ ] **4. Run layout checks at 1440×1000, 390×844 and 1024×768, plus 200% zoom/focused regions; run all R1 gates and full pytest.** Expected: no covered headings, positive registered layout offset, no ResizeObserver warnings, no new horizontal clipping.

**Acceptance:** Header and content rectangles do not overlap at scroll zero across the route manifest and viewport matrix. **Commit/PR:** codex/frontend-r2-layout-contract; fix: register the app bar height with Vuetify layout. **Rollback:** revert App.vue and layout assertion changes together; later design work must retain the verified geometry contract rather than depending on the temporary implementation.

## R3 — Commit portfolio context atomically

**Outcome:** The selector, settings and result context cannot describe a backend selection that failed to persist.

**Consumes:** R8 typed context transport and the shared PortfolioContext contract. **Produces:** usePortfolioContextStore with the contract above; compatibility delegation in app.ts; a synchronized bootstrap in auth.ts.

- [ ] **1. Write failing store and UI tests with controlled deferred backend operations.**

~~~ts
it('keeps the committed account when persistence fails', async () => {
  const context = usePortfolioContextStore()
  await context.reconcileContext() // fixture backend returns account 1
  backend.updateAccount.mockRejectedValueOnce(new Error('Connection lost'))
  await expect(context.changeContext({
    accountSelection: { type: 'account', id: 2 },
  })).rejects.toThrow('Connection lost')
  expect(context.committed.accountSelection).toEqual({ type: 'account', id: 1 })
  expect(context.transitionError).toBeInstanceOf(Error)
})
it('commits date, currency and digits together after session refresh', async () => {
  const pending = context.changeContext({
    effectiveCurrentDate: '2025-12-31', currency: 'EUR', digits: 4,
  })
  expect(context.committed).toMatchObject({ currency: 'USD', digits: 2 })
  refresh.resolve()
  await pending
  expect(context.committed).toMatchObject({
    effectiveCurrentDate: '2025-12-31', currency: 'EUR', digits: 4,
  })
})
~~~

The tests configure the typed backend fixture before store creation; define backend/refresh/context in beforeEach, with backend.read returning the initial complete fixture. Add account, broker, group and all cases; two rapid queued changes; a failed operation followed by a successful queued operation; ambiguous network outcome requiring reconciliation; and logout during an outstanding mutation.

Run npm run test:unit -- portfolioContext AccountSelection.context SettingsDialog.context; expected initial failure is missing store/atomic behavior.

- [ ] **2. Implement a serialized transition queue that remains usable after rejection.**

~~~ts
let queue: Promise<void> = Promise.resolve()
function changeContext(patch: ContextPatch): Promise<void> {
  const operation = queue.then(() => applyTransition(copyPatch(patch)))
  queue = operation.catch(() => undefined)
  return operation
}
~~~

copyPatch copies/freezes the discriminated patch; validate IDs/date/currency/digits against backend choices before sending. applyTransition increments revision and sets isTransitioning synchronously before its first await; readers watch that revision to invalidate outstanding work and suspend new reads. Keep the prior committed values visible with a busy state. Persist the account or complete settings tuple, finish required token/session refresh, then read back canonical context and replace committed once. Emit the compatibility dataRefreshTrigger only after readiness resumes.

For a response failure known to reject the mutation, retain the old committed tuple and expose the error. For network loss or partial settings/token-refresh completion, call reconcileContext before enabling reads; if reconciliation fails, set isReady=false and show a context-recovery action. Do not pretend the old or new server context is known. Do not automatically write a compensating server rollback. A generation/session epoch prevents a late response after logout from resurrecting context.

Public reconcileContext uses the same serial queue. Inside applyTransition, call a private readAndCommit helper directly rather than awaiting a new queued reconciliation behind itself. Before a queued mutation starts while isReady=false, attempt that read-only reconciliation; reject without another server mutation if it still fails. Increment committed.revision by replacing the snapshot with the same previous values at transition start, then replace its values atomically after confirmation; the revision remains the same for that transition's accepted result.

- [ ] **3. Centralize initialization and persistence compatibility.** Hydrate canonical values from user/settings/account-choice responses; localStorage is only a validated fallback for anonymous/bootstrap display. Catch invalid JSON and discard invalid selections. app.ts existing getters/actions delegate to the context store; do not maintain a second mutable context. auth.ts initialization invokes reconciliation once and logout resets context/readiness. Keep labels/currency symbols separate from canonical currency codes.
- [ ] **4. Change AccountSelection to render committed state and emit mutation intent.** Use a separate pending choice for keyboard interaction if needed; disable account arrows/commit controls during a pending transition. On failure, retain/revert to committed selection and show the actual error. SettingsDialog sends the entire date/currency/digits tuple to changeContext and closes only after atomic success.
- [ ] **5. Make required effective-date token refresh a real success condition.** The current updateDashboardSettings path catches refresh failure and still returns success. The new typed context transport must reject that operation and reconcile. Keep the Axios refresh queue as the single synchronization mechanism; effective-date refresh must join the same coordination rather than rotate tokens concurrently through an independent path. Add a concurrent 401 plus settings-refresh test in axiosConfig.spec.ts.
- [ ] **6. Run the failing cases, full R1 gates, browser account/settings failure cases and full pytest.** Test the visible label and displayed result context, not only API invocation counts.

**Acceptance:** Failed/queued/ambiguous mutations never expose an unconfirmed context as current; date, currency and digits commit together; broker/group selection and existing persistence remain compatible. **Commit/PR:** codex/frontend-r3-committed-context; fix: coordinate committed portfolio context. **Rollback:** revert the entire store/delegation/UI change together; no database schema or server data rollback is required. Record this PR as behavior affecting displayed financial outputs and require human review.

## R4 — Derive date presets from the committed effective date

**Outcome:** Changing the effective date without navigation changes the next YTD/all-time query correctly.

**Consumes:** R3 committed context. **Produces:** Reactive date-range derivation in useTableSettings; a single table-range update per preset/context change.

- [ ] **1. Add the exact stale-date regression.**

~~~ts
it('uses the newly committed effective date for the next preset', async () => {
  backend.read.mockResolvedValue(contextFixture('2026-09-08'))
  const context = usePortfolioContextStore()
  await context.reconcileContext()
  const settings = useTableSettings()
  backend.read.mockResolvedValue(contextFixture('2025-12-31'))
  await context.reconcileContext()
  await settings.handleTimespanChange('ytd')
  expect(settings.dateFrom.value).toBe('2025-01-01')
  expect(settings.dateTo.value).toBe('2025-12-31')
})
~~~

contextFixture returns all required context fields with an all-account selection, USD, digits 2 and the passed ISO date. Cover all_time with null start, a specific calendar year, leap day and a custom explicit range. Preserve the existing behavior for explicit ranges instead of silently rebasing them.

Run npm run test:unit -- useTableSettings; expect the old copied ref to produce 2026 dates.

- [ ] **2. Replace the copied ref and remove competing range writes.**

~~~ts
const context = usePortfolioContextStore()
const effectiveCurrentDate = computed(
  () => context.committed.effectiveCurrentDate
)
// Preset changes compute once from this current value and commit the complete
// { timespan, dateFrom, dateTo, page: 1 } object through updateTableSettings.
~~~

If no effective date is ready, await reconcileContext or return a recoverable not-ready state; do not silently substitute the browser's current date. A context commit recalculates relative presets once; explicit date ranges remain explicit. Remove the parallel manual preset calculation in SettingsDialog so it cannot race the table watcher.
- [ ] **3. Give each table one canonical parameter-change path.** A date-range change updates state only; the fetch watcher is the sole query trigger. Reset page to 1 on filter/range/account changes. Keep page-size preferences and the existing grouped-table behavior. Cancel pending debounced search writes on unmount so an old page cannot change the next page's filters.
- [ ] **4. Run focused date tests, current positions/FX/transactions tests, all R1 gates and full pytest.** Expected: exactly one fetch for the resulting committed parameter tuple, with the new date.

**Acceptance:** The audited 2025/2026 stale-date case passes on a mounted page, with no page reload or calendar-time fallback. **Commit/PR:** codex/frontend-r4-effective-date; fix: derive table ranges from committed context. **Rollback:** revert date derivation and callers together; do not change server dates.

## R5 — Apply the latest-request lifecycle to tables and detail views

**Outcome:** Old responses, cancellation and concurrent requests cannot overwrite newer context or silently drop changed parameters.

**Consumes:** R3 context, R4 canonical table params, R8 optional AbortSignal transport support. **Produces:** useLatestRequest with the shared signature and migrated non-dashboard data loaders. Chart and Dashboard consumers use the same runner through their own tasks.

- [ ] **1. Create a controlled deferred helper and failing runner tests.**

~~~ts
export function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

it('discards an old response even when transport ignores abort', async () => {
  const old = deferred<string[]>()
  const current = deferred<string[]>()
  const fetcher = vi.fn().mockReturnValueOnce(old.promise)
    .mockReturnValueOnce(current.promise)
  const query = useLatestRequest(fetcher, p => Object.freeze({ ...p }))
  const first = query.run({ search: 'old' })
  const second = query.run({ search: 'new' })
  current.resolve(['new response'])
  expect((await second).status).toBe('accepted')
  old.resolve(['old response'])
  expect((await first).status).toBe('discarded')
  expect(query.data.value).toEqual(['new response'])
  expect(query.loading.value).toBe(false)
})
~~~

Also test invalidation during pending work; late rejection after current success; first request finishing while second still loads; an AbortError from invalidation; rejected then successful retry; caller mutation of nested params; and disposal. Run npm run test:unit -- useLatestRequest before implementation; expected missing-module failure.

- [ ] **2. Implement the runner with a generation check on every side effect.**

~~~ts
let generation = 0
let controller: AbortController | null = null
async function run(params: TParams): Promise<LatestResult<TData>> {
  const captured = snapshot(params)
  const mine = ++generation
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  loading.value = true
  error.value = null
  try {
    const next = await fetcher(captured, { signal })
    if (mine !== generation || signal.aborted) return { status: 'discarded' }
    data.value = next
    return { status: 'accepted', data: next }
  } catch (cause) {
    if (mine !== generation || signal.aborted) return { status: 'discarded' }
    const failure = cause instanceof Error ? cause : new Error(String(cause))
    error.value = failure
    return { status: 'failed', error: failure }
  } finally {
    if (mine === generation) loading.value = false
  }
}
function invalidate(): void {
  generation += 1
  controller?.abort()
  controller = null
  data.value = null
  error.value = null
  loading.value = false
}
~~~

Declare data/error with shallowRef, loading with ref, return readonly refs, and register invalidate using onScopeDispose only when getCurrentScope exists. Keep pure runner tests outside a component usable. No cache, polling loop or deep-watch-everything abstraction.

- [ ] **3. Define immutable query snapshots and context suspension.** types/query.ts defines TableQueryParams with context, ISO date range, page, itemsPerPage, search and a copied sort descriptor. Snapshot all nested objects explicitly. Watch context revision/transition synchronously to invalidate before a backend context mutation can finish. Only issue reads when isReady && !isTransitioning. A successful commit starts exactly one request for the current params.
- [ ] **4. Remove FX's boolean in-flight skip.** A changed EUR search/page/date always runs with the latest snapshot; abort superseded work. An identical init is prevented by the single watcher, not by dropping all requests. Add a mounted FX regression that changes search while the first promise is unresolved, resolves newer then older, and asserts EUR results remain visible.
- [ ] **5. Migrate PositionsPageBase and its parent adapters without leaking side effects.** OpenPositionsPage currently writes cash balances/portfolio totals inside fetchOpenPositions before the child can accept or discard the response; ClosedPositionsPage writes totals likewise. Make those fetch adapters pure. Return all rows/footer/cash values in one typed response; expose them through slots or an accepted-result event emitted only after acceptance. The parent must not update totals from an unguarded promise.
- [ ] **6. Migrate Transactions, database list pages, Summary and SecurityDetail loaders.** Each independently loadable resource gets its own runner. Preserve unrelated panels on a same-context error and show recoverable errors. A route security ID, selected account, period or pagination change belongs in the immutable params. Dispose pending work on route unmount. Keep transport request bodies unchanged except adding supported Axios signal options.
- [ ] **7. Verify mounted integration cases and all gates.** Run npm run test:unit -- useLatestRequest TableRequests PositionsPageBase PositionsPages; test FX and Transactions out-of-order fixtures through the browser harness; run complete unit/lint/type/build/browser and full pytest.

**Acceptance:** The two audited source reproductions pass as mounted component tests; changing a filter while loading cannot be lost; old data cannot change rows, cash totals, errors or loading; no query begins while backend context is transitioning. **Commit/PR:** codex/frontend-r5-latest-requests; fix: guard portfolio queries against obsolete responses. Commit runner/tests first and consumer batches next within the reviewed PR. **Rollback:** revert a consumer batch with its adapter changes; do not partially restore unguarded side effects or remove the generic runner while chart consumers depend on it.

## R6 — Make dashboard retry recover the actual content

**Outcome:** A successful retry removes the widget error and restores its content; independent widget loading remains independent.

**Consumes:** R3 context and R5 runner. **Produces:** Dashboard loader integration and recovery.mjs; no change to backend NAV error semantics in this PR.

- [x] **1. Extend the current retry tests past request-count assertions.**

~~~ts
// Synthetic display data; these are the current backend's dictionary keys.
const summaryFixture = {
  'Current NAV': '1,000.00', Invested: '900.00', 'Cash-out': '0.00',
  total_return: '11.11%', irr: 'N/R',
}
it('restores summary content after failure then successful retry', async () => {
  api.getDashboardSummary.mockRejectedValueOnce(new Error('Temporary failure'))
    .mockResolvedValueOnce(summaryFixture)
  const wrapper = mountDashboardWithRealStores()
  await flushPromises()
  expect(wrapper.find('[data-testid="summary-error"]').exists()).toBe(true)
  await wrapper.get('[data-testid="summary-retry"]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[data-testid="summary-error"]').exists()).toBe(false)
  expect(wrapper.find('[data-testid="summary-card"]').exists()).toBe(true)
  expect(wrapper.get('[data-testid="summary-card"]').text())
    .toContain(summaryFixture['Current NAV'])
})
~~~

mountDashboardWithRealStores is a local helper in DashboardPage.requests.spec.ts: install Pinia/Vuetify, configure the synthetic context backend and mock the four dashboard endpoints. The Current NAV/Invested/Cash-out/total_return/irr keys come from backend/dashboard/views.py:63-113; their amounts above are synthetic presentation inputs, not claimed calculated results. The generated DashboardSummaryResponse currently advertises a metrics envelope while this view returns the dictionary directly; R8 must characterize and type the actual response rather than wrapping data to satisfy a stale schema. Repeat the full recovery assertion for allocations, history and NAV. Run npm run test:unit -- DashboardPage.retry DashboardPage.requests; expect the current retained error to fail.

- [x] **2. Replace four independent ad hoc loaders with four runner instances.** Bind each widget's data/error/loading to its runner; remove retained error flags that can hide successful content. Starting retry clears that widget's error; accepted data clears it permanently; failure sets only that widget error. Do not rely on clearErrors(), which only clears the global snackbar.
- [x] **3. Preserve same-context chart presentation and explicit empty states.** Keep existing NAV data mounted during parameter updates and expose an updating overlay. A context invalidation removes the old context's result. Preserve the current history 404/no-data convention only for that documented endpoint; distinguish a request error from empty successful data. The chart/backend plan owns the separate HTTP-200 empty-on-error backend defect.
- [x] **4. Add the real-browser failure/recovery case.** recovery.mjs injects one failure, switches the fixture to success, clicks the actual Retry button and asserts visible content, absent inline error and no duplicate fetch burst. Verify each widget can recover while another remains failed.
- [x] **5. Run complete R1 gates and full pytest.** Chart migration work must preserve these tests, not replace them with wrapper-call counts.

**Acceptance:** The exact audited failed-summary → successful-HTTP-response → still-hidden-content case is fixed; rejected/aborted old attempts cannot reintroduce errors. **Commit/PR:** codex/frontend-r6-dashboard-recovery; fix: restore dashboard widgets after successful retries. **Rollback:** revert loader integration as a coherent batch; preserve any separately merged chart rendering changes.

## R7 — Reduce cold-route delivery cost

**Outcome:** Login/profile do not download the dashboard/chart/dialog graph, and the app no longer needs a complete icon font.

**Consumes:** Passing R1–R6 behavior gates and the master bundle budget. **Produces:** Lazy route boundaries, intentional Vuetify imports, used SVG icons and deterministic complete-route measurements.

- [ ] **1. Add a failing delivery assertion before editing imports.** Build the production app and record the complete cold dashboard JS/CSS request graph, including lazy descendants. Repeat for login and profile. scripts/measure-route-bundles.mjs reads the Vite manifest and the browser-observed resource set, computes gzip byte totals once per unique asset, and emits JSON.

~~~js
assert.equal(loginGraph.some(path => path.includes('dashboard')), false)
assert.equal(resources.some(path => /materialdesignicons.*\.(woff2?|ttf|eot)/.test(path)), false)
// Do not assert success from a smaller renamed entry chunk alone.
assert.ok(dashboardTotals.gzipJsCss > 0)
~~~

Use module membership from the manifest to identify dashboard/chart ownership; filename matching above is illustrative until explicit chunk labels exist. Record current cold-route ownership in delivery.mjs and assert absence of the owned modules on login/profile.

- [ ] **2. Convert ordinary route components to lazy imports, preserving routes/guards.**

~~~js
{
  path: '/transactions',
  name: 'Transactions',
  component: () => import('../views/TransactionsPage.vue'),
  meta: { requiresAuth: true },
}
~~~

Apply to every route view, including profile/database children. Do not add a second auth initializer or change redirects. Handle a failed lazy chunk load with a recoverable reload message, not an endless redirect loop.
- [ ] **3. Make expensive dialogs genuinely on demand.** Use defineAsyncComponent in the owning view and mount on first open. Preserve imports whose continuing WebSocket/SSE session must survive the visible dialog closing; create on first open, then retain until session completion/unmount. Do not unmount an active import merely to reduce initial bytes.
- [ ] **4. Remove blanket Vuetify registration after enumerating dynamic usages.** Keep vite-plugin-vuetify auto-import. Explicitly register only components/directives that are dynamically selected and cannot be discovered statically. Run all route/dialog smoke cases with real Vuetify and fail on unresolved components/directives.
- [ ] **5. Replace full-font MDI usage with an explicit SVG icon registry.** Add the supported released @mdi/js package at an exact verified version during implementation. plugins/icons.ts maps every existing icon name used statically or dynamically to an imported SVG path and uses Vuetify's SVG icon set; preserve the default Vuetify aliases required by built-in inputs. Unknown icon names throw in tests and use a visible fallback with logging in development. Remove @mdi/font and its CSS only when the registry inventory and browser route tests pass.
- [ ] **6. Gate development debug imports themselves.** Move authDebugConsole, authDebug and axiosDebug imports under import.meta.env.DEV dynamic loading; production must not register window.authDebug or download their code. Preserve deliberate development diagnostics without printing tokens in production.
- [ ] **7. Measure complete graphs and validate interactions.** Run production build, delivery measurement and route/dialog matrix on the same fixtures/runtime; compare desktop/mobile interaction and rendering. Engineering target: at least 25% lower combined cold dashboard JS+CSS gzip than the audit's approximately 535 kB, targeting at most 401 kB, and no MDI font request. A missed target requires an explicit measured tradeoff review; it is not a promised speedup. The later chart pilot must keep the entire dashboard dependency graph within the master's 535 kB budget or obtain a reviewed variance.
- [ ] **8. Run all R1 gates and full pytest.**

**Acceptance:** Existing routes/dialogs render correctly; imports remain operational; no font request or production debug bundle; dashboard modules stay off login/profile; before/after complete-route artifact is attached to the PR. **Commit/PR:** codex/frontend-r7-route-delivery; perf: split route delivery and use explicit UI imports. **Rollback:** route, Vuetify and icon subchanges are separate commits; revert the failing layer with its dependency/lockfile change, preserving verified behavior fixes.

## R8 — Establish typed transport without breaking callers

**Outcome:** New reliability modules have strict, testable transport contracts while existing imports from services/api.ts remain valid.

**Consumes:** R1 strict checking and the installed Axios client. **Produces:** The backend interface used by R3 and typed cancellable table methods used by R5; legacy exports remain compatibility wrappers.

- [ ] **1. Characterize actual endpoint response/request shapes.** Read current frontend/services/api.ts and the corresponding backend serializers/views without modifying backend files. Record representative synthetic fixtures for context, open/closed positions, transactions, FX and database tables. Preserve numbers already formatted for display; raw decimal values remain strings. Treat unknown/unavailable financial values distinctly from zero.
- [ ] **2. Add failing compatibility and cancellation tests.**

~~~ts
it('preserves the legacy open-positions request body and forwards cancellation', async () => {
  const controller = new AbortController()
  await api.getOpenPositions(null, '2025-12-31', 1, 25, '', {},
    { signal: controller.signal })
  expect(http.post).toHaveBeenCalledWith(
    '/open_positions/api/get_open_positions_table/',
    { dateFrom: null, dateTo: '2025-12-31', page: 1,
      itemsPerPage: 25, search: '', sortBy: {} },
    expect.objectContaining({ signal: controller.signal }),
  )
})
it('rejects malformed table rows instead of presenting an empty portfolio', () => {
  expect(() => decodeOpenPositions({ total_items: 1 })).toThrow(
    'Invalid open positions response',
  )
})
~~~

The first snippet uses the current property spellings in api.ts:343-348; preserve them. Add tests that importing a new typed module does not instantiate Pinia/router and that old exports still resolve. Run npm run test:unit -- apiContracts apiCompatibility; expected failure is absent optional signal/decoder behavior.

- [ ] **3. Introduce a narrow injected HTTP client and error envelope.**

~~~ts
import type { AxiosInstance } from 'axios'
export interface RequestOptions { signal?: AbortSignal }
let installedClient: AxiosInstance | null = null
export function configureApiTransport(client: AxiosInstance): void {
  installedClient = client
}
export function getApiTransport(): AxiosInstance {
  if (!installedClient) throw new Error('API transport is not initialized')
  return installedClient
}
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly code?: string,
    readonly details?: unknown,
  ) { super(message); this.name = 'ApiError' }
}
~~~

Configure the existing axiosInstance in main.js before router installation. This module imports Axios types only; it does not import legacy axiosConfig, stores or router, preventing the strict dependency graph from pulling the legacy cycle into itself. Normalize unknown thrown strings/objects at the typed transport boundary and never attach auth headers/tokens to user-visible error details.

- [ ] **4. Define the context backend dependency explicitly.**

~~~ts
export type ContextValues = Omit<PortfolioContext, 'revision'>
export interface PortfolioContextBackend {
  read(): Promise<ContextValues>
  updateAccount(selection: AccountSelection): Promise<void>
  updateSettings(settings: {
    effectiveCurrentDate: string; currency: string; digits: number
  }): Promise<void>
}
export function configurePortfolioContextBackend(
  backend: PortfolioContextBackend
): void
export function getPortfolioContextBackend(): PortfolioContextBackend
~~~

services/api/context.ts implements the backend using the typed HTTP client. Map existing settings field names (table_date, default_currency, digits) explicitly; parse server-confirmed responses, finish effective-date refresh through the injected shared auth coordinator, then read canonical state. Inject the refresh coordinator from main.js so the strict context module does not import legacy Axios/store modules. The singleton getter throws before configuration; tests configure a new fake per test and reset it during teardown. R3's store consumes this exact backend interface.
- [ ] **5. Extract only the exercised domain methods.** Move cancellable portfolio/table/transaction/database reads into the listed domain modules; keep their old API signatures and add a final optional RequestOptions argument. api.ts re-exports them. Keep unexercised mutation/import/session code in the compatibility module until its dedicated refactor; no wholesale rewriting. Decoders validate required containers/fields and counts, preserve optional fields, and reject structurally invalid successful responses with a descriptive ApiError.
- [ ] **6. Type display and raw values deliberately.** portfolioTables.ts distinguishes raw decimal strings, already-formatted display strings, null/unavailable markers and integer record counts. Do not use parseFloat or arithmetic to reconstruct authoritative financial values. Add precise interfaces for rows/totals actually consumed by R5. Do not cast a number[] year list through unknown into objects; adapt to the correct {text,value} shape or consume numbers consistently.
- [ ] **7. Keep generated schema types reproducible.** Make generation runnable from the documented environment without assuming /tmp or a Unix shell; use a Node script or platform-neutral temporary path while invoking uv from backend/. Check generated changes for drift in a dedicated command; do not regenerate every PR from a live database or pretend function-based endpoints are described when they are not.
- [ ] **8. Run API compatibility tests, both strict/global type checks, all R1 gates and full pytest.** Confirm no request payload/response semantics changed and api.ts compatibility imports still build.

**Acceptance:** R3/R5 can import typed modules without router/store side effects; existing callers compile and retain endpoint bodies; cancellation reaches Axios; malformed payloads produce recoverable errors rather than false empty data. **Commit/PR:** codex/frontend-r8-typed-transport; refactor: add typed cancellable API boundaries. **Rollback:** revert an extracted domain with its api.ts wrapper and tests; retain exported names for already-merged consumers. No backend schema or financial formula changes.

## Common execution and review record

Each PR runs focused failing tests first, records the expected failure, implements the bounded change, then runs:

~~~text
# Working directory: frontend/
node --version
npm run test:unit
npm run lint
npm run type-check
npm run type-check:reliability
npm run build
npm run test:browser

# Working directory: backend/
uv run python -m pytest
~~~

Attach actual command exits, complete test counts, browser fixture completeness, screenshots/geometry where applicable, before/after request traces, and any measured delivery delta. Report environmental or pre-existing failures separately; a required failing gate leaves the PR unready unless a human explicitly approves the documented exception.

Use the project's commit body fields: What changed; Why; Numerical impact / example; Tests added; Reviewer(s). For presentation/context changes, describe which existing financial results are selected/displayed and explicitly state that formulas are unchanged. Keep rollback to coherent reviewed commits. Do not merge or deploy automatically.

## Plan self-review checklist

- [ ] R1 covers local runtime/storage initialization, complete CI scope, Vue/TS lint and strict new modules.
- [ ] R2 verifies real geometry rather than absence of a CSS string.
- [ ] R3 retains broker/group/all/account variants and commits date/currency/digits atomically, including session refresh.
- [ ] R4 reproduces effective-date changes without navigation and avoids duplicate fetch triggers.
- [ ] R5 rejects obsolete responses for all dependent side effects and never drops FX parameter changes.
- [x] R6 verifies content recovery after success, not only that Retry invokes the API.
- [ ] R7 measures complete cold-route dependency graphs and protects active import sessions during lazy mounting.
- [ ] R8 preserves api.ts exports, request bodies, raw financial value semantics and an acyclic strict boundary.
- [ ] The master/design/chart plans use these exact shared interfaces; conflicting file edits are sequenced through the master.
- [ ] All PRs retain the complete pytest gate and human review; no production action is implied by this planning document.
