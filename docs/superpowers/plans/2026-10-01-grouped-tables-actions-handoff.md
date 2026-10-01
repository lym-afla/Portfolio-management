# D4 Grouped Tables and Accessible Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Inline GLM execution is selected; do not delegate implementers unless the user requests it. If the skills are unavailable, follow this written sequence and project rules directly.

**Goal:** Complete master task 16/D4: practical grouped-column views for both positions tables, reusable controls/actions, and identified, accessible transaction confirmation/forms.

**Architecture:** Preserve financial fields and R's API/query ownership. Derive headers, group boundaries, pinned identity and footer alignment from one ordered visible-column model. Keep display preferences separate from the existing query controller. Reuse existing transaction handlers and detail/delete endpoints behind shared presentation components.

**Tech Stack:** Existing Vue 3, TypeScript, Pinia, Vuetify, Vitest, agent-browser and Vite. Locked Node >=24.20.0 <25 and backend uv project mode. No new production dependencies.

**Spec:** Accepted [D4 design/workflow task](2026-09-08-frontend-design-workflows.md#d4-consolidate-table-controls-actions-and-dialog-accessibility), [grouped-table audit](../../audits/2026-09-08-grouped-tables-and-allocation-pies.md), and [master plan](2026-09-08-frontend-modernization.md). Read the full D4 section; this handoff supplies current-source interfaces and execution boundaries.

## Global constraints

- Pull latest `origin/codex/frontend-modernization`, including user-merged PR #50 at `2238ef3e6789b552f497cfbaef1976fabf02d719` and this handoff. Create `codex/grouped-tables-actions`; record actual base and inspect later commits. Do not base on main or replay C1/D3.
- Read `AGENTS.md`, `.memory-bank/index.md`, AI rules and authoritative NAV/calculation/FX documents. Preserve user changes; no reset, clean, destructive stash, force push or production mutation.
- Scope is open/closed positions and Transactions, plus shared components and the two transaction forms. No D5 all-route rollout, C2/C3/ECharts, pies, import extraction, broker/security extraction or backend changes. Three solid pies remain C4. Reuse D1/D3 light visual system.
- Preserve every existing backend key/value, signed and unavailable values, totals, quantity/price units and transaction event payload. No money parsing, arithmetic, formula changes or invented closed Entry/Exit prices.
- Preserve R3/R5 context/session isolation, request snapshots, debounce, latest-response acceptance and error/retry behavior. Presentation presets must not create a competing fetch controller.
- Table identity and chooser selections persist per table and authenticated user, independently of globally shared query settings. Do not store transaction data or auth tokens in preferences; unknown user identity must not share persistent preferences across users.
- Synthetic populated fixtures only. Use agent-browser with observed refs for browser interactions. Verify geometry by hit-testing as well as bounding boxes; Vuetify's inline sizes can clip apparently valid rectangles.
- All required checks must return actual exit code 0. Capture npm/pytest's exit status before printing logs; warning counts or the last command in a pipe are not gate results. No lint suppression/checker weakening or stale baseline entries.

## Review focus

1. Hidden/reordered columns retain identity and Assets/Cash/TOTAL labels, correct footer alignment, units and intelligible hidden-sort state (tasks 1–3).
2. Saved Full ledger survives navigation, resize, malformed/old preference data and reporting-currency changes without crossing users/tables (task 2).
3. Sort/search/page actions retain server order and latest-query ownership; the rendered table must not re-sort or filter just the received page (task 3).
4. Regular/FX transactions with the same numeric ID, delayed detail replies, rejected deletion and changed filters cannot retarget confirmation or issue duplicate requests (task 5).
5. Mobile/native zoom and keyboard focus retain every action, both header tiers and useful financial inspection; actual DOM associations and hit targets must be verified (tasks 3–6).

## File responsibilities

| Path | Responsibility |
|---|---|
| `frontend/src/config/positionsHeaders.js` | Existing keys plus group/full-label/unit/identity metadata; retain exports needed by callers |
| `frontend/src/config/positionsTableViews.ts` (new) | Pure preset definitions and ordered visible-column/header derivation |
| `frontend/src/composables/usePositionsTableView.ts` (new) | User/table-scoped presentation preferences, validation and migration |
| `frontend/src/components/workspace/types.ts` | Shared toolbar/action/confirmation presentation contracts |
| `frontend/src/components/workspace/{WorkspaceActions,WorkspaceTableToolbar,WorkspaceEmptyState,ConfirmActionDialog}.vue` (new) | Reusable accessible presentation components |
| `frontend/src/components/PositionsPageBase.vue` | View chooser, grouped chooser, semantic/sticky table, explicit sort summary and existing query integration |
| `frontend/src/views/{OpenPositionsPage,ClosedPositionsPage}.vue` | Stable table IDs, security/type identity, footer label/leaf alignment |
| `frontend/src/composables/useTableSettings.ts` | Only necessary integration with existing query setters; keep query ownership intact |
| `frontend/src/views/TransactionsPage.vue` | Existing action routing, toolbar and fixed-identity delete lifecycle |
| `frontend/src/components/transactions/TransactionRow.vue` | Named row action buttons; unchanged emitted row payload |
| `frontend/src/components/dialogs/{TransactionFormDialog,FXTransactionFormDialog}.vue` | Visible form grouping/errors, keyboard/focus and rejected-save preservation |
| `frontend/tests/unit/{config,workspace,components}/` | Focused metadata, preferences, table, actions, dialog and lifecycle regressions |
| `frontend/tests/browser/{fixtures,fixture-server,layout,run-smoke}.mjs` | Complete populated fixtures and rendered behavior checks |
| `docs/design/frontend-workspace.md`, `docs/design/assets/frontend-workspace/` | D4 choices, rendered evidence, limits and reproducible checks |

## Presentation model and exact views

Add stable metadata on every original leaf: `key`, `groupId`, `title` (short), `fullTitle` (qualified), `unitKind`, `description`, `identity`, `pinned`. Group IDs: `identity`, `entry`, `current`/`exit`, `performance`. Unit kinds distinguish identity/date/quantity/instrument-price/reporting-money/ratio; describe instrument-specific price semantics, including bond percent-of-nominal. Units react to committed reporting currency where appropriate; never label a local-currency price as reporting money just for consistency.

Export `PositionTableId = 'open-positions' | 'closed-positions'`, `PositionPresetId = 'overview' | 'comparison' | 'full-ledger' | 'custom'`; `positionPresets(tableId)`, and `buildPositionView(tableId, preset, visibleKeys, currency)` from the new config module. Output is one ordered visible leaf list plus flat/grouped headers derived from it. Use existing key order inside each group; ignore invalid keys and always retain `name`. Group-start flags feed headers, body and footers, not separate index-based rules. Do not rename backend keys.

| View | Open keys | Closed keys |
|---|---|---|
| Overview | `name, currency, entry_value, current_value, share_of_portfolio, total_return_amount, total_return_percentage, irr` | `name, currency, entry_value, exit_value, total_return_amount, total_return_percentage, irr` |
| Comparison | `name, currency, investment_date, entry_price, entry_value, current_price, current_value, share_of_portfolio` | `name, currency, investment_date, entry_value, exit_date, exit_value` |
| Full ledger | All original 20 leaves: Identity 4 + Entry 3 + Current 3 + Performance 10 | All original 16 leaves: Identity 3 + Entry 2 + Exit 2 + Performance 9 |

Overview is one structural header row, fully qualified labels, Security (`name`) with Type as secondary identity text. Comparison labels: **Entry & valuation** / **Entry & exit**, both sides simultaneously visible. Full ledger has exactly two structural rows; quiet left-aligned group bands and numeric leaves aligned with values. Flatten redundant closed Amount/% groups into qualified Performance leaves. Custom uses the selected visible leaves with grouping, no third structural tier. Wrapping a heading over two text lines is allowed.

`usePositionsTableView(tableId, columns)` produces reactive `{ preset, visibleKeys, setPreset, toggleColumn, resetView }`. Persist a versioned `{ version: 1, preset, visibleKeys }` under a table/user-scoped key; validate enum/types/duplicates/unknown keys, tolerate unavailable storage, force `name` visible, and fall back to Overview for corrupt/unconfigured data. No existing persisted column preferences exist at this checkpoint; do not invent a migration from global query sort/search preferences. Restore existing per-table presentation data if later source changes add it. Resize never mutates saved choice. Session changes cancel observers/read state; derive stable user scope from existing auth identity, not access tokens or display names.

Add `tableId` to PositionsPageBase props; keep fetchPositions/accepted-result contracts. Keep local query source in `useTableSettings` and `usePortfolioRequest`, separate from presentation preferences. If installed `v-data-table` re-sorts/filters the received page, use its actual server-controlled variant/props as a bounded rendering repair. Never add backend sorting or calculate numeric sort values from formatted strings.

Shared interfaces in workspace/types.ts:

```ts
interface WorkspaceAction { id: string; label: string; icon?: string; disabled?: boolean; loading?: boolean }
interface TableQueryView { search: string; page: number; itemsPerPage: number }
interface ConfirmationSubject {
  title: string; confirmLabel: string;
  details: readonly { label: string; value: string }[]
}
```

`WorkspaceActions` props `{ primary?: WorkspaceAction; secondary: readonly WorkspaceAction[]; overflow: readonly WorkspaceAction[] }`, emit `action(id)`. `WorkspaceTableToolbar` props `{ query: TableQueryView; searchLabel: string; searchPlaceholder?: string; rowsPerPageOptions: readonly number[] }`, emit `update:query(Partial<TableQueryView>)`, slots filters/actions/columns; it emits intent only. `WorkspaceEmptyState` props `{ title; description; action?: WorkspaceAction }`, emit action(id). `ConfirmActionDialog` props `{ modelValue; subject: ConfirmationSubject; busy; error: string|null }`, emits update:modelValue and confirm. Parent owns detail loading, API calls and immutable selected identity; confirmation is disabled while details load.

## Task 1: Column model and preset derivation

- [ ] Read actual header exports, percentage keys, parent/footer slots, table settings and installed Vuetify server/header APIs. Inventory the original 20/16 keys in tests before restructuring.
- [ ] Write failing `tests/unit/config/positionsTableViews.spec.ts`: exact Overview/comparison lists above; every original key reachable in Full ledger; open Performance10/closed Performance9; two-tier ceiling; no invented closed price keys; qualified full labels; visibility drops empty groups and recomputes first-leaf boundaries; `name` survives hide-all.
- [ ] Observe RED, extend metadata and implement pure builders. Preserve existing descriptions, percentage fields, sort support and external exports; update old header tests for deliberate grouping changes without dropping key/meaning assertions.
- [ ] Test reporting currency changes update reporting-money descriptions while instrument prices retain their unit meaning. Run focused config tests and commit the model unit.

## Task 2: Shared toolbar and presentation preferences

- [ ] Write failing `tests/unit/workspace/TableToolbar.spec.ts` for labelled search, rows selector and slots; one change emits one intent, no fetching/money formatting. Write `tests/unit/workspace/PositionsTablePreferences.spec.ts` for independent open/closed/user state, corrupt storage, invalid keys, locked name, refresh/navigation restoration and saved Full ledger preserved on resize.
- [ ] Implement the shared toolbar/empty state and view composable/contracts. Keep rows-per-page in one place with pagination in the table footer. Search remains debounced through the existing setter; do not build a second debounce/fetch path.
- [ ] Add grouped Columns chooser with full qualified names, checked state, locked Security identity and explicit Done; it stays open during repeated choices. Presets have visible labels and selection state. Toggling a leaf yields Custom without erasing previous valid selection data.
- [ ] Verify GREEN plus existing table-settings/date/context/pagination regressions; commit the controls/preferences unit.

## Task 3: Position table integration, semantics, pinning and totals

- [ ] Write failing `tests/unit/components/PositionsTableViews.spec.ts`: render both tables in every view, keep amount/% separately sortable, hide Type/reorder identity without pinning Currency, retain Assets/Cash/TOTAL labels in Security column, and render every footer cell under its visible leaf. Empty/error/filtered-empty states remain distinct.
- [ ] Add hidden-sort test: sort by Entry price, hide it, retain visible `Sorted by Entry price — ascending` and Clear sort action; visibility/preset does not mutate server sort until Clear. Add a multi-page fixture whose server order differs from local order; assert displayed order and outbound sort/search/page params remain server-owned with R5 stale-response tests.
- [ ] Integrate stable table IDs, Security+Type overview identity and pure visible metadata. Replace nth-child pinning with key-based cell/header/footer props and measured offsets, updating when visible columns/widths change and cleaning observers on unmount. Preserve name truncation/accessibility and useful mobile data width.
- [ ] Render a named, keyboard-reachable horizontal/vertical table region and caption. Add actual colgroup/group/leaf/row associations, unique header IDs/data-cell headers where needed, and aria-sort on the actual sorted leaf. Use installed Vuetify slots/props and inspect their rendered output; do not assume it creates semantics. Focusable glossary triggers have qualified labels.
- [ ] Keep both header tiers together during vertical scroll; second-tier offset is measured, not a fixed font-dependent number. Header/body/footer group boundaries come from visible metadata. Table scrolling stays below the existing measured app-bar layout; no page-level overflow or compressed financial cards.
- [ ] Verify component/config suites and current PositionsPageBase/PositionsPages tests, types and build. Commit the table integration unit; rendered scrolling/hit checks remain mandatory task 6.

## Task 4: Transaction action hierarchy and row controls

- [ ] Write failing `tests/unit/workspace/WorkspaceActions.spec.ts` for primary/secondary/overflow keyboard access and exact emitted IDs. Write `tests/unit/components/TransactionRow.actions.spec.ts` for named Edit/Delete buttons including date and available account/security, 44px targets and unchanged emitted row object.
- [ ] Implement actions: primary Add transaction; secondary Import transactions; overflow Add FX transaction, Transfer asset, Record merger. Wire IDs to the existing handlers in TransactionsPage; preserve lazy dialog loading and completion events. Keep all five flows reachable and enabled/disabled appropriately.
- [ ] Replace click-only row icons with named Vuetify buttons, preserve signed amount text and row descriptions. Integrate shared toolbar while retaining date range and query ownership.
- [ ] Verify GREEN and existing transaction description/request/dialog delivery tests. Commit the action unit.

## Task 5: Exact confirmation and form accessibility

- [ ] Write failing `tests/unit/workspace/ConfirmActionDialog.spec.ts` using real Vuetify/teleported dialogs, attachTo document.body: identified details remain after API rejection, Cancel/Escape never confirm, busy blocks repeated confirm, accessible title/description and focus restoration. Do not substitute a generic dialog div stub.
- [ ] Write `tests/unit/components/TransactionsPage.confirmation.spec.ts`: regular_5 and fx_5 stay distinct; fixed selection survives filter/account/list changes; late detail replies cannot replace a later subject; detail failure disables deletion; rejected deletion retains subject/error; success deletes once through the correct endpoint and refreshes existing query. Auth session change closes/invalidate old subject and pending replies.
- [ ] Reuse `getTransactionDetails`, `getFXTransactionDetails`, `deleteTransaction`, `deleteFXTransaction` from `frontend/src/services/api.ts` with current signatures. Snapshot transaction kind/actual ID and displayed date/account/security/type/amount/quantity/currency. If list details are insufficient, load existing detail before enabling confirm; do not manufacture missing financial descriptions or convert raw amounts through float. No new backend/detail endpoint.
- [ ] Parent retains selected snapshot until close; generic Delete/OK becomes **Delete transaction** / **Cancel**. Failure retains inline error and subject; success closes only after mutation outcome is known. No promised undo. Initial destructive focus goes to Cancel, idle Escape cancels, busy state prevents duplicate submit/accidental dismissal; restore focus to invoking control or meaningful table/action fallback if the deleted row is gone.
- [ ] Add form regression coverage for rejected regular/FX saves preserving all entered fields, inline field/server errors, visible section labels, initial/returned focus and unchanged save payloads/Yup rules. Keep bond percent price hints; do not change numeric validation or formula rules under a UI task.
- [ ] Run focused action/confirmation/form tests, full frontend units and both types. Commit the dialog/form unit.

## Task 6: Rendered acceptance, review and submission

- [ ] Extend complete synthetic fixtures for both positions tables with long names, two+ currencies, zero/negative/unavailable values, totals and multiple server pages; regular/FX transactions with duplicate numeric IDs, detail delay/failure and deletion failure. Mutation fixtures record actual request identity/body so UI success cannot mask wrong endpoint/subject.
- [ ] Add rendered checks using agent-browser and snapshot refs: switch presets, make several chooser changes before Done, restore on route return, hide active sort and Clear sort, change reporting currency, sort/page and verify server order, scroll horizontally/vertically with both header tiers/identity/footer alignment, and open glossary by keyboard. Assert control containment and `elementFromPoint` hit-testing at 1440×1000, 1024×768, 390×844 and 768×1024.
- [ ] Check actual DOM caption, group/leaf/data/row associations and aria-sort; inspect at least one full ledger and both flat Overviews. Record a screen-reader smoke with actual available assistive tooling, or explicitly mark it unavailable rather than inferring a complete screen-reader audit from DOM tests.
- [ ] Verify real keyboard row actions, overflow items, destructive focus/Cancel/Escape/return, rejected delete/detail/save and subsequent correction. Use synthetic mutations only. Verify actual native 200% browser zoom with the corrected `qa-native-zoom.mjs` (DPR/viewport plus reachable controls); the smoke suite's CSS zoom profile is supplementary, not this gate.
- [ ] Save synthetic captures under `docs/design/assets/frontend-workspace/`: `d4-open-overview-desktop.png`, `d4-open-ledger-desktop.png`, `d4-open-overview-mobile.png`, `d4-closed-comparison-desktop.png`, `d4-closed-overview-mobile.png`, `d4-columns-mobile.png`, `d4-transaction-confirmation.png`. Record table-local scrolling, focus/contrast and action/menu checks in docs/design/frontend-workspace.md. Batch review/fixes and one confirmation pass; further checks require new changes or unresolved defects.
- [ ] Obtain scoped technical review, correct important findings with focused regressions, and review the rendered evidence before submission. Record visual/assistive limitations honestly. Close every browser/server/observer started for QA.

## Required final gates and delivery

From frontend on locked Node: `npm run test:unit`, `npm run type-check`, `npm run type-check:reliability`, `npm run lint`, `npm run api:types:check`, `npm run build`, `npm run test:browser` plus affected focused cases. New focused suites above run first; maintain existing request/context/date/recovery/delivery/dialog tests. API types are generated, never edited manually. Baseline lint is 36 warnings at the merged D3 checkpoint; gate matches exact diagnostic fingerprints, not just the count. Update only justified stale/moved entries after verifying no new diagnostic debt; capture actual checker exit code.

From backend with test settings/live tests disabled: `uv run python -m pytest` as project rules require. Latest executor full baseline was 1386 passed/10 skipped; root verified scoped C1 and D3 checks separately, not that full count. Establish your current baseline and report actual results/exit codes. Do not fix unrelated protected code or silently waive a failed gate.

- [ ] Update handoff checkboxes, durable tracker and design notes with actual base/head, RED/GREEN, gate exits, reviews and screenshot paths. Distinguish implemented/review-ready, integration, visual acceptance and final release.
- [ ] Push `codex/grouped-tables-actions` and open a draft PR into `codex/frontend-modernization`. Include before/after view examples, all-field/key preservation, server query ownership, delete identity/failure tests and rendered evidence. Attach it if supported. If browser/publication tools are unavailable, preserve finished work and report precisely which acceptance remains unmet.
- [ ] Stop after the review-ready D4 proposal. Do not merge either branch, deploy or begin C2/C3/D5. Any unexpected protected/numeric behavior proposal needs its own needs-approval PR; this assignment does not authorize financial changes.

**Completion:** Both position tables, shared controls/actions and transaction confirmation/forms must satisfy their specified behavior and rendered gates. Missing evidence is not completion. Main and broader modernization remain unfinished; C2 is the next separate task after D4 integration.
