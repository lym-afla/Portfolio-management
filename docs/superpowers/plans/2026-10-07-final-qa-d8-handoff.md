# D8 integrated frontend QA implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Track checkboxes and commit each verified task.

**Goal:** Verify the integrated default-on frontend across every route and critical workflow, fix bounded defects, and deliver an honest reviewable acceptance record.

**Architecture:** Preserve the merged application and its R/D/C ownership boundaries. Extend the existing synthetic browser harness to audit a genuinely unflagged default-on build across the full route matrix, retaining explicit rollback coverage separately. D8 supplies release-candidate evidence; it does not authorize deployment or satisfy C5b removal approval by itself.

**Tech stack:** Existing Vue/Vuetify/Vite/TypeScript, ECharts with lazy Chart.js fallback, agent-browser, Vitest; Node >=24.20.0 <25; backend uv/pytest.

**Spec:** [D8 design-workflow requirements](2026-09-08-frontend-design-workflows.md), [master plan](2026-09-08-frontend-modernization.md), [current tracker](2026-09-30-frontend-modernization-progress.md), [C5a handoff](2026-10-07-chart-cutover-c5-handoff.md).

## Starting point and global constraints

- PR #60 merged at `9d369af7`, reviewed implementation `6c701ec0`. Pull the latest `origin/codex/frontend-modernization`, including this handoff. Create `codex/frontend-final-qa-d8` in a dedicated worktree; leave other checkouts alone.
- Read AGENTS.md and `.memory-bank/index.md`, its coding rules and authoritative NAV/calculation/FX documents. Read the accepted audit plus current D3–D7 and C3–C5 evidence.
- The three ECharts families now default on when their build flags are absent. Exact false is rollback. Chart.js remains a lazy compatibility fallback. No dependency removal, backend/financial/API changes, new product features, main merge, deployment or release tag in this assignment.
- Exact server displays, comma separators, signs, units, precision, missing/partial statuses and both IRR horizons remain unchanged. Child presentation components must not acquire request ownership.
- Dedicated screen-reader/AT work remains excluded. Retain keyboard/focus, labels, contrast, semantics, exact tables, mobile behavior and native 200% zoom. Light theme only; no dark-mode rollout, localization, exports or new shortcuts.
- Current evidence reference: executor 1003 units; lint 0 errors/8 warnings; backend 1386 passed/10 skipped; root independently passed 29 loader/policy/fallback tests. These are historical results, not a baseline rerun or a required test count.
- C5b still requires an owner-accepted release validation cycle and separate removal approval. D8 can run before that cleanup because the integrated dual-renderer candidate is ready for QA. A later removal change must rerun affected acceptance checks.

## Review focus

1. Modern default versus rollback artifact confusion: identify actual flag values, build output and loaded graph for every run (task 0).
2. Dense/long/signed content at small widths: control hit-testing and contained text, not only page scrollWidth (task 1).
3. Async dialog, import, broker and context changes: late results never mutate a replacement workflow or leak credentials (task 2).
4. Chart fallback failure/retry and zoom across real refresh/context changes: no duplicate requests, stale values or lost user choice (task 2).
5. Evidence drift: capture actual tested committed code, inspect pixels and retain failures/limitations rather than declaring blanket completion (task 3).

## File map

- Create `docs/design/frontend-final-qa.md`: route/state/viewport ledger, defect dispositions, gate results, release-review checklist and remaining boundaries.
- Update `docs/design/frontend-route-review.md` and `frontend-workspace.md` to link current acceptance and describe implemented conventions; retain historical records as historical.
- Create `docs/design/assets/frontend-final-qa/` for new synthetic captures; do not rewrite earlier workstreams' captures incidentally.
- Extend `frontend/tests/browser/run-smoke.mjs` and its existing fixtures/flows; create `frontend/tests/browser/final-qa-d8.mjs` if a separate orchestrator is needed. Reuse lifecycle/measurement helpers rather than duplicating them.
- Bounded application fixes belong in the existing owning components/composables and their focused tests. Record every fix separately; do not turn QA into a broad refactor.
- Update `.memory-bank/Tech details/frontend.md`, `.memory-bank/index.md`, master-plan current status pointer and the durable tracker. Do not edit personal Codex memories.

## Task 0 — Establish the actual default-on audit artifact

- [ ] Record clean base SHA, supported runtime/browser versions and installed lockfile dependencies in the dedicated worktree. Enumerate the real router and existing 18-route fixture inventory; explain any route/redirect exclusions instead of assuming coverage from a count.
- [ ] Build a dedicated artifact with all three `VITE_*_ECHARTS_ENABLED` keys genuinely absent. Check effective values including any Vite env files, not only process.env; restore the environment after each build. Record artifact path/hash and flags in evidence.
- [ ] Extend the full route/profile runner to explicitly target this artifact. `run-smoke.mjs` currently builds its standard artifact with all three flags false: that remains useful rollback evidence but does NOT prove default-on all-page acceptance. Keep those assertions; add a distinct default-on matrix and unambiguous result labels.
- [ ] Add a meaningful harness regression proving artifact selection/defaults and env restoration, including a build failure path. Confirm default dashboard/security load modern renderers; login/profile/transactions load no chart runtime. No forced false flags hidden in the D8 path.
- [ ] Run baseline smoke and existing recovery/dialog-recovery on their intended artifacts. Reproduce any failure directly before assigning an environment label. Commit harness changes separately from UI fixes.

## Task 1 — All-route visual and keyboard audit

- [ ] Cover every route at 1440x1000, 1024x768, 390x844 and 768x1024 on the unflagged artifact. Cover populated, empty, filtered-empty and error/retry states where applicable. Put justified N/A entries in the ledger for inapplicable states.
- [ ] Use realistic synthetic long account/security/broker names, multiple currencies, signed values, missing prices and dense tables. For each row record Route, Fixture/account, Viewport, State, Keyboard/focus, Context/data match, Screenshot, Result and Remaining issue.
- [ ] Check one clear heading, action hierarchy, wrapped descriptions, navigation reachability, full selected-account labels (including underlying inputs), no object-string leaks, responsive app-bar clearance, readable labels and measured contrast. Check actual control bounds and elementFromPoint after scrolling below fixed headers; no force clicks to bypass covered controls.
- [ ] Verify open/closed position Overview, comparison, Full ledger and Custom views: all fields reachable, grouped headers and totals aligned, key-based sticky identity, horizontal scrolling confined to tables, server sorting preserved, preferences scoped to user/table and unaffected by resize.
- [ ] Verify Performance's eight metrics/groups/totals and independent filters; data-family paging/search/actions; Prices/FX labels/orientation; settings unavailable-account preservation and guarded saves; auth errors. Preserve exact display strings and numerical meaning.
- [ ] Use real keyboard Tab/Shift+Tab/Enter/Space/Escape paths, visible focus and dialog focus return. Exercise desktop-to-mobile-to-desktop transitions. Verify native 200% zoom with actual DPR change, then reset; CSS viewport simulation alone is insufficient.
- [ ] For a real defect, write the smallest behavior regression, observe RED, fix within the owning UI boundary, rerun the affected audit rows and commit. Do not add source-mirroring snapshots or hide overflow to make checks pass. Report protected/out-of-scope defects separately.

## Task 2 — Integrated workflow and chart acceptance

- [ ] Run transaction create/edit/rejected save/delete flows, delayed details, cancel/reopen and session change. Confirm correct subject/endpoint, duplicate-submit prevention, edits retained on rejection and current-generation focus only.
- [ ] Run import configuration, mapping/create-security, confirmation, Stop pending/ack, warnings/recoverable row errors and uncertain terminal errors through synthetic loopback WebSockets. Check no stale completion or automatic restart after close/unmount/reopen. Keep exact legacy command parity including date_to.
- [ ] Run broker form failure/cancel/reopen/reactivation/delete retry and replacement confirmations with fake credentials only. Inspect visible messages and recorded artifacts for secret leakage. Never contact live broker services or persist test credentials.
- [ ] On the unflagged build, verify NAV and its two IRRs plus all three solid pies and both security histories; stock/bond/crypto, duplicate-date events, exact tables, status/reason/subtotal, pie ineligibility, immutable denominators and annotated carry-forward. Reuse C3/C4/C5 cases and independently inspect their current rendered output.
- [ ] Test actual compatible refresh (request observed and response accepted) with both zoom bounds retained; incompatible context/security change and logout reset state. Park each history response independently and inspect loading. Test malformed-v2/error without downgrade, genuine legacy-only, renderer failure, user-chosen fallback, failed fallback chunk and successful retry, preserving choice and zero extra financial requests.
- [ ] Check tooltip pointer behavior as well as deterministic geometry probes at both edges and partially scrolled positions. Verify viewport containment AND freedom from fixed-header occlusion at mobile/native zoom. Document any synthetic hooks; no public test route or production auth bypass.
- [ ] Repeat explicit all-off and per-family rollback checks separately from the default-on matrix. C5a's saved delivery result is 483,948 dashboard gzip bytes versus approximately 535 kB target; remeasure current cold JS+CSS graphs and timing for login/profile/transactions/dashboard/security. Account for fonts/exclusions and all fetched modules; do not raise budgets silently or claim loopback timing is production timing.

## Task 3 — Evidence, gates and review package

- [ ] Capture new synthetic screenshots for representative dense routes, grouped tables, each workflow family, all modern charts, mobile tooltip and native zoom. Inspect actual images for clipping, occlusion, stale data and misleading capture state. Include capture SHA/flags/viewport/fixture; hashes alone are not visual inspection.
- [ ] Record implemented financial workspace conventions in `frontend-workspace.md`: visible committed context with pending changes separate; accepted server display values with exact semantics; heading/context/primary action/sections; grouped tables and sticky identity; equivalent chart tables; R owns context/requests, D presentation, C chart boundaries. Link exact current code paths.
- [ ] Once changes stabilize, commit implementation then run gates sequentially with actual process exit codes: `npm run test:unit`, `type-check`, `type-check:reliability`, `type-check:charts`, `api:types:check`, `lint`, `build`, full `test:browser`, the new default-on full route matrix, `test:delivery`, and focused cases `charts-c2`, `charts-c3`, `charts-c4`, `charts-c5`, `brokers-security-d7`, `imports-d6`, `layout`, `context`, `dates`, `requests`, `recovery`, `dialogs`, `dialog-recovery`, `d4`, `d5`, `settings-account`. Record the exact command for the new matrix in evidence.
- [ ] Run `uv run python -m pytest` from backend with test settings/coverage intact. Do not silently omit it for a presentation-only diff. Later changes require affected checks again; distinguish final tested implementation from docs-only commits.
- [ ] Review final diff for unauthorized backend/arithmetic/API changes, formatted-value drift, duplicate request owners, credential persistence, unscoped styles and weakened tests/budgets. Remove only owned scratch artifacts and close owned browser/server sessions.
- [ ] Update tracker as D8 implemented/pending review only if every applicable row passes; otherwise enumerate blockers. Provide a short owner review checklist with specific captures and workflows, separating local synthetic evidence from any unperformed real release cycle. Do not label modernization complete or C5b approved.
- [ ] Push `codex/frontend-final-qa-d8` and open one draft PR into `codex/frontend-modernization`; include baseline/tested head, defect list, gate results, default-on versus rollback matrix, delivery, visual evidence and unresolved release decisions. Stop for review. No merge/deploy/dependency removal.

## Completion boundary

D8 is accepted only after review of the actual rendered evidence and integrated behavior. C5b and eventual main/release decisions remain separate. This assignment prepares all useful local QA without claiming a live release validation cycle occurred. After any later Chart.js cleanup, rerun affected default/fallback/release checks and update the record before final release approval.
