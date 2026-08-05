# Unified Trade Cash-Flow Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Remove `cash_flow` from trade rows; make `price × quantity ± commission` the single source of truth for trade cash flow, with broker-level precision rounding.

**Architecture:** `_spot_legs` computes an effective price so `p×q` exactly reproduces the CSV settlement. `total_cash_flow` and `nav.py` compute `-(p×q) ± commission` for crypto trades (instead of reading a stored `cash_flow`), rounded to the broker's `cash_precision`. `realized.py` and `positions.py` are unchanged.

**Tech Stack:** Django, Decimal math.

## Global Constraints

- **Decimal only** — never `float`. `ROUND_HALF_UP`.
- **Protected calc layer:** `services/transactions.py`, `services/nav.py`, `services/realized.py`, `services/positions.py`, `services/crypto_exchange.py` — changes need `needs-approval` PR + regression fixtures.
- All commands from `backend/`. Tests: `./.venv/Scripts/python.exe -m pytest <path> -q --no-cov`.
- Git identity: YL-STARDESTROYER / yaroslav.linik@gmail.com.
- `Transactions.price` is already `decimal_places=9` (no migration needed for price).
- `Transactions.cash_flow` is `decimal_places=9` (PR #35).

## Key facts (read before implementing)

1. `Transactions.price` is `DecimalField(max_digits=18, decimal_places=9)` — already 9dp. No precision migration needed.
2. `total_cash_flow` (`services/transactions.py:160-248`): crypto trades (`CRYPTO_TRADE_IN/OUT`) are in `cash_flow_types` (lines 206-207) and read `transaction.cash_flow` directly. The Buy/Sell branch (lines 221-239) computes `-(quantity × price) + commission`.
3. `nav.py:411`: `_calculate_cash_flow` computes `-transaction.quantity * transaction.price` for crypto trades — no commission term.
4. `_spot_legs` (`crypto_exchange.py:505-575`): stablecoin branch currently sets `cash_flow` on the leg and computes effective price for base-fee buys only.
5. `persist_crypto_exchange_event` (`crypto_exchange.py:352-470`): writes `cash_flow` from `leg.get("cash_flow")` (line 458-461) for trade legs.
6. `Brokers` model (`common/models.py:87`): has `name`, `country` — no precision field yet.
7. Commission sign: stored **negative** for a cost (matching the model docstring).

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `backend/common/models.py` | Add `cash_precision` to `Brokers` | 1 |
| `backend/common/migrations/` | Migration for `cash_precision` | 1 |
| `backend/services/crypto_exchange.py` | `_spot_legs` unified effective price; stop emitting `cash_flow` on legs; `persist` stops writing it | 2, 3 |
| `backend/services/transactions.py` | `total_cash_flow`: crypto trades → p×q branch + broker rounding | 4 |
| `backend/services/nav.py` | `_calculate_cash_flow`: add commission + broker rounding | 5 |
| `backend/tests/integration/workflows/test_crypto_exchange_persistence.py` | Regression fixtures for all 5 fee cases | 2, 4 |
| `backend/tests/unit/calculations/` | `total_cash_flow` + `nav` calc proofs | 4, 5 |

---

## Task 1: Add `cash_precision` to Brokers + migration

**Files:**
- Modify: `backend/common/models.py` (the `Brokers` class, ~line 87-92)
- Create: migration
- Test: verify field exists + default

**Interfaces:**
- Produces: `Brokers.cash_precision` (IntegerField, default=2) — consumed by Tasks 4 and 5.

- [ ] **Step 1: Add the field**

In `backend/common/models.py`, in the `Brokers` class (after `country`), add:

```python
    cash_precision = models.IntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(9)],
        help_text="Decimal places the broker uses for cash settlement (e.g. 2 for traditional, 8 for crypto).",
    )
```

Add `MinValueValidator, MaxValueValidator` to the `from django.core.validators import ...` import if not already there.

- [ ] **Step 2: Generate and apply migration**

Run: `./.venv/Scripts/python.exe manage.py makemigrations common`
Inspect: must be a single `AddField` on `brokers`, `name="cash_precision"`, `default=2`.

Run: `./.venv/Scripts/python.exe manage.py migrate common`

- [ ] **Step 3: Set crypto brokers to 8dp**

Run:
```
./.venv/Scripts/python.exe manage.py shell -c "
from common.models import Brokers
updated = Brokers.objects.filter(name__icontains='OKX').update(cash_precision=8)
updated += Brokers.objects.filter(name__icontains='Bybit').update(cash_precision=8)
print(f'Updated {updated} crypto brokers to cash_precision=8')
"
```

- [ ] **Step 4: Run full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q --no-cov`
Expected: same pass count (additive nullable field with default).

- [ ] **Step 5: Commit**

```bash
git add backend/common/models.py backend/common/migrations/<new_migration>.py
git commit -m "feat(schema): add cash_precision to Brokers (default=2, crypto=8)"
```

---

## Task 2: Unified effective price in `_spot_legs` (stop emitting cash_flow)

**Files:**
- Modify: `backend/services/crypto_exchange.py:505-575` (`_spot_legs` stablecoin branch)
- Test: `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`

**Interfaces:**
- Produces: legs with `price` (effective, all cases) and NO `cash_flow` key. `quantity` and `fee_asset` as before. Consumed by Task 3 (persist) and Tasks 4-5 (calc).

**Design:** For ALL buys/sells, compute `effective_price` so `|price × quantity| ± commission == |settlement|`. The `quote_cash_amount` parameter (from CSV's quote-leg Balance Change) is the settlement. Remove `cash_flow` from the leg dict.

- [ ] **Step 1: Write the failing regression tests (RED)**

Add to `test_crypto_exchange_persistence.py`. These test `_spot_legs` directly:

```python
def test_spot_legs_quote_fee_effective_price_excludes_commission():
    """Quote-fee buy: price = (settlement - commission) / qty. The commission
    is subtracted from the settlement before deriving price, so p*q excludes
    the fee (commission enters calc separately). cash_flow is NOT on the leg."""
    from services.crypto_exchange import _spot_legs
    legs = _spot_legs("buy", "ETH", "USDT", Decimal("1"), Decimal("100"),
                      Decimal("-0.5"), "USDT", quote_cash_amount=Decimal("100.5"))
    leg = legs[0]
    assert leg["quantity"] == Decimal("1")
    # price = (100.5 - (-0.5)) / 1 = 101... NO. price = (settlement - commission) / qty
    # settlement=100.5, commission=-0.5 (negative cost). (100.5 - (-0.5)) = 101? No.
    # The formula: price = (settlement + commission) / qty where commission is negative.
    # = (100.5 + (-0.5)) / 1 = 100.0 = raw fill.
    assert leg["price"] == Decimal("100")
    assert "cash_flow" not in leg


def test_spot_legs_base_fee_effective_price_includes_fee_in_qty():
    """Base-fee buy: price = settlement / net_qty (commission different currency,
    not subtracted). Settlement = gross trade value."""
    from services.crypto_exchange import _spot_legs
    legs = _spot_legs("buy", "BTC", "USDT", Decimal("0.06684041"), Decimal("74837.4"),
                      Decimal("-0.00006684"), "BTC", quote_cash_amount=Decimal("5002.16249933"))
    leg = legs[0]
    assert leg["quantity"] == Decimal("0.06677357")  # net
    assert "cash_flow" not in leg
    # price = 5002.16249933 / 0.06677357
    assert leg["price"] == Decimal("5002.16249933") / Decimal("0.06677357")


def test_spot_legs_no_fee_price_is_fill():
    """No-fee buy: price = settlement / qty = fill price."""
    from services.crypto_exchange import _spot_legs
    legs = _spot_legs("buy", "BTC", "USDT", Decimal("0.001"), Decimal("96058"),
                      Decimal("0"), "", quote_cash_amount=Decimal("96.058"))
    leg = legs[0]
    assert leg["price"] == Decimal("96058")
    assert "cash_flow" not in leg


def test_spot_legs_sell_quote_fee():
    """Quote-fee sell: price excludes commission; qty is gross (negative)."""
    from services.crypto_exchange import _spot_legs
    legs = _spot_legs("sell", "BTC", "USDT", Decimal("0.2"), Decimal("70000"),
                      Decimal("-0.5"), "USDT", quote_cash_amount=Decimal("13999.5"))
    leg = legs[0]
    assert leg["quantity"] == Decimal("-0.2")
    # price = (13999.5 + (-0.5)) / 0.2 = 13999/0.2 = 69995
    assert leg["price"] == Decimal("69995")
    assert "cash_flow" not in leg
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py -k "spot_legs_quote_fee_effective or spot_legs_base_fee_effective or spot_legs_no_fee_price or spot_legs_sell_quote_fee" -q --no-cov`
Expected: FAIL (current code emits `cash_flow` and doesn't compute effective price for quote-fee).

- [ ] **Step 3: Rewrite the `_spot_legs` stablecoin branch**

Replace the entire stablecoin branch (`if quote.upper() in STABLECOIN_CURRENCIES:` block) with:

```python
    if quote.upper() in STABLECOIN_CURRENCIES:
        # The settlement is the actual quote-currency amount that moved (from
        # the CSV's quote-leg Balance Change). Prefer it over qty*price (which
        # produces Decimal noise). Issue #32.
        settlement = quote_cash_amount if quote_cash_amount is not None else qty * price
        normalized_fee_asset = (fee_asset or "").upper()
        fee_in_quote = normalized_fee_asset == quote.upper()

        if side.lower() == "buy":
            base_quantity = qty
        elif side.lower() == "sell":
            base_quantity = -qty
        else:
            raise ValueError(f"Unsupported spot side: {side}")

        # Net base-asset fee into quantity (PR #31).
        if normalized_fee_asset == base.upper():
            base_quantity = base_quantity + fee_delta

        # Effective price so that |price * quantity| reproduces the settlement.
        # For quote-fee: subtract commission (same currency) from settlement first.
        # For base-fee / no-fee / third-asset: commission is different currency
        # (or zero) — don't subtract; the fee is already in net_qty or absent.
        if fee_in_quote:
            priced_settlement = settlement + fee_delta  # fee_delta negative -> reduces
        else:
            priced_settlement = settlement

        if base_quantity != 0:
            effective_price = abs(priced_settlement) / abs(base_quantity)
        else:
            effective_price = price

        return [
            {
                "asset": base,
                "quantity": base_quantity,
                "price": effective_price,
                "price_asset": "USD",
                "role": "base",
                "quote_currency": quote.upper(),
                "fee_asset": normalized_fee_asset,
            }
        ]
```

Key: NO `cash_flow` key in the leg. The effective price formula handles all cases uniformly.

- [ ] **Step 4: Run the tests to verify pass**

Run: same command as Step 2.
Expected: all 4 PASS.

- [ ] **Step 5: Update existing _spot_legs tests that assert cash_flow**

Many existing tests (from PR #31/#34) assert `leg["cash_flow"]`. Those assertions must be removed (cash_flow is no longer on the leg). READ the test file, find all `leg["cash_flow"]` or `cash_flow` assertions in `_spot_legs` tests, and remove them. Replace with `price` assertions where appropriate.

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py -k "spot_legs" -q --no-cov`
Expected: all PASS.

- [ ] **Step 6: Run the import tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Update any test that asserts `event.legs[0]["cash_flow"]` — remove the assertion.

- [ ] **Step 7: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/integration/workflows/test_crypto_exchange_persistence.py backend/tests/unit/imports/test_crypto_exchange_import.py
git commit -m "fix(crypto): unified effective price; remove cash_flow from spot legs

_spot_legs now computes an effective price so |p*q| reproduces the exact
settlement for all fee types. cash_flow is no longer emitted on the leg.
Quote-fee: price = (settlement + commission) / qty (commission same ccy).
Base-fee: price = settlement / net_qty (commission different ccy, in qty)."
```

---

## Task 3: Stop persisting `cash_flow` on trade legs

**Files:**
- Modify: `backend/services/crypto_exchange.py:458-461` (`persist_crypto_exchange_event`)

**Interfaces:**
- Produces: trade rows with `cash_flow=NULL`. Non-trade rows (deposits/withdrawals/transfers that use `_is_stablecoin_cash_leg`) still write `cash_flow`.

- [ ] **Step 1: Remove the cash_flow write for trade legs**

In `persist_crypto_exchange_event`, the `if leg_cash_flow is not None:` block (lines ~458-461) currently writes `cash_flow` for ALL priced legs. Change it to only write for non-trade categories (stablecoin cash legs still need it). Replace:

```python
                if leg_cash_flow is not None:
                    tx_kwargs["cash_flow"] = _normalize_model_decimal(
                        Transactions, "cash_flow", leg_cash_flow
                    )
```

with:

```python
                # Trade legs no longer carry cash_flow (computed from p*q in
                # total_cash_flow). Only stablecoin cash legs (deposits/
                # withdrawals/rewards) write cash_flow directly.
                if leg_cash_flow is not None and category not in {"trade"}:
                    tx_kwargs["cash_flow"] = _normalize_model_decimal(
                        Transactions, "cash_flow", leg_cash_flow
                    )
```

- [ ] **Step 2: Run crypto persistence tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py -q --no-cov`
Expected: update any test that asserts `tx.cash_flow` on a trade row — those should now be `None`. The stablecoin-cash-leg tests (deposits/withdrawals) should still have `cash_flow` set.

- [ ] **Step 3: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/integration/workflows/test_crypto_exchange_persistence.py
git commit -m "fix(crypto): stop persisting cash_flow on trade legs (computed from p*q)"
```

---

## Task 4: `total_cash_flow` — crypto trades to p×q branch + broker rounding

**Files:**
- Modify: `backend/services/transactions.py:160-248` (`total_cash_flow`)
- Test: `backend/tests/unit/calculations/test_total_cash_flow_crypto.py` (new)

**Interfaces:**
- Consumes: `Brokers.cash_precision` (Task 1).
- Produces: `total_cash_flow` for crypto trades returns `round(-(p×q) + commission, cash_precision)`.

- [ ] **Step 1: Write the failing calc test (RED)**

Create `backend/tests/unit/calculations/test_total_cash_flow_crypto.py`:

```python
"""Tests for total_cash_flow on crypto trades under the unified model.

Crypto trades no longer store cash_flow; total_cash_flow computes
-(price*quantity) + commission (when commission is in the trade currency),
rounded to the broker's cash_precision.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, Transactions
from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN
from services.transactions import total_cash_flow


@pytest.fixture
def crypto_setup(user):
    broker = Brokers.objects.create(investor=user, name="OKX Test", country="Crypto", cash_precision=8)
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="okx-test")
    return broker, account


@pytest.mark.django_db
def test_quote_fee_buy_cash_flow_equals_settlement(crypto_setup):
    """Quote-fee buy: total_cash_flow = -(p*q) + commission == -settlement."""
    _, account = crypto_setup
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=Decimal("1"), price=Decimal("100"),
        commission=Decimal("-0.5"), commission_currency="USDT",
    )
    cf = total_cash_flow(tx)
    # -(100*1) + (-0.5) = -100.5
    assert cf == Decimal("-100.5")


@pytest.mark.django_db
def test_base_fee_buy_cash_flow_no_commission_term(crypto_setup):
    """Base-fee buy: commission in BTC (different currency) — not subtracted."""
    _, account = crypto_setup
    net_qty = Decimal("0.06677357")
    eff_price = Decimal("5002.16249933") / net_qty
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=net_qty, price=eff_price,
        commission=Decimal("-0.00006684"), commission_currency="BTC",
    )
    cf = total_cash_flow(tx)
    # -(p*q) with no commission term (different currency).
    expected = (-(eff_price * net_qty)).quantize(Decimal("0.00000001"))
    assert cf == expected
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/calculations/test_total_cash_flow_crypto.py -q --no-cov`
Expected: FAIL (crypto trades still in `cash_flow_types`, reading the NULL `cash_flow` field → returns 0).

- [ ] **Step 3: Modify `total_cash_flow`**

In `backend/services/transactions.py`:

**3a.** Remove `TRANSACTION_TYPE_CRYPTO_TRADE_IN` and `TRANSACTION_TYPE_CRYPTO_TRADE_OUT` from the `cash_flow_types` list (lines 206-207). They now fall through to the Buy/Sell-style computation.

**3b.** The existing Buy/Sell branch (line 221) currently checks `transaction.type in [TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL]`. Change it to also include crypto trades:

```python
    elif transaction.type in [
        TRANSACTION_TYPE_BUY,
        TRANSACTION_TYPE_SELL,
        TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    ]:
```

**3c.** In the computation body, add the commission only when it's in the same currency:

```python
        if transaction.quantity and transaction.price is not None:
            effective_price = get_price(transaction) or Decimal(0)
            calculated_cash_flow = -Decimal(transaction.quantity) * effective_price

            if transaction.aci:
                calculated_cash_flow += Decimal(transaction.aci)

            # Add commission only when it's in the trade's currency (quote-fee).
            # For base-asset fees (different currency), commission is display-only.
            if (
                transaction.commission
                and transaction.commission_currency
                and transaction.commission_currency.upper() == (transaction.currency or "").upper()
            ):
                calculated_cash_flow += Decimal(transaction.commission)
```

**3d.** Before the final `return`, add broker-precision rounding:

```python
    # Round to the broker's cash_precision to absorb price-storage residuals.
    cash_precision = 2
    if hasattr(transaction, "account") and transaction.account and transaction.account.broker:
        cash_precision = transaction.account.broker.cash_precision
    return calculated_cash_flow.quantize(Decimal(1).scaleb(-cash_precision), rounding=ROUND_HALF_UP)
```

(Import `ROUND_HALF_UP` from `decimal` at the top of the file if not already.)

- [ ] **Step 4: Run the calc test to verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/calculations/test_total_cash_flow_crypto.py -q --no-cov`
Expected: PASS.

- [ ] **Step 5: Run the full suite — fix any regressions**

Run: `./.venv/Scripts/python.exe -m pytest -q --no-cov`
The crypto-trade branch move will break tests that asserted `total_cash_flow` reading `cash_flow`. Update those. The `accounts.py` balance tests may also need updating (they sum `total_cash_flow`). Run focused suites first:

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/ tests/unit/calculations/ -q --no-cov`
Expected: all PASS after updating stale assertions.

- [ ] **Step 6: Commit**

```bash
git add backend/services/transactions.py backend/tests/unit/calculations/test_total_cash_flow_crypto.py
git commit -m "fix(calc): total_cash_flow computes p*q for crypto trades + broker rounding

Crypto trades move from the cash_flow-reading branch to the p*q-computing
branch. Commission added only when in the trade's currency. Result rounded
to the broker's cash_precision to absorb price-storage residuals."
```

---

## Task 5: `nav.py` — add commission + broker rounding to crypto cash flow

**Files:**
- Modify: `backend/services/nav.py:402-412` (`_calculate_cash_flow`)
- Test: `backend/tests/unit/calculations/test_nav_crypto_cash_flow.py` (new)

- [ ] **Step 1: Write the failing test (RED)**

Create `backend/tests/unit/calculations/test_nav_crypto_cash_flow.py`:

```python
"""Tests for nav.py _calculate_cash_flow on crypto trades (IRR path)."""

from datetime import datetime
from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, Transactions
from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN
from services.nav import _calculate_cash_flow


@pytest.fixture
def crypto_setup(user):
    broker = Brokers.objects.create(investor=user, name="OKX Test", country="Crypto", cash_precision=8)
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="okx-test")
    return broker, account


@pytest.mark.django_db
def test_nav_crypto_quote_fee_includes_commission(crypto_setup):
    """IRR cash flow for a quote-fee crypto buy includes commission."""
    _, account = crypto_setup
    tx = Transactions.objects.create(
        investor=account.broker.investor, account=account,
        type=TRANSACTION_TYPE_CRYPTO_TRADE_IN, currency="USDT",
        date=datetime(2026, 1, 1),
        quantity=Decimal("1"), price=Decimal("100"),
        commission=Decimal("-0.5"), commission_currency="USDT",
    )
    cf = _calculate_cash_flow(tx)
    # -(100*1) + (-0.5) = -100.5
    assert cf == Decimal("-100.5")
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/calculations/test_nav_crypto_cash_flow.py -q --no-cov`
Expected: FAIL (current code computes `-qty*price` without commission → `-100`, not `-100.5`).

- [ ] **Step 3: Modify `_calculate_cash_flow`**

In `backend/services/nav.py`, the crypto-trade block (lines ~402-412). Replace:

```python
    if transaction.type in [
        TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    ]:
        if transaction.quantity is not None and transaction.price is not None:
            # IRR treats crypto trades as asset cash flows: buys are negative,
            # sells are positive, while account cash balances stay unchanged.
            return -transaction.quantity * transaction.price
        return Decimal(0)
```

with:

```python
    if transaction.type in [
        TRANSACTION_TYPE_CRYPTO_TRADE_IN,
        TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
        TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    ]:
        if transaction.quantity is not None and transaction.price is not None:
            cf = -transaction.quantity * transaction.price
            # Add commission when in the trade's currency (quote-fee).
            if (
                transaction.commission
                and transaction.commission_currency
                and transaction.commission_currency.upper() == (transaction.currency or "").upper()
            ):
                cf += Decimal(transaction.commission)
            # Round to broker's cash_precision.
            cash_precision = 2
            if transaction.account and transaction.account.broker:
                cash_precision = transaction.account.broker.cash_precision
            return cf.quantize(Decimal(1).scaleb(-cash_precision), rounding=ROUND_HALF_UP)
        return Decimal(0)
```

(Add `from decimal import ROUND_HALF_UP` to nav.py's imports if needed.)

- [ ] **Step 4: Run the test to verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/calculations/test_nav_crypto_cash_flow.py -q --no-cov`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q --no-cov`
Expected: fix any regressions, then all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/nav.py backend/tests/unit/calculations/test_nav_crypto_cash_flow.py
git commit -m "fix(nav): add commission + broker rounding to crypto IRR cash flow"
```

---

## Task 6: Regression sweep — full integration verification

**Files:**
- Test: `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`

- [ ] **Step 1: Write end-to-end persistence + calc regression**

Add to `test_crypto_exchange_persistence.py` — persist each fee case through the full pipeline (normalize → persist → total_cash_flow) and assert the settlement matches:

```python
@pytest.mark.django_db
def test_unified_model_quote_fee_buy_full_pipeline(user, crypto_account):
    """End-to-end: quote-fee buy persists with effective price; total_cash_flow
    reproduces the settlement exactly."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event
    from services.transactions import total_cash_flow

    event = CryptoExchangeEvent(
        provider="okx_csv", provider_event_id="csv:e2e-1", group_id="e2e-1",
        timestamp_ms=1738454400000, category="trade", raw_type="spot_fill",
        legs=[{"asset": "ETH", "quantity": Decimal("1"), "price": Decimal("100"),
               "price_asset": "USD", "role": "base", "quote_currency": "USDT",
               "fee_asset": "USDT"}],
        fee={"asset": "USDT", "quantity": Decimal("-0.5"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    tx = Transactions.objects.get(investor=user, account=crypto_account)
    assert tx.cash_flow is None  # not stored on trade rows
    assert tx.price == Decimal("100")
    assert tx.quantity == Decimal("1")
    assert tx.commission == Decimal("-0.5")
    cf = total_cash_flow(tx)
    assert cf == Decimal("-100.5")  # -(100*1) + (-0.5)
```

- [ ] **Step 2: Run the full suite**

Run: `./.venv/Scripts/python.exe -m pytest -q --no-cov`
Expected: all pass (modulo pre-existing stablecoin_peg order-dependent failures).

- [ ] **Step 3: Migration check**

Run: `./.venv/Scripts/python.exe manage.py makemigrations --check --dry-run`
Expected: "No changes detected".

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/workflows/test_crypto_exchange_persistence.py
git commit -m "test: end-to-end unified model regression (quote-fee buy)"
```

---

## Final: PR

- [ ] Open PR with `needs-approval`. Title: `refactor(crypto): unified trade cash-flow model (p×q±commission, no stored cash_flow on trades)`. Reference the spec. Note: re-import required for historical data.

---

## Self-Review

**Spec coverage:**
- Unified invariant (p×q±commission == settlement) → Task 2 (effective price), Tasks 4-5 (calc).
- cash_flow removed from trade rows → Task 3 (persist), Task 2 (leg).
- Broker cash_precision → Task 1 (schema), Tasks 4-5 (rounding).
- Price field 9dp → already done (no task needed; verified at common/models.py:233).
- Calc-layer changes (total_cash_flow, nav.py) → Tasks 4-5.
- realized.py / positions.py unchanged → verified (no tasks touch them).
- Regression fixtures → Tasks 2, 4, 6.

**Placeholder scan:** Steps 5 in Tasks 2 and 4 say "READ the test file" and "fix any regressions" — these are necessary because the exact stale assertions depend on the prior PRs' test state, which the implementer must inspect. The new test code and implementation code are complete. ✓

**Type consistency:** `cash_precision` (Task 1) → used in Tasks 4-5. `quote_cash_amount` (Task 2 `_spot_legs` param) → already threaded from the adapter (PR #35). `commission_currency` comparison (Tasks 4-5) → consistent field name. ✓
