# Phase D reconciled dashboard statement — evidence record

Branch: `codex/dashboard-reconciled-statement-d` (worktree
`Portfolio-management-dashboard-d`), based on `origin/codex/frontend-modernization`
at `efca731d`. Design/contract: `docs/design/dashboard-reconciled-statement-d.md`.
Plan: `docs/superpowers/plans/2026-10-15-dashboard-reconciled-statement-d.md`.
Status: **draft, needs-approval** — financial review and design review pending;
no merge authorized.

## Tested commits (all gates on committed code)

| Commit | Content |
|---|---|
| `88f6ff87` | backend read model + opt-in `summary_contract=2` + schema |
| `e42cb1e2` | typed boundary + `PortfolioValueStatement.vue` + wiring |
| `f75f7755` | `dashboard-statement-d` browser case + fixture modes |
| `bbb2ec5a` | browser-case corrections (capture path, request deltas, zoom scroll, tablet) |
| `1da17090` | this phase's captures (only `dashboard-summary-d` assets retaken) |

Gate results (exit codes are the actual process exit codes):

| Gate | Result |
|---|---|
| Backend `uv run python -m pytest` (test settings) | **exit 0** — 1450 passed, 10 skipped, coverage 84.14% (≥80% gate) |
| New backend suites | `test_dashboard_summary_reconciliation.py` 28 scenarios + `test_dashboard_summary_contract_v2.py` 4 tests — 34 passed |
| `npm run test:unit` | **exit 0** — 119 files, 1145 tests (clean-machine rerun; the marathon run had 1 unrelated `ProfileRoutes` load flake, and one contaminated post-cleanup run with leaked-process fallout — both superseded by the clean rerun) |
| `npm run type-check` | **exit 0** |
| `npm run type-check:charts` | **exit 0** |
| `npm run type-check:reliability` | **exit 0** |
| `npm run lint` (strict baseline) | **exit 0** (0 errors, 8 baseline warnings; baseline re-pinned for 3 line-shifted `api.ts` entries after the additive type re-export) |
| `npm run api:types:check` | **exit 0** |
| `npm run build` | **exit 0** (2.4s) |
| Browser `dashboard-statement-d` | **exit 0** — desktop 1440×1000, tablet 1024×768, mobile 390×844; approved composition, expanded/collapsed (mouse + real Enter), one-owner summary request deltas (`summary_contract=2` on every request), partial/unreconciled/legacy-only/malformed states, long-amount elementFromPoint containment, desktop→mobile→desktop, native 200% zoom (DPR 2 verified, reset to 1) |
| Browser context / dates / recovery / requests | **exit 0** ×4 |
| Browser charts-c2 / charts-c3 / charts-c4 / charts-c5 / charts-c | **exit 0** ×5 (charts-c additionally log-verified below) |
| Browser delivery / layout | **exit 0** ×2 |
| Browser FULL route matrix | **exit 0** — all 18 routes × 4 viewports, 0 failures, 0 fixture mismatches |
| Browser final-qa-d8 | **exit 1 — one failing workflow, PRE-EXISTING**: `chart-acceptance: price table keeps exact dollar displays` fails identically on the untouched base `efca731d` (comparison run recorded in `temp_files/gate-finalqa-BASE.log`). Everything else in the D8 default-on pass is green: 90 probes, 37 workflows, 3 rollback spot checks, 35 captures, dashboard gzip 490,527 < 535k budget. All 90 default-on probes also pass on this branch. |
| Browser charts-c exit-code anomaly | two runs produced **clean PASS logs** (`PASS desktop /dashboard`, `PASS charts c flow`, zero route failures/mismatches) with an anomalous process exit (127 once, an exit-wedge once) — the known agent-browser exit-wedge family on this case; the PASS evidence is in `temp_files/gate-browser-charts-c*.log` and the FULL matrix covers the same surface green |

Perf record (plan Task 1, synthetic multi-account fixture: 3 accounts × 2 assets
× ~34 rows): **247 queries, 0.155 s** (`test_multi_account_query_count_is_recorded_and_bounded`,
`DASHBOARD-STATEMENT-PERF`).

## Real-data validation (disposable copy, read-only probes)

Method: copied `backend/db.sqlite3` into the worktree (original never opened
for write), backend served from the worktree on :8000, frontend built with
`VITE_API_URL=http://127.0.0.1:8000` and served on :8080, a SimpleJWT pair
minted against the copy. Completed checks:

- Multi-account (All accounts, 8 accounts across ByBit/Charles Stanley/IB/OKX/Tinkoff):
  statement renders the real API document verbatim (invested $200,821.03 /
  cash out ($46,294.53) / net capital $154,526.50 / net result ($18,434.47)
  with the `(partial)` flag), charts and allocation coexist, amounts contained.
- Single crypto account (OKX Trading, fully liquidated): control ($40,068.24)
  vs attributed ($27.34) → unexplained ($40,040.90) with `reconciliation:
  incomplete`, reasons exactly `crypto_coin_fee_not_attributed` +
  `in_kind_flows_unclassified`, 7 unmatched transfer-outs counted. The legacy
  page shows only "(98.3%)" with no explanation; the statement names the gap.
- Account switch via the header arrows re-renders the per-account statement.
- Historical-date and currency contexts were exercised in the synthetic
  browser matrix (dates case + statement case); the real-data session covered
  the account axis only before the disposable environment was torn down.
- Legacy parity on real data: the five legacy fields are byte-identical with
  and without the negotiation parameter (same endpoint, same handler).

## Unresolved reconciliation cases (acceptance gaps for financial review)

1. **RUB bonds: engine FX decomposition does not compose with the cash-ledger
   identity.** On real data the six RUB bonds produce `fxSecurity` ≈ $421,815
   against a $136k NAV, and the All-accounts statement shows unexplained
   ($426,569.74). The engine values bond basis in the reporting currency by
   converting the buy-in *percentage* at entry-date FX; the resulting
   attribution cannot be reconciled against the ledger identity. Surfaced
   verbatim as the unexplained difference — never folded into FX by this
   branch (this IS the certified-FX row's engine component; the gap is that
   the pieces do not sum to the control total). Needs an engine-level
   financial decision.
2. **Coin-denominated crypto fees** (e.g. BTC fee on a BTC-USDT trade): the
   unrealized engine values the raw quantity sum while NAV uses the
   fee-depleted `position()`; the fee burn is unattributed by the engine
   (unit-pinned; reason `crypto_coin_fee_not_attributed`).
3. **Unmatched external crypto transfers**: transfer-outs book no realized
   result (transfer types are not disposals); transfer-ins enter at zero
   basis. No in-kind policy is invented — flows are counted diagnostically
   (`unclassifiedInKindFlows`) and the statement stays incomplete.
4. **Same-day disposal + reacquisition** degenerates the weighted-average
   buy-in walk (basis −0) and overstates unrealized; pinned as an honest
   `unreconciled` regression.
5. **Amortizing bonds**: the engine's redemption basis uses sell-date
   notional; notional drift between buy and sell lands in the unexplained
   difference. No amortizing-bond reconciliation is claimed.
6. **pre-existing final-qa-d8 failure** (above) — owned by the D8 workstream,
   not this branch (base-reproduction evidence recorded).

## Review callouts (from the design doc, §6)

1. Income is gross of tax (diverges from `get_capital_distribution`, which
   nets `Tax` rows — reusing it would double-count taxes with the Taxes row).
2. Crypto reward income converts the USD-denominated reward value with
   USD→target FX (the existing distribution helper's coin-rate conversion
   over-scales coin-currency reward rows).
3. Certified FX = engine security FX + independently derived cash-flow FX
   (`cash at EOP rates − the same flows at own-date rates`); the residual FX
   in `services/performance.py` is not reused and that surface is unchanged.
4. Total return keeps the incumbent formula with signed cash-out — this is
   exactly the approved mock's arithmetic (17.50% for the mock example).
