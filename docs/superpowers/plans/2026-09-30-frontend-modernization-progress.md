# Frontend modernization progress

Updated 30 September 2026. This is the durable, human-facing status tracker for the accepted [master plan](2026-09-08-frontend-modernization.md). The original task numbering is retained. Update this file after each independently verified task; commit evidence and distinguish implementation, review, merge and release.

## Current checkpoint

- Implementation branch: `codex/frontend-modernization`.
- Verified remote and synchronized local code checkpoint: `9b32d3d9dbe0e8f46b7f37786e5da2bd8b79f5ae`.
- Compared with `origin/main`: 34 commits ahead, 0 behind at this checkpoint. This is a snapshot, not a completion measure.
- Financial fixes [#46](https://github.com/lym-afla/Portfolio-management/pull/46), [#47](https://github.com/lym-afla/Portfolio-management/pull/47) and [#48](https://github.com/lym-afla/Portfolio-management/pull/48) are merged into the implementation branch. Their source branches were deleted by the user.
- Main has not received the modernization branch. No deployment performed.
- 13 of 24 planned tasks have implementation/review evidence. Eleven remain, including C1, which is now unblocked.
- Last whole-foundation verification at `deea60df`: 262 frontend tests; 1261 backend tests / 10 skipped; both type checks, lint/build; 72 synthetic browser route profiles. These results predate the three merges. The combined `9b32d3d9` baseline has not been rerun in this planning turn.

## Task status

| Task | Workstream | Deliverable | Status / evidence |
|---|---|---|---|
| 1 | R1 | Runtime and verification gates | Implemented/reviewed: `1b6d803c`, `c32c33e0` |
| 2 | R8 | Typed transport foundation | Implemented/reviewed: `92228fd8`, `e2153d1f` |
| 3 | R2 | Measured header/main layout | Implemented/reviewed: `9f69dede` |
| 4 | R3 | Atomic committed context/session isolation | Implemented/reviewed: `06184e43`, `8ae59291`, `ef21af7f`; fixture repair `dd8811be` |
| 5 | R4 | Reactive effective-date presets | Implemented/reviewed: `d12f66d5` |
| 6 | R5 | Latest-request lifecycle and recovery | Implemented/reviewed: `886f430f`, `190ddcd6`, `30f310d2` |
| 7 | R6 | Dashboard widget retries | Implemented/reviewed: `66f22c5e` |
| 8 | F1 | Chart sample alignment | Merged PR #46: `607f5383` |
| 9 | F2 | Contribution boundary inclusion | Merged PR #47: `71eaa1d7` |
| 10 | F3 | Allocation percentage scale | Merged PR #48: `9b32d3d9` |
| 11 | C1 | Opt-in exact chart contract | **Next; ready to execute after combined-baseline verification** |
| 12 | R7 | Route/dialog/icon delivery | Implemented, review findings corrected: `c9711d33`, `7c1473cc`, `a1ab7ff8`; measured dashboard delivery 36.57% lower |
| 13 | D1 | Semantic tokens and scoped components | Implemented/reviewed: `55bbdaca`; rendered visual acceptance remains D3 |
| 14 | D2 | Context controls and responsive navigation | Implemented/reviewed: `deea60df`; Performance settings finding corrected, full browser gates passed |
| 15 | D3 | NAV-first dashboard/positions visual pilot | Not implemented; accepted brief prepared |
| 16 | D4 | Grouped-table views, controls/actions/dialog accessibility | Not implemented |
| 17 | C2 | Typed chart adapters and lifecycle | Not implemented; follows C1 |
| 18 | C3 | ECharts NAV pilot, both IRRs and accessible inspection | Not implemented; follows C1/C2 |
| 19 | D5 | Visual system across route families | Not implemented; follows accepted D3/D4 pilot |
| 20 | D6 | Transaction import workflow extraction | Not implemented |
| 21 | D7 | Broker/security workflow extraction | Not implemented |
| 22 | C4 | Three solid allocation pies and security histories | Not implemented; follows NAV acceptance and F3 |
| 23 | C5 | ECharts cutover and Chart.js removal | Not implemented; gate last, retain fallback until acceptance |
| 24 | D8 | All-page visual/accessibility/behavior QA and documentation | Not implemented |

## Next execution and boundaries

Execute only C1 using the [30 September handoff plan](2026-09-30-chart-contract-v2-handoff.md) and [GLM executor prompt](2026-09-30-chart-contract-v2-glm-prompt.md). The accepted full contract remains in [chart workstream C1](2026-09-08-chart-correctness-echarts.md#task-c1-add-an-opt-in-exact-chart-contract-without-removing-legacy-responses).

D3 can proceed independently with the incumbent Chart.js renderer, but is a separate assignment. After C1 is reviewed/integrated, continue D3/D4 and C2/C3 according to the master dependencies. Do not fold these tasks into the C1 PR.

C1 touches the protected `NAV_at_date` function for optional diagnostics. Earlier financial approvals do not approve this new proposal. Require a separate reviewed PR with `needs-approval`; no auto-merge into the implementation branch or main.

The final release gate is not just passing unit tests: it includes the dashboard/positions visual pilot, grouped column views, actual three solid pies, both IRRs with exact horizons, accessible chart legend/table/tooltip/zoom, complete workflow/route rollout, and D8 acceptance. CSS zoom evidence does not substitute for native browser zoom or production delivery verification.

## Detailed records

- [Master plan](2026-09-08-frontend-modernization.md): overall scope/dependencies and release criteria.
- [Reliability plan](2026-09-08-frontend-reliability-platform.md), [chart plan](2026-09-08-chart-correctness-echarts.md), [design/workflow plan](2026-09-08-frontend-design-workflows.md): accepted task specifications.
- `.superpowers/sdd/2026-09-08-frontend-modernization/progress.md`: local detailed executor ledger and rulings. This folder is Git-ignored and may not exist in another checkout; never require it as the only source of handoff context.
- `temp_files/task-14-*`: local verification logs; unavailable remotely unless supplied. The evidence above is historical, not a claim that another executor has independently verified those logs.

## Completion record template

For each task record: baseline and final commit; exact files; RED/GREEN tests; full relevant gate results; review findings and fixes; numeric/compatibility impact; PR URL and approval/merge status; deferred acceptance; next task. A task is not done because its component file exists or a PR was opened.
