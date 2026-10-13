# Real-data validation corrections — phase B evidence ledger (presentation)

Date: 12 October 2026 (review round 1 incorporated 13 October). Branch `codex/release-validation-presentation-b` (dedicated worktree `D:\Developing\Portfolio-management-relval-pres-b`), base `20cc3c81` (`origin/codex/frontend-modernization`: PR #62/phase A merged). Scope: **phase B Tasks 4–5 implemented** (navigation/header geometry; shared tables and responsive actions) **including the full review round**. Phase A's functional fixes are preserved untouched — the context/date ownership, year options, zero-versus-absent handling and import lifecycle guards all keep their regressions green (full unit suite and the `dates`/`context`/`imports-d6`/`imports-prices` browser cases pass on this branch). No backend file touched; no financial calculation, string or precision changed.

Commits: `8d569dcc` (Tasks 4–5), `bd740078` (ledger/tracker/captures), `d0b78bec` (review round). Gates on the committed review head are in [Gates](#gates-actual-exit-codes).

## Task 4 — navigation and header geometry

### Compact expanding navigation rail (`Navigation.vue`)

- **Compact desktop rail**: `mdAndUp` renders the drawer as a permanent 72px rail (`rail-width="72"`, `expand-on-hover`). Collapsed, it shows icons only; every route keeps its label as the accessible name (`aria-label` + `aria-current="page"` for the active route) and a ≥44px hit area.
- **Expands on pointer hover and keyboard focus; collapses after both leave**: pointer expansion is Vuetify's `expand-on-hover`; keyboard focus drives the SAME public mouseenter/mouseleave contract by dispatching synthetic hover events on the drawer root (`dispatchHover`), so the two input paths share one expansion state. Pointer-leave while focus is inside re-arms expansion; collapse happens only when both are gone. Expansion OVERLAYS the page — Vuetify keeps the registered layout size at the rail width, so `v-main` never reflows and charts never resize on hover (asserted: `main.left` stays 0 while expanded).
- **Stable structure**: the section subheaders (Portfolio/Positions/Data/Personal) and dividers render in BOTH states and compress to CSS separators while collapsed (font-size 0, 10px tall). The first implementation removed them from the DOM while collapsed; the rendered layout flow caught the consequence — the accessibility tree changed between snapshot and click and the harness's positional refs clicked the neighbouring item (Overview resolved to Performance). Conditional rendering would be the same trap for assistive tech; the committed version keeps the tree identical in both states (pinned by `Navigation.spec.ts` + the browser case's subheader-height probes in both states).
- **Explicit touch/mobile toggle**: below `mdAndUp` the hamburger trigger opens the temporary full-labelled drawer with section grouping; route selection closes it and restores focus to the trigger (existing behavior, still pinned).
- Regressions: `tests/unit/workspace/Navigation.spec.ts` (RED-first: 2 of 3 failed against the incumbent full drawer — rail semantics, expand/collapse state machine, mobile toggle); rendered acceptance in `tests/browser/presentation-b.mjs` (real CDP pointer hover, focusin/focusout, both-leave semantics, overlay assertion, hit-area heights, active-route label, mobile open/close/focus-restore) with captures `rail-expanded-hover.png` / `rail-collapsed-desktop.png`.

### Header geometry (`App.vue`, `WorkspaceContextStrip.vue`, `AccountSelection.vue`)

- **Duplicated context summary removed**: the strip's text line (account label · valuation date · reporting currency) repeated exactly what the account/date/currency controls display. The strip now renders only the controls slot, the Display preferences action (min 44px, disabled until ready) and the pending (`role=status`, "Updating to …") and error (`role=alert`) feedback. RED-first: `WorkspaceContextStrip.spec.ts` asserts the duplication is gone (`Valuation date:`/`Reporting currency:` text absent, no `data-testid="committed-account"` span) while feedback/preferences behavior stays pinned. The `layout`/`context`/`dates` browser cases (committed values, pending labels, safe fallbacks) pass unchanged — the controls remain the truthful single display.
- **Unused toolbar space removed**: the `.app-bar-title` row rendered an empty line on every non-summary page and a `v-divider` ran under the strip; both are gone. The `v-app-bar` itself now renders only when it has content (context pages, or /summary's settings dialog) — on desktop the profile/database routes have no header region at all. On mobile the bar remains as the fixed navigation trigger's reserved zone (`app-bar-content--bare`, 64px) so the registered height equals real content (the route probe's header-vs-content assertion would otherwise flag the empty bar — it did during development, and reserving the trigger zone is the honest fix, not loosening the probe).
- **`assertLayoutGeometry` bare-shell mode** (harness): the shared route probe now accepts a bar-less page ONLY when the context strip is absent (a missing bar beside the strip stays a defect); bare pages still assert scroll-zero, content presence and no `[object Object]`.
- **Equal control heights + unclipped labels**: account select, valuation date and reporting currency all sit on the same 56px row (comfortable density + explicit field min-height; the stale 44px mobile override removed — min-height does not accumulate, the later rule silently won at 390px and the browser case caught it). `AccountSelection` lost its flat `v-card` wrapper, which clipped the floated "Account or Account group" label in half (`overflow: hidden` on the card cut the label that rises above the field box); long committed values render single-line with ellipsis (`account-select__label` + `title`) so the field never grows taller than its siblings. RED-first structural pin: `AccountSelection.label.spec.js` (no `.v-card` wrapper; ellipsis label element). Rendered: the presentation-b case hit-tests the floated label center and asserts geometry.
- **Arrow borders**: pixel-decoded the arrow buttons at DPR 1 and DPR 2 on the base — all four edges present (the "light" columns were only the rounded corners); no border defect reproduced on this base. The label clipping and height mismatch were the real, fixed defects; recorded honestly rather than "fixed" blind.
- **Short Profile / scrolling**: at 1440×1000, 1280×600 and a forced 1280×430 the Profile page does not scroll artificially (`scrollHeight <= innerHeight`, asserted in presentation-b); long pages still scroll (full matrix exercises them). The base already had no artificial overflow; the assertion keeps it that way.
- **Hit-testing**: every header control is hit-tested after hover, keyboard entry, mobile and (via the d5 native-zoom flow) native 200% zoom; tooltips are covered by the `charts-c3` case, whose placement probes measure the fixed header live — the resized (shorter) header passed clean.

## Task 5 — shared tables and responsive actions

### Shared table rules (`assets/workspace.css`)

- One rule set under `.workspace-ui` covers Vuetify `v-table`/`v-data-table` (v-data-table renders an inner v-table) and the plain `.workspace-table`: visible neutral row separators (`1px solid rgb(var(--v-theme-border))`, replacing the effectively invisible `rgba(border, 0.12)` default), a black header-bottom rule (`2px solid rgb(var(--v-theme-text-primary))` — the light theme's ink) on the LAST header row with the light rule between grouped-header tiers, and clear totals rules (2px ink top on every tfoot row, 2px ink bottom on the last; body-row totals via `tr.total-row`). Fixed-header tables zero their header border with `!important` and draw an inset shadow instead — the shared rule restyles that shadow (`inset 0 -2px 0 ink`) so sticky headers stay correct; Vuetify-specific selector shapes are mirrored so nothing needs `!important`.
- Applied everywhere through the existing `.workspace-ui` scope (WorkspacePage/PositionsPageBase/TransactionsPage roots): historical reconciliation, both position tables (Open/Closed), transactions (two-tier header), Data tables (Brokers/Accounts/Securities), prices/FX, security metadata and transaction history. SummaryPage's own 12%-opacity borders were removed in favour of the shared rules (its zebra/group/subtotal backgrounds and the account-performance column bands stay).
- Untouched by design: cell text, exact financial strings, numeric alignment, tabular digits, grouped-header associations, sticky/pinned columns (`position: sticky` re-asserted), horizontal scrolling (asserted at 390px), and the C4 exact chart tables (already full-contrast; not in the plan's page list).

### Security links and italic share cells

- `SecurityLink.vue`: `.security-link` — restrained primary color, no underline at rest, underline on hover and `:focus-visible`; router-link semantics and the shared focus outline unchanged. Verified in presentation-b with a real CDP hover (underline computed) and keyboard focus.
- `AllocationDataTable.vue`: the Share column (header, body cells, total share) renders italic (`allocation-table__share`); display strings, statuses and precision untouched. The legacy dashboard table's "%" header was already italic — consistent family look.

### Responsive transaction actions (`WorkspaceActions.vue`, `fitActions.ts`)

- The candidate actions (secondary first, then overflow, in order) render directly whenever the measured row width permits; a ResizeObserver-driven fit loop measures every rendered control (including the "More actions" activator, always measured during the fit pass) and keeps the largest ordered prefix that fits, moving the suffix into the menu. One instance per action (prefix/suffix slice), exact unchanged action ids and handlers, primary always direct; when the focused action collapses into the menu, focus moves to the activator. Without real layout (unit jsdom, `clientWidth` 0) nothing is hidden — the incumbent presentation.
- `fitVisibleActions` is a pure function, unit-tested RED-first (`fitActions.spec.ts`) for prefix fitting, menu reservation, ordering and degenerate widths; the component spec now pins the no-layout all-direct contract (the old spec pinned the always-menu behavior this task supersedes).
- Rendered acceptance: presentation-b asserts all five transaction actions direct at desktop (menu absent), the exact menu item order behind the activator at 390px, no row overflow at either width, and the desktop→390→desktop transition round-trip; capture `transactions-desktop-actions.png` / `transactions-390-menu.png`.
- Harness updates for the measured tiers (each preserving the original assertions' intent): `d4` transactions flow asserts the wide-row direct hierarchy; `d5` prices probes accept either tier (direct button, or the hittable overflow activator that hosts it at 390px); `dialogs` and `imports-d6` try the direct button first, then open the overflow menu — both paths reach the same dialog.

### Security transaction-history pagination (verify-first)

- D7's implementation is intact and verified — no second paginator added. Existing coverage (distinct per-page fixtures, exactly-one request per page change, RENDERED rows switching, page reset on period filter, mobile footer probes) was extended in `brokers-security-d7.mjs` with the plan's remaining bullets: the request `itemsPerPage` reaches the wire (10 initial → 25 after the change), a page-size change resets to page 1, exactly one refetch per change, and the "Showing X-Y of Z" range label agrees with the page size (clamped to the 23-row fixture total at 25/page). Case passes at desktop/tablet/mobile.

## Deliberately superseded prior pins (behavior the owner requested)

- `WorkspaceActions.spec.ts`: "overflow actions behind a labelled menu" → all-candidates-direct at unmeasured width + menu contract covered rendered (underlying reachability/id assertions retained).
- `d4.mjs` transactions overflow assertions → wide-row direct hierarchy (menu behavior retained in presentation-b).
- `dialogs.mjs` static overflow classification → measured tiers (direct-first, menu fallback).
- `Navigation.spec.ts` desktop full-drawer assertions → compact rail semantics.
- `d5.mjs` breakdown-year pick: the probe re-picked the already-selected year and relied on the OLD integer wire (string '2026' vs number 2026) to coerce a "change"; on the phase A string wire a same-value pick correctly fires no request. The probe now picks the genuinely different 2025 (pre-existing failure on the pristine base `20cc3c81`, reproduced there before fixing — phase A never ran the d5 case).

## Review round 1 (draft PR #63) — all four findings corrected RED-first (`d0b78bec`)

1. **WorkspaceActions focus preservation.** The focused action's identity is captured BEFORE any tier change (menu items live in a teleported overlay, so containment alone is not enough — a candidate id that belongs to this component counts as inside; once a button unmounts, `activeElement` is already lost to `<body>`). After the fit lands, focus returns to the same action where it still exists (either tier), otherwise to the More actions activator, otherwise — when widening removed the activator entirely — to the last direct action. Rendered regressions in `presentation-b`: desktop→narrow restores focus to the activator and never drops to `<body>`; narrow→desktop WHILE THE MENU IS OPEN with a menu item focused lands focus on that exact action, now direct; a resize whose fit keeps the focused action direct does not steal it. Unit regressions: `WorkspaceActions.fit.spec.ts` (activator follows the disappeared slot; no steal when the action survives).
2. **Residual-overflow convergence.** The old loop restored all candidates and recomputed the same estimate each iteration — it never shed an action. The verification pass now reduces the RETAINED count by one per correction and re-checks the real row, bounded by the candidate count. A usable layout when even the primary action and the activator cannot share one line is now DEFINED: the row wraps (both controls stay visible; measured from the real `fixedWidth + gap + menuWidth > availableWidth`), and the wrap survives later refits whose "no overflow" is achieved BY the wrap (the degenerate flag is computed per fit and guards the reset). Regressions: an over-estimate leaving genuine overflow converges to the truly fitting count (estimate says 4, real row fits 2 → 2); the degenerate case wraps and releases; rendered probes at 260px assert wrap + visibility + no horizontal overflow + release on widen.
3. **Unmount-safe asynchronous fitting.** Every fit takes a generation token and re-checks ownership (`disposed`, token, element availability) after EVERY await; unmount invalidates immediately, so a stale continuation stops at the next check and cannot touch a replacement instance. A width change observed while a fit is running queues a refit that runs when the active one finishes (not swallowed, not interleaved). Two further root causes surfaced and were fixed while driving these regressions:
   - **rAF does not fire in occluded windows** — the fit path was rAF-based (`nextFrame` + rAF-coalesced scheduling), so a backgrounded/occluded tab stalled mid-measurement with the candidates unmounted and the menu closed until a frame happened to be produced. This was the source of the intermittent `dialogs`/`d5` failures (reproduced live: `requestAnimationFrame` counter static at 0 with the page `visible` but the window occluded). The fit is now entirely microtask-based (Vue `nextTick` flushes the DOM; the width reads force layout synchronously); queueing coalesces on the microtask queue.
   - **The fit's own measuring toggle fed the ResizeObserver** (the activator joins the row for the measure pass, jittering the strip box) — honoring those self-induced events refit forever. The observer now filters same-width events (<1px), and a resize arriving while the USER'S overflow menu is open closes the menu via its model (a refit would reshuffle its items mid-interaction; programmatic model changes emit no `update:model-value`, so the fit is chained on `nextTick`) and runs right after. Regressions: unmount during measurement (no unhandled rejection, replacement untouched, replacement fits normally), mid-fit resize at a new width triggers the refit (mount fit + both events = three estimator calls), plus the previously green convergence/wrap/focus cases.
   - Measuring passes now stage the candidates with `aria-hidden` on the row (layout boxes kept for their widths, excluded from the accessibility tree), so a snapshot can never catch a candidate that is about to move tiers; the `dialogs` click helper retries a tier move like it already retries a covered click.
4. **Bare-shell allowance restricted.** `assertLayoutGeometry` takes an explicit `allowBareShell` (only `/profile*` and `/database*` routes pass it, only honored at ≥960px); anything else missing both header and context strip FAILS. Negative regression `assertBareShellGuard` (in the `layout` case, every viewport): removes the dashboard's `.v-app-bar` AND `.workspace-context` from the DOM and requires the probe to fail citing the restriction.

The four finding regressions were observed RED against the pre-fix component (6/6 failing) before implementation.

## Not reproduced (recorded honestly)

- Arrow-border defect: not reproducible at DPR 1/2 on this base (pixel-decoded both scales — complete borders, rounded corners only); the adjacent label-clip and height defects were real and fixed.

## Gates (actual exit codes)

Implementation head `8d569dcc` (round 1, historical):

| Gate | Result | Exit |
|---|---|---|
| `npx vitest run --no-file-parallelism` | 108 files / **1081 passed** | 0 |
| `npm run type-check` / `:reliability` / `:charts` | clean | 0 / 0 / 0 |
| `npm run api:types:check` | match | 0 |
| `npm run lint` | 0 errors / 8 baseline warnings | 0 |
| `npm run build` | ok | 0 |
| FULL browser route matrix (18 routes × 4 viewports, zero mismatches) | `routeFailures: []` | 0 |
| focused browser `presentation-b` (desktop + mobile) | PASS (first run hit the recorded agent-browser transient — mobile probe body empty after a 10 s awaited readiness; clean rerun 0) | 0 |
| focused `layout` / `context` / `dates` / `requests` / `recovery` / `dialogs` / `dialog-recovery` / `d4` / `d5` / `settings-account` / `imports-d6` / `imports-prices` / `brokers-security-d7` / `charts-c2` / `charts-c3` / `charts-c4` / `charts-c5` / `delivery` | all PASS (`charts-c5` needed one clean rerun — the recorded daemon-transient class; the nav-only candidate renders identically when built and inspected standalone) | 0 |
| browser `final-qa-d8` (unflagged default-on acceptance, committed head) | **PASS — 90 route probes + 12 long-name + 37 workflows + 3 rollback spot-checks, 0 failures**; delivery remeasured dashboard 485,118 gzip < 535,000 target | 0 |
| browser `delivery` | PASS | 0 |
| backend `uv run python -m pytest` (test settings) | **1399 passed / 10 skipped**, coverage 83.57% | 0 |

Review head `d0b78bec` (round 1 corrections):

| Gate | Result | Exit |
|---|---|---|
| `npx vitest run --no-file-parallelism` | 109 files / **1087 passed** | 0 |
| `npm run type-check` / `:reliability` / `:charts` | clean | 0 / 0 / 0 |
| `npm run api:types:check` | match | 0 |
| `npm run lint` | 0 errors / 8 baseline warnings | 0 |
| `npm run build` | ok | 0 |
| FULL browser route matrix (18 routes × 4 viewports, zero mismatches) | `routeFailures: []`, `fixtureMismatches: []` | 0 |
| ALL 18 focused browser cases (incl. the extended `presentation-b` and the new bare-shell guard in `layout`) | **all PASS sequentially, no reruns needed** (the rAF fix removed the stall class that previously forced clean reruns of `dialogs`/`d5`/`charts-c5`) | 0 |
| browser `final-qa-d8` (unflagged default-on acceptance, committed head) | first attempt died on the recorded agent-browser daemon ECONNRESET mid-flow (harness process crash, not an assertion); clean rerun **PASS — 90 route probes + 12 long-name + 37 workflows + 3 rollback spot-checks, 0 failures**; dashboard 485,131 gzip < 535,000 target | 0 |
| browser `delivery` | PASS | 0 |
| backend `uv run python -m pytest` (test settings) | **1399 passed / 10 skipped**, coverage 83.57% | 0 |

Captures (inspected, synthetic fixtures only): `docs/design/assets/presentation-b/` — `rail-expanded-hover.png`, `rail-collapsed-desktop.png`, `positions-desktop-rules.png`, `transactions-desktop-actions.png`, `transactions-390-menu.png`, `transactions-390-mobile.png` (retaken on the review head; `transactions-390-menu.png` now shows the menu open with an item focused across the desktop-restore transition).

## Boundaries

Phase C (charts presentation), phase D (dashboard summary choice) and C5b (Chart.js removal) not started. Chart.js retained with all flags. No main merge, no deployment, no backend change, no real data committed (all evidence is synthetic-fixture based).
