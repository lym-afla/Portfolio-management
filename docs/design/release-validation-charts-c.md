# Release validation phase C — charts and security presentation (Tasks 6–7)

Evidence ledger for phase C of the [correction plan](../superpowers/plans/2026-10-09-release-validation-fixes.md).
Branch `codex/release-validation-charts-c`, dedicated worktree `Portfolio-management-charts-c`, base `2d80e359`
(PR #63/phase B merged; verified remote tip before branching). Draft PR into `codex/frontend-modernization`; stops for review — no merge, no deployment, no C5b, no palette change.

## Task 0 — baseline and inventory (source-confirmed before any edit)

Baseline gates on the pristine base `2d80e359` in this worktree (sequential, actual exit codes):

| Gate | Result | Exit |
|---|---|---|
| `test:unit` | 1084 passed / 3 failed — the known canvas-heavy timeout flake class under machine load (`allocation.spec.ts` ×2, `securityHistory.spec.ts` ×1, 20–21 s timeouts); isolated rerun of both files: all green | 1 → clean rerun 0 |
| `type-check` / `type-check:reliability` / `type-check:charts` | clean | 0 / 0 / 0 |
| `api:types:check` | clean | 0 |
| `lint` | 0 errors / 8 warnings (baseline unchanged) | 0 |
| `build` | clean | 0 |

Source-confirmed inventory relevant to Tasks 6–7 (each verified by reading the base code, not assumed):

- **NAV option** (`features/charts/buildNavOption.ts`): both y-axes draw ECharts default `splitLine`s (two competing grids); tooltip appends per-line unit suffixes (`(USD)`), per-IRR horizon date-range brackets, and a trailing `Portfolio NAV (all categories)` totals line; totals also exist in `ChartDataTable` (`document.totals` column).
- **Legend** (`ChartLegend.vue`): every button carries a 1px border plus a selected inset ring (the "heavy outline").
- **Inspection card** (`ChartInspection.vue`): a separate bordered card duplicating exact values, plus the only keyboard-operable zoom selects (Start/End period) and Reset zoom button.
- **Exact tables** (`ChartDataTable.vue`, `SecurityDataTable.vue`): always rendered, never collapsed; the security table renders every observation with no pagination (distinct same-date keys stay distinct rows via `period.key`).
- **Pies** (`buildAllocationOption.ts`): labels are category names at the default outside position, so ECharts draws leader lines (`labelLine` default visible); no slice separators; percentages exist only in tooltip/table/legend aria-labels, never on the pie.
- **Sharpness**: all three ECharts wrappers register `CanvasRenderer`; zrender's canvas painter fixes `devicePixelRatio` at construction and `Painter.resize(w, h)` never re-reads it, so a native-zoom DPR change after init CSS-scales the stale backing store (blur). `zrender.ZRender.prototype.resize` takes no dpr; `echarts.init`'s `opts.devicePixelRatio` is init-only. Re-initialization is the only public-API way to change backing resolution.
- **Geometry**: NAV pilot renders inside `NAVChart.vue`'s `#chart` slot (`.chart-wrapper`, 16px padding, inside `v-card-text`); the dashboard's other sections are `WorkspaceSection`s; security charts render inside `WorkspaceSection` content at 320px canvas height. Rendered measurements recorded in the acceptance section below.
- **Security account selector** (`views/database/SecurityDetailPage.vue` + `features/securities/useSecurityDetail.ts`): local model starts `null` (v-select shows an empty field while the request is unfiltered); options come from `getAccountChoices` whose first group offers `All accounts → {type:'all', id:null}`.
- **Holdings context backend inventory**: `get_security_detail` (`backend/services/securities.py`) exposes `open_position`/values scoped by the optional account filter but **no per-account holdings breakdown**. Canonical primitives exist: `services.positions.position` (per-account sums; handles crypto commission/option cash-flow depletion) and `services.positions.get_accounts_with_positions` (non-zero accounts at a date — no production caller today). `Accounts` carry `broker` (name), `is_active`; `format_account_display` builds qualified display names.

## Findings and resolution status

Populated per task as commits land; every row distinguishes source-confirmed cause, reproduced cause and still-unverified hypothesis.

| Owner requirement | Task | Status |
|---|---|---|
| Charts span their content section, aligned with page edges | 6 | pending |
| Sharp at native 200% zoom | 6 | pending |
| Secondary-axis grid removed; simplified tooltip/legend borders | 6 | pending |
| Inspection card removed; zoom/reset + keyboard inspection retained | 6 | pending |
| Exact tables collapsed behind labelled buttons; observation pagination 25/50/100 | 6 | pending |
| Pies: no leader lines, white separators, certified percentage labels | 6 | pending |
| Unfiltered security selector visibly says "All accounts" | 7 | pending |
| Current/previous broker-account holdings as of valuation date | 7 | pending |

## Gates on the committed head

Recorded after all tasks land (sequential, actual exit codes).

## Captures

Synthetic-only captures land under `docs/design/assets/charts-c/`.
