# C4 allocation pies and security histories implementation plan

> **For agentic workers:** Use superpowers:executing-plans task by task, with failing behavioral regressions before implementation.

**Goal:** Add exactly three solid allocation pies and migrate price/position history rendering behind independent default-off ECharts gates, preserving exact server financial semantics.
**Architecture:** Extend the validated C1/C2 boundary and C3 renderer/fallback patterns. Dashboard keeps one breakdown request for three documents; D7's security owner keeps one request per history. Pure option builders and lazy renderers consume accepted documents; existing renderers remain available on the same accepted response.
**Tech stack:** Vue 3, TypeScript, Vuetify, existing pinned ECharts/vue-echarts, Vitest and agent-browser; Node 24.20.0 reference.
**Spec:** [Accepted C4 design](2026-09-08-chart-correctness-echarts.md#task-c4-migrate-allocations-to-solid-pies-and-security-histories-after-nav-acceptance), [master plan](2026-09-08-frontend-modernization.md), [tracker](2026-09-30-frontend-modernization-progress.md).

## Base and boundaries

- PR #58/D7 is merged at `13a2129d`; fetch latest `origin/codex/frontend-modernization`, including this handoff. Dedicated worktree/branch: `codex/allocation-security-charts-c4`. Never change another session's checkout.
- Read AGENTS.md, `.memory-bank/index.md`, repository rules and financial conventions. Backend/schema/calculation changes are outside this assignment. If the existing wire cannot support a requirement, document the exact gap; do not fabricate metadata or silently change financial logic.
- F3 was reviewed and merged in PR #48; C1/C2 contract and C3 NAV pilot are integrated. Confirm the current source-linked ratio contract and fixtures before rollout, not old pre-F3 recomputed percentages.
- C3 NAV stays default-off and retains bars/two IRRs. Add separate `VITE_ALLOCATION_ECHARTS_ENABLED` and `VITE_SECURITY_ECHARTS_ENABLED`, enabled only for exact string `true`, default false. C5 owns default-on release and Chart.js removal. No deployment/main merge or D8 work.
- Preserve D7 broker behavior, credential fixes, security sections, request ownership and mobile transaction pagination. Existing security chart code is now in `frontend/src/views/database/SecurityDetailPage.vue`, with five resources owned by `features/securities/useSecurityDetail.ts`; the old C4 text about unguarded Promise.all is obsolete.
- Screen-reader audits are out of scope. Keep keyboard/focus, labels, semantic markup, readable exact tables, contrast, native zoom and actual control hit-testing.
- No new dependencies unless a concrete unavailable capability is documented for review; ECharts PieChart/LineChart registrations use existing packages. No new product routes or dormant PriceChart rollout.

## Review focus

1. Allocation focus must never hide slices, renormalize shares or alter the full-NAV denominator.
2. Signed, incomplete, nonpartitioning and nonpositive allocations must show honest reasons plus all table rows, never a misleading pie.
3. Price units differ from reporting currency; bonds remain percent of nominal, and quantity/date identities are never reconstructed from rounded labels.
4. Independent history requests must survive out-of-order responses, route/account/context changes and disposal without duplicate requests or mixed documents.
5. Tooltips, tables and controls must remain visible below the fixed header through resize/scroll/zoom, including empty/error/fallback states.

## Files and ownership

- Extend `frontend/src/features/charts/contracts.ts`, `parseChartEnvelope.ts`, `chartApi.ts`, `rendererPolicy.ts` with allocation/security query/result types, envelope parsing, transport and independent flags.
- Create `buildAllocationOption.ts`, `buildSecurityOption.ts`, `AllocationChart.vue`, `SecurityHistoryChart.vue`, and lazy `EChartsAllocation.vue`/`EChartsSecurity.vue` in that feature. Add `AllocationLegend.vue`/`AllocationDataTable.vue` and `SecurityDataTable.vue` only where existing NAV components cannot express their semantics cleanly.
- Reuse `renderBoundary.ts`, stable series styles, `tooltipPlacement.ts` and failure-boundary pattern from `ChartHost.vue`. Generalize existing shared components only with NAV regression coverage; do not force a NAV-specific interaction type onto allocations.
- Dashboard integration: `frontend/src/views/DashboardPage.vue`, `frontend/src/components/dashboard/BreakdownChart.vue`. Preserve current chart/table controls and one breakdown fetch, not three separate requests.
- Security integration: `frontend/src/features/securities/useSecurityDetail.ts`, `frontend/src/views/database/SecurityDetailPage.vue`, existing overview chart slots. D7 owner remains authoritative for chart requests. A helper named `useSecurityCharts` is optional only if it replaces/delegates those two resource owners, never adds another watcher/request set.
- Tests in `frontend/src/features/charts/__tests__/{allocation,securityHistory,remainingChartApi,remainingChartIntegration}.spec.ts`; extend real fixtures and render harness. Explicitly include new TS tests in checked configurations without silent exclusions or any/never casts to conceal mismatched contracts.
- Browser `frontend/tests/browser/charts-c4.mjs`, fixture server and smoke registry. Evidence `docs/design/frontend-charts-c4.md`, captures `docs/design/assets/charts-c4/`, tracker.

## Task 0 — Wire and behavior characterization

- [ ] Read the actual dashboard breakdown and database history handlers (`backend/dashboard/views.py`, `backend/database/views.py`) and `backend/services/charts.py` builders. Inventory endpoints, query parameters, envelope shapes, units, identity, period/effective-date rules, empty/error branches and abort semantics with source references.
- [ ] Pin allocation `chartV2` dimension map vs security `{legacy, chartV2}` wrappers. Security price currently takes period but no account_id; position takes period and optional account_id. Do not add unsupported parameters from conceptual query interfaces.
- [ ] Characterize existing accepted legacy data/renderer wiring and request counts, D7 account scope, native chart tabs and title behavior. Confirm v2 empty price/position documents retain identified zero-point series.
- [ ] Establish baseline gates and populated fixtures; record current SHA/commands. Legacy observations alone cannot certify v2 correctness. Commit characterization tests/inventory before functional changes.

## Task 1 — Exact transport and lifecycle boundary

- [ ] Add RED tests for validated v2, genuine legacy-only, invalid present metadata, wrong document kind/dimension/security identity, C1 errors, aborts and context mismatch. Preserve original decimal/display strings byte-for-byte, including large values and comma separators.
- [ ] Implement one `chart_contract=2` request per existing fetch. No retry-by-downgrade or extra legacy request. A missing v2 field may yield explicit legacy-only; a malformed present field is an error. Use shared sanitized errors, preserving status/code/retryable metadata.
- [ ] Validate context against each endpoint's actual semantics: price instrument currency is not reporting currency; security local account selection may differ from global scope. Do not blindly reuse NAV's dateTo validator or reconstruct broker/group memberships client-side. Verify supported identity metadata; record any unverifiable field without inventing a match.
- [ ] Keep immutable accepted snapshots and detached renderer inputs. Add route A→B/responses B→A, pending global context, historical date, local account/period changes, error→retry, unmount and bounded reconciliation regressions. Price/position settle independently; no duplicate history requests or new detail/transactions fetches.
- [ ] Wire D7 resources through these transports while preserving legacy projections for existing charts. Run focused API/lifecycle/type tests and commit.

## Task 2 — Three solid allocation pies

- [ ] Add RED tests for asset_type, asset_class and currency. Each eligible document produces one pie series with zero inner radius, server-ranked slices and stable server-ID colors shared with NAV where category identity matches. No donut or bar substitution for eligible modern allocation cards.
- [ ] Require backend `allocationSummary.pieEligibility === 'eligible'`; use `toPlotNumber` only at geometry boundary. Never use ECharts-derived percent as authoritative. Tooltips/table use exact server amount/share/denominator/totalShare displays and statuses.
- [ ] Test approved 25/75 against 100, signed -25/125, incomplete 25/50, missing valuation, explicit zero, all-zero, negative total and legacy_non_partitioning. Ineligible => reason plus complete signed/status table. No abs(), positive-subset normalization, invented residual/Other slice or hardcoded total 100%. Zero rows stay in the table without artificial slices.
- [ ] Implement HTML legend highlight/focus only; built-in selection disabled. Prove every legend operation preserves angles, all rows, shares and denominator. Use keyboard-operable controls and stable focus after compatible refresh.
- [ ] Keep chart/table tabs available in each of the three cards. Show independent rendering failure/retry or explicit user-chosen legacy fallback on the same accepted payload; data errors remain data errors. Commit allocation implementation.

## Task 3 — Price and position histories

- [ ] Add RED tests for ordinary instrument currency, bond `98.500000` percent-of-nominal (never divide by 100), crypto quantity `0.000116590`, huge decimals, empty identified series, missing points, same-date distinct server keys and multiple events at one timestamp.
- [ ] Build unsmoothed price lines and step-end holdings from server order/identity. Do not collapse duplicate-date table rows, calculate new positions, interpolate missing valuations or treat unknown as zero. Axis units come from series metadata; exact tooltips/tables never format plotting numbers as financial truth.
- [ ] Preserve original observations in table. Effective-date carry-forward is presentation-only and clearly labelled with source observation date; append only if an earlier known endpoint exists and no identical endpoint is present, never from a future quote. Keep any synthetic plotted endpoint separate from the validated document and observed-point table. If wire semantics do not permit honest carry-forward, record the blocker instead of inferring observations.
- [ ] View-only zoom and inspection retain server point identity, exact display/status/reason/knownSubtotal where present. Native controls and data tables expose every point; no silent sampling/rounding.
- [ ] Integrate through D7 overview slots with one owner per resource; retain stock/bond/crypto metadata and activity behavior. Commit separately from allocations.

## Task 4 — Lazy gates, fallback and rendered acceptance

- [ ] Gate renderers independently, preserve NAV flag behavior. Verify default-off builds fetch no additional allocation/security ECharts modules; auth/profile fetch no chart chunks. With either flag on, only corresponding eligible validated documents use modern renderer. Record cold loaded-graph gzip by route and flag combination; do not claim C5 performance acceptance from chunk names alone.
- [ ] Use the established tooltip placement below fixed/sticky overlays, escape server strings, bound/wrap tooltip boxes. Test long labels, all slice edges, partially scrolled charts, desktop→390px→desktop and native 200% zoom with DPR verified/reset; assert bounds and actual hit-testing, not only scrollWidth.
- [ ] Extend synthetic browser fixtures with backend-faithful v2/legacy envelopes and expected request counts. `charts-c4` must prove three visible solid pies, all chart/table tabs, invariant legend denominator, each ineligible state, stock/bond/crypto histories, duplicate-date table rows, independent failure/recovery and stale responses.
- [ ] Exercise allocation/security flags independently and together, plus NAV enabled alongside them. Check legacy-only notices, malformed-v2 error (no silent downgrade), renderer failure/user-chosen fallback and zero extra request on visual interactions.
- [ ] Capture all three pies, a signed/incomplete table, bond and crypto histories/tables, mobile tooltip and native zoom with synthetic values only. Inspect actual images; record source fixture, flag state, SHA, viewport and measurements. Retain earlier captures unchanged unless deliberately updating their evidence.
- [ ] Run focused tests then full matrix on final committed implementation with actual process exit codes. Update evidence/tracker as implemented/pending review, push one draft PR into modernization and stop. No merge/default-on rollout/deployment.

## Final gate matrix

Frontend: `npm run test:unit`, `type-check`, `type-check:reliability`, `type-check:charts`, `api:types:check`, `lint`, `build`, `test:browser`, `test:delivery` (each via `npm run`). Run new `npm run test:browser -- --case charts-c4` and existing focused cases individually: `brokers-security-d7`, `imports-d6`, `layout`, `context`, `dates`, `requests`, `recovery`, `dialogs`, `dialog-recovery`, `d4`, `d5`, `settings-account`, `charts-c2`, `charts-c3`.

Backend from `backend/`: `uv run python -m pytest` with repository test settings/coverage intact. Reference last executor report: 857 frontend tests, lint 0 errors/8 warnings; backend 1386 passed/10 skipped. Counts are historical, not acceptance targets. Root independently reran 86 focused D7 tests plus a credential punctuation probe; final full suites were executor-reported. This planning update runs no application gates.

Use agent-browser with synthetic loopback, reject unexpected requests, run heavy gates sequentially and clean up owned sessions/servers. Report environment failures precisely; a passing route matrix is not proof that a distinct failed scenario was environmental—reproduce/rerun that scenario directly.

## Completion boundary

C4 acceptance requires three honest solid pies, both security histories and exact-data access without regressions to NAV or D7. C5 separately owns default-on rollout, delivery/performance release acceptance, rollback and eventual Chart.js removal. D8 remains final visual/keyboard/responsive/workflow QA. Screen-reader auditing is not a gap.
