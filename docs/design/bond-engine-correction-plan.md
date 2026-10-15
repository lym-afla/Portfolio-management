# Bond engine correction plan — PROTECTED CODE, NOT IMPLEMENTED

Status: **plan for review only**. This document proposes corrections to
protected financial calculations identified by the Phase D statement
reduction (`docs/design/dashboard-statement-d-evidence.md`, review round 3).
Nothing here is implemented on `codex/dashboard-reconciled-statement-d`; the
statement's guard (reason `bond_notional_fallback_unconverted`) keeps the
affected cases uncertified until a correction PR is merged. Any implementation
requires its own needs-approval PR touching protected code, with the
regressions below as acceptance.

## Defect 1 — currency-consistent unrealized bond price/FX decomposition

**Location.** `services/realized.py`, `unrealized_gain_loss`, bond branch:

```
price_appreciation = notional_lcl x (price_lcl - buy_in_lcl) x pos x fx_eop / 100     # correct
unrealized         = notional_lcl x (price_target - buy_in_target) x pos / 100        # DEFECT
fx_effect          = unrealized - price_appreciation                                  # inherits
```

**Defect.** `notional_lcl` is the bond's nominal-currency notional
(`get_effective_notional` without a currency argument resolves to the
nominal currency, fx = 1), but `price_target`/`buy_in_target` are
target-currency figures (and the two target prices are themselves
inconsistent: the price is NOT fx-converted for bonds while the buy-in IS
converted by entry-date FX). The product is neither local nor target
currency; whenever nominal ≠ reporting currency the "FX effect" is
approximately the RUB par of the position presented as reporting currency
(real data: +$421,815 fxSecurity against a $136k NAV).

**Correction (proposed).** Compute the decomposition from consistently
scaled quantities:

```
price_appreciation = notional_conv_eop x (price_lcl - buy_in_lcl) x pos x fx_eop / 100
unrealized_total   = value_target - basis_target
fx_effect          = unrealized_total - price_appreciation
```

with `notional_conv_eop = get_effective_notional(..., currency=target)` (the
converted notional already available) and `basis_target = notional_entry_conv
x buy_in_lcl x pos / 100` — i.e. both the value and the basis converted with
the SAME convention (basis at entry-date FX via the converted buy-in, value
at EOP FX), so `fx_effect` collapses to `basis x (fx_eop - fx_entry)`, the
par-value rate drift.

**Expected numeric results** (sanitized regression dataset: 10 RUB bonds,
par 1,000, bought 95% = 9,500 RUB at RUB→USD 0.0100; price 100, RUB→USD
0.0125 at the effective date):

| Quantity | Expected |
|---|---|
| Bond value (target) | 10,000 RUB × 0.0125 = **125.00** |
| Basis (target) | 9,500 RUB × 0.01 = **95.00** |
| Unrealized total | **30.00** |
| Unrealized price | 1,000 × 5 × 10 × 0.0125 / 100 = **6.25** |
| Unrealized FX | 9,500 × 0.0025 = **23.75** |
| Statement outcome | control 56.25 = 6.25 + 23.75 + cash FX 26.25 → reconciled |

Current (defective) values pinned by
`test_rub_bond_nonamortizing_unrealized_fx_is_dimensionally_broken`:
fx_security 9,898.75, unreconciled −9,875.

## Defect 2 — currency conversion in the transactions-fallback notional path

**Location.** `services/bonds.py get_current_notional`, final fallback:

```
current_notional = initial_notional - abs(total_redeemed)
return current_notional          # DEFECT: missing * fx_rate
```

**Defect.** The other two branches (non-amortizing; NotionalHistory) return
`notional * fx_rate`, but the redemption-aggregate fallback returns the
nominal-currency notional unconverted. An amortizing bond without
NotionalHistory on/before the valuation date is valued at RUB-par as if it
were reporting currency (sanitized: NAV $10,131.25 for a $256 portfolio).
Because the inflated value flows into both the value term and (via
Defect 1's bracket) the basis term, the two errors can CANCEL, and the
statement's identity closes falsely (`test_rub_bond_fallback_notional_currency_error_falsely_reconciles`,
now split into an engine characterization plus the read-model guard
`test_rub_bond_fallback_notional_stays_uncertified_in_statement`).

**Correction (proposed).** `return current_notional * fx_rate` — one token,
matching the two sibling branches.

**Expected numeric results** (same dataset, amortizing, no NotionalHistory):
`get_effective_notional(..., "USD")` → 1,000 × 0.0125 = **12.50** (currently
1,000); bond value **125.00** (currently 10,000); NAV **256.25** (currently
10,131.25); with Defect 1 also corrected the statement reconciles at
**56.25** (currently falsely reconciled at 10,131.25-scale).

## Required coverage for the correction PR

Matrix (each cell = its own hand-derived Decimal expectations, computed
BEFORE implementation):

- Bond kinds: non-amortizing; amortizing **without** NotionalHistory
  (fallback branch); amortizing **with** NotionalHistory (history branch).
- Events: buy-and-hold; partial redemption (par reduction + cash);
  full redemption at par; coupon income.
- Currencies: same currency (nominal = reporting; decomposition must be
  unchanged — zero-diff guard); foreign nominal (the correction's target);
  historical valuation date whose FX differs from the effective date
  (fx drift sign both ways).
- Scopes: single account; multi-account with
  account isolation asserted (`get_effective_notional` account filtering
  must not leak another account's redemption aggregate).
- Cross-consumer integration on a sanitized fixture database: corrected
  values must agree across (a) `NAV_at_date`/dashboard NAV and the
  statement's NAV row, (b) the statement decomposition (unrealized
  price/FX, control total, reconciled), (c) open/closed positions
  valuation and `calculate_value_at_date`, and (d) any AnnualPerformance
  regeneration path — one shared sanitized dataset, asserted with the same
  independent Decimal expectations (NAV 256.25, net result 56.25, security
  FX 23.75 for the example above).

The Phase D statement guard (`bond_notional_fallback_unconverted`) is to be
retired in the same PR — after the correction the fallback branch converts,
so the guard's condition becomes unreachable; its regression flips to
asserting the corrected reconciled outcome.

## Explicit non-goals of this plan

- No changes to average buy-in (`calculate_buy_in_price`), to realized
  gain/loss pairing, or to FX graph resolution.
- No re-derivation of bond price conventions (percentage-of-par stays).
- No statement-side workaround: the read model's guard remains the only
  mitigation until this plan is implemented and reviewed.
