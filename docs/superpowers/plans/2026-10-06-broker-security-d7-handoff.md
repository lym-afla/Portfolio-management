# D7 broker connections and security detail implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this handoff task by task, with failing behavioral regressions before changes.

**Goal:** Extract broker connection management and security detail into focused, typed components without losing provider capabilities, financial displays or request ownership.
**Architecture:** Keep compatible entrypoints, one broker orchestration owner and one security request owner. Children receive display-only models and emit explicit intents. Reuse existing API adapters, R request lifecycle and D5 UI conventions; keep incumbent security chart rendering separate from this extraction.
**Tech stack:** Vue 3, TypeScript, Vuetify, Vitest, existing Chart.js, agent-browser synthetic fixtures; portable Node 24.20.0 reference.
**Spec:** [Accepted D7 design](2026-09-08-frontend-design-workflows.md#d7-decompose-broker-connections-and-security-detail-without-changing-their-capabilities), [master plan](2026-09-08-frontend-modernization.md), [progress tracker](2026-09-30-frontend-modernization-progress.md).

## Base and constraints

- PR #57/D6 is user-merged into `codex/frontend-modernization` at `0167c409`. Fetch the latest branch, including this handoff, before starting. Do not branch from main or an unmerged proposal.
- Use a dedicated worktree and branch `codex/broker-security-extraction-d7`. Never switch/reset another executor's checkout. Read AGENTS.md, `.memory-bank/index.md` and `.memory-bank/Rules for AI Coding Agent.md`.
- No backend, financial calculation, import protocol, database or dependency migration changes. No D8 implementation, C4 chart-v2 rollout/pies or C5 cutover. ECharts remains default-off. No main merge or deployment.
- Preserve PR #54/#55 settings/context fixes, D5 layout/focus and D6 socket/import lifecycle fixes. Do not reopen historical waivers.
- Dedicated screen-reader support/audits are out of scope under amendment `abbed5e8`. Keyboard/focus, labels, contrast, semantic markup, responsive and native 200% zoom checks remain required.
- Never use live broker endpoints or real credentials for tests. Synthetic credential literals may appear only in isolated test inputs, never screenshots, diagnostic output or display models. No secrets in Pinia, browser storage or telemetry.
- Accepted interface examples are guidance: characterize actual wire behavior first and record discrepancies instead of silently changing provider semantics.

## Review focus

1. Two providers with the same numeric token id must never share busy state or mutation targets.
2. A delayed request from a closed/replaced form or prior auth session must not mutate the new session or release its busy lock.
3. Rejected provider validation must preserve retryable form inputs without displaying/logging secrets; success/cancel/unmount must erase credential drafts.
4. Security A/B, account and period requests resolving out of order must not mix titles, metadata, histories or transactions.
5. Populated bond/crypto fields, missing values and decimal display strings must survive extraction and viewport changes unchanged.

## Ownership and files

- Keep `frontend/src/components/BrokerTokenManager.vue` as compatibility entrypoint with emits `error`, `success`, `info`.
- Create `frontend/src/features/brokers/types.ts`, `useBrokerConnections.ts`, `BrokerConnectionList.vue`, `BrokerConnectionForm.vue`.
- `useBrokerConnections` owns lists, capability lookup, row commands and request/session ownership. Key commands by `{ provider, tokenId }`; confirmation snapshots identity and label. List gets allowlisted display fields only. Form owns its ephemeral provider-specific credential draft and emits to the API owner; no duplicate draft in the parent/store.
- Keep `frontend/src/views/database/SecurityDetailPage.vue` as route/title compatibility entrypoint.
- Create `frontend/src/features/securities/types.ts`, `useSecurityDetail.ts`, `SecurityOverview.vue`, `SecurityMetadata.vue`, `SecurityActivity.vue`.
- `useSecurityDetail` owns the existing detail, price, position, transactions and account-choice resources with `usePortfolioRequest`; accept reactive security id, account/period/pagination and committed context inputs. Reuse current query signatures and watcher/invalidation behavior. Children never fetch.
- Keep chart data/options and `LineChart` ownership at the entrypoint or a clearly named unchanged legacy presentation module if needed; overview exposes `price-chart`/`position-chart` slots. Do not translate numeric strings or replace charts as part of D7.
- Existing adapters: `frontend/src/services/api.ts`. Narrowly remove raw broker-response/error logging in the touched credential path if it can expose secrets; no general API rewrite.
- Tests: `frontend/tests/unit/features/brokers/connections.spec.ts`, `forms.spec.ts`; `frontend/tests/unit/features/securities/detail.spec.ts`; retain existing `BrokerTokenManager.spec.js`, `SecurityDetailPage.crypto.spec.js` and any bond tests.
- Browser: add `frontend/tests/browser/brokers-security-d7.mjs`, register `--case brokers-security-d7` in `run-smoke.mjs`, extend only required synthetic fixtures/handlers.
- Evidence: `docs/design/frontend-brokers-security.md`, captures under `docs/design/assets/brokers-security/`, progress tracker.

## Task 0 — Characterize contracts and baseline

- [ ] Inventory every broker action, provider form field, conditional dialog, success/reactivation/error branch, refresh and emitted event against both incumbent and read-only backend serializers/endpoints. Record API path/method and complete payload, optional/null/default handling; distinguish revoke/delete/test.
- [ ] Current source shows Tinkoff and IB test operations; Bybit/OKX report unsupported testing. Verify capabilities, do not invent buttons/endpoints. Pin Tinkoff post-save testing and reactivation branch separately.
- [ ] Pin Tinkoff token/type/sandbox, IB token/account/paper-trading, Bybit key/secret/testnet, OKX key/secret/passphrase/simulated-trading payloads from source. Check real async Vuetify validation before save; if an incumbent flaw prevents valid gating, document and fix it minimally with a regression.
- [ ] Inventory security metadata, bond/crypto conditions, units, history options, account selection, transactions pagination, title events and retry states. Record the five current resource signatures and all request triggers. Capture populated incumbent behavior before extracting.
- [ ] Run baseline focused tests and required gate commands, recording actual exit codes and SHA. Reproduce any inherited failure on pristine base before claiming a waiver.
- [ ] Commit characterization fixtures/tests and source-linked inventory. Tests must call existing handlers/rendered controls, not merely repeat fixtures or search source text.

## Task 1 — Broker owner and safe display boundary

- [ ] Write failing tests for `{provider, tokenId}` collision isolation, correct endpoints/payloads, unsupported test actions, once-only mutation, rejected requests and exact confirmation subject.
- [ ] Add overlap regressions: request A starts; form closes/session changes; B starts; A resolves/rejects while B is pending. Assert no stale success/error/refresh or busy-lock release. Check list-load ordering as well.
- [ ] Implement typed provider draft union, safe display allowlist and `useBrokerConnections` around existing adapters. Keep test/revoke/delete distinct. No new financial/provider calculation behavior.
- [ ] Remove credential-bearing response/error logging from the directly touched broker path; test with synthetic secrets in a rejection so none appear in alerts, emitted notices or captured logs. Do not log request bodies.
- [ ] Run focused tests and actual type-check scope. Explicitly include every new TS test in a checked project; verify resolved file lists. Vitest transpilation is not type-checking; no silent exclusions or `any` escape hatches to obtain green gates.
- [ ] Commit broker owner and contract changes.

## Task 2 — Broker list and form extraction

- [ ] Write failing behavioral tests for each provider's valid/invalid submit, field-error retry, cancellation, success, unmount, reopen and credential reset. Include Tinkoff reactivation and unknown broker/provider mapping confirmation.
- [ ] Extract list and form, retain user-visible capabilities and precise connection deletion/revocation wording. Use shared workspace/dialog patterns, text+icon status, row-scoped busy/error and explicit accessible names. Remove duplicate incumbent handler/state bodies after routing through new owner.
- [ ] Verify focus entry, delayed form fields, close/unmount cancellation and return to invoking control. Preserve entered values on same-form rejected save; clear drafts on successful save/cancel/unmount, including alternate close paths.
- [ ] Run broker component and feature regressions; commit separately from security work.

## Task 3 — Security resource owner

- [ ] Write failing tests for route A→B with responses B→A; account/period changes; session invalidation; retry; pagination reset; all five resources and parent title event. Request counts must equal characterized behavior (no duplicate fetch after extraction).
- [ ] Implement `useSecurityDetail` with detached query snapshots and existing latest-request guards. Preserve account/period/date meaning and server pagination/sort ownership. No resource commits after its owner becomes stale/unmounted.
- [ ] Check simultaneous old success and rejection cannot replace the accepted new security, loading state or error. Independently recover a failed resource without discarding valid siblings.
- [ ] Run feature and existing security tests; commit resource extraction.

## Task 4 — Security sections and value parity

- [ ] Write failing populated component tests for stock, bond and crypto views, missing metadata, zero values, negative values and large exact display strings. Keep quantities/currency/percent-of-nominal distinct; use server display strings, including commas, precision and missing-value markers.
- [ ] Extract overview, metadata and activity into prop-driven sections, preserve existing history charts through slots and existing transaction-row components. Unknown/missing metadata is explicit, not a reason to suppress the section.
- [ ] Pin `99.125000%` bond display, high-precision crypto quantities and financial strings beyond JS safe integer range without converting display values through Number. Preserve existing chart plotting boundary unchanged.
- [ ] Run feature/component/type checks; commit security presentation separately.

## Task 5 — Rendered acceptance and final evidence

- [ ] Add synthetic browser flows for all four provider forms and supported commands; backend-faithful responses; assert exact identity/payload and no duplicate mutation. Rejections retain editable inputs; cancellation sends nothing; screenshots contain no credential values.
- [ ] Render populated stock/bond/crypto security details, empty and failed/recovered resources, account/period/pagination changes and route transitions. Assert visible values/units and request counts, not just page titles.
- [ ] At 1440×1000, 1024×768, 390×844 and 768×1024 verify page headings, actions, row controls, form fields and chart/table regions by bounds AND hit-testing below the fixed header. Repeat desktop→mobile→desktop and native 200% zoom; verify/reset DPR. Do not infer usable controls from body scrollWidth.
- [ ] Capture broker list, provider form/error with credentials blank/masked, destructive confirmation, populated bond/crypto desktop/mobile and zoom evidence. Inspect PNGs; record SHA, fixture, viewport and limitations.
- [ ] Run the full matrix below on committed code, capturing each process exit code directly. Avoid concurrent heavy gates. Re-run affected checks after fixes, not whole suites without cause.
- [ ] Update evidence/tracker as implemented/pending review, include exact tested SHA and honest deviations. Push one draft PR into `codex/frontend-modernization`; stop for review. No merge or deploy.

## Final gate matrix

From `frontend/`, using the declared Node version and lockfile:

```powershell
npm run test:unit
npm run type-check
npm run type-check:reliability
npm run type-check:charts
npm run api:types:check
npm run lint
npm run build
npm run test:browser -- --case brokers-security-d7
npm run test:browser
npm run test:delivery
```

Also run focused cases individually: `imports-d6`, `layout`, `context`, `dates`, `requests`, `recovery`, `dialogs`, `dialog-recovery`, `d4`, `d5`, `settings-account`, `charts-c2`, `charts-c3`. Preserve both chart-flag states. Use agent-browser, synthetic loopback only; reject unexpected requests and clean up only owned browser/server sessions.

From `backend/` run `uv run python -m pytest` using repository test settings/configuration. No coverage weakening. Reference executor baseline after D6: 773 frontend tests, lint 0 errors/13 warnings; backend 1386 passed/10 skipped. These are historical counts, not promised D7 results. Root independently verified 140 focused D6/socket tests; full baseline gates were executor-reported. This documentation-only handoff runs no application gates.

## Completion boundary

D7 completes only after review and user merge, with broker/security capabilities preserved and evidence accepted. Then C4 owns the three solid allocation pies and security-history renderer migration; C5 owns cutover/removal; D8 owns final visual/keyboard/responsive/workflow acceptance. Screen-reader auditing is not a remaining gap.
