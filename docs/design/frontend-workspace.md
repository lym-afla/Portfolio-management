# Frontend workspace pilot — D3 NAV-first dashboard and positions

Date: 1 October 2026. Scope: D3 of the accepted [design/workflow plan](../superpowers/plans/2026-09-08-frontend-design-workflows.md), executed on branch `codex/dashboard-visual-pilot` (base `dab231b9` on `codex/frontend-modernization`). All captures and measurements below come from the populated synthetic fixture harness (`frontend/tests/browser/fixtures.mjs` + `frontend/scripts/qa-preview.mjs` static build bound to the fixture API, served at `http://127.0.0.1:5189`, agent-browser session `design-pilot`). **Everything in the screenshots is synthetic data.** No production account, broker or financial value is shown.

## Reading order and hierarchy

The dashboard (`DashboardPage.vue`) is composed with the D1 workspace components for the first time:

1. **Committed context** — the shell context strip (account · valuation date · reporting currency) stays in the fixed app bar, exactly as D2 delivered it. The dashboard does not duplicate it; the values region repeats it as a quiet `workspace-meta` line (`All accounts · 2026-09-08 · USD`, long account names wrap) so the numbers stay attributable while scrolling.
2. **Portfolio values** — `PortfolioMetrics` renders the five actual summary fields as a semantic `<dl>`: dominant **Total NAV** (`--workspace-metric` clamp size, full row) above four quieter equal metrics (Invested, Cash out, Total return · *Since inception*, IRR since inception) in a 4-column grid (2-column below 960px). Values are the backend-formatted strings verbatim — `$100.00`, `($25.00)`, `−2.40%`, `N/R` for null; no parsing, no second currency symbol, zeros and losses never hidden.
3. **Value and return over time** — the incumbent Chart.js NAV card, full width, unchanged props/events (same `update-params` contract, retained rendering while updating). Scoped-only CSS: the frequency `v-btn-toggle` wraps and the canvas height drops 600→360px below 600px. Dense canvas point labels are untouched; they remain a C3 issue.
4. **Allocation** — `WorkspaceSection` with the three incumbent `BreakdownChart` cards side by side at ≥960px (stacked below). **Transitional state:** these are still horizontal bars, not the three solid pies — C4 owns the pies; each card keeps its Chart/Table tabs so the allocation table remains one obvious click away.
5. **Historical reconciliation** — `WorkspaceSection` wrapping the existing `SummaryOverTimeTable` (card chrome removed; table scrolls locally inside `.workspace-table-region`). **Update Account Performance** was reduced from a large primary button inside the card to a secondary tonal action in the section header, hidden while the section is loading/failed.

Page title: `WorkspacePage` renders the single `h1` ("Dashboard"); the shell releases its duplicate heading per the D1 ownership contract.

## Positions pilot integration

`PositionsPageBase` received scoped integration only — D1 `v-defaults-provider` defaults and `workspace-ui` scope, the control strip wraps below 600px instead of overflowing the page, and one defect was corrected during review (below). Toolbar structure, grouped two-row headers, all 20 leaf columns, footer totals (Total for assets / Cash / TOTAL), column chooser and sorting are unchanged; preset redesign belongs to D4.

**Defect found and fixed (mobile sticky identity):** at 390px the content-driven Name column grew to 440px — wider than the viewport — so at full horizontal scroll the pinned Type+Name pair covered the entire screen and hid the columns being scrolled to. Fix: below 600px the sticky Name column is capped (`max-width: calc(100vw - 176px)`); the shared nowrap/ellipsis rule truncates very long names. Verified at max scroll: Name 214px wide, last column (IRR) visible beside it.

## Verification evidence

Viewports checked: 1440×1000, 1024×768, 390×844, 768×1024, plus native 200% zoom. All with the dense fixtures (8 positions, 3 currencies, zero/negative/`N/R` values; NAV series with both IRR lines; long account name selected).

- **Header clearance:** app bar bottom 125px, first content top 196px at desktop; `assertLayoutGeometry` passes at all viewports (browser `layout` case).
- **No page-level horizontal clipping:** `scrollWidth` equals viewport width at every checked size; scrolling belongs to the table wrapper (1815px content in a 1184px/358px region).
- **Reading order:** measured section tops 196 → 435 → 1187 → 1566 (values → NAV → allocation → history).
- **Table behavior:** 2-row grouped headers, 13 default-visible leaves, footer totals rows, sort by Name asc→Bitcoin / desc→Vanguard, sticky identity at both desktop and mobile horizontal scroll.
- **Native 200% zoom:** applied through Chrome's real zoom (CDP `Input.dispatchKeyEvent` Ctrl+Plus ×5 after Ctrl+0 on a 1440×1000 window; measured `devicePixelRatio` 2.0 and CSS viewport 720×500 — not CSS zoom, not viewport scaling). At 200%: no clipping, all actions reachable (Display preferences, Update Account Performance, 6 allocation tabs, account menu opens within viewport), Tab shows a solid 2px focus outline rgb(15,76,129), drawer opens with Enter and closes with Escape returning focus to the toggle.
- **Contrast (computed pairs, WCAG AA):** primary NAV value 13.27:1, secondary values 13.27:1, metric labels 5.73:1, context label 5.73:1, section heading 13.27:1, history table text 21:1, NAV card title 21:1, app-bar context text 6.09:1, focus indicator vs surface 8.86:1, tonal action text 8.33:1 — all pass (normal ≥4.5, large ≥3, focus ≥3).

### Screenshots (synthetic fixtures, viewport/zoom noted in filenames' sections above)

| File | Content |
|---|---|
| `assets/frontend-workspace/pilot-desktop.png` | Dashboard, 1440×1000, zoom 100% |
| `assets/frontend-workspace/pilot-mobile.png` | Dashboard, 390×844, zoom 100% |
| `assets/frontend-workspace/pilot-mobile-nav.png` | Mobile navigation drawer open, 390×844 |
| `assets/frontend-workspace/pilot-positions-desktop.png` | Dense Open Positions, 1440×1000 |
| `assets/frontend-workspace/pilot-positions-mobile.png` | Dense Open Positions, 390×844 |

### Reproduction

```text
cd frontend
node scripts/qa-preview.mjs            # fixture API + built app on http://127.0.0.1:5189
npx --no-install agent-browser --session design-pilot --init-script tests/browser/auth-init.js open http://127.0.0.1:5189/dashboard
npx --no-install agent-browser --session design-pilot set viewport 390 844
# native zoom (Ctrl+0 then N× Ctrl+Plus key events via CDP, verified by devicePixelRatio):
node scripts/qa-native-zoom.mjs "$(npx --no-install agent-browser --session design-pilot get cdp-url)" http://127.0.0.1:5189 200
```

The full browser case matrix (`npm run test:browser`, plus `--case layout|context|dates|requests|recovery|delivery|dialogs|dialog-recovery`) was run green before and after the sticky-identity fix and again after the toolbar correction; the `layout` case now also asserts that every positions toolbar control is really visible (elementFromPoint hit-test, inside the toolbar box, within the viewport) and that the Columns menu opens, at all four viewports.

## Failures and corrections during the pilot

1. **Browser layout case failed after the dashboard switch** — its long-title check targeted the shell's legacy h1, which the shell correctly no longer renders once the route owns its heading. The check now accepts either heading (`legacy-page-heading` or `workspace-page-heading`); intent (single h1 in main, no fixed-header growth) unchanged.
2. **Mobile sticky Name column covering the viewport** — found in the first mobile positions review, fixed with the narrow-screen cap, re-verified (see above). Positions screenshots retaken after the fix.
3. **`vite preview`/static build path errors on Windows** (rolldown entry resolution with backslash roots; QA script initially served the wrong directory) — fixed inside the throwaway QA script only; no app change.
4. **Positions toolbar controls clipped/off-screen (PR review round)** — my first mobile verification only measured bounding boxes and missed that Vuetify's `.v-toolbar__content` is a fixed inline 64px box with `overflow: hidden`: below 600px only the Year select was really visible, and hit-tests at the Search/Columns/Rows positions returned table cells. The correction makes the toolbar box grow and wrap at every width (`height: auto !important` against the inline style), gives the Columns button a 44px touch target, narrows the Search column basis and makes the Rows column content-sized — the old 12-column basis sum plus the Columns button had also been pushing the Rows-per-page select past the right viewport edge at sm/md widths (1024/720 CSS px included). A rendered regression now runs in the browser `layout` case at all four viewports: each control must be inside the toolbar box, within the viewport, and actually hittable (`elementFromPoint`), and the Columns menu must open with its 20 column entries. Observed RED against the unfixed markup (mobile: clipped Columns button; desktop/tablet/zoom-200: Rows select past the viewport), GREEN after the fix. The committed `qa-native-zoom.mjs` was also rewritten to the documented key-event method (the first committed version used `Emulation.setDeviceMetricsOverride`, which does not reproduce Chrome's zoom devicePixelRatio in this build); it now reaches exactly 200% (dpr 2.0, CSS 720×500) and exits non-zero otherwise, verified live.

## Deliberate decisions and acceptance limits

- **Transitional allocation bars:** the three cards still render horizontal Chart.js bars. The required final presentation is three solid pies with backend-ratio labels — that is mandatory C4 work and is **not** satisfied by this pilot.
- **Chart accessibility is not passed:** the incumbent NAV chart has no equivalent accessible data table, and canvas point labels are dense. Recorded as outstanding **C3** work; C3's renderer replacement must repeat these captures.
- **Table controls remain incumbent:** grouped presets, organized column chooser, aria-sort and pinned-identity-by-key are **D4**; this pilot deliberately changed none of that behavior (the sticky-width cap is a defect fix, not a redesign).
- **Mobile name truncation:** very long security names ellipsize in the capped sticky column below 600px; the full name is available on desktop and via the security link. D4's preset work revisits mobile density.
- **`SummaryCard`** is retained unchanged (with its tests) as a compatibility adapter; no view consumes it now. Deleting it is cleanup for a later task.
- **Native zoom via CDP key events:** agent-browser's `press Control+=` does not trigger browser zoom in this headless build; the committed `scripts/qa-native-zoom.mjs` drives `Input.dispatchKeyEvent` (Ctrl+0 reset, then Ctrl+Plus steps) and self-verifies `devicePixelRatio` so the documented evidence is reproducible from the repository.

Human visual acceptance of these captures precedes any D5 rollout.

---

# D4 — grouped tables, controls and accessible actions

Date: 1 October 2026. Scope: task 16/D4 of the [design/workflow plan](../superpowers/plans/2026-09-08-frontend-design-workflows.md), executed on branch `codex/grouped-tables-actions` (base `4d44f34d` on `codex/frontend-modernization`). All captures use the complete synthetic D4 fixtures (`tests/browser/d4-datasets.mjs`): 12 open positions across two server pages (long names, three currencies, zero/negative/`N/R` values), 5 closed positions, transactions with duplicate numeric ids (`regular_5`/`fx_5`), a slow detail reply, a failing detail endpoint and a first-failing deletion. **Everything in the screenshots is synthetic data.**

## What shipped

1. **One ordered visible-column model.** Every original leaf (20 open / 16 closed) now carries `groupId`/`fullTitle`/`unitKind`/`identity`/`pinned`/`description` metadata in `positionsHeaders.js`; `positionsTableViews.ts` derives presets and headers from it. Overview is a single flat header row with fully qualified labels (`Security`, `Entry value (USD)` …); Comparison (`Entry & valuation` / `Entry & exit`) shows both sides with quiet group bands; Full ledger is exactly two structural rows (Identity · Entry · Current/Exit · Performance); closed Amount/% groups flatten into qualified Performance leaves. No invented closed price fields; every original key stays reachable.
2. **Server-owned rendering.** Vuetify 3.12 always re-sorts and re-filters the items it is handed; `customKeySort` no-ops plus `itemsLength` (and no `:search` binding) make the displayed order exactly the server's page order while header clicks still cycle asc→desc→none through the existing query pipeline. The D4 browser case pins this with a fixture whose order deliberately ignores the requested sort.
3. **Presentation preferences.** `usePositionsTableView` persists `{version, preset, visibleKeys}` per table and per authenticated user (`positionsTableView.v1.u<id>.<table>`), validates/corrupts-to-Overview, always keeps `name` visible, never writes on resize or route changes, and resets in memory (never touching stored data) when the session ends.
4. **Semantics.** Real `<caption>` (e.g. "Open Positions — Full ledger view") via Vuetify's colgroup slot, per-group `<colgroup>`, `scope="colgroup"` bands, `scope="col"` leaves with stable ids, `headers=` associations on every body cell, `scope="row"` on the Security cell, `aria-sort` on the actually sorted leaf, a focusable named scroll region (`tabindex=0` + aria-label), focusable glossary triggers whose accessible names carry the full title, unit and description.
5. **Key-based pinning with measured offsets.** `col-pin-1`/`col-pin-2` classes come from the leaf model (Type+Security; Security alone when Type is hidden — Currency can never become sticky), and the second offset is the ResizeObserver-measured width of the first pinned column (verified equal to the rendered Type width in the browser run).
6. **Toolbar and choosers.** The shared `WorkspaceTableToolbar` wraps outside the table's scroll region (the D3 clipping lesson); preset select with visible labels; the grouped Columns chooser lists every leaf by lifecycle group with qualified names (money columns append the reporting currency), keeps the Security checkbox locked, stays open across repeated changes and closes on an explicit **Done**.
7. **Hidden sort.** Hiding the sorted leaf keeps a visible `Sorted by Entry price — ascending` summary with **Clear sort**; the server sort is untouched until Clear (verified against the recorded outbound request bodies).
8. **Actions and rows.** `WorkspaceActions` renders primary Add transaction, secondary Import transactions and overflow Add FX transaction / Transfer asset / Record merger, all mapped to the existing handlers and lazy dialogs. Row icons became named Vuetify buttons ("Delete Buy transaction on 08-Sep-26: Fixture Broker — Main — ACME Corp") with 44px `workspace-row-action` targets and unchanged payloads.
9. **Exact-identity deletion.** `ConfirmActionDialog` shows date/account/security/type/amount(s) with currency, focuses Cancel first, restores focus on close, blocks duplicates while busy, and supports detail-loading/detail-failed states. TransactionsPage snapshots kind+numeric id at open, loads `getTransactionDetails`/`getFXTransactionDetails` only when the list row lacks amounts, drops late replies by generation, keeps subject+error after a rejected delete (retry verified: exactly two DELETE attempts — one 400, one 204 — after fixing the fixture to stop counting CORS preflights as deletes), deletes `regular_5` vs `fx_5` through their own endpoints, refreshes once on success, closes on auth session change, and falls back to the primary action for focus when the invoking row is gone.
10. **Forms.** Both transaction forms gained visible section labels (Transaction details / Amounts) via a shared renderer, first-field focus with return-focus, and field updates that revalidate (regular) / clear the field error (FX) so a rejected save can actually be corrected — the browser flow proves the corrected payload is sent verbatim. Yup rules, payload shapes (numbers cross the wire as strings, as today) and the bond `%` price hint are unchanged.

## Rendered evidence

- **Browser case `d4`** (`npm run test:browser -- --case d4`): tables flow (caption, flat/grouped rows, colgroup/scopes/ids, cell associations, server order at page 1 and 2, rows-per-page 10, aria-sort cycling, sticky pair + measured offset under horizontal scroll, both header tiers below the app bar under vertical scroll, footer-under-leaf alignment, chooser stay-open/Done, navigation/resize persistence, hidden sort + Clear, EUR currency reactivity via the context strip with instrument prices unchanged), transactions flow (hierarchy + keyboard-opened overflow, Cancel-first focus, Escape focus return, rejected-then-successful deletion, FX endpoint, slow detail, failing detail, rejected save with preserved fields and corrected retry), per-viewport hit-tests at 1440×1000, 1024×768, 390×844, 768×1024, and the seven captures below. Green: tables flow, transactions flow, screenshots, all viewport checks, zero fixture mismatches.
- **Native 200% zoom** (`scripts/qa-native-zoom.mjs`, CDP Ctrl+Plus ×5 after Ctrl+0, `devicePixelRatio` 2.0, CSS viewport 720×500 — not CSS zoom): no page-level horizontal overflow on positions or transactions; after normal scrolling clears the (taller at 200%) fixed app bar, every toolbar control (Year, Search, View, Columns, Rows) and the primary/secondary/overflow actions plus row delete buttons are `elementFromPoint`-hittable; glossary triggers remain focusable; caption still present. Zoom reset verified (`dpr` 1).
- **Screen-reader pass: not performed.** No assistive-technology tooling (NVDA/JAWS/VoiceOver) is available in this execution environment, and DOM-level associations are not a substitute for a screen-reader audit; D8 owns the real pass.

### Screenshots (synthetic fixtures)

| File | Content |
|---|---|
| `assets/frontend-workspace/d4-open-overview-desktop.png` | Open Positions, Overview, 1440×1000 |
| `assets/frontend-workspace/d4-open-ledger-desktop.png` | Open Positions, Full ledger (two-tier headers, pinned identity), 1440×1000 |
| `assets/frontend-workspace/d4-open-overview-mobile.png` | Open Positions, Overview, 390×844 |
| `assets/frontend-workspace/d4-closed-comparison-desktop.png` | Closed Positions, Entry & exit, 1440×1000 |
| `assets/frontend-workspace/d4-closed-overview-mobile.png` | Closed Positions, Overview, 390×844 |
| `assets/frontend-workspace/d4-columns-mobile.png` | Grouped Columns chooser open, 390×844 |
| `assets/frontend-workspace/d4-transaction-confirmation.png` | Identified delete confirmation, 1440×1000 |

ductions

```text
cd frontend
npm run test:browser -- --case d4        # full rendered flow + captures
node scripts/qa-preview.mjs              # manual review against static dense fixtures
# native 200% zoom (dpr self-verifying):
node scripts/qa-native-zoom.mjs "$(npx --no-install agent-browser --session d4zoom get cdp-url)" http://127.0.0.1:5189 200
```

## PR #51 review round (2 October 2026)

Six reviewer findings corrected, each with a regression (12 new tests, 8 observed RED first):

1. **Delayed DELETE outcomes are generation/session-guarded** — `deleteTransactionConfirm` captures the dialog generation and auth epoch when the request is issued; a success or rejection that resolves after either changed no longer closes, refreshes or surfaces an error for state it no longer owns.
2. **Detail subjects use the actual detail-API currency fields** — list rows carry `cur`/`from_cur`/`to_cur`, but the detail endpoints return the serializer fields; the regular mapping now reads `currency` and the FX mapping `from_currency`/`to_currency`/`commission_currency` (commission keeps its own currency). All browser/unit fixtures were reshaped to the real serializer wire contract.
3. **Accessibility/pinning initialize on first render** — the caption, the named focusable scroll region and the measured pin offset are applied the moment the table appears after its loading skeleton, not only after a view change.
4. **Cash/TOTAL footer rows share the base row's cell semantics** — the tfoot-extra slot now exposes a per-leaf binding helper and the Open page applies it, so every Cash/TOTAL cell carries the same `headers` association, leaf identity and key-based pin class as the totals cell above it.
5. **Delayed form fields focus when ready, with close cancellation** — both transaction forms focus the first input when a slow form structure finally renders; a dialog closed in the meantime cancels the focus (no stealing from the restored invoker).
6. **D4 screenshot session is registered for guaranteed cleanup** — the capture session joins the harness sessions map before the capture, so `cleanupBrowserHarness` closes it even when the capture throws.

Gates after the round (actual exit codes): unit 366 passed (0), both type-checks (0), lint 0 errors / 35 warnings (0), api:types (0), build (0), `--case d4` green (0) with the slow-detail subject now asserting `498.25 EUR` — the detail payload's own serializer currency — full browser matrix green (0), backend pytest 1386 passed / 10 skipped (0).

### Second review round (2 October 2026)

Two follow-up corrections, each with regressions observed RED against the unfixed code:

7. **DELETE busy cleanup follows request ownership** — `closeDeleteDialog` now also releases the busy lock (a closed dialog can never hold a future confirmation disabled), and the confirm handler's `finally` clears `deleteBusy` only when the request still owns the current dialog generation/session. Regression: DELETE A issued, session ends, a fresh session opens DELETE B on another subject, and A settles in between — B's confirmation stays disabled until B itself settles and closes its own dialog (the unguarded `finally` re-enables it; verified RED, then GREEN).
8. **Delayed form focus is unmount-cancellable and scoped to its owning dialog** — the first-field focus poll runs under a cancellation token (bumped on reopen and on component unmount) and its target query is scoped to the overlay containing that dialog's own title id, so a concurrently open sibling dialog can never receive the focus. Regressions: a form unmounted before its structure arrives leaves another dialog's focused field untouched; a late structure focuses the form's own overlay even when a sibling's overlay precedes it in DOM order (both RED, then GREEN).

Gates after the round (actual exit codes): unit 369 passed (0), both type-checks (0), lint 0 errors / 35 warnings (0), api:types (0), build (0), `--case d4` green (0), full browser matrix green (0), backend pytest 1386 passed / 10 skipped (0).

### Third review round (2 October 2026): focus lifecycle

The remaining focus-lifecycle defect in both transaction forms is closed:

9. **Permanent disposal + instance-scoped focus target** — the delayed first-field focus now checks a permanent `focusDisposed` guard set in `onUnmounted` (a late structure response can no longer *start* focus work after unmount; the token only cancelled already-running polls, and its entry bump let new calls self-validate), and the focus target is looked up inside this instance's own card element, identified by a per-instance id derived from Vue's component `uid` (a template ref proved unreliable inside teleported overlay content). A replacement dialog of the same type can therefore never be matched. Regressions for BOTH forms: open with a delayed structure, unmount, mount the same form type, focus its second field, resolve the OLD response — focus must remain unchanged (observed RED: the dead instance stole focus into the replacement's first field; GREEN after the fix). The DELETE request-ownership fix from the previous round is untouched and still green.

Gates after the round (actual exit codes): unit 371 passed (0), both type-checks (0), lint 0 errors / 35 warnings (0), api:types (0), build (0), `--case d4` green (0), full browser matrix green (0), backend pytest 1386 passed / 10 skipped (0).

## Deliberate decisions and limits (D4)

- **Reporting-money labels:** money leaves' descriptions resolve the committed currency ("in your reporting currency (USD/EUR)"); instrument prices stay "in the security's trading currency" with the bond percent-of-nominal note and never follow the reporting currency. Row values keep arriving as backend-formatted strings (mixed local symbols under the "prefer security currency" setting) - displayed verbatim, never parsed.
- **Pre-existing Save-button recovery gap, minimally fixed:** after a server field rejection the Save button stayed disabled because manual setFieldValue never revalidated the field; the D4 correction revalidates on change (regular) / clears that field's error (FX) using the SAME Yup schema and payload shapes. Validation rules themselves are untouched.
- **Summary tables, dashboard, C2/C3/C4 pies:** untouched (D5/C2-C4 scope).
- **Third-tier nesting:** none anywhere - wrapping a header label over two text lines is allowed, structural rows never exceed two.
- **Screen-reader audit:** unavailable in this environment (recorded above); DOM/ARIA structure is verified and honest about that limit.

# C2 — typed chart adapters and shared request lifecycle

## What shipped (2 October 2026, branch `codex/chart-adapters-c2`)

A validated, exact chart-v2 boundary behind the incumbent dashboard NAV chart, ready for the separate C3 renderer pilot:

- **`src/features/charts/contracts.ts`** — the C1 wire contract as handwritten types (the generated `api.d.ts` does not describe `chartV2`): ChartDocument/ChartValue/ChartPeriod/ChartSeries/ChartUnit/ChartErrorBody plus NavQuery/ReadyChartContext/LegacyNav/NavResult. Decimal strings stay strings end to end.
- **`parseChartEnvelope.ts` / `adaptLegacyNav.ts`** — pure runtime validation from `unknown`: unique server-issued series/period identity, UTC-round-tripped calendar ISO dates, fixed-notation decimal strings (`NaN`/`Infinity`/exponent/numeric v2 values rejected), status/reason/enum shapes, ok⇒strings & non-ok⇒nulls, `knownSubtotal` only for partial, point/totals lengths, both IRR series for nav, interval end = period end with inception null-start, allocation documents (complete unique series references, ascending ranks, reporting-money summary, eligible claims require complete partition and ok contributions — arithmetic certification stays backend-owned) and price/position documents (security identity required; bond `98.500000` percent_of_nominal and instrument money currency distinct from reporting currency). The legacy adapter preserves styling/extra fields (`empty`, stack, datalabels) and `N/A`/`N/R` markers, never inventing identity or dates; HTTP 200 without `chartV2` is `legacy_only`, a present-but-invalid `chartV2` is a contract error, never a downgrade.
- **`chartApi.ts`** — one GET with `chart_contract=2` via the shared injected transport (auth interceptors and AbortSignal preserved; no `api.ts`/`axiosConfig` import, enforced by mocking tests); C1 400/500 nested error envelopes mapped to `ChartApiError` (code/status/retryable); `ChartContextMismatchError` for local disagreement of accountSelection/currency/digits and `effectiveDate ≠ query.toDate` — historical ranges stay valid because the backend binds `effectiveDate` to the chart's `dateTo`, not the committed effective date; `accountIds` shape-checked only, membership never reconstructed. Exactly one network request in every failure case.
- **`useNavChart.ts`** — reuses `usePortfolioRequest(fetchNavChart, snapshotNavQuery)` (no second request manager/watcher/generation counter); `snapshotNavQuery` detached-clones and recursively freezes the query; a mismatch may call the existing store's `reconcileContext` only while it is still the runner's current error, the captured revision matches, the scope is live and the store can read — and **at most once per divergence episode** (suppression lifted only by an accepted result), which the rendered run proved necessary: the first implementation reconciled → refreshed → mismatched → reconciled… against a still-disagreeing server (5316 fixture requests before the guard).
- **DashboardPage** — NAV wiring swapped to the boundary (`NavChartParams` → `NavQuery` mapping with runtime mode/frequency guards; `dateTo` falls back to the committed effective date exactly as the backend treats an absent end date); NAVChart receives a fresh `structuredClone` of the validated legacy payload so renderer-side dataset mutation cannot touch the retained `NavResult`; concise `legacy_only` capability notice only (`data-testid="nav-capability-notice"`); the single dashboard refresh watcher and child parameter-event ownership are unchanged; `getNAVChartData` stays in `services/api.ts` for remaining callers.

## Rendered evidence

`npm run test:browser -- --case charts-c2` (desktop flow + mobile pass, both captures under `tests/browser/artifacts/screenshots/charts-c2-*.png` — synthetic data only): v2 negotiation renders Chart.js with no notice; legacy-only shows the notice and still renders; malformed v2 errors with **exactly one** request (no legacy retry); manual retry restores; a parameter change issues one request and the mounted chart element survives; a current mismatch reconciles once, stays bounded (no loop), and recovers via the user's retry; a stale held mismatch released after a newer query neither errors nor re-requests; mobile 390×844 keeps the chart and the frequency control genuinely hittable (elementFromPoint hit-test, per the D3 toolbar lesson). The default browser nav fixture now serves the full C1 `chartV2` document, so the whole 72-profile matrix exercises the typed boundary.

## Deviations from the handoff wording (recorded for review)

1. **Feature tsconfig lives at `frontend/tsconfig.charts.json`, not `src/features/charts/tsconfig.json`** — a nested tsconfig broke Vite 8's alias resolution for `@/services/*` imports inside feature tests (empirically isolated; alias imports failed only while the nested file existed). Root placement follows the `tsconfig.reliability.json` precedent; script target updated.
2. **`dashboardIntegration.spec.ts` is excluded from the strict charts check** (it remains covered by the main `type-check`): importing DashboardPage pulls the entire legacy app graph into the strict closure, and strict-fixing 218 pre-existing `api.ts` errors is not C2 scope. The strict check still covers the whole feature boundary (contracts, parser, adapter, transport, lifecycle, fixtures).
3. **Legacy dataset `type` is validated-when-present rather than required** — merged incumbent fixtures (e.g. `DashboardPage.requests.spec`) prove real servers omit it; the plan's literal `type: 'bar' | 'line'` would reject renderable payloads.

## Gates (executor machine, portable Node v24.20.0; actual exit codes)

Baseline on merged D4 head `297fb95c` before implementation: unit 65 files/371 passed (0), lint 0 errors/35 warnings (0), type-check/type-check:reliability/api:types (0). Final: focused charts 95 passed (0); `test:unit` 69 files/**466 passed** (0); `type-check:charts` (0); `type-check` (0); `type-check:reliability` (0); `lint` 0 errors/35 warnings (0); `api:types:check` (0); `build` (0); `--case charts-c2` (0); full browser matrix **72 route profiles**, 756 fixture requests, zero mismatches (0); backend `uv run python -m pytest` **1386 passed/10 skipped**, coverage 83.25% (0). Affected focused cases: `recovery` (0), `context` (0); `requests` and `dates` fail **identically on the pristine baseline** `15533ba0` (verified in a clean worktree) — inherited D4-era harness staleness (selectors reference the pre-D4 toolbar markup; D4's gates ran the full matrix + `d4` only), reported here rather than silently patched outside C2 scope.

## Deliberate decisions and limits (C2)

- Chart.js remains the only renderer; the validated `document` is retained for C3 but nothing renders it yet. No ECharts dependency, options or pie rollout (C4), no security/allocation transport migration, no backend change.
- `legacy_only` results skip the captured-context check by construction (nothing certified to compare); the capability notice states that plainly instead of pretending v2 validation occurred.
- Reconciliation is deliberately conservative: one attempt per divergence episode, lifted only by an accepted result — a persistently disagreeing server leaves the error visible for manual retry instead of looping.

## PR #52 review round (2 October 2026): empty security documents and error sanitization

Both findings corrected with regressions observed RED against the unfixed code:

1. **Actual C1 empty price/position documents are accepted with their identified empty series** — the backend's `build_security_price/position_document` always emits the series (`points: []`, `periods: []`, `outcome: 'empty'`); the Task-2 rule "an empty document must not carry series" rejected that real output. The empty rule is now kind-aware: price/position empties keep any identified series (each necessarily zero-point through the points/periods length check), while nav and allocation empties still carry no series (matching their backend branches) and only allocation keeps its sampling period. The empty-security fixtures were corrected to the backend shape, regressions cover both history kinds and pin the still-rejected empty-nav-with-series case.
2. **Nested C1 error messages/codes keep the shared sanitization** — `ChartApiError` and `ChartContextMismatchError` now extend `ApiError`, so every message/code passes the shared sanitizing constructor (`safeText`) instead of raw pass-through of a server-controlled nested `error.message`. Regressions feed credential-bearing nested messages (JWT bearer token; `Authorization: Bearer` header) and assert the leak is redacted while `code`/`status`/`retryable` metadata is preserved; ordinary C1 messages still pass verbatim.

Gates after the round (actual exit codes): focused charts 97 (0), `test:unit` 69 files/468 (0), `type-check:charts`/`type-check`/`type-check:reliability` (0), `lint` 0 errors/35 warnings (0), `api:types:check` (0), `build` (0), `--case charts-c2` (0), full browser matrix 72 profiles/zero mismatches (0), backend pytest 1386 passed/10 skipped (0). The inherited D4-era `requests`/`dates` selector failures remain documented above and in the tracker, untouched by this round.

# C3 — gated ECharts NAV pilot

## What shipped (2–3 October 2026, branch `codex/nav-echarts-pilot-c3`)

An opt-in, lazily delivered ECharts renderer for the validated NAV document with accessible exact-value inspection, behind `VITE_NAV_ECHARTS_ENABLED` (default off; only the exact string `true` opts in; no repository default enables it). Chart.js remains the default and rollback renderer; all financial semantics and C2 request handling are unchanged.

- **Task 0 (bounded test-only repair, closure of the inherited D4 follow-up):** `requests.mjs` matches each route's current accessible search label exactly ('Search' on FX, 'Search transactions' on transactions); `dates.mjs` opens Year through the D4 toolbar (`.workspace-table-toolbar .positions-year-select`). Both failed identically on pristine `15533ba0` before the change and pass after, with held-old/new-accepted ordering and the single-YTD-query/range assertions intact. No application code touched.
- **Pure boundary:** `renderBoundary.toPlotNumber` is the sole decimal-string→number conversion (null for non-ok even with knownSubtotal; RangeError for nonfinite, e.g. a 400-digit plotValue); `buildNavOption` maps server period keys to a category axis (displayLabel formatter), bars stack `nav` on axis 0, both raw-ratio IRRs unstacked on axis 1 with `connectNulls:false`, hidden series excluded, dataZoom window view-only; `seriesStyles` colors by djb2 hash of the server id (insertions never recolor survivors) with fixed distinct solid/dashed IRR styles; `interaction.ts` owns visibility/viewport/inspection plus `reconcileInteraction` (surviving ids keep state, new ids appear visible, invalid viewport/inspection cleared).
- **Accessibility:** native `aria-pressed` legend buttons keyed by server ids with the two exact control names `Since-inception IRR (annualized)` / `Interval IRR (annualized)`; exact-value table (caption, scoped headers, sticky period identity, tabular right-aligned values, every series column, status+reason+knownSubtotal for unavailable points, partial-calendar markers, and a `Portfolio NAV (all categories)` column sourced only from `document.totals` regardless of hidden categories); shared inspection panel (one inspectedPeriodKey for pointer/table/keyboard; actual units and horizons — first interval is inception; native start/end period selects with ordered-key validation and Reset zoom). Text interpolation only — an HTML-looking series name stays inert.
- **Renderer lifecycle:** `rendererPolicy.resolveRenderer` allows ECharts only for validated v2 results; `ChartHost` lazily imports `EChartsNav` (defineAsyncComponent; the module registers only bar/line, grid, tooltip+axis-pointer, dataZoom, ARIA and the canvas renderer; vue-echarts owns init/disposal; `notMerge` updates so hidden/stale series never merge back; owned ResizeObserver/window-resize fallback cleanup; aria-busy overlay keeps the chart mounted during same-context refresh). Option-construction/render failures are recoverable: explicit Retry and an explicit user-chosen "Use previous chart" backed by the same accepted result — never an empty-success chart, and never a second API request.
- **Panel integration:** `NavChartPanel` wraps the incumbent `NAVChart`, which gained a named `chart` slot around its complete plot/no-data body (default content unchanged, controls single-owned). The slot is supplied only when policy selects ECharts; a v2 empty document shows the no-data notice instead of an empty canvas; a user fallback removes the slot and shows the incumbent body plus a clear notice; the incumbent renderer receives a fresh `toRaw`-detached legacy copy (`structuredClone` chokes on Vue prop proxies — found by test). DashboardPage passes the C2 NavResult/loading/error/parameter events through with its sole refresh watcher and retry ownership unchanged; interaction is preserved only across same-context changes and reset on invalidation.
- **Harness:** isolated `__tests__/render` page (no production router imports) with mode/frequency/legacy-only/empty/invalid-contract/loading controls over explicit synthetic fixtures.

## Dependencies (recorded decisions)

`echarts@6.1.0` (Apache-2.0) and `vue-echarts@8.3.1` (MIT) pinned exactly via `npm view` registry metadata checked 2 October 2026 against the installed runtime (vue 3.5.11 satisfies `^3.3.0`; echarts `^6.0.0` peer satisfied; no unrelated upgrades). All ECharts runtime imports live only inside the lazy `EChartsNav.vue` graph; `buildNavOption` imports types only.

## Rendered and delivery evidence

`--case charts-c3` (exit 0) over two distinct artifacts — the shared default-off build and its own `VITE_NAV_ECHARTS_ENABLED=true` build (never rebuilt silently as flag-off) — plus the isolated harness on a dedicated dev server:

- **Flag-off:** incumbent Chart.js canvas, no pilot artifacts, no capability notice, **no ECharts asset fetched and no ECharts module in the loaded graph** on the dashboard (a dormant lazy chunk in the build is allowed — it is never requested), nor on login.
- **Flag-on (dashboard):** pilot composition renders; independent IRR toggles (one hidden leaves the other and all bars); legend/zoom issue **zero** data requests; table-row focus/click inspects the period into the shared model; viewport selects + Reset zoom are view-only; a same-context parameter refresh issues exactly one request, keeps the chart element mounted (marker identity), keeps the hidden IRR hidden, and keeps partial/known-subtotal/N-A text explicit; mobile 390×844 keeps every control genuinely hittable (`scrollIntoView` + elementFromPoint); **native 200% zoom via CDP key events, devicePixelRatio 2 verified and reset verified**; an `outrange` plotValue produces a recoverable rendering failure whose "Use previous chart" fallback shows the incumbent canvas with a notice and **no extra request beyond its own query**; legacy-only shows the honest notice on the incumbent renderer; malformed v2 errors exactly once with no pilot and no retry; a current mismatch reconciles once (bounded episode) and manual retry recovers.
- **Isolated harness:** mounts the pilot from synthetic fixtures; empty and invalid-contract scenario buttons produce the empty-state notice and the error state.
- **Delivery measurements** (`tests/browser/artifacts/charts-c3-delivery.json`): flag-off dashboard **336,646 gzip bytes** JS/CSS — within the unchanged 401,000 budget; flag-on **529,275 gzip bytes**, the delta being one `EChartsNav` chunk of **192,511 gzip bytes** (+110 css). Fonts are excluded (helper measures JS/CSS only) and no render-timing claim is made — both limits recorded rather than papered over.
- **Captures** (synthetic data only): `docs/design/assets/frontend-workspace/c3-nav-{desktop,mobile,partial,keyboard,legacy}.png`. Functional verification used DOM/state/hit-test assertions; the captures are attached for human visual review, and a real screen-reader pass remains D8.

## RED/GREEN and gates (actual exit codes; portable Node v24.20.0)

Baseline on `bcee56d1`+Task 0 before implementation: unit 468 (0), lint 0/35 (0), all three type checks, api:types, build (0). Every task began with failing regressions: navOption.spec 22 (unresolved modules), navAccessibility.spec 13 (components stashed, unresolved imports; one genuine defect caught - missing reason text for unavailable values), navLifecycle.spec 12 (missing modules; then GREEN; the reactive-prop structuredClone and __esModule async-mock interop were real integration findings), navIntegration.spec 9 (7/9 RED without the wiring). Final matrix AS ORIGINALLY REPORTED (test:unit 524, type-checks, lint 0/35, api:types, build, full browser 72 profiles, all focused cases, delivery, backend 1386/10 — all 0) carried a defect: the type-check and lint results were produced on a working tree that contained fixes never included in the pushed `e034bed4`. Reproduced against the pushed commit, that head had 1 TS error (render/main.ts TS2769) and 8 new lint diagnostics — the earlier all-green type/lint claim was NOT reproducible at the commit under review and is retracted. The corrected matrix on the review-round head is below.


## PR #53 review round (3 October 2026): seven findings corrected

All seven findings fixed with regressions first (`navReview.spec.ts`, 9 cases observed RED 9/9 against `e034bed4`, then GREEN); the previously uncommitted TS2769 fix and all eight lint diagnostics are now committed, with no check weakened and no baseline expansion:

1. **Partial status/reason/knownSubtotal in inspection** — every series value line and the `Portfolio NAV (all categories)` line from `document.totals` append status, reason and labelled knownSubtotal; the review fixtures use ordinary currency display strings exactly as the backend emits them (partial-ness lives in status, not in decorated display text).
2. **Exact-display tooltips and labelled axes** — the default numeric tooltip is replaced by a formatter built from server displays + status/reason/knownSubtotal + unit labels (never plotted numbers); every server string is HTML-escaped because ECharts renders tooltip strings as markup (regression: an HTML-looking label renders as `&lt;img …`); the money axis is labelled with currency scaling (`USD thousands` derived from unit currency + plotDivisor) and the return axis as `%`.
3. **Per-IRR horizons, no "raw ratio"** — a shared `seriesControlName` helper names both controls consistently, each IRR line shows its own horizon (inception-to-endpoint vs the server-provided interval, inception semantics at the first sample), and ratio units read `annualized percentage`.
4. **Batched inside-zoom** — `datazoom` handling normalizes batched wheel/pinch events alongside flat slider events to the same server-key viewport.
5. **Panel initialization** — the interaction watch is `immediate`, so mounting with an existing accepted result initializes full visibility instead of an empty pilot.
6. **Harness Pinia** — the isolated harness installs Pinia (NAVChart needs the app store) and opens/renders independently in the browser run.
7. **Committed type/lint state** — `5ed7ec16` includes the TS2769 fix and the eight lint corrections (dead imports/helpers after the serve-app extraction; prefer-const); `2223ece9` adds the harness window-typing declaration. The d4 session-cleanup source assertion became CRLF-tolerant (same meaning; the working tree had been rewritten with CRLF by a stash cycle, which is also what had hidden the divergence between the working tree and the pushed commit).

**Retaken captures** (five genuinely distinct images, each scrolled so the chart, both IRRs and the relevant controls are in view): desktop (chart + legend + controls, both IRRs visible), partial (table + inspection showing `partial (missing_price); known subtotal 90000` text), keyboard (inspection panel focused), mobile 390x844 (chart area), legacy (incumbent renderer + notice). **Completed measurements** (report in `tests/browser/artifacts/charts-c3-delivery.json`): flag-off dashboard 336,829 gzip bytes / flag-on 529,965 (unchanged budgets); NAV API 13/11 ms (flag-off/flag-on, fixture server — local-loopback numbers, not production latency claims); domContentLoaded 229/340 ms; fonts 0/0 fetched (system font stack — none delivered); isolated-harness cold frontend render 589 ms (script evaluation to first painted pilot canvas, no API involved). Init-script-based page instrumentation was abandoned after proving unreliable (agent-browser re-executes `--init-script` per command and its window object was not reliably observable from page evals) — recorded so the method is not retried blindly.


## PR #53 review round 2 (3 October 2026): tick/tooltip semantics, responsive shrink, faithful formatting

Four review findings plus the formatting requirement, each with failing regressions first (units 533 -> 538):

1. **Return-axis ticks** — a presentation-only formatter labels raw ratios as percentages (0.05 -> `5%`, 0.1234 -> `12.34%`, -0.02 -> `-2%`, 0 -> `0%`); plotted values and the validated document are asserted unchanged. RED -> GREEN.
2. **Tooltip units** — axis and value unit labels are now separate: exact amounts carry their stated currency only (`USD 100,000.00`), and the `thousands` plotting-scale label exists solely on the scaled money axis. RED -> GREEN.
3. **Tooltip horizons** — tooltip IRR lines use the shared annualized control names with per-series horizons (inception-to-endpoint vs the server-provided interval; the horizon helper moved to `interaction.ts` and is shared with the inspection panel so the two surfaces cannot drift). RED -> GREEN.
4. **Responsive shrink** — desktop->390px previously pinned a **974px child inside a 324px panel**, clipping the interval-IRR control; a `min-width: 0 / max-width: 100%` chain through the pilot grid and renderer wrapper fixes it. The browser case now asserts, after desktop->390 AND after restoring 390->desktop, that EVERY legend control sits inside the panel, the canvas resizes with it, the viewport controls fit, and visibility state survives. RED observed pre-fix with exactly the review's geometry (`widest 974px vs panel 324px`); GREEN post-fix.
5. **Thousands separators** — traced: the screenshot defect came from the **browser fixtures** (`$80200.00`), not server formatting or rendering; the app renders server display strings verbatim. The fixtures now generate comma-grouped, signed-parenthesized displays like the real backend `currency_format` output, and new formatting regressions pin verbatim rendering for `USD 10,000.00`, `(USD 1,234,567,890.12)`, zero, 4-dp precision, partial `known subtotal 9007199254740993.123456789` and a 32-significant-digit display beyond Number's safe range — no parsing, no Number conversion, no backend presentation change needed. (These verbatim tests passed immediately against existing rendering, which is itself the finding: the renderer was already exact; only fixtures were unfaithful.)

Gates after the round (actual exit codes, committed head `f6892bf8`): `test:unit` 538 (0; one transient icons-inventory timeout on the first run, clean on immediate rerun and in every focused run) · type-checks x3 (0) · lint 0/35 (0) · api:types (0) · build (0) · full `test:browser` 72 profiles (0) · all focused cases incl. both-flag charts-c3 with resize transitions and native 200% zoom (0) · `test:delivery` (0) · backend 1386/10 (0). Fresh captures retaken with formatted fixtures; the partial capture now shows comma-grouped monthly NAV values, and the browser case asserts `\d,\d{3}` appears in the rendered table before capturing.

## Deliberate decisions, deviations and limits

- **Strict-check scoping:** tsconfig.charts.json keeps every pure/renderer feature module strict; NavChartPanel.vue, the two dashboard integration specs and the dev harness are excluded because they compose/mount the legacy app graph (the C2 precedent) - they remain covered by the main type-check. No exclusion was added for pure code.
- **Delivery interpretation:** "no ECharts in the module graph" is asserted over *fetched* assets and *loaded* modules; the default-off build does contain a never-requested dormant lazy chunk.
- **Renderer-copy cloning:** structuredClone(toRaw(...)) because prop reactivity wraps the result; the retained validated NavResult stays immune to Chart.js-side mutation (regression-pinned since C2).
- **Reconciliation:** C2's once-per-episode mismatch suppression is untouched and regression-pinned in navIntegration.
- **Unmet acceptance / not in scope:** approval of this pilot does **not** authorize default-on rollout (C5), the three solid allocation pies or security charts (C4), main merge or deployment; a real screen-reader audit (D8) and true render-timing measurements were not performed; the screenshots' visual review is the reviewer's.
