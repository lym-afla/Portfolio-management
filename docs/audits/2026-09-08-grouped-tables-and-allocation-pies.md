# Focused review: grouped tables and dashboard allocation pies

Date: 8 September 2026. Scope: position headers, Summary tables, and the dashboard's three allocation cards. This follows the user's request to reconsider complex column grouping and explicitly mark allocations as pie charts. No application code or financial calculations are changed by this review.

**Decision status:** The three solid allocation pies are explicitly requested. The hybrid table design below is a recommendation for the planned visual pilot, not a claim that the user has approved a final rendered design. It updates the earlier plan's assumption that every position view must always have two header rows.

## Recommendation

**Use a compact Overview with fully named columns, a side-by-side comparison preset, and a two-row grouped Full ledger.** Preserve Entry versus Current/Exit meaning. Remove the need to read the full ledger for everyday monitoring. Modernization here means reducing the number of simultaneous choices and making column identities reliable; removing every group label would lose useful information.

For the dashboard, **Asset Type, Asset Class and Currency must be solid pie charts**. The separate NAV timeline remains stacked bars with both existing IRR lines. This supersedes the August specification's instruction to replace allocation pies with bars.

## What the current code actually does

| Table | Structural header rows | Available / initially visible columns | Consequence |
|---|---:|---:|---|
| Open positions | 2 | 20 / 13 | Current contains 13 leaves spanning valuation, performance, income and charges. Its heading is too broad to guide scanning. |
| Closed positions | 2 | 16 / 16 | Seven separate financial groups repeat Amount and % labels; every field is initially exposed. |
| Account performance | 2 | 1 + 8 per period | With four periods, this is already 33 columns. Reducing header height does little to solve its width. |
| Portfolio breakdown on Summary | 2 | 14 | Repeated amount/percentage pairs need clear units and associations. |
| Dashboard history | 1 | Periods as columns, metrics as rows | The app already has a useful alternative for historical comparison. |

Evidence: [position definitions](<D:/Project Y/Portfolio management/frontend/src/config/positionsHeaders.js:1>), [defaults](<D:/Project Y/Portfolio management/frontend/src/config/positionsHeaders.js:127>), [account performance](<D:/Project Y/Portfolio management/frontend/src/views/SummaryPage.vue:14>), [portfolio breakdown](<D:/Project Y/Portfolio management/frontend/src/views/SummaryPage.vue:176>), [dashboard history](<D:/Project Y/Portfolio management/frontend/src/components/dashboard/SummaryOverTimeTable.vue:9>).

There is no current third nesting tier in the position configuration. Three visible text lines may be wrapped labels rather than three logical header rows. The old Current → Gain/Loss → leaf structure in the August specification is historical. Preserve the useful improvements already present: shared definitions, end-aligned numerals, selectable columns and dynamically aligned footer cells.

## Critical findings

### T1 — The grouping follows the implementation more than the user's question

Open positions place Price, Value, Share %, Price change, realized/unrealized G/L, distributions, commissions and returns under Current. A current valuation and a realized return are different concepts. Closed positions instead fragment performance into several small groups. The siblings require different scanning habits.

Use a consistent lifecycle: **Identity → Entry → Current or Exit → Performance**. Current contains only current valuation fields; Performance contains return-related leaves. Full ledger still has many columns intentionally, but everyday Overview and comparison presets expose smaller task-specific subsets. Simply moving ten columns under a new heading would not by itself solve density.

In the actual component harness at 1440px, Current's header cell spans approximately x845–1495 and is end-aligned, putting its title beyond the visible viewport. Body cells have no group-start divider. Left-align group labels and carry restrained boundaries down through the table; the visual grouping must be visible where the user first encounters its columns.

### T2 — Group meaning disappears in the column chooser

[PositionsPageBase.vue:116](<D:/Project Y/Portfolio management/frontend/src/components/PositionsPageBase.vue:116>) renders only the leaf title. Users must distinguish duplicate Date/Price/Value choices and repeated Amount/% checkboxes without seeing the parent group. This is a concrete usability defect, not a matter of visual taste.

Keep two labels per metric: a short grouped-table title and a full standalone title. Examples: Entry price, Current price, Entry value, Exit value, Realized G/L amount, Commission %. Use the full label in Columns, sort descriptions, accessible names and details. Organize the chooser by group, permit multiple changes before Done, and retain all original metric keys.

### T3 — Visibility and pinned identity are not stable enough

Column visibility is currently component-local and permits hiding Type and Name. Sticky CSS pins positions 1 and 2, rather than identity keys; the second offset is fixed at 90px while the first width is only a minimum. In the actual component harness, hiding Type and Name made Currency and Position sticky and removed row identity/footer labels. [Visibility state](<D:/Project Y/Portfolio management/frontend/src/components/PositionsPageBase.vue:282>), [sticky selectors](<D:/Project Y/Portfolio management/frontend/src/components/PositionsPageBase.vue:474>), [footer labels](<D:/Project Y/Portfolio management/frontend/src/views/OpenPositionsPage.vue:48>).

Pin security identity by key and measured width. Keep at least one row identity visible. Persist preset/visible keys per table; retain custom choices on navigation and do not silently overwrite them on resize. Derive group boundaries, headers and footers from the same visible leaf list. A hidden sort column must remain identifiable in a visible sort summary, with a clear way to remove it.

### T4 — Visual grouping needs semantic and temporal context

The native Summary headers do not explicitly associate group/leaf/row headers. The application does not add scope or aria-sort to the position headers; built-in keyboard sorting alone does not establish those associations. Currency subheaders in Summary are created once in a ref, which can retain stale units after a reporting-currency change. [Summary header markup](<D:/Project Y/Portfolio management/frontend/src/views/SummaryPage.vue:176>), [currency labels](<D:/Project Y/Portfolio management/frontend/src/views/SummaryPage.vue:367>).

The component browser check confirmed missing scope attributes and absent aria-sort after visibly sorting Name. It also found the toolbar's Search and Columns controls beyond the 390px viewport. Keep the selector/control strip outside the table's horizontal overflow region and wrap it independently. These findings are not a complete screen-reader audit.

Use real colgroups/group scopes and leaf/row headers for regular grouping; explicit unique header IDs and data-cell associations where the hierarchy requires them. Verify the rendered Vuetify DOM and screen-reader behavior. Derive visible units from the committed context, while preserving each instrument's actual price unit. This follows the [W3C grouped-header guidance](https://www.w3.org/WAI/tutorials/tables/irregular/) and [multi-level associations guidance](https://www.w3.org/WAI/tutorials/tables/multi-level/).

## Proposed table experience

| View | Intended task | Presentation |
|---|---|---|
| Overview — default for new/unconfigured views | Which holdings need attention? | One header row with fully qualified labels and 8 open / 7 closed columns. |
| Entry & valuation / Entry & exit | Compare acquisition with valuation or disposal | Both sides visible together, with a quiet group band and their own Date/Price/Value leaves where those metrics actually exist. |
| Full ledger | Reconcile all financial components | All 20 open / 16 closed fields, two semantic header rows, contained horizontal scroll, pinned identity. |
| Columns — customization | Choose a personal subset | Grouped, fully named checkboxes; persisted per table; no loss of any original field. |

**Open Overview:** Security, Currency, Entry value, Current value, Portfolio share %, Total return amount, Total return %, IRR. Show Type as secondary identity text. Quantity, entry/current prices and dates remain in the comparison and Full ledger views.

**Closed Overview:** Security, Currency, Entry value, Exit value, Total return amount, Total return %, IRR. Type remains secondary identity text. The existing closed response does not expose Entry/Exit price leaves; do not invent them for visual symmetry.

**Full ledger mapping:** Open = Identity 4 + Entry 3 + Current 3 + Performance 10. Closed = Identity 3 + Entry 2 + Exit 2 + Performance 9. Stable leaf keys remain unchanged. Use qualified Performance labels instead of a third group tier or repeated generic Amount/% labels.

**Group-band treatment:** Small, left-aligned section labels on a restrained neutral background; leaf headings carry stronger reading priority and numeric leaves align with their values. Add a subtle boundary at the start of each group, extending through header, body and footer. Avoid full-height colored columns or a separate card around every group. Keep both header tiers together during vertical scrolling, below the app bar. Wrapped text is permitted where helpful; header row count and text line count are different constraints.

**Mobile:** Default new/unconfigured views to Overview, keep security identity visible, and contain horizontal scrolling inside the table. Preserve an explicitly saved Full ledger preference and provide an easy Overview switch. Keep names, signs, units and column controls available without hover. Do not turn every holding into a tall card or hide Entry behind a mutually exclusive Current tab: those approaches weaken comparison.

**Amount and percentage:** Keep independently sortable columns in the main ledger. A paired amount/percentage cell can be useful in a future compact row detail, but adopting it everywhere would obscure which metric is sorted and increase row height. It is an alternative, not part of this recommended first change.

**Summary tables:** Use a selected-period account table for compact review, with explicit multi-period comparison/full-history access. Keep all years, YTD, All-time, account sections, subtotals and calculation meanings available. A later account-focused comparison can transpose metrics into rows, following the dashboard history precedent. Preserve amount/% leaves in the portfolio breakdown while clarifying their full labels and reactive units.

## Dashboard allocation decision

The three cards are currently horizontal bars: [dashboard dimensions](<D:/Project Y/Portfolio management/frontend/src/views/DashboardPage.vue:243>), [shared Bar component](<D:/Project Y/Portfolio management/frontend/src/components/dashboard/BreakdownChart.vue:13>), [horizontal options](<D:/Project Y/Portfolio management/frontend/src/config/chartConfig.js:55>). Current tests explicitly expect no pie options; this needs an intentional test update at implementation time, not merely a prop change.

- **Target:** three solid pies titled Asset Type, Asset Class and Currency. Same diameter and visual weight, side by side on wide screens and stacked on narrow screens, below the primary NAV region. Doughnut styling is optional future refinement, not the requested default.
- **Inspection:** stable category colors, visible category/value/% legend and Chart/Table access. Hover, keyboard focus or tap highlights a slice and shows the same backend-formatted values. Do not require hovering to understand the allocation.
- **Many categories:** preserve every category; allow the legend/list to expand and prioritize readable labels outside the circle. Do not switch to bars solely because there are more than four slices. Do not invent Other by subtracting from NAV. Any future aggregation must be an explicit, accurate contract with full detail retained.
- **Stable denominator:** selecting a legend item highlights/focuses it. It must not hide other slices and silently renormalize the remaining geometry into a new whole. Display percentages come from the approved backend ratio contract, not ECharts' calculated percentage label.
- **Rendering:** one ECharts pie series per card, with slices from the contract's allocations. Register the PieChart module during C4. This choice is independent of NAV's bar/line roles. ECharts supports this directly; its default all-zero pie can show equal sectors, so explicitly disable that behavior and provide the empty state. [ECharts pie documentation](https://echarts.apache.org/handbook/en/how-to/chart-types/pie/basic-pie/)

### Financially honest pie states

Draw the pie only for a backend-confirmed complete, nonnegative partition with a positive total. These are real domain constraints: short positions are allowed, missing price/FX can omit valuations, and the current crypto branch can contribute to total NAV without entering ordinary breakdown buckets. [NAV category handling](<D:/Project Y/Portfolio management/backend/services/nav.py:279>), [crypto branch](<D:/Project Y/Portfolio management/backend/services/nav.py:300>).

For negative, incomplete, unavailable, all-zero or nonpartition cases, keep the full signed/status data table and a concise explanation in the pie region. Do not take absolute values, omit negative categories, renormalize a positive subset or convert unknown values to zero. A known zero can remain as a zero row in the legend/table without an artificial slice. The current table's hardcoded 100% also needs the contract-aware treatment planned in C4.

Example acceptance: complete 25/75 allocations render two sectors and backend labels 25%/75%; adding a known zero does not change their geometry; an unknown or negative category prevents a misleading whole-portfolio pie. F3's percentage-scale investigation remains a prerequisite; a pie migration must not conceal a scale error.

## Changes to the implementation plan

1. **D3/D4:** adopt the hybrid table design as the proposed visual pilot. Extend column metadata and persistence, identity pinning, accessible headers, group-derived body/footer boundaries and explicit hidden-sort treatment. Check the actual comparison experience, not just header row count.
2. **D5:** apply the agreed table pattern to both position pages and simplify Summary's period presentation while retaining full comparison/history. Keep units reactive to committed context.
3. **C4:** replace the horizontal-allocation-bar target with the three solid pies and the eligibility/denominator rules above. Preserve the established financial contract and chart/table accessibility.
4. **C5/D8:** require three accepted allocation pies plus NAV and two security charts, and compare actual desktop/mobile tables against the pilot. Keep existing migration fallback until these checks pass.

D3 can initially verify layout with the incumbent bars; it must label them transitional. Final pie acceptance belongs to C4/C5, so this follow-up does not introduce a dependency cycle or force unsafe geometry before the chart contract is ready. The documentation marks the requested target now; application rendering is unchanged.

## Evidence scope

Independent source/design assessment: `/root/architecture_audit`; independent detector and component-browser assessment: `/root/design_review`; allocation/domain assessment: `/root/chart_audit`; primary-agent synthesis and proposed interactive illustration. The chart assessment and source review did not use live financial data. Existing dashboard evidence uses synthetic fixtures. The interactive recommendation is illustrative, not an implemented product screenshot or proof of financial results.

The focused detector ran once over the five relevant source/config targets and returned no findings. This does not establish usable tables: browser/source evidence exposed the group-label, chooser, pinning and semantic issues above. The browser harness imported the actual PositionsPageBase and both current header definitions, with real Vuetify and a synthetic fetcher. It isolated table behavior from full-app authentication and backend calculations; it is not an end-to-end production validation. Summary's currency reactivity remains a source-identified risk rather than a reproduced full-app failure.

The separate live detector reported clipping alongside transition/nested-card/edge findings. The measured toolbar clipping was confirmed; table/toolbar nesting and sticky-header edges were false positives, and framework transition findings did not establish a separate defect. No persistent browser overlay remains.

Current-component captures: [open desktop](assets/2026-09-08-tables/open-positions-before-desktop.png), [open mobile](assets/2026-09-08-tables/open-positions-before-mobile.png), [closed desktop](assets/2026-09-08-tables/closed-positions-before-desktop.png), [closed mobile](assets/2026-09-08-tables/closed-positions-before-mobile.png). Proposed illustrative views: [Overview](assets/2026-09-08-tables/proposed-open-overview-736.png), [Full ledger](assets/2026-09-08-tables/proposed-open-ledger-736.png).

The proposed example's open/closed and preset switches were browser-checked at 736px and 390px; the narrow toolbar fits while financial columns scroll inside their region. This is visual/interaction evidence for the proposal, not application regression testing or calculated portfolio data.

Verification covers documentation and proposal behavior only. Full frontend/backend application test gates in the implementation plan remain future execution requirements.
