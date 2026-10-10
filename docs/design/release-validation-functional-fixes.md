# Real-data validation corrections — phase A evidence ledger

Date: 10 October 2026. Branch `codex/release-validation-functional-fixes` (dedicated worktree `D:\Developing\Portfolio-management-relval-fixes`), base `f32e7d09` (`origin/codex/frontend-modernization`: PR #61/D8 merged plus the correction plan). Scope: **phase A Tasks 1–3 complete** (statuses below; two review rounds incorporated). The correction plan transcribes the owner's real-data annotations from the C5b release-validation run. Phase A was reviewed twice by the owner; both rounds are folded into the commits listed here.

## Task 1 — date selection, historical boundary and inception

### Frontend (commits `1e373dee`, `d697cba7`, `2e2b0451`)

- **Displayed range / request reconciliation on a historical valuation date**: a persisted custom range (From=2026-01-01, To=2026-10-09) reconciles when a valuation date of 2024-06-30 commits — `calculateDateRange` clamps a custom To *and From later than* the effective date, `DateRangeSelector` clamps its displayed local bounds when the effective date changes, and `DashboardPage` clamps both the request start and end. Verified with a mounted unit regression (`DashboardPage.requests.spec.ts`: exactly one accepted refresh; persisted params and outgoing query agree on `2024-06-30`) and by the rendered browser flow (`dates` case: displayed activator text `30 Jun 2024 ➔ 30 Jun 2024`, one `get-nav-chart-data` request with both bounds clamped).
- **Calendar-picker commit with a keyboard guard** (`2e2b0451`): the first implementation committed on `update:model-value`; the rendered `dates` case caught a real defect — Chrome native date inputs fire `input` **and** `change` on every segment edit, so every intermediate valid date (2025-09-08 → 2025-01-08 → 2025-01-03 on the way to 2025-12-31) was pushed through the context owner, and each commit's draft resync rewrote the input value mid-edit, resetting the native edit session and swallowing the next keystroke. The composable (`useValuationDateDraft`) now arms a guard on `keydown`: a keyboard-preceded `change` defers to the blur/Enter commit (typed segment path), while a `change` with no preceding keydown — the browser calendar-picker path, which the plan requires to commit without Enter/blur — commits immediately. Verified against the real rendered control: typed 2025-12-31 produces exactly one settings POST; a `change` without keydown commits at once; both trigger exactly one accepted NAV refresh. The composable unit tests (10/10) never caught this — the rendered case did, which is why the review required real-control verification.

### Backend (commit `0086f32e` — PROTECTED, needs-approval)

- **All-time was broken outright**: `_get_earliest_date_for_accounts` returns a `datetime` (`Min` over the datetime `date` column) which the legacy window compared against `date` objects — `TypeError`, HTTP 500 on every All-time request. The owner's real-data finding reproduced.
- **Requested From before the scope's inception sampled pre-inception periods** (From=2000 → years of empty samples, a zero IRR base, solver-unavailable IRRs).
- **Fix** (`services/charts.py get_nav_chart_data`): the authoritative effective start is the **later of the requested From and the selected scope's canonical inception** (earliest transaction date, normalized to a calendar date). All-time uses the inception. An inception after the effective end falls through to the honest empty outcome (`outcome: 'empty'`). Zero-valued observations **after** inception are retained.

Regressions: `TestNavInceptionFloor` (8 cases — floor from an early From, All-time at inception, inception-after-end honest empty, zero retention, **empty scope returns honest empty even for an explicit From**, per-scope isolation, cash-only inception, both IRR semantics across the sampled intervals); contract tests seeded with canonical inceptions so parity/units/intervals stay non-empty. Isolation: the backend commit is separately labelled for a **needs-approval draft PR** (protected chart/NAV chain per `Steerings/Calculation Conventions.md`); legacy payloads unchanged; no formula changes — only the sampling window start.

## Task 2 — year options, performance and security resource failures

### Year-options wire mismatch (commits `66c9ed9e`, `3e9e87b3`, `d697cba7`)

Source-confirmed on the base and re-confirmed against the real backend: `get_year_options_api` returns numeric years as `{text, value}` **strings**, a `{divider: true}` separator and the special All-time/`ytd` ranges — while `getYearOptions` demanded an integer array. On real data every year-options fetch threw `Invalid year options response`, so the positions pages surfaced "Unable to load positions or year options" and Summary surfaced its resource-failure banner with an empty year menu (synthetic fixtures fed integers, so focused runs never saw it).

- **Fix**: one explicit typed adapter (`YearOption`) in `services/api/database.ts` with strict per-entry validation; `calendarYearOptions` derives the numeric-year subset for Summary's breakdown selector; PositionsPageBase consumes the server list as authoritative (its All-time/YTD entries map to the timespan labels, calendar years stay numeric, dividers pass through); the selected Summary year defaults into the offered range.
- **Regressions**: `yearOptions.spec.ts` pins the exact real wire (captured from the disposable copy: years, divider, specials), malformed-entry rejection, the Summary filter; PositionsPageBase behavioral coverage mounts the real component against the real wire shape — no year-options failure banner, adapted items, no raw `all_time` in the menu; the pre-existing integer-wire mapping test and the `apiContracts` year test updated to the authoritative wire; spec mocks across RoutePatterns/DetailRequests updated; the browser fixture wire replaced with the real labelled-option/divider/special-range contract. Empty-history, historical-valuation and failed-year-options-fetch states are covered by the mounted positions/summary specs (failure keeps a readable safe selected label; no misleading selection).

### Account performance failure — diagnosed as absent precomputed data

Probed read-only against the disposable copy: `summary/api/summary_data/` returns **200 with empty contexts** (`years: [], lines: []` for all three groups) for the probed scope/period — the backend confirms the account performance data is absent, not an endpoint/serialization/calculation error. With the year-options adapter in place the year selector works, and Summary renders the honest empty state; no catch-all error mask was added. Owner verification with a data-bearing year remains part of the manual pass.

### Bond partial-load alert — partially diagnosed (not fixed)

Status: **partial — reproduced and characterized, page-level trigger still unproven.** Reproduction on the disposable copy (bond with bond metadata): the page shows "Unable to load part of this security" while **all three sub-requests return HTTP 200** and both history envelopes carry `chartV2` with `outcome: 'ready'` (series `price`/`position`), and transactions 200 with a characterized empty list. The rendered page shows one modern exact-values table (display parity verified against its API response) and one legacy fallback canvas — a mixed per-document rendering. The production parser run over the captured real envelopes reported a **context mismatch**: the real envelope context carries the committed broker selection (`{type: 'broker', id: …}`, `accountIds: []`, effective date as configured) — the exact page-level trigger (hypotheses: the account-scoped request parameters or the empty-transactions path interacting with the partial-failure aggregation) is **not reproduced through the mounted page yet**. Recorded per the plan's rule for unreproduced findings, with the probe evidence preserved locally.

Planned absent-data breakdown-row behavior (explicitly accounted): the plan's rule — hide portfolio-breakdown rows only when **all** relevant cells are explicitly absent under the documented response contract, always retaining numeric zero, meaningful N/A/status and totals — is **not implemented in this pass**; no code change touches breakdown rows in phase A, so current behavior (zero/status/totals preserved, rows never hidden) is unchanged. The rule's RED tests land with the Task-2/6 implementation in a later phase.

## Task 3 — account-based price import and progress readability

**Complete.** Two real defects found and fixed:

- **The consumer called a nonexistent method** (`377b1245`): `PriceImportConsumer.import_prices` filtered resolved securities through `security.position(...)` — `Assets` has no `position` method; the real helper is the module-level `services.positions.position(asset, date, investor, account_ids)`. **Every account-based price import died before importing anything** with `Global error: 'Assets' object has no attribute 'position'`. The consumer now calls the real function through `database_sync_to_async` with the same argument order — no formula change (the call semantics — scope-restricted positive position at the effective date — are unchanged). Consumer-level regressions (`backend/tests/unit/imports/test_price_import_consumer.py`, draining the async generator against seeded committed data, no ASGI machinery, no network): a single-account command resolves only that account's holding; a multi-account command resolves the union; a flat (buy+sell) position is not eligible; an account selection without holdings completes with the explicit `no_eligible_securities` event. The frontend payload was never at fault (as the plan suspected — the `accounts` field was already sent).
- **Explicit no-eligible-securities result** (frontend + consumer): an account-based selection resolving zero eligible securities now completes with `no_eligible_securities: true` and a plain-language message instead of a generic "completed" 0/0 stream, and `PriceImportDialog` renders it as an explicit info result (`data-testid="no-eligible-securities"`) instead of a generic error alert.
- **Account payload pinned at the dialog boundary** (`PriceImportDialog.accounts.spec.ts`, real rendered teleported dialog): the exact selected identities reach `importPrices` — `accounts: [7, 11]` multi, `[7]` single — alongside `securities: [42]`; the single-account test submits through the rendered dialog button. The spec fixture now mirrors the real serializer wire (frequency choices weekly/monthly/quarterly/yearly — the synthetic `'D'` choice was unfaithful and corrected to `weekly`, `eac48d4f`).
- **Progress label readability** (`ProgressDialog.readability.spec.ts`): the completion percentage moved out of the moving fill into a stable contrasting element (`data-testid="import-progress-label"`, `text-body-2` spans, 12px bar) — the old in-slot label rendered white-on-light over the unfilled track and was unreachable/unreadable at low percentages. Document-level regressions verify the label exists and carries the percentage at 0/25/50/100%, is not inside `.v-progress-linear`, and stays stable across updates.

Not exercised live: provider rejection, transport failure, delayed completion and close/reopen ownership run through D6's existing socket-lifecycle coverage; the new consumer tests stop at the provider boundary by design (no network, synthetic data only). No live imports were run against any real data.

## Gates (actual exit codes, final head `eac48d4f` unless noted)

| Gate | Result | Exit |
|---|---|---|
| `npx vitest run --no-file-parallelism` (serialized; canvas-heavy chart specs time out under full worker parallelism on this machine) | 104 files / **1043 passed** | 0 |
| `npm run type-check` / `:reliability` / `:charts` | clean | 0 / 0 / 0 |
| `npm run lint` | baseline clean, no new diagnostics | 0 |
| `npm run api:types:check` | match | 0 |
| `npm run build` | ok | 0 |
| `node tests/browser/run-smoke.mjs --case dates` (typed commit, reconciliation, calendar-picker path) | PASS desktop /open-positions + mounted date flow, `fixtureMismatches: []` | 0 |
| backend `uv run python -m pytest` (test settings, full suite) | **1398 passed / 10 skipped**, coverage 83.53% | 0 |

Recorded flake: one earlier full-unit attempt lost a single canvas-heavy chart spec to a 20s worker timeout under load (`remainingChartIntegration.spec.ts`, 28s); the file passes solo (16/16) and the serialized rerun is the recorded green run above. One earlier run lost `allocation.spec.ts` to the same worker-pool timeout; same resolution. The dates browser case failed deterministically mid-round while the intermediate-commit defect was live (2025-01-03 instead of 2025-12-31, three runs identical) — that failure was the defect, not the harness.

## Boundaries

Phase B–D not started. Chart.js retained. C5b implementation and removal not started; the owner's acceptance of the release-validation cycle remains the gate. No merge, deploy, production mutation, or real data committed (all real-data reproduction used the disposable copy; no real values, screenshots or tokens committed).
