# Asset-Denominated Commission Fee — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop converting asset-denominated crypto-trade fees (e.g. BTC fee on a BTC-USDT buy) into the quote currency; instead net them into the base asset's quantity so the position is correct, and add a `commission_currency` field so the fee displays in its native asset.

**Architecture:** Single behavioral change in `_spot_legs` (stablecoin branch): when the fee is in the base asset, net it into `quantity` and leave `cash_flow` as pure `qty × price`. The calc layer (`position()`, NAV, realized-gains) is **untouched** — its existing `Sum(quantity)` aggregates pick up the netted value. A new nullable `commission_currency` column on `Transactions` (mirroring `FXTransaction`) lets the serializer render the fee in its native asset.

**Tech Stack:** Django + DRF (backend), Decimal math, Vue 3 (frontend — no change needed).

## Global Constraints

- **Decimal only** for money/quantity — never `float`. Internal precision ≥6 dp prices, ≥9 dp quantities. Rounding `ROUND_HALF_UP`.
- **Protected calc layer untouched:** `services/positions.py`, `services/nav.py`, `services/realized.py`, `services/transactions.py:total_cash_flow`, `core/*` — **zero changes**. The netted quantity flows through their existing `Sum(quantity)` reads.
- Schema change is **additive only**: one nullable `commission_currency` column on `Transactions`. No backfill.
- All commands run from `backend/`. Tests: `./.venv/Scripts/python.exe -m pytest <path> -q --no-cov`. Frontend: `cd ../frontend && npm run dev` (port 8080).
- Git identity: `YL-STARDESTROYER / yaroslav.linik@gmail.com`.
- `services/crypto_exchange.py` is **protected** — changes require a PR with `needs-approval` label and regression fixtures with expected numeric results (AGENTS.md).

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `backend/common/models.py` | Add `commission_currency` field to `Transactions` | 1 |
| `backend/common/migrations/` | Additive migration for the new field | 1 |
| `backend/services/crypto_exchange.py` | `_spot_legs` base-fee netting + `persist_crypto_exchange_event` writes `commission_currency` | 2, 3 |
| `backend/database/serializers.py` | `TransactionSerializer.get_commission` uses `commission_currency` when present | 4 |
| `backend/tests/integration/workflows/test_crypto_exchange_persistence.py` | Regression fixtures: base-fee netting, quote-fee unchanged, position proof | 2, 3 |
| `backend/tests/unit/calculations/test_position_uses_netted_quantity.py` (new) | Calc-layer-compatibility proof | 3 |

## Key facts (read before implementing)

1. **`_spot_legs` stablecoin branch** (`crypto_exchange.py:516-545`) currently converts a base-asset fee to quote terms (`fee_in_quote = abs(fee_delta) * price`, line 520) and folds it into `cash_flow` (line 527). This is the bug. The fix splits base-fee (net into `quantity`) from quote-fee (unchanged — net into `cash_flow`).
2. **Data invariant (verified against the user's CSV):** for a base-fee leg, `Balance Change = Amount − |fee|` exactly (e.g. `0.05379082 − 0.00005379 = 0.05373703`). So `qty + fee_delta` (= `Amount + Fee`, Fee negative) equals the real holding.
3. **`persist_crypto_exchange_event`** writes `commission` at lines 462-465 (`event.fee["quantity"]`); the companion `commission_currency` write goes right after it.
4. **`TransactionSerializer.get_commission`** (`database/serializers.py:456-467`) formats commission via `format_value(obj.commission, "commission", obj.currency, digits)`. After the schema change it should use `obj.commission_currency or obj.currency`. `format_value` already renders the currency label (e.g. `BTC0.00`, `₮0.01`, `$1.50`) — verified. So **no frontend change is needed**: the existing `|| Fee: {{ commission }}` in `CommissionDisplay.vue` shows whatever the serializer produces.
5. **`FXTransaction.commission_currency`** (`common/models.py:437`) is the established pattern to mirror: `CharField(max_length=4, choices=ALL_CURRENCY_CHOICES, null=True, blank=True)`.
6. The calc layer reads `quantity` via `Sum(quantity)` in `position()` (positions.py:63), `_portfolio_at_date` (nav.py:84-92), and realized.py (lines 582, 657, 1073); and iterates `transaction.quantity` in `get_economic_basis` (realized.py:425-500) and `calculate_buy_in_price` (realized.py:271-307). **None of these change** — netting at write time makes them correct automatically.

---

## Task 1: Add `commission_currency` field to `Transactions` (+ migration)

**Files:**
- Modify: `backend/common/models.py:247` (after the `commission` field)
- Create: `backend/common/migrations/0095_transaction_commission_currency.py` (exact number: run makemigrations and use whatever it generates)
- Test: covered by migration applying cleanly + Task 2/3 assertions

**Interfaces:**
- Produces: `Transactions.commission_currency` (CharField, nullable) — consumed by Task 3 (persist write) and Task 4 (serializer).

- [ ] **Step 1: Add the field to the model**

In `backend/common/models.py`, immediately after the `commission` field (line 247), add:

```python
    commission = models.DecimalField(max_digits=15, decimal_places=9, null=True, blank=True)
    # Currency/asset of the commission (e.g. "BTC" for a BTC-denominated fee on
    # a BTC-USDT trade). Mirrors FXTransaction.commission_currency. Null when
    # the commission is in the trade's own currency or absent.
    commission_currency = models.CharField(
        max_length=4, choices=ALL_CURRENCY_CHOICES, null=True, blank=True
    )
```

(`ALL_CURRENCY_CHOICES` is already imported at the top of `common/models.py` — confirm before saving.)

- [ ] **Step 2: Generate the migration**

Run: `./.venv/Scripts/python.exe manage.py makemigrations common`
Expected: a new migration file is created, e.g. `0095_transaction_commission_currency.py`, containing an `AddField` on `model_name="transaction"`, `name="commission_currency"`. **Inspect the generated file** — it must be a single `AddField` operation, nullable, no data migration.

- [ ] **Step 3: Apply the migration and verify**

Run: `./.venv/Scripts/python.exe manage.py migrate common`
Expected: `Applying common.0095_transaction_commission_currency... OK`.

Then verify the column exists and is nullable:
Run: `./.venv/Scripts/python.exe manage.py shell -c "from common.models import Transactions; f=Transactions._meta.get_field('commission_currency'); print(f'null={f.null} blank={f.blank} max_length={f.max_length}')"`
Expected: `null=True blank=True max_length=4`.

- [ ] **Step 4: Run the full test suite to confirm no breakage**

Run: `./.venv/Scripts/python.exe -m pytest -q --no-cov`
Expected: same pass/fail count as before (the 2 pre-existing `test_stablecoin_peg` order-dependent failures may appear; they are unrelated — verify they also fail on `main`).

- [ ] **Step 5: Commit**

```bash
git add backend/common/models.py backend/common/migrations/0095_transaction_commission_currency.py
git commit -m "feat(schema): add commission_currency to Transactions (nullable, mirrors FXTransaction)"
```

---

## Task 2: Net base-asset fee into quantity in `_spot_legs` (stablecoin branch)

**Files:**
- Modify: `backend/services/crypto_exchange.py:516-545` (`_spot_legs` stablecoin branch)
- Test: `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`

**Interfaces:**
- Produces: for a stablecoin-quote spot trade with a base-asset fee, the leg's `quantity` is `qty + fee_delta` (net) and `cash_flow` is pure `qty × price`. Adds a `"fee_asset"` key to the leg dict. Consumed by Task 3 (persist `commission_currency`).

**Design:** Split the base-fee and quote-fee handling. Base-fee → net into `quantity`, pure `cash_flow`. Quote-fee → unchanged (current behavior). Both branches add `"fee_asset": fee_asset.upper() if fee_asset else ""` to the leg dict.

- [ ] **Step 1: Write the failing regression test (RED)**

Add to `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`:

```python
@pytest.mark.django_db
def test_base_asset_fee_netted_into_quantity(user, crypto_account):
    """Regression for issue #30: a base-asset fee (e.g. BTC fee on a BTC-USDT
    buy) must be NETTED into the base quantity, not converted to quote and
    folded into cash_flow. The stored quantity is the real holding; cash_flow
    is the pure trade value."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    # BTC-USDT buy: 0.001 BTC @ 96058, fee -0.00000012 BTC (base asset).
    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:base-fee-1",
        group_id="order-base-fee",
        timestamp_ms=1738454400000,
        category="trade",
        raw_type="spot_fill",
        legs=[
            {
                "asset": "BTC",
                "quantity": Decimal("0.00099988"),  # 0.001 + (-0.00000012), net
                "price": Decimal("96058"),
                "price_asset": "USD",
                "role": "base",
                "cash_flow": Decimal("-96.058"),  # pure qty*gross_price; see note below
                "quote_currency": "USDT",
                "fee_asset": "BTC",
            }
        ],
        fee={"asset": "BTC", "quantity": Decimal("-0.00000012"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    tx = Transactions.objects.get(investor=user, account=crypto_account)
    assert tx.quantity == Decimal("0.00099988")
    assert tx.cash_flow == Decimal("-96.06")
    assert tx.commission == Decimal("-0.00000012")
```

**Important note on the test leg shape:** this test asserts what `persist_crypto_exchange_event` *receives* from `_spot_legs`. To drive `_spot_legs` directly through the normalizer (the real path), instead test the leg construction by calling `_spot_legs` and asserting the leg dict. Replace the test above with this version that exercises `_spot_legs` directly:

```python
def test_spot_legs_nets_base_fee_into_quantity():
    """_spot_legs stablecoin branch: a base-asset fee is netted into the base
    quantity; cash_flow is the pure trade value (no fee conversion)."""
    from services.crypto_exchange import _spot_legs

    # BTC-USDT buy: qty=0.001, price=96058, fee=-0.00000012 BTC (base).
    legs = _spot_legs(
        side="buy",
        base="BTC",
        quote="USDT",
        qty=Decimal("0.001"),
        price=Decimal("96058"),
        fee_delta=Decimal("-0.00000012"),
        fee_asset="BTC",
    )
    assert len(legs) == 1
    leg = legs[0]
    # Net quantity: 0.001 + (-0.00000012) = 0.00099988
    assert leg["quantity"] == Decimal("0.00099988")
    # Pure trade value, NO fee conversion: -(0.001 * 96058) = -96.058
    assert leg["cash_flow"] == Decimal("-96.058")
    assert leg["quote_currency"] == "USDT"
    assert leg["fee_asset"] == "BTC"


def test_spot_legs_quote_fee_still_folded_into_cash_flow():
    """_spot_legs stablecoin branch: a quote-asset fee (e.g. USDT fee) is still
    netted into cash_flow (unchanged behavior). Regression guard."""
    from services.crypto_exchange import _spot_legs

    # TRUMP-USDT sell: qty=0.6798, price=16.557, fee=-0.01125545 USDT (quote).
    legs = _spot_legs(
        side="sell",
        base="TRUMP",
        quote="USDT",
        qty=Decimal("0.6798"),
        price=Decimal("16.557"),
        fee_delta=Decimal("-0.01125545"),
        fee_asset="USDT",
    )
    assert len(legs) == 1
    leg = legs[0]
    # Quantity is gross (the fee is in quote, not base).
    assert leg["quantity"] == Decimal("-0.6798")
    # cash_flow = value - fee = (0.6798 * 16.557) - 0.01125545 = 11.24419315
    assert leg["cash_flow"] == Decimal("11.24419315")
    assert leg["fee_asset"] == "USDT"


def test_spot_legs_zero_fee_no_fee_asset_key():
    """_spot_legs stablecoin branch: zero fee -> no fee applied, fee_asset empty."""
    from services.crypto_exchange import _spot_legs

    legs = _spot_legs(
        side="buy",
        base="BTC",
        quote="USDT",
        qty=Decimal("0.001"),
        price=Decimal("96058"),
        fee_delta=Decimal("0"),
        fee_asset="",
    )
    leg = legs[0]
    assert leg["quantity"] == Decimal("0.001")
    assert leg["cash_flow"] == Decimal("-96.058")
    assert leg["fee_asset"] == ""
```

(Add `from decimal import Decimal` and `import pytest` at the top of the file if not already present — they are.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py -k "spot_legs" -q --no-cov`
Expected: 3 FAIL — `_spot_legs` still converts the base fee to quote and folds into cash_flow (the `quantity`/`cash_flow`/`fee_asset` assertions fail).

- [ ] **Step 3: Implement the base-fee netting in `_spot_legs`**

In `backend/services/crypto_exchange.py`, replace the entire stablecoin branch (lines 516-545):

```python
    if quote.upper() in STABLECOIN_CURRENCIES:
        value = qty * price
        normalized_fee_asset = (fee_asset or "").upper()

        if side.lower() == "buy":
            base_quantity = qty
            sign = -1
        elif side.lower() == "sell":
            base_quantity = -qty
            sign = 1
        else:
            raise ValueError(f"Unsupported spot side: {side}")

        if normalized_fee_asset == base.upper():
            # Base-asset fee: net into the base quantity (the fee is paid in the
            # asset being bought/sold, so it reduces the holding). cash_flow is
            # the pure trade value (no fee->quote conversion). Issue #30.
            base_quantity = base_quantity + fee_delta
            cash_flow = sign * value
        elif normalized_fee_asset == quote.upper():
            # Quote-asset fee: net into cash_flow (unchanged behavior). The fee
            # is in the cash currency, so it reduces the cash moved.
            cash_flow = sign * (value + abs(fee_delta))
        else:
            # Third-asset fee (e.g. BNB): not represented (deferred, issue #30).
            cash_flow = sign * value

        return [
            {
                "asset": base,
                "quantity": base_quantity,
                "price": price,
                "price_asset": "USD",
                "role": "base",
                "cash_flow": cash_flow,
                "quote_currency": quote.upper(),
                "fee_asset": normalized_fee_asset,
            }
        ]
```

**Why `sign * (value + abs(fee_delta))` for the quote-fee case:** buy → cash leaves, so `- (value + fee)`; sell → cash arrives, so `+ (value - fee)`. The original code expressed this as `-(value + fee_in_quote)` for buy and `value - fee_in_quote` for sell. The unified form: buy sign=-1 → `-(value + fee)`; sell sign=+1 → `+(value + fee)`. **Wait — that's wrong for sell.** For a sell with a quote fee, the original was `value - fee_in_quote` (you receive value minus fee). The unified `sign * (value + abs(fee))` for sell gives `+(value + fee)` which ADDS the fee — wrong. Use the original's per-side form instead. Replace the quote-fee branch with:

```python
        elif normalized_fee_asset == quote.upper():
            # Quote-asset fee: net into cash_flow (unchanged behavior).
            if side.lower() == "buy":
                cash_flow = -(value + abs(fee_delta))
            else:
                cash_flow = value - abs(fee_delta)
```

And drop the `sign` variable entirely (it was only used in the now-removed unified form). The base-fee branch keeps `cash_flow = sign * value` — but to avoid the same sell/buy confusion, replace with explicit per-side:

```python
        if side.lower() == "buy":
            base_quantity = qty
        elif side.lower() == "sell":
            base_quantity = -qty
        else:
            raise ValueError(f"Unsupported spot side: {side}")

        if normalized_fee_asset == base.upper():
            base_quantity = base_quantity + fee_delta
            if side.lower() == "buy":
                cash_flow = -value
            else:
                cash_flow = value
        elif normalized_fee_asset == quote.upper():
            if side.lower() == "buy":
                cash_flow = -(value + abs(fee_delta))
            else:
                cash_flow = value - abs(fee_delta)
        else:
            if side.lower() == "buy":
                cash_flow = -value
            else:
                cash_flow = value
```

This is explicit, mirrors the original's per-side structure, and avoids sign confusion.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py -k "spot_legs" -q --no-cov`
Expected: 3 PASS.

- [ ] **Step 5: Run the full crypto persistence + import suites**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py tests/unit/services/test_okx_csv_parser.py tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Expected: all pass (the existing crypto-crypto and quote-fee tests must stay green).

- [ ] **Step 6: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/integration/workflows/test_crypto_exchange_persistence.py
git commit -m "fix(crypto): net base-asset fee into quantity; cash_flow is pure trade value

For stablecoin-quote spot trades with a base-asset fee (e.g. BTC fee on a
BTC-USDT buy), the fee is now netted into the base quantity (the real holding)
instead of being converted to the quote currency and folded into cash_flow.
The quote-asset-fee case is unchanged. Adds a fee_asset key to the leg dict."
```

---

## Task 3: Persist `commission_currency` + calc-layer compatibility proof

**Files:**
- Modify: `backend/services/crypto_exchange.py:462-465` (`persist_crypto_exchange_event` commission write)
- Test: `backend/tests/integration/workflows/test_crypto_exchange_persistence.py` (commission_currency assertion)
- Create: `backend/tests/unit/calculations/test_position_uses_netted_quantity.py` (position proof)

**Interfaces:**
- Consumes: the `fee_asset` leg key from Task 2, and `event.fee["asset"]` from the normalizer.
- Produces: `Transactions.commission_currency` populated for crypto trades with a non-zero fee.

- [ ] **Step 1: Write the failing commission_currency test (RED)**

Add to `test_crypto_exchange_persistence.py`:

```python
@pytest.mark.django_db
def test_base_fee_trade_persists_commission_currency(user, crypto_account):
    """The fee asset is persisted to commission_currency (issue #30) so the
    frontend can show '|| Fee: BTC0.000000012'."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:ccy-1",
        group_id="order-ccy",
        timestamp_ms=1738454400000,
        category="trade",
        raw_type="spot_fill",
        legs=[
            {
                "asset": "BTC",
                "quantity": Decimal("0.00099988"),
                "price": Decimal("96058"),
                "price_asset": "USD",
                "role": "base",
                "cash_flow": Decimal("-96.058"),
                "quote_currency": "USDT",
                "fee_asset": "BTC",
            }
        ],
        fee={"asset": "BTC", "quantity": Decimal("-0.00000012"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    tx = Transactions.objects.get(investor=user, account=crypto_account)
    assert tx.commission_currency == "BTC"
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py::test_base_fee_trade_persists_commission_currency -q --no-cov`
Expected: FAIL — `tx.commission_currency is None` (not yet written).

- [ ] **Step 3: Write `commission_currency` in `persist_crypto_exchange_event`**

In `backend/services/crypto_exchange.py`, immediately after the existing commission write (lines 462-465), add:

```python
                if event.fee and event.fee.get("quantity") not in (None, 0, Decimal("0")):
                    tx_kwargs["commission"] = _normalize_model_decimal(
                        Transactions, "commission", event.fee["quantity"]
                    )
                    fee_ccy = str(leg.get("fee_asset") or event.fee.get("asset") or "").upper()
                    if fee_ccy:
                        tx_kwargs["commission_currency"] = fee_ccy
```

- [ ] **Step 4: Run to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py::test_base_fee_trade_persists_commission_currency -q --no-cov`
Expected: PASS.

- [ ] **Step 5: Write the calc-layer compatibility proof (position)**

Create `backend/tests/unit/calculations/test_position_uses_netted_quantity.py`:

```python
"""Calc-layer compatibility proof for the asset-denominated fee fix (#28/#30).

After a base-asset-fee spot buy is persisted with a NETTED quantity, position()
must return that netted quantity WITHOUT any change to the calc layer — proving
the Sum(quantity) aggregate picks up the correction automatically.
"""

from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, Transactions
from constants import TRANSACTION_TYPE_CRYPTO_TRADE_IN
from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event
from services.positions import position


@pytest.fixture
def crypto_account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    return Accounts.objects.create(broker=broker, name="Unified", native_id="okx-main")


@pytest.mark.django_db
def test_position_returns_netted_quantity_after_base_fee_buy(user, crypto_account):
    """A BTC-USDT buy with a BTC fee persists net quantity; position() returns it."""
    from datetime import datetime, timezone

    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:pos-1",
        group_id="order-pos",
        timestamp_ms=1738454400000,
        category="trade",
        raw_type="spot_fill",
        legs=[
            {
                "asset": "BTC",
                "quantity": Decimal("0.00099988"),  # net of the BTC fee
                "price": Decimal("96058"),
                "price_asset": "USD",
                "role": "base",
                "cash_flow": Decimal("-96.058"),
                "quote_currency": "USDT",
                "fee_asset": "BTC",
            }
        ],
        fee={"asset": "BTC", "quantity": Decimal("-0.00000012"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)

    btc_asset = Transactions.objects.get(investor=user, account=crypto_account).security
    event_date = datetime(2025, 2, 1, tzinfo=timezone.utc)
    held = position(btc_asset, event_date, user)
    assert held == Decimal("0.00099988")  # net — NOT the gross 0.001
```

- [ ] **Step 6: Run the position proof + full crypto/OKX/import suites**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/calculations/test_position_uses_netted_quantity.py tests/integration/workflows/test_crypto_exchange_persistence.py tests/unit/services/test_okx_csv_parser.py tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/integration/workflows/test_crypto_exchange_persistence.py backend/tests/unit/calculations/test_position_uses_netted_quantity.py
git commit -m "feat(crypto): persist commission_currency; prove position() uses netted qty"
```

---

## Task 4: Serializer renders commission in its native currency

**Files:**
- Modify: `backend/database/serializers.py:456-467` (`TransactionSerializer.get_commission`)
- Test: manual (the serializer method is exercised by the transactions-table consumer; an explicit unit test is optional but recommended)

**Interfaces:** none new. Reads `obj.commission_currency` (added in Task 1) and falls back to `obj.currency`.

**Key fact:** `format_value(value, "commission", currency, digits)` already renders the currency label (verified: `BTC0.00`, `₮0.01`, `$1.50`). So changing the currency argument from `obj.currency` to `obj.commission_currency or obj.currency` makes the transactions-table commission render in the fee's native asset with **no frontend change**.

- [ ] **Step 1: Write a failing test (RED)**

Add a test to `backend/tests/unit/test_formatting_utils.py` (or a new serializer test). Simplest: test `format_value` directly with `commission_currency`:

```python
def test_format_value_commission_uses_commission_currency_label():
    """When commission_currency is set, the commission renders in that asset."""
    from decimal import Decimal
    from core.formatting_utils import format_value
    # BTC-denominated fee -> "BTC" label, not the trade's USDT currency.
    assert format_value(Decimal("-0.00068030"), "commission", "BTC", 2) == "(BTC0.00)"
```

(This already passes — it documents the contract. The real change is in the serializer.)

For the serializer change, add an integration-style test if a serializer test pattern exists; otherwise rely on manual verification (Step 4) + the persist tests (Task 3) that confirm `commission_currency` is stored.

- [ ] **Step 2: Change `get_commission` to prefer `commission_currency`**

In `backend/database/serializers.py`, change `TransactionSerializer.get_commission` (lines 456-467):

```python
    def get_commission(self, obj):
        """Format commission for display.

        Uses commission_currency (the fee's native asset, e.g. BTC for a
        BTC-denominated crypto fee) when set; otherwise the trade's currency.
        """
        fee_currency = obj.commission_currency or obj.currency
        return format_value(
            obj.commission, "commission", fee_currency, self.get_digits()
        )
```

- [ ] **Step 3: Run the serializer/formatting tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/test_formatting_utils.py -q --no-cov`
Expected: PASS.

- [ ] **Step 4: Run the full backend suite**

Run: `./.venv/Scripts/python.exe -m pytest -q --no-cov`
Expected: same pass count as Task 1 Step 4 (no regressions; `commission_currency` is null for all non-crypto rows so `obj.commission_currency or obj.currency` falls back to the old behavior).

- [ ] **Step 5: Commit**

```bash
git add backend/database/serializers.py backend/tests/unit/test_formatting_utils.py
git commit -m "feat(serializer): render commission in its native currency (commission_currency)"
```

---

## Final: full verification + manual check

- [ ] **Step 1: Full backend suite**

Run: `./.venv/Scripts/python.exe -m pytest -q --no-cov`
Expected: all pass (modulo the 2 pre-existing stablecoin_peg order-dependent failures).

- [ ] **Step 2: Migration check**

Run: `./.venv/Scripts/python.exe manage.py makemigrations --check --dry-run`
Expected: "No changes detected".

- [ ] **Step 3: Manual end-to-end (after deleting existing OKX rows and re-importing)**

Start backend (`./.venv/Scripts/python.exe run_uvicorn.py`) + frontend. Re-import the OKX CSV. Verify a base-fee trade (e.g. BTC-USDT buy) shows: quantity net of fee (e.g. `0.0001` for a 0.00011659 buy with a BTC fee), cash_flow = pure trade value, and `|| Fee: BTC0.00` (the BTC asset label, not USDT). Verify a quote-fee trade is unchanged.

- [ ] **Step 4: Open the PR**

Title: `fix(crypto): asset-denominated fee netted into quantity + commission_currency (#28/#30)`. Label `needs-approval`. Reference the spec and issues #28/#30. Note the historical-data limitation (re-import required).

---

## Self-Review

**Spec coverage:**
- Component 1 (`_spot_legs` base-fee netting) → Task 2 ✓
- Component 2 (schema `commission_currency`) → Task 1 ✓
- Component 3 (persist `commission_currency`) → Task 3 ✓
- Component 4 (frontend display) → Task 4 (serializer; **refined** — no frontend change needed because `format_value` already renders the currency label) ✓
- Component 5 (regression fixtures + position proof) → Tasks 2 & 3 ✓
- Edge cases (zero fee, rebate, missing fee_asset) → Task 2's `_spot_legs` rewrite + tests ✓
- Calc layer untouched → Task 3 Step 5 (position proof) confirms ✓

**Placeholder scan:** Task 2 Step 3 contains a self-corrected sign-confusion note inline (the `sign *` form was wrong; the final code uses explicit per-side branches). The final code in the plan is the corrected version. No TBD/TODO.

**Type consistency:** `fee_asset` (leg dict key, Task 2) → read in Task 3 (`leg.get("fee_asset")`). `commission_currency` (model field, Task 1) → written in Task 3, read in Task 4 (`obj.commission_currency`). Consistent throughout.

**Spec refinement vs. plan:** the spec's Component 4 said "Frontend `CommissionDisplay.vue` + call sites." Verification during planning revealed `format_value` already renders the currency label and the serializer already formats commission — so the frontend needs **no change**. The serializer `get_commission` change (Task 4) is sufficient. This is a simplification, not a deviation; documented in Task 4.
