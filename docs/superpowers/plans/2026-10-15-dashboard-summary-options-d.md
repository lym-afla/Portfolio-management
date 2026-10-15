# Phase D dashboard summary design-options implementation plan

> **For agentic workers:** Use superpowers:executing-plans to execute this design-only handoff task by task. Stop for the owner's composition choice before production implementation.

**Goal:** Deliver three comparable, inspectable dashboard-summary designs for owner selection.

**Architecture:** Isolated synthetic preview artifacts under docs/design; the live dashboard, request owners and financial calculations remain unchanged. All alternatives use the same field inventory and scenario strings.

**Tech stack:** Existing Vue/Vuetify design language; standalone HTML/CSS/JavaScript preview with no new dependency or remote runtime required.

**Spec:** docs/superpowers/plans/2026-10-09-release-validation-fixes.md, Task 8.

**Verified base:** origin/codex/frontend-modernization at 7a917827, after PR #64 merge. Fetch current remote before starting; do not use main or an old PR branch.

## Constraints

- This assignment is D-design only. Production implementation follows an explicit owner selection and a separate implementation handoff.
- Preserve every existing metric, its meaning, units, period, scope, exact display and zero/missing distinction. No invented financial formulas, client-side recomputation or implied accounting reconciliation.
- Preserve comma-grouped amounts and exact large/decimal strings. Never pass financial display strings through Number.
- Existing palette only; no chart redesign, backend changes, Chart.js removal/C5b, deployment or real portfolio data/screenshots.
- Retain keyboard operation, visible focus, readable contrast, responsive layout and semantic labels. Dedicated screen-reader work remains out of scope.
- Use a dedicated worktree and new codex/dashboard-summary-options-d branch. Do not disturb other checkouts.

## Task 1 — Establish the source-backed content inventory

- [ ] Read AGENTS.md, .memory-bank/index.md and its financial conventions, the parent Task 8 plan, and the current progress tracker.
- [ ] Trace frontend/src/views/DashboardPage.vue and frontend/src/components/dashboard/SummaryCard.vue through their actual API/projection sources; locate any renamed files rather than assuming paths.
- [ ] Create docs/design/dashboard-summary-options-d.md with a field matrix: source key, current label, meaning, unit, horizon/context, exact display, missing/status handling, and placement in each alternative.
- [ ] Identify which figures do and do not reconcile. Do not draw subtotal/equals/bridge relationships unless source semantics justify them. Record uncertainties explicitly.
- [ ] Define shared synthetic scenarios: ordinary positive, loss/negative, genuine zero, missing/unavailable/partial where supported, long labels/currency values, and beyond-safe-integer precision. Use identical strings in all alternatives; do not invent a server status unsupported by this surface.

## Task 2 — Build three comparable previews

Create docs/design/dashboard-summary-options-d.html with local assets in docs/design/assets/dashboard-summary-d/. Keep all preview code outside the production application and build graph. Include simple option/scenario controls and an explicit synthetic-data label.

- [ ] A: Compact financial statement (initial recommendation): invested capital first, available gains/income/cost metrics in a logical order, emphasized NAV, separate returns section. Grouping does not assert a reconciled bridge.
- [ ] B: Statement plus headline NAV: prominent NAV/return header over an aligned compact statement containing all existing fields.
- [ ] C: Grouped panels: Capital, Performance and Current value, clear ordered headings; avoid disconnected metric tiles.
- [ ] Preserve all fields in each design. Do not omit less prominent data or force the owner to compare different scenarios.
- [ ] Present each in the context of the current dashboard's header and surrounding charts, with enough context to judge density and above-the-fold space. Synthetic context only; no changes to live charts.
- [ ] Document a brief comparison of scan order, density, comparison ease and mobile behavior; recommend one with concrete reasons, without treating recommendation as approval.

## Task 3 — Verify and prepare the decision package

- [ ] Use agent-browser per project instructions. Capture all three at desktop 1440x1000 and mobile 390x844 (at least six PNGs); visually inspect actual captures and ensure labels, negatives, long values and totals are readable.
- [ ] Exercise all synthetic scenarios; check every inventory field appears exactly as intended and amounts remain byte-for-byte unchanged.
- [ ] Check desktop-to-mobile-to-desktop resizing, keyboard controls, real element containment/hit testing and native 200% zoom with verified DPR and reset. Do not rely only on body scrollWidth or hide overflow to pass.
- [ ] Use viewport-only captures where needed; verify screenshot route/option/scenario and record artifact paths and actual results. Describe any incomplete checks honestly.
- [ ] Confirm git diff contains only the design package and tracker/docs. No production files, dependency changes, secrets or historical screenshot churn. For this docs/preview-only change, run relevant preview checks; a full backend/application gate matrix is unnecessary unless application files were changed (which is outside this assignment).
- [ ] Update docs/superpowers/plans/2026-09-30-frontend-modernization-progress.md: Phase C merged; Phase D options prepared/pending owner selection; Phase D implementation not started; C5b remains pending.
- [ ] Commit and push, open a draft PR into codex/frontend-modernization, and stop. Return the PR link, preview instructions, six capture links, comparison and the question: A, B, C, or specified adjustments?

## Review focus

The owner must be able to compare like-for-like designs without running the app. Review missing-versus-zero, negative values, long exact amounts, clarity of return horizons, and whether visual grouping falsely suggests arithmetic relationships. Do not claim implementation acceptance from approval of a mockup.

## After owner selection (not authorized in this assignment)

Write the selected composition's implementation plan, covering existing request ownership, field/string parity, loading/error/empty states, layout tests, focused dashboard/chart cases, full route/D8 acceptance and delivery budget. Implement only after the owner selects a direction. C5b still requires its separate release-validation acceptance and removal approval.
