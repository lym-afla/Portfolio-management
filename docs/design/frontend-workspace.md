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
