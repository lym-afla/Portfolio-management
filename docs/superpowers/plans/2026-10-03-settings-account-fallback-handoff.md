# Settings account-selection preservation implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task-by-task. Work in a dedicated checkout; do not switch the shared D5 checkout.

**Goal:** Prevent saving Profile Settings from silently replacing an unavailable saved account selection with All accounts.

**Architecture:** Preserve the server-returned account identity as form state, separate from the select's display model. Resolve availability against the returned account options and guard saving before either existing write occurs. Keep the profile-preferences endpoint and committed-context queue as their existing owners; no new API or parallel context state.

**Tech Stack:** Vue 3, Vuetify 3, Pinia, Vitest, existing agent-browser harness; Node >=24.20.0 <25.

**Spec:** The behavior contract below defines this bounded correction to Profile Settings. Read [the progress tracker](2026-09-30-frontend-modernization-progress.md), [workspace evidence](../../design/frontend-workspace.md), `AGENTS.md` and `.memory-bank/Rules for AI Coding Agent.md` before implementation.

## Starting point and coordination

PR #54 is merged at `610dff992d76fe4f9459f059c6810de2a4e58819` (3 October 2026), including the corrected header selector. Fetch the latest `origin/codex/frontend-modernization` with this handoff and create `codex/settings-account-selection-preservation` in a dedicated worktree. Record its actual base and working directory before every gate batch. Never reset, stash, checkout or commit in another executor's active D5 checkout.

D5 can modify the same `ProfileSettings.vue` for presentation. Keep this fix small and coordinate integration through reviewed PRs into modernization. After either PR merges, the other executor must incorporate the latest base and rerun affected settings/context tests; do not take an unmerged D5 branch as this fix's base. This is a supplementary bug fix, not completion of another master-plan task.

## Global constraints

- Frontend-only. No backend, financial calculation, persistence schema, API contract or authorization changes; no D5 redesign or other workstream.
- Preserve the PR #54 header fix and existing account/group/broker identity types, including numeric IDs and `{ type: 'all', id: null }`.
- Reuse `formatAccountChoices` and `committedAccountLabel` where applicable. Do not add fake selectable options, repair requests, implicit All accounts defaults, or infer account identity from a display string.
- Existing save order stays: `updateUserSettings` for non-context preferences, followed on success by `context.changeContext` for account/currency/digits/date. No transactional API redesign. Surface rejection honestly; do not claim rollback of the first write if the second fails.
- No merge or deployment. Publish a draft PR for review. Real screen-reader testing remains distinct from DOM/input checks.

## Behavior contract

1. On successful load, preserve `{type: settings.selected_account_type, id: settings.selected_account_id}` exactly when structurally valid, whether or not choices contain it. Never substitute the live header selection: the settings response is the authority for this form's initial value.
2. A matching selectable option is resolved and retains normal behavior for all/account/broker/group. An absent specific identity is unresolved: show **Unavailable** and a persistent associated message, **“Your saved account selection is unavailable. Choose an available account selection before saving.”** Do not expose raw objects in visible text or the combobox input value.
3. Empty choices are not permission to save a replacement. Even a valid saved All accounts identity remains unresolved when the response contains no matching option; display **All accounts** honestly, with an availability message **“Account choices are unavailable. Reload settings before saving.”** A malformed/missing saved identity is unresolved and must not default to All accounts.
4. While loading, after load failure, or while account resolution is invalid/unavailable, disable Save and guard `saveSettings` itself before **both** `updateUserSettings` and `changeContext`. Submitting through Enter or invoking the handler must produce zero writes. No auto-save occurs when options arrive.
5. The user can select any real available option, including All accounts explicitly, to resolve the field. Preserve all other edits. The display model may be a safe string for an unresolved choice, as in PR #54, but form identity remains a separate object; accept only actual selectable option values into it.
6. After valid explicit selection, preserve existing request shapes and queue behavior. Rejected profile or context writes retain form edits and show an error; no automatic fallback to All accounts, no success message on failure, no duplicate writes from repeated submit while saving. Disable Save and use a handler guard while an existing save is pending.
7. Do not expand scope into a general settings reload/recovery or session-lifecycle redesign. Test delayed initial responses and existing failure paths. Preserve existing group-manager/broker-token behavior and events.

## Review focus

| Failure mode | Required proof |
|---|---|
| Missing account/broker/group silently broadens scope | Original identity retained; unavailable label; saving another preference makes zero writes |
| All accounts or empty/malformed choices confuse availability | Test explicit real All accounts versus no matching option; no invented options/defaults |
| Slot fixes visible text but leaves raw input value | Real Vuetify assertions on exact visible label **and exact input value** |
| UI-disabled Save can still execute or double-submit | Direct handler/Enter tests; zero writes when unresolved, one save sequence while pending |
| Fix bypasses context queue or collides with D5 | Existing payload assertions retained; dedicated checkout; final diff limited to this correction |

## Source map

- Modify `frontend/src/views/profile/ProfileSettings.vue`: account select, `settingsForm`, `loadData`, `saveSettings`, loading/saving/resolution state and message. Keep this correction local unless a tiny pure helper genuinely improves tests.
- Read `frontend/src/utils/accountUtils.js`, `frontend/src/components/AccountSelection.vue`: existing choice flattening, label semantics and PR #54 safe display-model pattern. No header change is expected.
- Read `frontend/src/stores/portfolioContext.ts`, `frontend/src/services/api/context.ts` and settings API functions through `frontend/src/services/api.ts`: preserve existing queue and payload ownership.
- Add `frontend/tests/unit/components/ProfileSettings.accountSelection.spec.js`; update `frontend/tests/unit/components/ProfileSettings.context.spec.js` with backend-faithful available choices. Its current empty choices plus injected broker value is not a valid available-selection fixture after this fix; retain its queue/payload assertions with a real broker option.
- Browser: add `frontend/tests/browser/settings-account.mjs` and a `settings-account` case in `run-smoke.mjs`; narrowly extend `fixture-server.mjs`/`fixtures.mjs` only as required, keeping normal route fixtures unchanged. Use real backend response shapes, not new application endpoints.
- Evidence: add a bounded section to `docs/design/frontend-workspace.md` and supplementary record in the progress tracker. Do not mark D5 completed.

## Task 1 — preserve identity and expose unresolved state

- [ ] Establish baseline in the dedicated checkout and inspect actual settings/choices responses. Record current SHA, Node version and any baseline failures.
- [ ] Write failing real-Vuetify tests for matching all/account/broker/group, missing specific identities despite other options being present, empty choices, malformed saved identity and delayed load. Pin form identity, exact visible label, exact underlying input value, available menu entries and loading/Save state. Stub unrelated child managers and APIs, not the account select.
- [ ] Demonstrate genuine RED: missing account currently becomes `{type:'all',id:null}`. Include a saved identity distinct from live header context to prevent accidental replacement from the store.
- [ ] Implement separate identity/display/availability handling inside ProfileSettings. Save may only become eligible after settings and choices loaded successfully and the form identity matches a real selectable option. Display a persistent accessible field message for unresolved states.
- [ ] Verify GREEN plus the retained context spec with realistic choices. Commit implementation and tests together.

## Task 2 — guard saving and preserve explicit choices

- [ ] Write failing tests: change another preference while account is unresolved then submit (zero profile/context writes); directly invoke handler; explicitly select a real account and All accounts; failed load; repeated submit while pending; rejected profile write; rejected context write. Confirm rejected writes preserve the selected identity and other edits.
- [ ] Guard before the first write, snapshot the submitted form/context patch as needed, and retain the existing two-stage save ownership. The account chosen explicitly must reach `changeContext` with its original type/id; context-owned fields must stay absent from `updateUserSettings`. No separate `updateAccount` call.
- [ ] Assert successful saves occur exactly once, availability warnings clear after valid selection, and no safe display string can enter the transport payload. Do not weaken existing payload tests.
- [ ] Run the focused settings and AccountSelection regression suites; commit the save correction.

## Task 3 — rendered acceptance and final review

- [ ] Add the focused browser scenario with faithful settings returning a missing account ID and a choices list containing other valid options. Verify at desktop and 390px: Unavailable label, exact safe input value, visible associated explanation and zero mutation requests after attempted unresolved submission.
- [ ] Choose an actual available account through the rendered select, edit a display preference, save and assert the fixture receives the expected profile payload and context selection; confirm readback. Repeat explicit All accounts, rejected save and delayed initial load. Require unmatched requests to fail.
- [ ] Check keyboard interaction and native 200% zoom with visible, hittable controls/message; record DOM/keyboard evidence without claiming a screen-reader audit. Use agent-browser; synthetic loopback only. Clean up only owned sessions/servers.
- [ ] On committed implementation run, from `frontend/`: `npm run test:unit`, `npm run type-check`, `npm run type-check:reliability`, `npm run type-check:charts`, `npm run lint`, `npm run api:types:check`, `npm run build`, full `npm run test:browser`, and focused cases `settings-account`, `context`, `layout`. Capture each actual exit code. From `backend/`, run `uv run python -m pytest` with `DJANGO_SETTINGS_MODULE=portfolio_management.test_settings` per project policy. Do not relax gates/baselines.
- [ ] Record tested SHA and directory, exact test counts, failures/retries and limits. Update evidence/tracker in a separate documentation commit if useful. Source changes after testing require affected gates again.
- [ ] Push and open one draft PR into `codex/frontend-modernization`, explaining the trigger (unavailable saved selection + unrelated settings save), before/after behavior and deliberate save-blocking policy. Stop for review. Report any D5 overlap for integration; do not merge either PR yourself.
