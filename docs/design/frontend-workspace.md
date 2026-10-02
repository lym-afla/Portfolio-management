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

## Deliberate decisions and limits (D4)

- **Reporting-money labels:** money leaves' descriptions resolve the committed currency ("in your reporting currency (USD/EUR)"); instrument prices stay "in the security's trading currency" with the bond percent-of-nominal note and never follow the reporting currency. Row values keep arriving as backend-formatted strings (mixed local symbols under the "prefer security currency" setting) - displayed verbatim, never parsed.
- **Pre-existing Save-button recovery gap, minimally fixed:** after a server field rejection the Save button stayed disabled because manual setFieldValue never revalidated the field; the D4 correction revalidates on change (regular) / clears that field's error (FX) using the SAME Yup schema and payload shapes. Validation rules themselves are untouched.
- **Summary tables, dashboard, C2/C3/C4 pies:** untouched (D5/C2-C4 scope).
- **Third-tier nesting:** none anywhere - wrapping a header label over two text lines is allowed, structural rows never exceed two.
- **Screen-reader audit:** unavailable in this environment (recorded above); DOM/ARIA structure is verified and honest about that limit.
