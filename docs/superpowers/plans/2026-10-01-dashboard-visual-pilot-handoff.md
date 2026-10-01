# D3 Dashboard and Positions Visual Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This assignment selects inline GLM execution; do not dispatch implementers unless the user requests delegation. If the skills are unavailable, follow this written sequence and project rules directly.

**Goal:** Complete master task 15/D3 with a rendered NAV-first dashboard and a reviewed desktop/mobile positions pilot, preserving financial values and existing request behavior.

**Architecture:** Reuse D1 workspace components/tokens and D2 committed context. Introduce a display-only summary adapter and semantic metrics component, then reorganize the existing dashboard widgets. Keep current Chart.js components and data contracts; positions receive only scoped visual integration, with table behavior deferred to D4.

**Tech Stack:** Existing Vue 3, TypeScript, Pinia, Vuetify, Vitest, Vite and agent-browser. Node >=24.20.0 <25; backend uv project mode. No new production dependencies.

**Spec:** Accepted [design/workflow D3](2026-09-08-frontend-design-workflows.md#d3-build-and-review-the-nav-first-desktopmobile-pilot), [master plan](2026-09-08-frontend-modernization.md), and [grouped table/pie review](../../audits/2026-09-08-grouped-tables-and-allocation-pies.md). This handoff resolves current source gaps; read the accepted D3 section as well.

## Global constraints

- Start from the latest `origin/codex/frontend-modernization`, including PR #49 merge `7481e060850e3becdbfb4be2a5006867b91e1f77` and this documentation commit. Create `codex/dashboard-visual-pilot`. Inspect later remote changes and record the actual base; do not revert to the code checkpoint or base on main.
- Preserve local/user changes. No reset, clean, force push, destructive stash or production data mutation.
- Read `AGENTS.md`, `.memory-bank/index.md`, the AI rules and the three authoritative NAV/calculation/FX documents. PR #49 is integrated; do not reimplement C1 or change its protected diagnostics.
- Light theme first: existing brokerage blue, neutral surfaces, system font, tabular numerals. Reuse `WorkspacePage`, `WorkspaceSection`, D1 tokens/defaults and committed-context presentation. Scope styling to the pilot; no global route redesign.
- Keep all five actual summary fields, existing signs, unavailable markers and horizon meaning. No financial calculations, parsing display strings, additional currency symbols, or invented cash/YTD metrics.
- Preserve request ownership, latest-response rejection, atomic account/date/currency context, retained NAV during updates and isolated widget Retry. An unsuccessful context transition cannot relabel old values with the attempted selection.
- No C2/C3 chart adapters/renderers, v2 frontend negotiation, ECharts install, Chart.js removal, new pies, D4 table presets/toolbar/header redesign, D5 route rollout, D6/D7 extraction or migrations. The three solid allocation pies remain mandatory C4 work; retain obvious access to existing allocation tables here.
- Use synthetic populated data only. Browser automation uses agent-browser and observed element refs; no force actions. Adapt paths and shell to the executor machine, use explicit UTF-8 reads/writes, and do not depend on ignored `.superpowers/sdd/` files.

## Review focus

1. Zero, negative, unavailable and null display values survive the summary adapter without reinterpretation (task 1).
2. Pending/failed account/date changes keep visible labels tied to committed data; widget retries remain independent (task 2).
3. Mobile and actual browser zoom retain readable context, reachable controls and focus; scrolling belongs to dense content, not the entire page (tasks 2/3).
4. Dense positions with long names, two currencies and signed/missing values retain sticky identity, grouped headers, totals and sorting (task 3).
5. Populated fixture contracts and request provenance are checked; an empty table, mockup or malformed fixture cannot count as visual acceptance (task 3).

## Files and interfaces

| Path | Responsibility |
|---|---|
| `frontend/src/components/workspace/types.ts` | Add the missing `MetricDisplay` presentation type; preserve existing context types |
| `frontend/src/components/dashboard/summaryMetrics.ts` (new) | Explicit mapping of the validated direct summary dictionary |
| `frontend/src/components/dashboard/PortfolioMetrics.vue` (new) | Semantic, responsive definition list with dominant NAV |
| `frontend/src/components/dashboard/SummaryCard.vue` | Compatibility adapter if retained; no competing arbitrary-key table |
| `frontend/src/views/DashboardPage.vue` | Reading order, committed context, sections and existing widget integration |
| `frontend/src/components/dashboard/SummaryOverTimeTable.vue` | Scoped historical-section visual integration only |
| `frontend/src/components/PositionsPageBase.vue` | D1 scoped defaults/classes; preserve table implementation |
| `frontend/tests/unit/workspace/DashboardComposition.spec.ts` (new) | Summary mapping, semantic presentation and section composition |
| `frontend/tests/unit/components/DashboardPage.{retry.spec.js,requests.spec.ts}` | Preserve existing lifecycle/recovery behavior |
| `frontend/tests/unit/components/SummaryCard.spec.js` | Compatibility behavior if the component changes |
| `frontend/tests/browser/{fixtures.mjs,fixture-server.mjs,run-smoke.mjs}` | Existing synthetic harness; extend only as needed for populated pilot evidence |
| `docs/design/frontend-workspace.md` (new) | Visual choices, reproducible QA, screenshots and remaining acceptance |
| `docs/design/assets/frontend-workspace/` (new) | Real rendered synthetic screenshots |

Current-source detail: `MetricDisplay` is absent from `workspace/types.ts`. Add `interface MetricDisplay { id: string; label: string; value: DisplayValue; unitLabel?: string; explanation?: string }`, importing `DisplayValue` from `@/types/portfolioTables`. It accepts the decoder's formatted string/null boundary, not raw numbers. Render null with the established unavailable marker; preserve supplied `N/A`, `N/R`, zero and signed strings exactly.

`summaryMetrics(summary: Awaited<ReturnType<typeof getDashboardSummary>>): readonly MetricDisplay[]` maps these fields in this order:

| Source key | ID | Label / explanation |
|---|---|---|
| `Current NAV` | `nav` | Total NAV |
| `Invested` | `invested` | Invested |
| `Cash-out` | `cash-out` | Cash out |
| `total_return` | `total-return` | Total return / Since inception |
| `irr` | `irr` | IRR since inception |

Use the existing `frontend/src/services/api/dashboard.ts` decoder; its contract is a direct dictionary, not a `metrics` envelope. Use the decoder in test setup for plain fixture strings rather than weakening branded types or adding casts to hide errors. Malformed payloads remain errors at the API boundary.

`PortfolioMetrics` props: `{ metrics: readonly MetricDisplay[]; contextLabel: string }`. Render a semantic `dl` with `dt`/`dd`, stable `data-metric` identifiers and explicit source order. NAV is dominant; the four secondary values have quieter equal hierarchy. It performs no money/percentage formatting.

Dashboard reading order: committed context; portfolio values; **Value and return over time**; **Allocation**; historical reconciliation. Keep existing NAVChart props/events and surrounding renderer-neutral section; chart accessibility/legend/tooltip/zoom belong to C3. Place Account Performance as a secondary section action. Currency, account and effective date remain readable.

## Task 1: Display-only portfolio metrics

- [ ] Inspect actual summary decoder, workspace types, existing SummaryCard callers and tests; record differences from the older D3 pointers.
- [ ] Write failing `DashboardComposition.spec.ts` tests for IDs `nav, invested, cash-out, total-return, irr`, labels/horizons and exact rendering of `$0.00`, `$100.00`, `($100.00)`, `−2.40%`, `N/A`. Add null and `N/R` fixtures. Assert semantic `dt`/`dd`, all five entries and no double currency decoration. Use `decodeDashboardSummary` for fixtures.
- [ ] Run the focused test and record a genuine missing-adapter/component failure.
- [ ] Add `MetricDisplay`, `summaryMetrics` and `PortfolioMetrics` with D1 scoped styling. Keep SummaryCard as a compatible adapter if still used; switch the dashboard consumer without duplicating the metrics.
- [ ] Run the focused tests plus existing SummaryCard tests; resolve failures without deleting assertions for preserved behavior. Commit this presentation unit using the project commit template.

## Task 2: NAV-first dashboard composition

- [ ] Extend the composition tests to assert the section reading order and secondary Account Performance action. Retain the existing request/retry tests for all four widget families and committed context; add a targeted assertion if the new context markup is not covered.
- [ ] Verify the new assertions fail against the incumbent layout.
- [ ] Compose the dashboard using existing workspace components and committed context helpers. Do not duplicate shell headings or controls; account/date/currency labels come from accepted committed state, with pending state separate.
- [ ] Move NAV before allocations/history; preserve its update-params event, current data, errors and retained rendering during updates. Fit existing frequency controls with a scoped wrapping layout or labelled select on narrow screens; no chart data/adapters change.
- [ ] Integrate the historical table as a secondary reconciliation section and keep allocation table access discoverable. Preserve empty, loading, failed and retry states; do not use visual polish to conceal failures.
- [ ] Run composition, SummaryCard, DashboardPage request/retry tests, both type checks and build. Commit the layout unit. Do not claim visual acceptance from component tests alone.

## Task 3: Rendered desktop/mobile pilot and positions integration

- [ ] Apply D1 scoped defaults/classes to PositionsPageBase without rebuilding its toolbar, grouped headers or financial fields. Any functional table change belongs to D4; keep all existing columns, totals, sticky identity and sorting.
- [ ] Inspect `frontend/tests/browser/run-smoke.mjs`, `fixture-server.mjs`, `fixtures.mjs`, `auth-init.js` and the installed agent-browser skill/help. Reuse their authenticated synthetic setup and cleanup rather than inventing endpoints or touching real accounts.
- [ ] Supply complete valid synthetic dashboard and dense Open Positions fixtures: long account/security names, at least two currencies, zero/negative/unavailable values, sufficient rows and columns for scrolling; NAV with its existing series including both IRRs. Verify the displayed endpoints and selection/date/currency provenance. Changes to shared fixtures must retain all browser cases.
- [ ] Start a local preview/dev server with a recorded session/process handle. Use `agent-browser --help` (or `npx --no-install agent-browser --help` from frontend), a dedicated `design-pilot` session, observed `snapshot -i` refs, and re-snapshot after navigation/actions.
- [ ] Review populated dashboard and positions at 1440×1000, 1024×768, 390×844 and 768×1024. Confirm header clearance; readable committed context; dominant NAV trajectory; reachable controls and allocation tables; no page-level horizontal clipping; table-local scrolling with sticky identity and usable headers/totals.
- [ ] Verify keyboard navigation/menu open-close, visible focus and actions at **actual browser 200% zoom**. CSS zoom or viewport scaling is not equivalent evidence. If native zoom is unavailable, report that gate as unverified; do not mark it passed.
- [ ] Inspect computed contrast against WCAG AA: normal text >=4.5:1, large text >=3:1, and relevant control/focus contrast >=3:1. Document actual measured pairs, not just token names.
- [ ] Save real rendered images: `pilot-desktop.png`, `pilot-mobile.png`, `pilot-mobile-nav.png`, `pilot-positions-desktop.png`, `pilot-positions-mobile.png` in the evidence directory. Capture mobile navigation open. Label all evidence synthetic and record viewport/zoom/commit.
- [ ] Batch the first desktop/mobile review, fix the identified defects together, then make one confirmation pass; perform further checks only for unresolved behavior or newly introduced defects. Image generation/mockups/empty screens cannot replace rendered QA.
- [ ] Write `docs/design/frontend-workspace.md` with hierarchy, spacing, density, action placement, reproduction steps, screenshots, failures/corrections and acceptance limits. The incumbent NAV lacks the equivalent accessible data table: record it as outstanding C3 work, not as a passed chart accessibility gate. D4 grouped presets and C4 three solid pies remain outstanding too.

## Verification and delivery

First establish a current baseline after the merged C1; historical counts are evidence, not expected assertions. Run commands from frontend with the locked Node runtime on PATH, using a workspace UV cache for API generation when needed:

```text
npm run test:unit -- tests/unit/workspace/DashboardComposition.spec.ts tests/unit/components/DashboardPage.retry.spec.js tests/unit/components/DashboardPage.requests.spec.ts tests/unit/components/SummaryCard.spec.js
npm run test:unit
npm run type-check
npm run type-check:reliability
npm run lint
npm run api:types:check
npm run build
npm run test:browser
```

The browser smoke suite validates route/layout/context/date/request/recovery regressions; it does not replace populated visual review or native zoom. Inspect its current supported `--case` values before using focused cases. Run full pytest from backend with test settings, live external tests disabled and `uv run python -m pytest`, as required by project rules. Record all command exit codes, test counts, lint baseline and any transient failure honestly. No generated API drift or additional lint warnings accepted. Do not change protected financial code to fix an unrelated baseline failure.

- [ ] Obtain scoped technical review of final UI/lifecycle changes, plus inspect rendered evidence; correct important findings with focused regressions. Do not substitute technical review for human visual acceptance.
- [ ] Close the agent-browser session and stop all servers/processes started for this task; verify cleanup.
- [ ] Update the durable progress tracker and D3 checkboxes with base/head, tests, visual evidence, review findings and deferred acceptance. Distinguish implemented/review-ready, human visual acceptance, integration and release.
- [ ] Push `codex/dashboard-visual-pilot` and open a draft PR into `codex/frontend-modernization`. Include screenshots, display-value preservation, tested states and remaining C3/D4/C4 gates. No financial approval label is needed solely for presentation; if scope unexpectedly touches protected logic, stop that change and propose it separately under project rules.
- [ ] Stop after the review-ready D3 PR. Do not merge, deploy, start D4/C2/C3 or claim the whole modernization complete. If publication/browser capability is unavailable, preserve completed work and state exactly which evidence remains missing.

**Completion:** D3 is review-ready only with preserved values/lifecycle, passing gates, populated rendered desktop/mobile dashboard and positions evidence, and documented limitations. Human visual acceptance precedes D5 rollout. Main release still requires the remaining master tasks.
