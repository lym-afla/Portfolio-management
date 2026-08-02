# OKX CSV Import — 8 Fixes Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 8 issues found during live testing of the OKX Trading History CSV import, so the user's actual 55-row CSV imports cleanly and displays correctly.

**Architecture:** Changes span three layers: the CSV adapter (`services/importer.py::build_okx_csv_events` + `parse_okx_trading_csv`), the crypto persistence (`services/crypto_exchange.py::persist_crypto_exchange_event` and the `normalize_okx_*` helpers), and the frontend display (`frontend/src/components/transactions/TransactionDescription.vue` + a new format helper). No schema/migration changes. All monetary math stays `Decimal`.

**Tech Stack:** Django + DRF (backend), pandas CSV parsing, Vue 3 + Vuetify (frontend), pytest (tests).

## Global Constraints

- **Decimal only** for money/price/quantity — never `float`. Internal precision ≥6 dp prices, ≥9 dp quantities. Rounding `ROUND_HALF_UP`.
- **No schema/migration changes.** No edits to `common/models.py` or calc-layer services (`core/portfolio_utils.py`, `core/transactions_utils.py`, etc.).
- **Protected logic** (`persist_crypto_exchange_event`, `normalize_okx_*`, `_spot_legs`) lives in `services/crypto_exchange.py` — changes here are financial-behavior changes requiring a PR with `needs-approval` label and unit tests + regression fixtures.
- All commands run from `backend/`. Tests: `./.venv/Scripts/python.exe -m pytest <path> -q --no-cov`. Frontend: `cd ../frontend && npm run dev` (port 8080).
- CSV file under test: the user's real export at `C:\Users\PC-Admin\Downloads\NzAyMjA3Mzg=~...\OKX Trading History_*.csv` (55 data rows: 36 spot, 2 option, 17 transfer).
- Git identity: `YL-STARDESTROYER / yaroslav.linik@gmail.com`. Auto-commit only non-protected formatting/test-only changes; open a PR for the protected-logic tasks.

## File Structure (what changes per file)

| File | Responsibility | Touched by tasks |
|---|---|---|
| `backend/services/importer.py` | CSV adapter (`build_okx_csv_events`), the async parser (`parse_okx_trading_csv`), FX dispatch | 1, 2, 6 |
| `backend/services/crypto_exchange.py` | `normalize_okx_spot_fill` (currency + fee propagation), `persist_crypto_exchange_event` (Buy/Sell type + currency), option settlement normalizer | 3, 4, 6, 8 |
| `backend/services/fx.py` (read-only ref) | existing `save_single_transaction` FX path | 2 |
| `frontend/src/components/transactions/TransactionDescription.vue` | transaction display format | 5, 7 |
| `frontend/src/utils/formatUtils.js` (new) | `formatQuantity` / `formatPrice` helpers | 7 |
| `backend/tests/unit/services/test_okx_csv_parser.py` | adapter + parser unit/integration tests | all backend tasks |
| `backend/tests/integration/workflows/test_crypto_exchange_persistence.py` | persist-layer regression tests | 3, 4, 8 |

## Decisions locked with the user

- **Task 1 (transfers):** Import **ALL** transfers. Stablecoin (USDT/USDC) Transfer in/out → `Cash in`/`Cash out`. Non-stablecoin (BTC, TRUMP) Transfer in/out → `Crypto transfer in`/`Crypto transfer out`.
- **Task 2 (CONVERT):** Split by quote. `USDC-USDT-CONVERT` (stablecoin↔stablecoin) → `FXTransaction`. `BTC-USDT-CONVERT` (crypto↔stablecoin) → normal spot trade via `normalize_okx_spot_fill`. Side inferred from the **sign of `Balance Change`** (CONVERT rows have empty `Action`).
- **Task 4 (types):** Stablecoin-quote single-leg spot trades → `Buy`/`Sell`. Crypto-crypto two-leg trades → keep `Crypto trade in`/`out`.
- **Task 8 (options):** Use the existing option machinery — option sell = an OPTION leg (±contracts) via `normalize_okx_option_fill`; expiry = settlement leg (collateral release) via `normalize_okx_option_settlement`. Do **not** model the option as raw BTC cash flows.

## Key facts discovered during analysis (read before implementing)

1. **`build_okx_csv_events` is a sync function** returning `(events, skipped_transfer_ids)`. The async `parse_okx_trading_csv` consumes it. The transfer/convert/FX dispatch must therefore happen inside `build_okx_csv_events` (or a new sibling helper it calls) so the parser just iterates `(payload, source_id)` tuples. **New payload kinds:** `"transfer"`, `"fx"`.
2. **`_normalize_okx_csv_event`** dispatches on `payload["__kind"]`. New kinds (`"transfer"`, `"fx"`) need branches. `"transfer"` builds a `CryptoExchangeEvent` directly (no shared normalizer exists for arbitrary transfer routing). `"fx"` does NOT go through `persist_crypto_exchange_event` at all — see Task 2.
3. **The fee is already mostly wired** (Task 6): `normalize_okx_spot_fill` reads `fee`/`feeCcy` and `_spot_legs` folds the fee into `cash_flow`. The bug is that `persist_crypto_exchange_event` never writes the `commission` field — the option-fill branch writes commission correctly via `event.fee`, but the **spot stablecoin-quote branch** drops the fee into `cash_flow` and never records `commission`. Verify against the actual symptom ("commission is None") before changing anything.
4. **Task 3 currency fix:** `persist_crypto_exchange_event` line ~429 hardcodes `currency="USD"` for the priced-leg branch. The stablecoin quote currency is NOT currently carried on the leg dict. `_spot_legs` must add a `quote_currency` key, and the persist branch must read it (defaulting to `"USD"`).
5. **The CSV's `Amount` is `0` for transfer rows** — the real amount is the signed `Balance Change`. Parse from `Balance Change`.
6. **Several existing tests encode the OLD behavior** and MUST be updated, not deleted: `test_convert_symbols_are_skipped`, `test_transfer_rows_are_skipped_and_not_emitted_as_events`, `test_full_parser_counts_transfers_as_skipped`. Updating a test that asserts old behavior is part of each task, not an afterthought.
7. **Option sell row** (`BTC-USD-260605-80000-C`, Sell 7 @ 0.0022 BTC): `Amount=7` contracts, `Balance Change=-0.00701889 BTC` (net outflow incl. margin blocked), `Fee=-0.00001078 BTC`. The fill price is in BTC. `_leg_fiat_price` will try to convert `0.0022 BTC` to USD via the BTC/USD quote-asset price lookup — this already works for crypto-denominated option premiums (the `price == Decimal("1")` / `_quote_asset_fiat_price` path). Confirm with a regression test.
8. **Option expiry row** (`Action=Expired OTM`): `Position Change=-0.00716211` (7 contracts removed), `Balance Change=+0.00716211` (collateral released). The settlement normalizer currently maps `balChg = Position Change` — but for an OTM expiry the **collateral release is `Balance Change` (+0.00716211)**, not `Position Change` (-0.00716211). Using `Position Change` would record a BTC *outflow* on expiry, which is wrong. **Task 8 fixes this mapping.**

---

## Task 1: Import transfers (stablecoin→cash, crypto→crypto-transfer)

**Files:**
- Modify: `backend/services/importer.py:690-833` (`build_okx_csv_events`) and `665-688` (`_normalize_okx_csv_event`)
- Test: `backend/tests/unit/services/test_okx_csv_parser.py`

**Interfaces:**
- Produces: a new payload kind `"transfer"` consumed by `_normalize_okx_csv_event`, which returns a `CryptoExchangeEvent` with `category="deposit"` (Transfer in, stablecoin) / `"withdrawal"` (Transfer out, stablecoin) / `"transfer"` (non-stablecoin either direction). The stablecoin categories already route to cash via `persist_crypto_exchange_event`'s `_is_stablecoin_cash_leg` + `_cash_tx_type_for_category`. Non-stablecoin `category="transfer"` already routes to `Crypto transfer in/out` via `_transaction_type_for_event`.

**Design:** Transfer rows have `Amount=0`; the signed amount is `Balance Change`. The leg asset is `Balance Unit`. For stablecoins the existing cash-routing needs `category` in `{"deposit","withdrawal","reward"}` (see `STABLECOIN_CASH_CATEGORIES`); for non-stablecoins `category="transfer"` gives `Crypto transfer in/out`. So: stablecoin Transfer in → `deposit`, stablecoin Transfer out → `withdrawal`, any non-stablecoin → `transfer`.

- [ ] **Step 1: Update the existing transfer-skipped tests to the new behavior (RED)**

In `test_okx_csv_parser.py`, replace `test_transfer_rows_are_skipped_and_not_emitted_as_events` with a new test asserting transfers are now EMITTED, and add a stablecoin + crypto case. Replace the body of `test_transfer_rows_are_skipped_and_not_emitted_as_events` with:

```python
def test_transfer_rows_become_events_not_skipped():
    """Transfers are now imported: stablecoins route to cash (deposit/withdrawal),
    non-stablecoins route to crypto transfers. Nothing is skipped."""
    rows = [
        # non-stablecoin transfer out (BTC)
        {
            "id": "3679092537441165312", "Order id": "3679092536973701120",
            "Time": "2026-06-22 20:05:01", "Trade Type": "Transfer", "Symbol": "",
            "Action": "Transfer out", "Amount": "0", "Trading Unit": "cont",
            "Filled Price": "0.00000000", "PnL": "0.0", "Fee": "0.00000000",
            "Fee Unit": "BTC", "Position Change": "0.0", "Position Balance": "0.0",
            "Balance Change": "-0.45849457", "Balance": "0.0", "Balance Unit": "BTC",
        },
        # stablecoin transfer out (USDT) -> withdrawal
        {
            "id": "3679091815014244352", "Order id": "3679091814748102656",
            "Time": "2026-06-22 20:04:40", "Trade Type": "Transfer", "Symbol": "",
            "Action": "Transfer out", "Amount": "0", "Trading Unit": "cont",
            "Filled Price": "0.00000000", "PnL": "0.0", "Fee": "0.00000000",
            "Fee Unit": "USDT", "Position Change": "0.0", "Position Balance": "0.0",
            "Balance Change": "-300.00389139", "Balance": "0.0", "Balance Unit": "USDT",
        },
        # stablecoin transfer in (USDT) -> deposit
        {
            "id": "2173839971167281152", "Order id": "2173839971033657344",
            "Time": "2025-01-19 14:57:59", "Trade Type": "Transfer", "Symbol": "",
            "Action": "Transfer in", "Amount": "0", "Trading Unit": "cont",
            "Filled Price": "0.00000000", "PnL": "0.0", "Fee": "0.00000000",
            "Fee Unit": "USDT", "Position Change": "0.0", "Position Balance": "0.0",
            "Balance Change": "357.14000000", "Balance": "357.14", "Balance Unit": "USDT",
        },
    ]
    df = _df_from_rows(rows)
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    assert skipped == []  # nothing skipped anymore
    assert len(events) == 3
    kinds = [e[0]["__kind"] for e in events]
    assert kinds == ["transfer", "transfer", "transfer"]
    # Stablecoin in -> deposit; stablecoin out -> withdrawal; BTC out -> transfer.
    cats = [e[0]["category"] for e in events]
    assert cats == ["transfer", "withdrawal", "deposit"]
    # Signed amount parsed from Balance Change, not Amount.
    amts = [e[0]["amount"] for e in events]
    assert amts == ["-0.45849457", "-300.00389139", "357.14000000"]
    ccys = [e[0]["ccy"] for e in events]
    assert ccys == ["BTC", "USDT", "USDT"]
```

Also update `test_mixed_csv_emits_events_and_skips_transfers` (lines ~414-440): the transfer it includes should now appear in `events` (not `skipped`). Change the final assertions to `assert len(events) == 3` and `assert skipped == []`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/services/test_okx_csv_parser.py -q --no-cov -k "transfer or mixed"`
Expected: FAIL — `build_okx_csv_events` still appends to `skipped_transfer_ids` and emits no events for transfers.

- [ ] **Step 3: Implement transfer handling in `build_okx_csv_events`**

In `services/importer.py`, replace the `if trade_type == "Transfer":` block (lines ~722-724) with:

```python
if trade_type == "Transfer":
    balance_unit = (_strip_okx_bom(row.get("Balance Unit")) or "").upper()
    action = str(row.get("Action") or "").strip().lower()
    # Transfer rows carry Amount=0; the signed movement is Balance Change.
    amount = Decimal(str(row.get("Balance Change") or "0"))
    is_stablecoin = balance_unit in {"USDT", "USDC"}
    if is_stablecoin:
        # Stablecoin in -> deposit (Cash in); out -> withdrawal (Cash out).
        category = "deposit" if "in" in action else "withdrawal"
    else:
        # Non-stablecoin (BTC/TRUMP) internal moves stay crypto transfers.
        category = "transfer"
    payload = {
        "__kind": "transfer",
        "category": category,
        "ccy": balance_unit,
        "amount": str(amount),
        "ts": str(fill_time),
        "billId": str(row_id),
    }
    events.append((payload, str(row_id)))
    continue
```

- [ ] **Step 4: Add the `"transfer"` branch to `_normalize_okx_csv_event`**

In `_normalize_okx_csv_event` (lines ~665-688), after the `kind == "option_settlement"` branch, build the event directly (no shared normalizer). Replace the function body's dispatch so it handles the new kind. Add this import at top of the function's body alongside the existing imports:

```python
    if kind == "transfer":
        ccy = payload["ccy"].upper()
        amount = Decimal(payload["amount"])
        category = payload["category"]
        return CryptoExchangeEvent(
            provider=OKX_CSV_IMPORT_PROVIDER,
            provider_event_id=f"csv_transfer:{payload['billId']}",
            group_id=payload["billId"],
            timestamp_ms=int(payload["ts"]),
            category=category,
            raw_type="transfer",
            legs=_single_leg(ccy, amount, ccy),
        )
```

This requires importing `CryptoExchangeEvent` and `_single_leg` — add them to the existing `from services.crypto_exchange import (...)` block inside the function (lines ~673-677).

- [ ] **Step 5: Update the integration test `test_full_parser_counts_transfers_as_skipped`**

Rename to `test_full_parser_imports_transfers` and rewrite the assertions. The transfer in the fixture is BTC (non-stablecoin) → it should now be imported as a `Crypto transfer out`, not skipped:

```python
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_full_parser_imports_transfers(tmp_path, user, okx_account):
    rows = _spot_buy_pair() + [
        {
            "id": "3679092537441165312", "Order id": "3679092536973701120",
            "Time": "2026-06-22 20:05:01", "Trade Type": "Transfer", "Symbol": "",
            "Action": "Transfer out", "Amount": "0", "Trading Unit": "cont",
            "Filled Price": "0.00000000", "PnL": "0.0", "Fee": "0.00000000",
            "Fee Unit": "BTC", "Position Change": "0.0", "Position Balance": "0.0",
            "Balance Change": "-0.45849457", "Balance": "0.0", "Balance Unit": "BTC",
        },
    ]
    csv_path = tmp_path / "okx.csv"
    _write_okx_csv(csv_path, rows)
    updates = await _drain(
        parse_okx_trading_csv(str(csv_path), okx_account.id, user.id, confirm_every=False)
    )
    complete = next(u for u in updates if u.get("status") == "complete")
    # 1 spot event (2 legs) + 1 transfer event (1 leg) -> 3 persisted, 0 skipped.
    assert complete["data"]["skippedTransactions"] == 0
    assert complete["data"]["importedTransactions"] == 3
    txs = await _persisted_txs(user, okx_account)
    assert len(txs) == 3
    # The BTC transfer is a Crypto transfer out (quantity negative).
    transfer_tx = next(t for t in txs if t.type == "Crypto transfer out")
    assert transfer_tx.quantity == Decimal("-0.45849457")
```

- [ ] **Step 6: Run all OKX parser tests; verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/services/test_okx_csv_parser.py -q --no-cov`
Expected: PASS (all tests including the updated transfer/mixed tests).

- [ ] **Step 7: Commit**

```bash
git add services/importer.py tests/unit/services/test_okx_csv_parser.py
git commit -m "feat(okx): import transfers as cash (stablecoin) or crypto-transfer"
```

---

## Task 3: Fix currency display (USDC/USDT instead of USD) for stablecoin-quote trades

**Files:**
- Modify: `backend/services/crypto_exchange.py:481-573` (`_spot_legs` — add `quote_currency` to the stablecoin leg) and `:416-444` (`persist_crypto_exchange_event` — read it)
- Test: `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`

**Interfaces:**
- Produces: a new optional `quote_currency` key on stablecoin-quote spot legs. `persist_crypto_exchange_event` reads `leg.get("quote_currency", "USD")` for the `currency` field. Crypto-crypto legs are unaffected (no `quote_currency` → defaults to `"USD"`).

**Why this is the fix:** Line ~429 hardcodes `currency="USD"`. For a `TRUMP-USDT` buy the cash actually leaves/arrives in USDT, so `currency` must be `"USDT"`. The quote currency is known in `_spot_legs` (`quote` argument) but not currently written onto the leg.

- [ ] **Step 1: Write a failing regression test (RED)**

Add to `test_crypto_exchange_persistence.py`:

```python
@pytest.mark.django_db
def test_stablecoin_quote_spot_trade_records_currency_as_stablecoin(user, crypto_account):
    """A BTC-USDT buy must persist currency='USDT' (the actual quote/cash
    currency), not 'USD'. Regression for OKX CSV issue #3."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:trade-1",
        group_id="order-1",
        timestamp_ms=1767225600000,
        category="trade",
        raw_type="spot_fill",
        legs=[
            {
                "asset": "BTC",
                "quantity": Decimal("0.001"),
                "price": Decimal("96058"),
                "price_asset": "USD",
                "role": "base",
                "cash_flow": Decimal("-96.058"),
                "quote_currency": "USDT",
            }
        ],
        fee={"asset": "BTC", "quantity": Decimal("0"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)

    tx = Transactions.objects.get(investor=user, account=crypto_account)
    assert tx.currency == "USDT"
```

- [ ] **Step 2: Run the test; verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py::test_stablecoin_quote_spot_trade_records_currency_as_stablecoin -q --no-cov`
Expected: FAIL — `tx.currency == "USD"`.

- [ ] **Step 3: Add `quote_currency` to the stablecoin leg in `_spot_legs`**

In `services/crypto_exchange.py`, inside the `if quote.upper() in STABLECOIN_CURRENCIES:` branch (lines ~495-523), add `"quote_currency": quote.upper(),` to the single leg dict (alongside `"cash_flow": cash_flow`):

```python
        return [
            {
                "asset": base,
                "quantity": base_quantity,
                "price": price,
                "price_asset": "USD",
                "role": "base",
                "cash_flow": cash_flow,
                "quote_currency": quote.upper(),
            }
        ]
```

- [ ] **Step 4: Read `quote_currency` in `persist_crypto_exchange_event`**

Change line ~429 in `persist_crypto_exchange_event` from `currency="USD",` to:

```python
                    currency=str(leg.get("quote_currency") or "USD").upper(),
```

(Leave the crypto-crypto two-leg path producing `currency="USD"` — those legs have no `quote_currency` key, so the default applies.)

- [ ] **Step 5: Run the regression test; verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py -q --no-cov`
Expected: PASS (new test + all existing persist tests).

- [ ] **Step 6: Commit**

```bash
git add services/crypto_exchange.py tests/integration/workflows/test_crypto_exchange_persistence.py
git commit -m "fix(crypto): persist quote-currency (USDT/USDC) on stablecoin-quote trades"
```

---

## Task 4: Use Buy/Sell for stablecoin-quote trades; keep Crypto trade for crypto-crypto

**Depends on:** Task 3 (the `quote_currency` leg key is the signal that a leg is a stablecoin-quote cash trade).

**Files:**
- Modify: `backend/services/crypto_exchange.py:304-321` (`_transaction_type_for_event`) and `:416-444` (persist branch — pass leg context)
- Test: `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`

**Interfaces:**
- Produces: stablecoin-quote spot trades (single leg with `quote_currency` set) persist as `TRANSACTION_TYPE_BUY`/`TRANSACTION_TYPE_SELL`. Crypto-crypto trades (two legs, no `quote_currency`) keep `Crypto trade in`/`out`.

**Design:** `_transaction_type_for_event(event, quantity)` doesn't see the leg. Add an optional `leg` parameter; when the leg carries `quote_currency`, return Buy/Sell. Update the one call site (line ~421).

- [ ] **Step 1: Write a failing test (RED)**

Add to `test_crypto_exchange_persistence.py`:

```python
@pytest.mark.django_db
def test_stablecoin_quote_spot_buy_uses_buy_type(user, crypto_account):
    """Stablecoin-quote spot trades display/behave like cash purchases, so a
    buy is type='Buy' (not 'Crypto trade in'). Regression for OKX issue #4."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:trade-buy",
        group_id="order-buy",
        timestamp_ms=1767225600000,
        category="trade",
        raw_type="spot_fill",
        legs=[{
            "asset": "TRUMP", "quantity": Decimal("0.6803"),
            "price": Decimal("73.209"), "price_asset": "USD", "role": "base",
            "cash_flow": Decimal("-49.81"), "quote_currency": "USDT",
        }],
        fee={"asset": "TRUMP", "quantity": Decimal("-0.0006803"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    tx = Transactions.objects.get(investor=user, account=crypto_account)
    assert tx.type == "Buy"


@pytest.mark.django_db
def test_crypto_crypto_trade_keeps_crypto_trade_type(user, crypto_account):
    """Crypto-crypto pairs (two legs, no quote_currency) stay 'Crypto trade in/out'."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    event = CryptoExchangeEvent(
        provider="bybit",
        provider_event_id="exec-cc",
        group_id="order-cc",
        timestamp_ms=1767225600000,
        category="trade",
        raw_type="spot_execution",
        legs=[
            {"asset": "ETH", "quantity": Decimal("0.1"), "price": Decimal("0.0016"),
             "price_asset": "BTC", "role": "base"},
            {"asset": "BTC", "quantity": Decimal("-0.00016"), "price": Decimal("1"),
             "price_asset": "BTC", "role": "quote"},
        ],
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    types = {t.type for t in Transactions.objects.filter(investor=user, account=crypto_account)}
    assert types == {"Crypto trade in", "Crypto trade out"}
```

- [ ] **Step 2: Run; verify both fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py::test_stablecoin_quote_spot_buy_uses_buy_type tests/integration/workflows/test_crypto_exchange_persistence.py::test_crypto_crypto_trade_keeps_crypto_trade_type -q --no-cov`
Expected: FAIL — first asserts `Buy` but gets `Crypto trade in`; second already passes (sanity check it stays green).

- [ ] **Step 3: Add `leg` param to `_transaction_type_for_event`**

In `services/crypto_exchange.py`, change the signature and the trade branch:

```python
def _transaction_type_for_event(event, quantity, leg=None):
    category = (event.category or "").lower()
    raw_type = (event.raw_type or "").lower()
    if category == "reward":
        return TRANSACTION_TYPE_CRYPTO_REWARD
    if category == "settlement":
        return TRANSACTION_TYPE_OPTION_SETTLEMENT
    if category in {"transfer", "deposit", "withdrawal"} or raw_type in {
        "deposit",
        "withdrawal",
        "transfer",
    }:
        return (
            TRANSACTION_TYPE_CRYPTO_TRANSFER_IN
            if quantity > 0
            else TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT
        )
    # Stablecoin-quote spot trades behave like cash purchases (Buy/Sell);
    # they carry a quote_currency key on the leg (set by _spot_legs).
    if leg is not None and leg.get("quote_currency"):
        return TRANSACTION_TYPE_BUY if quantity > 0 else TRANSACTION_TYPE_SELL
    return TRANSACTION_TYPE_CRYPTO_TRADE_IN if quantity > 0 else TRANSACTION_TYPE_CRYPTO_TRADE_OUT
```

Add `TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL` to the `constants` import at the top of the file (lines ~15-26).

- [ ] **Step 4: Pass `leg` at the call site**

Line ~421, change:

```python
                tx_type = _transaction_type_for_event(event, quantity)
```

to:

```python
                tx_type = _transaction_type_for_event(event, quantity, leg=leg)
```

- [ ] **Step 5: Run tests; verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py tests/unit/services/test_okx_csv_parser.py -q --no-cov`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/crypto_exchange.py tests/integration/workflows/test_crypto_exchange_persistence.py
git commit -m "fix(crypto): use Buy/Sell types for stablecoin-quote spot trades"
```

---

## Task 6: Persist commission (fee) on stablecoin-quote spot trades

**Files:**
- Modify: `backend/services/crypto_exchange.py:416-444` (`persist_crypto_exchange_event` priced-leg branch)
- Test: `backend/tests/integration/workflows/test_crypto_exchange_persistence.py`

**Interfaces:** none new. Reads `event.fee` (already populated by the normalizer) and writes `commission` when present.

**Analysis (verify before coding):** The CSV adapter already maps `Fee`/`Fee Unit` → `fee`/`feeCcy`, and `normalize_okx_spot_fill` builds `event.fee`. For the stablecoin-quote single-leg path, `_spot_legs` folds the fee into `cash_flow` (so the cash balance is correct), but `persist_crypto_exchange_event` never writes `commission`. The fix: when `event.fee` exists and is non-zero, write it to `commission`. The fee quantity is in `event.fee["asset"]` terms (e.g. BTC) — store it as-is; the frontend `CommissionDisplay` shows the value with the asset.

- [ ] **Step 1: Write a failing test (RED)**

Add to `test_crypto_exchange_persistence.py`:

```python
@pytest.mark.django_db
def test_stablecoin_quote_spot_trade_records_commission(user, crypto_account):
    """The CSV Fee must land in the commission field, not be silently dropped.
    Regression for OKX issue #6."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event

    event = CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv:trade-fee",
        group_id="order-fee",
        timestamp_ms=1767225600000,
        category="trade",
        raw_type="spot_fill",
        legs=[{
            "asset": "TRUMP", "quantity": Decimal("0.6803"),
            "price": Decimal("73.209"), "price_asset": "USD", "role": "base",
            "cash_flow": Decimal("-49.81"), "quote_currency": "USDT",
        }],
        fee={"asset": "TRUMP", "quantity": Decimal("-0.0006803"), "is_rebate": False},
    )
    persist_crypto_exchange_event(event, user, crypto_account)
    tx = Transactions.objects.get(investor=user, account=crypto_account)
    assert tx.commission == Decimal("-0.0006803")
```

- [ ] **Step 2: Run; verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py::test_stablecoin_quote_spot_trade_records_commission -q --no-cov`
Expected: FAIL — `tx.commission is None`.

- [ ] **Step 3: Write `commission` from `event.fee` in the persist branch**

In `persist_crypto_exchange_event`, inside the priced-leg `else` branch (after the `if leg_cash_flow is not None:` block, lines ~441-444), add:

```python
                if event.fee and event.fee.get("quantity") not in (None, 0, Decimal("0")):
                    tx_kwargs["commission"] = _normalize_model_decimal(
                        Transactions, "commission", event.fee["quantity"]
                    )
```

(Place this inside the `else` so it applies to both stablecoin-quote and crypto-crypto priced legs — the option-fill branch already stores commission via its own leg; verify the option test still passes.)

- [ ] **Step 4: Run the full persist test suite; verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py -q --no-cov`
Expected: PASS (new test + no regressions; option-fill commission test stays green).

- [ ] **Step 5: Commit**

```bash
git add services/crypto_exchange.py tests/integration/workflows/test_crypto_exchange_persistence.py
git commit -m "fix(crypto): persist commission (fee) on stablecoin-quote spot trades"
```

---

## Task 2: USDC↔USDT-CONVERT as FX; BTC↔USDT-CONVERT as spot trade

**Files:**
- Modify: `backend/services/importer.py:690-833` (`build_okx_csv_events` — detect CONVERT, route FX vs spot) and `:836-960` (`parse_okx_trading_csv` — persist FX via `save_single_transaction`), plus a new FX-persist helper
- Test: `backend/tests/unit/services/test_okx_csv_parser.py`

**Interfaces:**
- Produces: a new payload kind `"fx"` with keys `from_ccy`, `to_ccy`, `from_amount`, `to_amount`, `rate`, `ts`, `billId`. `parse_okx_trading_csv` detects `__kind == "fx"` and calls a new `_persist_okx_csv_fx_event(...)` helper that builds an `FXTransaction` dict and saves via `services.transactions.save_single_transaction`.
- For `BTC-USDT-CONVERT`: emits a `"spot"` payload (existing path) with `side` inferred from `Balance Change` sign — no FX row.

**Design:** CONVERT rows have empty `Action`. The two rows of a CONVERT share an `Order id`: one is the currency given up (negative `Balance Change`), one is the currency received (positive `Balance Change`). For a stablecoin↔stablecoin CONVERT (both legs' `Balance Unit` ∈ {USDT,USDC}), build an FX event: `from_ccy` = the leg with negative `Balance Change`, `to_ccy` = the leg with positive `Balance Change`, amounts = `abs(Balance Change)`, `rate = from_amount / to_amount`. For a crypto↔stablecoin CONVERT, emit a normal spot payload keyed on the base leg, with `side` derived from the sign of the base leg's `Balance Change` (positive → buy, negative → sell).

- [ ] **Step 1: Update the convert-skipped test and add FX + spot-convert tests (RED)**

In `test_okx_csv_parser.py`, replace `test_convert_symbols_are_skipped` (lines ~297-325) with two tests:

```python
def test_usdc_usdt_convert_emits_fx_event():
    """USDC-USDT-CONVERT (stablecoin<->stablecoin) becomes an FX payload, not a
    spot trade. Side is inferred from Balance Change sign (empty Action)."""
    rows = [
        {  # USDC given up
            "id": "2602510860429074432", "Order id": "2602510860294856704",
            "Time": "2025-06-16 11:41:07", "Trade Type": "Spot",
            "Symbol": "USDC-USDT-CONVERT", "Action": "", "Amount": "103.836812",
            "Trading Unit": "USDC", "Filled Price": "0.993950", "PnL": "0.0",
            "Fee": "0.0", "Fee Unit": "USDC", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "-103.836812",
            "Balance": "0.0", "Balance Unit": "USDC",
        },
        {  # USDT received
            "id": "2602510860429074433", "Order id": "2602510860294856704",
            "Time": "2025-06-16 11:41:07", "Trade Type": "Spot",
            "Symbol": "USDC-USDT-CONVERT", "Action": "", "Amount": "103.208630",
            "Trading Unit": "USDC", "Filled Price": "0.993950", "PnL": "0.0",
            "Fee": "0.0", "Fee Unit": "USDT", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "103.208630",
            "Balance": "0.0", "Balance Unit": "USDT",
        },
    ]
    df = _df_from_rows(rows)
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    assert skipped == []
    assert len(events) == 1
    payload, _ = events[0]
    assert payload["__kind"] == "fx"
    assert payload["from_ccy"] == "USDC"
    assert payload["to_ccy"] == "USDT"
    assert payload["from_amount"] == "103.836812"
    assert payload["to_amount"] == "103.208630"


def test_btc_usdt_convert_emits_spot_event():
    """BTC-USDT-CONVERT (crypto<->stablecoin) is a normal purchase: emits a spot
    payload with side inferred from the base (BTC) leg's Balance Change sign."""
    rows = [
        {  # BTC received (buy)
            "id": "2893075670726385664", "Order id": "2893075670558613504",
            "Time": "2025-09-24 17:06:13", "Trade Type": "Spot",
            "Symbol": "BTC-USDT-CONVERT", "Action": "", "Amount": "0.002839",
            "Trading Unit": "BTC", "Filled Price": "113345.97", "PnL": "0.0",
            "Fee": "0.0", "Fee Unit": "BTC", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "0.002839",
            "Balance": "0.0", "Balance Unit": "BTC",
        },
        {  # USDT given up
            "id": "2893075670726385665", "Order id": "2893075670558613504",
            "Time": "2025-09-24 17:06:13", "Trade Type": "Spot",
            "Symbol": "BTC-USDT-CONVERT", "Action": "", "Amount": "321.819075",
            "Trading Unit": "BTC", "Filled Price": "113345.97", "PnL": "0.0",
            "Fee": "0.0", "Fee Unit": "USDT", "Position Change": "0.0",
            "Position Balance": "0.0", "Balance Change": "-321.819075",
            "Balance": "0.0", "Balance Unit": "USDT",
        },
    ]
    df = _df_from_rows(rows)
    events, skipped = build_okx_csv_events(df, timedelta(hours=3))

    assert skipped == []
    assert len(events) == 1
    payload, _ = events[0]
    assert payload["__kind"] == "spot"
    assert payload["instId"] == "BTC-USDT"  # CONVERT suffix stripped
    assert payload["side"] == "buy"  # BTC Balance Change positive
    assert payload["fillSz"] == "0.002839"
```

- [ ] **Step 2: Run; verify both fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/services/test_okx_csv_parser.py -q --no-cov -k "convert"`
Expected: FAIL — `build_okx_csv_events` still skips all CONVERT symbols.

- [ ] **Step 3: Detect and route CONVERT rows in `build_okx_csv_events`**

In the `if trade_type == "Spot":` block (lines ~726-729), special-case CONVERT before grouping. Replace:

```python
        if trade_type == "Spot":
            # Defer: collect all rows, then pair base+quote per Order id below.
            spot_groups.setdefault(order_id, []).append((row, row_id, fill_time, symbol_clean))
            continue
```

with:

```python
        if trade_type == "Spot":
            if symbol_clean.endswith("-CONVERT"):
                convert_groups.setdefault(order_id, []).append(
                    (row, row_id, fill_time, symbol_clean)
                )
                continue
            spot_groups.setdefault(order_id, []).append((row, row_id, fill_time, symbol_clean))
            continue
```

Add `convert_groups = {}` next to `spot_groups = {}` (line ~706).

Then, after the spot-emission loop (before `return events, skipped_transfer_ids`), add CONVERT handling:

```python
    # CONVERT rows: stablecoin<->stablecoin = FX; crypto<->stablecoin = spot.
    for order_id, rows in convert_groups.items():
        base_symbol = symbol_clean  # not available here; recompute from rows
        # Recompute the underlying symbol (drop the -CONVERT suffix).
        sample_symbol = rows[0][3]
        underlying = sample_symbol[: -len("-CONVERT")]  # e.g. BTC-USDT or USDC-USDT
        units = {(rows[i][0].get("Balance Unit") or "").upper(): i for i in range(len(rows))}
        # Pair each row; classify by whether BOTH units are stablecoins.
        all_stablecoin = all(u in {"USDT", "USDC"} for u in units)
        if all_stablecoin:
            # FX: from = negative Balance Change leg, to = positive leg.
            from_row = to_row = None
            for r, _rid, _ft, _sym in rows:
                bal = Decimal(str(r.get("Balance Change") or "0"))
                if bal < 0:
                    from_row = r
                elif bal > 0:
                    to_row = r
            if from_row is None or to_row is None:
                # Malformed convert (no signed legs); skip defensively.
                for _r, rid, _ft, _sym in rows:
                    skipped_transfer_ids.append(rid)
                continue
            from_ccy = (from_row.get("Balance Unit") or "").upper()
            to_ccy = (to_row.get("Balance Unit") or "").upper()
            from_amount = abs(Decimal(str(from_row.get("Balance Change") or "0")))
            to_amount = abs(Decimal(str(to_row.get("Balance Change") or "0")))
            payload = {
                "__kind": "fx",
                "from_ccy": from_ccy,
                "to_ccy": to_ccy,
                "from_amount": str(from_amount),
                "to_amount": str(to_amount),
                "ts": str(rows[0][2]),
                "billId": str(rows[0][1]),
            }
            events.append((payload, str(rows[0][1])))
        else:
            # crypto<->stablecoin: emit a spot payload from the base (crypto) leg.
            base, quote = underlying.split("-")
            for r, rid, ft, _sym in rows:
                unit = (r.get("Balance Unit") or "").upper()
                if unit != base:
                    continue
                bal = Decimal(str(r.get("Balance Change") or "0"))
                side = "buy" if bal > 0 else "sell"
                amount = abs(Decimal(str(r.get("Amount") or "0")))
                filled_price = Decimal(str(r.get("Filled Price") or "0"))
                fee = Decimal(str(r.get("Fee") or "0"))
                fee_unit = _strip_okx_bom(r.get("Fee Unit")) or ""
                fee_ccy = fee_unit if fee_unit else quote
                payload = {
                    "__kind": "spot",
                    "instId": underlying,
                    "side": side,
                    "fillSz": str(amount),
                    "fillPx": str(filled_price),
                    "fillTime": str(ft),
                    "tradeId": str(rid),
                    "ordId": str(order_id),
                    "fee": str(fee),
                    "feeCcy": fee_ccy,
                }
                events.append((payload, str(rid)))
                break
```

- [ ] **Step 4: Add the FX persist helper + dispatch in `parse_okx_trading_csv`**

**Contract note (verified):** `services.transactions.save_single_transaction` returns a *dict* `{"success": bool, "transaction_id": id, "type": "fx"}` on success or `{"success": False, "error": str}` on any failure. Because `FXTransaction` has a `UniqueConstraint` on `(investor, account, import_provider, import_account_id, import_event_id)`, a duplicate would make `.create()` raise `IntegrityError` inside the helper's broad try/except — surfacing as `success: False`, which conflates "duplicate" with "real error". To get clean dedup (matching how `persist_crypto_exchange_event` does an explicit `.exists()` check), the helper does a pre-existence check and returns a sentinel.

In `services/importer.py`, near `_normalize_okx_csv_event`, add a helper:

```python
def _persist_okx_csv_fx_event(payload, investor, account):
    """Persist a stablecoin<->stablecoin CONVERT as an FXTransaction.

    Bypasses the crypto-event pipeline (no asset/price resolution) and saves
    via ``services.transactions.save_single_transaction`` with ``is_fx=True``.

    Returns ``"created"`` if a new FXTransaction was persisted, ``"duplicate"``
    if one already exists for this event id, or raises on a genuine error.
    """
    from common.models import FXTransaction
    from services.transactions import save_single_transaction

    provider = OKX_CSV_IMPORT_PROVIDER
    event_id = f"csv_fx:{payload['billId']}"
    import_account_id = account.native_id or str(account.id)

    # Explicit dedup (mirrors persist_crypto_exchange_event) so duplicates are
    # distinguishable from real save errors.
    if FXTransaction.objects.filter(
        investor=investor,
        account=account,
        import_provider=provider,
        import_account_id=import_account_id,
        import_event_id=event_id,
    ).exists():
        return "duplicate"

    from_amount = Decimal(payload["from_amount"])
    to_amount = Decimal(payload["to_amount"])
    rate = from_amount / to_amount if to_amount else Decimal("0")
    data = {
        "is_fx": True,
        "investor": investor,
        "account": account,
        "date": datetime.fromtimestamp(int(payload["ts"]) / 1000, tz=timezone.utc).replace(tzinfo=None),
        "from_currency": payload["from_ccy"],
        "to_currency": payload["to_ccy"],
        "from_amount": from_amount,
        "to_amount": to_amount,
        "exchange_rate": rate,
        "comment": f"provider={provider}; group_id={payload['billId']}",
        "import_provider": provider,
        "import_account_id": import_account_id,
        "import_event_id": event_id,
        "import_group_id": payload["billId"],
        "import_event_type": "fx",
    }
    result = save_single_transaction(data)
    if not result.get("success"):
        raise RuntimeError(f"FX save failed: {result.get('error')}")
    return "created"
```

In `parse_okx_trading_csv`'s event loop (lines ~909-948), branch on the payload kind BEFORE normalizing. Replace the start of the `for index, (payload, source_id) in enumerate(events):` body:

```python
    for index, (payload, source_id) in enumerate(events):
        try:
            if payload.get("__kind") == "fx":
                outcome = await database_sync_to_async(_persist_okx_csv_fx_event)(
                    payload, investor, account
                )
                progress = min(((index + 1) / total_events) * 100, 100) if total_events else 100
                yield {
                    "status": "progress",
                    "message": f"Processing OKX event {index + 1} of {total_events}",
                    "progress": progress,
                    "current": index + 1,
                }
                if outcome == "created":
                    imported += 1
                    yield {
                        "status": "transaction_saved",
                        "message": "Saved OKX FX conversion",
                        "transaction": {"import_group_id": payload["billId"], "count": 1},
                    }
                else:  # "duplicate"
                    duplicate += 1
                    yield {
                        "status": "duplicate_transaction",
                        "message": f"OKX FX event already imported (id={source_id})",
                        "transaction": {"import_group_id": payload["billId"], "count": 0},
                    }
                continue

            event = _normalize_okx_csv_event(payload)  # re-tagged with okx_csv provider
            created = await database_sync_to_async(persist_crypto_exchange_event)(
                event, investor, account
            )
            # ... (existing progress/yield logic for non-FX events unchanged) ...
```

The existing `except Exception` around the loop body already catches any `RuntimeError` from a genuine FX save failure and yields `transaction_error` — no extra handling needed.

- [ ] **Step 5: Run all OKX parser tests; verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/services/test_okx_csv_parser.py -q --no-cov`
Expected: PASS (new convert tests + all others).

- [ ] **Step 6: Commit**

```bash
git add services/importer.py tests/unit/services/test_okx_csv_parser.py
git commit -m "feat(okx): USDC↔USDT-CONVERT as FX; BTC↔USDT-CONVERT as spot trade"
```

---

## Task 5: Display format for crypto Buy/Sell (auto-fixed by Task 4) — verify only

**Depends on:** Task 4.

**Files:** none to modify. **Verify** `frontend/src/components/transactions/TransactionDescription.vue`.

**Analysis:** The `isRegularTransaction` branch (lines 88-102) renders `{{ transaction.quantity }} @{{ transaction.price }} of <security-link> <commission-display>`. `isRegularTransaction` (lines 171-184) excludes `Crypto trade in/out`, `Option settlement`, cash, etc. — but `Buy`/`Sell` are NOT in the exclusion list, so once Task 4 changes the type to `Buy`/`Sell`, this branch fires and produces the desired `Buy 0.6803 @73.209 of TRUMP <Commission>` format with the security link. **No code change needed.**

- [ ] **Step 1: Manual verify (no code)**

After Task 4 lands, start the frontend (`cd ../frontend && npm run dev`), import a TRUMP-USDT trade via the OKX CSV path, and confirm the Transactions page shows `Buy 0.6803 @73.209 of TRUMP` with a clickable TRUMP link and a fee chip. If the `quantity`/`price` decimal formatting looks wrong, that is Task 7's concern.

- [ ] **Step 2: (No commit — verification only)**

If verification reveals the format is NOT applied, the fallback is to add `'Buy', 'Sell'` handling explicitly — but the analysis shows this is unnecessary. Record the verification result in the PR description.

---

## Task 7: Decimal-place formatting for quantity/price display

**Files:**
- Create: `frontend/src/utils/formatUtils.js`
- Modify: `frontend/src/components/transactions/TransactionDescription.vue`

**Interfaces:**
- Produces: `formatQuantity(value, digits)` and `formatPrice(value, digits)` exported from `formatUtils.js`. Rule: if `abs(value) >= 1`, format to `digits` decimal places (user's global setting, default 2); if `abs(value) < 1`, show the first significant digit (e.g. `0.6803 → "0.7"`, `0.00011659 → "0.0001"`).

**Design:** The `digits` setting is currently only in the profile form; wire it into the description component via the existing settings store/pinia (`useAppStore` or equivalent — confirm the source). The component receives `transaction.quantity`/`transaction.price` as strings; pass them through `formatQuantity`/`formatPrice` in the template.

- [ ] **Step 1: Confirm where `digits` lives at runtime**

Run: `grep -rn "digits" frontend/src/stores/ frontend/src/composables/`
Identify the store/getter that exposes the logged-in user's `digits` (likely `auth.ts` user profile). If it is not exposed, plan to read it from the auth user object: `authStore.user?.digits ?? 2`.

- [ ] **Step 2: Create `formatUtils.js`**

```javascript
// frontend/src/utils/formatUtils.js

/**
 * Format a numeric value with adaptive decimal places.
 *
 * For |value| >= 1: fixed `digits` decimal places (user's global setting).
 * For |value| < 1: show the first significant digit (e.g. 0.6803 -> "0.7",
 *   0.00011659 -> "0.0001"). Returns null for non-numeric / null input so the
 *   caller can fall back to the existing '–' sentinel.
 */
export function formatQuantity(value, digits = 2) {
  const num = typeof value === 'number' ? value : parseFloat(value)
  if (value == null || value === '' || (!value && value !== 0) || Number.isNaN(num)) {
    return null
  }
  if (Math.abs(num) >= 1) {
    return num.toFixed(digits)
  }
  // First significant digit: toPrecision(1) keeps one sig fig, strip exp notation.
  const precise = num.toPrecision(1)
  return Number(precise).toString()
}

/** Format a price with the same adaptive rule. */
export function formatPrice(value, digits = 2) {
  return formatQuantity(value, digits)
}
```

- [ ] **Step 3: Wire it into `TransactionDescription.vue`**

In the `<script setup>`, import the helper and the auth store, and add a computed `digits`:

```javascript
import { formatQuantity, formatPrice } from '@/utils/formatUtils'
import { useAuthStore } from '@/stores/auth'
const authStore = useAuthStore()
const digits = computed(() => authStore.user?.digits ?? 2)
```

In the template, replace the raw quantity/price in the regular + crypto-event branches. Lines 89-91 (`isRegularTransaction`):

```html
        <template v-if="transaction.quantity && transaction.quantity !== '–'">
          {{ formatQuantity(transaction.quantity, digits) }} @{{ formatPrice(transaction.price, digits) }}
        </template>
```

Lines 79-85 (`isCryptoEvent`):

```html
      <template v-else-if="isCryptoEvent">
        {{ transaction.type }} {{ formatQuantity(transaction.quantity, digits) }}
        {{ transaction.security?.ticker || transaction.security?.name }}
        <template v-if="transaction.price && transaction.price !== '–'">
          @{{ formatPrice(transaction.price, digits) }}
        </template>
      </template>
```

(Confirm the import path alias `@` resolves to `src/` — check `vite.config.js` / `jsconfig.json`. If not, use a relative path `../../utils/formatUtils.js`.)

- [ ] **Step 4: Manual verify + sanity test**

Start the frontend, view a transaction with qty `0.6803` (→ `0.7`), qty `0.00011659` (→ `0.0001`), qty `12.94056` (→ `12.94` with digits=2). Confirm no NaN/blank regressions for integer quantities.

There is no frontend test runner configured for this component (confirm via `package.json`); if `vitest` exists, add a unit test for `formatQuantity`. Otherwise, rely on manual verification and record it in the PR.

- [ ] **Step 5: Commit**

```bash
cd ../frontend
git add src/utils/formatUtils.js src/components/transactions/TransactionDescription.vue
git commit -m "feat(ui): adaptive decimal places for transaction quantity/price"
```

---

## Task 8: Options — option leg (sell) + settlement leg (collateral release), with corrected balChg mapping

**Files:**
- Modify: `backend/services/importer.py:731-769` (option-settlement branch — map `Balance Change`, not `Position Change`) and verify the option-fill branch
- Modify: `backend/services/crypto_exchange.py:812-834` (`normalize_okx_option_settlement`) — confirm it handles the corrected input
- Test: `backend/tests/unit/services/test_okx_csv_parser.py` (adapter), `backend/tests/integration/workflows/test_crypto_exchange_persistence.py` (persist)

**Interfaces:** none new. Fixes a data-mapping bug in the CSV adapter and verifies the option premium (BTC-denominated) resolves to a fiat price through the existing `_quote_asset_fiat_price` path.

**Analysis (the core bug):** The CSV adapter's option-settlement branch (lines ~737-753) sets `balChg = Decimal(str(row.get("Position Change") or "0"))`. For the user's OTM expiry, `Position Change = -0.00716211` (the 7 contracts removed) but `Balance Change = +0.00716211` (collateral RELEASED back to the wallet). The settlement normalizer's `balChg` is the **signed delivered coin amount** = the balance change, NOT the position change. Using `Position Change` records a BTC outflow on expiry (wrong sign). **Fix: use `Balance Change` for `balChg`.**

The option-fill branch (lines ~754-768) is correct: it maps `Amount` (contracts), `Filled Price`, `Fee`, `Fee Unit`. The existing `test_option_fill_maps_to_option_payload` already covers it. The sell persists as `-7` contracts of the option asset at `0.0022 BTC` premium; `_leg_fiat_price` converts via the BTC/USD quote lookup (price_asset=BTC from feeCcy).

- [ ] **Step 1: Update the option-settlement adapter test (RED)**

In `test_okx_csv_parser.py`, fix `test_option_expiration_maps_to_settlement_payload` (lines ~359-382). The fixture's `Balance Change` should be `+0.007162` (collateral released) and the assertion should expect `balChg` from `Balance Change`:

```python
def test_option_expiration_maps_to_settlement_payload():
    row = {
        "id": "3628711646064058370", "Order id": "0",
        "Time": "2026-06-05 11:00:34", "Trade Type": "Option",
        "Symbol": "BTC-USD-260605-80000-C", "Action": "Expired OTM",
        "Amount": "7.0", "Trading Unit": "cont", "Filled Price": "62703.943334",
        "PnL": "0.000154", "Fee": "0.000000", "Fee Unit": "BTC",
        "Position Change": "-0.007162", "Position Balance": "0.0",
        "Balance Change": "0.007162", "Balance": "0.0", "Balance Unit": "BTC",
    }
    df = _df_from_rows([row])
    events, _ = build_okx_csv_events(df, timedelta(hours=3))

    assert len(events) == 1
    payload, source_id = events[0]
    assert payload["__kind"] == "option_settlement"
    assert payload["ccy"] == "BTC"
    # balChg = Balance Change (collateral RELEASED, positive), NOT Position Change.
    assert payload["balChg"] == "0.007162"
    assert payload["px"] == "62703.943334"
    assert payload["billId"] == "3628711646064058370"
    assert payload["ordId"] == ""
    expected_dt = datetime(2026, 6, 5, 8, 0, 34, tzinfo=timezone.utc)
    assert payload["ts"] == str(int(expected_dt.timestamp() * 1000))
```

- [ ] **Step 2: Run; verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/services/test_okx_csv_parser.py::test_option_expiration_maps_to_settlement_payload -q --no-cov`
Expected: FAIL — `balChg` is `-0.007162` (from Position Change).

- [ ] **Step 3: Fix the adapter to use `Balance Change` for `balChg`**

In `services/importer.py`, in the option-expiration branch (lines ~737-753), change:

```python
                bal_chg = Decimal(str(row.get("Position Change") or "0"))
```

to:

```python
                # balChg is the signed DELIVERED coin amount = the wallet balance
                # change (collateral released on OTM expiry is positive; ITM
                # delivery is negative for the writer). Position Change tracks
                # contracts, not coin flow, so it has the wrong sign/magnitude.
                bal_chg = Decimal(str(row.get("Balance Change") or "0"))
```

- [ ] **Step 4: Add a persist regression test for the option sell + expiry pair**

Add to `test_crypto_exchange_persistence.py`. This needs a BTC USD price on the event date so `_quote_asset_fiat_price` resolves (the option premium is BTC-denominated):

```python
@pytest.mark.django_db
def test_option_sell_and_otm_expiry_persist_correctly(user, crypto_account):
    """OKX issue #8: selling a BTC call + OTM expiry. The sell is an option leg
    (-7 contracts @ 0.0022 BTC premium); the expiry releases collateral
    (+0.00716211 BTC settlement). Premium must resolve to fiat via BTC/USD."""
    from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event
    from common.models import Assets, Prices
    from datetime import date

    # Seed a BTC USD price on/before the sell date so premium fiat-resolves.
    btc = Assets.objects.create(
        investor=user, ISIN="CRYPTO:BTC", type="Crypto", name="BTC", ticker="BTC",
        currency="USD", exposure="Commodity",
    )
    Prices.objects.create(security=btc, date=date(2026, 5, 27), price=Decimal("105000"))

    # Option SELL: -7 contracts @ 0.0022 BTC, fee in BTC.
    sell_event = CryptoExchangeEvent(
        provider="okx_csv", provider_event_id="csv:opt-sell",
        group_id="opt-order", timestamp_ms=1769468114000,  # 2026-05-27 21:15:14 UTC
        category="trade", raw_type="option_fill",
        legs=[{
            "asset": "BTC-USD-260605-80000-C", "quantity": Decimal("-7"),
            "price": Decimal("0.0022"), "price_asset": "BTC", "role": "base",
            "instrument": "option",
        }],
        fee={"asset": "BTC", "quantity": Decimal("-0.00001078"), "is_rebate": False},
    )
    persist_crypto_exchange_event(sell_event, user, crypto_account)

    sell_tx = Transactions.objects.get(
        investor=user, account=crypto_account, type="Crypto trade out"
    )
    assert sell_tx.quantity == Decimal("-7")
    assert sell_tx.price == Decimal("0.0022")
    # Premium fiat-resolved: 0.0022 BTC * ~105000 USD/BTC.
    assert sell_tx.price is not None and sell_tx.price > 0

    # OTM EXPIRY: collateral released (+0.00716211 BTC).
    settle_event = CryptoExchangeEvent(
        provider="okx_csv", provider_event_id="csv:opt-settle",
        group_id="opt-order", timestamp_ms=1772664034000,  # 2026-06-05 08:00:34 UTC
        category="settlement", raw_type="option_delivery",
        legs=[{
            "asset": "BTC", "quantity": Decimal("0.00716211"),
            "price": Decimal("62703.94333408"), "price_asset": "USD", "role": "base",
        }],
    )
    persist_crypto_exchange_event(settle_event, user, crypto_account)

    settle_tx = Transactions.objects.get(
        investor=user, account=crypto_account, type="Option settlement"
    )
    # Positive: collateral came back.
    assert settle_tx.quantity == Decimal("0.00716211")
```

- [ ] **Step 5: Run all crypto persist + parser tests; verify pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/integration/workflows/test_crypto_exchange_persistence.py tests/unit/services/test_okx_csv_parser.py -q --no-cov`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/importer.py tests/unit/services/test_okx_csv_parser.py tests/integration/workflows/test_crypto_exchange_persistence.py
git commit -m "fix(okx): option expiry uses Balance Change (collateral release) for balChg"
```

---

## Final integration: import the user's real CSV

After all 8 tasks land and tests pass:

- [ ] **Step 1: Run the full test suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/unit/services/test_okx_csv_parser.py tests/integration/workflows/test_crypto_exchange_persistence.py tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Expected: PASS.

- [ ] **Step 2: Manual end-to-end import**

Start backend (`./.venv/Scripts/python.exe run_uvicorn.py`) + frontend. Import the real CSV via the OKX import dialog. Verify: 17 transfers imported (stablecoins as cash, BTC/TRUMP as crypto transfers), 2 CONVERT rows (1 FX + 1 spot), 18 spot trades as Buy/Sell with USDT/USDC currency + commission, 2 option rows (sell + expiry). Confirm the missing first USDT `Transfer in` (357.14) now appears as `Cash in`.

- [ ] **Step 3: Open the PR**

Because Tasks 3/4/6/8 touch protected logic (`services/crypto_exchange.py`, `persist_crypto_exchange_event`, `normalize_okx_*`), open a PR (not auto-commit). Add the `needs-approval` label. Title: `fix(okx): 8 CSV import fixes (transfers, FX, currency, types, fees, decimals, options)`. Reference this plan and the spec in the description.

---

## Self-Review (run before presenting)

**Spec coverage:**
- #1 transfers → Task 1 ✓ (decision: all transfers imported)
- #2 CONVERT/FX → Task 2 ✓ (decision: split USDC↔USDT=FX, BTC↔USDT=spot)
- #3 currency USDC→USD → Task 3 ✓
- #4 Buy/Sell types → Task 4 ✓ (depends on Task 3's `quote_currency`)
- #5 display format → Task 5 ✓ (verify-only, auto-fixed by Task 4)
- #6 fees → Task 6 ✓
- #7 decimals → Task 7 ✓ (frontend)
- #8 options → Task 8 ✓ (option leg + corrected balChg)

**Placeholder scan:** no TBD/TODO; every step has code or a command. Task 5 is intentionally verify-only (justified by code analysis). Task 2's FX persist helper is built against the *verified* contract of `save_single_transaction` (returns a dict, broad try/except conflates dup vs error) — the helper does its own explicit `FXTransaction.objects.filter(...).exists()` dedup and raises on genuine failure. Task 7's `digits` source (`authStore.user.digits`) is verified present in `UserProfileSerializer` (`users/serializers.py:127`) and consumed via `authStore.fetchUserData()`.

**Type consistency:** `quote_currency` (Task 3) is the key signal consumed in Task 4; both reference the same leg key. The `"transfer"` and `"fx"` payload kinds are defined in Task 1/Task 2 and dispatched consistently. `_persist_okx_csv_fx_event` is defined once and called once.

**Sequencing note:** Tasks 3→4 must be sequential (4 depends on 3's leg key). Tasks 1, 2, 6, 7, 8 are independent. Task 5 is verify-only after 4.
