# GLM prompt — D6

Fetch latest `origin/codex/frontend-modernization` (PR #56 is merged), read AGENTS.md, the progress tracker and `docs/superpowers/plans/2026-10-05-transaction-import-d6-handoff.md`, including its linked accepted D6 interfaces.

Execute only D6 on `codex/transaction-import-d6` in a dedicated worktree. Characterize every current import command/message and decision branch before extracting the transaction importer into one typed state owner, a validated legacy-protocol boundary, an orchestrator and small step components. Preserve exact payloads, financial strings, all result counters/warnings, parent events, account/security/transaction decisions and stop acknowledgment semantics. No automatic replay, duplicate starts or stale callbacks crossing runs.

Reuse the existing analyzer/WebSocket implementation and reviewed D5 UI/focus patterns. No backend/financial/protocol changes, D7/C4/C5 work, ECharts cutover, merge or deployment.

Follow RED→GREEN tasks and the full committed-head gate matrix, including synthetic file/API WebSocket browser flows. Update evidence/tracker, push and open one draft PR into `codex/frontend-modernization`. Stop for review; report tested SHA/directory, actual exit codes, screenshots, deviations and acceptance gaps honestly.

Scope amendment (5 October 2026): dedicated screen-reader support and assistive-technology audits are removed from the plan, including D8. Do not list their absence as an acceptance gap. Keep keyboard/focus, readable labels, contrast, responsive/native-zoom checks, semantic markup and exact-value tables. This is a planning change, not an instruction to remove existing application support.
