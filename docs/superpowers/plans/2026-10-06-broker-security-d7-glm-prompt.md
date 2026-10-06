# GLM prompt — D7

Fetch latest origin/codex/frontend-modernization (PR #57 is merged). Read AGENTS.md, the progress tracker and docs/superpowers/plans/2026-10-06-broker-security-d7-handoff.md with its linked D7 design.

Implement only D7 on codex/broker-security-extraction-d7 in a dedicated worktree. Characterize the current provider and security contracts first. Extract broker lists/forms/API ownership and security overview/metadata/activity with one request owner, preserving provider-specific payloads, safe secret handling, exact action identity, request/session lifecycle, financial strings and existing charts. Prove overlapping old/new requests and dialog callbacks with RED-first behavioral tests. Keep broker and security changes in separate commits.

No backend/financial/import protocol changes, C4/C5/D8 implementation, ECharts enablement, merge or deployment. Dedicated screen-reader audits are out of scope; keyboard/focus, labels, contrast, responsive/native-zoom and semantic checks remain required.

Run the full handoff gate matrix on committed code with real exit codes, including imports-d6 and the new brokers-security-d7 browser case. Explicitly type-check new TS tests. Update evidence and tracker, push and open one draft PR into codex/frontend-modernization. Stop for review and report tested SHA, results, screenshots, deviations and remaining issues.
