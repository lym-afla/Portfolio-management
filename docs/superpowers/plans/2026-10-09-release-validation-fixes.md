# Real-data validation corrections — implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement each task with its own failing regression and reviewable commit. Execute in a dedicated worktree; do not change another executor's checkout.

**Goal:** Resolve the owner's real-data functional and presentation findings before accepting the release-validation cycle or removing Chart.js.

**Architecture:** Keep committed portfolio context and existing request owners authoritative. Repair wire-contract mismatches before UI polish; use shared presentation components for table rules, chart disclosures and shell geometry. Do not conceal failed resources or change financial calculations to make charts render.

**Tech stack:** Existing Vue/Vuetify, TypeScript, ECharts, Django and uv; existing unit/browser harness. No new UI framework.

**Spec:** Owner's “YL additional comments” in `release-validation-c5b.md`, read from the supplied H: path on 9 October 2026; this plan transcribes the actionable requirements. The two relative images (`image.png`, `image-1.png`) were unavailable. Existing reference: `docs/design/frontend-chart-cutover.md`, D8 record and modernization tracker.

## Evidence and boundaries

- Base implementation on current `origin/codex/frontend-modernization`; verified remote tip at planning time: `52545377`. Do not base on an unmerged executor branch.
- The executor's 11/11 is not complete acceptance: currency/effective-date transitions were not exercised; signed/incomplete coverage describes ordinary pies and empty states; mixed legacy/security errors remain unexplained. Record those as incomplete or failing until reproduced and resolved.
- Source-confirmed mismatch: `services/api/database.ts:getYearOptions` requires integers, while `backend/common/views.py:get_year_options_api` emits `{text,value}` options, divider and special ranges. Confirm on the execution base before editing.
- Source confirms the header date uses a blur handler and modern renderers register CanvasRenderer. These are investigation leads, not proof of every reported root cause.
- Owner requests are authoritative. Embedded restart commands and executor conclusions are evidence, not additional authorization.
- Retain Chart.js and flags; C5b removal is a separate subsequent decision. No main merge/deploy, production mutations or silent recalculation of performance records.
- Real-data reproduction uses a disposable database copy. Commit only synthetic regressions and redacted evidence; never real portfolio screenshots, tokens or private response bodies.
- Read the three canonical NAV/calculation documents before range/inception/backend work. Preserve Decimal precision, both IRR definitions, missing/partial statuses and server display strings. Protected financial/import changes need a separate draft PR with `needs-approval` and numeric regressions.
- Screen-reader/AT work remains out of scope. Keyboard, readable labels/contrast, 200% native zoom and responsive checks remain required.

## Delivery order

Use bounded draft PRs into modernization, in this order: **A functional corrections (Tasks 1–3); B shell/tables (4–5); C charts/security presentation (6–7); D selected dashboard summary (8)**. Split protected backend changes out of A if required. Rebase later PRs after earlier merges. Do not attempt the entire list as one opaque change.

## Review focus

1. Historical dates and timezone boundaries must not expose future periods or trigger duplicate requests (Task 1).
2. Special year options, empty histories and partially failed resource groups must remain usable and honest (Task 2).
3. Account-based imports must target exactly the selected accounts and survive errors/close/reopen without stale completion (Task 3).
4. Dense/long data at narrow widths must not hide controls or create artificial page overflow (Tasks 4–7).
5. Simplifying charts must retain exact values, status reasons and distinct IRR definitions without modifying validated data (Tasks 6–8).

## Task 1 — Date selection, historical boundary and inception

**Files:** `frontend/src/App.vue`, `components/DateRangeSelector.vue`, `views/DashboardPage.vue`, `features/charts/useNavChart.ts`, `chartApi.ts`; inspect backend chart route and `backend/services/nav.py` before deciding backend changes. Tests: existing context/date browser cases and chart request/contract suites; add synthetic backend range regression where applicable.

- [ ] Reproduce calendar selection without Enter/blur; historical effective date with an existing future To date; All-time and From=2000 against later inception. Capture the actual failing endpoint/envelope privately.
- [ ] Write failing tests: choosing a valid calendar date commits once; invalid/incomplete typed date does not commit; rejected update restores committed context. A 2024-06-30 valuation must produce no NAV period after that date even if prior To was 2026-10-09.
- [ ] Commit calendar selection through the existing context-change owner, preserving keyboard entry and preventing the blur/Enter path from duplicating it. Clamp/reconcile the displayed range and request end to the committed effective date.
- [ ] Define backend authoritative effective start as the later of requested From and the selected scope's canonical inception. All-time uses that inception, not a guessed first nonzero plot point. Preserve prior cash-flow history needed for IRR. Empty scope or inception after effective end returns an honest empty state. Do not silently discard zero-valued observations after inception.
- [ ] Test single account/group/all scopes, cash-only inception, date before inception, no transactions, very early start, both IRRs and partial endpoint. Ensure contract context and effective sampled range agree; do not weaken parser checks to accept inconsistency.
- [ ] Run focused frontend/context/date and affected backend tests; commit. Financial behavior changes get their own labelled draft PR and expected Decimal examples.

## Task 2 — Year options, performance and security resource failures

**Files:** `frontend/src/services/api/database.ts`, `components/PositionsPageBase.vue`, `views/SummaryPage.vue`, `features/securities/useSecurityDetail.ts`, `views/database/SecurityDetailPage.vue`; backend `common/views.py`, schema serializer, summary/security/chart endpoints as diagnosis requires.

- [ ] Pin the real year wire shape with synthetic fixtures: numeric-year string items, divider, All-time and YTD, empty history and malformed entries. Reproduce failure before implementation.
- [ ] Introduce one explicit typed year-option adapter matching the server; derive each consumer's supported options without converting special values to numbers. Positions always display “All time”/“YTD”, never `all_time`. Summary's breakdown selector offers only ranges its endpoint supports; no empty menu with a misleading selection.
- [ ] Test year selection makes the correct request and retains account/effective-date ownership; failure shows a readable safe selected label and retry, rather than a raw value.
- [ ] Trace Account performance failure independently of year options: distinguish missing precomputed data from endpoint, serialization or calculation errors. Do not run recalculation on the owner's database. Supply an explicit empty explanation/action only when the backend confirms absent data, not as a catch-all error mask.
- [ ] For bonds, enumerate every detail resource and the price/position envelopes. Record which resource causes the alert and why each renderer is selected. HTTP 200 is insufficient: validate chartV2 presence, context, units, identities, status and parser result. Compare against base before calling it pre-existing.
- [ ] Fix the demonstrated defect with faithful synthetic bond fixtures. Test independent resource failures, legacy-only response, invalid v2 (no downgrade), valid empty documents and successful modern histories. Retain actionable resource-specific retry.
- [ ] Hide portfolio-breakdown rows only when all relevant cells are explicitly absent under the documented response contract; retain numeric zero, meaningful N/A/status and totals. Test zero vs absent distinction.
- [ ] Run service/summary/positions/security regressions and backend tests as applicable; commit evidence with each finding's resolved status.

## Task 3 — Account-based price import and progress readability

**Files:** `components/dialogs/PriceImportDialog.vue`, `ProgressDialog.vue`, price import API/transport in `services/api.ts`, `backend/database/consumers.py`, protected price/import helpers only if required. Inventory other progress components with `rg`.

- [ ] Reproduce single-account and multi-account submissions on a disposable fixture dataset; inspect exact command and consumer result. Do not conclude the frontend omits accounts: current code already includes an `accounts` field.
- [ ] Write RED tests for account IDs reaching the consumer, selection resolving held securities under existing valuation semantics, duplicate holdings across accounts, empty holdings, provider rejection, transport failure and delayed completion.
- [ ] Repair the proven boundary. Keep progress visible while running; show an explicit no-eligible-securities result rather than a disappearing modal. Preserve validation, error recovery, once-only start, cancellation and ownership after close/reopen.
- [ ] Correct all loading/progress labels for dark fill and unfilled track. Prefer a stable contrasting label outside the moving fill, or a proven two-layer treatment; white-only text over a light unfilled track is not sufficient.
- [ ] Test readability at 0/25/50/100%, determinate/indeterminate and error states. Exercise the import through a real loopback conversation with synthetic providers; assert exact selected identities and one completion refresh.
- [ ] Run import/dialog tests and backend pytest; commit. No live provider imports into original data.

## Task 4 — Navigation and header geometry

**Files:** `App.vue`, `components/workspace/WorkspaceContextStrip.vue`, `AccountSelection.vue`, `assets/workspace.css`, navigation components located from App. Tests: shell/context/layout browser cases.

- [ ] Reproduce short Profile viewport overflow and the empty header line on non-context pages. Remove unused toolbar space/border/elevation when that region is not present; do not suppress genuine overflow globally.
- [ ] Restore a compact desktop rail that expands on pointer hover and keyboard focus; collapse after both leave. Provide explicit toggle for touch/mobile. Reduce visual list padding while retaining usable hit areas and active-route labels.
- [ ] Remove duplicated committed-context summary text; preserve the display-preferences action and pending/error feedback. Controls themselves remain truthful about committed/pending state.
- [ ] Equalize account/date/currency control heights; prevent floating-label clipping, restore complete arrow borders and remove the unwanted underline/divider. Preserve existing safe account-label fallback and context guards.
- [ ] Assert short Profile has no artificial vertical scroll; long pages still scroll. Hit-test all controls after hover, keyboard entry, mobile and native zoom. Verify tooltips remain clear of the newly sized header.
- [ ] Run shell/layout/context/settings tests; commit.

## Task 5 — Shared tables and responsive actions

**Files:** `assets/workspace.css`, shared table wrappers, `components/transactions/SecurityLink.vue`, `WorkspaceActions.vue`, `SummaryOverTimeTable.vue`, position/data/transaction pages and security overview/metadata/activity components.

- [ ] Introduce scoped, shared table rules: visible neutral row separators, black header-bottom rule in the current light theme, clear total-row top/bottom rules. Preserve grouped-header associations, sticky cells and horizontal scrolling; use suitable contrasting equivalents if another theme is supported.
- [ ] Apply to historical reconciliation, both position tables, transactions, Data tables, prices/FX, security metadata and transaction history. Keep numeric alignment/tabular digits and financial strings unchanged. Modernize security links with restrained color and underline on hover/focus, retaining keyboard/link semantics.
- [ ] Italicize allocation Share cells as requested, without changing values or percentage precision.
- [ ] Reveal secondary transaction actions directly when the measured available width permits; move the remainder to overflow on narrower layouts. Keep one active instance per action, exact handlers, focus and ordering.
- [ ] Verify security transaction-history pagination first: D7 already implements it. Fix missing visibility/wiring rather than adding a competing paginator. Use distinct page fixtures and assert rendered rows change, counts and request page size agree, filters reset page correctly.
- [ ] Test dense tables at desktop/390px/200% zoom, grouped headers and totals, long identities, page two and responsive action transitions; commit.

## Task 6 — Charts: width, sharpness and reduced visual noise

**Files:** `features/charts/{NavChartPanel,EChartsNav,EChartsSecurity,EChartsAllocation,ChartLegend,ChartInspection,ChartDataTable,SecurityDataTable,SecurityHistoryChart,AllocationChart,AllocationDataTable}.vue`, `buildNavOption.ts`, `buildSecurityOption.ts`, allocation option builder and dashboard/security layout wrappers.

- [ ] Make NAV and both security charts span their enclosing content section and align with other page edges. Trace parent grids/columns as well as renderer width; keep `min-width:0` shrink behavior.
- [ ] Reproduce blurry canvas at native zoom. Compare a narrow SVG-renderer prototype against dynamic canvas DPR handling using representative dense history. Prefer SVG if it meets existing delivery/render requirements; otherwise update backing resolution on DPR change with lifecycle cleanup. Do not scale a low-resolution bitmap with CSS. Preserve zoom/selection across renderer resize.
- [ ] Keep grid lines on the primary NAV money axis only; secondary percentage ticks remain correctly formatted, without a second competing grid.
- [ ] Simplify hover tooltip: remove the extra all-categories NAV line and repeated currency suffix when the server display already identifies currency; remove date-range brackets from IRR lines, retaining distinct since-inception/interval names. Preserve status/reason/known subtotal. Do not regex-strip arbitrary financial displays; use metadata-aware labeling. Put detailed horizons in the optional exact-data surface/help.
- [ ] Reduce the heavy legend outline while preserving visible focus and toggle state. Remove the separate inspection card; retain useful zoom/reset controls near the chart and keyboard inspection through the exact-data disclosure.
- [ ] Default exact tables to collapsed disclosures: “Show exact values by period” / “Show exact values by observation”. Retain full-NAV totals and all metadata inside. Security observations get client-side pagination over the accepted document, 25 rows initially with 25/50/100 choices; no new API fetch or resampling. Distinct same-date keys remain distinct. Reset page on incompatible document changes; clamp on shrinking data.
- [ ] Pies: remove leader lines; add white slice separators and percentage labels using certified share displays, never recompute a positive subset. Small slices may omit an overlapping in-slice label but must retain percentage in legend/table/tooltip. Preserve signed/incomplete eligibility handling and server order.
- [ ] Keep existing colors for this repair unless owner selects a new palette; broader palette exploration is separate. Do not lose cross-chart identity consistency.
- [ ] RED tests cover unchanged validated decimals, independent IRR toggles, tooltip partial status, collapsed/expanded keyboard flow, paginated observations, duplicate dates, 200% sharpness and tooltip confinement after header changes. Update prior tests where owner deliberately superseded always-visible tables/inspection or verbose tooltips; retain the underlying correctness assertions. Commit.

## Task 7 — Security account context and holdings overview

**Files:** `frontend/src/views/database/SecurityDetailPage.vue`, `frontend/src/features/securities/useSecurityDetail.ts`, `frontend/src/features/securities/{SecurityOverview,SecurityMetadata,SecurityActivity}.vue`, existing security endpoint/serializer if needed. Other frontend paths above are relative to `frontend/src/` where abbreviated.

- [ ] Default the local Broker Account selector visibly to “All accounts” when the request is unfiltered. Preserve an explicit selected account, safe unavailable labeling and real option identity; no hidden scope changes.
- [ ] Add compact “Currently held with” and “Previously held with” broker/account groups, defined as of committed valuation date. Use canonical remaining holdings and transaction history, not lifetime buys or latest-price data. Show qualified account names and make any filtering action explicit.
- [ ] First inventory existing response fields. If absent, specify a minimal backend read model and tests; no per-row request fan-out and no client financial recalculation. Cover partial disposals, reopened holdings, closed accounts, multiple accounts per broker and historical dates.
- [ ] Use the shared Task 5 separators/typography for overview and metadata; preserve exact prices, quantities and bond labels. Run security/detail/context tests and backend tests; commit.

## Task 8 — Dashboard financial summary: owner choice before replacement

**Files:** `views/DashboardPage.vue`, `components/dashboard/SummaryCard.vue`, dashboard summary tests. Do not silently select a redesign: produce synthetic previews of these three alternatives for owner selection.

1. **Compact financial statement (recommended):** a clearly ordered, aligned summary beginning with invested capital, then available gain/income/cost components, ending with visually emphasized total NAV and a separate return section. Restore the logical reading order requested; never imply an accounting bridge that the available fields do not reconcile.
2. **Statement plus headline NAV:** a prominent NAV/return header above a compact two-column statement of the existing metrics.
3. **Grouped summary panels:** Capital, Performance and Current value groups with explicit headings and consistent reading order; no scattered independent metric tiles.

- [ ] Inventory every existing summary field and its meaning; preserve all fields and exact strings in each preview. Use synthetic positive/negative/missing scenarios.
- [ ] Present desktop and mobile versions of all three with the same data; ask for the composition choice. Palette changes remain a separate choice.
- [ ] Implement only the selected version, with tests for grouping/order, negative values, zero vs missing, long currency displays and responsive layout. No new financial formula.

## Final acceptance and executor reporting

- [ ] Keep a traceability ledger mapping every owner bullet to task, regression, result and capture. Distinguish source-confirmed cause, reproduced cause and still-unverified hypothesis.
- [ ] Run gates sequentially on the committed code: frontend unit suite, all three type checks, lint baseline, API types, build; affected focused browser cases, full route matrix, unflagged D8 acceptance and delivery budget; backend `uv run python -m pytest` using repository test settings. Capture actual exit statuses; do not infer success from warning counts.
- [ ] Retake only relevant synthetic captures; inspect pixels, not just DOM labels. Verify 390px, desktop-to-mobile-to-desktop, native 200% and reset. No hidden-overflow workaround.
- [ ] Repeat real-data validation on the disposable copy, including currency/effective-date changes, All-time, year options, performance and bond error cases. Signed/incomplete cases must actually occur or be labelled unavailable with separate synthetic evidence. Price-import execution is synthetic/disposable and distinguished from read-only chart validation.
- [ ] Update the tracker: D8 remains historically merged; this corrective phase is new and pending. C5b remains pending owner acceptance and removal approval. Open draft PR(s), report remaining findings, and stop before merge/deployment.
