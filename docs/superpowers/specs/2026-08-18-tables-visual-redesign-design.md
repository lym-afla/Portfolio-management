# Tables & Visual Redesign — Design Spec

Date: 2026-08-18
Source: `$impeccable critique` run (snapshot: `.impeccable/critique/2026-08-18T05-52-23Z__frontend-src.md`, score 14/40)
User decisions: tables & grouped headers first; keep two-row grouped headers; all issues in scope; flatten the 3rd header level; structural/layout critique welcome, not just cosmetics.

## Problem

The frontend is stock Vuetify with no design system: no palette or type scale in `main.js`, system-ui everywhere, no `tabular-nums` in a numeric app, a Vuetify 2 CSS variable (`--v-primary-base`) referenced in Vuetify 3 (silently broken accents), debug markup rendered into production headers, center-aligned numbers, three divergent table-header systems across sibling pages, sorting affordances that do nothing, and pies without tooltips as the primary breakdown visualization.

## Scope

All frontend visual/UX work on dashboards, tables, and charts. **No changes to backend, API contracts, or financial logic.** Purely presentational + client-side interaction. (AGENTS.md protected code untouched.)

## 1. Positions tables (core deliverable)

### One shared grouped-table component

Replace the three divergent header implementations (`OpenPositionsPage.vue` hand-rolled `<thead>`, `ClosedPositionsPage.vue` one-row `#header` slot, `PositionsPageBase.vue` built-in grouping) with a single declarative grouped-header layer used by both pages:

- Header config stays an array of groups with `children` (the model already exists).
- The component renders a **two-row `<thead>`**: row 1 = group cells (`scope="colgroup"`, `colspan` = leaf count), row 2 = leaf cells (`scope="col"`). Non-grouped columns use `rowspan="2"` in row 1.
- One header system means the TOTAL/footer row is generated from the same flattened header list — deleting the magic `colspan="6"`/`colspan="10"` in `OpenPositionsPage.vue`.

### Flatten the third nesting level

Cap nesting at two rows table-wide. The `Current > Gain/Loss > Realized/Unrealized/%` branch becomes prefixed leaves under a single Current group: `Realized G/L`, `Unrealized G/L`, `Total Return %` (exact names finalized during implementation against existing column semantics). Entry/Exit groups unchanged: `Date / Price / Value` leaves.

### Numeric presentation

- All money/percent/quantity leaf columns: `align: 'end'`; Type/Name stay `align: 'start'`.
- Global `font-variant-numeric: tabular-nums` (theme-level, applies to all numeric rendering including dashboard cards).

### Navigability

- **Sticky first column** (Type + Name): `position: sticky; left: 0` with solid background (theme surface) so it survives horizontal scroll. For Open Positions' two leading columns, Type sticky at `left: 0` and Name at a computed offset, or a combined sticky cell — implementation decides, requirement is that row identity is always visible.
- **Group separation that survives without reading the header**: subtle background tint on the group row plus a vertical border between groups (entry | current | exit), applied to header and body cells via the group index.
- `aria-sort` on sortable leaf headers; remove decorative sort icons from non-sortable ones.

### Column load: analyst default vs full ledger

- Introduce per-page **default visible columns** (~10–12 high-value ones: identity, entry trio, current value, total G/L, total return %) with a column-visibility toggle (Vuetify menu in the table toolbar) persisted in the existing `useTableSettings` store. All columns remain available; nothing is removed.

### Sorting honesty

`PositionsPageBase.vue` fetch already accepts `sortBy` — wire server-side sorting end-to-end and remove `disable-sort`. If a column is genuinely unsortable server-side, mark `sortable: false` so no icon renders.

## 2. Theme & typography (`$impeccable colorize`)

- Define a real Vuetify 3 theme in `main.js`/plugin: primary/secondary/surface/positive/negative palettes (light; dark later if wanted), keeping financial semantics in mind (positive/negative gains must not rely on color alone — pair with sign/arrow).
- Typography: keep a system stack but make it deliberate; add the numeric layer (`tabular-nums`), define a compact type scale, and use Vuetify density consistently (one density across tables, `compact` recommended).
- Replace every `var(--v-primary-base)` / hardcoded `#f8f9fa` / `rgba(0,0,0,…)` with `rgb(var(--v-theme-*))` tokens — kills the broken `SummaryCard.vue` accent and the detector's side-tab finding (replace the 4px side border with a full subtle surface variant or a small icon accent).
- Chart colors and label colors derived from the same theme tokens (`chartConfig.js`).

## 3. Charts (`$impeccable distill`)

- Breakdown pies → **sorted horizontal bar charts** with value + % labels; keep pie only if a breakdown has ≤4 slices. Removes the 50px-padding and forced-outside-label hacks.
- Restore tooltips everywhere (currently disabled on pies).
- NAV chart: fix the all-zero-portfolio "no data" false negative; error state renders *above* the chart, not below.

## 4. Layout & IA (structural critique)

- **Dashboard grid**: currently widgets drop in natural rows with no hierarchy. Establish an explicit grid: primary NAV number + NAV chart get the top band at full width; KPI summary cards next; breakdown charts last. One clear focal point per viewport.
- **App bar**: the fixed `paddingTop: 140px` body hack is brittle. Use Vuetify's layout system (`v-layout` + `v-app-bar`) so content offsets are computed, not hardcoded.
- **Error surfacing**: table/widget fetch errors get an inline retry action in the widget, not only the global 5-second snackbar (WCAG 2.2.1). Snackbar stays for transient success messages only.
- **Frequency toggle**: `D W M Q Y` → labeled buttons or a select with full words (Day/Week/Month/Quarter/Year), or short labels with tooltips.
- **Empty states**: distinguish "no data for this account" from "no results after filters" with distinct copy and a next-step CTA (e.g. "Import transactions").
- Clean the contradictory global `td { white-space: normal }` vs `.nowrap-table td { nowrap }` rules into one table-scoped rule.
- Tooltip glossary for domain terms (IRR, Total Return %, BoP/EoP NAV) via `v-tooltip` on header cells and KPI labels.

## Out of scope

Dark mode, i18n, saved views sharing via URL, CSV export UI, keyboard shortcuts beyond standard tab navigation (candidates for a follow-up).

## Implementation order

1. Theme foundation (tokens, tabular-nums, density, replace broken variables) — unblocks everything else.
2. Shared grouped-table component + Open/Closed positions migration.
3. Sorting wiring + column-visibility defaults.
4. Charts (bars, tooltips, NAV fixes).
5. Dashboard grid, app bar, error/empty states, glossary tooltips.
6. `$impeccable polish` pass + re-run `$impeccable critique`.

## Testing

- Frontend unit/component tests for the grouped-table component (rendering, scope attributes, colspan generation, sticky/alignment classes, column toggle persistence).
- Visual verification via browser after each milestone.
- No backend/pytest impact; CI green.
