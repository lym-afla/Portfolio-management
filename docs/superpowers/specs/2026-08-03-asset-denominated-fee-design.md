# Asset-Denominated Commission Fee — Design

**Date:** 2026-08-03
**Status:** In design (brainstorming complete, awaiting plan)
**Issues:** #28 (gross position), #30 (commission currency dimension + fee-folding)
**Branch (planned):** `fix/asset-denominated-fee`

## Problem

A crypto spot trade can carry a fee denominated in the **base asset** (e.g. a BTC fee on a BTC-USDT buy). The current code converts that fee into the quote currency and folds it into `cash_flow`, which produces two errors:

1. **Wrong cash_flow.** The USDT cash_flow is inflated by the fee's USD value. For a BTC-USDT buy of `0.001 @ 96058` with fee `-0.00000012 BTC`, the code computes `cash_flow = -(0.001×96058 + 0.00000012×96058) = -96.0695 USDT`. But only `96.058 USDT` actually left the account — the fee was paid in BTC, not USDT.
2. **Wrong position.** The persisted base `quantity` is gross (`+0.001`), so the BTC balance never reflects the fee. The real holding is `0.001 − 0.00000012 = 0.00099988 BTC`.

A secondary problem: `Transactions.commission` is a bare `Decimal` with no currency dimension. The fee asset survives only inside the free-text `comment` field, so the frontend cannot display `|| Fee: BTC0.000000012` (it shows only the number).

## Verified fee-basis patterns (from the user's actual CSV)

The CSV's `Fee Unit` column shows the fee currency. Across the user's 9 spot orders:

| Fee basis | Orders | Example | Current handling |
|---|---|---|---|
| Base asset (BTC/TRUMP/USDC) | 6 | `BTC-USDT Buy, Fee=-0.00005379 BTC` → `BalChg=0.05373703` | **BUG** — converted to quote, folded into cash_flow |
| Quote asset (USDT) | 1 | `TRUMP-USDT Sell, Fee=-0.01125545 USDT` → `BalChg=11.24419315` | Correct — netted into cash_flow |
| Third asset (e.g. BNB) | 0 | — | Silently dropped (pre-existing, no cases) |
| No fee | 2 | — | Unaffected |

Key data invariant: for a base-fee leg, `Balance Change = Amount − |fee|` exactly (e.g. `0.05379082 − 0.00005379 = 0.05373703`). The quote-fee case is already correct and unchanged by this design.

## Approach — net the fee into the base quantity at write time

At import/persist time, for the **base-asset-fee** sub-case only, net the fee into the base leg's `quantity` and leave `cash_flow` as the pure trade value. This makes the stored `quantity` reflect the real holding, so the calc layer's `Sum("quantity")` aggregates pick up the correction with **zero code changes** to `position()`, NAV, or realized-gains.

For a BTC-USDT buy of `0.001 @ 96058`, fee `-0.00000012 BTC`:

| Field | Today (buggy) | Fixed |
|---|---|---|
| `quantity` | `+0.001` (gross) | `+0.00099988` (net = `qty + fee_delta`) |
| `cash_flow` | `-96.0695` (value + fee-in-quote) | `-96.058` (pure `qty × price`) |
| `commission` | `-0.00000012` | `-0.00000012` (unchanged — display source) |
| `commission_currency` | *(none)* | `BTC` (new field) |

The asset side and cash side stay balanced: BTC down by the fee, USDT down by exactly the trade value.

### Why not the alternatives
- **Separate fee leg (negative-quantity row):** also zero calc changes, but doubles the transaction rows for fee'd trades and pollutes realized-gains lot tracking (the fee leg looks like a tiny disposal). Rejected.
- **`commission_currency` + change all calc consumers (`position()`, `_portfolio_at_date`, 3× realized.py quantity sums, 2× basis loops):** the "textbook correct" model but **6+ protected-calc changes that must stay in lockstep** or position/basis silently diverge. Violates the project's no-calc-layer-edits constraint. Rejected.

The chosen approach (net-at-write) is the smallest blast radius that produces correct numbers and leaves the protected calc layer untouched.

## Components

### Component 1: `_spot_legs` stablecoin branch — `services/crypto_exchange.py`
The only behavioral change. Split base-fee vs quote-fee handling:

- **`fee_asset == base`** (the bug): `base_quantity = qty + fee_delta` (fee_delta negative → nets); `cash_flow = -(qty × price)` (buy) / `+(qty × price)` (sell). No fee→quote conversion. Add `"fee_asset": fee_asset` to the leg dict.
- **`fee_asset == quote`**: unchanged — `cash_flow = ∓(value ± fee_in_quote)`, `quantity = qty` (gross). Add `"fee_asset": fee_asset` to the leg dict.
- **`fee_asset` is neither (third asset)**: unchanged — `fee_in_quote = 0`, fee dropped (0 cases in user data; deferred).
- **Zero fee**: both branches degenerate to no-fee behavior. `fee_asset` not added (or empty).

Rebate handling (`fee_delta > 0`): the `qty + fee_delta` math naturally increases the holding on a rebate — no special-casing.

The crypto-crypto two-leg branch of `_spot_legs` is **unchanged** (it already nets fees into the matching leg's quantity correctly).

### Component 2: Schema — `commission_currency` on `Transactions`
Add to `common/models.py`:
```python
commission_currency = models.CharField(
    max_length=4, choices=ALL_CURRENCY_CHOICES, null=True, blank=True
)
```
Mirrors `FXTransaction.commission_currency` (`common/models.py:437`). One additive migration (`AddField`, nullable). All existing rows get `NULL`; non-crypto transaction types are unaffected (the field stays null for them). Frontend treats `NULL` as "no currency shown" (falls back to current `|| Fee: {{ commission }}` display).

### Component 3: `persist_crypto_exchange_event` — `services/crypto_exchange.py`
Next to the existing commission write (lines ~462-465), also write `commission_currency` from `event.fee["asset"]` (or the leg's `fee_asset` key set by Component 1). ~2-line addition. Naming mapping: the leg dict key is `fee_asset` (set by `_spot_legs`); the persisted model field is `commission_currency` (mirroring `FXTransaction`). The persist step reads `leg.get("fee_asset") or event.fee.get("asset")` and writes it to `tx_kwargs["commission_currency"]`.

### Component 4: Frontend `CommissionDisplay.vue` + call sites
- `CommissionDisplay.vue`: add a `currency` prop; render ` || Fee: {{ currency }}{{ commission }}` when currency is present, else ` || Fee: {{ commission }}` (current behavior).
- `TransactionDescription.vue` call sites (lines 8-11 FX, 89-92 crypto, 115-118 regular): pass `:currency="transaction.commission_currency"`.
- `TransactionCashFlow.vue` already keys off `commission_currency` for FX rows — crypto rows now populate it too, so the third-currency-column logic extends naturally.

### Component 5: Verification — regression fixtures with expected numeric results
Per `AGENTS.md` (protected-logic changes require unit tests + regression fixtures). Concrete assertions:
- **Base-fee BTC-USDT buy** (`0.001 @ 96058`, fee `-0.00000012 BTC`): `quantity == 0.00099988`, `cash_flow == -96.058`, `commission == -0.00000012`, `commission_currency == "BTC"`.
- **Position proof:** after persisting that buy, `position(btc_asset, ...) == 0.00099988` (proves the calc layer picks up the netted quantity with zero calc changes).
- **Quote-fee TRUMP-USDT sell** (`0.6798 @ 16.557`, fee `-0.01125545 USDT`): `cash_flow == 11.24419315` (unchanged — regression guard for the quote branch).
- **Crypto-crypto trade** (e.g. ETH-BTC): unchanged (regression guard for the two-leg branch).

## Data flow

```
CSV (Fee, Fee Unit) → normalize_okx_spot_fill → event.fee{asset, quantity}
  → _spot_legs (stablecoin branch):
       base-fee:   quantity = qty + fee_delta        ← netted (NEW)
                   cash_flow = qty × price           ← pure (NEW)
                   leg["fee_asset"] = fee_asset      ← NEW
       quote-fee:  quantity = qty                    ← gross (unchanged)
                   cash_flow = value ± fee           ← net (unchanged)
                   leg["fee_asset"] = fee_asset      ← NEW
  → persist_crypto_exchange_event:
       quantity, cash_flow, commission, commission_currency (NEW) written
  → calc layer (position / total_cash_flow / basis): UNCHANGED — reads new values
  → frontend: CommissionDisplay shows commission_currency + commission
```

## Constraints honored

- **Decimal only** — all fee/quantity math is `Decimal` (the existing `_spot_legs` already enforces this).
- **Protected calc layer untouched** — `position()`, `_portfolio_at_date` (nav.py), `get_economic_basis`, `calculate_buy_in_price`, `total_cash_flow` crypto branch: **zero changes**. The netted quantity flows through their existing `Sum(quantity)` / `transaction.quantity` reads.
- **Schema change is additive** — one nullable `commission_currency` column; no backfill, no downtime.
- **Rounding** — `ROUND_HALF_UP`, ≥6 dp prices / ≥9 dp quantities (existing `_normalize_model_decimal` enforces this at persist).

## Edge cases

1. **Zero fee** — `fee_delta == 0`: both branches produce no-fee behavior; no `commission`/`commission_currency` written. Preserved.
2. **Fee rebate** (`fee_delta > 0`, `is_rebate=True`) — `qty + fee_delta` increases the holding on a base-asset rebate; `value ± fee_in_quote` increases cash on a quote-asset rebate. Handled by the arithmetic, no special-case.
3. **`fee_asset` empty/missing** — existing `else: fee_in_quote = Decimal("0")` fallback (no fee applied). Unchanged.

## Known limitations (deferred)

1. **Third-asset fees** (e.g. BNB fee on a BTC-USDT trade) — still silently dropped (`fee_in_quote = 0`, no quantity net). 0 cases in the user's CSV. Separate issue if it arises.
2. **Option-trade fees** — out of scope (different premium/collateral mechanic, issue #8 territory).
3. **Historical data** — existing crypto-trade rows (pre-this-design) keep gross `quantity` + inflated `cash_flow`. Re-import fixes them. A one-time backfill script is *possible* (parse `fee_asset`/`fee_quantity` from the `comment` field via the `_event_comment` format, recompute quantity/cash_flow) but is **not** part of this design; documented as an option.
4. **`digits` flow** — `consumers.py:1267,1286` hardcode `number_of_digits=2` instead of the user's `digits` setting. Separate minor issue, not this design.

## Testing strategy

- **Unit (persistence):** the regression fixtures above (Component 5) — assert exact `quantity`/`cash_flow`/`commission`/`commission_currency` values for base-fee, quote-fee, no-fee, and rebate cases.
- **Integration (position):** assert `position()` returns the netted quantity after a base-fee buy (proves calc-layer compatibility).
- **Adapter:** existing OKX/bybit normalizer tests stay green (the fee shape `{asset, quantity, is_rebate}` is unchanged; only `_spot_legs`'s consumption changes).
- **Existing suite:** the full backend suite must pass (the quantity/cash_flow value changes are scoped to crypto stablecoin-quote trades; no other transaction type is affected).

## Out of scope

- #29 (OKX funding + trading account model) — independent.
- The minor `digits`-flow fix.
- Backfill of historical rows.
