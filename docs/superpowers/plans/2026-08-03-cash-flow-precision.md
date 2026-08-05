# cash_flow Precision (2dp → 9dp) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Increase `Transactions.cash_flow` precision from `decimal_places=2` to `decimal_places=9` so crypto stablecoin amounts (8dp) aren't truncated at persist time, eliminating the spurious nonzero `$0.00` balance residuals.

**Architecture:** One `AlterField` migration on `Transactions.cash_flow`: `max_digits=10, decimal_places=2` → `max_digits=16, decimal_places=9`. Display is unaffected (`format_value`'s generic fallback already rounds to the user's `digits` setting for presentation). `_normalize_decimal_field` reads `decimal_places` dynamically from the field, so it automatically preserves the new precision.

**Tech Stack:** Django migration, DecimalField.

## Global Constraints

- **Decimal only** — never float.
- Schema change is a precision **increase** (existing 2dp values gain trailing zeros; no data loss).
- All commands from `backend/`. Tests: `./.venv/Scripts/python.exe -m pytest <path> -q --no-cov`.
- Git identity: YL-STARDESTROYER / yaroslav.linik@gmail.com.

## Background

`cash_flow` is `DecimalField(max_digits=10, decimal_places=2)`. Crypto stablecoin amounts carry 8dp (e.g. USDC `99.69064956`). At persist, `_normalize_decimal_field` quantizes to the field's `decimal_places=2`, truncating `99.69064956` → `99.69`. Symmetric in/out flows then leave rounding residuals that display as nonzero `$0.00` instead of `–` (the zero sentinel). The `quantity` and `commission` fields are already `decimal_places=9`; only `cash_flow` lags.

**Why `max_digits=16`:** with `decimal_places=9`, the field needs enough integer digits for large cash flows (the user's largest is ~30000 USDT = 5 integer digits). `16 - 9 = 7` integer digits → supports up to 9,999,999. Headroom for any realistic cash flow.

---

## Task 1: Increase cash_flow precision + regression test

**Files:**
- Modify: `backend/common/models.py:244` (the `cash_flow` field)
- Create: migration (run `makemigrations`, use whatever number it generates)
- Test: `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`

- [ ] **Step 1: Write the failing regression test (RED)**

Add to `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`:

```python
@pytest.mark.django_db
def test_cash_flow_preserves_full_precision(user, crypto_account):
    """Regression for issue #32: cash_flow must preserve 8dp stablecoin amounts
    (not truncate to 2dp), so symmetric in/out flows net to exactly zero."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    # A USDT cash-in of 99.69064956 (8dp stablecoin amount).
    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:cf-precision",
        group_id="cf-precision",
        timestamp_ms=1738454400000,
        category="deposit",
        raw_type="transfer",
        legs=_single_leg("USDT", Decimal("99.69064956"), "USDT"),
        fee=None,
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    tx = Transactions.objects.get(investor=user, account=crypto_account)
    # Full 8dp preserved — NOT truncated to 99.69.
    assert tx.cash_flow == Decimal("99.69064956")
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py::test_cash_flow_preserves_full_precision -q --no-cov`
Expected: FAIL — `tx.cash_flow == Decimal("99.69")` (truncated to 2dp).

- [ ] **Step 3: Increase the field precision**

In `backend/common/models.py`, change the `cash_flow` field (line 244) from:

```python
    cash_flow = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
```

to:

```python
    cash_flow = models.DecimalField(max_digits=16, decimal_places=9, null=True, blank=True)
```

- [ ] **Step 4: Generate and apply the migration**

Run: `./.venv/Scripts/python.exe manage.py makemigrations common`
Expected: a new migration with `AlterField` on `model_name="transaction"`, `name="cash_flow"`. Inspect it — must be a single `AlterField`, nothing else.

Run: `./.venv/Scripts/python.exe manage.py migrate common`
Expected: `Applying common.009X_... OK`.

- [ ] **Step 5: Run the test to verify it passes (GREEN)**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py::test_cash_flow_preserves_full_precision -q --no-cov`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `./.venv/Scripts/python.exe -m pytest -q --no-cov`
Expected: same pass count as before (modulo the 2 pre-existing stablecoin_peg order-dependent failures). No regression — the display layer rounds to `digits` for presentation, so the extra stored precision is invisible to existing tests.

- [ ] **Step 7: Commit**

```bash
git add backend/common/models.py backend/common/migrations/<the_new_migration>.py backend/tests/integration/workflows/test_crypto_exchange_persistence.py
git commit -m "fix(schema): increase cash_flow precision to 9dp (#32)

The cash_flow field was decimal_places=2, truncating 8dp stablecoin amounts
(e.g. USDC 99.69064956 -> 99.69) and leaving rounding residuals that display
as nonzero \$0.00 instead of the zero sentinel. Increased to max_digits=16,
decimal_places=9 (matching quantity/commission). Display unaffected (rounds
to the user's digits setting for presentation)."
```

---

## Self-Review

**Spec coverage:** the precision increase → Task 1 Step 3; regression test → Steps 1-2; migration → Step 4. ✓

**Placeholder scan:** the migration filename in Step 7 is `<the_new_migration>.py` — this is intentional (makemigrations generates the number). The field code and test are complete. ✓

**Type consistency:** `max_digits=16, decimal_places=9` is consistent with `quantity` (25,9) and `commission` (15,9). `_normalize_decimal_field` reads `decimal_places` dynamically. ✓
