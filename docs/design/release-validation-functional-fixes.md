# Real-data validation corrections — phase A evidence ledger

Date: 9 October 2026. Branch `codex/release-validation-functional-fixes` (dedicated worktree `D:\Developing\Portfolio-management-relval-fixes`), base `f32e7d09` (`origin/codex/frontend-modernization`: PR #61/D8 merged plus the correction plan). Scope: **phase A, Tasks 1–2 complete; Task 3 not started in this pass** (status below). The correction plan transcribes the owner's real-data annotations from the C5b release-validation run.

## Task 1 — date selection, historical boundary and inception

### Frontend (commit `1e373dee`)

- **Calendar picker never committed**: the header valuation date committed only on blur/Enter; choosing a date from the calendar picker left the change uncommitted until focus moved. The draft logic moved to `src/composables/useValuationDateDraft.ts` — commits through the existing context-change owner (`requestContextChange`) on `update:model-value` **and** blur/Enter, with commit-once semantics (an already-committed draft is a no-op, so the calendar path followed by blur/Enter never duplicates), an ISO-completeness guard (invalid/incomplete typed drafts never commit), and committed-date restoration on rejection.
- **Request end not clamped to the valuation date**: a persisted custom To (2026-10-09) kept sampling periods after a newly committed historical effective date (2024-06-30). `calculateDateRange` now clamps a custom To later than the effective date (fixing the displayed dashboard range for both consumers), and `DashboardPage.fetchNAVChartData` clamps the request end before building the query.

Regressions (RED first — 2 failed / 12 passed with the fixes stashed, GREEN after): `useValuationDateDraft.spec.ts` (commit-once, invalid/incomplete never commits, unchanged no-op, rejection restores, unreadable no-op), `dateRangeUtils.spec.js` (clamp cases), `DashboardPage.requests.spec.ts` (request end clamped to the committed date with fromDate preserved).

### Backend (commit `0086f32e` — PROTECTED, needs-approval)

- **All-time was broken outright**: `_get_earliest_date_for_accounts` returns a `datetime` (`Min` over the datetime `date` column) which the legacy window compared against `date` objects — `TypeError`, HTTP 500 on every All-time request. The owner's real-data finding reproduced.
- **Requested From before the scope's inception sampled pre-inception periods** (From=2000 → years of empty samples, a zero IRR base, solver-unavailable IRRs).
- **Fix** (`services/charts.py get_nav_chart_data`): the authoritative effective start is the **later of the requested From and the selected scope's canonical inception** (earliest transaction date, normalized to a calendar date). All-time uses the inception. An inception after the effective end falls through to the honest empty outcome (`outcome: 'empty'`). Zero-valued observations **after** inception are retained.

Regressions (observed RED on the unfixed service): requested From 2000 floors to the 2019-06-30 inception (first sampled period ≥ inception; nav/irr_inception/irr_interval series present); All-time starts at the inception; inception after the effective end returns `outcome: 'empty'`; zero retention (first sample `value: "0"`). The C1 completeness test's seeded cash-in moved before its requested window (the floor makes pre-inception *requested* samples impossible by design) and its return known-subtotal updated to `"20000"` with the contribution now inside the first interval.

Isolation: the backend commit is separately labelled for a **needs-approval draft PR** (protected chart/NAV chain per `Steerings/Calculation Conventions.md`); legacy payloads unchanged; no formula changes — only the sampling window start.

## Task 2 — year options, performance and security resource failures

### Year-options wire mismatch (commit `66c9ed9e` + `3e9e87b3`)

Source-confirmed on the base and re-confirmed against the real backend: `get_year_options_api` returns numeric years as `{text, value}` **strings**, a `{divider: true}` separator and the special All-time/`ytd` ranges — while `getYearOptions` demanded an integer array. On real data every year-options fetch threw `Invalid year options response`, so the positions pages surfaced "Unable to load positions or year options" and Summary surfaced its resource-failure banner with an empty year menu (synthetic fixtures fed integers, so focused runs never saw it).

- **Fix**: one explicit typed adapter (`YearOption`) in `services/api/database.ts` with strict per-entry validation; `calendarYearOptions` derives the numeric-year subset for Summary's breakdown selector; PositionsPageBase consumes the server list as authoritative (its All-time/YTD entries map to the timespan labels, calendar years stay numeric, dividers pass through); the selected Summary year defaults into the offered range.
- **Regressions**: `yearOptions.spec.ts` pins the exact real wire (captured from the disposable copy: years, divider, specials), malformed-entry rejection, the Summary filter; PositionsPageBase behavioral coverage (no year-options failure banner, adapted items); the pre-existing integer-wire mapping test and the `apiContracts` year test updated to the authoritative wire; spec mocks across RoutePatterns/DetailRequests updated (the api barrel re-exports the new adapter).

### Account performance failure — diagnosed as absent precomputed data

Probed read-only against the disposable copy: `summary/api/summary_data/` returns **200 with empty contexts** (`years: [], lines: []` for all three groups) for the probed scope/period — the backend confirms the account performance data is absent, not an endpoint/serialization/calculation error. With the year-options adapter in place the year selector works, and Summary renders the honest empty state; no catch-all error mask was added. Owner verification with a data-bearing year remains part of the manual pass.

### Bond partial-load alert — partially diagnosed (not fixed; not a cutover blocker)

Reproduction on the disposable copy (bond with bond metadata): the page shows "Unable to load part of this security" while **all three sub-requests return HTTP 200** and both history envelopes carry `chartV2` with `outcome: 'ready'` (series `price`/`position`), and transactions 200 with a characterized empty list. The rendered page shows one modern exact-values table (display parity verified against its API response) and one legacy fallback canvas — a mixed per-document rendering. The production parser run over the captured real envelopes reported a **context mismatch**: the real envelope context carries the committed broker selection (`{type: 'broker', id: …}`, `accountIds: []`, effective date as configured) — the page-level trigger remains unproven (hypotheses: the account-scoped request parameters or the empty-transactions path interacting with the partial-failure aggregation). Recorded per the plan's rule for unreproduced findings, with the probe evidence preserved locally.

## Task 3 — account-based price import and progress readability

**Not started in this pass** — the session budget went to the Task 1–2 root causes above. Reproduction plan (from the correction plan, unchanged): single/multi-account submissions on a disposable fixture dataset through the loopback conversation, RED tests for account IDs reaching the consumer, provider rejection, transport failure, delayed completion; the progress label contrast treatment verified at 0/25/50/100%, determinate/indeterminate and error states. Note: current code already includes an `accounts` field — do not assume the frontend omits accounts.

## Gates (actual exit codes, committed heads)

| Gate | Result | Exit |
|---|---|---|
| `npm run test:unit` (final: `--no-file-parallelism` — canvas-heavy chart specs time out under full worker parallelism on this machine, a documented environmental pattern; the same files pass solo and in the serialized run) | 102 files / **1031 passed** | 0 |
| `npm run type-check` / `:reliability` / `:charts` | clean | 0 / 0 / 0 |
| `npm run lint` | 0 errors (baseline unchanged) | 0 |
| `npm run api:types:check` | match | 0 |
| `npm run build` | ok | 0 |
| backend `uv run python -m pytest tests/` (test settings, full suite after the inception floor) | **1390 passed / 10 skipped** (+4 inception regressions) | 0 |

Two earlier full-unit attempts failed 3–4 canvas-heavy chart specs each under worker parallelism; both files pass solo and in the serialized recorded run.

## Boundaries

Phase B–D not started. Chart.js retained. C5b implementation and removal not started; the owner's acceptance of the release-validation cycle remains the gate. No merge, deploy, production mutation, or real data committed (all real-data reproduction used the disposable copy; no real values, screenshots or tokens committed).
