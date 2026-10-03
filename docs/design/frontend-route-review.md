# D5 route-family review — evidence and contracts

Date: 3 October 2026. Scope: task 19/D5 of the [design/workflow plan](../superpowers/plans/2026-09-08-frontend-design-workflows.md), executed on branch `codex/frontend-route-rollout-d5` (base `d1989802` on `origin/codex/frontend-modernization`, the C3-merged implementation branch plus the D5 handoff documents). All captures and browser runs use the synthetic fixture harness (`frontend/tests/browser/fixtures.mjs` + `tests/browser/run-smoke.mjs`); **every value shown is synthetic data**. No production account, broker or financial value is displayed anywhere in this document.

This ledger is the working D5 record: the behavioral contract inventory recorded **before** editing (Task 0), the per-family rendered evidence as each family passes, and the honest list of remaining acceptance gaps. Financial display strings, payloads, event names and request behavior are quoted from the incumbent code and preserved verbatim by the migration; nothing here authorizes a backend, financial or API change.

## Baseline gates (clean starting commit `d1989802`)

Actual process exit codes captured per command (logs in the executor's ignored `temp_files/d5-gates/`, not committed):

| Gate | Result | Exit |
|---|---|---|
| `npm run test:unit` | 74 files / 545 passed | 0 |
| `npm run type-check` | clean | 0 |
| `npm run type-check:reliability` | clean | 0 |
| `npm run type-check:charts` | clean | 0 |
| `npm run lint` | 0 errors / 35 warnings (baseline unchanged) | 0 |
| `npm run api:types:check` | match | 0 |
| `npm run build` | ok | 0 |
| `npm run test:browser` | 18 routes × 4 viewports, zero mismatches | 0 |
| `npm run test:delivery` | within budget | 0 |
| backend `uv run python -m pytest` (test settings) | 1386 passed / 10 skipped | 0 |

The historical reference numbers in the handoff (538 units, 72 profiles, 1386/10) are superseded by these current results; the C3 review rounds added the delta (545 vs 538).

## Route/heading ownership facts (recorded before editing)

- `App.vue` renders the legacy `h1[data-testid="legacy-page-heading"]` from the `update-page-title` emit **only while no `WorkspacePage` is mounted** (`workspaceHeadingCount`). A route that adopts `WorkspacePage` owns the single `h1[data-testid="workspace-page-heading"]` and the shell heading disappears — one heading per route is structural, not per-emitter.
- The workspace context strip (account · valuation date · reporting currency) is **not rendered** on `/profile*`, `/database*` and `/summary` (`showComponents` in `App.vue`). D5 preserves this; it does not add the strip to those routes. `/summary` additionally shows a `SettingsDialog` in the app bar (`showSettingsDialog`), which must survive.
- Routes and names in `frontend/src/router/index.js` are frozen for D5: `/login`, `/register`, `/dashboard`, `/open-positions`, `/closed-positions`, `/transactions`, `/profile` (+`/edit`, `/settings` children of `ProfileLayout`), `/database` (+`brokers|accounts|prices|securities|fx` children of `DatabasePage`), `/database/securities/:id` (top-level `SecurityDetail`, **not** a database child), `/summary`, `/debug-auth` (DEV-only), `/` → `/dashboard`.
- `DatabasePage` titles use an EN DASH (`Database – Brokers`); the nested `<router-view>` does not forward child title emits.
- Table state for Brokers/Accounts/Securities/Prices/FX comes from the **single global in-memory** `useTableSettings` → `appStore.tableSettings` (`{ dateFrom, dateTo, timespan, page, itemsPerPage, search, sortBy }`, no persistence, shared across those tabs in a session, search debounced 500 ms, every setter resets `page: 1`). Positions pages own their own per-user persisted view model (`usePositionsTableView`, `positionsTableView.v1.u<id>.<table>`).

## Contract inventory per route family (Task 0; behavior to preserve)

### `/summary` (SummaryPage)

- Requests: `performanceQuery` → `getAccountPerformanceSummary` (`GET /summary/api/summary_data/`), `breakdownQuery` → `getPortfolioBreakdownSummary(year)` (`GET /summary/api/portfolio_breakdown/`), `yearsQuery` → `getYearOptions` (`GET /api/get-year-options/`). All three run through `usePortfolioRequest` with context snapshots; performance/years re-run on `[context.canRead, dataRefreshTrigger]`, breakdown additionally on `selectedYear` — the breakdown-year filter retains its own request behavior.
- Wire shape (backend `services/summary.py`): `{ public_markets_context, restricted_investments_context, total_context }`; each context `{ years, lines }` with `years = ["YTD", ...calendar years descending..., "All-time"]`; each line `{ name, data: { [year]: { "BoP NAV", "Cash-in/out", "Return", "FX", "TSR percentage", "EoP NAV", "Commission", "Fee per AuM (percentage)" } } }` (server-formatted strings; frontend display labels differ: `Cash-in/(out)`, `TSR`, `Commissions`, `Fee per AuM`); groups carry a final `Sub-total` line inside `lines`; `total_context.line` is the TOTAL row. Frontend validation rejects a response missing any of the three contexts.
- The eight metric leaves and their display labels, the `N/A` missing-value marker, YTD/All-time column highlighting, group ordering (Public Markets then Restricted Investments) and the TOTAL row must all remain reachable and unchanged in every view mode.
- Breakdown table: categories `consolidated`/`unrestricted`/`restricted` (`*_context` keys, rendered uppercase), 13 data leaves + name, `(%)` italic subheaders, `(${appStore.selectedCurrency})` reactive units, year selector with divider items from `getYearOptions` (`table_years`), `TOTAL` row emphasis. `hasBreakdownData` gates on `consolidated_context` non-empty.

### `/open-positions`, `/closed-positions`, `/transactions` (already migrated D3/D4)

- Accepted D4 state: 20/16 leaves, presets/custom persistence, server-owned order (`customKeySort` no-op + `itemsLength`), hidden-sort notice with Clear sort, key-based pinning, cash/TOTAL footer semantics, `WorkspaceActions` hierarchy (Add transaction primary; Import transactions secondary; FX/Transfer/Merger overflow), exact-identity `ConfirmActionDialog` deletion with generation/session guards, form dialogs with section labels and focus safeguards. D5 touches these only for token/layout integration; no replacement table models.

### `/database` landing + children (Data family)

- `DatabasePage`: centered `v-tabs` as router-links (Brokers, Accounts, Securities, Prices, FX — that display order), `activeTab` derived from `route.path.includes()` priority accounts→brokers→securities→prices→fx; EN-dash titles; no data of its own.
- Brokers: `getBrokersTable` POST with `{ dateFrom: null, dateTo: effectiveCurrentDate, page, itemsPerPage, sortBy, search }`; headers Name/Country/Accounts/Securities/First Investment/Total NAV/Cash/IRR/Actions; ` TOTAL ` footer over `no_of_accounts, no_of_securities, nav, cash, irr`; IRR italic; edit pencil/delete icons; `window.confirm` quoting the broker **name** before `deleteBroker(id)`; `BrokerFormDialog` (`broker-added`/`broker-updated` → refetch).
- Accounts: same request pattern; dynamic one cash column per currency found in `accounts[].cash` keys (children headers `cash_<CCY>`); edit pre-fetches `getAccountDetails(id)` (the details payload feeds the dialog, not the row); `window.confirm('Are you sure you want to delete this account?')` (no identity — candidate for the shared exact-identity confirmation without changing the constraint level); `AccountFormDialog` (`account-added`/`account-updated` → refetch); server-driven form structure (`/database/api/accounts/form_structure/`), `broker` key unwrapped to its id on submit.
- Securities: `getSecuritiesForDatabase` POST; name cell links to `SecurityDetail` by id; headers Type/ISIN/Name/First Investment/Currency/Open Position/Current Value/Realised/Unrealised/Capital Distribution/IRR/Actions (British titles, `realized`/`unrealized` keys); `Add Security` + `Record Merger` actions; `SecurityFormDialog` (`security-added`/`security-updated` → refetch) and `MergerDialog` (`created` → refetch); edit pre-fetches `getSecurityDetails`; `window.confirm` without identity before `deleteSecurity`.
- Prices: filters **not live** — Asset Types/Accounts/Securities autocompletes + Start/End Date fields only take effect on **Apply Filters** (copies to `appliedFilters`, resets page); selecting an account auto-selects all returned securities; `Add Security`, `Add Price Entry`, `Import Prices` (success color) actions; headers Date/Security/Asset Type/Currency/Price/Actions; price strings (`98.50` percent-of-par for bonds included) displayed verbatim; click-to-edit price span; `getPriceDetails` pre-fetch; inline delete dialog listing Date/Security/Price with currency; retry re-runs only failed queries; `PriceFormDialog` (`price-added`/`price-updated` → refetch) and `PriceImportDialog` (`prices-imported` → refetch).
- FX: `DateRangeSelector` + Search + Rows per page toolbar; pivot grid from `utils/fxPivot.js` (`PAIR_ORDER` first, then alphabetical; one row per date; cells `{rate, id}`); filled cells show the rate and open edit via `getFXDetails(id)`; empty cells (`—`) open Add prefilled `{date, from_currency, to_currency}`; `Add FX Rate`/`Import FX Rates` actions; `FXDialog` (`fx-added`/`fx-updated` → refetch, `fx-delete` → page-level confirm then `deleteFXRate`); `FXImportDialog` (`import-completed`/`refresh-table` → refetch); date range init guards against a duplicate first `list_fx` POST.
- `/database/securities/:id` (SecurityDetail, top-level route): title = security name (sync watch); Broker Account scope selector from `getAccountChoices` (option/divider/header shapes); `getSecurityDetail(id, account)` + client chart config, `getSecurityPriceHistory(id, period)`, `getSecurityPositionHistory(id, period, account)`, `getSecurityTransactions(id, pagination, period, account)`; TimelineSelector periods with client-side start-date filter and synthetic last point at effectiveCurrentDate; sections Basic Information / Performance Metrics / Crypto Rewards (crypto) / Bond Information (bond, incl. coupon details) / Price History / Position History / Transaction History (TransactionRow with `show-single-cash-flow`, local rows-per-page); route-change `invalidate()` on all four queries. D5 applies the page/context shell only.

### `/profile*` and auth

- `ProfileLayout`: side nav `User details`/`Settings` + Logout; Delete Account dialog requires typing **DELETE** (case-sensitive) before the destructive button enables; success path `deleteUserAccount()` → `clearTokens()` → redirect **/register**. Children render in `md=8` column.
- `ProfilePage`: profile fields via `formatLabel`; Change Password dialog (old_password/new_password1/new_password2, autocomplete current-password/new-password, per-field errors, mismatch check client-side).
- `ProfileEdit`: dynamic fields from `getUserProfile`; `editUserProfile(form)`; username disabled; success snackbar + delayed redirect to `/profile` (1 s).
- `ProfileSettings`: seven setting fields (`default_currency`, `use_default_currency_where_relevant`, `chart_frequency`, `chart_timeline`, `NAV_barchart_default_breakdown`, `digits` 0–9, `selected_account` via grouped choices); save strips UI keys, `updateUserSettings(payload)`, then **`context.changeContext(patch)`** — the context-affecting save path (same serialized confirmation as the shell); `AccountGroupManager` (groups CRUD via `/users/api/account-groups/`, plain confirm on group delete, no confirm on account removal) and `BrokerTokenManager` (D7 scope, untouched) with error/success/info snackbars.
- `LoginPage`/`RegisterPage` + forms: centered narrow card; `LoginForm` (Username/Password, autocomplete username/current-password, exposed `setErrors`/`clearError`, `non_field_errors` → general alert; Proxy-string special case) → `authStore.login` → redirect `/profile`; authenticated users visiting auth routes are redirected to Profile by the router guard. `RegisterForm` (Username/Email/Password/Confirm Password; email has **no** autocomplete attribute; server-driven validation only) → register → success dialog → `/login`. Footer links cross-link Login/Register.

### Dialogs (public interfaces frozen)

- `AccountFormDialog` `modelValue`/`editItem` → `account-added`/`account-updated`; `BrokerFormDialog` → `broker-added`/`broker-updated`; `SecurityFormDialog` → `security-added`/`security-updated`/`security-skipped` (+ `isImport` trimmed payload, conflict sub-view with `confirm: true` re-submit); `PriceFormDialog` `modelValue`/`editItem`/`securities` → `price-added`/`price-updated` (price submitted as string); `FXDialog` `modelValue`/`editItem`/`prefill` → `fx-added`/`fx-updated`/`fx-delete` (rate string; pair locked in edit/prefill); `PriceImportDialog` → `prices-imported` (vee-validate cross-field rules; no Cancel button — scrim/esc only); `FXImportDialog` → `import-completed`/`refresh-table` (auto vs manual; AbortController stop + cancel endpoint); `AssetTransferDialog` → `transfer-completed` (persistent; camelCase payload; quantity from `getSecurityPosition`); `MergerDialog` → `created` (snake_cased by API layer); `UpdateAccountPerformanceDialog` → `update-started`/`update-error` (two-phase: validate endpoint, parent runs the SSE).
- All list-page dialogs load through `defineAppDialog` + `useFirstOpen` (stay mounted after first open) and invalidate via the parent's refetch. Legacy `blue darken-1`/`red darken-1` button colors and hand-written confirm markup are the restyle surface; event names, payloads, validation and completion invalidation are not.

## Rendered evidence ledger

Filled per family as it passes; states are populated / empty / filtered-empty / error unless marked N/A with a reason. All screenshots live under `docs/design/assets/frontend-workspace/` with `d5-` names.

| Route | Fixture/account | Viewport(s) | State | Keyboard/focus | Context/data match | Screenshot | Result | Remaining issue |
|---|---|---|---|---|---|---|---|---|
| _Task 0 — not yet rendered; rows land with each family below_ | | | | | | | | |

## Human visual-review checklist (for the reviewer)

- [ ] `/summary`: one Performance heading; period control labelled; single-period default matches returned YTD (or latest year); all eight metrics visible per period; comparison/history modes keep every group, Sub-total and TOTAL; breakdown year filter still refetches independently; `(USD)` follows reporting currency.
- [ ] Data landing + Brokers/Accounts/Securities: one heading per route; primary create action; identity-first rows; footers (` TOTAL `) retained; delete confirmations name their subject.
- [ ] Prices/FX: unit labels; pivot orientation; import entry points reachable.
- [ ] Profile/auth: narrow forms; one primary submit; typed DELETE still required; settings save still switches currency/digits app-wide.
- [ ] Mobile 390 px and 200 % zoom: no clipping; controls hit-testable; dialogs single-column.
