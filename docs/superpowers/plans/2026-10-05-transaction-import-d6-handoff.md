# D6 transaction import extraction implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` task-by-task, with characterization tests before extraction. Use a dedicated worktree; never switch or reset another executor's checkout.

**Goal:** Make the transaction import workflow understandable and testable while preserving its existing wire protocol, decisions, results and public events.

**Architecture:** Evolve `useImportState` into the single discriminated state owner. A typed legacy-protocol boundary and `useTransactionImport` orchestrator compose the existing analyzer, lookups and WebSocket transport. Small step components render state and emit intents; `TransactionImportDialog` remains the compatible entrypoint.

**Tech Stack:** Vue 3, Vuetify 3, Pinia, TypeScript, Vitest, agent-browser; Node >=24.20.0 <25 and backend uv project mode.

**Spec:** [Accepted D6 design and interfaces](2026-09-08-frontend-design-workflows.md#d6-extract-the-transaction-import-workflow-into-typed-testable-units), [master plan](2026-09-08-frontend-modernization.md), [progress tracker](2026-09-30-frontend-modernization-progress.md). The accepted D6 section contains the command union, state union, transport interface and start-command examples; read the entire section, not only this handoff.

## Base and scope

PR #56 is merged at `7248a02006a8618cca31918a25a9a23f81c4c5bf`; final proposal head `b5fc13d0`. Fetch latest `origin/codex/frontend-modernization`, including this handoff, then create `codex/transaction-import-d6` in an isolated worktree. Record actual base SHA and working directory. D5 and supplementary PRs #54/#55 are integrated; preserve their responsive layout, focus and settings guards. D6 is task20; five master-plan tasks remain including D6.

## Global constraints

- Read `AGENTS.md`, `.memory-bank/index.md`, `.memory-bank/Rules for AI Coding Agent.md` and applicable financial/import documentation. No backend/protected import logic, financial formula, rounding, schema or authorization change. Read backend producers to establish the existing wire contract; do not modify them to accommodate new types.
- Keep public props `{ modelValue: boolean }`, emits `update:modelValue` and `import-completed`, and the original completion payload supplied to the parent. Parent invalidation remains unchanged and occurs once for an accepted completion.
- Preserve commands byte-for-byte in field names, nesting, null/optional semantics and values for equivalent inputs. API start uses `confirm_every_transaction` and `date_from`; file start uses `confirm_every`. Do not add `date_to` to API start just because configuration displays it. Account-selection dates are a separate existing command contract.
- Preserve money/quantity/date/display strings without Number conversion. UI progress counters may be integers. Retain provider-specific account-match objects; do not reconstruct them from IDs and discard fields.
- Use the existing `useWebSocket('/ws/transactions/')` and `analyzeFile`. Adapt `connect()` with `Boolean(await connect())`; no second socket or reconnect policy, no automatic replay of starts/decisions after reconnect.
- Synthetic loopback fixtures only. Never import into a real account or use real broker credentials. Do not persist files, credentials, tokens or raw sensitive protocol messages in Pinia/localStorage/logs/screenshots. Existing unrelated transport issues should be recorded separately unless they prevent the bounded fix.
- ECharts stays default-off. No D7, C4 pies/security charts, C5 cutover, main merge or deployment. Do not redesign unrelated operational dialogs.

## Source map and interfaces

- Existing entrypoint: `frontend/src/components/dialogs/TransactionImportDialog.vue` (currently a large mixed orchestration/view component). Inventory both message-dispatch paths and all send sites before moving code.
- State owner: `frontend/src/composables/useImportState.ts`; update existing callers rather than creating a second state ref. Legacy `isIdle/isAnalyzing/isImporting/isMapping/isComplete/isError` must be computed projections while needed.
- Create `frontend/src/features/imports/types.ts`, `legacyImportProtocol.ts`, `useTransactionImport.ts`, `ImportMethodStep.vue`, `ImportSourceStep.vue`, `ImportReviewStep.vue`, `ImportResult.vue` as specified in the accepted plan.
- Reuse `frontend/src/composables/useWebSocket.ts`, existing API analyzer/lookups, `frontend/src/components/TransactionImportProgress.vue` and existing `SecurityMappingDialog`, `SecurityFormDialog`, `AccountMatchingDialog`, `ProgressDialog` under `components/dialogs/`.
- Protocol: typed `ImportCommand`/`ImportTransport`, `FileStartInput`, `ApiStartInput`, `AccountMatchPair`, `ImportResultData`, `TransactionImportState` from the accepted D6 section. Incoming boundary accepts `unknown`; decoder returns a discriminated validated event or a safe protocol error. Validate only required structure, preserving legitimate optional/provider data. Enumerate every actual backend message before deciding a message is unknown.
- Orchestrator exposes `selectMethod`, `back`, `analyze`, `startFile`, `startApi`, `requestStop`, `receive`, `reset`, plus typed decision methods for account matching/selection/creation, security mapping/creation/skip and transaction confirm/skip. Derive their input types from existing command shapes; no `any` send escape hatch. Expose readonly state and editable configuration separately. View-step components never send HTTP/socket commands.
- Tests: create `frontend/tests/unit/features/imports/{protocol,workflow}.spec.ts` and synthetic fixtures alongside them; retain `frontend/tests/unit/components/TransactionImportDialog.spec.js` and `TransactionImportDialog.warnings.spec.js`.
- Browser: add `frontend/tests/browser/imports-d6.mjs`, register `imports-d6` in `run-smoke.mjs`, narrowly extend existing fixture server/protocol helpers for synthetic socket conversations. Evidence: `docs/design/frontend-import-workflow.md`, new `d6-` captures and durable tracker.

## Review focus

| Risk | Required evidence |
|---|---|
| Extraction subtly changes start/decision payloads | Golden characterization fixtures for every send site, including flags, optional dates, full match objects and exact decimal strings |
| Duplicate sends or stale callbacks cross close/reopen/session boundaries | Deferred-connect/analyzer/decision tests, generation ownership, once-only starts/completion; teardown only owns its connection |
| Stop/disconnect becomes false completion | Stopping persists until actual `import_stopped`; disconnected/error state never claims completion; no replay |
| Validator rejects real messages or loses partial-result warnings | Inventory both old dispatch paths and backend send sites; fixtures for every event, all counters and structured warnings |
| Decomposition removes decision branches or usable controls | Real synthetic file/API browser paths with account/security/transaction decisions, keyboard focus, mobile/zoom and failure recovery |

## Task 0 — characterize the current workflow

- [ ] Establish baseline on the clean base. Reference only: D5 executor reported 639 frontend tests, lint 0 errors/13 warnings and backend 1386 passed/10 skipped. Measure the new baseline; do not reuse those as current results.
- [ ] Build a source-linked protocol inventory in `frontend-import-workflow.md`: trigger, outgoing exact command, incoming events, state/UI effect, completion event and teardown. Include both `handleMessage` paths and account-selection handling, not just the primary dispatcher. Cross-check actual backend consumers/producers, including progress, initialization, import/save errors, critical errors, security creation, account matching/selection, transaction confirmation, completion and stopped acknowledgment.
- [ ] Add synthetic characterization fixtures for file analyze/account/start, API broker/date/start, Galaxy variants, account matching/create/use-existing, security map/create/skip, transaction confirm/skip, stop/ack, warning completion and disconnect/error. Capture existing parent payload and five counters: total/imported/skipped/duplicate/errors. No invented numeric outcomes.
- [ ] Run fixtures against incumbent behavior before extraction. Record any actual discrepancy from the old design examples and preserve the verified wire behavior. Commit characterization and inventory.

## Task 1 — typed protocol boundary

- [ ] Write failing tests for the typed start/decision builders and incoming decoder. Assert full deep equality against Task0 fixtures, including null/absent distinctions, account-match extras, large decimal strings and structured warning endpoint/error fields.
- [ ] Implement `types.ts` and `legacyImportProtocol.ts` following the accepted interfaces. Known nonterminal messages remain nonterminal; malformed/unknown messages produce a safe recoverable protocol error, never fabricated completion. Do not log raw messages or secrets in errors.
- [ ] Integrate the protocol seam into existing handlers with minimal UI changes. If an unexpected message occurs during an active import, keep stop/cleanup ownership reachable and do not offer an unsafe duplicate start while server work may continue.
- [ ] Run protocol and incumbent dialog/warning tests; commit the boundary independently.

## Task 2 — one state owner and lifecycle-safe orchestration

- [ ] Write failing workflow tests for all characterized transitions, duplicate start while connect is pending, failed connect/send, late analyzer/lookups after close, stale socket events after reset/reopen, session end, once-only completion and stop pending until acknowledgment. Include reject/cancel paths for every decision type.
- [ ] Evolve `useImportState` in place to the accepted discriminated union and readonly state; move orchestration into `useTransactionImport`. Remove independent booleans as state authorities after migration; child overlay visibility derives from the active state. Configuration fields are not a second workflow state machine.
- [ ] Normalize the existing transport behind `ImportTransport`; preserve command order and existing explicit restart rules. Set start ownership before awaiting connect; only the owning generation may update state or emit completion. Cleanup invalidates pending work and removes the owned message watcher/socket connection. Do not clear unrelated auth/session state.
- [ ] `requestStop` sends once and enters stopping; stop acknowledgment determines the stopped outcome using existing semantics. A failed send or connection loss must not falsely say stopped/completed. Preserve a retryable decision's values after rejection.
- [ ] Close/reset removes previous file and decision data; late callbacks cannot repopulate the next run. Carry warnings and all server counters unchanged into completion and the compatibility emit. Do not derive success from imported-count arithmetic.
- [ ] Run workflow/protocol and original dialog suites; commit orchestration/state extraction.

## Task 3 — step components and compatible entrypoint

- [ ] Add failing public-behavior tests for method choice, relevant configuration, source/account review, each decision dialog, progress/stop and result with warnings. Retain original completion events and parent invalidation assertions; replace internal-boolean tests only with equivalent external-behavior coverage.
- [ ] Extract method/source/review/result components with typed props and intent emits. Keep existing decision dialogs first-class; keep security conflict/mapping/create/skip, account matching and per-transaction confirmation accessible. Do not reduce workflows to a happy-path wizard.
- [ ] Keep one polite progress announcement region, named controls, visible sections/errors, exact financial displays and a usable back path only where safe. Reuse reviewed focus patterns with close/unmount cancellation; no fixed timeout as the only response to slow fields. Shared importer entrypoint still honors v-model and emits the original completion payload.
- [ ] Verify file/API configuration and result/decision layouts at desktop, 390px and native 200% zoom. Assert actual control bounds/hit-testing rather than document scrollWidth alone. Commit UI composition after focused gates pass.

## Task 4 — rendered protocol acceptance, gates and review

- [ ] Run real loopback synthetic WebSocket flows through the UI: file analyze→review→start→transaction decision→warning result; API start→account matching/selection→security map/create/skip; stop→delayed acknowledgment; failed connect/send and disconnected/error; close/reopen and delayed old events. Assert exact commands/order, no duplicate starts/completion and unchanged final parent event. Fixtures must fail unmatched HTTP/socket traffic and reflect real backend envelopes.
- [ ] Capture configuration, decision, stopping and warning-result states using synthetic data. Inspect the images and record viewport/commit/source fixture. Real assistive-technology testing remains unperformed unless actually done; DOM/keyboard checks are not a screen-reader audit.
- [ ] On committed implementation run from `frontend/`: `npm run test:unit`, `npm run type-check`, `npm run type-check:reliability`, `npm run type-check:charts`, `npm run lint`, `npm run api:types:check`, `npm run build`, `npm run test:browser`, `npm run test:browser -- --case imports-d6`, `npm run test:delivery`. Ensure all new TS files are included in type checking; do not exclude the feature to pass.
- [ ] Also run existing focused cases `layout`, `context`, `dates`, `requests`, `recovery`, `dialogs`, `dialog-recovery`, `d4`, `d5`, `settings-account`, `charts-c2`, `charts-c3`. From `backend/`, run `uv run python -m pytest` with `DJANGO_SETTINGS_MODULE=portfolio_management.test_settings`. Capture native process exit codes; run heavy/browser gates sequentially to avoid the known worker/daemon contention. Do not raise delivery budgets or weaken assertions/lint baselines.
- [ ] Record tested SHA/directory, actual results, RED evidence, deviations, failures/retries and remaining acceptance. Remove only owned temporary sessions/servers. Update task20 to implemented/pending review, not merged/completed modernization.
- [ ] Push `codex/transaction-import-d6` and open one draft PR into `codex/frontend-modernization`. Describe the extracted boundaries and protocol parity evidence. Stop for review; no merge/deploy/D7/C4/C5 work.
