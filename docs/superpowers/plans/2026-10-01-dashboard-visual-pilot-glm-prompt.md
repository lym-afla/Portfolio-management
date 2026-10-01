# GLM-5.3 executor prompt — D3 dashboard visual pilot

Implement one bounded task in the Portfolio Management repository: master task 15/D3, the NAV-first dashboard and desktop/mobile positions visual pilot. Work inline using the committed handoff; do not implement the entire modernization.

## Starting point

Use your actual checkout path and host shell. Fetch and pull the latest `origin/codex/frontend-modernization`, including the D3 handoff documents. PR #49 is merged at `7481e060850e3becdbfb4be2a5006867b91e1f77`; C1 diagnostics and the four review corrections are integrated. PRs #46/#47/#48 are also merged. Do not reimplement them or check out an earlier checkpoint.

Create `codex/dashboard-visual-pilot` from the updated implementation branch. Record the actual base and inspect any later changes. Preserve user changes; no reset/clean/force push/destructive stash. Do not base on main or depend on ignored `.superpowers/sdd/` documents.

## Read before implementation

1. `AGENTS.md`, `.memory-bank/index.md`, `.memory-bank/Rules for AI Coding Agent.md`, and the authoritative NAV/calculation/FX documents named there.
2. `docs/superpowers/plans/2026-09-30-frontend-modernization-progress.md`.
3. `docs/superpowers/plans/2026-10-01-dashboard-visual-pilot-handoff.md`: execute its three tasks, constraints and acceptance gates.
4. D3 in `docs/superpowers/plans/2026-09-08-frontend-design-workflows.md`, master dependencies, and `docs/audits/2026-09-08-grouped-tables-and-allocation-pies.md`.

Use relevant installed planning/execution/design/browser skills when available. The accepted plan already selects the work; do not restart discovery or ask the user to approve routine implementation choices. No implementer delegation unless requested. Obtain a scoped technical review before submission if your environment supports it; report any review limitation.

## Required result

Recompose the dashboard in this order: visible committed context; portfolio values with dominant Total NAV; Value and return over time; Allocation; historical reconciliation. Reuse D1 workspace tokens/components and D2 committed context. Keep brokerage blue, neutral light surfaces, system font and tabular numbers; make hierarchy and spacing deliberate, with responsive controls.

The actual summary response is a direct dictionary: `Current NAV`, `Invested`, `Cash-out`, `total_return`, `irr`. Add the currently missing `MetricDisplay` type, a display-only `summaryMetrics` adapter and `PortfolioMetrics` semantic definition list as specified in the handoff. Preserve all five values in explicit order. Use the existing decoder in fixtures to honor branded display types. Preserve formatted strings and null/unavailable values; do not parse money, duplicate currency symbols, hide zeros/losses, turn Cash-out into Cash balance, or relabel lifetime IRR as YTD.

Keep the incumbent Chart.js NAV props/events and rendering lifecycle. Preserve stale-request rejection, committed account/date/currency labels, retained NAV during updates and independent widget Retry. Place chart controls responsively and Account Performance as a secondary action. Keep allocation table access obvious.

PositionsPageBase receives scoped visual integration only. Review a populated dense Open Positions table on desktop/mobile with long names, multiple currencies and signed/missing values; preserve existing grouped headers, all columns, totals, sorting and sticky identity. Full grouped-column presets and toolbar redesign remain D4.

No ECharts, frontend chart-v2 adapter/negotiation, financial/backend edits, pie implementation, Chart.js removal, route-wide rollout or import/broker refactors. C4 still requires three solid allocation pies; C3 still owns the accessible NAV table/legend/tooltip/zoom. Do not mark those requirements satisfied by this layout pilot.

## Verification and submission

Establish the current baseline, write focused behavior tests first and observe RED/GREEN for new summary/composition behavior. Run the complete frontend unit suite, both type checks, lint with no new debt, API type drift and production build; run browser smoke and full backend pytest under uv/test settings as specified in the handoff. Never present historical counts as your current results. Record transient failures and reruns honestly.

Use agent-browser for real rendered QA through the existing complete synthetic fixture/auth harness; inspect help and source before starting it. Review dashboard and dense positions at 1440×1000, 1024×768, 390×844 and 768×1024, plus keyboard/menu/focus and actual browser 200% zoom. CSS scaling is not native zoom. Report unavailable gates explicitly. Check header clearance, readable committed context, reachable actions, table-local scrolling and measured contrast. Save the five named synthetic screenshots and reproduction/decision notes under `docs/design/` as the plan requires. Mockups and empty-state screenshots are insufficient.

Fix review findings, clean up all servers/browser sessions, and update the durable tracker with base/head, exact gates, rendered evidence, review/integration state and remaining tasks. Push `codex/dashboard-visual-pilot`; open a draft PR into `codex/frontend-modernization` with screenshots and concise compatibility/validation details. Attach the PR if supported. If tooling prevents publication or visual evidence, preserve the work and identify the unsatisfied acceptance.

Stop after the independently reviewable D3 proposal. Do not merge either branch, deploy or start D4/C2/C3. Report the PR/commits, implemented scope, test and visual results, remaining human visual acceptance and limitations. The broader modernization is incomplete.
