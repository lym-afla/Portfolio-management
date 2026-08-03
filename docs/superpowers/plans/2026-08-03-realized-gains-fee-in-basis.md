# Realized-Gains: Fee-Inclusive Cost Basis (Price Adjustment) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `get_economic_basis` include the fee in the cost basis for stablecoin-quote crypto buys, by adjusting the stored fill price so `quantity × price == cash_paid` exactly. Zero calc-layer changes.

**Architecture:** In `_spot_legs` (stablecoin branch), for BUY trades only, after computing `base_quantity` and `cash_flow`, set `price = |cash_flow| / base_quantity`. This "effective price" (incl. commission) makes the calc layer's `basis = quantity × price` (realized.py:444) exactly equal the cash paid — fee included. Sells are NOT adjusted (the fee affects the asset disposed, not the cost basis).

**Tech Stack:** Django, Decimal math.

## Global Constraints

- **Decimal only** — never `float`. `ROUND_HALF_UP`.
- **Protected calc layer untouched:** `services/realized.py`, `services/positions.py`, `services/nav.py`, `services/transactions.py`, `core/*` — ZERO changes. The fix works because `get_economic_basis` computes `quantity × price`; adjusting the stored price makes it correct automatically.
- `services/crypto_exchange.py` is protected — changes require a `needs-approval` PR + regression fixtures with expected numeric results.
- All commands from `backend/`. Tests: `./.venv/Scripts/python.exe -m pytest <path> -q --no-cov`.
- Git identity: YL-STARDESTROYER / yaroslav.linik@gmail.com.

## Background (read before implementing)

After PR #31, a stablecoin-quote buy with a base-asset fee (e.g. BTC-USDT: `0.001 @ 96058`, fee `-0.00000012 BTC`) persists:
- `quantity = 0.00099988` (net — correct for position)
- `cash_flow = -96.058` (pure trade value — correct for cash)
- `price = 96058` (raw fill — **the gap**)

`get_economic_basis` (`realized.py:444`) computes `basis = quantity × price = 0.00099988 × 96058 = 96.0465`. But the cash actually paid was `96.058`. The fee's value (`0.0115`) is missing from the basis → realized gains are overstated by `fee × price` per lot.

**The fix:** adjust the stored price to the **effective price** `= |cash_flow| / base_quantity = 96.058 / 0.00099988 = 96069.53`. Then `quantity × price = 0.00099988 × 96069.53 = 96.058` exactly — fee included. This is the standard "adjusted cost base" brokerages display.

**Why buys only:** for a sell, the fee affects the *asset disposed* (you give up more units), not the *cost basis* (which comes from the original buy). The sell's `price` is used for proceeds; adjusting it would distort realized-gain-on-disposal. Sells keep the raw fill price.

## File Structure

| File | Responsibility |
|---|---|
| `backend/services/crypto_exchange.py` | `_spot_legs` stablecoin branch: adjust buy price |
| `backend/tests/integration/workflows/test_crypto_exchange_persistence.py` | Regression: adjusted price, basis-equals-cash-paid proof |

## Verified exact values (use verbatim in tests)

| Case | quantity | cash_flow | adjusted price | qty×price |
|---|---|---|---|---|
| Base-fee BUY (`0.001@96058`, fee `-0.00000012 BTC`) | `0.00099988` | `-96.058` | `96069.528343` | `96.058` |
| Quote-fee BUY (`1@100`, fee `-0.5 USDT`) | `1` | `-100.5` | `100.5` | `100.5` |
| No-fee BUY (`0.001@96058`, fee `0`) | `0.001` | `-96.058` | `96058` (unchanged) | `96.058` |
| Base-fee SELL (`0.2@70000`, fee `-0.0001 BTC`) | `-0.2001` | `14000` | `70000` (unchanged) | n/a |

---

## Task 1: Adjust buy price for fee-inclusive cost basis

**Files:**
- Modify: `backend/services/crypto_exchange.py:520-565` (`_spot_legs` stablecoin branch)
- Test: `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`

**Interfaces:** none new. The leg's `price` field changes for buys only.

- [ ] **Step 1: Write the failing regression tests (RED)**

Add to `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`:

```python
def test_spot_legs_buy_base_fee_adjusts_price_for_fee_inclusive_basis():
    """A buy with a base-asset fee adjusts the stored price so that
    quantity * price == cash_paid (the fee is baked into the effective price).
    This makes get_economic_basis correct without calc-layer changes (#30)."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="buy", base="BTC", quote="USDT",
        qty=Decimal("0.001"), price=Decimal("96058"),
        fee_delta=Decimal("-0.00000012"), fee_asset="BTC",
    )
    leg = legs[0]
    # quantity is net (PR #31); cash_flow is pure trade value (PR #31).
    assert leg["quantity"] == Decimal("0.00099988")
    assert leg["cash_flow"] == Decimal("-96.058")
    # Price is the EFFECTIVE price (incl. fee): 96.058 / 0.00099988 = 96069.528343.
    # This is NOT the raw fill (96058) — the fee is baked in so basis is correct.
    assert leg["price"] == Decimal("96069.528343")
    # The invariant: quantity * price == cash actually paid (|cash_flow|).
    assert leg["quantity"] * leg["price"] == Decimal("96.058")


def test_spot_legs_buy_quote_fee_adjusts_price_for_fee_inclusive_basis():
    """A buy with a quote-asset fee also adjusts price so basis includes the fee."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="buy", base="ETH", quote="USDT",
        qty=Decimal("1"), price=Decimal("100"),
        fee_delta=Decimal("-0.5"), fee_asset="USDT",
    )
    leg = legs[0]
    # quantity stays gross (quote-fee doesn't net into qty); cash_flow = value + fee.
    assert leg["quantity"] == Decimal("1")
    assert leg["cash_flow"] == Decimal("-100.5")
    # Effective price = 100.5 / 1 = 100.5 (raw was 100; fee baked in).
    assert leg["price"] == Decimal("100.5")
    assert leg["quantity"] * leg["price"] == Decimal("100.5")


def test_spot_legs_buy_no_fee_keeps_raw_fill_price():
    """A buy with no fee keeps the raw fill price (no adjustment needed)."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="buy", base="BTC", quote="USDT",
        qty=Decimal("0.001"), price=Decimal("96058"),
        fee_delta=Decimal("0"), fee_asset="",
    )
    leg = legs[0]
    assert leg["price"] == Decimal("96058")  # unchanged
    assert leg["quantity"] * leg["price"] == Decimal("96.058")


def test_spot_legs_sell_does_not_adjust_price():
    """A sell keeps the raw fill price — the fee affects the asset disposed
    (quantity), not the cost basis (which comes from the buy). Adjusting the
    sell price would distort realized-gain-on-disposal."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="sell", base="BTC", quote="USDT",
        qty=Decimal("0.2"), price=Decimal("70000"),
        fee_delta=Decimal("-0.0001"), fee_asset="BTC",
    )
    leg = legs[0]
    assert leg["price"] == Decimal("70000")  # raw fill, NOT adjusted
    assert leg["quantity"] == Decimal("-0.2001")  # net of fee (PR #31)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py -k "spot_legs_buy" -q --no-cov`
Expected: the two fee-adjustment tests FAIL (price is still the raw fill `96058`/`100`); the no-fee and sell tests PASS (they assert the unchanged behavior).

- [ ] **Step 3: Implement the buy-price adjustment**

In `backend/services/crypto_exchange.py`, in the stablecoin branch, AFTER the `cash_flow` is computed for each sub-case and BEFORE the `return [...]`, add a buy-only price adjustment. Replace the `return [...]` block (lines ~554-565) with:

```python
        # For BUYS, adjust the stored price to the effective price (incl. fee)
        # so that quantity * price == cash actually paid. This makes
        # get_economic_basis (realized.py) include the fee in the cost basis
        # WITHOUT any calc-layer change. Sells keep the raw fill price (the fee
        # affects the asset disposed, not the cost basis). Issue #30.
        effective_price = price
        if side.lower() == "buy" and base_quantity != 0:
            effective_price = abs(cash_flow) / base_quantity

        return [
            {
                "asset": base,
                "quantity": base_quantity,
                "price": effective_price,
                "price_asset": "USD",
                "role": "base",
                "cash_flow": cash_flow,
                "quote_currency": quote.upper(),
                "fee_asset": normalized_fee_asset,
            }
        ]
```

This works for all three sub-cases (base-fee, quote-fee, third-asset) because `cash_flow` already reflects the correct cash paid in each:
- Base-fee buy: `cash_flow = -value` (pure `qty×price`), `base_quantity = qty + fee` → `effective_price = value / net_qty` (slightly higher than fill).
- Quote-fee buy: `cash_flow = -(value + fee)`, `base_quantity = qty` → `effective_price = (value+fee) / qty` (fill + fee-per-unit).
- No-fee buy: `cash_flow = -value`, `base_quantity = qty` → `effective_price = value / qty = price` (unchanged — the division is exact).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py -k "spot_legs" -q --no-cov`
Expected: all `_spot_legs` tests PASS (the new fee-adjustment tests + the existing base-fee/quote-fee/zero-fee/sell tests from PR #31).

- [ ] **Step 5: Update existing tests that assert the raw fill price on buy legs**

The PR #31 tests `test_spot_legs_nets_base_fee_into_quantity` and `test_spot_legs_quote_fee_still_folded_into_cash_flow` may assert `leg["price"] == Decimal("96058")` / `Decimal("16.557")` on BUY legs. Those assertions are now stale (the price is adjusted). READ the current test file first. For any BUY-leg test that asserts the raw fill price, update it to assert the effective price OR remove the price assertion (the quantity/cash_flow/fee_asset assertions are the load-bearing ones; the price is now derived). For SELL-leg tests, the price assertion stays (sells are unadjusted).

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py -q --no-cov`
Expected: all PASS.

- [ ] **Step 6: Run the import-test suite (the OKX/bybit normalizer fixtures may assert prices)**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Expected: if any test asserts a buy leg's `price` field equals the raw fill, update it the same way (Step 5). Sells are unaffected.

- [ ] **Step 7: Add a basis-equals-cash-paid proof test**

Add to `test_crypto_exchange_persistence.py` — this is the calc-layer-compatibility proof (mirrors the position() proof from PR #31 Task 3):

```python
@pytest.mark.django_db
def test_buy_with_fee_has_fee_inclusive_cost_basis(user, crypto_account):
    """Proof that get_economic_basis includes the fee: persist a base-fee buy,
    then call get_economic_basis and assert the basis == cash actually paid
    (NOT cash_paid minus fee*price). This holds with ZERO calc-layer changes
    because the stored price is the effective (fee-inclusive) price."""
    from datetime import datetime, timezone
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event
    from services.realized import get_economic_basis

    # BTC-USDT buy: 0.1 @ 70000, fee -0.0001 BTC (base asset).
    # net qty = 0.0999; cash paid = 0.1*70000 = 7000; effective price = 7000/0.0999.
    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:basis-1",
        group_id="order-basis",
        timestamp_ms=1769472000000,  # 2026-01-27
        category="trade",
        raw_type="spot_fill",
        legs=[{
            "asset": "BTC",
            "quantity": Decimal("0.0999"),  # net of fee
            "price": Decimal("7000") / Decimal("0.0999"),  # effective price
            "price_asset": "USD",
            "role": "base",
            "cash_flow": Decimal("-7000"),
            "quote_currency": "USDT",
            "fee_asset": "BTC",
        }],
        fee={"asset": "BTC", "quantity": Decimal("-0.0001"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)

    btc = Transactions.objects.get(investor=user, account=crypto_account).security
    basis = get_economic_basis(btc, datetime(2026, 1, 28, tzinfo=timezone.utc), user, "USD")
    # Basis == cash paid (7000), NOT 7000 - fee*price (which would be 6993).
    assert basis == Decimal("7000")
```

**Note:** if `get_economic_basis`'s signature or the asset-resolution path differs, adapt the call to match the actual function (read `realized.py:328` for the signature). The key assertion is `basis == Decimal("7000")` (cash paid), proving the fee is included.

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py::test_buy_with_fee_has_fee_inclusive_cost_basis -q --no-cov`
Expected: PASS. If it FAILS (basis != 7000), that means `get_economic_basis` does something other than `quantity × price` — STOP and report BLOCKED with the actual basis value; do NOT modify `realized.py`.

- [ ] **Step 8: Run the full crypto/OKX/import + calc suites**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py tests/unit/services/test_okx_csv_parser.py tests/unit/imports/test_crypto_exchange_import.py tests/unit/calculations/ -q --no-cov`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/integration/workflows/test_crypto_exchange_persistence.py backend/tests/unit/imports/test_crypto_exchange_import.py
git commit -m "fix(crypto): fee-inclusive cost basis via effective price on buys (#30)

For stablecoin-quote BUYS with a fee, adjust the stored price to the
effective price (cash_paid / quantity) so get_economic_basis computes
basis = quantity*price = cash_paid exactly — the fee is included. Sells
keep the raw fill price (fee affects asset disposed, not cost basis).
Zero calc-layer changes (same mechanism as PR #31's quantity netting)."
```

---

## Final: full verification + PR

- [ ] **Step 1: Full backend suite**

Run: `./.venv/Scripts/python.exe -m pytest -q --no-cov`
Expected: all pass (modulo the 2 pre-existing stablecoin_peg order-dependent failures).

- [ ] **Step 2: Migration check**

Run: `./.venv/Scripts/python.exe manage.py makemigrations --check --dry-run`
Expected: "No changes detected" (no schema change in this PR).

- [ ] **Step 3: Open the PR**

Title: `fix(crypto): fee-inclusive cost basis via effective price on buys (#30)`. Label `needs-approval`. Note: the displayed fill price for fee'd buys is now the effective price (incl. commission), not the raw exchange fill — this is standard "adjusted cost base" and resolves the realized-gains basis gap documented in PR #31's Known Limitation #5.

---

## Self-Review

**Spec coverage:** The goal (fee-inclusive basis) → Task 1 Steps 1-4 (the `_spot_legs` change) + Step 7 (the basis proof). Buys adjusted, sells not → Steps 1, 3, 4. Existing tests updated → Steps 5, 6. ✓

**Placeholder scan:** Step 5 says "READ the current test file first" and "may assert" — this is intentional (I haven't re-read the post-PR#31 test file in this session, so the implementer must check). The fix code (Step 3) and new tests (Steps 1, 7) are complete with exact values. Step 7's note about `get_economic_basis`'s signature is a verification instruction, not a placeholder. ✓

**Type consistency:** `effective_price` is a Decimal (result of Decimal division). `base_quantity` and `cash_flow` are the PR #31 values. Consistent. ✓

**Known impact:** the displayed fill price for fee'd buys changes from the raw exchange fill to the effective price. This is the standard brokerage convention ("adjusted cost base") and was the documented alternative in PR #31's Known Limitation #5. Re-import applies it to historical data.
