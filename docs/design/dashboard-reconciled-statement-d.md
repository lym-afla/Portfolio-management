# Phase D — Reconciled dashboard statement: design & contract

Status: implemented on `codex/dashboard-reconciled-statement-d` for **draft review only**.
Approved visual: `docs/design/assets/dashboard-summary-d/approved-statement.png` (synthetic
mock; labels/rules below take precedence over the mock's example numbers).
Plan: `docs/superpowers/plans/2026-10-15-dashboard-reconciled-statement-d.md`.

---

## 1. Component / source matrix (Task 0 findings, verified against code)

| Statement row | Source (canonical, reused unchanged) | Notes verified in code |
|---|---|---|
| Current NAV | `services.nav.NAV_at_date(...,)["Total NAV"]` with `diagnostics` list | lru_cached; supports omission diagnostics (missing_price / missing_fx). Authoritative; never altered. |
| Invested | `Transactions` type `Cash in`, Σ`cash_flow` × own-date FX (same query shape as the legacy view) | Includes phantom `Cash in` rows created by in-kind **asset transfers** (`services.transactions._build_phantom_cash_transaction`) — legacy behavior preserved. |
| Cash out | `Transactions` type `Cash out`, Σ`cash_flow` × own-date FX | Already signed negative; preserved. Includes phantom `Cash out` rows (asset-transfer out-leg). |
| Net invested capital | invested + cash-out (subtotal, never an additive component) | |
| Realized gains/losses (price only) | Σ per asset `services.realized.realized_gain_loss(...)["all_time"]["price_appreciation"]` | Engine excludes commissions, taxes, income. Options: realized is computed by `_realized_option_close` (premium+payout+fee). |
| Unrealized gains/losses (price only) | Σ per asset `services.realized.unrealized_gain_loss(...)["price_appreciation"]` | Engine returns **zeros for options** by design (documented gap → incomplete). Missing price ⇒ 0 in engine — detected and downgraded to partial here. |
| Dividends & interest (gross) | New aggregation: `Dividend` + `Coupon` + `Interest income` `cash_flow` × own-date FX; crypto `Crypto reward` at `reward_value` (USD) × own-date USD→target FX; bond ACI net (`Buy` aci<0 / `Sell` aci>0) × own-date FX | **Diverges from `get_capital_distribution`**, which (a) nets `Tax` rows into the distribution and (b) converts reward values with the coin→target rate although reward value is already USD (latent double-scale). Ours is gross of tax; taxes are their own row. Flagged for financial review. |
| Fees | Σ commissions that hit cash, × own-date FX: same-currency `commission` on trade rows (exactly the legs `total_cash_flow` embeds), `Broker commission` rows, `FXTransaction.commission` legs | Cross-currency crypto coin fees (e.g. BTC fee on a BTC-USDT trade) are NOT here: they deplete the coin position and are absorbed by the unrealized engine (position() commission depletion). Counting them here too would double-count. |
| Taxes | Σ `Tax` rows `cash_flow` × own-date FX (negative) | `get_capital_distribution` nets these into distributions — reuse would double-count. performance.py's period table actually double-counts taxes today (distribution net of tax AND a separate tax row); its residual `fx` absorbs the difference. Not reproduced here. |
| FX effect | `fxSecurity + fxCash` (both independently derived — see §3) | **Not** the `performance.py` residual (EoP − Σcomponents, zeroed below 0.1). That residual is explicitly not reused. |
| Total NAV | = canonical NAV row, emphasized | |
| Total return (since inception) | Legacy formula `(NAV − Cash-out)/Invested − 1` with **signed** cash-out, `null` when invested = 0 | This IS the approved mock's arithmetic: its 17.50% = (112,500 − (−5,000))/100,000 − 1. No formula change. |
| IRR since inception | `services.nav.IRR(user, eff, currency, account_ids=..., cached_nav=NAV)` | Same definition as the legacy summary (external flows only; crypto transfers cf=0). `cached_nav` avoids a second NAV evaluation. |

Unsupported / gap states (never forced to balance; each carries an explicit reason):

- Unpriced crypto coin or missing cash-currency FX at the effective date → NAV partial
  with `knownSubtotal` (omission surfaced via `NAV_at_date(diagnostics=...)`).
- Open **option** positions: unrealized engine returns zeros → statement status partial,
  reason `option_unrealized_not_attributed`; unexplained difference carries the gap.
- **External (unmatched) crypto transfers** in scope since inception: the engine books
  transfer-outs with NO realized result at all (transfer types are not disposals) and
  transfer-ins at zero basis (deferred 100% gain). Any re-attribution would be a new
  policy → NOT invented here. They are excluded from net invested capital (legacy
  semantics), surfaced as `unclassifiedInKindFlows` and the statement goes partial +
  `reconciliation: incomplete`.
- Bond redemption basis uses sell-date effective notional (`realized.py`); for
  **amortizing** bonds the trades-cash cancellation against basis differs by the notional
  drift → shows up in the unexplained difference honestly.
- `Repo`, `Merger in/out`, `Stock split` produce zero cash flow in `total_cash_flow` and
  are not attributed; a non-zero cash-bearing type outside the known families would land
  in `otherFlows` (rendered only when non-zero) with a note.
- **Coin-denominated crypto fees** (BTC fee on a BTC-USDT trade): `position()` depletes
  the coin so NAV drops, but the unrealized engine values the raw quantity sum — the fee
  burn is invisible to the engine. Declared via reason
  `crypto_coin_fee_not_attributed`; the unexplained difference carries it verbatim.
- **Unmatched (external) crypto transfer-outs** book NO realized result
  (`is_disposal_transaction` excludes transfer types): the coin and its basis leave NAV
  silently. Surfaced via `unclassifiedInKindFlows` + the unexplained difference.
- **Same-day disposal + reacquisition** of one security degenerates the weighted-average
  buy-in walk (weights cancel → basis −0) and overstates unrealized. Pinned as an honest
  `unreconciled` outcome (regression test), not hidden.
- **Crypto reward rows carrying the coin as currency**: the engine's basis replay
  multiplies the (already USD) reward value by the coin→USD rate. Income in this service
  uses the USD value with USD→target conversion; reward rows denominated directly in USD
  reconcile exactly. The coin-currency variant surfaces as an unexplained difference
  pending an engine-level financial decision.

## 2. Scope, dates, identity rules

- One scope for everything: `get_selected_account_ids(user, user.selected_account_type, user.selected_account_id)` — same request owner as legacy; ownership enforced there (all branches filter by `broker__investor=user`).
- One effective date (`request.effective_current_date`, session middleware), one reporting currency (`user.default_currency`), one horizon: **since inception** (all `date__date__lte=effective`).
- Signed flows: `Cash out` cash_flow is already negative; nothing re-signs it.
- Internal (matched) crypto transfers: principal-only (engine treats matched pairs as neutral); neither flows nor capital. Cross-scope visibility follows the selected accounts.
- Same investor everywhere (every query filters investor or account∈selected).

## 3. Certified decomposition (the arithmetic the backend certifies)

All quantities Decimal, reporting currency Q, `f(c, d)` = `services.fx.get_rate(c, Q, d)["FX"]`.

```
netCapital      = invested + cashOut                        (Cash in/out rows at own-date f)
controlTotal    = NAV(effective) − netCapital               (identity/control, NOT proof)

realizedPrice   = Σ_a realized_a.price_appreciation         (own-date exit f on local price change)
unrealizedPrice = Σ_a unrealized_a.price_appreciation       (EOP f on local price change)
fxSecurity      = Σ realized_a.fx_effect + Σ unrealized_a.fx_effect
                (rate movement on basis; engine splits per transaction/EOP — independent)
income, fees, taxes, aci, otherFlows                        (§1 aggregations at own-date f)
fxCash          = Σ_c balance_c(EOP)·f(c, EOP) − Σ_rows cashFlow_row · f(row.currency, row.date)
                ("cash at EOP rates" minus "the same flows at their own-date rates";
                 balance & cashFlow come from the canonical `account.balance` /
                 `total_cash_flow` / FXTransaction-leg paths — never from the control total)

attributedSum   = realizedPrice + unrealizedPrice + income + fees + taxes + fxCash + otherFlows
unexplained     = controlTotal − attributedSum
```

Exactness argument (single-currency case): `GL_a = value_now + Σproceeds − Σbasis`, and the
cash ledger satisfies `balance = netCapital + trades + otherRows`, where
`trades = −Σbasis + Σproceeds − aci − sameCcyCommission`; substituting cancels every trade
leg and yields the decomposition with **aci and same-currency commissions as explicit
components** (aci folded into income per the existing distribution convention;
commissions into fees). Multi-currency adds exactly `fxCash`. The identity is therefore
closed by construction up to documented roundings — no component is a residual of the
statement total.

Tolerance (raw, documented basis):

```
tolerance = Σ_assets 4 · 0.5 · 10^(−cashPrecision_asset)      (realized price/fx, unrealized price/fx)
          + Σ_cashCurrencies 0.5 · 10^(−cashPrecision_broker) (per-currency balance re-quantization)
```

Reconciliation outcomes:

- `reconciled` — NAV complete, every component ok, `|unexplained| ≤ tolerance`.
- `unreconciled` — everything computed but `|unexplained| > tolerance`: the difference is
  shown verbatim as "Unreconciled difference"; it is never folded into FX or any row.
- `incomplete` — a dependency is partial (NAV omissions, missing price/FX, open options,
  unclassified in-kind flows): no certified bridge is claimed even if the sum happens to
  close.

Raw vs display: rows keep exact `raw` strings plus backend `display` strings. The UI
additionally sums the independently rounded display rows; if that differs from the
displayed subtotal the frontend shows an explicit "display rounding" adjustment line
(§Task 2). Display never feeds back into any financial value.

## 4. Wire contract (frozen, additive, opt-in)

Request: `GET /dashboard/api/get-summary/` — **without** `summary_contract`: legacy
five-field response, byte-identical (pinned by regression). With `summary_contract=2`:
legacy five fields unchanged **plus** `summaryV2`. Any other value → `400`

```json
{"error": {"code": "INVALID_SUMMARY_QUERY", "message": "...", "retryable": false}}
```

Internal calculation failures under the contract → `500`
`{"error": {"code": "SUMMARY_CALCULATION_FAILED", "message": "...", "retryable": true}}`
(legacy path keeps its incumbent uncaught behavior).

```jsonc
"summaryV2": {
  "version": 2,
  "kind": "statement",
  "context": {"accountSelection": {"type": "all", "id": null},
               "accountIds": [1], "effectiveDate": "2026-10-15",
               "currency": "USD", "digits": 2},
  "status": "complete | partial | unavailable",
  "reasons": ["missing_price", ...],                 // machine reasons, no sensitive data
  "capital": {
    "invested": Amount, "cashOut": Amount,
    "netInvestedCapital": Amount
  },
  "netResult": {
    "nav": Amount,                                   // partial ⇒ knownSubtotal
    "controlTotal": Amount,
    "components": {
      "realizedPrice": Amount, "unrealizedPrice": Amount, "income": Amount,
      "fees": Amount, "taxes": Amount, "fx": Amount, "otherFlows": Amount
    },
    "fxDetail": {"security": Amount, "cashFlows": Amount},
    "attributedSum": Amount,
    "unexplainedDifference": Amount,
    "toleranceRaw": "0.02",
    "toleranceBasis": "…",                           // human-readable derivation
    "reconciliation": "reconciled | unreconciled | incomplete"
  },
  "returns": {
    "totalReturn": ReturnValue,                      // {value, display, status, reason}
    "irr": ReturnValue
  },
  "diagnostics": {
    "omittedValuations": [ {"reason": "missing_fx", "account_id": 1, ...} ],
    "unclassifiedInKindFlows": {"present": true, "count": 2, "signedFmv": "-1200.00"},
    "notes": ["..."]
  }
}
// Amount   = {"raw": "…"|null, "display": "…", "status": "ok|partial|unavailable",
//              "reason"?: "...", "knownSubtotal"?: "…"}          (chart-value conventions)
```

No sensitive data in diagnostics: ids, currencies, reason codes only.

## 5. Frontend composition (approved visual)

- `PortfolioValueStatement.vue` (new, `src/components/dashboard/`): left statement card
  (Invested / Cash out / Net invested capital / Net result + expandable indented breakdown,
  start **expanded** per the approved image; strong Total NAV row) and right Returns card
  (Total return since inception, IRR since inception). Price-vs-FX separation help text.
- Rendered exclusively from server `display` strings; zero renders as `–` per
  `currency_format`; unavailable/partial render status + reason. No frontend arithmetic on
  raw values except the display-rounding cross-check (string-level decimal addition).
- Breakdown toggle: keyboard operable button with visible focus; collapsed state keeps
  incomplete/unreconciled status visible (status line lives outside the collapsible).
- Legacy-only response (no `summaryV2` on a v2 request): existing five metrics plus an
  honest "breakdown unavailable" notice — never fabricated components.
- Present-but-invalid `summaryV2` throws (typed boundary error), never a silent downgrade.
- Wire-in: same `summaryQuery` request owner in `DashboardPage.vue` (no additional fetch,
  no chart-request changes); `PortfolioMetrics` remains for the five legacy fields.
  NAV chart, allocation pies, history table, palette and shell untouched.

## 6. Financial-review callouts (explicit, for the draft PR)

1. Income is presented **gross of tax** (divergence from `get_capital_distribution`'s
   net-of-tax convention; also avoids the tax double-count embedded in today's period table).
2. Crypto reward income converts its USD value with USD→target FX (divergence from
   `get_capital_distribution`'s coin-rate conversion, which over-scales for coin-currency
   reward rows).
3. Certified FX is `fxSecurity + fxCash`; the residual FX in `performance.py` (and its
   0.1 zeroing threshold) is not reused and that surface is unchanged.
4. The engine gaps in §1 (coin fees, unmatched transfer-outs, same-day wraps, coin-currency
   reward basis, open options) are surfaced as incomplete/unreconciled states — resolving
   them requires engine-level financial decisions that are out of scope here.
