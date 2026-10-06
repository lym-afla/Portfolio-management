# GLM prompt — C4

Fetch latest origin/codex/frontend-modernization (PR #58 is merged). Read AGENTS.md, the progress tracker and docs/superpowers/plans/2026-10-06-allocation-security-charts-c4-handoff.md with its linked accepted C4 design.

Implement only C4 on codex/allocation-security-charts-c4 in a dedicated worktree: three solid allocation pies (Asset Type, Asset Class, Currency) plus price/position history renderers behind separate default-off gates. Preserve backend-certified eligibility, full-NAV denominator, exact decimal/display strings, stable identities and units. Ineligible allocations show reasons and complete tables; legends highlight without hiding or renormalizing slices.

Reuse C1/C2 validation, C3 renderer/fallback patterns and D7's existing security request owner. No duplicate request owners, backend/financial changes, NAV redesign, default-on rollout, Chart.js removal, C5/D8 work, merge or deployment. Preserve D7 broker fixes and mobile pagination. Screen-reader audits are out of scope; keyboard/focus, exact tables, responsive/native-zoom checks remain required.

Follow RED-first tasks, commit allocation/security work separately, run the full committed-head gate matrix with actual exit codes and all flag combinations, and inspect synthetic captures. Update evidence/tracker, push and open one draft PR into codex/frontend-modernization. Stop for review; report tested SHA, results, screenshots, deviations and unresolved requirements.
