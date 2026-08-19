# Crypto Follow-Ups: ITM Exit Value, Unpriced-Coin Resilience, USD Premium Routing — Design

**Date:** 2026-08-10
**Status:** Approved (brainstorming complete; pending implementation plan)
**Scope:** Three calc-layer edge cases surfaced by the crypto option feature (sub-project 4, PR #40): (1) ITM option `exit_value` double-applies `contract_size`; (2) unpriced crypto coins crash the realized/IRR/tables paths; (3) USD-denominated option premiums reach neither Total NAV nor the cash balance.
**Predecessor:** `docs/superpowers/specs/2026-08-07-crypto-option-accounting-and-realized-gain-design.md` (sub-project 4) + 3 rounds of follow-up fixes on PR #40.

---

## 1. Problem

Three independent edge cases remain after sub-project 4's three rounds of follow-up fixes.

### 1.1 ITM option `exit_value` double-applies `contract_size`

`tables_utils.py`'s entry/exit value loops multiply every option transaction's price by `contract_size` (added in round-2 Task 2). But the two option transaction types store prices with **different scalings**:

- **Opening fills** (`Crypto trade in/out`): the stored `price` is the raw per-contract premium (e.g. `0.0022` BTC), from `decompose_option_fill` which sets `"price": Decimal(fill_price)` with no `contract_size` scaling. The loop's `× contract_size` is the **single correct** application.
- **Settlements** (`Option settlement`): the stored `price` for ITM is the intrinsic per-contract value from `options.intrinsic_price(meta, spot, contract_size)`, which **already incorporates** `contract_size` (returns `contract_size × max(spot−strike,0)/spot`). The loop's `× contract_size` is a **double-application** → ITM exit_value is 100× too small (BTC) or 10× (ETH).

OTM is unaffected (settlement price = 0 → exit_value = 0 regardless). Realized G/L is unaffected (uses the option-aware `_realized_option_close` engine, not `exit − entry`). The bug manifests only in the displayed `exit_value` / `price_change_percentage` columns for ITM option rows.

### 1.2 Unpriced crypto coins crash realized/IRR/tables

`services/crypto.py::crypto_usd_price` raises `ValueError` when a coin has no `Prices` row (e.g. TRUMP — Yahoo has no TRUMP-USD quote, so no price is ever fetched). This propagates through call sites that don't catch it:

**Crash sites (no try/except):**
- `realized.py`: `get_economic_basis` → `transaction_fx_rate` (L528); `realized_gain_loss` → crypto closing-long FX (L1120); `calculate_buy_in_price` (L428, L461); `_realized_option_close` FX-convert (L195).
- `nav.py`: `IRR` per-transaction FX (L540); `calculate_portfolio_cash` per-currency FX (L446); the option-liability loop FX (L257).

**Already-safe (skip with warning):** NAV spot-crypto loop (L279), option-cash-flow routing (L353), cash-balance FX (L382).

Result: holding any crypto coin without a `Prices` row crashes the entire positions/IRR/closed-positions table (a 500 error), not just that coin's row. NAV's spot-crypto total handles it gracefully (skip with warning); the rest of the calc layer doesn't.

### 1.3 USD-denominated option premiums reach neither NAV path

OKX lists USD-settled ("linear") crypto options alongside the inverse coin-settled ones, and the importer trusts the CSV's `Balance Unit` (which can be USD). A USD-denominated option premium currently reaches **neither** Total NAV nor the cash balance:

- `balance()` (`accounts.py:83`) skips ALL option-security rows regardless of currency (added in round-2 Task 3 to stop the BTC premium leaking into the Cash balances card). This correctly excludes coin-settled premiums (BTC is a Crypto-bucket movement) but incorrectly excludes fiat-settled premiums (USD IS a cash movement).
- `nav.py`'s option-cash-flow routing loop (`nav.py:350`) only handles crypto-coin premiums (`is_crypto_code(coin)`) → USD premiums are `continue`d.

Dormant in current data (BTC options settle in BTC) but latent — the moment a USD-settled OKX option is imported, its premium/payout is silently dropped from NAV.

---

## 2. Goals & non-goals

### Goals

1. **ITM exit_value correct.** The closed-positions table's `exit_value`/`price_change_percentage` for an ITM option reflects the actual payout, not a 100×-too-small double-scaled value.
2. **Unpriced coins don't crash.** A crypto coin without a `Prices` row is handled gracefully: the calc layer resolves a fallback price (last-trade price) before giving up, and when it gives up it skips the asset with a warning (blank/N/A for value/realized/IRR) rather than crashing the page. Position quantity is always shown.
3. **USD option premiums reach NAV.** A fiat/stablecoin-denominated option premium routes into the cash balance (it's a cash movement); a coin-denominated premium routes into the Crypto bucket (unchanged). Every premium reaches exactly one NAV path; NAV-neutrality holds for both.

### Non-goals

| Item | Deferred to |
|---|---|
| Auto-fetching missing prices (wiring TRUMP-USD to Yahoo) | Ongoing (per-coin); the fallback uses last-trade price, not a live fetch |
| "Unpriced" UI badge (frontend indicator) | Frontend scope; backend returns blank/N/A, frontend renders it |
| Per-transaction FX caching | Future optimization |
| #29 two-account model (the transfer-neutrality root cause) | Separate sub-project |

---

## 3. Follow-up 1 — ITM exit_value: `options.option_transaction_value` helper

### 3.1 The asymmetry

The two option transaction types store prices with different scalings:

| Transaction type | Stored `price` | Scaled by `contract_size`? |
|---|---|---|
| Opening fill (`Crypto trade in/out`) | Raw per-contract premium (`0.0022` BTC) | No — needs `× contract_size` in value math |
| Settlement (`Option settlement`, ITM) | `intrinsic_price` return = `contract_size × max(spot−strike,0)/spot` | Yes — already size-scaled |

The shared value loop in `tables_utils.py` can't apply a single formula to both.

### 3.2 The helper

Add to `services/options.py`:

```python
def option_transaction_value(transaction, contract_size, fx_rate) -> Decimal:
    """Effective value contribution of an option transaction row.

    Opening fills: price is the raw per-contract premium (e.g. 0.0022 BTC)
      → value = price × |qty| × contract_size × fx.
    Settlements: price is the intrinsic per-contract value ALREADY scaled by
      contract_size (from intrinsic_price)
      → value = price × |qty| × fx (no second contract_size).
    """
    price = transaction.price or Decimal(0)
    qty = abs(transaction.quantity or Decimal(0))
    from constants import TRANSACTION_TYPE_OPTION_SETTLEMENT
    if transaction.type == TRANSACTION_TYPE_OPTION_SETTLEMENT:
        return price * qty * fx_rate
    return price * qty * contract_size * fx_rate
```

`tables_utils.py`'s entry/exit value loops call `options.option_transaction_value(transaction, contract_size, fx_rate)` for option assets instead of the inline `(get_price(tx) or Decimal(0)) × |qty| × contract_size × fx`. Non-options keep the inline formula (`contract_size = Decimal(1)`, no change).

### 3.3 Testing

- `option_transaction_value`: opening fill `0.0022 × 7 × 0.01 = 0.000154`; settlement OTM `0`; settlement ITM `intrinsic_q × 7` (NOT `× contract_size` again).
- `tables_utils` ITM closed row: exit_value = `intrinsic × qty × fx` (not 100× too small); realized_gl correct (from the option-aware engine).

---

## 4. Follow-up 2 — Unpriced-coin resilience: three-tier resolution + per-site guards

### 4.1 Three-tier price resolution

Add to `services/crypto.py` a fallback resolver that tries the market price, then the last-trade price, then gives up:

```python
def crypto_usd_price_with_fallback(code, date_as_of, investor=None) -> Optional[Decimal]:
    """Resolve a coin's USD price, falling back to the last transaction price.

    Tier 1: latest Prices row on/before date_as_of (the live market price).
    Tier 2: the asset's most recent Crypto trade in/out price (as USD),
            if that trade's currency is USD/USDT/USDC, or convertible via FX.
    Tier 3: None (unpriced — caller skips with warning).
    """
    # Tier 1
    try:
        return crypto_usd_price(code, date_as_of, investor)
    except ValueError:
        pass
    # Tier 2: last transaction price
    from common.models import Assets, Transactions
    from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN, TRANSACTION_TYPE_CRYPTO_TRADE_OUT
    asset = Assets.objects.filter(type="Crypto", name=code).first()
    if asset is None:
        return None
    last_trade = (
        Transactions.objects.filter(
            security=asset, investor=investor,
            type__in=[TRANSACTION_TYPE_CRYPTO_TRADE_IN, TRANSACTION_TYPE_CRYPTO_TRADE_OUT],
            price__isnull=False,
            date__date__lte=date_as_of,
        ).order_by("-date", "-id").first()
    )
    if last_trade is None or last_trade.price in (None, 0):
        return None
    if (last_trade.currency or "").upper() in ("USD", "USDT", "USDC"):
        return Decimal(last_trade.price)
    try:
        return Decimal(last_trade.price) * get_rate(last_trade.currency, "USD", last_trade.date)["FX"]
    except ValueError:
        return None
```

And a `safe_crypto_fx_rate` wrapper that returns `None` (with a warning) instead of raising:

```python
def safe_crypto_fx_rate(code, target, date_as_of, investor=None) -> Optional[Decimal]:
    """Like crypto_fx_rate, but returns None (with a warning) when the coin is
    unpriced (both market and last-trade fallbacks miss), instead of raising."""
    try:
        return crypto_fx_rate(code, target, date_as_of, investor)
    except ValueError:
        # Tier 2: try last-trade fallback for the USD price, then convert.
        usd_price = crypto_usd_price_with_fallback(code, date_as_of, investor)
        if usd_price is None:
            logger.warning("No USD price for %s on or before %s (market + last-trade) — skipping", code, date_as_of)
            return None
        logger.info("Using last-trade price for %s as of %s", code, date_as_of)
        if target.upper() == "USD":
            return usd_price
        # Convert USD → target via the fiat FX graph (no crypto hop needed).
        try:
            return usd_price * get_rate("USD", target, date_as_of)["FX"]
        except ValueError:
            return None
```

### 4.2 Per-call-site guards (skip-on-None)

Each crash site wraps its FX call in `safe_crypto_fx_rate`. If it returns `None`, the calc **skips** that transaction/asset (returns zeros / continues / yields N/A) rather than computing a wrong number:

- **`get_economic_basis` / `realized_gain_loss` / `calculate_buy_in_price`**: if a transaction's FX rate is `None`, skip that transaction in the basis replay / position walker. The asset's realized comes back as `Decimal(0)` (not a crash). The position is still tracked.
- **`_realized_option_close`**: if the FX conversion to target currency is `None`, return the realized in the native settle coin (don't FX-convert) with a warning. The table shows the native-coin value rather than crashing.
- **`IRR`**: if any transaction's FX rate is `None`, skip that transaction from the cash-flow list (contributes 0). The XIRR computes over the remaining flows. If too few flows remain, IRR returns "N/A".
- **`calculate_portfolio_cash`**: if a currency's FX rate is `None`, skip that currency from the portfolio cash total.
- **Option-liability loop (nav.py L257)**: if the option's settle-coin FX is `None`, skip the option from the Securities breakdown (it's unvalued) with a warning — same as the spot-crypto loop.

**Principle:** never silently compute a wrong number; never crash the page. An unpriced asset shows blank/N/A for value/realized/IRR, with a logged warning. Position quantity is always shown.

### 4.3 Why last-trade price (tier 2)

The most recent `Crypto trade in/out` price is the best available factual datapoint when no market price exists. For TRUMP: the last trade is `Crypto trade out @ 16.557 USDT` → tier 2 returns `16.557`, so TRUMP's realized/IRR compute against $16.56 instead of crashing. It's stale (frozen at the last trade), not perfectly accurate, but vastly better than a 500 error or a silent skip. Only `Crypto trade in/out` rows contribute (transfers/rewards/settlements don't carry a market price); `price__isnull=False, price != 0` guards skip zero-priced rows.

### 4.4 Testing

- `crypto_usd_price_with_fallback`: tier 1 hits → market price; tier 1 misses, tier 2 hits → last-trade price; both miss → `None`.
- `safe_crypto_fx_rate`: priced → rate; unpriced → `None` + warning.
- `realized_gain_loss` on unpriced-with-trades coin → computes against last-trade price (no crash).
- `realized_gain_loss` on unpriced-no-trades coin → `{total: 0}` + warning (no crash).
- `IRR` with an unpriced coin → Decimal or "N/A" (no crash).
- Regression: fully-priced portfolio unchanged (the `None` path never fires).

---

## 5. Follow-up 3 — USD option premium routing: currency-aware `balance()`

### 5.1 The principle

Every option premium reaches **exactly one NAV path**, determined by its currency:

| Premium currency | What it is | NAV path |
|---|---|---|
| Crypto coin (BTC/ETH) | Crypto-bucket movement (offset by option liability) | `nav.py` option-cash-flow loop → Crypto bucket + Total NAV |
| Fiat/stablecoin (USD/EUR/USDT/USDC) | Cash movement (received/paid fiat) | `balance()` → cash dict → NAV cash-balance loop → Total NAV |

### 5.2 The fix

Replace `balance()`'s blanket option skip (`accounts.py:83`) with a currency-aware one. Lift `_CASH_CURRENCIES` to a shared constant in `constants.py` (currently in `balance_tracker.py`):

```python
# constants.py
CASH_CURRENCIES = {code.upper() for code, _ in ALL_CURRENCY_CHOICES}
# = {"USD", "EUR", "GBP", "RUB", "CHF", "CNY", "USDT", "USDC"}
```

```python
# accounts.py balance()
if (
    transaction.security is not None
    and transaction.security.type == ASSET_TYPE_OPTION
    and (transaction.currency or "").upper() not in CASH_CURRENCIES
):
    # Coin-settled premium (BTC) — Crypto-bucket movement, not cash. Skip.
    continue
# Fiat/stablecoin-settled premium (USD) — IS a cash movement. Include.
```

`nav.py`'s option-cash-flow routing loop is unchanged (`is_crypto_code` filter stays — it handles coin-settled premiums; fiat-settled premiums no longer reach it because they're in the cash balance now).

### 5.3 No double-count verification

- **BTC-settled premium**: in the Crypto bucket (option-cash-flow loop); NOT in `balance()` (excluded by the coin currency). One path. ✓
- **USD-settled premium**: in the cash balance (via `balance()`); NOT in the option-cash-flow loop (`is_crypto_code("USD")` is False → `continue`). One path. ✓
- **Option liability**: in the Securities breakdown (the option-mark loop), regardless of settlement currency. Offset by the premium in the matching bucket. ✓

### 5.4 Testing

- `balance()` with USD-denominated option premium → `balance_result["USD"]` includes it.
- `balance()` with BTC-denominated option premium → BTC excluded (regression guard).
- NAV-neutrality: USD-settled short → `Total NAV == 0`; BTC-settled short → `Total NAV == 0` (regression).
- No double-count: a USD premium in exactly one path (cash balance, not the Crypto loop).

---

## 6. Affected components

| Component | Change | Protected? |
|---|---|---|
| `backend/services/options.py` | Add `option_transaction_value` helper | No (new) |
| `backend/core/tables_utils.py` | Entry/exit value loops call `option_transaction_value` for options | No |
| `backend/services/crypto.py` | Add `crypto_usd_price_with_fallback` + `safe_crypto_fx_rate` | No (new helpers) |
| `backend/services/realized.py` | Wrap FX calls in `safe_crypto_fx_rate`; skip on None (4-5 sites) | **Yes** |
| `backend/services/nav.py` | Wrap FX calls in `safe_crypto_fx_rate` (IRR / calculate_portfolio_cash / option-liability); skip on None | **Yes** |
| `backend/services/accounts.py` | `balance()`: currency-aware option skip | **Yes** |
| `backend/constants.py` | Add shared `CASH_CURRENCIES` constant | No |
| `backend/core/balance_tracker.py` | Import shared `CASH_CURRENCIES` (no behavior change) | No |
| Tests | `test_options.py`, `test_realized_option_paths.py`, `test_nav_option_paths.py`, `test_accounts_balance.py`, `test_tables_option_closed.py` | — |

No schema change, no migrations.

---

## 7. Phased plan preview

1. **Follow-up 1** (ITM exit_value) — `options.option_transaction_value` + tables_utils call. Isolated, low-risk.
2. **Follow-up 3** (USD premium routing) — `balance()` currency-aware skip + shared `CASH_CURRENCIES`. Isolated, low-risk.
3. **Follow-up 2** (unpriced resilience) — 3-tier resolver + per-site guards. Broadest. Sub-phases: (a) `crypto.py` helpers; (b) `realized.py` guards; (c) `nav.py` guards; (d) regression fixtures.

Each phase independently testable and mergeable.

---

## 8. Decisions ledger

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | ITM exit_value fix location | `options.py` helper (`option_transaction_value`) | Encapsulates per-contract-vs-size-scaled distinction in the option module; keeps tables_utils generic; unit-testable |
| 2 | Missing-price policy | Skip-with-warning (after 3-tier fallback) | Mirrors NAV's existing spot-crypto handling; never crashes, never silently wrong; last-trade fallback gives a real number when possible |
| 3 | Missing-price fallback source | Last `Crypto trade in/out` price | Best available factual datapoint; stale but vastly better than crash/skip; only trades carry a market price |
| 4 | USD premium routing | Currency-aware `balance()` (coin → Crypto bucket; fiat → cash balance) | Every premium in exactly one NAV path; matches economic reality; NAV-neutral for both |
| 5 | Shared cash-currency set | `CASH_CURRENCIES` in `constants.py` (derived from `ALL_CURRENCY_CHOICES`) | Authoritative source; shared by `balance()` and `balance_tracker` |
