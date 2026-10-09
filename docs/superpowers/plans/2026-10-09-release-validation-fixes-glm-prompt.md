# GLM handoff — real-data correction phase A

Fetch the latest origin/codex/frontend-modernization and read docs/superpowers/plans/2026-10-09-release-validation-fixes.md plus the modernization progress tracker and repository instructions.

Implement phase A only (Tasks 1–3: dates/inception, year options/performance/security resource failures, account-based price import/progress readability). Create codex/release-validation-functional-fixes in a dedicated worktree from the latest modernization tip. Preserve other executors' checkouts.

The owner's annotated findings are transcribed in the plan; the original H: file is not required. Treat GLM's previous 11/11 result as partial display-parity evidence, not release acceptance. Reproduce each finding before changing code; use actual backend wire shapes and synthetic regression fixtures. Identify root causes rather than hiding errors or weakening validation. Do not assume every issue needs a backend change.

Use failing regressions first and task-sized commits. Follow the plan's privacy, numeric and protected-code boundaries. If financial/protected backend changes are required, isolate them into a draft PR with needs-approval and numeric regression evidence; do not merge. Never run imports or recalculations against the owner's original database.

Run the specified gates sequentially on committed code and record actual exit codes. Keep a per-finding evidence ledger, including any unresolved or unavailable reproduction. Update the progress tracker. Push and open bounded draft PR(s) into codex/frontend-modernization, then stop for review.

Do not start phases B–D, choose a dashboard-summary redesign, remove Chart.js, implement C5b, merge or deploy. If a finding cannot be reproduced, document the exact tested context and continue independent tasks; do not mark it fixed without evidence.
