# Frontend import workflow — legacy protocol inventory (D6)

Source-linked inventory of the transaction import workflow, recorded at the D6
extraction base `57f251d3` (PR #56 merged). It is the wire-behavior contract
the D6 extraction must preserve byte-for-byte. Characterization fixtures:
`frontend/tests/unit/features/imports/fixtures.ts`, driven against the
incumbent component by `incumbent.spec.js` (51 tests, all green at base).

Sources: `frontend/src/components/dialogs/TransactionImportDialog.vue`,
`frontend/src/composables/useWebSocket.ts`,
`frontend/src/composables/useImportState.ts`,
`backend/transactions/consumers.py` (read-only),
`backend/transactions/views.py::analyze_file` (read-only).

## 1. Transport

- Single socket: `useWebSocket('/ws/transactions/')`, created at dialog setup.
  `connect()` resolves `true`/`false` (3 s timeout), auto-connects once at
  creation when auth is initialized, auto-reconnects 3 s after unclean closes.
  The dialog calls `reset()` (clears `intentionalClose`/`connectionAttempted`)
  immediately before each `await connect()` in a start flow, then sleeps 100 ms
  before checking `isConnected`. There is no replay of starts/decisions after
  reconnect (the incumbent does not resend anything on its own).
- Outgoing: `sendMessage(obj)` JSON-serializes one command; returns `false`
  when the socket is not `OPEN`. Incoming: parsed JSON lands in `lastMessage`
  (a fresh object per frame); the dialog watches it. Unparseable frames never
  reach the dialog (transport logs and drops).

## 2. Outgoing commands (exact wire objects)

| # | Trigger (dialog site) | Exact command |
|---|---|---|
| 1 | File “Import Transactions” (`startImport`) | `{type:'start_file_import', file_id, account_id, confirm_every, is_galaxy, galaxy_type: is_galaxy ? galaxyType : null, currency: is_galaxy ? currency : null}` |
| 2 | API “Import Transactions” (`startApiImport`) | `{type:'start_api_import', data:{broker_id, confirm_every_transaction, date_from: from\|\|null, date_to: to\|\|null}}` |
| 3 | “Stop Import” (`stopImport`) | `{type:'stop_import'}` — sent unconditionally, even when disconnected |
| 4 | Mapping dialog confirm (`handleConfirm`, mapping visible) | `{type:'security_mapped', action:'map', security_id}` |
| 5 | Mapping dialog skip (`handleSkip`, mapping visible) | `{type:'security_mapped', action:'skip', security_id:null}` |
| 6 | Progress confirm (`handleConfirm`, no mapping) | `{type:'transaction_confirmed', confirmed:true}` |
| 7 | Progress skip (`handleSkip`, no mapping) | `{type:'transaction_confirmed', confirmed:false}` |
| 8 | Security created from mapping (`handleSecurityAdded`) | `{type:'security_mapped', action:'map', security_id: newId}` |
| 9 | Security created otherwise (`handleSecurityAdded`) | `{type:'security_confirmation', security_id, security_created:true, security_data:{name, id}}` |
| 10 | Security form skipped from mapping (`handleSecuritySkipped`) | `{type:'security_mapped', action:'skip', security_id:null}` |
| 11 | Security form skipped otherwise | `{type:'security_confirmation', security_id:null, skip_transaction:true}` |
| 12 | Readonly-security confirm (`handleSecurityConfirm(true)`) | `{type:'security_confirmation', security_id}` — no other keys |
| 13 | Account selection dialog (`selectAccount`) | `{type:'select_account', data:{account_id, confirm_every_transaction, date_from, date_to}}` — dates passed through as-is (`null` when unset) |
| 14 | Account matching applied (`handleAccountsMatched`) | `{type:'accounts_matched', data:{pairs}}` — pairs carried verbatim incl. full `tinkoff_account`/`db_account` objects |
| 15 | Use existing matches (`handleUseExistingMatches`) | `{type:'use_existing_matches', data:{pairs}}` — same verbatim pairs |
| 16 | Create account (`handleAccountCreation`) | `{type:'create_account', data:{tinkoff_account, name, comment: comment\|\|''}}` |

Decision sends are guarded by `isConnected` (4–12); starts re-check it after
connecting (1–2). Guard-quiet decisions still reset the confirmation UI.

### Recorded wire discrepancy vs the accepted D6 example

The accepted design section says “The API start currently transmits
`date_from` only” and its example omits `date_to`. The incumbent **does**
send `date_to` (command 2, `TransactionImportDialog.vue` `startApiImport`) and
`backend/transactions/consumers.py` **reads** it
(`start_api_import(... date_to=data.get("date_to"))`, threaded into
`import_transactions_from_api`). Dropping it would change broker import
ranges for users who set a To date — a financial behavior change. Per the
handoff rule “record any actual discrepancy … and preserve the verified wire
behavior”, the extraction keeps `date_to` (`ApiStartInput.dateTo`,
`apiStartCommand` emits it). The account-selection command (13) is a separate
existing contract that has always carried both dates.

## 3. Incoming events and both dispatch paths

The dialog has TWO handlers. The `watch(lastMessage)` path intercepts a
subset of types itself and delegates everything else to
`handleWebSocketMessage`. Effective routing:

| Event (backend producer) | Route | Effect |
|---|---|---|
| `account_selection_required` `{data:{available_accounts}}` | watcher (dead branch: no backend producer) | lists accounts in the selection dialog |
| `import_error`/`critical_error` `{data:{error}}` | watcher | security-string → `handleImportError` (create/skip dialog); else error dialog (`errorMessage`), teardown+disconnect for `critical_error` only |
| `error` `{data:{message}}` | watcher | `importError` set, progress message cleared, state error |
| `progress` `{data:{message,total,current}}` | watcher | counters/message |
| all other types | `handleWebSocketMessage` | below |

`handleWebSocketMessage` routing (consumers.py is the producer reference):

| Event | Producer | Effect |
|---|---|---|
| `initialization` `{message, total_to_update}` (top-level fields) | `process_import` | totals + message |
| `security_creation_needed` `{security_info:{name,isin,currency}}` (top-level) | none found (dead branch) | prefills security form (`currency\|\|'RUB'`, `type:'Stock'`, `exposure:'Equity'`) |
| `import_update` `{data:{status:…}}` | `process_import` | see status table |
| `import_error`/`save_error` `{data:{error}}` | `process_import`/`send_error` | security-string → `handleImportError`; else same (`handleImportError`) — dead for `import_error` (watcher intercepts first), live for top-level `save_error` |
| `critical_error` | `send_error` | error dialog + disconnect + full reset (see defect D-2) |
| `import_complete` `{data, message}` | `process_import` | success dialog, counters, **emit `import-completed` with the RAW data object once**, disconnect, resets |
| `import_stopped` `{data:{message, stats?}}` | stop handler (stats) and `process_import` finally (no stats) | stopped outcome: error dialog “Import process was stopped by user”, stats into `importStats`, disconnect, resets; **never** emits `import-completed` |
| `transaction_confirmation` (top-level type) | none found (dead branch; would misread `data.data`) | — |
| `account_matching_required` `{data:{broker_id, broker_name, matched_pairs(object), unmatched_tinkoff, unmatched_db}}` | `start_api_import` | sets `selectedBroker` from the message, transforms `matched_pairs` object → array `{tinkoff_account_id(key), db_account_id: pair.db_account.id, tinkoff_account, db_account}` preserving both full objects, shows matching dialog, hides progress |

`import_update.data.status` values (all producers in `process_import` /
`process_account_matches` / `create_account_and_import`): `total_count`
(`total`, `message`), `progress` (`current`, `message`, `progress?`),
`transaction_saved` (`current`, `total`, `message`, `transaction`),
`transaction_error` / `save_error` (`message`, `error_detail`) → inline
`⚠️ …` message, import continues, `security_mapping`
(`mapping_data{security_description, isin, symbol, best_match}`,
`transaction_data`) → both overlays open, `transaction_confirmation`
(`data` = serialized transaction: money/quantity as display values passed
through verbatim) → confirmation overlay without mapping,
`unrecognized_operation` → **ignored by the frontend** (no branch).

Also produced by the backend but **ignored** by the incumbent:
`import_warning {data:{message}}` (e.g. “Import already in progress” — the
server-side duplicate-start guard) and `import_cancelled
{data:{message}}` (task cancelled on disconnect). The extraction must keep
accepting both without fabricating completion.

Error-string classification (frontend heuristic): messages containing
`Security not found`, `Could not match security`, `unsupported operand type`,
or `NoneType` open the “Unknown Security Detected” create/skip dialog, with
name/ISIN regex-extracted from the error (`/([^(]+)\(([^)]+)\)/` — the
captured name retains the matched prefix, e.g. `Security not found: ACME
Corp`).

Matched-account inconsistency: an `import_error` whose error contains
`not matched to any database account` while that `ID: <digits>` appears in
`matchedPairs` short-circuits to a dedicated “Server inconsistency detected…”
error dialog (early return; no other handling).

## 4. Counters, warnings, completion

- Five counters only, all server-owned integers:
  `totalTransactions, importedTransactions, skippedTransactions,
  duplicateTransactions, importErrors` plus structured
  `warnings:[{endpoint, error}]`. The parent emit payload is the RAW
  `import_complete.data` object (warning-free completions carry **no**
  warnings key); the success dialog normalizes its own view with
  `{warnings: [], ...result}`. Success is never derived by the frontend from
  counter arithmetic; stopping is never success.
- `import_stopped` shows the stopped outcome via the error dialog with the
  fixed string “Import process was stopped by user” and never emits
  `import-completed`.

## 5. Recorded incumbent defects (fixed only where the plan authorizes)

- **D-1** Stats-less `import_stopped` (sent by `process_import`’s finally
  block) overwrites `importStats` with `undefined`; the result template then
  crashes reading `.warnings`. The state owner must treat warnings as
  optional in both stop and completion.
- **D-2** `critical_error` sets the error message, then its own teardown’s
  `resetProgressDialog()` clears `errorMessage`, so the error dialog opens
  empty. The extracted orchestrator keeps the message visible; no wire
  impact.
- **D-3** `handleAccountsMatched(null)` crashes on `selection.pairs` in a
  `logger.log` call placed before the guard. The orchestrator validates
  before touching nested fields.
- **D-4** The bare `error {message}` envelope (no `data`; sent by the
  consumer for invalid JSON/missing keys) crashes the watcher on
  `message.data.message`. The decoder classifies it as a safe recoverable
  protocol error instead.
- **D-5** Cancel (`closeDialog`) never resets method selection;
  `importMethod/importMethodSelected` survive. The extracted reset clears
  the whole workflow (deviation recorded deliberately).
- **D-6** Starts have no once-only guard: a second click re-runs
  `connect`+`send`. Task 2 adds start ownership (send once per generation)
  while preserving the command bytes.
- **D-7** `analyze` failure flashes state `error` then immediately `idle`
  (two `setState` calls back-to-back); `accountIdentificationComplete`
  doubles as a completion latch in `finally`.

## 6. Teardown

Unmount disconnects the socket. Completion/stop/critical paths disconnect
(`intentionalClose`, no auto-reconnect afterwards) and reset progress and
confirmation state. `closeAccountMatching` disconnects+resets only when an
import error is pending. The auth/session stores are never touched.

## 7. Extraction status (D6 implementation record)

Implemented on `codex/transaction-import-d6` (worktree `Portfolio-management-d6`, base `57f251d3`). The extraction keeps every command, decision, counter, warning, parent payload and stop acknowledgment recorded in sections 1–6; the characterization fixtures (`frontend/tests/unit/features/imports/fixtures.ts`) are the invariant — the same objects pinned the incumbent (`incumbent.spec.js` at base) and now pin the extracted units (`protocol.spec.ts`, `workflow.spec.ts`, `steps.spec.ts`, the dialog-level suites).

### Boundaries delivered

- `frontend/src/features/imports/types.ts` — accepted D6 unions (`ImportCommand`, `ImportTransport`, `TransactionImportState`, typed start inputs, `AccountMatchPair` with provider extras, decision payloads).
- `frontend/src/features/imports/legacyImportProtocol.ts` — all 16 command builders (byte-parity with section 2, including the recorded `date_to` discrepancy) plus `decodeImportEvent` over every backend envelope of section 3; unknown/malformed input degrades to a recoverable `protocol-error` (reason only; never a raw payload, never fabricated completion).
- `frontend/src/composables/useImportState.ts` — the sole discriminated state owner (accepted shape); legacy `isIdle/isAnalyzing/isImporting/isMapping/isComplete/isError` are computed projections.
- `frontend/src/features/imports/useTransactionImport.ts` — orchestration: generation ownership (once-only starts/completion, stale-event containment across reset/reopen, late-analyzer discard), decisions with retry-preserving failed sends, stop-pending-until-`import_stopped`, disconnect notification, dismiss-to-configuration semantics.
- `ImportMethodStep.vue` (keyboard-operable cards), `ImportSourceStep.vue` (method-relevant configuration), `ImportReviewStep.vue` (identified-account review + Galaxy currency), `ImportResult.vue` (five counters + structured warnings) — typed props, intent emits, no transport access.
- `TransactionImportDialog.vue` — compatible entrypoint: props `{modelValue}`, emits `update:modelValue`/`import-completed` (raw payload, once); state projections + editable configuration + intent adapters; decision dialogs remain first-class.

### Verified rendered flows (browser case `imports-d6`, exit 0)

Synthetic loopback conversations over a minimal RFC6455 driver (`tests/browser/imports-ws.mjs`) against genuine backend envelopes; commands asserted verbatim at the fixture server:

- File analyze → review → start (`start_file_import` exact, once) → transaction decision (`transaction_confirmed`) → warning result (counters 3/3/0/0/0 + `spot_fills` warning) with the parent table refetch observed (`import-completed` → parent invalidation).
- API start (`start_api_import` with both dates, null `date_from`/`date_to` preserved) → account matching (`use_existing_matches` with full provider objects) → security mapping (`security_mapped` map, id 31) → completion.
- Stop → held acknowledgment: `stop_import` sent once, stop control disabled with no outcome until the synthetic `import_stopped`; stop never claims completion.
- Failed connect: recovery error, no running state, no duplicate start, no completion.
- Stale events on the idle-connected socket (delayed `import_complete`) do not complete or repopulate anything; close/reopen retains no previous file.
- Captures (committed, viewport 1440×1000 desktop / 390×844 mobile / native 200% zoom, fixture driver `imports-ws.mjs`, heads recorded in git): `d6-configuration-review`, `d6-decision-transaction-confirmation`, `d6-decision-security-mapping`, `d6-stopping`, `d6-warning-result`, `d6-mobile-configuration`, `d6-zoom200-method-choice`.

### Deliberate deviations (all recorded, none wire-affecting)

- D-1 fixed: stats-less `import_stopped` keeps the previous stats view (was a render crash).
- D-2 fixed: `critical_error` keeps its message visible (was cleared by its own teardown).
- D-4 fixed: bare `error {message}` envelopes become a recorded protocol issue (was a watcher crash).
- D-5 fixed: Cancel/close resets the whole workflow including method selection.
- D-6 fixed: starts are once-only per run (generation ownership).
- D-9 fixed: failed starts surface their recoverable error instead of closing silently; mid-run disconnects surface a recoverable error instead of hanging; recoverable errors return to configuration with inputs retained.
- Transport: the adapter reproduces the incumbent restart rule (`reset()` before each connect) and `sendMessage` compares `readyState` against the numeric `OPEN` constant because the automation harness proxies `window.WebSocket` without the constructor's static constants (recorded harness quirk; real browsers are unaffected).
- Unknown top-level message types are recorded as non-fatal protocol issues instead of being silently ignored.

### Remaining acceptance

- Real screen-reader audit remains D8 (none performed here; DOM/ARIA/keyboard checks are not a substitute).
- Security-creation and account-selection flows are exercised at unit level (they are frontend-accepted but backend-never-produced branches, recorded in section 3), not in the browser case.
- `import_warning`/`import_cancelled` remain accepted-and-ignored (parity).
