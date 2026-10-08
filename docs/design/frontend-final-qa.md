# D8 — integrated default-on frontend QA: acceptance record

Date: 8 October 2026. Scope: task 24/D8 of the [master plan](../superpowers/plans/2026-09-08-frontend-modernization.md), executed on branch `codex/frontend-final-qa-d8` (base `4033ce86`, the tip of `origin/codex/frontend-modernization`: PR #60/C5a merged at `9d369af7` plus the D8 handoff documents). Dedicated worktree `D:\Developing\Portfolio-management-d8`. **Every capture and value below is synthetic fixture data** (`frontend/tests/browser/`); no production account, broker or financial value appears anywhere.

This record audits the integrated **default-on** frontend — the artifact built with all three `VITE_*_ECHARTS_ENABLED` keys genuinely absent, which the C5a-reviewed policy renders as all-modern ECharts with a lazy Chart.js compatibility fallback. The existing run-smoke base matrix (built with explicit all-`false` flags) remains the **rollback** route matrix and was kept separate throughout; nothing in this assignment removes Chart.js, changes backend/financial/API code, merges, deploys or claims C5b release validation.

## Verdict

- **90/90 default-on route probes pass** (18 routes × 5 viewports) on the unflagged artifact, plus **12/12 long-name probes**, **30/30 workflow executions** across seven isolated families, **3/3 rollback spot checks**, and a default-on delivery remeasure within budget.
- **Zero application-code defects were found.** Every defect D8 uncovered was harness-side (recorded in [Harness findings](#harness-findings)); no source file under `frontend/src/` was touched by this assignment.
- Gate results: see [Gates](#gates) — recorded as actual process exit codes on the committed head.
- **Not claimed:** a live release-validation cycle, C5b removal approval, screen-reader/AT certification (out of scope per the owner amendment), main merge or deployment.

## Task 0 — the audited artifact

| Fact | Value |
|---|---|
| Base SHA | `4033ce86` (clean worktree, `git status` empty) |
| Runtime | Node v24.20.0 (engines `>=24.20.0 <25`), npm 11.19.0, agent-browser 0.36.0 (bundled headless Chromium), Windows x64 |
| Dependencies | installed from the committed `uv.lock` / package lockfiles; no lockfile changes in this branch |
| Default-on artifact | `frontend/tests/browser/artifacts/app-d8-default-on` — built with the three flag keys **deleted** from the build environment and no flag defined in any `.env*` file (scan asserted; recorded in `final-qa-d8-artifacts.json`) |
| Rollback artifact | `tests/browser/artifacts/app-d8-rollback` — all three keys explicitly `false` |
| Artifact hashes | sha256 over every file, in the committed [`final-qa-d8-artifacts.json`](assets/frontend-final-qa/final-qa-d8-artifacts.json) |
| Env-file scan | `.env.development` / `.env.example` define only `VITE_API_URL`; zero release-flag keys (assertion in the case + a unit regression) |

**Route inventory and exclusions.** The router (`frontend/src/router/index.js`) registers exactly the 18 routes the fixture inventory covers: `/login`, `/register`, `/dashboard`, `/open-positions`, `/closed-positions`, `/transactions`, `/profile` (+ `edit`, `settings`), `/database` (+ `brokers|accounts|prices|securities|fx`), `/database/securities/:id`, `/summary`, and `/` → `/dashboard`. `/debug-auth` is registered inside a DEV-only guard and does not exist in the production-like build — the exclusion is source-pinned, so no live navigation probe is possible or meaningful (carried over from the D5 record). `/database/securities/:id` is audited through id 1 (stock), 2 (bond) and 3 (crypto).

**Matrix definition.** Viewports: 1440×1000, 1024×768, 390×844, 768×1024 (tablet-portrait, the broker-manager flows' own target) and the CSS zoom-200 viewport. Each route is probed for: correct path (including the `/` → `/dashboard` redirect), mounted app, rendered text, CSS zoom fidelity, single-workspace-heading ownership, app-bar/content geometry (`assertLayoutGeometry` — no header-content overlap, no header control overflow, no raw `[object Object]` label anywhere), zero page errors and no unresolved UI registration. Result lines are prefixed `D8-DEFAULT-ON` / `D8-ROLLBACK`; the rollback spot matrix labels itself and the full rollback matrix remains the standard un-flagged `test:browser` run.

## Default-on route ledger

Every route × every viewport passed (90 probes); the table summarizes per route. "States" lists what the route family received across the whole case; justified N/A entries are inline.

| Route | Fixture/account | Viewports | States exercised | Keyboard/focus & containment evidence | Screenshots | Result | Remaining issue |
|---|---|---|---|---|---|---|---|
| `/` → `/dashboard` | fixture-user, all-accounts context | all 5 | redirect + full populated dashboard | geometry probe per load | `d8-dashboard-desktop.png` | pass | — |
| `/login`, `/register` | public session | all 5 | forms; error state via d5 machine (401 invalid credentials stays readable on-page) | one primary submit; autocomplete attributes pinned by D5 unit specs | `d8-dashboard-mobile.png` (nav), login covered by D5 captures | pass | — |
| `/dashboard` | NAV v2 + breakdown v2 + summary | all 5; native 200%; mobile tooltip | populated; signed/ineligible; malformed-v2 error; legacy-only notice; parked/compatible/incompatible refresh | legend/zoom/tab hit-tests at 390px with fixed-header clearance; native-zoom containment | `d8-dashboard-desktop.png`, `d8-nav-modern.png`, `d8-dashboard-tablet.png`, `d8-dashboard-tablet-portrait.png`, `d8-dashboard-mobile.png`, `d8-native-zoom.png`, `d8-nav-mobile-tooltip.png` | pass | — |
| `/open-positions`, `/closed-positions` | dense 12-row/5-row datasets, 3 currencies, zero/negative/N-R values | all 5 | populated; D4 presets/views; server-owned order | D4 viewport checks (bounds + elementFromPoint per control) at desktop and 390px | `d8-open-positions-desktop.png`, `d8-closed-positions-desktop.png` | pass | — |
| `/transactions` | D4 transactions + D6 import flows + WS loopback | all 5 + mobile flows | create/rejected-save/delete, delayed details, import analyze→confirm→complete, stop/ack, duplicate-submit prevention | dialogs focus entry/return (dialogs family); D4 row-action hit-tests | `d8-transactions-desktop.png`, `d8-transactions-mobile.png`, `d8-transactions-css-zoom200.png` | pass | — |
| `/profile`, `/profile/edit`, `/profile/settings` | fixture settings + choices; unavailable saved account 42 scenario | all 5 + mobile flows | unavailable-selection honesty; guarded saves; rejected profile/context writes; group/broker sections | labelled fields, Save disabled while unresolved (asserted), native-zoom hittability | `d8-profile-settings-desktop.png` | pass | — |
| `/database` landing | static nav | all 5 | populated only (no fetch) — others N/A | nav reachable | — | pass | — |
| `/database/brokers`, `/database/accounts`, `/database/securities` | D5 fixtures incl. genuine server-side search | all 5 + D7 flows | populated; empty; error/retry; filtered-empty (real server filtering) | named row actions; primary/secondary actions hittable at 390px (`assertMobilePageControlsFlow`) | `d8-brokers-desktop.png`, `d8-accounts-longname-desktop.png`, `d8-securities` covered by detail capture | pass | — |
| `/database/prices`, `/database/fx` | D5 fixtures (pivot, missing cell) | all 5 | populated; empty; error; filtered-empty (pair-code search) | pivot cells as buttons; toolbar rows-per-page through the pagination owner | `d8-fx-mobile.png` | pass | — |
| `/database/securities/1..3` | D7 detail envelopes + C4 v2 histories | all 5; native zoom; zoom-switch; fallback | stock/bond/crypto; renderer failure → retry → user fallback; duplicate-date/carry-forward events | `elementFromPoint` on charts region at 200% | `d8-security-detail-desktop.png`, `d8-security-stock.png`, `d8-security-bond.png`, `d8-security-crypto.png`, `d8-rollback-security.png` | pass | — |
| `/summary` | summary v2 + breakdown; d5 state machine | all 5 | populated; empty (both empty states + disabled controls); error; comparison/history views via D5 family flow | labelled period control; YTD/All-time bands | `d8-summary-desktop.png`, `d8-summary-empty.png` | pass | — |
| long-name variant | `longAccount` fixture (long display name selected) | desktop + mobile | 6 dense routes re-probed with the long committed label | geometry per load | `d8-open-positions-longname-desktop.png`, `d8-transactions-longname-desktop.png`, `d8-transactions-longname-mobile.png`, `d8-summary-longname-desktop.png`, `d8-accounts-longname-desktop.png` | pass (12/12) | chartful routes deliberately excluded from this pass: the long-account fixture's committed selection mismatches the C2/C4 chart envelopes' all-selection context by fixture design, which legacy-fallbacks charts for fixture reasons — captured in the default-on pass instead |

## Integrated workflow acceptance (per family, on the default-on artifact)

Each family ran against a **pristine fixture server on the same fixed port** with only its own mode enabled — reproducing exactly the conditions its focused case was proven under (see [Harness findings](#harness-findings) for why this isolation is load-bearing). Sessions are fresh per viewport as in the focused cases.

| Family | Flows verified (all pass) |
|---|---|
| d4 tables/transactions | grouped views/presets, server-owned order, hidden-sort + Clear, sticky identity + measured offset, chooser stay-open/Done, rejected-then-successful save/delete with exact-identity confirmation, delayed/failing detail, FX endpoint, session-change guards; viewport hit-tests at 1440/1024/768/390 |
| d7 brokers/security | broker CRUD + deletion confirmations, token save/auto-test/revoke with exact recorded payloads (fake credentials only; artifacts and messages inspected for secret leakage — none), reactivation/delete-retry, bond/crypto detail resources, native-200% region probe; desktop + mobile sessions |
| d6 imports | analyze → mapping/create-security → confirmation → complete over the loopback WebSocket, stop-pending/ack, warning/recoverable row errors, uncertain terminal error, stale-event containment on the idle-connected socket, no stale completion or auto-restart after close/unmount/reopen, `date_to` wire parity; desktop + mobile |
| settings account | unavailable saved identity (exact visible label + input value + persistent message), zero-write unresolved submissions, delayed load, keyboard/explicit resolution, exact two-stage save payloads, rejected profile/context writes with retained edits, mobile pass |
| dialogs | all ten dialog surfaces: visible section headings, named Cancel, focus entry on open and return on close, error rendering — desktop + mobile |
| charts | both IRR controls with independent toggles (zero requests), exact comma-grouped value table with full-NAV totals column and inception horizon, keyboard row inspection, zoom bounds retained across a compatible refresh (exactly one request) and reset across an incompatible one, parked-response honesty, signed/ineligible allocation state with immutable `$100.00` denominator, malformed-v2 single-request error without downgrade, genuine legacy-only notice, renderer failure → failed retry → user fallback, zoom-then-security-switch with no cross-context tooltip leakage, mobile containment + real pointer tooltip capture, native 200% zoom (CDP, DPR-verified 2 → 1) with hittable controls clear of the taller app bar |
| rendered states | summary empty (both empty states, disabled controls), brokers empty + error + genuine filtered-empty — default-on captures (`d8-summary-empty.png`, `d8-brokers-error.png`, `d8-brokers-filtered-empty.png`) |

**Rollback matrix (separate).** On the all-`false` artifact: the dashboard renders the incumbent Chart.js NAV + three horizontal allocation bars with **no ECharts module in the loaded graph** and Chart.js present; the security page renders legacy canvases with no modern tables; `/transactions` route probe passes (`D8-ROLLBACK` labels; captures `d8-rollback-dashboard.png`, `d8-rollback-security.png`). The full rollback route matrix is the standard `test:browser` run (all-false base artifact), executed in the gate list below; per-family rollback artifacts (NAV-only/all-on/no-flags/all-off rendered independence) remain covered by the `charts-c5` case, also in the gate list.

## Delivery (default-on artifact, cold graphs)

Gzip JS+CSS over the observed per-route cold resource graph (fonts excluded — system stack, zero font assets; loopback timings are not production latency). Target: the saved C5a cutover budget (~535 kB) for the modern dashboard.

| Route | gzip bytes |
|---|---|
| /dashboard (all-modern) | **483,952** (within 535,000) |
| /login | 236,759 |
| /profile | 236,672 |
| /transactions | 271,334 |
| /database/securities/1 | 463,234 |

login/profile/transactions load **no Chart.js and no ECharts runtime module** (asserted); no unopened dialog modules, no debug modules, no icon-font download. Full JSON: [`final-qa-d8-delivery.json`](assets/frontend-final-qa/final-qa-d8-delivery.json).

<a id="harness-findings"></a>
## Harness findings (all fixed in the harness; zero app-code defects)

1. **VITE_API_URL must be baked from a live fixture origin** — the first case build had no fixture server up, so `axios.create({ baseURL: undefined })` sent API calls to the static app server, whose SPA fallback answers API paths with index.html. The case now builds both artifacts inside the run with the live origin (regression-pinned for env restoration including a build-failure path).
2. **Fixture modes were mutually exclusive by construction.** The d4 branch intercepts the settings payloads (shadowing the settings-account flow); the settings fixtures pin a non-all committed selection that mismatches the C2/C4 chart envelopes (legacy fallback for fixture reasons); the import flow appends brokers that shifted the D7 token form's ids. The `longAccount` variant likewise mismatches chart contexts. Resolution: `startFixtureServer` gained a `port` option and the case gives each family a **pristine server on the same fixed port**, reproducing each focused case's proven conditions exactly.
3. **Dangling native-zoom/tooltip state and viewport leakage** across flows on one session (the d7 flow switches viewports internally) — resolved with fresh sessions per viewport and per-family server swaps, mirroring the focused cases.
4. **agent-browser daemon wedges**: a CLI command can hang indefinitely (execFile's 30 s timeout kills the node wrapper but the orphaned CLI binary holds the stdio pipes). `protocol.mjs` now races a 45 s watchdog so a wedge becomes an attributable failure; `runWorkflow` retries once, transparently, on documented transient signatures only.
5. **Unclosable servers**: a page-held WebSocket (un-upgraded upgrade request) stalled `server.close()` forever (Node exit 13). Both harness servers now `closeAllConnections()`; the case carries an activity-based stall watchdog that forces an attributable exit.

## Gates

Recorded from the gate runner (`frontend/temp_files/d8-gates/`, uncommitted) as actual process exit codes on committed head `1a8a8b72` (the implementation commit; the docs-only commits after it change no code). Portable Node v24.20.0; backend via uv with test settings.

| Gate (command) | Result | Exit |
|---|---|---|
| `npm run test:unit` | **1008/1008 passed** (99 files) on an idle machine in 30 s. Two earlier attempts each failed 4 canvas-heavy chart-spec tests with 20 s timeouts after 23-minute suite durations — the machine was still draining prior gate load; different chart-spec files failed each time and both specs pass in every focused run. Recorded as environment load flakes, not test defects. | 0 |
| `npm run type-check` | clean | 0 |
| `npm run type-check:reliability` | clean | 0 |
| `npm run type-check:charts` | clean | 0 |
| `npm run api:types:check` | match | 0 |
| `npm run lint` | 0 errors / 8 baseline warnings (baseline unchanged). Five new diagnostics in the new harness files (unused re-exports/imports, two empty catch guards) fixed and committed. | 0 |
| `npm run build` | ok | 0 |
| backend `uv run python -m pytest` (test settings) | **1386 passed / 10 skipped**, coverage gate intact | 0 |
| `npm run test:browser` (full rollback matrix, all-false base artifact) | 18 routes × 4 viewports, 735 fixture requests, **zero mismatches/route failures** | 0 |
| **default-on matrix**: `node tests/browser/run-smoke.mjs --case final-qa-d8` | 90 route probes + 12 long-name probes + 30 workflow executions + 3 rollback spot checks, **zero failures**; dashboard 483,964 gzip bytes (target ≤ 535,000); committed head `3521a5e8` | 0 |
| `npm run test:delivery` | within budget (rollback 401 kB budget asserted on the base artifact) | 0 |
| focused: `charts-c2`, `charts-c3`, `charts-c4`, `charts-c5`, `brokers-security-d7`, `imports-d6`, `layout`, `context`, `dates`, `requests`, `recovery`, `dialogs`, `dialog-recovery`, `d4`, `d5`, `settings-account` | all exit 0 (13–53 min each under gate-sequence machine load) | 0 |

Honesty notes: the first gate-sequence attempt ran the npm gates through a spawn invocation that cannot launch `.cmd` shims on Windows (instant null exits) — rerun through the corrected runner; the first committed-head rerun of `final-qa-d8` hit the summary-scoping ReferenceError at the very end of an otherwise green run (fixed in `3521a5e8`, then rerun green — that rerun is the recorded default-on result). The machine was under sustained load for the whole sequence: focused-case durations ran 2–4× their solo times, which is also what produced the unit-suite load flakes above.

## Boundaries, and what this record does NOT claim

- **C5b is not approved by this work.** Chart.js is retained as the lazy compatibility fallback; removal still requires an owner-accepted release validation cycle and separate removal approval. This local synthetic QA is explicitly **not** that cycle.
- **Screen-reader/AT work remains out of scope** per the owner's 5 October amendment: the keyboard/focus/labels/contrast checks above are DOM-level and are not an AT audit.
- No backend/financial/API change, no dependency removal, no new features, no dark mode/localization/exports, no merge or deployment, no release tag. Light theme only.
- Modernization is **not** labeled complete; the main branch has not received `codex/frontend-modernization`.

## Owner review checklist (specific captures and workflows)

1. Default-on dashboard at desktop and 390 px: three solid pies + ECharts NAV pilot with both IRR controls (`d8-dashboard-desktop.png`, `d8-dashboard-mobile.png`), exact-value table with statuses (`d8-nav-modern.png`).
2. The ineligible/signed allocation state keeps the certified reason and immutable `$100.00` denominator (`d8-allocation-ineligible.png`).
3. Security histories: stock/bond/crypto exact tables, percent-of-nominal bond displays, carry-forward annotation, tooltip without cross-security leakage (`d8-security-stock.png`, `d8-security-bond.png`, `d8-security-crypto.png`).
4. Native 200% zoom on the default-on dashboard (DPR-verified) and the mobile tooltip containment (`d8-native-zoom.png`, `d8-nav-mobile-tooltip.png`).
5. Rollback remains visually distinct (`d8-rollback-dashboard.png`, `d8-rollback-security.png`).
6. Try the flows yourself: `cd frontend && node tests/browser/run-smoke.mjs --case final-qa-d8` (command recorded; builds both artifacts and replays the full labeled matrix).
