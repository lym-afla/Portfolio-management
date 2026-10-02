# GLM-5.3 executor prompt — C2 chart adapters

Pull the latest `origin/codex/frontend-modernization` (includes user-merged PR #51 at `297fb95c` and this handoff). Read AGENTS.md, the project memory-bank rules, `docs/superpowers/plans/2026-09-30-frontend-modernization-progress.md`, the accepted chart plan, and `docs/superpowers/plans/2026-10-02-chart-adapters-c2-handoff.md`.

Create `codex/chart-adapters-c2` from that branch and implement C2 only, following the five handoff tasks with failing regressions first and scoped commits. Preserve C1 decimal strings, status/identity/date semantics and the existing Chart.js renderer. Use the real C1 wire contract and shared request lifecycle. Pay special attention to historical dateTo versus committed effective date, current-generation-only context reconciliation, no duplicate dashboard watchers, malformed-v2 failures without silent fallback, and permanent unmount/session cancellation.

No ECharts/pies/security rollout, backend/financial changes, D5/C3 work or dependency migration. Keep the legacy API facade compatible; no second request manager or chart-derived financial calculations.

Run required gates with actual exit codes, update the committed design evidence and progress tracker honestly, push your branch and open a draft PR into `codex/frontend-modernization`. Do not merge, deploy, or start C3. Report commit/PR, scope, regression evidence, gate results, limitations and remaining acceptance.
