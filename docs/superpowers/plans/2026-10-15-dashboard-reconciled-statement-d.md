# Phase D reconciled dashboard statement implementation plan

> **For agentic workers:** Use superpowers:executing-plans to execute task by task, with RED-first regressions for behavior changes. Stop at draft PR review; approval of the visual design is not approval to merge financial code.

**Goal:** Implement the owner-approved compact statement, with a backend-certified reconciliation of net result to canonical NAV.
**Architecture:** A scoped, Decimal-only backend read model provides raw values, formatted displays, provenance/completeness and reconciliation diagnostics. The frontend renders those values without calculating financial results. Retain the current summary request owner and legacy response compatibility.
**Tech stack:** Django/services, Decimal, pytest; Vue 3/Vuetify, TypeScript, Vitest and agent-browser.
**Spec:** Parent 2026-10-09-release-validation-fixes.md Task 8; this plan supersedes 2026-10-15-dashboard-summary-options-d.md's design-selection stage.
**Approved visual:** docs/design/assets/dashboard-summary-d/approved-statement.png (synthetic ImageGen mock; financial labels and requirements below take precedence over image artifacts).

## Approved composition and scope

Owner selected the first compact-statement option and approved the expanded reconciliation mock on 15 October 2026. Build it, not another options exercise; the MagicPath experiment is not the target.

Left statement: Invested; Cash out; Net invested capital subtotal; Net result subtotal with expandable breakdown; indented Realized gains/losses, Unrealized gains/losses, Dividends & interest, Fees, Taxes, FX effect; strong Total NAV row. Start breakdown expanded to match the approved image; collapse hides only component detail. Subtotals are never additional additive components. Right: Total return (since inception), IRR since inception. Keep NAV chart below, both IRR definitions, existing charts and exact-value controls intact. At mobile widths stack the sections with no truncated amounts. Existing palette and shell remain; navigation exploration is a separate unselected workstream.

Synthetic visual arithmetic: 100,000 invested + (-5,000) cash out = 95,000 net capital; 8,000 realized + 7,000 unrealized + 3,500 income - 1,000 fees - 500 taxes + 500 FX = 17,500 net result; 95,000 + 17,500 = 112,500 NAV. These are regression/example numbers, not evidence that existing functions implement this decomposition.

## Non-negotiable financial rules

- Read AGENTS.md and .memory-bank/index.md, Rules for AI Coding Agent.md, Portfolio NAV.md, Calculation Conventions.md and NAV Function and FX Flow.md before implementation. Protected changes require a needs-approval draft PR; no merge/deploy authorized.
- Same investor, selected accounts, reporting currency, effective date and since-inception horizon across ALL components, NAV and returns. Preserve signed flows: cash out is already negative. Validate account ownership. Internal transfers inside a selected scope must not create profit; scope-crossing transfers and in-kind contributions/withdrawals need explicit treatment.
- Canonical NAV remains authoritative; do not alter its formulas to make the statement fit. Money stays Decimal, internal prices >=6dp and quantities/FX >=9dp, ROUND_HALF_UP, user display digits.
- Net capital = signed external contributions plus signed external withdrawals (and explicitly classified noncash external flows if present). Net result = canonical NAV minus net capital is the identity/control total, not independent proof that attribution is correct.
- Independently derive mutually exclusive realized price result, unrealized price result, income, costs/taxes and FX attribution. Realized/unrealized price rows exclude separately presented FX. Confirm whether underlying functions already include fees/taxes/income before adding separate rows. Do not subtract costs twice.
- IMPORTANT source finding: backend/services/performance.py currently sets fx from eop_nav minus components_sum and zeros amounts below 0.1. Do NOT reuse this residual as certified FX or copy its fixed threshold. Do not change that existing performance surface as incidental scope.
- Compute unexplained difference = net result minus independently attributed components. Never relabel it FX, Other gain, or silently adjust a component. A material unexplained difference requires an explicit 'Unreconciled difference' diagnostic and an incomplete/unreconciled state. Reconciliation failure must remain visible and fails complete acceptance for supported scenarios.
- Missing price/FX/history is unknown, not zero. Carry partial/unavailable status and reasons; canonical NAV's known subtotal is not complete NAV. Do not claim a certified bridge when any dependency is incomplete. Preserve legitimate zero and negative holdings/results.
- Separate raw-precision tolerance (derived and documented) from display rounding. Sum independently rounded display rows as well; if they differ from displayed subtotals, expose a labelled display-rounding adjustment or equally explicit exact-value explanation. Never hide it in FX. Preserve raw strings and group thousands without Number conversion.

## Task 0 — Inspect, characterize and freeze the contract

- [ ] Fetch origin; create an isolated worktree on codex/dashboard-reconciled-statement-d from current origin/codex/frontend-modernization. Leave other worktrees/branches alone.
- [ ] Inspect backend/dashboard/views.py:get_dashboard_summary_api, services/nav.py, positions.py, realized.py, unrealized.py, performance.py, transactions.py, core/formatting_utils.py and applicable transfer/FX/bond logic. Trace actual return keys, signs, tax/fee inclusion and dates; no assumptions from function names.
- [ ] Inspect frontend/src/views/DashboardPage.vue, components/dashboard/summaryMetrics.ts, components/workspace/PortfolioMetrics.vue (locate if renamed), services/api/dashboard.ts and their tests. SummaryCard.vue is not the current live entrypoint; do not implement into an unused component.
- [ ] Create docs/design/dashboard-reconciled-statement-d.md: component/source matrix, supported instruments/events, scope/date rules, independent FX derivation (including cash FX), raw/display reconciliation rules, and unsupported states.
- [ ] Pin existing five summary fields and request counts before changes. Freeze an additive/versioned wire contract compatible with existing consumers. Prefer opt-in summary_contract=2 on the same request; retain legacy behavior without it. Include context, raw/display/status/reason per amount, component identities, control total, attributed sum, difference, tolerance and reconciliation outcome. No sensitive data in diagnostics.
- [ ] When historical data cannot support a classification, record it honestly and implement the explicit incomplete state; do not invent attribution. Any changed existing return formula or new policy for external in-kind flows must be called out separately for financial review.

## Task 1 — Backend read model and endpoint

- [ ] Add backend/services/dashboard_summary.py (or documented project-consistent equivalent) with one cohesive scoped calculation; reuse canonical functions and avoid recomputing NAV per display row. No frontend per-account fanout. Batch candidate/history reads where possible; record query count/runtime on a synthetic multi-account fixture.
- [ ] Add backend/tests/unit/services/test_dashboard_summary_reconciliation.py and endpoint regression tests BEFORE implementation. Expected raw values must be hand-derived Decimal fixtures, not copied from the implementation under test.
- [ ] Cover: approved numeric example; cash-only; buy/hold; partial disposal; complete disposal/rebuy; realized loss; negative/short positions if supported; dividends/interest; fees/taxes alone and embedded costs; gross-versus-net distributions; foreign security price gain versus FX gain; cash-only FX; FX conversion transactions/commissions; cross-account transfer inside and across selected scopes; in-kind flows; bond coupon/accrual/amortization/redemption; crypto coin fees and coin-settled options; zero capital, no activity, future transactions, historical cutoff, multi-account/investor isolation; missing prices/FX and incomplete basis; high-precision and display-rounding edge cases.
- [ ] For each instrument/event that is unsupported, assert an explicit incomplete diagnostic rather than a forced balanced result. Preserve canonical values and existing users' outputs. Inject a deliberately omitted/misclassified component and prove reconciliation fails instead of becoming FX.
- [ ] Integrate into backend/dashboard/views.py and common/schema_serializers.py. Regenerate API types via the repository workflow. Keep protected backend work in distinct commits; document formulas and expected numeric examples for human approval.

## Task 2 — Typed boundary and approved UI

- [ ] Extend frontend/src/services/api/dashboard.ts with runtime validation from unknown for the negotiated document. Present-but-invalid v2 must error, not silently downgrade. Validate context through the existing portfolio request owner; ignore stale responses on account/currency/date changes. No additional summary fetch, no changes to chart request ownership.
- [ ] Add a dedicated frontend/src/components/dashboard/PortfolioValueStatement.vue plus focused tests, and wire it into DashboardPage.vue. Retain existing loading/error/retry behavior. Legacy-only responses may show the old five metrics with an honest unavailable-breakdown notice, never fabricated components.
- [ ] Render exact server display strings for all rows and diagnostics. Show Net invested capital and Net result subtotal hierarchy, signed components, emphasized NAV and separated returns. Explain price-result/FX separation with concise help. Show zero as zero, unavailable as unavailable, and partial known values as partial.
- [ ] Breakdown toggle supports keyboard and visible focus; amounts stay right-aligned with tabular figures. Preserve all labels/horizons and page heading ownership. Collapse state must not conceal incomplete/unreconciled status.
- [ ] Test valid/partial/unreconciled/legacy/malformed documents, zero/negative/large values, requested context mismatch, late response ownership, toggle without requests, subtotal versus component hierarchy, and currency/date/account changes. No frontend financial arithmetic.

## Task 3 — Rendered acceptance and financial evidence

- [ ] Add a focused dashboard-statement-d browser case using backend-faithful synthetic contract fixtures. Verify actual rendered values and scope/request counts, all states, expanded/collapsed detail, all five original fields and chart coexistence.
- [ ] Capture and inspect desktop 1440x1000, tablet 1024x768, mobile390x844, desktop-mobile-desktop transitions and native200% zoom with DPR verification/reset. Test long exact amounts with element containment/hit testing, not body scrollWidth alone. Retake only this phase's synthetic assets.
- [ ] Run gates sequentially on committed code, recording actual exit codes: frontend unit suite, three type checks, lint, api:types:check, build, affected dashboard/chart/context/date/recovery cases including charts-c3/c4/c5 and charts-c, full route matrix, final-qa-d8, delivery budget; backend uv run python -m pytest with test settings. Full route matrix is NOT a substitute for focused workflows. Diagnose failures rather than labelling them environmental without evidence.
- [ ] Validate with a disposable copy of local real data if available: multi-account, historical date, currency changes and representative stock/bond/crypto contexts; no original DB writes or committed real values/screenshots. Report unavailable scenarios; API display parity alone is not independent financial proof. Owner financial acceptance remains pending even when tests pass.
- [ ] Update evidence and durable modernization tracker. Explicitly retire the pending design-options assignment and record approved visual, backend review status and remaining limitations. Commit/push and open draft PR into codex/frontend-modernization with needs-approval; include financial-review examples and exact tested SHA. Stop for review.

## Completion and boundaries

A beautiful table with unexplained reconciliation is not complete. A forced residual assigned to FX is not complete. Expose truthful incomplete states but list unsupported required cases as acceptance gaps. No Chart.js removal/C5b, navigation redesign, palette change, main merge, deployment or release tag. This plan authorizes implementation and draft review, not merge of protected calculations. Screen-reader work remains out of scope; existing keyboard, semantic, focus, contrast and zoom requirements remain.
