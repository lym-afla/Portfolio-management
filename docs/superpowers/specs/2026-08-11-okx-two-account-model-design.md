# OKX Two-Account Model + Funding-History Import — Design

**Date:** 2026-08-11
**Status:** In design (brainstorming complete; pending user review, then implementation plan)
**Scope:** Model OKX **funding** and **trading** as two `Accounts` rows; add a **Funding-History CSV** parser; pair internal funding↔trading transfers so the existing matched/unmatched disposition machinery can be reactivated safely; minimal backfill. This is **sub-project 5a** of the crypto-modeling program.
**Origin issue:** #29 (OKX two-account model; transfer-neutrality root cause).
**Predecessors:**
- `2026-08-06-crypto-as-currency-foundation-design.md` (sub-projects 1 + 3; PR #38) — Crypto as a first-class NAV class + embedded multi-currency commission model.
- `2026-08-07-crypto-option-accounting-and-realized-gain-design.md` (sub-project 4; PR #40) — option accounting + the matched-vs-unmatched transfer machinery that this spec *activates*.
- `2026-08-01-okx-csv-import-design.md` — the original Trading-History CSV design, which **deferred** the Funding-History CSV (line 12). This spec delivers that fast-follow.

**Follow-up (sub-project 5b, separate spec):** API sub-account tagging by endpoint; `/api/v5/asset/bills` fetch for internal transfers via the live API; full backfill/split of existing mixed API-imported data.

---

## 1. Problem

### Trigger

Issue #29: OKX has two account types — **funding** and **trading (unified)** — with internal transfers between them. The app models the entire OKX relationship as a **single `Accounts` row**, which (a) breaks transfer symmetry and (b) is the root cause sub-project 4's follow-ups worked around with `TRANSFER_DISPOSITION_ENABLED = False` (`services/realized.py:104`).

### Two symptoms (from #29)

1. **CSV internal transfers are one-sided.** A BTC `Transfer out` from the trading account imports as `Crypto transfer out` and reduces the BTC position, but there is no matching `Crypto transfer in` on a funding account — the asset appears to leave the portfolio when it really moved to the OKX funding account.
2. **Live API import mashes funding + trading events into one account; no dedup between them.** The OKX API adapter (`services/broker_api.py:600-630`) fetches both trading and funding endpoints and persists everything under one `Accounts` row.

### Root cause

The entire OKX relationship is collapsed into one account. Once funding and trading are modeled as **two real accounts** and internal transfers are **paired** (both legs in-portfolio), the matched-vs-unmatched machinery sub-project 4 already built (`_transfer_is_matched`, `allocate_group_carry`, `lookup_group_transfer_basis` — all gated behind `TRANSFER_DISPOSITION_ENABLED = False`) can be reactivated: matched transfers stay neutral with basis carrying across accounts; only genuinely unmatched (external) transfers realize.

### Why the flag cannot simply flip today

Sub-project 4's follow-ups disabled disposition because, with one account, OKX internal transfers, Simple-Earn round-trips, and cold-wallet withdrawals are all **indistinguishable** — any of them would be wrongly treated as a disposition. The two-account model + an earn-neutrality discriminator (§4) make them distinguishable, so the flag can flip safely.

### The Funding-History CSV is a new data source

The current `build_okx_csv_events` (`services/importer.py:846`) parses the **Trading History** CSV (`Trade Type` ∈ Spot/Option/Transfer). The file driving this spec is the **Funding History** CSV — a different schema, different row vocabulary, and a parser that does not exist yet. The 2026-08-01 design explicitly deferred it.

| | Trading History CSV (handled) | Funding History CSV (new) |
|---|---|---|
| Columns | `Trade Type, Symbol, Action, Amount, Filled Price, Balance Change, Balance Unit, …` | `Type, Amount, Before Balance, After Balance, Symbol` |
| Internal-transfer signal | `Trade Type=Transfer`, `Action=Transfer in/out` | `Type=From unified trading account` / `To unified trading account` |
| Earn / yield | n/a | `Stake`, `Simple Earn subscription/redemption`, `Deposit yield` |
| External flows | n/a | `Deposit`, `Place/Cancel/Fulfill an order` (C2C) |

### Verified economics (the user's real Funding CSV)

The attached file (`OKX Funding History_2021-07-01~2026-07-30`) confirms the funding-side legs of internal transfers appear as `From unified trading account` (asset entering funding) / `To unified trading account` (asset leaving funding). These pair with the trading CSV's `Transfer in/out`. Examples:

- `2026-06-22 20:05:02, From unified trading account, +0.45849457 BTC` → pairs with a trading CSV `Transfer out` of `0.45849457 BTC` at the same instant.
- `2026-02-09 20:15:18, To unified trading account, −0.67986040 TRUMP` → pairs with a trading CSV `Transfer in` of `0.67986040 TRUMP`.
- Stablecoin internal transfers (e.g. `2026-06-22 20:01:49, To unified trading account, −29994.78 USDT`) are cash legs → `Cash out` (funding) / `Cash in` (trading), net-zero to the portfolio.

It also confirms the earn lifecycle: `From unified trading account +300.00389139 USDT` immediately followed by `Stake −300.00389139 USDT` — the internal transfer brings the asset in, then a *separate* stake row moves it into the earning product.

---

## 2. Goals & non-goals

### Goals

1. **#29 resolved (CSV side).** OKX funding and trading are two `Accounts` rows. Internal funding↔trading transfers are paired (both legs in-portfolio), so non-stablecoin transfers no longer silently drop the position.
2. **Funding-History CSV import works.** A new parser handles every `Type` in the funding CSV and routes to the Funding account.
3. **Transfers are truly matched, not all-neutral.** `TRANSFER_DISPOSITION_ENABLED` flips to `True`; matched internal transfers carry basis cross-account (neutral); genuine external crypto flows realize; earn round-trips stay neutral.
4. **Funding balance reconciles.** Importing the funding CSV reproduces OKX's `After Balance` per coin (modulo explicitly-deferred edge cases).
5. **No historical-NAV regression.** Existing single-account data is preserved; the minimal backfill renames the account and creates an empty Funding account without rewriting transactions.

### Non-goals (deferred to sub-project 5b or later)

| Item | Deferred to |
|---|---|
| API sub-account tagging by endpoint + `/api/v5/asset/bills` fetch for internal transfers via live API | 5b |
| Full backfill: re-routing legacy API-imported funding-side rows to the Funding account | 5b |
| Mark-to-market-at-deposit for external crypto deposits (cost basis = spot at deposit time) | Later — 5a uses zero-basis lots for external crypto (existing machinery default); documented approximation |
| An explicit `Accounts.account_type` field | Later — only needed if API automation requires it; `native_id` disambiguates for now |
| Frontend account-management UI for the two accounts | Out of scope — accounts are created via the backfill command or existing account CRUD |

---

## 3. Data model

**No `Assets` / `Transactions` schema change.** The foundation already provides every field this design needs.

- **Two `Accounts` rows per OKX broker** (`common/models.py`, `Accounts`): `native_id ∈ {"trading", "funding"}`, `name = "OKX Trading" / "OKX Funding"`. The model already supports many accounts per broker (`unique_together = ["broker", "native_id"]`).
- **Pairing signal = `import_group_id`** (existing field, `models.py:293`). Both legs of an internal transfer carry the same synthesized group id (§5). This is exactly the key the existing `_transfer_is_matched` / `allocate_group_carry` machinery already keys on — no new `from_account`/`to_account` FK is introduced.
- **Event-discriminator signal = `import_event_type`** (existing field, `models.py:294`). Funding rows are tagged with well-defined tokens (§4) that the neutrality predicate reads.
- **Provider namespace** unchanged: CSV rows use `import_provider = "okx_csv"` (`OKX_CSV_IMPORT_PROVIDER`, `importer.py:615`); the funding parser uses a distinct `import_event_id` prefix (`csv_fund:`) so funding and trading CSV imports dedup independently.

---

## 4. Architecture

### 4.1 Funding-History CSV parser — `parse_okx_funding_csv`

A new async generator in `services/importer.py`, parallel to `parse_okx_trading_csv`. Responsibilities:

1. Read the CSV (skip the `UID:…,Account Type:…,Time Zone:UTC+3` metadata line; strip the BOM from every column name — already done by `_strip_okx_bom`).
2. Parse `Time` (`YYYY-MM-DD HH:MM:SS`, UTC+3 per header) → UTC ms-epoch (same conversion the trading parser uses).
3. Dispatch on the `Type` column per the mapping table (§4.2), building `CryptoExchangeEvent`s.
4. Persist via the existing `persist_crypto_exchange_event` (`services/crypto_exchange.py:360`), pinned to the user-selected **Funding** account.
5. Dedup on `(investor, account, import_provider="okx_csv", import_account_id, import_event_id="csv_fund:{id}")`.

The view layer (`transactions/views.py`, OKX branch) routes to `parse_okx_funding_csv` when the CSV header is the funding schema (detect: `Before Balance`/`After Balance` columns present, `Trade Type` absent). This auto-detection means the user does not have to tell the app which CSV type they are uploading — the existing upload modal and account selection are reused as-is.

### 4.2 Funding `Type` → event mapping

The parser maps each funding `Type` to a `CryptoExchangeEvent` with a `category`/`raw_type`/`group_id`, which `persist_crypto_exchange_event` + `_transaction_type_for_event` (`crypto_exchange.py:312-329`) and `_is_stablecoin_cash_leg` (`crypto_exchange.py:332-347`) turn into the final `Transaction.type`. The `import_event_type` token drives the neutrality discriminator (§6).

| Funding `Type` | leg category | leg asset | → `Transaction.type` | `import_event_type` | group_id | Disposition |
|---|---|---|---|---|---|---|
| `From unified trading account` | `transfer` | crypto (BTC/TRUMP/…) | `Crypto transfer in` | `okx_internal_transfer` | **synthesized** (§5) | matched-neutral |
| `From unified trading account` | `transfer` | stablecoin | `Cash in` | `okx_internal_transfer` | synthesized | net-zero cash |
| `To unified trading account` | `transfer` | crypto | `Crypto transfer out` | `okx_internal_transfer` | **synthesized** | matched-neutral |
| `To unified trading account` | `transfer` | stablecoin | `Cash out` | `okx_internal_transfer` | synthesized | net-zero cash |
| `Stake` / `Simple Earn subscription` | `transfer` | any | `Crypto transfer out` (crypto) / `Cash out` (stablecoin) | `okx_earn_subscription` | none | **always-neutral** (exempt) |
| `Simple Earn redemption` / `Unstake` | `transfer` | any | `Crypto transfer in` (crypto) / `Cash in` (stablecoin) | `okx_earn_redemption` | none | **always-neutral** (exempt) |
| `Deposit yield` | `reward` | any | `Crypto reward` (crypto) / `Interest income` (stablecoin) | `okx_earn_yield` | none | income (existing path) |
| `Deposit` (external) | `deposit` | stablecoin | `Cash in` | `okx_external_deposit` | none | cash in |
| `Deposit` (external) | `deposit` | crypto | `Crypto transfer in` | `okx_external_deposit` | none | **flag-eligible** (zero-basis lot) |
| `Place an order` / `Cancel an order` / `Fulfill an order` (C2C) | by sign | stablecoin | `Cash out` (Amount<0) / `Cash in` (Amount>0) | `okx_c2c_order` | none | sign-based cash |

**Rationale for the earn treatment (always-neutral):** Simple-Earn subscribe/redeem and stake/unstake move funds between the funding available balance and an earning product. They are not naturally paired by amount (partial redemptions), so under a naïve flag-flip the **crypto** legs would be wrongly treated as dispositions. Economically the round-trip nets to zero and only the `Deposit yield` is income — so the correct model is: exempt the crypto principal moves from disposition, recognize only the yield. (Stablecoin earn rows map to `Cash out`/`Cash in`, which already net to zero at the portfolio level — they need no discriminator; the §6 exemption applies only to crypto-transfer-typed earn rows.) This avoids modeling a third "OKX Earn" pseudo-account (considered, rejected as over-engineering for 5a).

**Rationale for C2C sign-based cash:** `Place an order` locks stablecoin (available balance drops); `Cancel an order` returns it; a fulfilled order finalizes the sale. Treating each row as `Cash in/out` by sign makes the funding cash balance track OKX's `After Balance` at every step. The place/cancel round-trip nets to zero cash. Documented as an approximation (a lock is modeled as a cash flow), accepted for reconciliation fidelity.

### 4.3 Internal-transfer pairing (the core mechanism)

Both the funding parser (for `From/To unified trading account`) **and** the existing trading parser (for `Trade Type=Transfer`) stamp the **same deterministic synthetic `import_group_id`**:

```
group_id = f"okx_xfer:{ccy_lower}:{canonical_amount}:{epoch_second}"
```

where `canonical_amount = str(Decimal(str(abs(amount))).normalize())` and `epoch_second` is the integer Unix second of the transfer. Because OKX records both legs of an internal transfer at the same instant and both CSVs are exported in UTC+3, both legs compute the identical key with **zero cross-file coordination**. The existing `_transfer_is_matched` (`services/realized.py:209-250`) then returns `True` for both legs → the realized walker keeps them neutral, and `allocate_group_carry` + `lookup_group_transfer_basis` carry basis from the funding OUT to the trading IN.

The required change to the trading parser is small: in `build_okx_csv_events`'s `Transfer` branch (`importer.py:858-879`), set the payload's `group_id` to the synthesized key instead of the raw billId (the billId moves into `provider_event_id`, preserving dedup). Stablecoin transfers still reroute to `Cash in/out` and need no group_id.

Collision guard: two same-ccy/amount internal transfers within the same second would collide. This is negligible in practice; if it occurs, the legs still resolve **neutral** (worst case: two true transfers merge into one matched group with pro-rata basis). No correctness risk — only a theoretical loss of per-transfer granularity.

Timestamp-skew fallback: if real data shows the two legs differ by a few seconds (verified during testing), widen the key to a per-minute bucket (`epoch_minute`) plus amount. Per-second is the default; the plan includes a verification step against the user's data.

### 4.4 Realized-engine changes

Two surgical edits activate the machinery:

1. **Neutrality discriminator** — applied at the realized walker's fall-through gate (`services/realized.py:964-980`). Add a predicate `is_unconditionally_neutral_transfer(transaction)` that returns `True` for crypto-transfer rows tagged with an earn `import_event_type` (`okx_earn_subscription`, `okx_earn_redemption`). The gate becomes: *"if the transfer is unconditionally-neutral, OR it is a (conditionally-neutral) transfer that is matched (or the flag is off), take the neutral branch; otherwise fall through to disposition."* Effect: earn-tagged crypto legs never fall through, regardless of `TRANSFER_DISPOSITION_ENABLED`; internal-transfer rows (`okx_internal_transfer`) remain governed by the flag and `_transfer_is_matched`. (The existing `is_neutral_transfer_transaction` in `services/transactions.py:113-118` already returns `True` for both crypto-transfer types, so it alone cannot express this — the new predicate is the discriminator.)
2. **Flag flip** (`services/realized.py:104`). Set `TRANSFER_DISPOSITION_ENABLED = True`. With pairing + earn-exemption in place, the only transfers subject to disposition are genuine external crypto flows — exactly #29's intent.

### 4.5 Cross-account basis carry — integration risk

`get_economic_basis` carries basis through an in-memory `carried_basis_by_group` populated **within a single replay**. A funding `OUT` and trading `IN` live on **different accounts**. Two carry paths exist:

- **In-memory carry** — works only if the realized walker replays both accounts in one pass (so the OUT precedes the IN in the same `carried_basis_by_group`).
- **Recursive fallback** — `lookup_group_transfer_basis` (`realized.py:704-794`) re-replays the source account's history; it must **span accounts** (query by `investor` + `import_group_id` + `import_provider`, not restricted to a single account) to recover the funding-side basis when the trading account's basis is computed in isolation.

**This is the single highest-risk integration point.** The implementation plan must: (a) determine how `realized_gain_loss` is invoked — per-account or portfolio-wide (it already accepts an `account_ids` set); (b) ensure that when computed per-account, the recursive lookup spans accounts; (c) add a regression test asserting basis on the trading account equals basis on the funding account after a matched transfer, for the both-orders (funding-imported-first and trading-imported-first) cases.

### 4.6 Backfill — management command

`python manage.py migrate_okx_two_account <broker_name>` (idempotent):

1. Find the broker's existing (single) OKX account. Rename it → `OKX Trading`, set `native_id = "trading"` if blank.
2. `get_or_create` an `OKX Funding` account (`native_id = "funding"`).
3. **Touch no transactions.** Historical rows stay on the renamed Trading account — they are predominantly trading data, so historical NAV is unchanged.
4. Print a summary of actions taken.

Known imperfection (deferred to 5b): legacy API-imported funding-side rows (external deposits via `/asset/deposit-history`) currently sit on the single account and will be on "Trading" after rename. They are external Cash-in / Crypto-transfer-in rows that do not break NAV; full re-routing is a 5b concern.

### 4.7 Frontend

Minimal. The existing upload modal already selects an account; the user imports the funding CSV with the Funding account selected and the trading CSV with the Trading account selected. The view-layer routing detects the funding schema by header inspection (§4.1) — no new UI, no new flags.

---

## 5. Transfer-pairing detail

### Synthesis (both parsers)

```python
def _okx_internal_transfer_group_id(ccy: str, amount, epoch_second: int) -> str:
    canonical = str(Decimal(str(abs(amount))).normalize())
    return f"okx_xfer:{ccy.lower()}:{canonical}:{epoch_second}"
```

- Both legs produce the same string ⇒ `_transfer_is_matched` returns `True` (same `import_group_id`, same `import_provider="okx_csv"`).
- The `allocate_group_carry` single-source guard (`len(source_keys) == 1`) passes: only the funding OUT contributes to the group, so its `(account_id, import_account_id)` is the sole source.
- Basis is reclaimed on the trading IN via `allocate_group_carry` (in-memory, if both replayed together) or `lookup_group_transfer_basis` (recursive, cross-account — §4.5).

### What stays neutral without pairing

Stablecoin internal transfers are `Cash out` (funding) + `Cash in` (trading) — net-zero cash at portfolio level with no basis-carry needed. They do not require a group_id.

---

## 6. Disposition discriminator detail

### Behavior matrix (after the flag flip)

| `import_event_type` | has group_id? | `_transfer_is_matched` | Result |
|---|---|---|---|
| `okx_internal_transfer` | yes | True | **neutral**, basis carries cross-account |
| `okx_earn_subscription` (OUT) | no | False | **neutral** (exempt — discriminator forces neutral) |
| `okx_earn_redemption` (IN) | no | False | **neutral** (exempt) |
| `okx_external_deposit` (IN, crypto) | no | False | **disposition-eligible** — opens a zero-basis lot |
| (external withdrawal OUT, crypto, when present) | no | False | **disposition-eligible** — realizes vs avg basis |
| legacy untagged crypto transfer (pre-5a data) | no | False | disposition-eligible (existing fall-through) |

### Why external crypto stays disposition-eligible

From the portfolio's boundary, an external crypto deposit/withdrawal crosses the modeled perimeter: the IN acquires an asset (zero basis — known approximation, §2), the OUT disposes of it (realize vs avg basis). If the user later models the cold wallet as another account, those flows pair and become neutral — consistent with the matched/unmatched design.

---

## 7. NAV / calc-layer interaction

- **Portfolio NAV:** unchanged in shape. Matched internal transfers are position-neutral and cash-neutral at the portfolio level (crypto OUT on funding cancels crypto IN on trading; cash OUT cancels cash IN). `nav.py:599-609` already treats `Crypto transfer in/out` as cf=0 for IRR.
- **Account-level NAV:** now meaningful and distinct per account — funding shows the staked/earning balance + yield; trading shows the trade fills + options.
- **Realized gain/loss:** with the flag ON and the discriminator in place, only genuinely external crypto flows realize. The cross-account basis carry (§4.5) preserves cost basis across the funding→trading move so no spurious gain/loss fires on internal transfers.

---

## 8. Testing

### Unit
- **Funding parser mapping:** feed one row per `Type` → assert the resulting `CryptoExchangeEvent` category / `group_id` / `import_event_type` per the §4.2 table.
- **Group-id synthesis:** `_okx_internal_transfer_group_id` is deterministic and equal for `+x`/`−x` of the same ccy/second; canonical-amount normalization collapses trailing zeros.
- **Neutrality discriminator:** `okx_earn_*`-tagged rows are neutral regardless of `TRANSFER_DISPOSITION_ENABLED`; `okx_internal_transfer` rows respect the flag and `_transfer_is_matched`.

### Integration
- **Pairing across CSVs:** import a funding "From unified" row and a trading "Transfer out" row (same ccy/amount/second) on their respective accounts → both legs carry the same `import_group_id`; `_transfer_is_matched` True for both; the trading account's economic basis equals the funding account's pre-transfer basis.
- **Cross-account carry, both import orders:** repeat with trading imported first, then funding — assert basis still carries (exercises the recursive fallback, §4.5).
- **Earn exemption with flag ON:** a `Simple Earn subscription` (crypto OUT) does **not** realize; a subsequent `redemption` (IN) does not add spurious basis; only `Deposit yield` flows to realized income.
- **Real funding-CSV fixture:** import the attached file into a Funding account → reconcile per-coin `After Balance` against the CSV (modulo C2C approximation); assert BABY/USDT `Deposit yield` totals post as income; assert BTC/TRUMP internal moves pair with synthetic groups.
- **Dedup:** re-importing the funding CSV creates zero new transactions.

### Regression
- All 1217 existing tests pass.
- A snapshot/fixture of historical NAV before the backfill command matches after (the command touches no transactions).
- The flag flip does not alter results for the existing transfer test fixtures (those legs are either matched or earn-tagged).

---

## 9. Open questions / follow-ups

1. **Timestamp alignment (verify in plan).** Confirm the funding CSV's `From/To unified trading account` second equals the trading CSV's `Transfer in/out` second on the user's real pair. If skew exists, widen the group-id bucket to per-minute.
2. **Realized-walker account scope (resolve in plan, §4.5).** Determine whether `realized_gain_loss` is invoked portfolio-wide or per-account, and ensure the recursive basis lookup spans accounts.
3. **External-crypto zero-basis deposit (5a approximation).** Accept zero basis for external crypto deposits now; mark-to-market-at-deposit is a later enhancement.
4. **5b scope (separate spec).** API endpoint→account tagging; `/api/v5/asset/bills` fetch; full backfill re-routing of legacy API-imported funding rows.

---

## 10. Implementation order (sketch — to be refined by writing-plans)

1. `_okx_internal_transfer_group_id` helper + unit tests.
2. Trading-parser change: synthesized group_id on Transfer rows.
3. Funding-History CSV parser (`parse_okx_funding_csv`) + mapping-table unit tests.
4. View-layer routing (funding-schema detection).
5. Neutrality discriminator in `transactions.py`.
6. Cross-account basis-carry verification + adjustment in `realized.py`.
7. Flag flip (`TRANSFER_DISPOSITION_ENABLED = True`).
8. Backfill management command.
9. Integration + regression tests (including the real funding-CSV fixture).
10. Flip is the last, gated step — the PR does not merge until steps 1–9 are green.
