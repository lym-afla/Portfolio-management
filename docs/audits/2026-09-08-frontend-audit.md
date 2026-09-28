# Frontend and charting audit — 8 September 2026

**Focused follow-up:** [Grouped table design and allocation pies](2026-09-08-grouped-tables-and-allocation-pies.md) adds the user's subsequent table review and explicit decision that Asset Type, Asset Class and Currency use solid pies. The original audit observations below describe the incumbent application, including its allocation bars.

Audited checkout: `a25f1882`. Scope: current `frontend/`, its chart API contract, and related documentation. Method: independent design review (Assessment A: `/root/design_review`), architecture and static detector review (Assessment B: `/root/architecture_audit`), chart/domain review (`/root/chart_audit`), and primary-agent browser verification and synthesis.

## Decision

**Modernize the existing Vue/Vuetify application incrementally. Prioritize trustworthy context and data refresh, repair the layout, then redesign the dashboard and shared components. Prototype Apache ECharts with `vue-echarts` as the preferred chart replacement.**

This is not an obsolete framework stack. The lockfile already contains Vue 3.5.11, Vite 8.1.4, Pinia 3 and Vuetify 3.12.5; every one of the 62 Vue components uses `<script setup>`. Only six use TypeScript. Earlier work largely modernized tooling while deliberately preserving behavior. The remaining problems are architectural, behavioral and visual.

Keep Vue, Vite, Pinia, and Vuetify initially. A framework or wholesale component-library rewrite would add substantial migration work without addressing the verified failures. A modern appearance can come from a coherent theme, layout, component defaults and interaction design. Chart.js can already render the required charts; migration should earn its cost through better analytical interaction.

## Evidence and limitations

- Installed the committed frontend lockfile using `npm ci`; application code, dependency declarations and lockfiles were not changed.
- Rendered the actual dashboard and Vuetify components at 1440×1000 and 390×844 using synthetic API responses in an isolated browser session. All screenshot amounts are illustrative; they are not portfolio records or financial evidence.
- Verified dashboard geometry, mobile clipping, accessible names and a failed-then-successful Retry interaction. Other pages/forms were source-reviewed. Incomplete synthetic responses prevented reliable full live review of Transactions and Positions; resulting fixture errors are excluded from findings.
- Reproduced four state/request issues using source-extracted functions and synthetic refs/API responses in an isolated Node VM. Chart helper/boundary reproductions used isolated Python execution without database writes.
- Checked chart capabilities and licenses against official documentation and repositories. No production backend, authenticated user data, live mutations, production deployment or full backend pytest run was involved.
- No device/network performance benchmark, complete WCAG assessment, or exhaustive financial regression suite was performed. Build sizes are measured; proposed performance gains remain hypotheses to measure.
- Both audit browser sessions and the temporary Vite server were stopped.

Current-render evidence: [desktop dashboard](<D:/Project Y/Portfolio management/docs/audits/assets/2026-09-08-frontend/dashboard-desktop.png>), [mobile dashboard](<D:/Project Y/Portfolio management/docs/audits/assets/2026-09-08-frontend/dashboard-mobile.png>), [mobile NAV](<D:/Project Y/Portfolio management/docs/audits/assets/2026-09-08-frontend/nav-mobile.png>).

## Highest-priority findings

Severity: P1 means a major correctness/usability/accessibility problem to resolve before a modernization release; P2 means a material improvement for the planned refactor. No P0 production outage was established. There are nine P1 and six P2 findings below; these are grouped findings, not a count of individual code defects.

### P1-1 — The fixed header obscures dashboard content

At scroll position zero, the desktop app bar ends at **137.94px**, while the first summary card begins at **16px**. The main content has **0px top padding**. The portfolio title, currency header and allocation headings sit beneath the app bar. The same overlap occurs on mobile.

Evidence: [App.vue:11](<D:/Project Y/Portfolio management/frontend/src/App.vue:11>) and the screenshots. The `height="auto"` app bar is a likely contributor; its exact layout-registration fix needs verification.

Repair the Vuetify app-bar/main layout contract, then test actual element rectangles across authenticated routes, route changes and responsive breakpoints. [AppLayout.spec.js:8](<D:/Project Y/Portfolio management/frontend/tests/unit/AppLayout.spec.js:8>) only checks that certain source strings are absent; it does not verify visible layout. Avoid another source-string assertion as the acceptance test.

### P1-2 — A failed account switch can mislabel the portfolio

[AccountSelection.vue:107](<D:/Project Y/Portfolio management/frontend/src/components/AccountSelection.vue:107>) immediately changes the visible selector, then awaits the backend update. The store only commits after success. A rejected request leaves account B selected while account A's data remains displayed. The isolated reproduction confirmed this mismatch.

Keep committed and pending selection distinct. Commit the visible context after successful persistence, or roll it back on failure with a useful error. Serialize account-context mutations so rapid changes cannot commit in the wrong order. All result panels should identify the context that produced their data.

### P1-3 — Request handling can retain or restore obsolete data

There are two different failures:

- [FXPage.vue:230](<D:/Project Y/Portfolio management/frontend/src/views/database/FXPage.vue:230>) drops every request while another is running, including changed parameters. Changing the search to EUR during a request never issues the EUR query afterward.
- [TransactionsPage.vue:251](<D:/Project Y/Portfolio management/frontend/src/views/TransactionsPage.vue:251>), [PositionsPageBase.vue:366](<D:/Project Y/Portfolio management/frontend/src/components/PositionsPageBase.vue:366>) and [DashboardPage.vue:306](<D:/Project Y/Portfolio management/frontend/src/views/DashboardPage.vue:306>) accept overlapping responses without a latest-request guard. Old results can overwrite newer results and incorrectly clear loading indicators.

Create a shared query lifecycle with immutable parameters, cancellation and/or generation checks, and parameter-aware deduplication. Query identity needs account/group, valuation date, currency, range, pagination, sort and search as applicable. Debounce search, but do not use debouncing as the correctness guarantee. Account changes involve server context too; coordinate those mutations before issuing dependent reads. Define mutation invalidation before adding caching.

### P1-4 — Date presets can use a stale valuation date

[useTableSettings.ts:9](<D:/Project Y/Portfolio management/frontend/src/composables/useTableSettings.ts:9>) copies the effective date into a separate ref. The preset handler at line 51 reuses it while nonempty. In the reproduction, changing the store date to 2025-12-31 still left a subsequent YTD request ending on 2026-09-08.

Use a reactive store reference/computed value and a single coordinated context update. Cover changes to the effective date without leaving the page.

### P1-5 — Successful retry does not restore the dashboard summary

[DashboardPage.vue:252](<D:/Project Y/Portfolio management/frontend/src/views/DashboardPage.vue:252>) updates data after success but does not clear the widget's prior error. `clearErrors()` clears the global snackbar, not `error.summary`. The template consequently continues to hide the summary.

Browser reproduction: inject one summary failure, restore successful responses, click the actual Retry button. The success request runs, but the summary card remains absent and Retry/error remain visible. The same missing-error-reset pattern occurs in other dashboard loaders. Reset local error state deliberately and test the full failure → retry → recovered-content journey. Current retry tests only check that requests are re-invoked.

The NAV endpoint separately catches calculation exceptions and returns empty datasets with HTTP 200, confusing failure with no data: [backend/dashboard/views.py:366](<D:/Project Y/Portfolio management/backend/dashboard/views.py:366>). Evolve that response contract through an independently reviewed backend change.

### P1-6 — Mobile controls and important context are squeezed out

At a 390px viewport, Quarter and Year frequency controls end at approximately **422px and 494px**. Global horizontal overflow suppression hides the problem instead of making the controls fit. The permanent navigation rail consumes 56px, while account-cycling buttons and settings leave the account name truncated.

Evidence: [Navigation.vue:2](<D:/Project Y/Portfolio management/frontend/src/components/Navigation.vue:2>), [NAVChart.vue:15](<D:/Project Y/Portfolio management/frontend/src/components/dashboard/NAVChart.vue:15>), [App.vue:132](<D:/Project Y/Portfolio management/frontend/src/App.vue:132>).

Use a temporary mobile drawer, prioritize the account name, and move lower-priority controls into a compact menu or select. Make the chart height responsive; avoid dense point labels on narrow screens. Keep wide financial tables horizontally scrollable inside a defined table region rather than compressing every column.

### P1-7 — Essential controls/charts lack accessible names or equivalent data access

The rendered accessibility tree exposes unnamed account arrow/settings buttons. The three allocation canvases have image roles but no accessible names; the raw NAV canvas has neither name nor fallback content. Transaction row actions are clickable icons rather than explicitly named buttons.

Evidence: [SettingsDialog.vue:3](<D:/Project Y/Portfolio management/frontend/src/components/SettingsDialog.vue:3>), [AccountSelection.vue:6](<D:/Project Y/Portfolio management/frontend/src/components/AccountSelection.vue:6>), [TransactionRow.vue:67](<D:/Project Y/Portfolio management/frontend/src/components/transactions/TransactionRow.vue:67>), [StackedBarLineChart.vue:1](<D:/Project Y/Portfolio management/frontend/src/components/charts/StackedBarLineChart.vue:1>).

Add explicit names, keyboard-operable controls, visible focus, chart descriptions and a NAV data-table alternative. Retain the existing allocation chart/table tabs. Test keyboard navigation and focus restoration in dialogs. Relevant standards are WCAG 1.1.1, 2.1.1 and 4.1.2; this audit does not establish full conformance. Use 44px as a comfortable touch design target, without incorrectly describing it as the universal AA minimum: WCAG 2.2's minimum target criterion is 24 CSS pixels with exceptions. [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/)

### P1-8 — Missing category values can shift data to the wrong date

The backend appends values only when a category exists, then pads the ends. A category present on Jan 1, absent Jan 2, and present Jan 3 becomes `[1, 3, null]`, rather than `[1, null, 3]`.

Evidence and isolated helper reproduction: [charts.py:245](<D:/Project Y/Portfolio management/backend/services/charts.py:245>) and [charts.py:263](<D:/Project Y/Portfolio management/backend/services/charts.py:263>).

Build each series against the complete date index. Decide the financial meaning of absence (zero exposure versus unavailable valuation) explicitly. This affects displayed financial outputs: fix through a separate reviewed PR with a numerical regression fixture, not as an incidental renderer change.

### P1-9 — Contribution intervals exclude a boundary day

The chart loop advances the previous endpoint by one day; the contribution query then uses a strict greater-than filter. For an endpoint of Jan 31, the next filter becomes `date > Feb 1`, excluding Feb 1 flows.

Evidence and boundary reproduction: [charts.py:194](<D:/Project Y/Portfolio management/backend/services/charts.py:194>), [charts.py:445](<D:/Project Y/Portfolio management/backend/services/charts.py:445>).

Specify an unambiguous interval convention and test a cash flow on the first day after the previous endpoint, including daily frequency. Route this through a separate financial-output PR with expected Decimal results and human review.

## Structural and visual improvements

| Priority | Finding and evidence | Concrete recommendation |
|---|---|---|
| P2-1 | All ordinary routes are eager imports; all Vuetify components/directives are registered globally; full MDI font is imported. [router:4](<D:/Project Y/Portfolio management/frontend/src/router/index.js:4>), [main:3](<D:/Project Y/Portfolio management/frontend/src/main.js:3>) | Lazy-load routes and expensive dialogs; use Vuetify auto-import deliberately; replace the full icon font with used SVG icons. Measure before/after entry bytes and route interactions. |
| P2-2 | CI runs only BrokerTokenManager tests and limited lint; no build/type-check gates. [CI:76](<D:/Project Y/Portfolio management/.github/workflows/ci.yml:76>), [PR checks:74](<D:/Project Y/Portfolio management/.github/workflows/pr-checks.yml:74>) | Pin a supported Node runtime, repair test initialization, gate the full suite/build/type-check, and add a small real-browser smoke suite for layout, context changes, errors and imports. |
| P2-3 | TypeScript covers six of 62 SFCs; strict and JS checking are disabled. [tsconfig:6](<D:/Project Y/Portfolio management/frontend/tsconfig.json:6>), [api:29](<D:/Project Y/Portfolio management/frontend/src/services/api.ts:29>) | Type account context, financial display values, chart contracts, table responses and import events first. Add boundary validation for untyped API responses; increase strictness in bounded modules. |
| P2-4 | Import dialog is 1,689 lines; API module 1,636; BrokerTokenManager 1,035; SecurityDetailPage 954. [Import dialog:524](<D:/Project Y/Portfolio management/frontend/src/components/dialogs/TransactionImportDialog.vue:524>) | Split API transport by domain. Extract import session/connection lifecycle, typed state transitions and step components. Keep Pinia focused on shared application context; local interaction state belongs near its view. Preserve behavior with workflow tests. |
| P2-5 | Dashboard gives similar weight to summary rows, allocation cards and accounting details; NAV is below the historical table. Field variants, colors and alignment vary. [Dashboard:10](<D:/Project Y/Portfolio management/frontend/src/views/DashboardPage.vue:10>), [theme](<D:/Project Y/Portfolio management/frontend/src/theme.js:1>) | Establish shared layout, spacing, typography, table, filter and action patterns. Put NAV/performance first; make allocations and reconciliation secondary. Define stable semantic and chart tokens rather than hardcoded per-component colors. |
| P2-6 | Default icon rail, unclear Summary/Dashboard distinction, five equal-weight transaction operations, generic delete confirmation and production-imported auth debug helpers. [Navigation:10](<D:/Project Y/Portfolio management/frontend/src/components/Navigation.vue:10>), [Transactions:177](<D:/Project Y/Portfolio management/frontend/src/views/TransactionsPage.vue:177>), [authDebugConsole:8](<D:/Project Y/Portfolio management/frontend/src/utils/authDebugConsole.js:8>) | Clarify information architecture and primary actions; persist useful table presets; identify the exact transaction in destructive confirmation. Gate debug imports themselves to development and remove obsolete documentation/dependencies after checking usage. |

Vue's official performance guidance supports route code splitting, tree-shaking and measuring actual bundles. The measured opportunity here is delivery cost, not evidence that Vue rendering itself is slow. [Vue performance guide](https://vuejs.org/guide/best-practices/performance)

### Proposed visual direction

Build a restrained financial workspace around the existing brokerage blue, neutral surfaces and system font. Preserve tabular numerals and dense analytical tables. Prefer subtle boundaries and limited shadows; make hierarchy come from spacing, alignment and type weight.

Proposed dashboard reading order:

1. **Context strip:** actual account/group name · valuation date · reporting currency. Keep formatting precision in preferences.
2. **Principal metrics:** NAV as the dominant value, then clearly labeled existing return/cash/investment metrics. Introduce a selected-period metric only when its precise backend definition exists.
3. **Value and performance:** the main NAV/IRR visualization and its controls, with a table alternative.
4. **Allocation:** compact comparisons by asset type/class/currency.
5. **Historical reconciliation:** the complete accounting table; performance recalculation as a contextual maintenance action.

Suggested starting typography: 32–36px principal value, 22–24px page heading, 13–14px table values, quieter metadata. Right-align comparable numbers. Use green/red consistently for financial direction; use a separate stable categorical palette for allocations. Do not rely on color alone for series identity.

Use labeled desktop navigation with optional collapse; use a mobile drawer. A proposed grouping is Overview, Performance, Positions (Open/Closed), Transactions and Data, subject to validating the distinct jobs currently served by Summary and Dashboard. On transaction pages, distinguish the primary everyday action from imports and occasional corporate actions. Preserve grouped columns, totals, server-side pagination, sticky identity columns, column selection and chart/table alternatives.

This is a proposed design direction, not an implemented redesign or approved visual mockup.

## Charting decision

| Library | Suitability for this application | Tradeoff / license |
|---|---|---|
| **Apache ECharts + vue-echarts — preferred** | Mixed stacked bars and two-axis lines, shared axis tooltip, zoom, scrollable legends, Canvas/SVG and flexible composition fit the complete chart inventory. | Apache-2.0 engine / MIT wrapper. More configuration complexity; explicitly implement accessible data access and controlled interaction state. |
| **Retain Chart.js — valid baseline** | Already handles the current visualizations. Lowest migration risk and enough for a visual refresh. | MIT. Richer interaction and chart accessibility require additional app/plugin work; zoom is an additional plugin. |
| **Highcharts — paid alternative** | Strong option when keyboard/screen-reader navigation and exports are major requirements. Core supports the mixed dashboard; Stock is optional. | Commercial licensing with specific noncommercial terms. Evaluate license scope and disable unsuitable default data grouping. |
| **TradingView Lightweight Charts — specialist** | Attractive for a future price/candlestick screen, but a poor default for these categorical allocation and stacked NAV charts. | Apache-2.0 with documented attribution requirements. Tooltips and legends need custom work; its financial Bar series is not the dashboard's stacked categorical bar. |

Primary sources: [ECharts mixed axes](https://echarts.apache.org/handbook/en/concepts/axis/), [stacked bars](https://echarts.apache.org/handbook/en/how-to/chart-types/bar/stacked-bar/), [Canvas/SVG](https://echarts.apache.org/handbook/en/best-practices/canvas-vs-svg/), [Vue wrapper](https://github.com/ecomfe/vue-echarts), [ECharts license](https://github.com/apache/echarts/blob/master/LICENSE); [Chart.js mixed charts](https://www.chartjs.org/docs/latest/charts/mixed.html), [zoom plugin](https://www.chartjs.org/chartjs-plugin-zoom/latest/guide/), [license](https://github.com/chartjs/Chart.js/blob/master/LICENSE.md); [Highcharts accessibility](https://www.highcharts.com/docs/accessibility/accessibility-module), [exports](https://www.highcharts.com/docs/export-module/export-module-overview), [Vue integration](https://github.com/highcharts/highcharts-vue), [licensing](https://shop.highcharts.com/license); [Lightweight Charts series/attribution](https://tradingview.github.io/lightweight-charts/docs), [tooltips](https://tradingview.github.io/lightweight-charts/tutorials/how_to/tooltips), [Vue tutorial](https://tradingview.github.io/lightweight-charts/tutorials/vuejs/wrapper).

Pin and evaluate released package versions during implementation. Do not migrate solely because one package appears newer. No alternate chart engine was installed or benchmarked in this audit.

### The NAV contract that must survive migration

| Element | Current meaning |
|---|---|
| NAV bars | Portfolio value snapshots in reporting currency divided by 1,000; API unit such as USDk. |
| IRR (RHS) | Annualized money-weighted XIRR from inception to each sample endpoint. Changing visible dateFrom does not rebase it. |
| Rolling IRR (RHS) | Annualized XIRR for the interval since the preceding chart sample. Frequency changes this horizon. It is **not trailing twelve-month IRR**. |
| First rolling point | Uses `start_date=None`, matching inception behavior. |
| Ordinary breakdown modes | None, account, asset type, asset class, currency. Dynamic stacked categories share the money axis. |
| Value Contributions | Previous NAV + interval contributions + residual return, summing to current NAV. |
| Cumulative Value | All-history net investments + residual return, summing to current NAV. |
| Unavailable returns | `N/A`, `N/R` and null require explicit unavailable states; they are not zero. |

Evidence: [chart series/IRR calls](<D:/Project Y/Portfolio management/backend/services/charts.py:74>), [scaling and boundaries](<D:/Project Y/Portfolio management/backend/services/charts.py:133>), [contributions](<D:/Project Y/Portfolio management/backend/services/charts.py:209>), [cumulative values](<D:/Project Y/Portfolio management/backend/services/charts.py:462>), [IRR calculation](<D:/Project Y/Portfolio management/backend/services/nav.py:462>).

Recommend labels such as **Since-inception IRR (annualized)** and **Interval IRR (annualized)**, with the interval displayed in the tooltip. The first point's inception horizon needs explicit explanation. Naming clarification must not silently change the calculation.

The backend currently emits Chart.js-specific datasets and formatting. Friendly period labels are used as equal-spaced categories. Daily/weekly/monthly/quarterly/yearly sampling uses period endpoints, with the requested final date appended. Exact timestamps and partial-period metadata cannot reliably be recovered from display labels. Introduce a typed frontend adapter first; add exact API dates separately before promising continuous-time spacing or precise exports.

### Current chart weaknesses to address regardless of library

- NAV loading unmounts the canvas; dataset-count changes destroy/recreate the chart. This loses unmanaged legend/zoom state. Keep the chart mounted and show a loading overlay; persist interaction state explicitly. Final unmount cleanup already exists and should be preserved. [NAVChart:35](<D:/Project Y/Portfolio management/frontend/src/components/dashboard/NAVChart.vue:35>), [renderer:50](<D:/Project Y/Portfolio management/frontend/src/components/charts/StackedBarLineChart.vue:50>)
- Colors depend on dataset index, so a new category can change IRR colors. Use stable metric/category IDs and fixed line styles. [NAVChart:158](<D:/Project Y/Portfolio management/frontend/src/components/dashboard/NAVChart.vue:158>)
- Tooltip return formatting depends on English labels. Use metric/unit metadata. The current interaction uses the default nearest intersecting item rather than a full date comparison. [chartConfig:203](<D:/Project Y/Portfolio management/frontend/src/config/chartConfig.js:203>), [Chart.js defaults](https://www.chartjs.org/docs/latest/configuration/interactions.html)
- Point labels clutter the mobile NAV chart. Use hover/focus details and selected/latest markers, stable legend controls and a shared crosshair tooltip.
- Stack totals sum hidden datasets and can be visually misleading with negative stacks. Distinguish total portfolio NAV from visible subtotal; specify signed-total placement. [chartConfig:161](<D:/Project Y/Portfolio management/frontend/src/config/chartConfig.js:161>)
- Allocation charts parse formatted monetary strings and recompute percentages from rounded display values. Preserve raw decimal strings and backend-provided percentages separately from localized labels. Do authoritative money math with Decimal on the backend; conversion to JavaScript numbers belongs only at the plotting boundary. [BreakdownChart:94](<D:/Project Y/Portfolio management/frontend/src/components/dashboard/BreakdownChart.vue:94>)

Six live chart instances need coverage: NAV, three allocation charts, security price history and security position history. The dormant PriceChart component and commented PricesPage chart should not expand the initial migration automatically. Security charts need correct price units for bonds, which use percentage of nominal, and a deliberate choice of step rendering for discrete holdings. [SecurityDetailPage:722](<D:/Project Y/Portfolio management/frontend/src/views/database/SecurityDetailPage.vue:722>), [axis configuration:819](<D:/Project Y/Portfolio management/frontend/src/views/database/SecurityDetailPage.vue:819>)

### Chart migration gate

Prototype the most complex NAV view first behind a replaceable renderer. Normalize the current response into stable series IDs, values/statuses, units and axis roles; preserve backend calculation ownership. Import only required ECharts modules and measure the resulting chunk.

Required acceptance cases:

1. All seven modes × five sampling frequencies, including signed stacks and categories that enter, disappear and return.
2. Correct units: 100,000 currency units → 100 on a thousands axis; ratio 0.1234 → 12.3% as a label, without a second multiplication in the data.
3. Independent visibility of both IRRs; first-point inception behavior; interval boundaries; no rebase from a changed viewport alone.
4. Zero, negative, null, N/A and N/R stay distinct; missing returns are gaps rather than false zero values or bridged lines.
5. Exact period/end-date handling, leap day, partial final periods, weekly boundaries and timezone-safe date handling.
6. Legend identity, colors, selected series and zoom survive ordinary refreshes and resize; define whether labels mean net NAV or visible subtotal.
7. A→B requests resolving B→A, failed account updates, retry recovery, unmount while loading and data mutation invalidation.
8. Keyboard/table access, mobile controls, long legends, export unit/status fidelity and contrast checks. ECharts ARIA descriptions/decals assist but do not establish keyboard or full WCAG conformance. [ECharts accessibility](https://echarts.apache.org/handbook/en/best-practices/aria/)

Zoom and rendering aggregation must not invent financial results. Highcharts Stock defaults average line points and sum columns when grouping; that would average IRRs and sum NAV snapshots. Disable grouping for these series, or request semantically correct server-calculated periods. The same principle applies to any library. [Highcharts data grouping](https://www.highcharts.com/docs/stock/data-grouping)

Measure backend calculation, transfer and rendering separately on long daily histories. A faster renderer does not eliminate repeated NAV/XIRR calculation costs. No unverified speedup percentage is proposed.

## Delivery sequence

| Phase | Scope | Exit condition |
|---|---|---|
| 1. Stabilize | Header layout, committed account context, latest-request logic, effective-date reactivity, local error recovery and accessible primary controls. | Real-browser regression cases for each reproduced issue; supported test runtime established. |
| 2. Financial chart repairs | Separate PRs for category/date alignment and contribution interval boundary. | Decimal numerical fixtures and required human financial review. Do not bury these in a styling PR. |
| 3. Frontend foundation | Lazy routes, selective Vuetify/icons, typed API boundaries, domain transport modules, shared query lifecycle and CI gates. | Measured bundle reduction, full relevant checks and unchanged financial payload interpretation. |
| 4. Design system and dashboard | Context strip, metric hierarchy, NAV-first layout, responsive controls, consistent tables/forms and navigation. | Agreed desktop/mobile reference captures and keyboard/error-state verification. |
| 5. Chart pilot and rollout | ECharts NAV pilot, then allocations and security charts after acceptance. | All parity cases pass; interaction/accessibility improvements demonstrable; measured bundle/render cost accepted. Remove old chart dependencies only once all live uses are migrated. |
| 6. Workflow extraction | Import state transitions and step components, broker-token management and security-detail decomposition. | Existing workflows preserved, connection cancellation/cleanup tested, module responsibilities clear. |

Use small reviewable PRs. Any change affecting financial outputs requires the project's numerical regression evidence and human approval. Update the project documentation alongside implementation: `.memory-bank/Tech details/frontend.md` still describes Vue CLI, Vuex and no script setup, and the NAV/FX map points to pre-extraction locations. Current code is the evidence used here; do not repeat the old migration plan blindly.

Suggested design follow-through: `$impeccable harden` for behavior and accessible controls; `$impeccable adapt` for narrow layouts; `$impeccable layout` and `$impeccable distill` for hierarchy; `$impeccable document` for the established design system; `$impeccable polish` after implementation and verification.

## Verification results and scorecard

| Check | Outcome |
|---|---|
| Production build | Pass; 15.37 seconds on this machine. |
| Initial JS | 1,365.81 kB minified / **415.12 kB gzip**. |
| Initial CSS | 837.10 kB / **119.70 kB gzip**. |
| MDI WOFF2 asset | **403.21 kB**, in addition to JS/CSS; other font formats also emitted. This does not imply a browser downloads all formats. |
| Type check | Pass, under the current non-strict configuration. |
| Lint | Pass, under the existing script/configuration scope. |
| Unit tests | **85 passed / 22 failed**, 18 files. Failures share `localStorage` being undefined. Local Node v26.8.1 differs from CI Node 20. One runtime-flag rerun produced the same result. Unresolved harness/runtime issue; not 22 proven product defects. |
| Static design detector | Successful scan, zero findings (`[]`). It did not detect the runtime/header/state/accessibility problems found manually. |
| Browser review | Dashboard desktop/mobile and retry journey verified with synthetic data; other routes source-reviewed. |

Technical quality score is **7/20, substantial work required**: accessibility 1/4, performance 1/4, responsive behavior 1/4, theming 2/4, implementation integrity 2/4. This is a prioritization rubric for the inspected scope, not a benchmark or compliance certificate. There is a useful system foundation, but the runtime failures prevent calling it coherent end to end.

Independent design Assessment A scored 21/40 before the retry reproduction. The synthesized design score below is **19/40**, with recovery reduced in light of that evidence. Write workflows were not executed, so prevention/control scores have limited confidence.

| Heuristic | Score /4 | Main basis |
|---|---:|---|
| System status | 3 | Skeletons and indicators exist; context visibility and request lifecycle need work. |
| Real-world match | 3 | Strong financial content; some unexplained terms. |
| User control | 2 | Cancel/back controls; draft/undo behavior unverified. |
| Consistency | 2 | Shared components, inconsistent variants/alignment. |
| Error prevention | 2 | Validation exists; generic destructive confirmation. |
| Recognition | 2 | Hidden date/currency and collapsed navigation. |
| Efficiency | 2 | Dense tables, sorting and imports; interaction/preset gaps. |
| Visual hierarchy | 1 | Occluded content and equal-weight widgets. |
| Error recovery | 1 | Successful retry can leave recovered content hidden. |
| Help | 1 | Scattered hints, little task-oriented explanation. |

For a frequent analyst, hidden context and stale results undermine trust. For a keyboard user, unnamed controls and inaccessible chart content block exploration. For a new user, Summary versus Dashboard and abbreviations increase recall demands. Preserve the financial density; reduce ambiguous context, redundant controls and avoidable chrome.

Local reproduction artifacts remain under ignored `temp_files/`: `frontend-architecture-repros.mjs`, `frontend-architecture-repros.json`, `frontend-audit-detector.json`, `frontend-audit-vitest-node26-no-webstorage.json`, and `frontend-audit/setup-fixture.js`. The durable deliverable is this report and its three clean screenshot captures.

Questions skipped: this request is an audit and recommendation; implementation and visual-direction decisions can follow from this concrete report.
