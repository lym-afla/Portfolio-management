# Crypto Option Accounting + Realized-Gain Engine — Design

**Date:** 2026-08-07
**Status:** Approved (brainstorming complete; pending implementation plan)
**Scope:** Option accounting for OKX/Bybit crypto options (calculated premium, realize-at-expiry, ITM intrinsic) + a corrected crypto transfer-neutrality engine that distinguishes neutral basis-carries from dispositions.
**Origin issues:** Resolves #33 (option SELL residual BTC — the program's original goal); fixes the realized-gain/IRR bugs surfaced during foundation testing (PR #38); partially addresses #29 symptom 1 (transfer symmetry).
**Predecessor:** `docs/superpowers/specs/2026-08-06-crypto-as-currency-foundation-design.md` (sub-projects 1 + 3, merged in PR #38). This spec is **sub-project 4** of the four-sub-project program defined there.

---

## 1. Problem

### Trigger

Issue #33 — an OKX option SELL leaves a residual BTC position (`+0.007019`) because the importer drops the fill's BTC balance change. The foundation spec (#1) deferred all option accounting here. Investigating the target model also surfaced a second, independent bug: the realized-gain engine treats **every** crypto transfer as neutral (`realized.py:752-755`), so one-sided transfers (cold-wallet withdrawals, moves to the un-modeled OKX funding account per #29) silently drop basis without realizing gain/loss — corrupting both realized P&L and IRR.

### Root cause — two independent gaps

**Gap A — Option economics are not modeled.** The OKX importer emits one leg per option fill: the contract itself, with the BTC balance change stuffed verbatim into `cash_flow`. The importer never computes a premium, never separates collateral, and `Option settlement` rows are unrecognized by the calc layer (they fall through every classifier). Result: the option position never closes cleanly, the BTC premium/collateral net is mis-attributed, and no realized P&L is recognized at expiry.

**Gap B — Transfer neutrality is unconditional.** `realized_gain_loss`'s walker treats `Crypto transfer in` and `Crypto transfer out` as uniformly neutral (position counter advances, no G/L). This is correct *only* for transfers whose basis is carried to a matching leg inside the portfolio. A transfer with no matching partner (BTC leaving the portfolio entirely) is economically a disposition and must realize.

### Why one spec covers both

Both gaps are symptoms of the same missing distinction: **is a quantity movement an internal book-value carry, or an external priced event?** The option collateral is a book-value carry (it should be neutral — but see §1.2 for why we omit it entirely rather than model it as a transfer); a cold-wallet withdrawal is a priced disposition. The realized-gain engine needs this distinction in one place, applied consistently to options and to ordinary crypto transfers. Splitting them across two specs would duplicate the neutrality logic and risk divergence.

### Verified economics (the user's real CSV)

Tracing `BTC-USD-260605-80000-C` in the user's OKX export confirms the OKX BTC-option **contract size = 0.01 BTC** (the spec's "÷100"):

- **2026-05-28 SELL:** `Amount=7` contracts, `Filled Price=0.0022` BTC, `Fee=−0.00001078` BTC, `Balance Change=−0.00701889` BTC, `PnL=0`.
- **2026-06-05 Expired OTM:** `Balance Change=+0.00716211` BTC, `Filled Price=62703.94` (underlying spot), `PnL=0.00015400` BTC.

Decomposition (settles in BTC, the underlying coin — read from the CSV's `Balance Unit`, never defaulted):

| Component | BTC | Derivation |
|---|---|---|
| Gross premium | `+0.000154` | `qty × fillPx × contract_size` = `7 × 0.0022 × 0.01` (= the settlement row's `PnL` column) |
| Fee | `−0.00001078` | CSV `Fee` |
| Collateral blocked | `0.00716211` | residual of `BC = +premium − collateral − fee` → `collateral = premium − fee − BC_signed` = `0.000154 − 0.00001078 − (−0.00701889)` = `0.00716211` |
| Net premium / realized profit | `+0.00014322` | `premium − fee` (collateral blocks then releases for the same amount across the cycle, so it cancels out of net profit) |

This confirms the foundation's target model. The sell's signed `Balance Change` decomposes into three components — premium received (in), collateral blocked (out), fee paid (out):

```
BC_sell = +premium − collateral − fee          ⟹  collateral = premium − fee − BC_sell
```

At OTM expiry the collateral is returned in full (`+0.00716211`), so across the cycle the collateral legs cancel and the net BTC movement equals the realized profit (`premium − fee = +0.00014322`).

---

## 2. Goals & non-goals

### Goals

1. **#33 resolved.** An option SELL produces a clean 2-row cycle whose net BTC = the realized profit (`+0.00014322`), not a residual.
2. **Option position opens and closes.** A written (SELL) option opens a short position on the Option asset; a bought (BUY) option opens a long. `Option settlement` closes it. The option asset appears briefly while open and nets to zero at expiry.
3. **Premium is calculated, not stuffed.** The importer computes `premium = qty × fillPx × contract_size` and stores it as the option row's `cash_flow`. The raw `Balance Change` is no longer used as `cash_flow`.
4. **Collateral is not tracked as a position movement.** Collateral stays implicitly inside the BTC (or ETH) position; the blocked amount is recorded in the transaction `comment` for audit. This avoids spurious NAV step-changes (the BTC never left the user's ownership).
5. **Realized P&L materializes at expiry.** OTM → terminal price 0 → writer keeps the full net premium. ITM → terminal price = intrinsic value (`max(spot−strike,0)` call / `max(strike−spot,0)` put) → writer pays the intrinsic. Both writer (short) and buyer (long) covered symmetrically.
6. **Open short option is NAV-neutral by default.** Marked at entry cost (premium received) → the BTC premium in the crypto bucket exactly offsets the option liability. Optional manual mark-to-market via a user-entered `Prices` row.
7. **Transfer engine distinguishes neutral from disposition.** Matched transfers (basis carried to an in-portfolio partner) stay neutral; unmatched one-sided transfers realize gain/loss (OUT) or add basis (IN). Fixes the realized-gain/IRR bug at its root.

### Non-goals (explicitly deferred)

| Item | Deferred to |
|---|---|
| #29 two-account model (OKX funding vs trading as separate `Accounts`) | Separate sub-project — orthogonal to option accounting; the transfer-engine fix here works regardless of account modeling |
| Automated option-price fetching (auto MTM) | Later — manual `Prices` entry covers MTM now |
| Physical option delivery | N/A — OKX/Bybit crypto options are European cash-settled |
| Greeks / advanced option analytics | Later spec |
| Frontend option-specific UI | Flagged for the implementation plan; backend serves data, frontend renders |
| Display-currency toggle (report crypto P&L in non-native currency) | Sub-project 2 (foundation spec) |

---

## 3. Data model

**No schema change to `Assets` or `Transactions`.** The foundation already established the required shape. The only `OptionMetadata` change is the *value* of an existing field.

### 3.1 `OptionMetadata.contract_size` — set correctly per coin (existing field)

The field exists (`common/models.py:704`, `DecimalField(max_digits=15, decimal_places=6)`). The importer currently hardcodes `Decimal("1")` (`crypto_exchange.py:152`). Sub-project 4 derives it from the underlying coin:

| Underlying | contract_size | Source |
|---|---|---|
| BTC | `0.01` | OKX BTC option contract = 0.01 BTC |
| ETH | `0.1` | OKX ETH option contract = 0.1 ETH |
| (other) | `1.0` | conservative default; logged warning |

Derived via `options.contract_size_for_underlying(coin_code)` (§4.1) — a data lookup, easy to extend.

**One-time backfill** (management command `python manage.py backfill_option_contract_sizes`, **not** a Django migration — it is a data fix, and AGENTS.md flags migrations as protected). Walks every `OptionMetadata` row whose `contract_size` is `1.0` or null, parses the underlying (from `Assets.name`, which is always populated as `{UNDERLYING}-{DDMMMYY}/{YYMMDD}-{STRIKE}-{C|P}`), and sets the correct size. Idempotent.

### 3.2 Transaction types — `OPTION_SETTLEMENT` already exists

The type `"Option settlement"` (`constants.py:81`) exists and the importer already emits it. **No new transaction type.** What is new: the calc layer *recognizes* it — it joins the disposal-equivalent bucket (closes the option position).

### 3.3 The 2-row model

The full written-call OTM cycle produces exactly **two** transaction rows. This mirrors how a stock sell already works — one row carries the security side (`quantity`, `price`), the cash side implicitly (`cash_flow`/`commission`); no separate cash leg.

**Entry (SELL fill):**

| field | value |
|---|---|
| `security` | Option asset `BTC-USD-260605-80000-C` |
| `type` | `Crypto trade out` (opens short) |
| `currency` | `BTC` (from CSV `Balance Unit` — never defaulted) |
| `quantity` | `−7` (contracts) |
| `price` | `0.0022` (real fill, BTC per contract) |
| `commission` / `commission_currency` | `−0.00001078` / `BTC` |
| `cash_flow` | `+0.000154` (= `7 × 0.0022 × 0.01`, gross premium — the engine applies `contract_size`) |
| `comment` | `"Collateral blocked: 0.00716211 BTC (not tracked — remains in BTC position)"` |

**Expiry (OTM):**

| field | value |
|---|---|
| `security` | same Option asset |
| `type` | `Option settlement` (closes the short) |
| `currency` | `BTC` |
| `quantity` | `+7` (closes the short to 0) |
| `price` | `0` (OTM terminal value) |
| `commission` | `0` |
| `cash_flow` | `0` (collateral return is a no-op — it never left) |
| `comment` | `"Expired OTM. Collateral 0.00716211 BTC released (not tracked)."` |

A long (BUY) option mirrors: entry is `Crypto trade in` with `cash_flow = −premium` (premium paid); expiry settles at intrinsic (OTM → 0, lose premium; ITM → gain `intrinsic − premium`).

### 3.4 NAV walk — smooth, no collateral wobble

Using the default mark = entry cost (`fillPx`) while open:

| Event | BTC crypto bucket | Option liability | ΔNAV |
|---|---|---|---|
| Entry | `+0.00014322` (net premium in) | `−0.000154` (at fillPx mark) | `−0.00001078` (the real fee) |
| (open) | — | `−0.000154` | flat |
| Expiry OTM | `0` | `0` (closed at price 0) | `+0.000154` (liability released) |
| **Total** | `+0.00014322` | `0` | **`+0.00014322`** = net profit ✓ |

The collateral `±0.00716211` wobble is gone. The only NAV movements are real economic events: the fee at entry, the realized profit at expiry.

### 3.5 BTC crypto-bucket aggregation (comprehensive)

`btc_value` draws from **every** BTC-denominated movement regardless of source:

```
btc_value = (btc_position_qty + routed_premium_qty) × btc_price
```

| Source | How it enters the BTC bucket | Owner |
|---|---|---|
| Spot BTC trades (`Crypto trade in/out`) | `position(BTC)` via `quantity` | existing |
| BTC transfers in/out | `position(BTC)` via `quantity` | existing |
| **BTC fees from ANY trade** (spot, option, any future BTC commission) | `position(BTC)` via the commission row's `commission` quantity | foundation's commission model (open-Q #2) |
| **BTC option premium** | `routed_premium_qty` — the `cash_flow` of option rows whose `currency=BTC` | **NEW (this spec)** |

The mirror holds for any collateral/premium coin (ETH option → ETH bucket): for each crypto coin C, the bucket aggregates `position(C) × price` plus the `cash_flow` of option rows denominated in C. BTC fees from non-option trades are included *by construction* through `position(BTC)` — no special-casing.

---

## 4. Architecture — `services/options.py`

A new module mirrors the foundation's `services/crypto.py`: pure helpers, `Decimal` throughout, unit-testable in isolation. The importer and calc layer both consume it; neither owns option economics inline.

```python
# services/options.py (sketch — final shape in the implementation plan)

OKX_CONTRACT_SIZES = {"BTC": Decimal("0.01"), "ETH": Decimal("0.1")}

def contract_size_for_underlying(coin_code: str) -> Decimal:
    """OKX option contract size by underlying. Default 1.0 (warned)."""

def gross_premium(quantity, fill_price, contract_size) -> Decimal:
    """Premium = qty × fillPx × contract_size. BTC example: 7 × 0.0022 × 0.01 = 0.000154."""

def intrinsic_price(option_meta, spot: Decimal, contract_size: Decimal) -> Decimal:
    """Per-contract intrinsic value at expiry, in the settlement currency.
    For USD-strike / coin-settled options (OKX/Bybit crypto style):
      call = contract_size × max(spot − strike, 0) / spot
      put  = contract_size × max(strike − spot, 0) / spot
    (contract_size scales one contract to its coin notional; /spot converts USD→coin.)"""

def option_mark_for_nav(option_asset, date, investor):
    """NAV mark: manual Prices row if present, else None (caller falls back to entry cost)."""

def is_option_asset(asset) -> bool:
    return asset.type == ASSET_TYPE_OPTION

def decompose_option_fill(payload) -> dict:
    """Central decomposer called by OKX and Bybit normalizers.
    Returns: {quantity, fill_price, premium, fee, fee_ccy, currency, underlying, collateral}.
    The normalizer maps this into a single option leg."""
```

**Why a dedicated module** (vs. inline importer logic): matches the foundation's `crypto.py` pattern; centralizes the Decimal-sensitive premium/intrinsic math in one unit-testable place; keeps the protected calc layer's invariants generic. The importer becomes a *consumer* of `options.decompose_option_fill`, not the owner of option economics.

---

## 5. Calc-layer changes

### 5.1 Classifiers (`services/transactions.py:89-109`)

Add `OPTION_SETTLEMENT` to the disposal bucket:

```python
def _transactions_is_disposal_transaction(transaction):
    return transaction.type in {SELL, CRYPTO_TRADE_OUT, OPTION_SETTLEMENT}
```

`Crypto trade in` already covers option BUY (paid entry). No new entry-side classifier.

### 5.2 `get_economic_basis` (`realized.py:425-500`) — apply `contract_size`

The replay already does average-cost basis; option legs already feed it as `Crypto trade in/out`. The only change: on a paid-entry (option BUY) iteration, multiply by `contract_size`:

```
basis += quantity × price × contract_size(asset) × fx_rate
```

For the canonical example: `7 × 0.0022 × 0.01 = 0.000154` BTC basis per-contract-received.

**Long-only invariant preserved.** `get_economic_basis` is long-only (resets basis to 0 when position goes ≤ 0, `realized.py:464-468`). A written option opens a **short**, so its premium is *not* tracked in `get_economic_basis`. The writer's premium basis is handled in `realized_gain_loss`'s short-close branch (§5.3), read directly from the opening SELL row's `cash_flow`. This keeps `get_economic_basis` minimal and avoids destabilizing the long-only invariant.

### 5.3 `realized_gain_loss` walker (`realized.py:626-941`) — option branches

**Option short open (SELL on an Option asset):** opens a short. No realized G/L yet. The opening row's `cash_flow` (= `qty × fillPx × contract_size`, gross premium) is the premium received — recorded for the close to find.

**Option short close (`Option settlement`):**
- Find the matching opening short (most recent open-short lot on this Option asset; average-cost across multiple writes is consistent with the existing model).
- `closing_proceeds = closing_qty × closing_price × contract_size`. OTM → `closing_price = 0` → proceeds `0`. ITM → `closing_price = intrinsic = options.intrinsic_price(meta, spot, contract_size)` (in settlement coin per contract), where `spot` = the settlement row's `price` (the underlying USD price at expiry, already stored by the importer). The `× contract_size` in `closing_proceeds` is then absorbed (intrinsic already includes it); equivalently, `closing_proceeds = closing_qty × intrinsic(meta, spot, size)`. The implementation normalizes so `contract_size` is applied exactly once.
- `realized_g_l = closing_proceeds − premium_received − fees` (sign-flipped for the short side).
- OTM example: `0 − 0.000154 − 0.00001078 = −0.00016478` from the option's own P&L sign, which inverts to **`+0.00014322`** realized for the writer (premium kept, no payout). ✓

**Long option close (`Option settlement` for a held long):** mirror. Buyer paid `−premium` at open; receives `intrinsic × qty × size` at close. OTM → receives 0 → realizes `−premium` (loss of premium). ITM → receives intrinsic → realizes `intrinsic − premium`.

### 5.4 NAV valuation — the short-option liability

Per the chosen mark policy (decision 3): **entry cost (premium) by default; optional manual MTM via a `Prices` row.**

```
option_mark = options.option_mark_for_nav(option_asset, date)   # Prices row if present
if option_mark is None:
    option_mark = entry_cost_basis_per_contract                 # premium received (short) / paid (long)
option_value = position(option, date) × option_mark             # negative qty short → negative (liability)
```

- **No `Prices` row** → mark = entry cost → short option value = `−qty × fillPx` = exactly the premium → opening is NAV-neutral (premium in BTC bucket = liability out). ✓
- **`Prices` row present** (user manually entered an option mark) → NAV marks to that price → on-demand MTM. No auto-fetch.
- **At expiry OTM** → the closing `Option settlement` row zeroes the position → `option_value = 0` → the liability disappears → the held-back premium emerges as realized gain. ✓

The short-option liability appears in the **Securities** breakdown (Option asset is `type="Option"`), valued negative. The premium BTC sits in the **Crypto** breakdown (§3.5). NAV total is unaffected by the split.

### 5.5 Transfer-neutrality fix (`realized.py:752-755`)

Today: every `Crypto transfer in/out` is neutral (position += qty, no G/L). The fix uses the existing group-carry mechanism's discriminator (`allocate_group_carry`, `realized.py:379-396`, which already returns 0 when a group spans multiple source accounts — line 386) and makes it explicit:

| Transfer scenario | `import_group_id` | Group-carry result | Realized treatment |
|---|---|---|---|
| **Matched** (both legs in portfolio: collateral out/in once #29 lands; future inter-account moves) | shared | basis carried | **Neutral** (today's behavior) |
| **Unmatched OUT** (no matching IN in portfolio: cold-wallet withdrawal, move to un-modeled funding account) | none / unpaired | basis *not* carried | **Disposition** — realize gain/loss at average cost |
| **Unmatched IN** (deposit from external source) | none / unpaired | no basis to carry | **Cost-basis event** at the transfer's price (or FMV) — adds basis, no G/L |

In `realized_gain_loss`, replace the blanket-neutral branch:

```python
if _transactions_is_neutral_transfer_transaction(transaction):
    if _transfer_is_matched(transaction):        # has a group_carry partner in-portfolio
        position += transaction.quantity
        continue                                 # neutral (today's behavior)
    else:
        # Unmatched transfer — treat as priced disposition (OUT) or basis event (IN)
        # falls through to the disposal/entry branches below
```

`_transfer_is_matched(tx)` checks whether a transfer-IN partner exists for this transfer-OUT (and vice versa) within the same `import_group_id` and within the portfolio's account set. The unmatched-OUT flows into the existing disposal branch (`realized.py:757-770`) → computes G/L at average cost → fixes the IRR bug. The unmatched-IN flows into the paid-entry branch → adds basis.

**Backward compatibility:** existing matched transfers (shared `import_group_id`, single source account) keep working identically. Only unmatched transfers change behavior — and for those, the old "neutral" behavior dropped basis silently, so the change is a strict improvement.

**IRR alignment:** `nav.py:_calculate_cash_flow` includes `CRYPTO_TRANSFER_IN/OUT` in the portfolio-level external-flow filter (`nav.py:370-378`). Post-fix, an unmatched OUT becomes an economic outflow, consistent with the realized G/L it now generates. Matched transfers stay excluded (correctly — internal).

### 5.6 Prerequisite — foundation open-Q #2

Section 5.2's basis math and §3.5's BTC fee aggregation rely on **commission rows depleting the fee-asset position** (a BTC fee reduces `position(BTC)`). Foundation open-Q #2 (`docs/.../crypto-as-currency-foundation-design.md` §9.2) flags that `services/positions.py` must read `commission` as a quantity-equivalent for commission-type rows. If absent, the BTC option fee won't reduce the BTC position and NAV won't reconcile. **This is a hard dependency.** The implementation plan's first phase adds a regression test asserting it.

---

## 6. Importer changes

### 6.1 `resolve_crypto_option_asset` — set `contract_size`

Change the hardcoded `Decimal("1")` to derive from the underlying:

```python
contract_size=options.contract_size_for_underlying(parsed.underlying)
```

Existing rows (with `contract_size=1.0`) are fixed by the backfill command (§3.1), not by re-import.

### 6.2 Option SELL fill → single option row

`normalize_okx_option_fill` (`crypto_exchange.py:832-864`) currently emits one leg with `cash_flow = Balance Change` (the *net*, conflating premium + collateral). New behavior: emit **one option leg** with the *premium* as `cash_flow`:

```python
qty = Decimal(payload["fillSz"])
price = Decimal(payload["fillPx"])
fee = Decimal(payload.get("fee") or "0")
fee_ccy = payload.get("feeCcy") or "USD"
currency = payload.get("balanceUnit") or fee_ccy        # FROM CSV — never defaulted to USD
signed_qty = qty if payload["side"] == "buy" else -qty

csize = options.contract_size_for_underlying(parsed.underlying)
premium = options.gross_premium(qty, price, csize)       # 7 × 0.0022 × 0.01 = 0.000154

collateral = _derive_collateral(payload, premium, fee)   # for comment only

legs=[{
    "asset": symbol,
    "quantity": signed_qty,                              # -7 for sell, +7 for buy
    "price": price,                                      # 0.0022 (real fill, per contract)
    "price_asset": currency,
    "role": "base",
    "instrument": "option",
    "cash_flow": premium if payload["side"] == "sell" else -premium,
    "contract_size": csize,
}]
```

**Currency source rule:** the option row's `currency` and `price_asset` come **from the CSV's `Balance Unit`**, never defaulted to USD. For a BTC-USD option, `currency = "BTC"`. The premium (`qty × fillPx × contract_size`) is then in that currency. `gross_premium()` is currency-agnostic; the currency travels with the row.

**Collateral derivation** (stored in `comment` only, never a leg). From `BC_sell = +premium − collateral − fee`, solve for the collateral magnitude:

```
collateral = premium − fee − BC_sell_signed
           = 0.000154 − 0.00001078 − (−0.00701889)
           = 0.00716211                                          ✓
```

(The implementation handles the BUY sign convention symmetrically; exact edge-case handling finalized in the implementation plan.)

### 6.3 Option expiry → single option-settlement row

`normalize_okx_option_settlement` (`crypto_exchange.py:887-909`) currently emits a BTC leg (the collateral release). New behavior: emit **one option leg** that closes the position:

```python
symbol = payload["instId"]                               # NEW: settlement must carry the option symbol
parsed = parse_option_symbol(symbol)
currency = payload.get("ccy")                            # BTC — from CSV Balance Unit
spot = Decimal(payload["px"])                            # underlying USD price at expiry
csize = options.contract_size_for_underlying(parsed.underlying)
contracts, was_short = _lookup_open_contracts(symbol, ...)   # open position direction/size

intrinsic = options.intrinsic_price(parsed, spot, csize) # BTC/contract (USD-strike, BTC-settled)
is_otm = (intrinsic == 0)
terminal_price = Decimal(0) if is_otm else intrinsic

legs=[{
    "asset": symbol,                                     # the OPTION asset, not BTC
    "quantity": -contracts if was_short else contracts,  # closes the short/long to 0
    "price": terminal_price,                             # 0 for OTM, intrinsic for ITM
    "price_asset": currency,
    "role": "base",
    "instrument": "option",
    "cash_flow": Decimal(0),                             # collateral return is a no-op
    "collateral_amount": Decimal(payload["balChg"]),     # for comment
    "is_otm": is_otm,
}]
```

**`_lookup_open_contracts`** — the importer queries the Option asset's open position direction and size at settlement time. (Fallback if the open position isn't found — e.g. partial import — trusts OKX's `Position Change` sign, with a warning.) This coupling point is an open question for the implementation plan (§9.2).

### 6.4 CSV adapter (`importer.py`) — minimal changes

1. **Option fill branch** (`importer.py:912-932`): pass `fillSz`/`fillPx`/`fee`/`feeCcy`/`balanceUnit`/raw `cashFlow` (Balance Change) to the normalizer; **stop pre-stuffing `cashFlow`** with the net Balance Change. The normalizer owns decomposition.
2. **Option settlement branch** (`importer.py:891-911`): add `instId: symbol` to the payload so the normalizer can resolve the Option asset.
3. **Currency always from CSV** — `Balance Unit` / `Fee Unit`, never defaulted.

### 6.5 Bybit mirror

`normalize_bybit_option_execution` / `_settlement` share the same shape; the Bybit CSV/API differs only in symbol format (`_parse_bybit_option_symbol`, `DDMMMYY` token) and fee sign (`-abs(...)`). The decomposition logic is identical and routes through the same `options.decompose_option_fill`.

### 6.6 Dedup — unchanged

Each option row's `import_event_id` stays `tradeId` (fill) / `billId` (settlement) — stable across re-imports. Sub-project 4 does **not** introduce an `import_group_id` for collateral (collateral is in comment only, no matching needed). Dedup is unaffected.

---

## 7. Affected components

| Component | Change | Protected? |
|---|---|---|
| `backend/services/options.py` | **New module** — `contract_size_for_underlying`, `gross_premium`, `intrinsic_price`, `option_mark_for_nav`, `is_option_asset`, `decompose_option_fill`. | No (new, but load-bearing — unit-tested like protected) |
| `backend/constants.py` | No new transaction type (reuse `OPTION_SETTLEMENT`); `OKX_CONTRACT_SIZES` may live here or in `options.py`. | No |
| `backend/common/models.py` | **No schema change.** `OptionMetadata.contract_size` value set correctly at creation + backfilled. | N/A |
| `backend/services/transactions.py` | Add `OPTION_SETTLEMENT` to the disposal classifier. | **Yes** |
| `backend/services/realized.py` | (1) Option short-open / short-close / long-close branches in `realized_gain_loss` using `contract_size` and `intrinsic_price`. (2) Transfer-neutrality fix at 752-755: matched→neutral, unmatched→disposition/entry. (3) `get_economic_basis` applies `contract_size` on option paid-entries. | **Yes** (the four most-protected methods) |
| `backend/services/nav.py` | (1) Securities loop values short option as liability at mark (entry cost or manual `Prices`). (2) Crypto loop aggregates option-row BTC `cash_flow` (premium) alongside `position(BTC)` and BTC fees. (3) IRR cash-flow filter consistent with the transfer fix. | **Yes** (`NAV_at_date`) |
| `backend/services/crypto_exchange.py` | (1) `resolve_crypto_option_asset` sets `contract_size`. (2) `normalize_okx_option_fill` emits one option leg with `cash_flow = premium`, collateral in comment. (3) `normalize_okx_option_settlement` emits one option leg (terminal price 0/intrinsic), collateral in comment. (4) Bybit normalizers mirror. (5) Persistence writes collateral to `comment`. | **Yes** (protected importer) |
| `backend/services/importer.py` | (1) Option-fill branch stops pre-stuffing `cashFlow`. (2) Option-settlement branch passes `instId`. (3) Currency always from CSV. | **Yes** (protected importer) |
| `backend/services/positions.py` | Verify (foundation open-Q #2) commission rows deplete fee-asset position; option rows' quantity drives option position. Regression guard added. | Indirect (foundation owns) |
| Management command `backfill_option_contract_sizes` | **New** — one-time data fix (not a migration). Sets `contract_size` by underlying. Idempotent. | No |
| `backend/database/serializers.py` | Option positions surface in Securities breakdown (short → negative value = liability); collateral comment visible in transaction detail. | No |
| Frontend | Option line items appear; short shown as liability. Out of backend scope but flagged for the plan. | N/A |
| Migrations | **None** — code/constants/data-command only. | N/A |

---

## 8. Testing strategy

Per AGENTS.md: protected-logic changes need unit tests + regression fixtures with expected numeric results; all tests use `Decimal`.

### 8.1 Prerequisites (hard dependencies)

| Dependency | Status | Why |
|---|---|---|
| Foundation commission-row position handling (open-Q #2: `positions.py` reads `commission` as quantity for commission-type rows) | Must be complete | BTC option fee depletes BTC position via this mechanism. Phase 1 adds a regression guard. |
| Foundation Crypto NAV bucket + BTC `position()` | Landed in PR #38 | BTC premium routing sits on top. |
| `OptionMetadata.contract_size` field | Exists (`models.py:704`) | Only the value changes. |

### 8.2 Unit tests — `services/options.py`

- `contract_size_for_underlying`: BTC → 0.01; ETH → 0.1; `"SOL"` → 1.0 + warning; lowercase `"btc"` → 0.01.
- `gross_premium`: `7 × 0.0022 × 0.01 = 0.000154`; zero-quantity → 0.
- `intrinsic_price`: CALL OTM (spot<strike) → 0; CALL ITM (spot>strike) → `size × (spot−strike) / spot` per contract; PUT ITM/OTM symmetric; at-strike → 0. Verify the USD-strike/BTC-settled `/spot` conversion and `contract_size` scaling.
- `option_mark_for_nav`: no `Prices` row → None; row present → that price.

### 8.3 Unit tests — classifier

- `_transactions_is_disposal_transaction`: `OPTION_SETTLEMENT` → True (NEW); `CRYPTO_TRADE_IN` / transfers → False.

### 8.4 Regression fixtures — option path (expected numeric results)

**Written call, OTM expiry (the user's CSV case):**
- Setup: Option `BTC-USD-260605-80000-C`, `contract_size=0.01`, CALL, strike 80000.
- SELL row: qty `−7`, price `0.0022` BTC, commission `−0.00001078` BTC, `cash_flow +0.000154` BTC.
- Settlement (OTM): qty `+7`, price `0`, `cash_flow 0`.
- Expected: realized G/L = **`+0.00014322`** BTC; position closed (0).

**Written call, ITM expiry (assignment — loss):**
- Spot at expiry 85000, strike 80000. USD-strike, BTC-settled (OKX inverse style): per-contract USD intrinsic = `contract_size × max(spot − strike, 0)` = `0.01 × 5000 = 50 USD`; BTC-settled intrinsic = `USD_intrinsic / spot` = `50 / 85000 = 0.0005882353 BTC` per contract.
- Settlement: qty `+7` (closes short), price `0.0005882353` BTC/contract, `cash_flow 0`.
- Payout = `7 × 0.0005882353 = 0.00411765` BTC (writer pays).
- Expected realized = `0.000154 − 0.00411765 − 0.00001078 =` **`−0.00403548`** BTC.

> **Units note for `intrinsic_price`:** for a USD-strike / BTC-settled option the per-contract intrinsic in the settlement coin is `contract_size × max(spot − strike, 0) / spot` (call). The `/spot` converts USD→BTC; `contract_size` scales one contract to its BTC notional. The importer passes `spot` (the settlement row's `price`) and `contract_size` (from `OptionMetadata`) so `options.intrinsic_price(meta, spot, contract_size)` returns BTC/contract directly. (For a BTC-strike option the formula differs; OKX/Bybit crypto options today are USD-strike/BTC-settled.)

**Long call, OTM expiry (buyer loses premium):**
- BUY: qty `+7`, price `0.0022`, `cash_flow −0.000154`. Settlement OTM: qty `−7`, price `0`.
- Expected: realized = **`−0.000154`** BTC (+ fee).

**Short option OPEN (not expired) — mark-at-cost neutrality:**
- SELL only. `get_economic_basis`: position `−7`, no realized G/L. Unrealized: option value `−7 × 0.0022 = −0.0154` (liability at entry mark) offset by `+0.000154` BTC premium → NAV-neutral at open.

**Manual MTM — user enters `Prices` row mid-life:**
- SELL + `Prices` at `0.001` BTC. NAV marks short at `−7 × 0.001 × 0.01 = −0.00007`. Realized still 0 until expiry.

Edge cases: zero quantity; missing `contract_size` (warned, 1.0); option with no `OptionMetadata` (error); missing `strike`/`option_type` at ITM settlement (error).

### 8.5 Unit tests — transfer-neutrality fix

- **Matched transfer** (shared `import_group_id`, single source account): stays neutral; G/L = 0; basis carried (today's behavior).
- **Unmatched OUT** (cold-wallet withdrawal, no group): NEW disposition — G/L recognized at average cost; IRR counts as external outflow.
- **Unmatched IN** (external deposit): NEW basis event — adds basis at transfer price/FMV; no G/L.
- **Multi-source group** (`allocate_group_carry` `len(source_keys)!=1`): explicitly NOT neutral — old silent-zero becomes an explicit disposition.

### 8.6 Importer tests (`test_okx_csv_parser.py`)

- `test_option_sell_emits_premium_cash_flow_not_net_balance_change`: SELL → `cash_flow = +0.000154` (premium), NOT `−0.00701889` (net); qty `−7`, price `0.0022`, commission `−0.00001078` BTC; comment contains `"Collateral blocked: 0.00716211 BTC"`.
- `test_option_settlement_otm_closes_short_at_zero`: Expired OTM → qty `+7`, price `0`, `cash_flow 0`; comment contains `"Expired OTM"`; asset = the OPTION (not BTC).
- `test_option_settlement_itm_closes_at_intrinsic`: Expired ITM, spot 85000 → price = `5000` (USD) / BTC-equivalent.
- `test_contract_size_set_on_creation`: BTC option → 0.01; ETH → 0.1.
- `test_option_currency_from_csv_balance_unit`: `currency = "BTC"`, never defaulted.
- `test_backfill_command_sets_contract_sizes`: existing rows with size 1.0 → BTC 0.01, ETH 0.1; idempotent.

### 8.7 Integration — full CSV import

Import the user's real CSV (`temp_files/...OKX Trading History...csv`); assert:
- BTC position after full import = **`+0.00014322`** (realized profit) — #33 residual BTC resolved.
- Option asset position = 0 (opened and closed).
- NAV on 2026-06-06 (post-expiry) reflects `+0.00014322 × BTC-USD` as realized gain.
- No collateral wobble (BTC position never dips by 0.00716211 then recovers).

### 8.8 IRR reconciliation

Portfolio IRR over the option cycle matches realized G/L: the SELL row's premium cash flow and the settlement's terminal cash flow produce an XIRR consistent with `+0.00014322` BTC profit. Matched transfers (post-#29) stay excluded; unmatched transfers become external flows.

---

## 9. Open questions for the implementation plan

Deferred to writing-plans, not blockers for this spec:

1. **Backfill discovery** — parse `OptionMetadata.underlying_asset.ticker`, the option `Assets.ISIN` (`CRYPTO:OPT:BTC-USD-...`), or re-run `parse_option_symbol` on `Assets.name`? Likely `name` (always populated).
2. **`_lookup_open_contracts` at settlement** — query `position()` at settlement date (clean, needs DB access at import time) vs. trust OKX's `Position Change` sign (fragile). Lean toward querying `position()`.
3. **Manual-MTM `Prices` lifecycle** — who creates the row, and how does the user enter it? Likely a frontend price-entry form (existing pattern for manual securities prices). Backend scope: ensure the NAV loop reads it.
4. **ITM exercise vs. cash settlement** — OKX/Bybit crypto options are European cash-settled; `intrinsic_price` covers this. Physical delivery (not present today) is a future extension.
5. **Multi-write averaging** — writing the same option twice before expiry: the close averages across both lots (consistent with the existing average-cost model). Confirm `get_economic_basis` handles this (it does).
6. **Transfer-match scope** — `_transfer_is_matched` checks for a partner within `import_group_id` and the portfolio account set. Pre-#29, matched transfers are rare; the predicate is conservative (unmatched unless proven matched). Post-#29 it broadens naturally.

---

## 10. Phased plan (preview)

The implementation plan (next step, via writing-plans) will likely sequence — each phase independently testable and mergeable:

1. **`services/options.py` + `contract_size` plumbing** — pure helpers; set `contract_size` at option-asset creation; backfill command. Unit tests (§8.2). *No calc-layer change yet.*
2. **Classifier + `Option settlement` recognition** — add `OPTION_SETTLEMENT` to disposal bucket; `get_economic_basis` applies `contract_size` on option entries. Unit tests (§8.3). *Option basis tracking live; no realization yet.*
3. **Importer: single option row (premium as `cash_flow`, collateral in comment)** — rewrite `normalize_okx_option_fill` / `_settlement` (+ Bybit mirror), CSV-adapter changes, currency-from-CSV. Importer tests (§8.6). *Re-importing the user's CSV produces the 2-row model; #33 residual BTC resolved at the position level.*
4. **Realized engine: option short/long close + ITM intrinsic** — `realized_gain_loss` branches using `options.intrinsic_price`. Regression fixtures with exact `0.00014322` (§8.4). *Realized P&L correct for options.*
5. **NAV: short-option liability (mark-at-cost + manual MTM) + BTC premium routing** — securities loop values short option at entry cost (or `Prices`); crypto loop aggregates BTC premium + fees. NAV regression (§8.7). *NAV smooth, no collateral wobble.*
6. **Transfer-neutrality fix** — `realized.py:752-755` matched-vs-unmatched; align IRR filter. Transfer fixtures (§8.5). *Realized-gain/IRR bugs for unmatched crypto transfers fixed.*
7. **Integration + IRR reconciliation** — full CSV import, end-to-end NAV + realized + IRR cross-check (§8.7, §8.8). *Closes #33 and the realized/IRR foundation bugs.*

Phase 4 (realized engine) and Phase 6 (transfer fix) are the most protected; Phase 3 (importer) is the largest.

---

## 11. Decisions ledger

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Scope | Options + general transfer engine together (largest) | Both are symptoms of one missing distinction (internal carry vs. external priced event); splitting duplicates the neutrality logic |
| 2 | Option lifecycle model | Short-option-as-security | Reuses the existing short-realized machinery; option position visible while open |
| 3 | Open short-option NAV value | Entry cost (premium) by default; manual MTM via `Prices` | NAV-neutral at open; no auto-fetch dependency; user controls MTM; OTM-expiry terminal price 0 |
| 4 | Transfer engine | Enhance group-carry; matched neutral, unmatched disposition/entry | Reuses well-built existing logic; no schema change; backward-compatible; fixes IRR at root |
| 5 | ITM expiry | Full OTM + ITM symmetry (intrinsic at expiry) | `intrinsic_price` is trivial from `OptionMetadata` + settlement spot |
| 6 | Long options + contract size | Cover BUY/long symmetrically; set + backfill `contract_size` (BTC=0.01, ETH=0.1) | Verifies the "÷100"; symmetric coverage |
| 7 | Collateral handling | Omit from positions; record in `comment` only | Avoids spurious NAV step-changes; BTC never left the user's ownership |
| 8 | Premium storage | Calculated (`qty × fillPx × contract_size`) as the option row's `cash_flow` | Matches foundation §5.5; calc-layer derives nothing at runtime |
| 9 | Architecture | New `services/options.py` owns option economics; importer + calc layer consume it | Mirrors foundation's `services/crypto.py`; centralizes Decimal-sensitive math |
| 10 | Currency source | CSV `Balance Unit` / `Fee unit`, never defaulted to USD | CSV defines currencies for every row; removes a silent-corruption risk |
