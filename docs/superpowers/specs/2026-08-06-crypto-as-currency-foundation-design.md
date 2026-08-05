# Crypto-as-Currency Foundation — Design

**Date:** 2026-08-06
**Status:** Approved (brainstorming complete; pending implementation plan)
**Scope:** Introduce Crypto as a first-class NAV asset class + revert the unified trade commission model to real-fill-price + separate per-currency commission entries.
**Origin issue:** #33 (option BTC leg) — this spec is the **foundation** of the multi-spec program that ultimately resolves #33. #33 itself stays open until the options-accounting spec (sub-project 4) lands.

---

## 1. Problem

### Trigger

Issue #33 — an OKX option SELL leaves a residual BTC position (`+0.007019`) because the importer drops the fill's BTC balance change. Investigating the fix surfaced a deeper architectural gap: **crypto coins are modeled only as priced securities, never as liquid balances.** This blocks correct options accounting (collateral, fees, premium all move BTC), and forces a series of workarounds in the trade commission model.

### Root cause — two coupled gaps

**Gap A — Crypto has no "balance" concept.** A crypto coin (BTC) is an `Assets` row (`type="Crypto"`, `currency="USD"`, `exposure="Commodity"`) valued purely as a priced position: `quantity × BTC-USD price`. There is no way to say "this account holds 0.5 BTC of liquid balance to pay fees or post collateral." Only stablecoins (USDT/USDC) have a balance concept, via the deposit/withdrawal→cash re-routing in `crypto_exchange.py`. Non-pegged coins are second-class.

**Gap B — The commission model compensates for Gap A.** Because a BTC fee has nowhere to land (no BTC balance), commits #28–#37 built a unified cash-flow model where:
- base-asset fees are **netted into quantity** (the BTC fee reduces the BTC quantity), and
- quote-currency fees are folded into an **effective price** so `|price × quantity|` reproduces the net settlement.

Then `total_cash_flow` (`transactions.py:234-257`) **deliberately excludes** commissions whose `commission_currency` differs from the trade currency (`transactions.py:256`). These were correct fixes *under the no-crypto-balance constraint*. Once the constraint lifts, the simpler real-price + separate-commission model becomes viable again and is economically cleaner (the stored price matches the fill, fees are visible entries).

### Why this is a foundation, not a bug fix

The intended end state for #33 (premium received as cash inflow at entry, collateral as book-value transfer, realized P&L at expiry) **requires** crypto coins to have balances. Options accounting cannot be built on top of the current "BTC is only a priced position" model. So the work decomposes into a dependency chain:

```
(1) Crypto-as-currency foundation   ← THIS SPEC (load-bearing)
     └── (2) Display-currency toggle (user pref; report crypto P&L in EUR/USD)
     └── (3) Commission model revert   ← INCLUDED IN THIS SPEC (tightly coupled to (1))
            └── (4) Options accounting (calculated premium, collateral transfer,
                   premium-at-entry P&L, MTM, realize-at-expiry)
                   └── #33 residual-BTC — resolved here
```

This spec covers (1) + (3). It does **not** fix #33 directly — #33 is the capstone of (4). But (4) cannot start until (1)+(3) land.

---

## 2. Goals & non-goals

### Goals

1. **Crypto is a first-class NAV class.** A new bucket alongside Cash and Securities. Each non-pegged coin (BTC, ETH, TRUMP, …) is a liquid balance valued at its live USD price, shown as its own line item, counted **once** in NAV.
2. **No double-count.** BTC stops being valued on the securities side of NAV; it is valued once, as Crypto.
3. **Crypto FX is price-derived.** `get_rate` resolves crypto codes via the `Prices` table (BTC-USD is the BTC→USD rate), chaining through the existing fiat FX graph. No `FX` table rows for crypto.
4. **Commission model reverts to real fill price + separate per-currency commission entries.** Trades store the real `fillPx`; commissions land in their own currency's balance (a BTC fee moves the BTC balance).
5. **Cross-currency commissions are separate rows.** A fee whose currency differs from the trade's (e.g. a BTC fee on a USDT trade) is emitted as its own `Transactions` row that moves the fee asset's quantity. Same-currency fees stay folded into the trade row. This keeps every row single-currency — `total_cash_flow` stays a per-row `Decimal` (no dict signature change needed).

### Non-goals (explicitly deferred)

| Item | Deferred to |
|---|---|
| Display-currency toggle (report crypto P&L in non-native currency) | Sub-project 2 |
| Option accounting: calculated premium, collateral transfer leg, premium-at-entry P&L, MTM, realize-at-expiry | Sub-project 4 |
| **#33 residual-BTC fix** | Sub-project 4 |
| Price-quotation multiplier / lot size (`÷100` for OKX options) | Sub-project 4 |
| Long-tail coin price fetching beyond ETH/TRUMP | Ongoing (per-coin) |
| Formal `Brokers.kind` field (fiat/crypto/hybrid) | Later spec |

### In-scope but flagged as the largest piece

- The **commission revert in `_spot_legs` + the importer** is the bulk of the work: splitting cross-currency commissions into separate rows, switching to real fill prices, and updating the import tests that currently assert effective-price behavior (from #28–#37). `total_cash_flow` itself needs only a narrow change (stop recomputing `quantity × price` for crypto trades; drop the cross-currency commission exclusion) — its signature stays `Decimal`, so the ~35 call sites are **not** disturbed.

---

## 3. The three-class NAV model

### Today

NAV = **Cash** (fiat + stablecoins) + **Securities** (everything with a `quantity × price`).

### After

| Class | What's in it | How it's valued | Examples |
|---|---|---|---|
| **Cash** | Fiat + stablecoins | Face value, FX-converted via `FX` table | USD, EUR, RUB, USDT, USDC |
| **Crypto** | Liquid non-pegged coins | `quantity × live coin-USD price` (from `Prices`), then FX-converted | BTC, ETH, TRUMP |
| **Securities** | Priced positions | `quantity × price`, FX-converted | Stocks, bonds, options, futures |

**Key rule:** stablecoins (USDT/USDC) remain **Cash** — the peg-to-fiat-at-1.0 line is the boundary. Non-pegged coins become **Crypto**. This is not a stored flag on each coin; it is determined structurally: stablecoins stay in the `balance()` cash dict and the FX peg short-circuit; everything else with `Assets.type == "Crypto"` routes to the Crypto bucket.

### Why a third class (not "fold into Cash")

Folding BTC into the Cash bucket would put a "BTC" line next to USD/EUR in the position table — confusing, since BTC is volatile and conceptually an asset. A third class lets each coin surface as its own line item (valued live) while still being *liquid* (spendable on fees, collateral, premium). It matches the mental model: crypto is neither fiat cash nor a traditional security.

---

## 4. Crypto class mechanics

### 4.1 Representation — stay in `Assets`, rigorous class boundary

Crypto coins **remain** `Assets` rows with `type="Crypto"`. **No schema change to `Assets`.** The class boundary is enforced at the code layer, not the schema layer.

Rationale: `Transactions.security` and `Prices.security` both FK to `Assets` (`models.py:226`, `:367`). Forking crypto into a separate model would require polymorphic-izing those FKs, parallel position logic, and migrating every existing `type="Crypto"` row plus its transactions/prices. `Assets` is already a heterogeneous instrument table (stocks, bonds, options, futures coexist) — crypto joining it is the established pattern. The `type` field is the discriminator.

The conceptual clarity is achieved via:
- a dedicated **`services/crypto.py`** module (helpers, valuation, FX resolution),
- clear **`is_crypto(asset)` / `is_crypto_code(code)`** checks,
- its own price-fetching, own NAV bucket, own position semantics.

### 4.2 No data migration of BTC rows

Existing BTC transactions and `Assets` rows created by the current importer already carry `type="Crypto"`. The foundation is a **code-level routing change** (crypto leaves the securities NAV loop, joins a new crypto loop), not a data migration. No `Transactions` or `Assets` rows need rewriting for the Crypto-class change itself.

### 4.3 Position & valuation

**Position** (`services/positions.py`): unchanged mechanism — `sum(quantity)` over the coin's transactions.

**Valuation** (`services/nav.py` — new crypto loop, replacing the securities path for crypto assets):

```
crypto_value_usd    = position(coin, date) × price_at_date(coin, date)   # price = BTC-USD from Prices
crypto_value_target = crypto_value_usd × fx_rate("USD", target_currency, date)
```

Identical math to securities valuation. The difference is purely **bucketing**: crypto assets route to a `"Crypto"` breakdown key, not `"Securities"` / `security.type`. The new loop is a near-copy of the securities loop (`nav.py:196-214`) with:
- a filter `security.type == "Crypto"` (the securities loop gains the inverse exclusion `security.type != "Crypto"`), and
- breakdown bucket `"Crypto"` plus a per-coin sub-key (e.g. `"Crypto: BTC"`).

### 4.4 Price source — per-asset `yahoo_symbol`

Drop the hardcoded `YAHOO_USD_PRICE_SYMBOLS = {"BTC": "BTC-USD"}` dict (`crypto_exchange.py:44`). Instead, **read the coin's `Assets.yahoo_symbol`** (an existing field, e.g. `"BTC-USD"`, `"ETH-USD"`, `"TRUMP-USD"`). `resolve_crypto_asset` (`crypto_exchange.py:102-116`) is extended to set `yahoo_symbol` on coin creation.

`fetch_crypto_usd_price_from_yahoo` (`crypto_exchange.py:212`) is generalized to accept any coin: it looks up `asset.yahoo_symbol` and fetches that Yahoo ticker. The foundation adds Yahoo mappings for at least **BTC, ETH, TRUMP** (set on their `Assets` rows). Long-tail coins without a Yahoo symbol remain unpriced (quantity tracked, value `None`) — documented limitation, deferred.

### 4.5 FX for crypto — price-derived (decision 2a)

`services/fx.py` `get_rate` gains a **crypto branch**. When `source` or `target` is a crypto code (resolved via `is_crypto_code`, which checks `Assets.type="Crypto"`):

```
BTC → EUR:
  btc_usd = price_at_date(BTC_asset, date)             # from Prices
  usd_eur = existing get_rate("USD", "EUR", date)      # from FX table
  return btc_usd × usd_eur

ETH → BTC (crypto-to-crypto):
  eth_btc = (ETH/USD) / (BTC/USD)                      # both legs via USD
```

Implementation: a resolver that, for a crypto code, returns its USD price (coins are USD-priced by convention) then chains through the existing fiat FX graph. The stablecoin-peg short-circuit (`fx.py:194-200`) stays — it is a special case of the same idea (USD↔USDT rate = 1.0).

**No `FX` table rows for crypto, ever.** The `Prices` table is the single source for coin-USD rates. This avoids duplication/drift between two tables.

**Cache:** the FX graph cache (`_get_graph`, keyed `(date, investor)`) is unaffected — crypto prices live in `Prices`, not `FX`, so they neither pollute nor need to invalidate the FX cache. The price-derived resolver reads `Prices` fresh on each hop.

### 4.6 What surfaces where

- **NAV total**: Crypto bucket summed in, once. No double-count.
- **NAV breakdown**: new `"Crypto"` key alongside `"Cash"` / `"Securities"`, plus per-coin sub-keys.
- **Positions table**: crypto coins appear as line items (quantity, live price, value, typed `"Crypto"`). Not in cash, not in securities.
- **Account balance** (`services/accounts.py:balance`): crypto coins do **NOT** contribute to the cash-balance dict. They are not cash. Stablecoins stay; non-pegged coins leave (they were never there anyway — only stablecoins were cash-routed).

---

## 5. Commission model revert

### 5.1 What reverts, what stays

| From #28–#37 | Disposition |
|---|---|
| `_spot_legs` effective-price derivation for stablecoin quotes (#32, #34) | **Reverted** — real fill price; fee is a separate entry |
| `_spot_legs` base-fee netted into quantity (#30, #31) | **Reverted** — real quantity; fee is a separate entry |
| `total_cash_flow` `quantity × price` recomputation (#37) | **Reverted** — per-leg cash flow stored directly; `total_cash_flow` returns the row's single-currency flow (no signature change) |
| `commission_currency` field on `Transactions` | **Stays** for same-currency commissions; cross-currency commissions move to separate rows (§5.3) |
| `commission_currency` exclusion of base-asset fees (`transactions.py:256`) | **Reverted** — cross-currency commissions are separate rows that move the fee asset's quantity; same-currency commissions still fold into the trade row |
| Option-leg verbatim `cash_flow` (#33 partial) | **Stays for now** — option changes deferred to sub-project 4 |
| Unified `import_group_id` / event dedup | **Stays** — unrelated to commission model |

### 5.2 Why the revert is correct *now*

#28–#37 were deliberate fixes for real bugs (fee-inclusive cost basis, asset-denominated fees) under the constraint that crypto coins had no balances. The effective-price / net-into-quantity workarounds were the only way to make `|price × quantity|` reproduce the net settlement when the fee had nowhere else to go. **Once §4 gives crypto coins their own balances, the simpler real-price + separate-commission model becomes viable and economically cleaner** (stored price = fill, fees visible). The revert is not saying #28–#37 were wrong — they were correct under the old constraint; the constraint is lifting.

### 5.3 Cross-currency commissions are separate rows

**The problem with keeping a cross-currency commission on the trade row:** the **position layer** sums `Transactions.quantity` grouped by security. A BTC fee sitting in the `commission`/`commission_currency` fields of a USDT trade row is invisible to that sum — the BTC position would show the full `+1` from the trade's quantity, not the fee-reduced `+0.999`. This is precisely the bug that #30/#31 fixed by netting the fee into quantity. If we revert the netting (real quantity), the fee must reduce the position through another mechanism.

**Solution: cross-currency commissions become separate rows.** A fee whose `commission_currency` differs from the trade's currency is emitted as its own `Transactions` row of a commission type, with its own `security` (the fee asset) and `currency` (the fee currency). Same-currency fees stay folded into the trade row as today.

For a BTC-USDT buy of 1 BTC @ 60,000 USDT, fee 0.001 BTC:

| Row | type | currency | security | quantity | price | commission |
|---|---|---|---|---|---|---|
| Trade | Crypto trade in | USDT | BTC | +1 | 60,000 (real fill) | — |
| Fee | Broker commission (crypto) | BTC | BTC | — | — | −0.001 |

Now every row is **single-currency**, and the position layer reconciles naturally: BTC position = `+1` (from trade quantity) `− 0.001` (from the fee row's commission, which the position layer sums as a quantity movement for commission rows). USDT cash = `−60,000`. The BTC cash balance (now that BTC is a Crypto-class balance, §4) absorbs the `−0.001`.

**Implication for `total_cash_flow`:** because every row is single-currency, `total_cash_flow(tx) → Decimal` **keeps its current signature**. It does not need to become a multi-currency dict. This removes the "~35 call-site migration" that an earlier draft of this spec flagged as the bulk of the cost. The change to `total_cash_flow` is narrower: (a) stop recomputing `quantity × price` for crypto trades — read the stored per-leg cash flow; (b) drop the `commission_currency != trade_currency` exclusion (no longer needed, since cross-currency commissions are no longer on the trade row).

**New transaction type:** a commission row needs a type. Options: reuse `TRANSACTION_TYPE_BROKER_COMMISSION`, or add `TRANSACTION_TYPE_CRYPTO_COMMISSION` for clarity and import-dedup isolation. Resolved in the implementation plan; the latter is preferred (mirrors the existing `CRYPTO_*` type family and keeps dedup keys clean).

### 5.4 Real price when the CSV gives only a net settlement

Today the importer derives an effective price from the net settlement when a separate fill price is absent. Under the revert, the **fill price must come from the CSV's `Filled Price` column** (the real price); the settlement is reconstructed as `fill_price × quantity ± fee`. If `Filled Price` is missing, that is a genuine data gap — not something to paper over with an effective price. Small importer change: stop deriving effective prices; require `Filled Price`.

### 5.5 Option legs — unchanged in this spec

Option fills currently carry `cash_flow` (verbatim from the CSV's Balance Change) because `quantity` is in contracts and `p × q` is nonsensical. Under the target model (sub-project 4), option premium is *calculated* as `quantity × fillPx × price_multiplier − commission`, and the collateral is a separate transfer leg derived from the Balance Change. **But that work is deferred.** The foundation leaves option legs exactly as they are today and only guarantees the spot-model revert does not break them. The price-multiplier / lot-size (`÷100`) concept is introduced and resolved in sub-project 4.

---

## 6. Decisions ledger

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Crypto NAV class | Third class (Cash / Crypto / Securities) | Avoids double-count; coins surface as own line items, not in fiat cash bucket |
| 2 | Crypto FX source | Price-derived from `Prices` (2a) | No second-table duplication/drift; reuses price infra |
| 3 | Crypto representation | Stay in `Assets`, rigorous code boundary | Avoids FK-fork tax; `Assets` already heterogeneous; class boundary in code |
| 4 | Foundation scope | Crypto class + commission revert (1+3) | Coupled: revert only makes sense once crypto has balances |
| 5 | Cash-flow API | Cross-currency commissions are separate rows; `total_cash_flow` stays per-row `Decimal` | Single-currency rows reconcile position and cash layers cleanly; avoids wide signature migration. (Revised during spec self-review: an earlier draft proposed a multi-currency dict, but it created a position/cash reconciliation gap.) |
| 6 | Broker typing | Defer `Brokers.kind` | Crypto class determined by asset, not account; not load-bearing |
| 7 | Option sequencing | Defer all option changes to sub-project 4 | Clean separation; no broken interim; #33 waits |
| 8 | Coin price source | Per-asset `yahoo_symbol` (drop hardcoded dict) | Reuses existing `Assets` fields; extensible |

---

## 7. Affected components

| Component | Change | Protected? |
|---|---|---|
| `backend/constants.py` | Add crypto-related helpers/sets (not a fixed choices list — coins are open-ended) | No |
| `backend/services/crypto.py` | **New module** — `is_crypto()`, `is_crypto_code()`, valuation helpers, FX resolver glue | No |
| `backend/services/nav.py` | New crypto loop; securities loop excludes crypto; IRR `_calculate_cash_flow` migrates to dict | **Yes** (`NAV_at_date`) |
| `backend/services/fx.py` | `get_rate` crypto branch (price-derived); keep stablecoin pegs | **Yes** (`FX.get_rate`) |
| `backend/services/transactions.py` | `total_cash_flow` stops recomputing `qty×price` for crypto trades; drops cross-currency commission exclusion (signature stays `Decimal`) | **Yes** (protected logic) |
| `backend/services/accounts.py` | `balance()` unchanged shape; crypto excluded from cash dict (routed via NAV crypto loop) | No |
| `backend/services/crypto_exchange.py` | `_spot_legs` reverts to real price + **separate commission rows** for cross-currency fees; `resolve_crypto_asset` sets `yahoo_symbol`; `fetch_crypto_usd_price_from_yahoo` generalized | **Yes** (protected importer logic) |
| `backend/services/pricing.py` | No change to `price_at_date`; crypto uses it like securities | Indirect |
| `backend/core/balance_tracker.py` | No change (cash flow still per-row `Decimal`) | No |
| `backend/database/serializers.py` | Display of separate commission rows; crypto bucket in breakdown | No |
| `backend/constants.py` | Possibly add `TRANSACTION_TYPE_CRYPTO_COMMISSION` | No |
| `backend/common/models.py` | **No schema change** in this spec (deferred `Brokers.kind` would be later) | N/A |
| Migrations | **None** in this spec (routing/constants/code change only) | N/A |

---

## 8. Testing strategy

Per AGENTS.md: protected-logic changes need unit tests + regression fixture with expected numeric result; all tests use `Decimal`.

### New unit tests

- `is_crypto()` / `is_crypto_code()` — BTC/ETH/TRUMP true; USDT/USDC/USD/EUR false; unknown code false.
- `get_rate` crypto branch — BTC→USD (from `Prices`), BTC→EUR (chain via USD), ETH→BTC (both legs via USD), missing price → `ValueError`.
- `total_cash_flow` — crypto trade reads stored per-leg cash flow (no `qty×price` recompute); same-currency commission folds in; option leg unchanged (verbatim cash_flow); signature still `Decimal`.
- `_spot_legs` real-price + separate commission rows — BTC-USDT buy with BTC fee emits trade row (USDT, real fillPx) **plus** a separate BTC commission row; stablecoin-quote buy stores real fillPx with same-currency fee folded in.
- `fetch_crypto_usd_price_from_yahoo` — generalized for any `yahoo_symbol` (mocked Yahoo response).

### Regression fixtures (expected numeric results)

- **NAV with BTC + stock**: BTC 0.5 @ $60,000 = $30,000 in Crypto bucket; AAPL 10 @ $150 = $1,500 in Securities; USD 1,000 cash. Total NAV $32,500, breakdown `{Cash: 1000, Crypto: 30000, Securities: 1500}`. BTC counted once.
- **NAV before/after the routing change** is invariant for portfolios with no crypto (regression guard).
- **Multi-currency trade with separate commission rows**: the BTC-USDT buy above contributes `-60000` to USDT cash and the BTC commission row contributes `-0.001` to BTC cash; BTC position = `+1` (trade quantity) `− 0.001` (commission row) = `+0.999`, reconciling across both layers.
- **FX conversion**: BTC cash reported in EUR = `$30,000 × USD→EUR rate`.

### Integration

- Full OKX CSV import of a spot-only fixture (no options) — verify real prices, separate commission entries, correct per-currency balances.
- Existing crypto import tests updated to the new commission model (the effective-price assertions from #28–#37 are replaced by real-price + separate-commission assertions).

### Edge cases

- Zero quantity trade; missing price; missing `yahoo_symbol` (coin unpriced, value `None`, NAV skips with a warning); same-currency commission; commission with no `commission_currency` (defaults to trade currency, as today).

---

## 9. Open questions for the implementation plan

These are deferred to the writing-plans phase, not blockers for this spec:

1. **Commission-row type & dedup** — reuse `TRANSACTION_TYPE_BROKER_COMMISSION` or add `TRANSACTION_TYPE_CRYPTO_COMMISSION`; the separate commission row needs its own `import_event_id` (e.g. `{event_id}:fee`) so it dedups cleanly against re-imports.
2. **Position layer for commission rows** — confirm `services/positions.py` sums commission-row quantity as a position movement for the fee asset (it currently keys on trade `quantity`; commission rows have `quantity=None` and the movement lives in `commission`). This is the one place the model needs the position layer to read `commission` as a quantity equivalent for commission-type rows.
3. **Per-coin `yahoo_symbol` backfill** — existing BTC `Assets` rows may not have `yahoo_symbol` set; a one-time backfill (data migration, not schema) sets `BTC-USD` / `ETH-USD` / `TRUMP-USD` on existing rows. Whether this runs as a Django migration or a management command is a plan-level choice.
4. **Display of the Crypto bucket** — frontend positions-table section for crypto. Out of backend scope but called out so the plan can flag a frontend follow-up.

---

## 10. Phased plan (preview)

The implementation plan (next step, via writing-plans) will likely sequence:

1. **Constants + `services/crypto.py`** — `is_crypto` helpers, no behavior change yet.
2. **FX crypto branch** — `get_rate` price-derived resolver, unit-tested in isolation.
3. **NAV crypto loop** — new bucket, securities-loop exclusion, regression fixture. (At this point Crypto-class is live; commission model still old.)
4. **Commission revert in `_spot_legs` + importer** — real fill price; cross-currency fees become separate commission rows; same-currency fees stay folded. Update import tests (the effective-price assertions from #28–#37 are replaced). This is the largest phase.
5. **`total_cash_flow` narrow change** — stop recomputing `qty×price` for crypto trades; drop the cross-currency commission exclusion. Signature stays `Decimal`; minimal call-site impact.
6. **Price-fetching generalization** — `yahoo_symbol`-driven, backfill existing rows.

Each phase is independently testable and mergeable. Phase 4 is the largest (commission model + importer + test updates).
