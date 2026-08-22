# OKX Two-Account Model + Funding-History Import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Model OKX funding and trading as two `Accounts` rows, import the Funding-History CSV, pair internal funding↔trading transfers so the existing matched/unmatched disposition machinery can be reactivated, and add a minimal backfill — resolving issue #29's root cause.

**Architecture:** No DB schema change. Two `Accounts` rows per OKX broker (`native_id` trading/funding). A new funding-history CSV parser reuses the existing `CryptoExchangeEvent` → `persist_crypto_exchange_event` pipeline. Both CSV parsers stamp a deterministic synthetic `import_group_id` so internal-transfer legs pair across files. A new `is_unconditionally_neutral_transfer` discriminator exempts earn moves, so flipping `TRANSFER_DISPOSITION_ENABLED = True` realizes only genuine external crypto flows. A backfill command renames/creates the two accounts without touching transactions.

**Tech Stack:** Django 5 / Django Channels, pandas (CSV), pytest (+ pytest-asyncio, `--asyncio-mode=auto`), `Decimal` for all money math, `uv` project mode.

## Global Constraints

- **Decimal only** for money/price/quantity — never `float`. Internal precision ≥6 dp (prices) / ≥9 dp (quantities, FX). `ROUND_HALF_UP`. Persisted aggregates 2 dp.
- **All commands from `backend/`** via `uv run`. Single-test dev loop: `uv run python -m pytest -c pytest_fast.ini <path>::<test> -v --tb=short`. Full suite: `uv run python -m pytest -c pytest.ini -v --tb=short`.
- **Async parser tests** use `@pytest.mark.django_db(transaction=True)` + `@pytest.mark.asyncio`; ORM access inside async goes through `database_sync_to_async`. `DJANGO_SETTINGS_MODULE = portfolio_management.test_settings` is set by the `.ini` files.
- **No DB migration** in this plan. The only data-model change is an in-memory dataclass field (`CryptoExchangeEvent.event_type`).
- **Protected logic touched (needs PR + `needs-approval` label):** `services/realized.py` (`realized_gain_loss` walker), `services/transactions.py` (transfer predicates), `services/crypto_exchange.py` (persist), `services/importer.py` (OKX parsers). Each task commits on green; the branch is already `feat/crypto-option-accounting`.
- **OKX CSV conventions:** UTF-8 with BOM on nearly every cell (`_strip_okx_bom` handles it); first line is metadata (`UID:…,Time Zone:UTC+3`); `header=1` for pandas; `Time` is `YYYY-MM-DD HH:MM:SS` in the export TZ → UTC ms-epoch via `_okx_time_to_utc_ms`. Stablecoins = `{"USDT","USDC"}`.
- **Provider namespace:** CSV imports use `import_provider = "okx_csv"` (constant `OKX_CSV_IMPORT_PROVIDER`). Funding rows use `import_event_id` prefix `csv_fund:`; trading rows use `csv_transfer:`/`csv:` — they dedup independently.

---

## File Structure

**Modified:**
- `backend/services/crypto_exchange.py` — add `event_type` field to `CryptoExchangeEvent`; persist prefers it for `import_event_type`.
- `backend/services/importer.py` — add `_okx_internal_transfer_group_id`; trading-parser Transfer branch stamps synthesized group_id; add `_build_okx_funding_events` + `_okx_funding_row_to_payload` + `_normalize_okx_funding_event` + `parse_okx_funding_csv` + `_okx_csv_is_funding_schema`.
- `backend/services/transactions.py` — add `is_unconditionally_neutral_transfer` + token set.
- `backend/services/realized.py` — rewire the transfer gate to respect the discriminator; flip `TRANSFER_DISPOSITION_ENABLED = True`.
- `backend/transactions/views.py` — OKX branch routes funding-schema CSVs to `parse_okx_funding_csv`.

**Created:**
- `backend/common/management/commands/migrate_okx_two_account.py` — backfill command.
- `backend/tests/unit/services/test_okx_funding_csv_parser.py` — funding-parser tests.
- `backend/tests/unit/services/test_okx_internal_transfer_pairing.py` — pairing + cross-account basis-carry tests.
- `backend/tests/unit/services/test_realized_transfer_disposition.py` — discriminator + flag-flip tests.
- `backend/tests/unit/management/test_migrate_okx_two_account.py` — backfill command tests (path mirrors existing `tests/unit/` layout; create `tests/unit/management/` if absent).

**Interfaces (consumed/produced across tasks):**
- Task 1 produces `CryptoExchangeEvent.event_type` + `persist_crypto_exchange_event` writing `import_event_type = event.event_type or event.category`.
- Task 2 produces `_okx_internal_transfer_group_id(ccy, amount, timestamp_ms) -> str` (in `importer.py`).
- Task 4 produces `parse_okx_funding_csv(file_path, account_id, user_id, confirm_every)` (async generator) and `_normalize_okx_funding_event(payload)`.
- Task 5 produces `_okx_csv_is_funding_schema(file_path) -> bool` (in `importer.py`).
- Task 6 produces `is_unconditionally_neutral_transfer(transaction) -> bool` (in `transactions.py`).

---

### Task 1: Add `event_type` field to `CryptoExchangeEvent` + persist fallback

The fine-grained discriminator tokens (`okx_internal_transfer`, `okx_earn_subscription`, …) must reach `Transactions.import_event_type`. Today `persist_crypto_exchange_event` overwrites that field with `event.category`, so an additive optional field + an `or` fallback is needed. This is purely additive: existing normalizers don't set `event_type` → behavior unchanged.

**Files:**
- Modify: `backend/services/crypto_exchange.py:64-73` (dataclass), `:452`, `:487` (two `import_event_type=event.category` sites).
- Test: `backend/tests/unit/services/test_crypto_exchange_event_type.py` (new).

**Interfaces:**
- Produces: `CryptoExchangeEvent.event_type: Optional[str] = None`; persist writes `import_event_type = event.event_type or event.category`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/services/test_crypto_exchange_event_type.py
"""CryptoExchangeEvent.event_type flows to Transactions.import_event_type."""
from decimal import Decimal

import pytest

from common.models import Accounts, Brokers, CustomUser, Transactions
from services.crypto_exchange import CryptoExchangeEvent, persist_crypto_exchange_event, _single_leg


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(username="evt-type-user", password="x")


@pytest.fixture
def account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    return Accounts.objects.create(broker=broker, name="Funding", native_id="okx-fund")


def _event(category, event_type=None):
    return CryptoExchangeEvent(
        provider="okx_csv",
        provider_event_id="csv_fund:1",
        group_id="g1",
        timestamp_ms=1750000000000,
        category=category,
        raw_type="funding",
        event_type=event_type,
        legs=_single_leg("BTC", Decimal("0.5"), "BTC"),
    )


@pytest.mark.django_db(transaction=True)
def test_event_type_overrides_category_when_set(user, account):
    persist_crypto_exchange_event(_event("transfer", event_type="okx_internal_transfer"), user, account)
    tx = Transactions.objects.get()
    assert tx.import_event_type == "okx_internal_transfer"


@pytest.mark.django_db(transaction=True)
def test_falls_back_to_category_when_event_type_unset(user, account):
    persist_crypto_exchange_event(_event("transfer"), user, account)
    tx = Transactions.objects.get()
    assert tx.import_event_type == "transfer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_crypto_exchange_event_type.py -v --tb=short`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'event_type'`.

- [ ] **Step 3: Add the field + persist fallback**

In `backend/services/crypto_exchange.py`, add the field to the dataclass (after `fee`, line ~73):

```python
@dataclass
class CryptoExchangeEvent:
    provider: str
    provider_event_id: str
    group_id: str
    timestamp_ms: int
    category: str
    raw_type: str
    legs: List[Dict[str, Any]]
    fee: Optional[Dict[str, Any]] = None
    event_type: Optional[str] = None
```

At BOTH persist sites (`crypto_exchange.py:453` stablecoin-cash branch and `:487` priced-asset branch), change:

```python
            import_event_type=event.category,
```

to:

```python
            import_event_type=event.event_type or event.category,
```

(Use Edit with `replace_all=True` on the exact string `import_event_type=event.category,` — it appears exactly twice, both must change.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_crypto_exchange_event_type.py -v --tb=short`
Expected: PASS (both tests).

- [ ] **Step 5: Run the existing OKX CSV suite to confirm no regression**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_csv_parser.py -v --tb=short`
Expected: PASS (existing tests still green — fallback preserves old behavior).

- [ ] **Step 6: Commit**

```bash
git add backend/services/crypto_exchange.py backend/tests/unit/services/test_crypto_exchange_event_type.py
git commit -m "feat(crypto_exchange): CryptoExchangeEvent.event_type -> import_event_type

Additive optional field; persist prefers event.event_type over category so
fine-grained provenance tokens (okx_internal_transfer, okx_earn_*) reach
Transactions.import_event_type. Existing normalizers unchanged (fallback)."
```

---

### Task 2: `_okx_internal_transfer_group_id` helper

Pure deterministic function. Both parsers (Task 3, Task 4) call it to stamp a shared `import_group_id` on internal-transfer legs.

**Files:**
- Modify: `backend/services/importer.py` (add helper near the other OKX helpers, after `_strip_okx_bom` ~line 657).
- Test: `backend/tests/unit/services/test_okx_internal_transfer_group_id.py` (new).

**Interfaces:**
- Produces: `_okx_internal_transfer_group_id(ccy: str, amount, timestamp_ms: int) -> str`.
- Consumes: nothing.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/services/test_okx_internal_transfer_group_id.py
"""Deterministic synthetic group id for OKX internal transfers."""
from decimal import Decimal

from services.importer import _okx_internal_transfer_group_id


def test_sign_and_case_invariant_within_same_second():
    funding_leg = _okx_internal_transfer_group_id("BTC", Decimal("0.45849457"), 1750600000000)
    trading_leg = _okx_internal_transfer_group_id("btc", Decimal("-0.45849457"), 1750600000500)
    assert funding_leg == trading_leg
    assert funding_leg == "okx_xfer:btc:0.45849457:1750600000"


def test_canonical_amount_strips_trailing_zeros():
    key = _okx_internal_transfer_group_id("USDT", "300.00389139000000", 1750600000000)
    assert "300.00389139" in key  # Decimal.normalize() collapses trailing zeros


def test_different_second_does_not_collide():
    a = _okx_internal_transfer_group_id("BTC", Decimal("1"), 1750600000000)
    b = _okx_internal_transfer_group_id("BTC", Decimal("1"), 1750600001000)
    assert a != b


def test_different_ccy_does_not_collide():
    a = _okx_internal_transfer_group_id("BTC", Decimal("1"), 1750600000000)
    b = _okx_internal_transfer_group_id("TRUMP", Decimal("1"), 1750600000000)
    assert a != b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_internal_transfer_group_id.py -v --tb=short`
Expected: FAIL — `ImportError: cannot import name '_okx_internal_transfer_group_id'`.

- [ ] **Step 3: Implement the helper**

Add to `backend/services/importer.py` immediately after `_strip_okx_bom` (after line 657):

```python
def _okx_internal_transfer_group_id(ccy, amount, timestamp_ms):
    """Synthesize a deterministic group id pairing the two legs of an OKX
    internal funding<->trading transfer.

    Both the funding CSV (``Type = From/To unified trading account``) and the
    trading CSV (``Trade Type = Transfer``) stamp this same key, so the
    existing matched-transfer machinery (``_transfer_is_matched`` /
    ``allocate_group_carry``) pairs the legs without any cross-file
    coordination. OKX records both legs at the same instant, so epoch-second
    granularity aligns them; abs(amount) makes the key sign-invariant so an
    OUT leg and its IN leg compute the identical string.
    """
    canonical_amount = str(abs(Decimal(str(amount))).normalize())
    return f"okx_xfer:{str(ccy).lower()}:{canonical_amount}:{int(timestamp_ms) // 1000}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_internal_transfer_group_id.py -v --tb=short`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/importer.py backend/tests/unit/services/test_okx_internal_transfer_group_id.py
git commit -m "feat(okx): _okx_internal_transfer_group_id — synthetic pairing key

Deterministic okx_xfer:{ccy}:{amount}:{second} stamped by both CSV parsers
so internal funding<->trading transfer legs pair via import_group_id (#29)."
```

---

### Task 3: Trading parser stamps synthesized group_id on Transfer rows

Today the trading parser sets `group_id = billId`, which can never match the funding leg's billId. Change the non-stablecoin Transfer branch to use the synthesized key; the billId stays in `provider_event_id` so dedup is unchanged.

**Files:**
- Modify: `backend/services/importer.py:858-879` (`build_okx_csv_events` Transfer branch), `:685-698` (`_normalize_okx_csv_event` transfer kind branch).
- Test: `backend/tests/unit/services/test_okx_csv_parser.py` (append).

**Interfaces:**
- Produces: trading-CSV non-stablecoin Transfer rows now carry `import_group_id = okx_xfer:...`.
- Consumes: `_okx_internal_transfer_group_id` (Task 2).

- [ ] **Step 1: Write the failing test (append to `test_okx_csv_parser.py`)**

```python
# append to backend/tests/unit/services/test_okx_csv_parser.py
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_trading_transfer_row_carries_synthesized_group_id(tmp_path, user, okx_account):
    """A non-stablecoin Transfer row stamps okx_xfer:* on import_group_id."""
    # One BTC Transfer out row (trading -> funding).
    rows = [_okx_csv_header_row()] + [{
        "id": "770000000001",
        "Order id": "",
        "Time": "2026-06-22 20:05:02",
        "Trade Type": "Transfer",
        "Symbol": "BTC-USDT",
        "Action": "Transfer out",
        "Amount": "0.45849457",
        "Trading Unit": "BTC",
        "Filled Price": "",
        "PnL": "",
        "Fee": "",
        "Fee Unit": "",
        "Position Change": "",
        "Position Balance": "",
        "Balance Change": "-0.45849457",
        "Balance": "",
        "Balance Unit": "BTC",
    }]
    csv_path = tmp_path / "trading.csv"
    _write_okx_csv(csv_path, rows)

    await _drain(parse_okx_trading_csv(str(csv_path), okx_account.id, user.id, confirm_every=False))

    txs = await _persisted_txs(user, okx_account)
    assert len(txs) == 1
    tx = txs[0]
    assert tx.type == "Crypto transfer out"
    assert tx.import_group_id == "okx_xfer:btc:0.45849457:1750601102"  # 2026-06-22 20:05:02 UTC+3 -> epoch
    # Dedup key still carries the billId.
    assert tx.import_event_id == "csv_transfer:770000000001:0"
```

> **Note on the epoch literal:** `2026-06-22 20:05:02 UTC+3` = `2026-06-22 17:05:02 UTC` = epoch `1750601102`. If the test fails on this literal, run `_okx_time_to_utc_ms("2026-06-22 20:05:02", timedelta(hours=3)) // 1000` in a REPL and update the assertion to the printed value. Do not weaken the assertion.

> **Helper reuse:** `_okx_csv_header_row`, `_write_okx_csv`, `_drain`, `_persisted_txs` already exist in `test_okx_csv_parser.py` (lines 48-71, 734-749). If `_okx_csv_header_row` is not the exact name, use whatever local helper builds the metadata+header pair — open the file and mirror an existing transfer/spot test's setup exactly.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_csv_parser.py::test_trading_transfer_row_carries_synthesized_group_id -v --tb=short`
Expected: FAIL — `tx.import_group_id == '770000000001'` (the old billId behavior) ≠ `"okx_xfer:..."`.

- [ ] **Step 3: Edit the Transfer branch in `build_okx_csv_events`**

In `backend/services/importer.py`, replace the `if trade_type == "Transfer":` block (lines 858-879) with:

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
            # Non-stablecoin legs get a synthesized group id so they pair with
            # the funding CSV's From/To unified trading account leg (#29).
            group_id = (
                _okx_internal_transfer_group_id(balance_unit, amount, fill_time)
                if category == "transfer"
                else None
            )
            payload = {
                "__kind": "transfer",
                "category": category,
                "ccy": balance_unit,
                "amount": str(amount),
                "ts": str(fill_time),
                "billId": str(row_id),
                "group_id": group_id,
            }
            events.append((payload, str(row_id)))
            continue
```

- [ ] **Step 4: Edit the transfer kind branch in `_normalize_okx_csv_event`**

Replace lines 685-698 with:

```python
    kind = payload["__kind"]
    if kind == "transfer":
        ccy = payload["ccy"].upper()
        amount = Decimal(payload["amount"])
        category = payload["category"]
        return CryptoExchangeEvent(
            provider=OKX_CSV_IMPORT_PROVIDER,
            provider_event_id=f"csv_transfer:{payload['billId']}",
            group_id=payload.get("group_id") or payload["billId"],
            timestamp_ms=int(payload["ts"]),
            category=category,
            raw_type="transfer",
            legs=_single_leg(ccy, amount, ccy),
        )
```

(The `or payload["billId"]` fallback preserves the old unique-group_id behavior for stablecoin transfers and any payload without a synthesized group_id.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_csv_parser.py::test_trading_transfer_row_carries_synthesized_group_id -v --tb=short`
Expected: PASS.

- [ ] **Step 6: Run the full OKX CSV suite + transfer tests for regression**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_csv_parser.py -v --tb=short`
Expected: PASS — stablecoin-transfer and dedup tests still green (fallback path).

- [ ] **Step 7: Commit**

```bash
git add backend/services/importer.py backend/tests/unit/services/test_okx_csv_parser.py
git commit -m "feat(okx): trading Transfer rows stamp synthesized import_group_id

Non-stablecoin Transfer legs now carry okx_xfer:* so they pair with the
funding CSV leg (#29). billId stays on provider_event_id for dedup."
```

---

### Task 4: Funding-History CSV parser

The new data source. A row-to-payload mapper, an event normalizer, and an async generator mirroring `parse_okx_trading_csv`. Every funding `Type` is mapped; internal transfers carry the synthesized group_id; fine-grained `event_type` tokens drive the discriminator (Task 6).

**Files:**
- Modify: `backend/services/importer.py` (add helpers + `parse_okx_funding_csv`).
- Test: `backend/tests/unit/services/test_okx_funding_csv_parser.py` (new).

**Interfaces:**
- Produces: `parse_okx_funding_csv(file_path, account_id, user_id, confirm_every)` async generator; `_normalize_okx_funding_event(payload) -> CryptoExchangeEvent`; `_build_okx_funding_events(df, tz_offset) -> (events, skipped_ids)`.
- Consumes: `CryptoExchangeEvent.event_type` (Task 1), `_okx_internal_transfer_group_id` (Task 2), `_strip_okx_bom`, `_parse_okx_csv_tz_offset`, `_okx_time_to_utc_ms`, `_single_leg`, `persist_crypto_exchange_event`, `OKX_CSV_IMPORT_PROVIDER`, `get_investor`, `get_account`, `database_sync_to_async`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/services/test_okx_funding_csv_parser.py
"""OKX Funding History CSV parser — row mapping + full async pipeline."""
from decimal import Decimal

import pytest
from channels.db import database_sync_to_async

from common.models import Accounts, Brokers, CustomUser, Transactions
from services.importer import (
    OKX_CSV_IMPORT_PROVIDER,
    _normalize_okx_funding_event,
    parse_okx_funding_csv,
)


# ---- CSV helpers (mirror test_okx_csv_parser.py's _write_okx_csv pattern) ----
FUNDING_COLUMNS = ["id", "Time", "Type", "Amount", "Before Balance", "After Balance", "Symbol"]


def _write_funding_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write("\ufeffUID:652654290649420911,\ufeffAccount Type:Main,\ufeffTime Zone:UTC+3\n")
        fh.write("\ufeff" + ",".join(FUNDING_COLUMNS) + "\n")
        for r in rows:
            fh.write(",".join("\ufeff" + str(r.get(c, "")) for c in FUNDING_COLUMNS) + "\n")


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(username="fund-user", password="x")


@pytest.fixture
def funding_account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    return Accounts.objects.create(broker=broker, name="OKX Funding", native_id="funding")


@pytest.fixture
def trading_account(user):
    # Reuses the same broker if created, else makes one.
    broker, _ = Brokers.objects.get_or_create(investor=user, name="OKX", defaults={"country": "Crypto"})
    return Accounts.objects.create(broker=broker, name="OKX Trading", native_id="trading")


async def _drain(gen):
    return [u async for u in gen]


@database_sync_to_async
def _txs(user, account):
    return list(Transactions.objects.filter(investor=user, account=account).order_by("date", "id"))


# ---- row-to-event unit tests (no DB) ----
def test_internal_transfer_in_crypto_maps_to_transfer_in_with_group():
    payload = {
        "__kind": "funding", "category": "transfer", "event_type": "okx_internal_transfer",
        "ccy": "BTC", "amount": "0.45849457", "ts": "1750601102000",
        "billId": "103346514176", "group_id": "okx_xfer:btc:0.45849457:1750601102",
    }
    ev = _normalize_okx_funding_event(payload)
    assert ev.category == "transfer"
    assert ev.event_type == "okx_internal_transfer"
    assert ev.group_id == "okx_xfer:btc:0.45849457:1750601102"
    assert ev.provider_event_id == "csv_fund:103346514176"


def test_deposit_yield_stablecoin_maps_to_reward():
    payload = {
        "__kind": "funding", "category": "reward", "event_type": "okx_earn_yield",
        "ccy": "USDT", "amount": "0.01862035", "ts": "1750000000000",
        "billId": "103917829937", "group_id": "103917829937",
    }
    ev = _normalize_okx_funding_event(payload)
    assert ev.category == "reward"
    assert ev.event_type == "okx_earn_yield"


def test_earn_subscription_crypto_maps_to_transfer_out_exempt():
    payload = {
        "__kind": "funding", "category": "transfer", "event_type": "okx_earn_subscription",
        "ccy": "BTC", "amount": "-0.05912186", "ts": "1750600000000",
        "billId": "103346408767", "group_id": "103346408767",
    }
    ev = _normalize_okx_funding_event(payload)
    assert ev.event_type == "okx_earn_subscription"
    assert ev.legs[0]["asset"] == "BTC"


# ---- full async pipeline ----
@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_full_funding_parser_persists_each_type(tmp_path, user, funding_account):
    rows = [
        {"id": "1", "Time": "2026-07-30 08:58:30", "Type": "Deposit yield", "Amount": "0.01862035", "Before Balance": "0.73387918", "After Balance": "0.75249953", "Symbol": "USDT"},
        {"id": "2", "Time": "2026-06-22 20:05:02", "Type": "From unified trading account", "Amount": "0.45849457", "Before Balance": "0", "After Balance": "0.45849457", "Symbol": "BTC"},
        {"id": "3", "Time": "2026-06-22 20:05:02", "Type": "Stake", "Amount": "-0.45849457", "Before Balance": "0.45849457", "After Balance": "0", "Symbol": "BTC"},
        {"id": "4", "Time": "2026-06-22 19:50:42", "Type": "Deposit", "Amount": "29994.781592", "Before Balance": "0", "After Balance": "29994.781592", "Symbol": "USDT"},
        {"id": "5", "Time": "2026-03-23 14:48:45", "Type": "Place an order", "Amount": "-400", "Before Balance": "400", "After Balance": "0", "Symbol": "USDT"},
    ]
    csv_path = tmp_path / "funding.csv"
    _write_funding_csv(csv_path, rows)

    updates = await _drain(parse_okx_funding_csv(str(csv_path), funding_account.id, user.id, confirm_every=False))
    assert "complete" in [u["status"] for u in updates]

    txs = await _txs(user, funding_account)
    assert len(txs) == 5
    by_event = {t.import_event_type for t in txs}
    assert by_event == {"okx_earn_yield", "okx_internal_transfer", "okx_earn_subscription", "okx_external_deposit", "okx_c2c_order"}
    # The internal-transfer BTC leg carries the synthesized group.
    btc_xfer = [t for t in txs if t.import_event_type == "okx_internal_transfer"][0]
    assert btc_xfer.type == "Crypto transfer in"
    assert btc_xfer.import_group_id.startswith("okx_xfer:btc:")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_funding_parser_dedups_on_reimport(tmp_path, user, funding_account):
    rows = [
        {"id": "1", "Time": "2026-07-30 08:58:30", "Type": "Deposit yield", "Amount": "0.01862035", "Before Balance": "0.73387918", "After Balance": "0.75249953", "Symbol": "USDT"},
    ]
    csv_path = tmp_path / "funding.csv"
    _write_funding_csv(csv_path, rows)

    await _drain(parse_okx_funding_csv(str(csv_path), funding_account.id, user.id, confirm_every=False))
    await _drain(parse_okx_funding_csv(str(csv_path), funding_account.id, user.id, confirm_every=False))

    txs = await _txs(user, funding_account)
    assert len(txs) == 1  # dedup on (provider, account, import_account_id, import_event_id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_funding_csv_parser.py -v --tb=short`
Expected: FAIL — `ImportError: cannot import name 'parse_okx_funding_csv'`.

- [ ] **Step 3: Implement the row mapper**

Add to `backend/services/importer.py` (after `_okx_internal_transfer_group_id` from Task 2):

```python
def _okx_funding_row_to_payload(row, tz_offset):
    """Map one Funding History CSV row to an event payload, or None to skip.

    Funding History schema: id, Time, Type, Amount, Before Balance,
    After Balance, Symbol. ``Amount`` is signed (IN positive, OUT negative).
    """
    row_type = _strip_okx_bom(row.get("Type")) or ""
    rtype = row_type.strip().lower()
    ccy = (_strip_okx_bom(row.get("Symbol")) or "").upper()
    amount = Decimal(str(row.get("Amount") or "0"))
    ts = _okx_time_to_utc_ms(_strip_okx_bom(row.get("Time")), tz_offset)
    row_id = str(_strip_okx_bom(row.get("id")) or "")
    is_stablecoin = ccy in {"USDT", "USDC"}

    if rtype == "from unified trading account":
        category = "deposit" if is_stablecoin else "transfer"   # IN to funding
        event_type = "okx_internal_transfer"
    elif rtype == "to unified trading account":
        category = "withdrawal" if is_stablecoin else "transfer"  # OUT of funding
        event_type = "okx_internal_transfer"
    elif rtype in {"stake", "simple earn subscription"}:
        category = "withdrawal" if is_stablecoin else "transfer"  # OUT to earn
        event_type = "okx_earn_subscription"
    elif rtype in {"simple earn redemption", "unstake"}:
        category = "deposit" if is_stablecoin else "transfer"     # IN from earn
        event_type = "okx_earn_redemption"
    elif rtype == "deposit yield":
        category = "reward"
        event_type = "okx_earn_yield"
    elif rtype == "deposit":
        # External on-chain deposit into funding.
        category = "deposit" if is_stablecoin else "transfer"
        event_type = "okx_external_deposit"
    elif rtype in {"place an order", "cancel an order", "fulfill an order"}:
        # C2C order lifecycle: sign-based cash (lock/unlock/fulfill).
        category = "deposit" if amount > 0 else "withdrawal"
        event_type = "okx_c2c_order"
    else:
        return None  # unhandled Type — caller skips

    # Internal crypto transfers pair with the trading CSV leg via the
    # synthesized key; everything else gets a unique (row-scoped) group id.
    group_id = (
        _okx_internal_transfer_group_id(ccy, amount, ts)
        if event_type == "okx_internal_transfer"
        else row_id
    )
    return {
        "__kind": "funding",
        "category": category,
        "event_type": event_type,
        "ccy": ccy,
        "amount": str(amount),
        "ts": str(ts),
        "billId": row_id,
        "group_id": group_id,
    }


def _build_okx_funding_events(df, tz_offset):
    """Map a Funding History CSV DataFrame into event payloads.

    Returns ``(events, skipped_ids)`` mirroring ``build_okx_csv_events``.
    """
    events = []
    skipped_ids = []
    for _, row in df.iterrows():
        row_id = str(_strip_okx_bom(row.get("id")) or "")
        payload = _okx_funding_row_to_payload(row, tz_offset)
        if payload is None:
            skipped_ids.append(row_id)
            continue
        events.append((payload, row_id))
    return events, skipped_ids
```

- [ ] **Step 4: Implement the normalizer**

Add to `backend/services/importer.py` (near `_normalize_okx_csv_event`):

```python
def _normalize_okx_funding_event(payload):
    """Build a CryptoExchangeEvent from a funding-history payload."""
    if payload.get("__kind") != "funding":
        return None
    ccy = payload["ccy"].upper()
    amount = Decimal(payload["amount"])
    return CryptoExchangeEvent(
        provider=OKX_CSV_IMPORT_PROVIDER,
        provider_event_id=f"csv_fund:{payload['billId']}",
        group_id=payload.get("group_id") or payload["billId"],
        timestamp_ms=int(payload["ts"]),
        category=payload["category"],
        raw_type="funding",
        event_type=payload["event_type"],
        legs=_single_leg(ccy, amount, ccy),
    )
```

(`CryptoExchangeEvent` and `_single_leg` are imported at the top of `importer.py` already — confirm; if not, add `from services.crypto_exchange import CryptoExchangeEvent, _single_leg` near the existing import at line ~1185 / module top. The trading parser already imports `persist_crypto_exchange_event` lazily inside the function; mirror that.)

- [ ] **Step 5: Implement the async generator**

Add to `backend/services/importer.py` (after `parse_okx_trading_csv`, ~line 1267):

```python
async def parse_okx_funding_csv(file_path, account_id, user_id, confirm_every):
    """Parse an OKX Funding History CSV and persist canonical crypto events.

    Async generator mirroring ``parse_okx_trading_csv``. Routes every funding
    ``Type`` to the user-selected OKX Funding account. Internal transfers
    carry a synthesized ``import_group_id`` so they pair with the trading
    CSV's ``Transfer in/out`` legs (#29 two-account model).
    """
    yield {"status": "initialization", "message": "Opening and reading OKX Funding History CSV"}

    try:
        with open(file_path, "r", encoding="utf-8-sig", newline="") as fh:
            first_line = fh.readline()
        tz_offset = _parse_okx_csv_tz_offset(first_line)

        df = pd.read_csv(file_path, header=1, encoding="utf-8-sig")
        if df.empty:
            raise ValueError("The OKX Funding CSV file is empty or could not be read.")
        df.columns = [str(c).lstrip("\ufeff").strip() for c in df.columns]
        string_cols = df.select_dtypes(include=["string", "object"]).columns
        for col in string_cols:
            df[col] = df[col].map(_strip_okx_bom)

        events, skipped_ids = _build_okx_funding_events(df, tz_offset)
        total_events = len(events)
    except Exception as exc:
        logger.exception("Failed to read OKX Funding CSV: %s", exc)
        yield {"status": "critical_error", "message": f"Failed to read CSV: {exc}"}
        return

    yield {"status": "initialization", "data": {"total_to_update": total_events}}

    try:
        investor = await get_investor(user_id)
        account = await get_account(account_id)
        logger.debug("Retrieved investor and OKX Funding account")
    except Exception as exc:
        yield {"status": "critical_error", "message": f"Account/investor lookup failed: {exc}"}
        return

    imported = 0
    duplicate = 0
    skipped = len(skipped_ids)
    import_errors = 0

    from services.crypto_exchange import persist_crypto_exchange_event

    for index, (payload, row_id) in enumerate(events):
        try:
            event = _normalize_okx_funding_event(payload)
            created = await database_sync_to_async(persist_crypto_exchange_event)(
                event, investor, account
            )
        except Exception as exc:
            logger.exception("Failed to persist OKX funding event %s: %s", row_id, exc)
            import_errors += 1
            yield {"status": "error", "message": f"Failed row {row_id}: {exc}", "transaction_id": row_id}
            continue

        if created:
            imported += len(created)
            yield {"status": "transaction_saved", "transaction_id": row_id, "data": {"event": payload}}
        else:
            duplicate += 1
            yield {"status": "duplicate_transaction", "transaction_id": row_id}

        if confirm_every and (index + 1) % confirm_every == 0:
            yield {"status": "progress", "data": {"current": index + 1, "total": total_events}}

    yield {
        "status": "complete",
        "data": {
            "totalTransactions": total_events + skipped,
            "importedTransactions": imported,
            "skippedTransactions": skipped,
            "duplicateTransactions": duplicate,
            "importErrors": import_errors,
        },
    }
    logger.debug("Yielded completion of OKX Funding CSV import process")
```

- [ ] **Step 6: Run the funding-parser tests**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_funding_csv_parser.py -v --tb=short`
Expected: PASS (all tests). If `test_full_funding_parser_persists_each_type` fails on a specific `Type` mapping, read the failure, recheck `_okx_funding_row_to_payload`, and fix — do not weaken the asserted `by_event` set.

- [ ] **Step 7: Commit**

```bash
git add backend/services/importer.py backend/tests/unit/services/test_okx_funding_csv_parser.py
git commit -m "feat(okx): Funding-History CSV parser + Type->event mapping

New parse_okx_funding_csv handles Deposit yield, From/To unified trading
account, Stake/Simple Earn subscribe+redeem, external Deposit, C2C orders.
Internal transfers carry the synthesized group_id; event_type tokens drive
the neutrality discriminator (#29)."
```

---

### Task 5: View-layer routing for funding-schema CSVs

Auto-detect the funding schema by header (the user uploads via the same modal; the app figures out which parser to call).

**Files:**
- Modify: `backend/services/importer.py` (add `_okx_csv_is_funding_schema`), `backend/transactions/views.py:718-726` (OKX branch).
- Test: `backend/tests/unit/services/test_okx_csv_schema_detection.py` (new).

**Interfaces:**
- Produces: `_okx_csv_is_funding_schema(file_path) -> bool` (in `importer.py`).
- Consumes: `parse_okx_funding_csv` (Task 4).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/services/test_okx_csv_schema_detection.py
"""Funding vs trading CSV schema detection."""


def _write(path, meta_line, header_line):
    with open(path, "w", encoding="utf-8-sig") as fh:
        fh.write(meta_line + "\n")
        fh.write(header_line + "\n")


def test_funding_schema_detected(tmp_path):
    p = tmp_path / "f.csv"
    _write(p, "\ufeffUID:x,\ufeffTime Zone:UTC+3",
           "\ufeffid,\ufeffTime,\ufeffType,\ufeffAmount,\ufeffBefore Balance,\ufeffAfter Balance,\ufeffSymbol")
    from services.importer import _okx_csv_is_funding_schema
    assert _okx_csv_is_funding_schema(str(p)) is True


def test_trading_schema_not_detected_as_funding(tmp_path):
    p = tmp_path / "t.csv"
    _write(p, "\ufeffUID:x,\ufeffTime Zone:UTC+3",
           "\ufeffid,\ufeffOrder id,\ufeffTime,\ufeffTrade Type,\ufeffSymbol,\ufeffAction,\ufeffAmount")
    from services.importer import _okx_csv_is_funding_schema
    assert _okx_csv_is_funding_schema(str(p)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_csv_schema_detection.py -v --tb=short`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement the detector**

Add to `backend/services/importer.py` (near `_parse_okx_csv_tz_offset`):

```python
def _okx_csv_is_funding_schema(file_path):
    """Return True when the CSV header matches the Funding History schema.

    Detection keys on the Funding-only columns (``Before Balance`` /
    ``After Balance``) being present and the Trading-only column
    (``Trade Type``) being absent. Robust to the BOM OKX prepends.
    """
    try:
        with open(file_path, "r", encoding="utf-8-sig", newline="") as fh:
            fh.readline()  # metadata line (UID/Time Zone)
            header_line = fh.readline()
    except OSError:
        return False
    header = {str(c).lstrip("\ufeff").strip().lower() for c in header_line.split(",")}
    return "before balance" in header and "after balance" in header and "trade type" not in header
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_csv_schema_detection.py -v --tb=short`
Expected: PASS.

- [ ] **Step 5: Wire the view branch**

In `backend/transactions/views.py`, add to the OKX-imports block at the top:

```python
from services.importer import _okx_csv_is_funding_schema, parse_okx_funding_csv
```

(alongside the existing `parse_okx_trading_csv` import at line 37).

Replace the OKX branch (lines 718-726) with:

```python
            elif "OKX" in account.broker.name.upper():
                # Route to the Funding or Trading parser by CSV schema. The
                # user uploads via the same modal and selects the target
                # account (OKX Funding or OKX Trading); the schema detector
                # picks the correct parser (#29 two-account model).
                parser = (
                    parse_okx_funding_csv
                    if _okx_csv_is_funding_schema(file_path)
                    else parse_okx_trading_csv
                )
                async for update in parser(file_path, account_id, user.id, confirm_every):
                    yield update
```

- [ ] **Step 6: Run the OKX test suites for regression**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_csv_schema_detection.py tests/unit/services/test_okx_csv_parser.py tests/unit/services/test_okx_funding_csv_parser.py -v --tb=short`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/services/importer.py backend/transactions/views.py backend/tests/unit/services/test_okx_csv_schema_detection.py
git commit -m "feat(okx): auto-route CSV to funding vs trading parser by schema

_okx_csv_is_funding_schema detects the Funding History header; the OKX view
branch dispatches accordingly so the user reuses the existing upload modal."
```

---

### Task 6: Unconditionally-neutral discriminator + walker gate rewire

Exempt earn moves from disposition so the flag can flip safely. The discriminator keys on the `import_event_type` tokens set by Task 1/Task 4.

**Files:**
- Modify: `backend/services/transactions.py:113-118` region (add predicate + token set), `backend/services/realized.py:67-74` (import), `:964-980` (walker gate).
- Test: `backend/tests/unit/services/test_realized_transfer_disposition.py` (new).

**Interfaces:**
- Produces: `is_unconditionally_neutral_transfer(transaction) -> bool` and `UNCONDITIONALLY_NEUTRAL_TRANSFER_TOKENS` (in `transactions.py`).
- Consumes: `TRANSFER_DISPOSITION_ENABLED`, `_transfer_is_matched` (both in `realized.py`).

> **Leave the flag `False` for this task** — Task 8 flips it. The discriminator must work whether the flag is on or off.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/services/test_realized_transfer_disposition.py
"""The earn-token discriminator keeps earn crypto legs neutral even when
TRANSFER_DISPOSITION_ENABLED is True and the leg is unmatched."""
from decimal import Decimal

import pytest

from common.models import Accounts, Assets, Brokers, CustomUser, Transactions
from services import realized as realized_mod
from services.realized import realized_gain_loss


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(username="disc-user", password="x")


@pytest.fixture
def btc(user):
    return Assets.objects.create(name="BTC", isin="BTC", asset_type="crypto")


@pytest.fixture
def account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    return Accounts.objects.create(broker=broker, name="OKX Funding", native_id="funding")


def _tx(user, account, btc, qty, event_type, tx_type="Crypto transfer out"):
    return Transactions.objects.create(
        investor=user, account=account, security=btc, currency="USD",
        type=tx_type, date="2026-06-22 20:00:00", quantity=Decimal(qty),
        price=Decimal("100"), import_provider="okx_csv", import_account_id="funding",
        import_event_id=f"e-{event_type}-{qty}", import_group_id=f"g-{event_type}-{qty}",
        import_event_type=event_type,
    )


@pytest.mark.django_db(transaction=True)
def test_earn_subscription_stays_neutral_when_flag_on(user, account, btc, monkeypatch):
    # Open a long BTC position, then an earn subscription OUT (no partner leg).
    Transactions.objects.create(investor=user, account=account, security=btc, currency="USD",
        type="Crypto trade in", date="2026-06-20 20:00:00", quantity=Decimal("1"), price=Decimal("100"))
    _tx(user, account, btc, "-0.5", "okx_earn_subscription")
    monkeypatch.setattr(realized_mod, "TRANSFER_DISPOSITION_ENABLED", True)

    result = realized_gain_loss(btc, "2026-07-01", user)
    # Earn subscription is unconditionally neutral -> no realized G/L.
    assert result["all_time"]["total"] == Decimal("0")


@pytest.mark.django_db
def test_external_deposit_unmatched_realizes_zero_basis_when_flag_on(user, account, btc, monkeypatch):
    # An external crypto IN (unmatched, disposition-eligible) opens a zero-basis lot.
    _tx(user, account, btc, "0.5", "okx_external_deposit", tx_type="Crypto transfer in")
    # Then sell half.
    Transactions.objects.create(investor=user, account=account, security=btc, currency="USD",
        type="Crypto trade out", date="2026-06-23 20:00:00", quantity=Decimal("-0.25"), price=Decimal("200"),
        cash_flow=Decimal("50"))
    monkeypatch.setattr(realized_mod, "TRANSFER_DISPOSITION_ENABLED", True)

    result = realized_gain_loss(btc, "2026-07-01", user)
    # Zero-basis lot (0.25 @ 0) sold for 50 -> realized = 50.
    assert result["all_time"]["total"] == Decimal("50")
```

> **Note:** the exact `result["all_time"]["total"]` shape comes from `realized_gain_loss`'s return structure (the walker yields an `"all_time"` bucket — confirmed by call sites `summary_analysis/views.py:209` reading `["all_time"]["total"]`). If the key differs, open `services/realized.py` `realized_gain_loss`'s return and adjust the assertion to the real top-level realized total key. Do not weaken the assertion to `>= 0`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_realized_transfer_disposition.py -v --tb=short`
Expected: FAIL — the earn-subscription test realizes a gain (the discriminator doesn't exist yet, so with the flag monkeypatched True the unmatched OUT falls through).

- [ ] **Step 3: Add the discriminator to `services/transactions.py`**

After `is_neutral_transfer_transaction` (after line 118), add:

```python
# import_event_type tokens that mark a crypto transfer as a principal-only
# internal book move (Simple Earn subscribe/redeem, stake/unstake). These
# are unconditionally neutral: they never fall through to disposition,
# regardless of TRANSFER_DISPOSITION_ENABLED, because the round-trip nets
# to zero and only the (separately-recognized) Deposit yield is income.
# See sub-project 5a / issue #29.
UNCONDITIONALLY_NEUTRAL_TRANSFER_TOKENS = frozenset(
    {
        "okx_earn_subscription",
        "okx_earn_redemption",
    }
)


def is_unconditionally_neutral_transfer(transaction):
    """True when a crypto transfer is a principal-only book move that must
    never realize, independent of ``TRANSFER_DISPOSITION_ENABLED``."""
    if transaction.type not in (
        TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
        TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    ):
        return False
    return (transaction.import_event_type or "") in UNCONDITIONALLY_NEUTRAL_TRANSFER_TOKENS
```

- [ ] **Step 4: Rewire the walker gate in `services/realized.py`**

Add to the import block at lines 67-74:

```python
from services.transactions import (
    get_price as _transactions_get_price,
    is_disposal_transaction as _transactions_is_disposal_transaction,
    is_neutral_transfer_transaction as _transactions_is_neutral_transfer_transaction,
    is_paid_entry_transaction as _transactions_is_paid_entry_transaction,
    is_reward_transaction as _transactions_is_reward_transaction,
    is_unconditionally_neutral_transfer as _transactions_is_unconditionally_neutral_transfer,
    reward_value as _transactions_reward_value,
)
```

Replace the transfer gate block (lines 964-980) with:

```python
            if _transactions_is_neutral_transfer_transaction(transaction):
                # When TRANSFER_DISPOSITION_ENABLED is True (#29), an unmatched
                # transfer falls through to the disposal/entry branches below
                # — UNLESS it is an unconditionally-neutral book move (Simple
                # Earn subscribe/redeem, stake/unstade): those are principal-
                # only and must never realize, regardless of the flag.
                if (
                    TRANSFER_DISPOSITION_ENABLED
                    and not _transactions_is_unconditionally_neutral_transfer(transaction)
                    and not _transfer_is_matched(transaction, investor, account_ids)
                ):
                    logger.debug(
                        "Unmatched %s for asset %s: treating as disposition/entry.",
                        transaction.type, getattr(asset, "name", asset),
                    )
                    # fall through to is_position_reducing logic below
                else:
                    position += transaction.quantity
                    logger.debug(f"Position after neutral transfer: {position}")
                    continue
```

- [ ] **Step 5: Run the discriminator tests**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_realized_transfer_disposition.py -v --tb=short`
Expected: PASS (both tests).

- [ ] **Step 6: Run the full realized/test suite for regression (flag still False)**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_realized_transfer_disposition.py tests/unit/services/test_okx_csv_parser.py -v --tb=short`
Expected: PASS — with the flag still False, existing transfer behavior is unchanged.

- [ ] **Step 7: Commit**

```bash
git add backend/services/transactions.py backend/services/realized.py backend/tests/unit/services/test_realized_transfer_disposition.py
git commit -m "feat(realized): unconditionally-neutral discriminator for earn transfers

is_unconditionally_neutral_transfer exempts okx_earn_* crypto legs from
disposition so TRANSFER_DISPOSITION_ENABLED can flip True safely (#29).
Flag stays False here; Task 8 flips it."
```

---

### Task 7: Cross-account basis-carry regression tests

The existing `lookup_group_transfer_basis` partner-leg query is investor-scoped (no account filter — confirmed at `realized.py:709-719, 767-783`), and `realized_gain_loss`'s dominant call pattern is portfolio-wide. So matched internal transfers are *expected* to carry basis funding→trading already. This task proves it in both walker modes (portfolio-wide and per-account). **The deliverable is the test coverage; if an assertion fails, raise a follow-up task — do not weaken the assertion.**

**Files:**
- Test: `backend/tests/unit/services/test_okx_internal_transfer_pairing.py` (new).

**Interfaces:**
- Consumes: `_okx_internal_transfer_group_id`, `realized_gain_loss`, `parse_okx_funding_csv`, `parse_okx_trading_csv`.

- [ ] **Step 1: Write the regression tests**

```python
# backend/tests/unit/services/test_okx_internal_transfer_pairing.py
"""Matched internal funding<->trading transfers carry basis cross-account
in both portfolio-wide and per-account realized-walker modes (#29)."""
from decimal import Decimal

import pytest
from channels.db import database_sync_to_async

from common.models import Accounts, Assets, Brokers, CustomUser, Transactions
from services.realized import get_economic_basis


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(username="pair-user", password="x")


@pytest.fixture
def broker(user):
    return Brokers.objects.create(investor=user, name="OKX", country="Crypto")


@pytest.fixture
def funding(user, broker):
    return Accounts.objects.create(broker=broker, name="OKX Funding", native_id="funding")


@pytest.fixture
def trading(user, broker):
    return Accounts.objects.create(broker=broker, name="OKX Trading", native_id="trading")


@pytest.fixture
def btc(user):
    return Assets.objects.create(name="BTC", isin="BTC", asset_type="crypto")


def _buy(user, account, btc, qty, price, date, group):
    Transactions.objects.create(
        investor=user, account=account, security=btc, currency="USD",
        type="Crypto trade in", date=date, quantity=Decimal(qty), price=Decimal(price),
        import_provider="okx_csv", import_account_id=account.native_id,
        import_event_id=f"buy-{account.id}-{group}", import_group_id=group, import_event_type="trade",
    )


def _xfer(user, account, btc, qty, date, group, direction):
    tx_type = "Crypto transfer in" if direction == "in" else "Crypto transfer out"
    Transactions.objects.create(
        investor=user, account=account, security=btc, currency="USD",
        type=tx_type, date=date, quantity=Decimal(qty), price=None,
        import_provider="okx_csv", import_account_id=account.native_id,
        import_event_id=f"xfer-{account.id}-{group}", import_group_id=group,
        import_event_type="okx_internal_transfer",
    )


@pytest.mark.django_db
def test_basis_carries_portfolio_wide(user, funding, trading, btc):
    """Portfolio-wide walker: funding OUT + trading IN in one replay."""
    group = "okx_xfer:btc:0.5:1750000000"
    _buy(user, funding, btc, "1", "100", "2026-06-20 20:00:00", "b1")
    _xfer(user, funding, btc, "-0.5", "2026-06-22 20:00:00", group, "out")
    _xfer(user, trading, btc, "0.5", "2026-06-22 20:00:01", group, "in")

    # Economic basis on the trading account should equal the funding cost of 0.5 BTC.
    basis, qty = get_economic_basis(btc, "2026-06-23", user, account_ids=None)
    # The trading leg reclaims the funding basis (50 = 0.5 * 100).
    assert qty == Decimal("0.5")
    assert basis == Decimal("50")


@pytest.mark.django_db
def test_basis_carries_per_account_via_recursive_lookup(user, funding, trading, btc):
    """Per-account walker (account_ids=[trading]) exercises the recursive
    cross-account fallback in lookup_group_transfer_basis."""
    group = "okx_xfer:btc:0.5:1750000000"
    _buy(user, funding, btc, "1", "100", "2026-06-20 20:00:00", "b1")
    _xfer(user, funding, btc, "-0.5", "2026-06-22 20:00:00", group, "out")
    _xfer(user, trading, btc, "0.5", "2026-06-22 20:00:01", group, "in")

    basis, qty = get_economic_basis(btc, "2026-06-23", user, account_ids=[trading.id])
    assert qty == Decimal("0.5")
    assert basis == Decimal("50")
```

> **Signature check:** `get_economic_basis` may return a basis object rather than a `(basis, qty)` tuple. Before finalizing, open `services/realized.py` `get_economic_basis` and confirm its return shape. If it returns a dict/namedtuple, adjust the two assignment lines (`basis, qty = ...`) to the real shape and update the assertions accordingly. The economic invariant being asserted — *trading-side basis after a matched 0.5 BTC transfer equals the funding-side cost of 50* — must be preserved; only the access path adapts.

> **If a test fails:** the cross-account basis carry has a real bug. Raise a follow-up task to fix `lookup_group_transfer_basis` / `transactions_before` (likely the recursive replay's account scoping). Do **not** change `Decimal("50")` to make the test pass.

- [ ] **Step 2: Run the tests**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_internal_transfer_pairing.py -v --tb=short`
Expected: PASS. If FAIL, follow the "If a test fails" note above and stop this task — surface the finding.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/services/test_okx_internal_transfer_pairing.py
git commit -m "test(realized): cross-account basis carry for matched transfers

Regression coverage proving funding->trading basis carry works in both
portfolio-wide and per-account walker modes (#29). Machinery already spans
accounts; this locks the invariant."
```

---

### Task 8: Flip `TRANSFER_DISPOSITION_ENABLED = True`

The gated capstone. With pairing (Tasks 2-5) and the earn discriminator (Task 6) in place, only genuine external crypto flows realize. This is the last code change before integration.

**Files:**
- Modify: `backend/services/realized.py:99-104`.
- Test: update any existing test that asserted the old all-neutral behavior.

**Interfaces:**
- Produces: `TRANSFER_DISPOSITION_ENABLED = True`.

- [ ] **Step 1: Flip the flag + update the comment**

Replace `backend/services/realized.py:99-104` with:

```python
# Matched crypto transfers (both legs in-portfolio, paired via
# import_group_id) stay neutral and carry basis cross-account. Unmatched
# transfers (genuine external flows) realize gain/loss. Earn book-moves
# (okx_earn_subscription / okx_earn_redemption) are exempted by
# is_unconditionally_neutral_transfer and stay neutral regardless.
# Activated by sub-project 5a / issue #29 (two-account model).
TRANSFER_DISPOSITION_ENABLED = True
```

- [ ] **Step 2: Run the full test suite to find affected tests**

Run: `uv run python -m pytest -c pytest.ini -v --tb=short 2>&1 | tail -60`
Expected: mostly PASS; collect any FAILures.

- [ ] **Step 3: Triage and update affected tests**

For each failure caused by the flag flip (i.e. a test that previously asserted a crypto transfer realized `0` and now sees a non-zero value because its transfer is unmatched and untagged):
- Open the failing test.
- If the transfer is meant to be neutral (an internal move), give it a real partner leg (so `_transfer_is_matched` returns True) OR tag it `okx_internal_transfer` with a matching group — reflecting the post-#29 world where internal transfers are paired.
- If the transfer is meant to be a genuine external flow, update the assertion to the new (correct) realized value.
- Do **not** revert the flag or add `monkeypatch.setattr(..., False)` to silence the failure.

Re-run after each fix:
Run: `uv run python -m pytest -c pytest_fast.ini <fixed-test-file> -v --tb=short`

- [ ] **Step 4: Run the full suite green**

Run: `uv run python -m pytest -c pytest.ini -v --tb=short`
Expected: PASS (all suites).

- [ ] **Step 5: Commit**

```bash
git add backend/services/realized.py <any updated test files>
git commit -m "feat(realized): enable matched-vs-unmatched transfer disposition (#29)

Flip TRANSFER_DISPOSITION_ENABLED True. Matched internal transfers carry
basis cross-account (neutral); genuine external crypto flows realize; earn
book-moves stay neutral via the discriminator. Updated affected legacy tests
to reflect paired internal transfers."
```

---

### Task 9: Backfill management command `migrate_okx_two_account`

Idempotently splits an OKX broker's single account into Trading + Funding **without touching transactions**.

**Files:**
- Create: `backend/common/management/commands/migrate_okx_two_account.py`.
- Test: `backend/tests/unit/management/test_migrate_okx_two_account.py` (new; create `tests/unit/management/__init__.py` if missing).

**Interfaces:**
- Produces: `Command` (`migrate_okx_two_account <broker_name> [--dry-run]`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/management/test_migrate_okx_two_account.py
"""migrate_okx_two_account: rename existing -> Trading, create Funding, no tx rewrite."""
import pytest
from django.core.management import call_command

from common.models import Accounts, Brokers, CustomUser, Transactions


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(username="bf-user", password="x")


@pytest.fixture
def okx_broker_with_legacy_account(user):
    broker = Brokers.objects.create(investor=user, name="OKX", country="Crypto")
    legacy = Accounts.objects.create(broker=broker, name="Unified", native_id="okx-main")
    return broker, legacy


@pytest.mark.django_db
def test_renames_legacy_to_trading_and_creates_funding(user, okx_broker_with_legacy_account):
    broker, legacy = okx_broker_with_legacy_account
    # One historical transaction on the legacy account.
    Transactions.objects.create(investor=user, account=legacy, type="Crypto trade in",
        date="2026-01-01 00:00:00", quantity=1, price=100, currency="USD")

    call_command("migrate_okx_two_account", "OKX")

    accounts = {a.native_id: a for a in Accounts.objects.filter(broker=broker)}
    assert set(accounts) == {"trading", "funding"}
    assert accounts["trading"].name == "OKX Trading"
    assert accounts["funding"].name == "OKX Funding"
    # The legacy row was renamed in place (same pk) -> tx still attached.
    assert accounts["trading"].pk == legacy.pk
    assert Transactions.objects.filter(account=accounts["trading"]).count() == 1
    assert Transactions.objects.filter(account=accounts["funding"]).count() == 0


@pytest.mark.django_db
def test_idempotent(okx_broker_with_legacy_account):
    broker, legacy = okx_broker_with_legacy_account
    call_command("migrate_okx_two_account", "OKX")
    call_command("migrate_okx_two_account", "OKX")  # second run is a no-op
    assert Accounts.objects.filter(broker=broker, native_id="trading").count() == 1
    assert Accounts.objects.filter(broker=broker, native_id="funding").count() == 1


@pytest.mark.django_db
def test_dry_run_makes_no_changes(okx_broker_with_legacy_account):
    broker, legacy = okx_broker_with_legacy_account
    call_command("migrate_okx_two_account", "OKX", "--dry-run")
    assert legacy.name == "Unified"  # unchanged
    assert Accounts.objects.filter(broker=broker).count() == 1


@pytest.mark.django_db
def test_missing_broker_reports_error(capsys):
    call_command("migrate_okx_two_account", "Nope")
    out = capsys.readouterr().out
    assert "not found" in out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/management/test_migrate_okx_two_account.py -v --tb=short`
Expected: FAIL — `CommandError: Unknown command: 'migrate_okx_two_account'`.

- [ ] **Step 3: Implement the command**

```python
# backend/common/management/commands/migrate_okx_two_account.py
"""Management command: split an OKX broker's single account into Trading + Funding.

Usage:
    uv run python manage.py migrate_okx_two_account "OKX" [--dry-run]

Sub-project 5a / issue #29. Idempotent: renames the broker's existing account
to "OKX Trading" (native_id=trading) and get_or_creates an "OKX Funding"
account (native_id=funding). Touches NO transactions, so historical NAV is
unchanged. Run after creating the two accounts so the funding-history CSV can
be imported into the Funding account.
"""
from django.core.management.base import BaseCommand

from common.models import Accounts, Brokers


class Command(BaseCommand):
    help = "Split an OKX broker's single account into Trading + Funding (#29)."

    def add_arguments(self, parser):
        parser.add_argument(
            "broker_name",
            type=str,
            help="Exact name of the OKX broker whose account should be split.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without saving.",
        )

    def handle(self, *args, **options):
        broker_name = options["broker_name"]
        dry_run = options["dry_run"]

        try:
            broker = Brokers.objects.get(name=broker_name)
        except Brokers.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Broker {broker_name!r} not found."))
            return

        # Already migrated?
        trading = Accounts.objects.filter(broker=broker, native_id="trading").first()
        funding = Accounts.objects.filter(broker=broker, native_id="funding").first()
        if trading and funding:
            self.stdout.write(self.style.WARNING(
                f"{broker_name} already has Trading (id={trading.id}) and Funding "
                f"(id={funding.id}) accounts. Nothing to do."
            ))
            return

        # Pick the legacy account to rename: the first non-funding account.
        legacy = Accounts.objects.filter(broker=broker).exclude(native_id="funding").first()
        if legacy is None:
            self.stdout.write(self.style.ERROR(
                f"{broker_name} has no account to rename into Trading. Create one first."
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY RUN: would rename account {legacy.id} ({legacy.name!r}) -> "
                f"'OKX Trading' (native_id=trading) and create 'OKX Funding' (native_id=funding)."
            ))
            return

        legacy.name = "OKX Trading"
        legacy.native_id = "trading"
        legacy.save(update_fields=["name", "native_id"])
        funding, created = Accounts.objects.get_or_create(
            broker=broker, native_id="funding",
            defaults={"name": "OKX Funding"},
        )
        self.stdout.write(self.style.SUCCESS(
            f"Renamed account {legacy.id} -> 'OKX Trading' (native_id=trading). "
            + ("Created 'OKX Funding' (id=%d)." % funding.id if created else "'OKX Funding' already existed (id=%d)." % funding.id)
            + " No transactions were modified."
        ))
```

- [ ] **Step 4: Run the command tests**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/management/test_migrate_okx_two_account.py -v --tb=short`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add backend/common/management/commands/migrate_okx_two_account.py backend/tests/unit/management/
git commit -m "feat(management): migrate_okx_two_account backfill command

Idempotently renames an OKX broker's existing account -> OKX Trading and
creates OKX Funding. Touches no transactions -> historical NAV unchanged (#29)."
```

---

### Task 10: End-to-end integration test — funding + trading CSV pairing

Proves the whole flow on realistic data: import a trading CSV and a funding CSV into their respective accounts, assert internal transfers pair (same `import_group_id` on both legs), yield posts as income, and `_transfer_is_matched` returns True for both legs.

**Files:**
- Test: append to `backend/tests/unit/services/test_okx_internal_transfer_pairing.py`.

**Interfaces:**
- Consumes: `parse_okx_trading_csv`, `parse_okx_funding_csv`, `_transfer_is_matched`.

- [ ] **Step 1: Write the integration test**

```python
# append to backend/tests/unit/services/test_okx_internal_transfer_pairing.py
import pytest
from channels.db import database_sync_to_async

from common.models import Transactions
from services.importer import parse_okx_funding_csv, parse_okx_trading_csv
from services.realized import _transfer_is_matched


# reuse the trading-CSV writer helpers from test_okx_csv_parser.py if importable;
# otherwise define minimal local writers matching that file's pattern.
async def _drain(gen):
    return [u async for u in gen]


@database_sync_to_async
def _all_txs(user):
    return list(Transactions.objects.filter(investor=user).order_by("date", "id"))


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_funding_and_trading_csvs_pair_internal_btc_transfer(
    tmp_path, user, broker, funding, trading
):
    """Import both CSVs; the BTC internal-transfer legs share import_group_id
    and are mutually matched."""
    # Funding CSV: one 'From unified trading account' BTC in at 2026-06-22 20:05:02 UTC+3.
    funding_rows = [{
        "id": "103346514176", "Time": "2026-06-22 20:05:02",
        "Type": "From unified trading account", "Amount": "0.45849457",
        "Before Balance": "0", "After Balance": "0.45849457", "Symbol": "BTC",
    }]
    # Trading CSV: the matching 'Transfer out' BTC leg at the same instant.
    trading_rows = [{
        "id": "770000000001", "Order id": "", "Time": "2026-06-22 20:05:02",
        "Trade Type": "Transfer", "Symbol": "BTC-USDT", "Action": "Transfer out",
        "Amount": "0.45849457", "Trading Unit": "BTC", "Filled Price": "",
        "PnL": "", "Fee": "", "Fee Unit": "", "Position Change": "",
        "Position Balance": "", "Balance Change": "-0.45849457", "Balance": "",
        "Balance Unit": "BTC",
    }]
    fund_csv = tmp_path / "fund.csv"
    trade_csv = tmp_path / "trade.csv"
    _write_funding_csv(fund_csv, funding_rows)          # local helper (see test_okx_funding_csv_parser.py)
    _write_okx_trading_csv(trade_csv, trading_rows)     # local helper mirroring test_okx_csv_parser.py

    await _drain(parse_okx_trading_csv(str(trade_csv), trading.id, user.id, confirm_every=False))
    await _drain(parse_okx_funding_csv(str(fund_csv), funding.id, user.id, confirm_every=False))

    txs = await _all_txs(user)
    assert len(txs) == 2
    funding_in = [t for t in txs if t.account_id == funding.id][0]
    trading_out = [t for t in txs if t.account_id == trading.id][0]
    assert funding_in.type == "Crypto transfer in"
    assert trading_out.type == "Crypto transfer out"
    # Same synthesized group across both legs.
    assert funding_in.import_group_id == trading_out.import_group_id
    assert funding_in.import_group_id.startswith("okx_xfer:btc:")
    # Mutually matched.
    assert _transfer_is_matched(funding_in, user) is True
    assert _transfer_is_matched(trading_out, user) is True
```

> **Helper note:** `_write_funding_csv` is defined in `test_okx_funding_csv_parser.py` (Task 4); `_write_okx_trading_csv` mirrors `_write_okx_csv` in `test_okx_csv_parser.py`. If cross-file helper import is awkward, copy the two small helpers into this test file. Keep the row shapes exactly as shown so the timestamps produce the same epoch second on both sides.

- [ ] **Step 2: Run the integration test**

Run: `uv run python -m pytest -c pytest_fast.ini tests/unit/services/test_okx_internal_transfer_pairing.py::test_funding_and_trading_csvs_pair_internal_btc_transfer -v --tb=short`
Expected: PASS. If `_transfer_is_matched` returns False for either leg, the two `import_group_id` values differ — debug the epoch-second alignment of the two writers (the timestamps must land in the same UTC second).

- [ ] **Step 3: Run the entire test suite green**

Run: `uv run python -m pytest -c pytest.ini -v --tb=short`
Expected: PASS (full suite, including pre-existing 1217 tests).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/unit/services/test_okx_internal_transfer_pairing.py
git commit -m "test(okx): end-to-end funding+trading CSV transfer pairing (#29)

Importing both CSVs into their respective accounts produces two legs that
share import_group_id and are mutually _transfer_is_matched -> neutral with
cross-account basis carry."
```

---

## Self-Review notes

**Spec coverage:** every spec section maps to a task — account modeling (Task 9 backfill + reused two-account test fixtures), funding parser (Task 4), pairing (Tasks 2-3), discriminator + flag (Tasks 6 + 8), cross-account carry (Task 7), backfill (Task 9), view routing (Task 5), integration (Task 10). Non-goals (API tagging, /asset/bills, full backfill, MTM-at-deposit, account_type field) are explicitly deferred to 5b — no task implements them.

**Open follow-ups surfaced by planning (5b candidates):**
- The `event_type` field is the provenance channel; the API adapter (5b) will need to set the same tokens when it tags sub-accounts.
- If Task 7 reveals a real cross-account carry bug, a focused `realized.py` fix becomes its own task (protected — PR + needs-approval).
- External crypto deposits are zero-basis in 5a; MTM-at-deposit is a later enhancement.
