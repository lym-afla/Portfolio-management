# GLM-5.3 executor prompt — C1 exact chart contract

You are implementing one bounded task in the Portfolio Management repository. Complete master task 11/C1 (the opt-in exact chart contract) and prepare its separate review PR. Work inline. Do not implement the whole modernization or delegate unrelated work.

## Starting point

Repository: the Portfolio Management checkout on your executor machine. The source-machine path was `D:/Project Y/Portfolio management`; use your actual local checkout path. PowerShell examples in the plan may be adapted to your host shell while retaining uv project mode and the locked Node runtime.

Base: `origin/codex/frontend-modernization`. Verified code checkpoint: `9b32d3d9dbe0e8f46b7f37786e5da2bd8b79f5ae` on 30 September 2026. PR46 chart sample alignment, PR47 contribution lower-bound inclusion and PR48 percentage scale are merged into that branch; their old branches were deleted. Do not reimplement/cherry-pick those fixes. Main has not received the modernization work.

Fetch/check current remote state and create `codex/chart-contract-v2` from the implementation branch. If the remote moved, inspect its intervening changes and record the actual base. Preserve user changes and locally supplied planning documents; no reset/clean/destructive stash operations. Do not use main as your implementation base.

## Read before coding

1. `AGENTS.md`, `.memory-bank/index.md`, `.memory-bank/Rules for AI Coding Agent.md`.
2. `.memory-bank/Product Overview/Portfolio NAV.md`, `.memory-bank/Steerings/Calculation Conventions.md`, `.memory-bank/Tech details/NAV Function and FX Flow.md`.
3. `docs/superpowers/plans/2026-09-30-frontend-modernization-progress.md`.
4. `docs/superpowers/plans/2026-09-30-chart-contract-v2-handoff.md`: execute its numbered tasks and full embedded C1 specification.
5. The master scope/dependencies in `docs/superpowers/plans/2026-09-08-frontend-modernization.md` and accepted C1 section in `docs/superpowers/plans/2026-09-08-chart-correctness-echarts.md`.

The 30 September documents are committed to the implementation branch with this handoff. Pull the latest branch before reading them and create the C1 proposal branch from that updated checkpoint so the plan travels with the work. Do not check out the earlier code checkpoint just to reproduce its hash. Do not depend on the Git-ignored `.superpowers/sdd/` folder being available remotely.

## Implement exactly this scope

Keep legacy endpoint behavior without `chart_contract`. Explicit `chart_contract=2` adds `chartV2` to NAV/allocation objects; security histories use `{legacy: unchangedArray, chartV2: ChartDocument}`. Use the full schema from the plan: no minimal replacement.

Capture raw Decimal strings, backend-scaled plot values, exact sampled ISO endpoints/period intervals, stable source IDs, context/account membership, units, statuses/reasons and display strings at the existing calculation sources. Never parse formatted legacy values, infer IDs from labels or dates from period captions. Preserve duplicate-name account grouping and both actual IRR horizons, including first-point inception behavior. Never relabel interval IRR as trailing-twelve-month IRR.

Add only minimum optional keyword-only omission diagnostics to `NAV_at_date` in `backend/services/nav.py`. It is protected by name even outside models.py. Default calls/returns, valuation fallbacks, formulas, grouping and caches remain compatible. Missing/omitted valuation becomes explicit unknown/partial metadata, never zero or complete NAV; use knownSubtotal only as a partial subtotal. Incomplete terminal NAV makes modern IRR unavailable without changing legacy IRR.

For allocations emit backend-certified pie eligibility using complete raw Decimal amounts and the full positive NAV denominator. Preserve signed data, exact ratio shares, stable ordering and nonpartitioning legacy semantics. Test 25/75 against100, -25/125,25/50, missing valuation and zero/negative totals. Do not manufacture Other, take absolute values, omit negatives or renormalize visible data.

Security metadata comes before float serialization, preserves ordered same-day events with unique source keys, and labels bond 98.5 as percent_of_nominal 98.5. Enforce existing authorization and generic errors. V2 invalid queries return400 INVALID_CHART_QUERY; calculation failures return500 CHART_CALCULATION_FAILED; genuine emptiness returns200 with outcome empty. Absent-v2 legacy behavior remains unchanged.

No ECharts install/renderers, frontend redesign, pies, grouped tables, import/broker refactors, schema migrations or Chart.js removal in this task.

## Verification and delivery

First verify the combined merged baseline. Last foundation counts 262 frontend/1261 backend were before those merges; do not report them as your current results. From backend use uv project mode and test settings. Run merged regressions:

- `tests/unit/services/test_chart_alignment.py`
- `tests/integration/services/test_chart_contribution_boundaries.py`
- `tests/unit/services/test_allocation_percentage_scale.py`

Then write failing tests first, observe RED, implement minimally and verify GREEN. Required new API suite: `backend/tests/integration/api/test_chart_contract_v2.py`; pure value tests and protected diagnostics output-equivalence fixtures as detailed in the plan. Include real Decimal, missing/zero/signed values, duplicate account names, partial buckets and both IRRs. Run full pytest, required core coverage, generated API drift, frontend unit/types/lint/build and scoped technical review. Use installed Node24.20.x; backend commands from backend with `uv run`. Explicit UTF-8 file reads/writes; synthetic fixtures only. Fix actual failures without dropping assertions or changing formulas to satisfy tests.

Keep an execution ledger and update the durable progress tracker with base/final commit, files, actual tests/exit codes, coverage, review findings, compatibility/numeric impact, deferred acceptance and PR state. Explain inherited coverage gaps; never mark unmet gates green.

Prepare a draft PR from `codex/chart-contract-v2` into `codex/frontend-modernization`, label `needs-approval`, following the project's required financial-review format. New protected diagnostics need separate human approval; earlier F approvals do not approve this change. Include exact legacy equality, numeric fixtures, changed protected paths and limitations. Attach the PR if your environment supports it. If publication capability is unavailable, leave the exact review-ready branch/diff and PR body and explicitly report that limitation.

Do not merge into either branch or deploy. Stop after the review-ready C1 proposal; do not start C2/C3/D3. Report implemented scope, RED/GREEN and full gate results, PR/commit, remaining approval/blockers and what is still outstanding. The broader modernization is incomplete.
