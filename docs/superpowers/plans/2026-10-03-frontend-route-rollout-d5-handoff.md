# D5 — visual system across route families

> Executor: use the executing-plans workflow. Complete only D5, in family-sized commits; publish one draft PR and stop for review.

## Goal and accepted design

Apply the reviewed workspace hierarchy, table controls and form patterns to every existing route family. Preserve every financial value, workflow and URL. This implements task 19 of the [master plan](2026-09-08-frontend-modernization.md), specifically [D5 in the accepted design/workflow plan](2026-09-08-frontend-design-workflows.md#d5-roll-the-reviewed-system-across-every-existing-route-family). Read the [progress tracker](2026-09-30-frontend-modernization-progress.md) and [reviewed workspace evidence](../../design/frontend-workspace.md) first.

Verified starting checkpoint: PR #53/C3 merged on 3 October 2026 at `2e77e5c7edc9d485c37d3437e58857e6d938ad95`; final proposal head `3cd33c06`. Fetch the latest `origin/codex/frontend-modernization`, including these handoff documents, and create `codex/frontend-route-rollout-d5` from it. Record the actual base SHA. Do not reset someone else's work or reuse the merged C3 branch.

Architecture: compose existing Vue/Vuetify pages with D1/D4 workspace components. Existing controllers, API functions, request lifecycle, settings owners and dialog events remain authoritative. No universal schema-driven page builder. Stack: Vue 3, Vuetify 3, Pinia, existing TypeScript/JavaScript boundary, Vitest and agent-browser. Use the Node version required by `frontend/package.json` (currently >=24.20.0 <25).

## Scope and non-negotiable boundaries

- Read `AGENTS.md`, `.memory-bank/index.md` and `.memory-bank/Rules for AI Coding Agent.md`. No backend, financial calculation, API/schema or numeric rounding changes. If a protected change proves necessary, document it separately rather than folding it into D5.
- The account-selector `[object Object]` defect is being fixed separately, per the user. Do not duplicate that fix or cherry-pick an unmerged proposal. Preserve it if it lands upstream; report any remaining dependency honestly. D5 work on other routes can proceed independently.
- C3 stays default-off. Preserve both renderer paths, exact display strings, both IRRs, tooltip visibility, request ownership and delivery budgets. Three solid allocation pies/security history migration are C4, cutover/removal is C5. D6 import orchestration and D7 broker/security internals remain separate.
- Keep all existing routes, IDs, auth guards, dialog `modelValue`/completion events and caller invalidation. Keep development-only debug tools out of production. Do not perform real deletes/imports, use production data, merge, deploy or start another workstream.
- Use semantic tokens and existing components. Numeric cells are right-aligned; preserve server/formatted strings, comma thousands separators, sign conventions, precision and missing-value markers. Never parse/recalculate money to restyle it.
- Existing D4 position views and transaction ownership safeguards are already accepted. Integrate their appearance; do not implement replacement table models or weaken their tests.

## Source map and interfaces

- Shared: `frontend/src/components/workspace/{WorkspacePage,WorkspaceSection,WorkspaceActions,WorkspaceTableToolbar,WorkspaceEmptyState,ConfirmActionDialog}.vue`, `types.ts`; `frontend/src/theme/defaults.ts`; `frontend/src/assets/workspace.css`; `frontend/src/main.js`.
- Route/heading ownership: `frontend/src/router/index.js`, `frontend/src/App.vue`. `WorkspacePage` owns its heading and registers with the shell. Nested database/profile layouts must not introduce duplicate route headings or nested page wrappers.
- Performance: `frontend/src/views/SummaryPage.vue`. Preserve `performanceQuery`, `breakdownQuery`, `yearsQuery`, public/restricted account groups, subtotals and total. Its account-performance periods and portfolio-breakdown year selector are distinct controls.
- Already migrated: `frontend/src/views/{DashboardPage,OpenPositionsPage,ClosedPositionsPage,TransactionsPage}.vue` and their existing components/tests. Change only what D5 integration requires.
- Data: `frontend/src/views/DatabasePage.vue`, `frontend/src/views/database/{BrokersPage,AccountsPage,SecuritiesPage,PricesPage,FXPage,SecurityDetailPage}.vue`.
- Profile/auth: `frontend/src/views/profile/{ProfileLayout,ProfilePage,ProfileEdit,ProfileSettings}.vue`, `frontend/src/views/{LoginPage,RegisterPage}.vue`, `frontend/src/components/{LoginForm,RegisterForm,AccountGroupManager}.vue`.
- Forms: `frontend/src/components/dialogs/{AccountFormDialog,BrokerFormDialog,SecurityFormDialog,PriceFormDialog,FXDialog,PriceImportDialog,FXImportDialog,AssetTransferDialog,MergerDialog,UpdateAccountPerformanceDialog}.vue`. Presentation only; preserve each actual public interface. Shared destructive UI must retain special confirmation inputs, including the profile's typed DELETE requirement; extend an explicit slot only if needed, without weakening constraints.
- Verification: `frontend/tests/unit/workspace/RoutePatterns.spec.ts` (new; split by route family if clearer), existing component/request/auth suites, `frontend/tests/browser/{routes.mjs,run-smoke.mjs}` and the existing fixture/case helpers. Add a focused `d5` browser case using current harness conventions.
- Evidence: create `docs/design/frontend-route-review.md`; place new synthetic captures under `docs/design/assets/frontend-workspace/` with distinct `d5-` names. Update the durable tracker, not historical claims in other handoffs.

## Review risks and required evidence

| Risk | Regression / acceptance |
|---|---|
| Compact Performance view silently drops history or changes numbers | Every returned period and all eight metrics reachable; groups/subtotals/total unchanged; exact strings and independent breakdown-year requests asserted |
| Shared controls change API payloads, order or deletion identity | Characterize existing events and request parameters; verify original handlers, exact subject, rejected outcomes and async ownership where touched |
| Global defaults break accepted pages/overlays | Apply defaults last; rerun D3/D4/C3, resize transitions, hit-testing and native 200% zoom |
| Route wrapper or form migration breaks keyboard/auth behavior | One route heading, named controls, error/focus behavior, original links/redirects, development-only debug route |
| Green evidence comes from unrealistic fixtures or uncommitted fixes | Fixtures match actual serializer shapes; fail unmatched requests; record committed head and process exit codes; actual route/state captures |

## Task 0 — baseline and coverage ledger

- [ ] Read the source map and accepted D5 section. Inventory each route's actions, columns, filters, dialogs, events and settings owner before editing. Record these contracts in `frontend-route-review.md`.
- [ ] Establish baseline gates below on the clean starting commit. C3 previously repaired `requests`/`dates`; do not carry their old failure waiver forward. Historical references: full frontend 538 tests before the final C3 tooltip rounds; final focused chart suite 174; lint 0 errors/35 warnings; backend 1386 passed/10 skipped. These are references, not substitutes for current results.
- [ ] Create the route/state evidence ledger and focused D5 harness skeleton. Use synthetic, backend-faithful fixtures; record unsupported states as N/A with a reason (e.g. filtered-empty on login), never as passed.
- [ ] Commit the baseline/contract ledger independently. No production code change in this task.

## Task 1 — Performance and accepted table parity

- [ ] Write failing behavior tests for `/summary`: single-period default, explicit comparison and full-history modes, all groups/metrics/periods retained, independent year filter, reactive currency labels, exact strings including `10,000`, and empty/error recovery. Introduce a small pure display projection only if it makes period selection testable; it must not calculate values.
- [ ] Provide a clearly labelled account-performance period control. Default to returned `YTD` if available, otherwise latest returned calendar year, otherwise the first available server period. Preserve server ordering and keys; don't relabel YTD as an indistinguishable full year. Comparison allows choosing multiple returned periods; full history shows all. Keep view selection stable during resize. Disable unavailable controls for empty data.
- [ ] Retain all eight existing leaves: BoP NAV, Cash-in/(out), Return, FX, TSR, EoP NAV, Commissions, Fee per AuM. Single-period mode uses flat qualified labels; comparison/history use accessible grouping and table-local scroll. Do not add the deferred metrics-as-rows design.
- [ ] Apply WorkspacePage/Section/toolbar patterns and reactive units to the existing breakdown table. Changing the first table's view is presentation-only and makes no additional request; the existing breakdown-year filter retains its own request behavior.
- [ ] Check Open/Closed Positions and Transactions against D4, making only necessary token/layout integration changes. Preserve 20/16 leaves, presets/custom persistence, server-owned order, hidden-sort notice, sticky identity and cash/TOTAL semantics; preserve all transaction actions and DELETE/focus ownership safeguards.
- [ ] Run focused tests and actual populated/empty/filtered-empty/error route checks; record desktop/mobile evidence before committing this family.

## Task 2 — Data inventory and metadata forms

- [ ] Write failing route/control regressions for Data landing links, broker/account/security action mapping, filtering, original detail URLs and dialog completion invalidation. Verify actual component controls rather than blanket stubs that erase names/events.
- [ ] Migrate Data navigation/landing, Brokers, Accounts and Securities with concise headings, primary create actions, shared search/table controls, quiet identity-first rows and clear form sections. Preserve broker connections, account currencies/groups/totals/deletion constraints, security identifiers/types/bond/crypto fields and sharing/mapping.
- [ ] Apply the shared page/context shell to SecurityDetail only. Preserve account scope and price/position/activity access; do not extract internals or replace charts.
- [ ] Reuse ConfirmActionDialog for applicable confirmations while leaving parent handlers authoritative. Preserve special requirements and exact subject identity; add delayed/rejected/closed/session-change tests if lifecycle wiring changes. Never make an irreversible action easier by removing a confirmation constraint.
- [ ] Finish column visibility persistence only where missing, using each table's current owner and table/user identity. Reject removed keys and invalid/empty preferences to analyst defaults, keeping all fields reachable; never share one global list.
- [ ] Verify each route's four applicable states, keyboard actions, representative form and link navigation; commit the family with evidence.

## Task 3 — Prices, FX and operational dialogs

- [ ] Write failing tests for price security/date/source controls and unit labels, FX pair/orientation labels, existing import/transfer/merger/performance entrypoint events and rejected-form preservation.
- [ ] Migrate Prices and FX to shared layout and named table-local scrolling. Keep price precision, bond percentage-of-par and FX orientation/values unchanged. Reuse existing import handlers and protocol.
- [ ] Bring the listed operational dialogs into the reviewed form layout: visible section labels, readable errors, mobile single column, named actions, focus entry/return and cancellation. Preserve validation, payloads and completion events. Do not extract import orchestration (D6) or broker/security internals (D7).
- [ ] Exercise slow loading, rejected save, cancel/reopen and successful fixture completion; verify the owning caller invalidates exactly as before. Record route-state/form evidence and commit.

## Task 4 — Profile and authentication

- [ ] Write failing tests for profile navigation/settings sections, original settings payloads and context-affecting save behavior; login/register labels, errors, password autocomplete and redirect behavior; profile deletion's typed confirmation remains required.
- [ ] Compose profile identity, display defaults, account defaults and broker connections with shared hierarchy. Preserve group management and existing settings choices. Nested layout supplies navigation while the active page owns one heading.
- [ ] Restyle login/register as narrow surfaces with one primary submit, visible field labels and error summary. Keep auth/session/redirect logic unchanged. Keep debug-auth development-only; verify production navigation never exposes it.
- [ ] Verify real links, keyboard traversal, representative rejected form and mobile behavior; commit this family with evidence.

## Task 5 — app-wide defaults and cross-route acceptance

- [ ] Only after the families pass, apply reviewed `workspaceDefaults` through Vuetify configuration in `frontend/src/main.js`; update its formerly pilot-only comment. Retain targeted density overrides and scoped layout rules. Avoid copying all workspace CSS globally without checking scope.
- [ ] Replace remaining inconsistent literal colors, uppercase group noise and gratuitous percentage italics in migrated surfaces with tokens/standard classes. Do not make unrelated cleanup commits or reformat untouched code.
- [ ] Verify the 18-route/four-profile matrix in `routes.mjs`, the new `d5` cases, and retained focused cases. Check both resize directions, actual control hit targets and overlay visibility below the fixed header. At native 200% zoom verify DPR, actions and form errors remain reachable, then reset zoom. The harness's reflow profile alone does not prove native zoom.
- [ ] Rerun D3/D4 and both C3 flag states after global defaults: tooltips at partial scroll positions, both IRRs, legend/table/viewport controls, exact strings and flag-off lazy delivery remain intact. Do not raise delivery budgets to pass.
- [ ] Capture each route family from its own rendered build. Keep historical accepted screenshots unchanged unless a deliberate comparable update is documented. Use viewport-only capture for open tooltips; a full-page capture can change layout and dismiss them.

## Task 6 — final committed-head gates and draft review

Run from `frontend/`, capturing each process's real exit code (PowerShell: `$LASTEXITCODE` immediately after each native command; no output pipe masking it):

```text
npm run test:unit
npm run type-check
npm run type-check:reliability
npm run type-check:charts
npm run lint
npm run api:types:check
npm run build
npm run test:browser
npm run test:browser -- --case d5
npm run test:delivery
```

Also run retained focused browser cases `layout`, `context`, `dates`, `requests`, `recovery`, `dialogs`, `dialog-recovery`, `d4`, `charts-c2`, `charts-c3`, using the existing harness's build/flag handling. Retain `tests/unit/components/PositionsPages.spec.js`, `TransactionDescription.crypto.spec.js` and `tests/unit/utils/formatUtils.spec.js` within the full unit gate. From `backend/`, run `uv run python -m pytest` with `DJANGO_SETTINGS_MODULE=portfolio_management.test_settings` as in earlier handoffs. Do not weaken lint baselines/checkers or test assertions; remove only demonstrably stale fingerprints for diagnostics actually fixed.

- [ ] Before final verification, commit implementation and record SHA; verify no uncommitted source fixes or stash-dependent state. Record failures/retries honestly. An evidence-only commit afterward must identify the tested implementation SHA. Rerun affected gates if code changes afterward.
- [ ] Evidence ledger must list route, state, viewport, tested SHA, screenshot, behavior checks, result and limitations. Distinguish real assistive-technology testing from DOM/keyboard checks. Real screen-reader audit remains D8 if not performed; provide a short human visual-review checklist and any blockers, not a fabricated accessibility pass.
- [ ] Update tracker task19 to implemented/pending review, with actual gate exits and PR link. Do not mark integrated or modernization complete. Clean up only owned browser sessions and servers.
- [ ] Push `codex/frontend-route-rollout-d5`; open one **draft** PR into `codex/frontend-modernization`. Describe route coverage, unchanged contracts, evidence, deviations and remaining acceptance. Stop for review; no merge/deployment/D6/D7/C4/C5 work.
