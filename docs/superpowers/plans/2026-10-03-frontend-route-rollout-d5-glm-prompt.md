# GLM executor prompt — D5

Fetch the latest `origin/codex/frontend-modernization` and read `AGENTS.md`, `.memory-bank/index.md`, the modernization progress tracker, and `docs/superpowers/plans/2026-10-03-frontend-route-rollout-d5-handoff.md`.

PR #53/C3 is merged. Execute D5 only on a new `codex/frontend-route-rollout-d5` branch from the updated modernization branch. Follow the handoff's tasks and route-family acceptance checks: extend the accepted workspace design to Performance, Data routes, profile/auth and remaining forms; preserve the existing D4 tables/actions. Performance needs a compact single-period view with explicit comparison/full-history access, preserving every metric and exact formatted value.

The account-selector `[object Object]` fix is being handled separately: do not duplicate it. ECharts stays default-off; no backend/financial changes, chart cutover, allocation pies, D6/D7 extraction, merge or deployment.

Establish the current baseline, write meaningful failing regressions before behavior changes, commit by route family, and record real browser review in `docs/design/frontend-route-review.md`. Preserve all URLs, API payloads, dialog events, request/session ownership, precision and comma thousands separators. Apply global defaults only after individual families pass, then recheck D3/D4/C3. Use agent-browser with backend-faithful synthetic fixtures, native 200% zoom and actual hit-testing.

Run the complete handoff gate matrix on committed code with captured process exit codes. Update the tracker and evidence honestly, distinguishing screenshots/DOM checks from real screen-reader testing. Push and open one draft PR into `codex/frontend-modernization`; stop for review and report the tested SHA, results, screenshots, deviations and remaining acceptance.
