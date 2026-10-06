# D7 — Broker connections and security detail: characterized contracts

Recorded 6 October 2026 on base `49093a2d` (post PR #57/D6 merge `0167c409`), worktree
`Portfolio-management-d7`, branch `codex/broker-security-extraction-d7`. Every statement
below is read from the incumbent sources at that base (paths and line anchors in
parentheses) or reproduced by the committed characterization tests; discrepancies between
the accepted design sketches and the real wire are recorded explicitly, not silently
"fixed". No backend or financial code was changed.

Sources: `frontend/src/components/BrokerTokenManager.vue`, `frontend/src/views/database/SecurityDetailPage.vue`,
`frontend/src/services/api.ts`, `frontend/src/config/chartConfig.js`, `frontend/src/views/profile/ProfileSettings.vue`,
`backend/users/views.py`, `backend/users/serializers.py`, `backend/users/models.py` (read-only characterization),
plus the retained suites `frontend/tests/unit/components/BrokerTokenManager.spec.js`,
`SecurityDetailPage.crypto.spec.js`, `DetailRequests.spec.js`.

## 1. Broker connection management (incumbent `BrokerTokenManager.vue`)

### 1.1 Endpoints, methods and payloads (source: `services/api.ts` 1088-1345, `backend/users/views.py` 365-718)

| Action | Wire call | Frontend payload (verbatim) |
|---|---|---|
| List | `GET /users/api/broker_tokens/` | — |
| Save Tinkoff | `POST /users/api/tinkoff-tokens/save_read_only_token/` | `{ broker, token, token_type, sandbox_mode }` |
| Save IB | `POST /users/api/ib-tokens/` | `{ broker, token, account_id, paper_trading }` |
| Save Bybit | `POST /users/api/bybit-tokens/` | `{ broker, api_key, api_secret, testnet }` |
| Save OKX | `POST /users/api/okx-tokens/` | `{ broker, api_key, api_secret, passphrase, simulated_trading }` |
| Test Tinkoff | `POST /users/api/tinkoff-tokens/{id}/test_connection/` | — |
| Test IB | `POST /users/api/ib-tokens/{id}/test_connection/` | — |
| Revoke | `POST /users/api/revoke_token/` | `{ token_type: <provider>, token_id }` |
| Delete | `DELETE /users/api/{tinkoff\|ib\|bybit\|okx}-tokens/{id}/` | — |
| Broker options | `GET /database/api/brokers/` | — |

Backend facts that shape the contract (read-only):
- `broker_tokens` returns `{ tinkoff_tokens, ib_tokens, bybit_tokens, okx_tokens }` (views.py 366-380).
- Tinkoff save handles: invalid broker → 400; `verify_token` failure → 401/400; identical
  already-active token → 400 `{ message: "This exact token is already active", ... }`;
  identical inactive token → 200 `{ message: "Existing token has been reactivated", id }`;
  new token → 200 `{ message: "Token saved successfully", id }` (views.py 574-661).
- Tinkoff/IB `test_connection` respond `{ ..., token: <fresh serializer data> }` with the
  token key at the TOP LEVEL of the body and flip `is_active` server-side (views.py 429-487).
- Crypto viewsets report testing unsupported: 501 `"Crypto exchange token verification is
  not implemented yet"`; the frontend has no test button for them (views.py 682-704).
- Delete is server-rejected for active tokens: 400 `"Cannot delete active token.
  Deactivate it first."` (views.py 489-498).
- Revoke sets `is_active = False`, returns `{ message: "Token revoked successfully" }`.

Recorded wire discrepancies (preserved, not "fixed"):
- **IB list rows are `{ id }` only.** `InteractiveBrokersApiTokenSerializer` extends the
  base fields `["id", "token"]` and `token` is write-only, so the wire carries no
  `is_active`, `account_id` or `paper_trading` even though the model has them
  (serializers.py 238-247, 439-446; models.py 381-398). The incumbent renders IB rows with
  an error icon/„Invalid token" tooltip, an empty `Account: ` title and a permanent
  per-row Delete button, and — because the inactive filter tests the missing `is_active` —
  IB rows are hidden unless "Show inactive tokens" is checked. The extraction preserves
  this exact rendered behavior; enriching the IB wire is backend work outside D7.
- **The incumbent's Tinkoff post-test row replacement is dead code.** `testConnection`
  checks `response?.data?.token`, but `testTinkoffConnection` already resolves the body, so
  `response.data` is `undefined`; the row status actually updates through the unconditional
  `fetchTokens()` that follows (BrokerTokenManager.vue 747-755). The extraction keeps
  test→refresh→success semantics and drops the dead branch with a regression proving the
  list refresh still drives the row update.
- The IB `test_connection` endpoint has no server-side `verify_token` implementation, so a
  real click surfaces the generic failure mapping (`An unexpected error occurred` emitted
  to the parent). Incumbent behavior, retained.

### 1.2 Commands, identity and busy state (BrokerTokenManager.vue 743-779, 919-939)

- Test, revoke and delete are three distinct commands to three distinct endpoints;
  the revoke call carries `{ token_type: provider, token_id }` — provider and token id
  always travel together.
- Busy state is one map keyed by the string `` `${broker}-${tokenId}` `` used only by the
  test button (`isTestingConnection`). Same numeric ids across providers (`tinkoff-1` vs
  `ib-1`) already produce distinct keys; the extraction re-keys this as the typed pair
  `{ provider, tokenId }` and must keep it collision-free.
- Delete confirmations snapshot `brokerToDelete`/`tokenToDelete` before the dialog opens;
  the incumbent dialog text is generic ("permanently delete this token") and does NOT name
  the provider/connection. D7's accepted design requires the confirmation to name the
  broker/connection while keeping the delete vs revoke distinction ("must not imply
  deleting portfolio transactions"); this is an intentional, regression-pinned upgrade.
- Revoke/delete emit `success` ("Token revoked successfully" / "Token deleted
  successfully"); revoke failure goes through `handleError`. Neither revoke nor delete has
  incumbent row-busy state (only test does); row busy state for destructive commands is
  added per the D7 design ("row-scoped busy/error"), release guarded by request ownership.

### 1.3 Error mapping and emits (BrokerTokenManager.vue 694-720)

`handleError` maps: 400 + `message` containing `already active` → "Token Already Exists"
message dialog (and closes the form, keeping the draft — see §1.5); `response.data.error`
→ that message; 403 → permission text; no response → connectivity text; else
`error.message` or the generic text — all through `emit('error', ...)` to the parent
(ProfileSettings snackbars). `success`/`info` events: test success → "Connection test
successful"; unsupported provider test → info "Connection testing is not implemented for
this broker yet"; per-provider save success texts differ ("Token saved successfully" for
Tinkoff/IB, "Bybit token saved successfully", "OKX token saved successfully").
`BrokerTokenManager` keeps emits `error`, `success`, `info` as the compatibility surface.

### 1.4 Provider form fields, mapping and validation (BrokerTokenManager.vue 400-600, 950-1018)

- Broker select is fed by `GET /database/api/brokers/` (`{id, name}` records). Name
  mapping: `tinkoff` → tinkoff, `interactive brokers` → ib, `bybit` → bybit, `okx` → okx
  (case-insensitive substring); anything else opens the "Select Broker Type" radio dialog;
  Confirm applies provider defaults, Cancel clears the broker selection. Confirmation with
  no selected type emits `error` "Please select a broker type".
- Visible fields per provider: Tinkoff → API Token (password) + disabled Token Type
  (forced `read_only`) + disabled Sandbox switch (forced false, rules pin both); IB → API
  Token + Account ID + Paper Trading switch; Bybit → API Key (plain) + API Secret
  (password) + Testnet switch; OKX → API Key + API Secret + Passphrase + Simulated
  Trading switch. All required-text rules are `!!v || ...`.
- Save is double-gated: `v-form` v-model validity disables Save, and `saveToken()` calls
  `form.validate()` first (real async Vuetify validation in the browser; the unit-stub
  form always validates true — the rendered browser case exercises the real gating).
- Switching brokers clears every credential field and resets provider defaults
  (`handleBrokerSelection`, 950-987).

### 1.5 Credential-safety findings (fixed in D7 with regressions, per review focus 3)

- **F1 — response logging in the token path.** `fetchTokens` logs the entire
  `getBrokerTokens` response (`logger.log('Unknown', 'API response:', response)`),
  `getBrokerTokens` logs the axios response, and the save/test catch handlers log
  `error.response?.data` — the list body contains Bybit/OKX `api_key` values and DRF
  validation errors can echo rejected secret fields. D7 removes raw response/error-body
  logging from the directly touched broker path (component + the token adapters in
  `api.ts`); no request bodies are logged. Not a general API rewrite.
- **F2 — tinkoff reactivation leaks the draft.** The `reactivated` branch closes the form
  dialog and returns WITHOUT `form.reset()`/`resetNewToken()` (792-807), so the secret
  stays in memory and reappears if the dialog is reopened. Success paths must erase
  credential drafts; fixed with a regression.
- **F3 — "already active" rejection leaks the draft.** `handleError`'s already-active
  branch closes the dialog while keeping `newToken` (695-704). The form is closed, so the
  draft's open lifetime has ended; fixed to erase. (Other rejections keep the dialog open
  with values retained for retry — incumbent behavior, pinned by tests.)
- Secrets never enter Pinia, localStorage or display models, before or after D7; synthetic
  credentials exist only inside test inputs and are asserted absent from alerts, emitted
  notices and display models.

### 1.6 Display surface (BrokerTokenManager.vue 1-601)

Four expansion panels (Tinkoff/Interactive Brokers/Bybit/OKX) with counts; "Show inactive
tokens" checkbox filters `is_active` (default hidden); loading progress bar replaces the
panels on first fetch. Row content: status icon (`is_active` → success check / error
cross; tooltip "Valid token"/"Invalid token", crypto "Stored token"/"Inactive token");
title (Tinkoff: "Read Only Token"/"Full Access Token" by `token_type`; IB: `Account:
{account_id}`; crypto: `API key: {api_key}`); subtitle "Created on {formatted date}"
(`en-GB` 2-digit day/short month/numeric year + 2-digit time, `N/A` when missing,
"Invalid Date" on parse failure) + chips: Paper Trading (IB), Testnet (Bybit), Simulated
Trading (OKX), Inactive (all when `!is_active`). Row actions per §1.2; empty provider
lists render "No tokens found" info alerts. `brokerOptions`, `getTokenStatusText` and
`getTokenStatusColor` are incumbent dead code carrying lint-baseline warnings; the
extraction removes them and their stale baseline entries.

## 2. Security detail (incumbent `SecurityDetailPage.vue`)

### 2.1 The five resources and their exact triggers (519-527, 616-642)

| Resource | Fetcher (existing signature) | Trigger watch sources |
|---|---|---|
| detail | `getSecurityDetail(id, account, options)` then `getChartOptions(security.currency)` | `[canRead, dataRefreshTrigger, route.params.id, selectedAccountId]` |
| price | `getSecurityPriceHistory(id, period, options)` | `[canRead, dataRefreshTrigger, route.params.id, selectedAccountId, selectedPeriod]` |
| position | `getSecurityPositionHistory(id, period, account, options)` | same sources as price (one watch, two runs) |
| transactions | `getSecurityTransactions(id, pagination, period, account, options)` | price sources + `transactionOptions` (deep) |
| accounts | `getAccountChoices(options)` with `context.committed` params | `[canRead, dataRefreshTrigger]` |

- All five go through `usePortfolioRequest` (latest-request generations + abort + context
  revision/canRead invalidation, `useLatestRequest.ts`); snapshots are frozen with the
  committed context and pagination attached.
- Route-id change (sync watch) invalidates detail/price/position/transactions (not
  accounts); route-id/account/period changes (sync watch) reset the transactions page to 1
  while preserving `itemsPerPage`. `context.committed.revision`/`canRead` changes
  invalidate ALL queries via `usePortfolioRequest`'s internal watch.
- Detail query = two awaits (security then chart options by its currency);
  `chartOptionsLoaded` gates both chart sections. `loading` = `!context.canRead ||
  detailQuery.loading`; `loadError` = the OR of all five query errors, rendered as the
  "Unable to load part of this security" alert; a settled state without a security shows
  "Security not found or error loading data."
- The parent title event `update-page-title` fires synchronously on security-name changes
  with `value?.name ?? ''` (route compatibility surface, App.vue `updatePageTitle`).
- Initial request counts per mounted page (characterized, must not change): 1 detail +
  1 price + 1 position + 1 transactions + 1 accounts = 5 fetches.

### 2.2 Request params (wire semantics preserved)

- `selectedAccountId` = `null` for the all-selection/no account else `selectedAccount.id`;
  `period` starts `'1Y'`; transactions pagination starts `{ page: 1, itemsPerPage: 10 }`
  with options `[10, 25, 50, 100]`; the rows-per-page select and v-pagination own
  `transactionOptions`; "Showing X-Y of Z entries" uses page math against
  `total_items` (`totalTransactions`), never a client count.
- `accountOptions` = `formatAccountChoices(getAccountChoices().options)` with
  divider/header/option item slots (the shared prepare_account_choices shape).

### 2.3 Display sections and conditional rules (1-451)

- WorkspacePage title `security?.name || 'Security'`, description
  `` `${security.ISIN || 'No ISIN'} · ${security.instrument_type} · ${security.currency}` ``.
- Basic Information (ISIN, Type, Currency, First Investment — raw wire values).
- Performance Metrics table rows: Current Position (always); Buy-in Price and Current
  Price only when truthy; Current Value; Total Accrued Interest only for
  `instrument_type === 'Bond'` when `bond_data.total_aci !== undefined && !== '–'`
  (with the caption "(net of ACI paid at acquisition)"); YTM at Acquisition for Bond when
  `bond_data.ytm` truthy; Realized Gain/Loss; Unrealized Gain/Loss; Capital
  Distribution; IRR. All values render as server display strings, never reformatted.
- Crypto Rewards section (Crypto only): Native rewards =
  `crypto_reward_native_quantity`, Fiat reward value = `crypto_reward_fiat_value`.
- Bond Information section (Bond && `bond_data`): left table — Notional label switches
  `Current Nominal`/`Notional` by `is_amortizing` (row only when `current_notional`
  non-null), Initial Nominal only when amortizing (non-null), Issue Date, Maturity Date,
  Bond Type = `coupon_type || 'Standard'` + "(Amortizing)" caption, Credit Rating when
  present; right table — Coupon per Bond (non-null), Coupon Rate (truthy), Coupon
  Frequency as `{n}x per year`, Next Coupon Payment, and when `current_aci` exists:
  Current Accrued Interest (`aci_amount`) and Days Accrued as
  `{aci_days} / {total_days} days`. Unknown/missing bond metadata hides only the
  affected rows, never the section.
- Chart sections (Price History / Position History) render only when
  `chartOptionsLoaded`; each embeds a `TimelineSelector` (shared period control,
  effective-date-aware YTD visibility) and a 400px `LineChart` with skeleton while
  loading. Chart data/options construction (client-side period filtering on top of the
  period-parameterized server query, last-point extension to `effectiveCurrentDate`,
  `getTimeConfig` axis buckets, y titles `Price (${currency})` / `Position`,
  position `beginAtZero`) is chart rendering owned by this page and stays UNCHANGED at
  the entrypoint (or a clearly named unchanged legacy presentation module); overview
  sections expose `price-chart`/`position-chart` slots. No ECharts, no numeric-string
  translation, C4/C5 untouched.
- Transaction History: `v-data-table` (Date/Account/Description/Type/Cash Flow,
  disable-sort) rendering rows through the shared `TransactionRow` with
  show-single-cash-flow/show-broker-account and no actions; bottom slot owns rows-per-page,
  the "Showing …" range and `v-pagination`.

### 2.4 Value-parity pins (from the wire, never through Number)

- Bond percentage price display `"99.125000%"` and high-precision crypto quantities
  (`"0.010000000"`) must survive extraction verbatim, including comma-grouped and
  beyond-safe-integer strings; display values cross the boundary as strings only.
- Missing values render as the server's markers (`–`, `NA`, `N/A`) or omit the row per
  §2.3; missing bond metadata keeps the section with explicit gaps.

## 3. Baseline gates on pristine base `49093a2d` (this worktree, Node v24.20.0)

All exit codes captured directly into per-gate logs (no pipes): `test:unit` 87 files /
775 passed — 0; `type-check` — 0; `type-check:reliability` — 0; `type-check:charts` — 0;
`api:types:check` — 0; `lint` 0 errors / 13 warnings — 0; `build` — 0. Focused incumbents:
`BrokerTokenManager.spec.js` + `SecurityDetailPage.crypto.spec.js` + `DetailRequests.spec.js`
22 passed — 0. (The D6-recorded 773 was the review-round-3 head; the merged base carries 775.)

## 4. D7 execution record

Branch `codex/broker-security-extraction-d7` (worktree `Portfolio-management-d7`), base
`49093a2d`. Task-sized commits, each preceded by its RED runs:

- `400bf756` task 0 — contract inventory (this document §1-§3) + 18 rendered/handler
  characterization pins (broker `incumbent.spec.js` 10, security `incumbent.spec.js` 8),
  green against the pristine incumbent; baseline gates §3.
- `146bb2ca` task 1 — `features/brokers/{types.ts,useBrokerConnections.ts}` +
  `connections.spec.ts` (24 cases, RED as an unresolved module; the ownership/release,
  once-only, retained-subject and credential-hygiene cases fail against the incumbent
  semantics by design). Removes raw response/error-body logging from the token adapters
  (api.ts) and attaches causes to the two mapped test errors (two moved
  preserve-caught-error baseline fingerprints legitimately fixed).
- `2d74abb2` task 2 — `BrokerConnectionList.vue` + `BrokerConnectionForm.vue` +
  `BrokerTokenManager.vue` rewritten as the composing compatibility entrypoint.
  `forms.spec.ts` 12 cases RED (unresolved components). The retained
  `BrokerTokenManager.spec.js` keeps every pin, re-driven through the form child.
  Three dead-code lint fingerprints of the rewritten file removed from the baseline.
  Deliberate, review-focus-driven corrections pinned RED-first against the incumbent:
  the delete confirmation names the exact connection and states portfolio transactions
  are not affected; the tinkoff reactivation and already-active close paths erase the
  credential draft.
- `84136726` task 3 — `features/securities/{types.ts,useSecurityDetail.ts}` owner over
  the five characterized resources with exact trigger/invalidation parity;
  `SecurityDetailPage.vue` rewired (template untouched). `detail.spec.ts` 10 cases RED
  (unresolved module): per-trigger request counts, A/B and period overlap, session
  invalidation, independent price recovery, pagination reset, disposed-owner silence.
- `d2e02eb1` task 4 — `SecurityOverview.vue` / `SecurityMetadata.vue` /
  `SecurityActivity.vue` prop-driven sections + `price-chart`/`position-chart` slots;
  the page builds views through pure string-preserving mappings (no Number conversion);
  charts stay at the entrypoint. 7 section cases RED (unresolved modules) including the
  accepted `99.125000%` bond example and beyond-safe-integer strings.
- Task 5 — `tests/browser/brokers-security-d7.mjs` + `--case brokers-security-d7` in
  `run-smoke.mjs` + the `brokersSecurityD7Flow` fixture block (stateful token
  inventory, recorded write bodies, queued save rejection, per-id security resources
  with failure switch, populated account choices); gates below.

Recorded deviations (all behavioral corrections required by the handoff's review
focuses, each regression-pinned; incumbent parity otherwise byte-for-byte):
(1) delete confirmation names the subject; (2) delete subject survives a rejection so a
retry retargets the same token (the incumbent dropped the snapshot in its `finally`);
(3) credential drafts are erased on every accepted close path incl. reactivation and
already-active (the incumbent leaked them); (4) superseded/disposed broker requests no
longer emit, refresh or release other requests' busy tokens; (5) `confirmDelete` is
once-only per snapshot; (6) raw broker response/error-body logging removed from the
touched token path. Wire discrepancies preserved and documented in §1: IB rows are
`{id}`-only (hidden by default), the tinkoff post-test response branch was dead code
(the refresh drives the row update) and is dropped with the refresh semantics pinned,
and the per-provider save endpoints/payloads are unchanged.

Known flow limitations: the d7 browser case expands the Vuetify expansion panels
(rows are not in the accessibility tree while collapsed) and resets the synthetic token
inventory at the start of each pass so both desktop routes exercise identical state.
Captures under `docs/design/assets/brokers-security/` (broker list desktop/mobile,
masked form error, delete confirmation, bond/crypto desktop, bond tablet/mobile,
200% zoom bond) are taken from synthetic fixtures; no real credentials anywhere.

## 5. Final gate matrix (actual exit codes)

Frontend, from `frontend/` with the declared Node v24.20.0 (portable) and lockfile,
run sequentially at committed head `cb5131b1`:

| Gate | Result |
|---|---|
| `npm run test:unit` | 0 — 92 files / 846 passed |
| `npm run type-check` | 0 |
| `npm run type-check:reliability` | 0 |
| `npm run type-check:charts` | 0 |
| `npm run api:types:check` | 0 |
| `npm run lint` | **1** — one new diagnostic (unused `lacksText` helper in the new flow file) |
| `npm run build` | 0 |
| `npm run test:browser -- --case brokers-security-d7` | 0 — desktop/tablet/mobile × 2 routes, zero fixture mismatches |
| `npm run test:delivery` | 0 |
| focused `imports-d6`, `layout`, `context`, `dates`, `requests`, `recovery`, `dialogs`, `dialog-recovery`, `d4`, `d5`, `settings-account`, `charts-c2`, `charts-c3` | all 0 (charts-c3 runs both renderer-flag states internally) |
| `npm run test:browser` (full) | 0 — 18 routes × 4 viewports, zero fixture mismatches |

Fix head `b409d9eb` (dead helper removed): `npm run lint` — 0 (0 errors / 8 baseline
warnings, baseline unchanged from 49093a2d minus the three legitimately-fixed
fingerprints documented above) and `--case brokers-security-d7` re-run — 0, zero
mismatches. Final head `d16b21dc` commits the IB test-parity fix and a spec cleanup
that every test run since task 2 had already exercised in the working tree — the
committed tree is byte-identical to the tree the full matrix above ran — and at
`d16b21dc` the focused broker/security suites (83 tests), `npm run lint` and
`npm run type-check` were re-verified, all exit 0. Backend at `b409d9eb`:
`DJANGO_SETTINGS_MODULE=portfolio_management.test_settings uv run python -m pytest`
— exit 0, 1386 passed / 10 skipped, coverage 83.25% (identical to the D6 baseline; D7
touches no backend file).

Type coverage of the new tests: `tests/unit/features/brokers/connections.spec.ts`,
`forms.spec.ts` and `tests/unit/features/securities/detail.spec.ts` are explicitly
listed in the main tsconfig `include` (the D6 socket-spec precedent); verified with
`vue-tsc --noEmit --listFilesOnly` (all three resolved, plus the feature modules
through `src/**/*`). Vitest transpilation was never represented as type-checking.

