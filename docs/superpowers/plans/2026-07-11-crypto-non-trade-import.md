# Crypto Non-Trade Transaction Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the ByBit/OKX crypto import to handle deposits, withdrawals, earn/rewards, and BTC option premium trades + expiry settlements — in addition to the existing spot trades — via a unified time-sorted event stream.

**Architecture:** Generalize `CryptoExchangeEvent` as `category` + `legs[]` (single-leg for deposits/withdrawals/rewards/options, two-leg for spot). Each adapter calls multiple exchange endpoints, merges their normalized events by `timestamp_ms` via a shared k-way merge utility, and yields one unified stream to the unchanged persistence path. The only persistence-layer change is an `instrument` dispatch (coin vs option resolver) and a new `settlement` category branch.

**Tech Stack:** Python 3.13, Django, `requests` (hand-rolled signed REST), `yfinance`, `Decimal`, pytest.

## Global Constraints

These apply to every task. Copied verbatim from `AGENTS.md` and the approved spec.

- **Numeric safety:** Always use `Decimal` for money/price math — never `float`. Internal precision ≥ 6 dp for prices, ≥ 9 dp for quantities/FX. Rounding: `ROUND_HALF_UP`. Persisted aggregates: 2 dp.
- **Protected code:** `backend/**/calculations*.py`, `backend/**/performance*.py`, `backend/**/services/performance/**`, `backend/**/services/fx/**`, `backend/**/services/bonds/**`, `common/models.py`, and all `migrations/**` must NOT change. Changes to `persist_crypto_exchange_event` numeric behavior require human approval (this plan only changes its asset-resolution *dispatch*, not formulas).
- **No schema/migration changes:** The crypto TX types (`Crypto reward`, `Crypto transfer in/out`, `Crypto trade in/out`), `Option settlement`, `OptionMetadata`, and the `import_*` idempotency fields already exist.
- **Tests:** `Decimal` everywhere, edge cases (zero quantity, missing price). All changes must pass `pytest`.
- **Test discovery:** Unit normalize tests run via `pytest tests/unit/imports/test_crypto_exchange_import.py`; integration tests via `pytest tests/integration/workflows/test_crypto_exchange_persistence.py`.
- **Commit style:** Each task ends with a commit. Spec-impl changes use `feat:`; pure test additions use `test:`; the spec doc is already committed.
- **Backward compat:** The existing `parse_option_symbol` tests (ByBit `DDMMMYY` format) MUST keep passing after the parser rewrite. The rewrite auto-detects format; it does not replace the ByBit branch.

---

## File Structure

**Files modified (all in `backend/`):**

| File | Responsibility | Changes |
|---|---|---|
| `core/crypto_exchange_import.py` | Normalize exchange payloads → `CryptoExchangeEvent`; persist events. | Add `_single_leg`, `_merge_sorted_events`, 8 new normalizers, rewrite `parse_option_symbol`, extend `_transaction_type_for_event` + `persist_crypto_exchange_event` dispatch. |
| `core/crypto_exchange_clients.py` | Signed REST clients + pagination iterators. | Add `BybitClient.iter_deposits`, `iter_withdrawals`, `iter_option_executions`, `iter_option_settlements`; `OKXClient.iter_asset_deposits_withdrawals`, `iter_earn_lending_history`, `iter_option_fills`, `iter_option_settlements`. |
| `core/broker_api_utils.py` | `BybitAPI`/`OKXAPI` adapters + `get_broker_api` factory. | Extend `get_transactions` on both adapters to call all endpoints, merge via `_merge_sorted_events`, track `partial_failures`. |
| `tests/unit/imports/test_crypto_exchange_import.py` | Unit tests for normalizers + parser + merge. | Add tests for every new unit; keep existing tests green. |
| `tests/unit/api/test_crypto_exchange_clients.py` | Unit tests for client iterators. | Add tests for new iterators. |
| `tests/integration/workflows/test_crypto_exchange_persistence.py` | Integration tests for persistence. | Add single-leg + option regression tests. |

**Files NOT touched (protected):** `common/models.py`, all `migrations/**`, `core/portfolio_utils.py`, `core/securities_utils.py`, frontend.

---

## Task 1: `_single_leg` helper

**Files:**
- Modify: `core/crypto_exchange_import.py` (add near `_spot_legs`, ~line 341)
- Test: `tests/unit/imports/test_crypto_exchange_import.py`

**Interfaces:**
- Produces: `_single_leg(asset: str, quantity: Decimal, price_asset: str, role: str = "base", instrument: str = "coin") -> List[Dict[str, Any]]` — returns a one-element legs list.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/imports/test_crypto_exchange_import.py`:

```python
from core.crypto_exchange_import import _single_leg


def test_single_leg_builds_one_element_list_with_defaults():
    legs = _single_leg("BTC", Decimal("0.001"), "BTC")

    assert len(legs) == 1
    leg = legs[0]
    assert leg["asset"] == "BTC"
    assert leg["quantity"] == Decimal("0.001")
    assert leg["price"] is None
    assert leg["price_asset"] == "BTC"
    assert leg["role"] == "base"
    assert leg["instrument"] == "coin"


def test_single_leg_accepts_option_instrument():
    legs = _single_leg("BTC-27DEC24-75000-C", Decimal("2"), "USDT", role="base", instrument="option")

    assert legs[0]["instrument"] == "option"
    assert legs[0]["role"] == "base"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py::test_single_leg_builds_one_element_list_with_defaults tests/unit/imports/test_crypto_exchange_import.py::test_single_leg_accepts_option_instrument -v`
Expected: FAIL with `ImportError: cannot import name '_single_leg'`

- [ ] **Step 3: Implement `_single_leg`**

Add to `core/crypto_exchange_import.py` just above `def _spot_legs` (line ~334):

```python
def _single_leg(asset, quantity, price_asset, role="base", instrument="coin"):
    """Build a one-element legs list for deposits, withdrawals, rewards, and options."""
    return [
        {
            "asset": asset,
            "quantity": quantity,
            "price": None,
            "price_asset": price_asset,
            "role": role,
            "instrument": instrument,
        }
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py::test_single_leg_builds_one_element_list_with_defaults tests/unit/imports/test_crypto_exchange_import.py::test_single_leg_accepts_option_instrument -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run full existing test file to confirm no regressions**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Expected: all previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add core/crypto_exchange_import.py tests/unit/imports/test_crypto_exchange_import.py
git commit -m "feat: add _single_leg helper for single-leg crypto import events"
```

---

## Task 2: `_merge_sorted_events` utility

**Files:**
- Modify: `core/crypto_exchange_import.py` (add near top, after `CryptoExchangeEvent` dataclass ~line 53)
- Test: `tests/unit/imports/test_crypto_exchange_import.py`

**Interfaces:**
- Consumes: iterables yielding `CryptoExchangeEvent` (has `.timestamp_ms: int`).
- Produces: `_merge_sorted_events(*iterables) -> Iterable[CryptoExchangeEvent]` — yields events in non-decreasing `timestamp_ms` order, stable (ties broken by source-stream order, earlier positional arg first).

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/imports/test_crypto_exchange_import.py`:

```python
from core.crypto_exchange_import import _merge_sorted_events


def _event(ts, eid):
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=eid,
        group_id=eid,
        timestamp_ms=ts,
        category="trade",
        raw_type="x",
        legs=[],
    )


def test_merge_sorted_events_interleaves_by_timestamp():
    a = [_event(100, "a1"), _event(300, "a3")]
    b = [_event(200, "b2"), _event(400, "b4")]

    result = [e.provider_event_id for e in _merge_sorted_events(iter(a), iter(b))]

    assert result == ["a1", "b2", "a3", "b4"]


def test_merge_sorted_events_preserves_stable_order_on_ties():
    a = [_event(100, "a1")]
    b = [_event(100, "b1")]

    result = [e.provider_event_id for e in _merge_sorted_events(iter(a), iter(b))]

    assert result == ["a1", "b1"]


def test_merge_sorted_events_handles_empty_streams():
    result = list(_merge_sorted_events(iter([]), iter([]), iter([_event(100, "x")])))

    assert [e.provider_event_id for e in result] == ["x"]


def test_merge_sorted_events_handles_all_empty():
    assert list(_merge_sorted_events(iter([]), iter([]))) == []


def test_merge_sorted_events_single_stream():
    a = [_event(100, "a1"), _event(200, "a2")]

    result = [e.provider_event_id for e in _merge_sorted_events(iter(a))]

    assert result == ["a1", "a2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k merge_sorted -v`
Expected: FAIL with `ImportError: cannot import name '_merge_sorted_events'`

- [ ] **Step 3: Implement `_merge_sorted_events`**

Add to `core/crypto_exchange_import.py` after the `CryptoExchangeEvent` dataclass (line ~54):

```python
import heapq


def _merge_sorted_events(*iterables):
    """K-way merge of CryptoExchangeEvent streams by timestamp_ms (stable).

    Ties are broken by source-stream order (earlier positional arg first),
    then by original position within that stream.
    """
    counters = [0] * len(iterables)
    heap = []
    for stream_idx, it in enumerate(iterables):
        try:
            event = next(it)
            heapq.heappush(heap, (event.timestamp_ms, stream_idx, counters[stream_idx], event))
            counters[stream_idx] += 1
        except StopIteration:
            pass

    while heap:
        _, stream_idx, _, event = heapq.heappop(heap)
        yield event
        try:
            nxt = next(iterables[stream_idx])
            heapq.heappush(heap, (nxt.timestamp_ms, stream_idx, counters[stream_idx], nxt))
            counters[stream_idx] += 1
        except StopIteration:
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k merge_sorted -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run full test file**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add core/crypto_exchange_import.py tests/unit/imports/test_crypto_exchange_import.py
git commit -m "feat: add _merge_sorted_events k-way merge utility"
```

---

## Task 3: Rewrite `parse_option_symbol` to support both exchanges

**Files:**
- Modify: `core/crypto_exchange_import.py:450-496` (`parse_option_symbol`)
- Test: `tests/unit/imports/test_crypto_exchange_import.py`

**Interfaces:**
- Produces: `parse_option_symbol(symbol: str) -> Dict[str, Any]` returning `{underlying, expiration_date, strike_price, option_type, settlement_asset?}`. Auto-detects ByBit (`DDMMMYY`, e.g. `BTC-27JUN26-100000-C`) vs OKX (`YYMMDD` + settlement-coin segment 2, e.g. `BTC-USD-240315-50000-C`).
- **Backward compat:** existing tests at `test_crypto_exchange_import.py:252-295` (ByBit format) MUST keep passing.

**Detection logic:** ByBit symbols have segment 2 = 7-char date ending in 2-digit year (`27JUN26`); OKX symbols have segment 2 = a known settlement coin (`USD`, `USDC`, `USDT`). Detect by checking whether segment 2 uppercased is in `{"USD","USDT","USDC"}`.

- [ ] **Step 1: Write failing tests for OKX format**

Append to `tests/unit/imports/test_crypto_exchange_import.py`:

```python
def test_parse_okx_option_symbol_call():
    parsed = parse_option_symbol("BTC-USD-240315-50000-C")

    assert parsed["underlying"] == "BTC"
    assert parsed["expiration_date"].isoformat() == "2024-03-15"
    assert parsed["strike_price"] == Decimal("50000")
    assert parsed["option_type"] == "CALL"
    assert parsed["settlement_asset"] == "USD"


def test_parse_okx_option_symbol_put_usdt_settlement():
    parsed = parse_option_symbol("BTC-USDT-240315-50000-P")

    assert parsed["expiration_date"].isoformat() == "2024-03-15"
    assert parsed["option_type"] == "PUT"
    assert parsed["settlement_asset"] == "USDT"


@pytest.mark.parametrize(
    "symbol",
    [
        "BTC-USD-2413-50000-C",      # too-short date
        "BTC-USD-240315-50000",      # missing side
        "BTC-USD-240315-notnum-C",   # bad strike
        "BTC-ETH-240315-50000-C",    # segment 2 not a date or known coin
    ],
)
def test_parse_okx_option_symbol_rejects_malformed(symbol):
    with pytest.raises(ValueError):
        parse_option_symbol(symbol)
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k "okx_option or parse_okx" -v`
Expected: FAIL (current parser treats segment 2 as `DDMMMYY` date → `KeyError` on month for `USD`).

- [ ] **Step 3: Rewrite `parse_option_symbol`**

Replace the body of `parse_option_symbol` at `core/crypto_exchange_import.py:450-496` with:

```python
OPTION_SETTLEMENT_COINS = {"USD", "USDT", "USDC"}


def parse_option_symbol(symbol: str) -> Dict[str, Any]:
    parts = symbol.split("-")
    if len(parts) not in (4, 5):
        raise ValueError(f"Malformed option symbol: {symbol}")

    segment_two = parts[1].upper()
    if segment_two in OPTION_SETTLEMENT_COINS:
        return _parse_okx_option_symbol(parts, symbol)
    return _parse_bybit_option_symbol(parts, symbol)


def _parse_bybit_option_symbol(parts, symbol):
    underlying, expiry_token, strike, option_side = parts[:4]
    settlement_asset = parts[4] if len(parts) == 5 else None
    if not underlying:
        raise ValueError(f"Malformed option symbol: {symbol}")
    if settlement_asset == "":
        raise ValueError(f"Malformed option settlement asset: {symbol}")
    if len(expiry_token) != 7:
        raise ValueError(f"Malformed option expiration: {expiry_token}")

    try:
        day = int(expiry_token[:2])
        month = MONTH_NUMBERS[expiry_token[2:5].upper()]
        year = 2000 + int(expiry_token[5:])
        expiration_date = date(year, month, day)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Malformed option expiration: {expiry_token}") from exc

    option_type_by_side = {"C": "CALL", "P": "PUT"}
    try:
        option_type = option_type_by_side[option_side.upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown option side: {option_side}") from exc

    try:
        strike_price = Decimal(strike)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Malformed option strike: {strike}") from exc
    if not strike_price.is_finite():
        raise ValueError(f"Malformed option strike: {strike}")

    parsed = {
        "underlying": underlying,
        "expiration_date": expiration_date,
        "strike_price": strike_price,
        "option_type": option_type,
    }
    if settlement_asset:
        parsed["settlement_asset"] = settlement_asset
    return parsed


def _parse_okx_option_symbol(parts, symbol):
    underlying, settlement_asset, expiry_token, strike, option_side = parts[:5]
    if len(parts) != 5:
        raise ValueError(f"OKX option symbol requires settlement segment: {symbol}")
    if not underlying or not settlement_asset:
        raise ValueError(f"Malformed option symbol: {symbol}")
    if len(expiry_token) != 6:
        raise ValueError(f"Malformed OKX option expiration: {expiry_token}")

    try:
        year = 2000 + int(expiry_token[:2])
        month = int(expiry_token[2:4])
        day = int(expiry_token[4:6])
        expiration_date = date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"Malformed OKX option expiration: {expiry_token}") from exc

    option_type_by_side = {"C": "CALL", "P": "PUT"}
    try:
        option_type = option_type_by_side[option_side.upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown option side: {option_side}") from exc

    try:
        strike_price = Decimal(strike)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Malformed option strike: {strike}") from exc
    if not strike_price.is_finite():
        raise ValueError(f"Malformed option strike: {strike}")

    return {
        "underlying": underlying,
        "expiration_date": expiration_date,
        "strike_price": strike_price,
        "option_type": option_type,
        "settlement_asset": settlement_asset.upper(),
    }
```

- [ ] **Step 4: Run new OKX tests**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k "okx_option or parse_okx" -v`
Expected: PASS (new tests)

- [ ] **Step 5: Run the EXISTING ByBit parser tests to confirm backward compat**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k "parse_btc_call or parse_btc_put or settlement_suffixed or parse_option_symbol_rejects" -v`
Expected: PASS — all pre-existing tests still green.

- [ ] **Step 6: Run full test file**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add core/crypto_exchange_import.py tests/unit/imports/test_crypto_exchange_import.py
git commit -m "feat: parse_option_symbol supports OKX YYMMDD format alongside ByBit"
```

---

## Task 4: Deposit & withdrawal normalizers (ByBit + OKX)

**Files:**
- Modify: `core/crypto_exchange_import.py` (add normalizers near `normalize_bybit_spot_execution` ~line 400)
- Test: `tests/unit/imports/test_crypto_exchange_import.py`

**Interfaces:**
- Produces:
  - `normalize_bybit_deposit(payload: Dict) -> CryptoExchangeEvent` (`category="deposit"`)
  - `normalize_bybit_withdrawal(payload: Dict) -> CryptoExchangeEvent` (`category="withdrawal"`)
  - `normalize_okx_deposit_withdrawal(payload: Dict) -> CryptoExchangeEvent` (direction from `payload["type"]` ∈ `{"deposit","withdrawal"}`)

**ByBit deposit payload fields** (per `/v5/asset/deposit/query-record`): `coin`, `amount`, `txID`, `successAt` (ms string), `status`. Withdrawal payload (`/v5/asset/withdraw/query-record`): `coin`, `amount`, `id`, `createdAt` (ms string), `status`.

**OKX payload fields** (per `/api/v5/asset/deposit-withdraw`): `ccy`, `amt`, `billId`, `ts` (ms), `type` (`"deposit"` or `"withdraw"`).

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/imports/test_crypto_exchange_import.py`:

```python
from core.crypto_exchange_import import (
    normalize_bybit_deposit,
    normalize_bybit_withdrawal,
    normalize_okx_deposit_withdrawal,
)


def test_normalize_bybit_deposit_stablecoin():
    event = normalize_bybit_deposit(
        {
            "coin": "USDT",
            "amount": "500",
            "txID": "dep-tx-1",
            "successAt": "1700000000000",
            "status": "SUCCESS",
        }
    )

    assert event.provider == "bybit"
    assert event.provider_event_id == "dep-tx-1"
    assert event.category == "deposit"
    assert event.raw_type == "deposit"
    assert event.timestamp_ms == 1700000000000
    assert event.fee is None
    assert len(event.legs) == 1
    assert event.legs[0]["asset"] == "USDT"
    assert event.legs[0]["quantity"] == Decimal("500")
    assert event.legs[0]["instrument"] == "coin"


def test_normalize_bybit_withdrawal_btc():
    event = normalize_bybit_withdrawal(
        {
            "coin": "BTC",
            "amount": "0.05",
            "id": "wd-1",
            "createdAt": "1700000001000",
            "status": "success",
        }
    )

    assert event.category == "withdrawal"
    assert event.provider_event_id == "wd-1"
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("-0.05")
    assert event.legs[0]["instrument"] == "coin"


def test_normalize_okx_deposit():
    event = normalize_okx_deposit_withdrawal(
        {
            "ccy": "USDT",
            "amt": "200",
            "billId": "okx-dep-1",
            "ts": "1700000002000",
            "type": "deposit",
        }
    )

    assert event.provider == "okx"
    assert event.category == "deposit"
    assert event.provider_event_id == "deposit:okx-dep-1"
    assert event.legs[0]["quantity"] == Decimal("200")


def test_normalize_okx_withdrawal_direction_prefixed_id():
    event = normalize_okx_deposit_withdrawal(
        {
            "ccy": "BTC",
            "amt": "0.1",
            "billId": "okx-wd-1",
            "ts": "1700000003000",
            "type": "withdrawal",
        }
    )

    assert event.category == "withdrawal"
    assert event.provider_event_id == "withdrawal:okx-wd-1"
    assert event.legs[0]["quantity"] == Decimal("-0.1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k "bybit_deposit or bybit_withdrawal or okx_deposit or okx_withdrawal" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the three normalizers**

Add to `core/crypto_exchange_import.py` after `normalize_bybit_spot_execution` (~line 420):

```python
def normalize_bybit_deposit(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    coin = payload["coin"].upper()
    amount = Decimal(payload["amount"])
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["txID"],
        group_id=payload["txID"],
        timestamp_ms=int(payload["successAt"]),
        category="deposit",
        raw_type="deposit",
        legs=_single_leg(coin, amount, coin),
    )


def normalize_bybit_withdrawal(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    coin = payload["coin"].upper()
    amount = -abs(Decimal(payload["amount"]))
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["id"],
        group_id=payload["id"],
        timestamp_ms=int(payload["createdAt"]),
        category="withdrawal",
        raw_type="withdrawal",
        legs=_single_leg(coin, amount, coin),
    )


def normalize_okx_deposit_withdrawal(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    ccy = payload["ccy"].upper()
    amount = Decimal(payload["amt"])
    direction = payload["type"].lower()
    if direction not in {"deposit", "withdrawal"}:
        raise ValueError(f"Unknown OKX asset movement type: {payload['type']}")
    signed_amount = amount if direction == "deposit" else -abs(amount)
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=f"{direction}:{payload['billId']}",
        group_id=payload["billId"],
        timestamp_ms=int(payload["ts"]),
        category=direction,
        raw_type=direction,
        legs=_single_leg(ccy, signed_amount, ccy),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k "bybit_deposit or bybit_withdrawal or okx_deposit or okx_withdrawal" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run full test file**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add core/crypto_exchange_import.py tests/unit/imports/test_crypto_exchange_import.py
git commit -m "feat: add ByBit/OKX deposit & withdrawal normalizers"
```

---

## Task 5: Reward normalizers + internal-transfer filtering

**Files:**
- Modify: `core/crypto_exchange_import.py` (add normalizers + skip constants)
- Test: `tests/unit/imports/test_crypto_exchange_import.py`

**Interfaces:**
- Produces:
  - `normalize_bybit_reward(payload: Dict) -> Optional[CryptoExchangeEvent]` — returns `None` for internal-transfer rows.
  - `normalize_okx_reward(payload: Dict) -> Optional[CryptoExchangeEvent]`
  - Constants `SKIPPED_BYBIT_INTERNAL_TRANSFER_TYPES`, `SKIPPED_OKX_INTERNAL_TRANSFER_TYPES`.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/imports/test_crypto_exchange_import.py`:

```python
from core.crypto_exchange_import import (
    normalize_bybit_reward,
    normalize_okx_reward,
)


def test_normalize_bybit_reward_btc():
    event = normalize_bybit_reward(
        {
            "symbol": "BTC",
            "change": "0.001",
            "transactionTime": "1700000004000",
            "type": "Earn",
            "id": "earn-1",
        }
    )

    assert event.category == "reward"
    assert event.raw_type == "earn"
    assert event.provider_event_id == "earn-1"
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("0.001")
    assert event.legs[0]["instrument"] == "coin"


def test_normalize_bybit_reward_skips_internal_transfer():
    event = normalize_bybit_reward(
        {
            "symbol": "USDT",
            "change": "100",
            "transactionTime": "1700000005000",
            "type": "InternalTransfer",
            "id": "tr-1",
        }
    )

    assert event is None


def test_normalize_okx_reward_stablecoin():
    event = normalize_okx_reward(
        {
            "ccy": "USDT",
            "amt": "5.5",
            "billId": "okx-earn-1",
            "ts": "1700000006000",
            "subType": "24",
        }
    )

    assert event.category == "reward"
    assert event.provider_event_id == "okx-earn-1"
    assert event.legs[0]["quantity"] == Decimal("5.5")


def test_normalize_okx_reward_skips_internal_transfer():
    event = normalize_okx_reward(
        {
            "ccy": "USDT",
            "amt": "100",
            "billId": "okx-tr-1",
            "ts": "1700000007000",
            "subType": "1",
        }
    )

    assert event is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k "bybit_reward or okx_reward" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement reward normalizers + skip constants**

Add near the top of `core/crypto_exchange_import.py` after `STABLECOINS` (line ~24):

```python
SKIPPED_BYBIT_INTERNAL_TRANSFER_TYPES = {"InternalTransfer", "Transfer"}
SKIPPED_OKX_INTERNAL_TRANSFER_SUBTYPES = {"1", "128", "129"}
```

Add after `normalize_okx_deposit_withdrawal`:

```python
def normalize_bybit_reward(payload: Dict[str, Any]) -> Optional[CryptoExchangeEvent]:
    tx_type = payload.get("type", "")
    if tx_type in SKIPPED_BYBIT_INTERNAL_TRANSFER_TYPES:
        return None
    symbol = payload["symbol"].upper()
    amount = Decimal(payload["change"])
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["id"],
        group_id=payload["id"],
        timestamp_ms=int(payload["transactionTime"]),
        category="reward",
        raw_type="earn",
        legs=_single_leg(symbol, amount, symbol),
    )


def normalize_okx_reward(payload: Dict[str, Any]) -> Optional[CryptoExchangeEvent]:
    if payload.get("subType") in SKIPPED_OKX_INTERNAL_TRANSFER_SUBTYPES:
        return None
    ccy = payload["ccy"].upper()
    amount = Decimal(payload["amt"])
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=payload["billId"],
        group_id=payload["billId"],
        timestamp_ms=int(payload["ts"]),
        category="reward",
        raw_type="earn",
        legs=_single_leg(ccy, amount, ccy),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k "bybit_reward or okx_reward" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run full test file**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add core/crypto_exchange_import.py tests/unit/imports/test_crypto_exchange_import.py
git commit -m "feat: add ByBit/OKX reward normalizers with internal-transfer filtering"
```

---

## Task 6: Option normalizers (premium + settlement, both exchanges)

**Files:**
- Modify: `core/crypto_exchange_import.py` (add normalizers)
- Test: `tests/unit/imports/test_crypto_exchange_import.py`

**Interfaces:**
- Produces:
  - `normalize_bybit_option_execution(payload: Dict) -> CryptoExchangeEvent` (`category="trade"`, `raw_type="option_execution"`, `instrument="option"`)
  - `normalize_okx_option_fill(payload: Dict) -> CryptoExchangeEvent` (`category="trade"`, `raw_type="option_fill"`)
  - `normalize_bybit_option_settlement(payload: Dict) -> CryptoExchangeEvent` (`category="settlement"`)
  - `normalize_okx_option_settlement(payload: Dict) -> CryptoExchangeEvent` (`category="settlement"`)

**ByBit option execution payload** (`/v5/execution/list`, `category=option`): `symbol` (e.g. `BTC-27JUN26-100000-C`), `execId`, `orderId`, `side`, `execQty`, `execPrice`, `execFee`, `feeCurrency`, `execTime`.

**OKX option fill payload** (`/api/v5/trade/fills-history`, `instType=OPTION`): `instId` (e.g. `BTC-USD-240315-50000-C`), `tradeId`, `ordId`, `side`, `fillSz`, `fillPx`, `fee`, `feeCcy`, `fillTime`.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/imports/test_crypto_exchange_import.py`:

```python
from core.crypto_exchange_import import (
    normalize_bybit_option_execution,
    normalize_bybit_option_settlement,
    normalize_okx_option_fill,
    normalize_okx_option_settlement,
)


def test_normalize_bybit_option_execution_buy_call():
    event = normalize_bybit_option_execution(
        {
            "symbol": "BTC-27JUN26-100000-C",
            "execId": "opt-ex-1",
            "orderId": "opt-order-1",
            "side": "Buy",
            "execQty": "2",
            "execPrice": "500",
            "execFee": "1",
            "feeCurrency": "USDT",
            "execTime": "1700000008000",
        }
    )

    assert event.category == "trade"
    assert event.raw_type == "option_execution"
    assert event.provider_event_id == "opt-ex-1"
    assert event.group_id == "opt-order-1"
    assert len(event.legs) == 1
    assert event.legs[0]["instrument"] == "option"
    assert event.legs[0]["asset"] == "BTC-27JUN26-100000-C"
    assert event.legs[0]["quantity"] == Decimal("2")
    assert event.legs[0]["price"] == Decimal("500")
    assert event.legs[0]["price_asset"] == "USDT"


def test_normalize_okx_option_fill_sell_put():
    event = normalize_okx_option_fill(
        {
            "instId": "BTC-USD-240315-50000-P",
            "tradeId": "okx-opt-1",
            "ordId": "okx-opt-order-1",
            "side": "sell",
            "fillSz": "1.5",
            "fillPx": "1200",
            "fee": "-1.8",
            "feeCcy": "USDT",
            "fillTime": "1700000009000",
        }
    )

    assert event.category == "trade"
    assert event.raw_type == "option_fill"
    assert event.legs[0]["instrument"] == "option"
    assert event.legs[0]["asset"] == "BTC-USD-240315-50000-P"
    assert event.legs[0]["quantity"] == Decimal("-1.5")
    assert event.legs[0]["price"] == Decimal("1200")


def test_normalize_bybit_option_settlement_exercised():
    event = normalize_bybit_option_settlement(
        {
            "symbol": "BTC",
            "change": "0.5",
            "transactionTime": "1700000010000",
            "type": "Settlement",
            "id": "settle-1",
            "orderLinkId": "opt-order-1",
            "newWalletBalance": "65000",
        }
    )

    assert event.category == "settlement"
    assert event.raw_type == "option_delivery"
    assert event.group_id == "opt-order-1"
    assert event.provider_event_id == "settle-1"
    assert event.legs[0]["instrument"] == "coin"
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("0.5")
    assert event.legs[0]["price"] == Decimal("65000")


def test_normalize_okx_option_settlement():
    event = normalize_okx_option_settlement(
        {
            "instId": "BTC-USD-240315-50000-C",
            "settlCcy": "BTC",
            "settlAmt": "0.3",
            "settlPx": "65000",
            "ts": "1700000011000",
            "billId": "okx-settle-1",
            "ordId": "okx-opt-order-1",
        }
    )

    assert event.category == "settlement"
    assert event.provider_event_id == "okx-settle-1"
    assert event.group_id == "okx-opt-order-1"
    assert event.legs[0]["asset"] == "BTC"
    assert event.legs[0]["quantity"] == Decimal("0.3")
    assert event.legs[0]["price"] == Decimal("65000")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k "option_execution or option_fill or option_settlement" -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement the four option normalizers**

Add to `core/crypto_exchange_import.py` after `normalize_okx_deposit_withdrawal` / `normalize_okx_reward`:

```python
def normalize_bybit_option_execution(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    symbol = payload["symbol"]
    qty = Decimal(payload["execQty"])
    price = Decimal(payload["execPrice"])
    fee_currency = payload.get("feeCurrency") or "USD"
    signed_qty = qty if payload["side"].lower() == "buy" else -qty
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["execId"],
        group_id=payload.get("orderId") or payload["execId"],
        timestamp_ms=int(payload["execTime"]),
        category="trade",
        raw_type="option_execution",
        legs=[
            {
                "asset": symbol,
                "quantity": signed_qty,
                "price": price,
                "price_asset": fee_currency,
                "role": "base",
                "instrument": "option",
            }
        ],
        fee={
            "asset": fee_currency,
            "quantity": -abs(Decimal(payload.get("execFee") or "0")),
            "is_rebate": False,
        },
    )


def normalize_okx_option_fill(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    symbol = payload["instId"]
    qty = Decimal(payload["fillSz"])
    price = Decimal(payload["fillPx"])
    fee_ccy = payload.get("feeCcy") or "USD"
    signed_qty = qty if payload["side"].lower() == "buy" else -qty
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=payload["tradeId"],
        group_id=payload.get("ordId") or payload["tradeId"],
        timestamp_ms=int(payload["fillTime"]),
        category="trade",
        raw_type="option_fill",
        legs=[
            {
                "asset": symbol,
                "quantity": signed_qty,
                "price": price,
                "price_asset": fee_ccy,
                "role": "base",
                "instrument": "option",
            }
        ],
        fee={
            "asset": fee_ccy,
            "quantity": Decimal(payload.get("fee") or "0"),
            "is_rebate": False,
        },
    )


def normalize_bybit_option_settlement(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    symbol = payload["symbol"].upper()
    amount = Decimal(payload["change"])
    settlement_price = Decimal(payload["newWalletBalance"])
    return CryptoExchangeEvent(
        provider="bybit",
        provider_event_id=payload["id"],
        group_id=payload.get("orderLinkId") or payload["id"],
        timestamp_ms=int(payload["transactionTime"]),
        category="settlement",
        raw_type="option_delivery",
        legs=_single_leg(symbol, amount, symbol),
    )


def normalize_okx_option_settlement(payload: Dict[str, Any]) -> CryptoExchangeEvent:
    ccy = payload["settlCcy"].upper()
    amount = Decimal(payload["settlAmt"])
    settlement_price = Decimal(payload["settlPx"])
    legs = _single_leg(ccy, amount, ccy)
    legs[0]["price"] = settlement_price
    return CryptoExchangeEvent(
        provider="okx",
        provider_event_id=payload["billId"],
        group_id=payload.get("ordId") or payload["billId"],
        timestamp_ms=int(payload["ts"]),
        category="settlement",
        raw_type="option_delivery",
        legs=legs,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -k "option_execution or option_fill or option_settlement" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run full test file**

Run: `pytest tests/unit/imports/test_crypto_exchange_import.py -q --no-cov`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add core/crypto_exchange_import.py tests/unit/imports/test_crypto_exchange_import.py
git commit -m "feat: add option premium + settlement normalizers for ByBit and OKX"
```

---

## Task 7: Persistence dispatch — settlement type + option resolver

**Files:**
- Modify: `core/crypto_exchange_import.py:255-270` (`_transaction_type_for_event`) and `:307` (`persist_crypto_exchange_event` asset resolution)
- Test: `tests/integration/workflows/test_crypto_exchange_persistence.py`

**Interfaces:**
- Consumes: `resolve_crypto_option_asset` (already exists at line 72), `TRANSACTION_TYPE_OPTION_SETTLEMENT` (already in `constants.py:67`).
- Produces: `_transaction_type_for_event` now returns `Option settlement` for `category=="settlement"`; `persist_crypto_exchange_event` dispatches on `leg.get("instrument")`.

**This is the only task near protected persistence code.** The numeric/idempotency logic is untouched.

- [ ] **Step 1: Write failing integration tests**

Append to `tests/integration/workflows/test_crypto_exchange_persistence.py`. Add `OptionMetadata` and `TRANSACTION_TYPE_OPTION_SETTLEMENT` to the imports at the top of the file:

```python
from common.models import Accounts, Assets, Brokers, OptionMetadata, Prices, Transactions
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
)
```

Then append these tests:

```python
def _deposit_event(**overrides):
    data = {
        "provider": "bybit",
        "provider_event_id": "dep-1",
        "group_id": "dep-1",
        "timestamp_ms": 1700000000000,
        "category": "deposit",
        "raw_type": "deposit",
        "legs": [
            {
                "asset": "USDT",
                "quantity": Decimal("500"),
                "price": Decimal("1"),
                "price_asset": "USDT",
                "role": "base",
                "instrument": "coin",
            }
        ],
        "fee": None,
    }
    data.update(overrides)
    return CryptoExchangeEvent(**data)


@pytest.mark.django_db
def test_persist_deposit_creates_transfer_in_row(user, crypto_account):
    created = persist_crypto_exchange_event(_deposit_event(), user, crypto_account)

    assert len(created) == 1
    tx = created[0]
    assert tx.type == TRANSACTION_TYPE_CRYPTO_TRANSFER_IN
    assert tx.quantity == Decimal("500")
    assert persist_crypto_exchange_event(_deposit_event(), user, crypto_account) == []


def _option_premium_event(**overrides):
    data = {
        "provider": "bybit",
        "provider_event_id": "opt-ex-1",
        "group_id": "opt-order-1",
        "timestamp_ms": 1700000008000,
        "category": "trade",
        "raw_type": "option_execution",
        "legs": [
            {
                "asset": "BTC-27JUN26-100000-C",
                "quantity": Decimal("2"),
                "price": Decimal("500"),
                "price_asset": "USDT",
                "role": "base",
                "instrument": "option",
            }
        ],
        "fee": {"asset": "USDT", "quantity": Decimal("-1"), "is_rebate": False},
    }
    data.update(overrides)
    return CryptoExchangeEvent(**data)


@pytest.mark.django_db
def test_persist_option_premium_creates_option_asset_with_metadata(user, crypto_account):
    created = persist_crypto_exchange_event(_option_premium_event(), user, crypto_account)

    assert len(created) == 1
    tx = created[0]
    assert tx.type == TRANSACTION_TYPE_CRYPTO_TRADE_IN
    assert tx.security.type == "Option"
    meta = OptionMetadata.objects.get(asset=tx.security)
    assert meta.strike_price == Decimal("100000")
    assert meta.option_type == "CALL"
    assert meta.expiration_date.isoformat() == "2026-06-27"


def _option_settlement_event(**overrides):
    data = {
        "provider": "bybit",
        "provider_event_id": "settle-1",
        "group_id": "opt-order-1",
        "timestamp_ms": 1700000010000,
        "category": "settlement",
        "raw_type": "option_delivery",
        "legs": [
            {
                "asset": "BTC",
                "quantity": Decimal("0.5"),
                "price": Decimal("65000"),
                "price_asset": "BTC",
                "role": "base",
                "instrument": "coin",
            }
        ],
        "fee": None,
    }
    data.update(overrides)
    return CryptoExchangeEvent(**data)


@pytest.mark.django_db
def test_persist_option_settlement_uses_option_settlement_type(user, crypto_account):
    created = persist_crypto_exchange_event(_option_settlement_event(), user, crypto_account)

    assert len(created) == 1
    assert created[0].type == TRANSACTION_TYPE_OPTION_SETTLEMENT


@pytest.mark.django_db
def test_persist_coin_leg_still_uses_crypto_resolver(user, crypto_account):
    # Regression: existing spot-trade path must still resolve as Crypto asset.
    created = persist_crypto_exchange_event(_crypto_event(), user, crypto_account)

    assert all(c.security.type == ASSET_TYPE_CRYPTO for c in created)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/workflows/test_crypto_exchange_persistence.py -k "deposit or option_premium or option_settlement or coin_leg_still" -v`
Expected: FAIL — `_transaction_type_for_event` falls through to `Crypto trade in` for settlement; option premium legs resolve via `resolve_crypto_asset` (creating a `Crypto` asset, not `Option`).

- [ ] **Step 3: Add settlement branch to `_transaction_type_for_event`**

At `core/crypto_exchange_import.py`, add `TRANSACTION_TYPE_OPTION_SETTLEMENT` to the import from `constants` (line ~14):

```python
from constants import (
    ASSET_TYPE_CRYPTO,
    TRANSACTION_TYPE_CRYPTO_REWARD,
    TRANSACTION_TYPE_CRYPTO_TRADE_IN,
    TRANSACTION_TYPE_CRYPTO_TRADE_OUT,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_IN,
    TRANSACTION_TYPE_CRYPTO_TRANSFER_OUT,
    TRANSACTION_TYPE_OPTION_SETTLEMENT,
)
```

Then modify `_transaction_type_for_event` (line 255) to add the settlement branch BEFORE the transfer check:

```python
def _transaction_type_for_event(event, quantity):
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
    return TRANSACTION_TYPE_CRYPTO_TRADE_IN if quantity > 0 else TRANSACTION_TYPE_CRYPTO_TRADE_OUT
```

- [ ] **Step 4: Add instrument dispatch to `persist_crypto_exchange_event`**

At `core/crypto_exchange_import.py:307`, replace:

```python
            asset = resolve_crypto_asset(leg["asset"], user)
```

with:

```python
            if leg.get("instrument") == "option":
                asset = resolve_crypto_option_asset(parse_option_symbol(leg["asset"]), user)
            else:
                asset = resolve_crypto_asset(leg["asset"], user)
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `pytest tests/integration/workflows/test_crypto_exchange_persistence.py -k "deposit or option_premium or option_settlement or coin_leg_still" -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the FULL integration test file to confirm no regressions**

Run: `pytest tests/integration/workflows/test_crypto_exchange_persistence.py -q --no-cov`
Expected: all pass — the existing spot-trade tests must still resolve as `Crypto` assets.

- [ ] **Step 7: Commit**

```bash
git add core/crypto_exchange_import.py tests/integration/workflows/test_crypto_exchange_persistence.py
git commit -m "feat: option-aware persistence dispatch + Option settlement tx type"
```

---

## Task 8: New client iterators

**Files:**
- Modify: `core/crypto_exchange_clients.py` (add iterator methods to `BybitClient` ~line 135 and `OKXClient` ~line 233)
- Test: `tests/unit/api/test_crypto_exchange_clients.py`

**Interfaces:**
- Produces (all yield raw payload dicts, paginated, same shape as existing `iter_executions`/`iter_fills_history`):
  - `BybitClient.iter_deposits(params)`, `iter_withdrawals(params)` — `/v5/asset/deposit/query-record`, `/v5/asset/withdraw/query-record`. Rows in `result.rows` (`nextPageCursor` not used; these endpoints paginate via `limit`/`cursor` if present).
  - `BybitClient.iter_option_executions(params)` — `/v5/execution/list` with `category=option` merged into params.
  - `BybitClient.iter_option_settlements(params)` — `/v5/account/transaction-log` filtered to settlement `type`.
  - `OKXClient.iter_asset_deposits_withdrawals(params)` — `/api/v5/asset/deposit-withdraw`.
  - `OKXClient.iter_earn_lending_history(params)` — `/api/v5/finance/savings/lending-history`.
  - `OKXClient.iter_option_fills(params)` — `/api/v5/trade/fills-history` with `instType=OPTION`.
  - `OKXClient.iter_option_settlements(params)` — `/api/v5/account/options-settlement-history` (or the documented settlement endpoint).

**Pattern to follow:** Mirror the existing `iter_executions` (ByBit, lines 116-134) and `iter_fills_history` (OKX, lines 211-232) exactly: same `get_private` call, same `result.list`/`data` extraction, same cursor handling, same `CryptoExchangeAPIError` on malformed payload.

- [ ] **Step 1: Write failing tests for one ByBit and one OKX iterator (the rest follow the identical pattern)**

Read the existing test style at `tests/unit/api/test_crypto_exchange_clients.py` first (the `monkeypatch` + `FakeResponse` pattern). Then append:

```python
def test_bybit_iter_deposits_paginates_and_yields_rows(monkeypatch):
    client = BybitClient(api_key="k", api_secret="s")
    pages = [
        {"retCode": 0, "retMsg": "OK", "result": {"rows": [{"coin": "USDT", "txID": "d1"}], "nextPageCursor": ""}},
    ]
    calls = {"n": 0}

    def fake_get(path, params=None):
        idx = calls["n"]
        calls["n"] += 1
        return pages[idx]

    monkeypatch.setattr(client, "get_private", fake_get)
    rows = list(client.iter_deposits({"limit": 50}))

    assert [r["txID"] for r in rows] == ["d1"]


def test_bybit_iter_option_executions_passes_option_category(monkeypatch):
    client = BybitClient(api_key="k", api_secret="s")
    captured = {}

    def fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return {"retCode": 0, "retMsg": "OK", "result": {"list": [], "nextPageCursor": ""}}

    monkeypatch.setattr(client, "get_private", fake_get)
    list(client.iter_option_executions({"limit": 5}))

    assert captured["path"] == "/v5/execution/list"
    assert captured["params"]["category"] == "option"


def test_okx_iter_asset_deposits_withdrawals_yields_data(monkeypatch):
    client = OKXClient(api_key="k", api_secret="s", passphrase="p")
    page = {"code": "0", "msg": "", "data": [{"ccy": "BTC", "billId": "b1", "type": "deposit"}]}

    def fake_get(path, params=None):
        return page

    monkeypatch.setattr(client, "get_private", fake_get)
    rows = list(client.iter_asset_deposits_withdrawals({}))

    assert rows[0]["billId"] == "b1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/api/test_crypto_exchange_clients.py -k "iter_deposits or iter_option_executions or iter_asset_deposits" -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement all eight iterators**

Add to `BybitClient` in `core/crypto_exchange_clients.py` (after `iter_executions`, ~line 134):

```python
    def iter_deposits(self, params=None):
        params = params or {}
        data = self.get_private("/v5/asset/deposit/query-record", params)
        rows = data.get("result", {}).get("rows")
        if rows is None:
            raise CryptoExchangeAPIError(f"Malformed Bybit deposit response: {data}")
        for row in rows:
            yield row

    def iter_withdrawals(self, params=None):
        params = params or {}
        data = self.get_private("/v5/asset/withdraw/query-record", params)
        rows = data.get("result", {}).get("rows")
        if rows is None:
            raise CryptoExchangeAPIError(f"Malformed Bybit withdrawal response: {data}")
        for row in rows:
            yield row

    def iter_option_executions(self, params=None):
        params = {**(params or {}), "category": "option"}
        yield from self.iter_executions(params)

    def iter_option_settlements(self, params=None):
        params = {**(params or {}), "type": "Settlement"}
        yield from self.iter_transaction_log(params)
```

Add to `OKXClient` (after `iter_fills_history`, ~line 232):

```python
    def iter_asset_deposits_withdrawals(self, params=None):
        params = params or {}
        data = self.get_private("/api/v5/asset/deposit-withdraw", params)
        rows = data.get("data")
        if rows is None:
            raise CryptoExchangeAPIError(f"Malformed OKX deposit-withdraw response: {data}")
        for row in rows:
            yield row

    def iter_earn_lending_history(self, params=None):
        params = params or {}
        data = self.get_private("/api/v5/finance/savings/lending-history", params)
        rows = data.get("data")
        if rows is None:
            raise CryptoExchangeAPIError(f"Malformed OKX lending response: {data}")
        for row in rows:
            yield row

    def iter_option_fills(self, params=None):
        params = {**(params or {}), "instType": "OPTION"}
        yield from self.iter_fills_history(params)

    def iter_option_settlements(self, params=None):
        params = params or {}
        data = self.get_private("/api/v5/account/options-settlement-history", params)
        rows = data.get("data")
        if rows is None:
            raise CryptoExchangeAPIError(f"Malformed OKX options-settlement response: {data}")
        for row in rows:
            yield row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/api/test_crypto_exchange_clients.py -k "iter_deposits or iter_option_executions or iter_asset_deposits" -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run full client test file**

Run: `pytest tests/unit/api/test_crypto_exchange_clients.py -q --no-cov`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add core/crypto_exchange_clients.py tests/unit/api/test_crypto_exchange_clients.py
git commit -m "feat: add deposit/withdrawal/option iterators to BybitClient and OKXClient"
```

---

## Task 9: Wire adapters to the unified stream + partial-failure tracking

**Files:**
- Modify: `core/broker_api_utils.py:481-595` (`BybitAPI`, `OKXAPI`)
- Test: `tests/unit/api/test_crypto_exchange_clients.py`

**Interfaces:**
- Consumes: all normalizers from Tasks 4-6, `_merge_sorted_events` (Task 2), the new iterators (Task 8).
- Produces: `BybitAPI.get_transactions` / `OKXAPI.get_transactions` now yield a merged stream across all endpoint types; `self.partial_failures: List[Tuple[str, str]]` populated on per-endpoint errors.

- [ ] **Step 1: Write failing test for the unified stream**

Append to `tests/unit/api/test_crypto_exchange_clients.py`. This test monkeypatches the `BybitClient` class methods (since `get_transactions` constructs the client internally) and asserts merged-stream order plus partial-failure tracking. Read the existing `BybitAPI` full-flow test in this file first to mirror its `database_sync_to_async` + `monkeypatch` conventions exactly.

```python
@pytest.mark.django_db
async def test_bybit_api_get_transactions_merges_streams_and_tracks_failures(
    user, monkeypatch
):
    from common.models import Accounts, Brokers
    from users.models import BybitApiToken

    broker = Brokers.objects.create(investor=user, name="Bybit", country="Crypto")
    account = Accounts.objects.create(broker=broker, name="Unified", native_id="bybit-main")
    token = BybitApiToken.objects.create(
        user=user, broker=broker, api_key="k", is_active=True, testnet=False
    )
    token.set_api_secret("s", user)
    token.save()

    # Monkeypatch BybitClient iterators at the class level.
    from core.crypto_exchange_clients import BybitClient

    def fake_iter_executions(self, params):
        return iter([{
            "execId": "e1", "symbol": "BTCUSDT", "side": "Buy",
            "execQty": "0.1", "execPrice": "60000", "execTime": "300",
        }])

    def fake_iter_deposits(self, params):
        raise CryptoExchangeAPIError("Bybit HTTP 403: forbidden")

    def fake_iter_empty(self, params):
        return iter([])

    monkeypatch.setattr(BybitClient, "iter_executions", fake_iter_executions)
    monkeypatch.setattr(BybitClient, "iter_deposits", fake_iter_deposits)
    monkeypatch.setattr(BybitClient, "iter_withdrawals", fake_iter_empty)
    monkeypatch.setattr(BybitClient, "iter_option_executions", fake_iter_empty)
    monkeypatch.setattr(BybitClient, "iter_transaction_log", fake_iter_empty)
    monkeypatch.setattr(BybitClient, "iter_option_settlements", fake_iter_empty)

    api = BybitAPI()
    await api.connect(user)
    events = []
    async for event in api.get_transactions(account):
        events.append(event)

    # The trade event from iter_executions still yielded despite deposit failure.
    assert len(events) == 1
    assert events[0].provider_event_id == "e1"
    # The deposit endpoint failure was recorded, not raised.
    assert any("403" in msg for _, msg in api.partial_failures)
```

**Note:** `_safe`'s endpoint-name argument is a literal string (not `iterator.__name__`, since generators have no `__name__`). See the implementation in Step 3.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/api/test_crypto_exchange_clients.py -k "merges_streams" -v`
Expected: FAIL (`partial_failures` attribute does not exist yet).

- [ ] **Step 3: Refactor `BybitAPI.get_transactions`**

First, update the import at `core/broker_api_utils.py:26-29` to include the new normalizers and the merge utility:

```python
from .crypto_exchange_import import (
    _merge_sorted_events,
    normalize_bybit_deposit,
    normalize_bybit_reward,
    normalize_bybit_option_execution,
    normalize_bybit_option_settlement,
    normalize_bybit_spot_execution,
    normalize_bybit_withdrawal,
    normalize_okx_deposit_withdrawal,
    normalize_okx_option_fill,
    normalize_okx_option_settlement,
    normalize_okx_reward,
    normalize_okx_spot_fill,
)
```

Then replace `BybitAPI.get_transactions` (lines 500-536) with:

```python
class BybitAPI(BrokerAPI):
    """Bybit BrokerAPI adapter returning normalized crypto exchange events."""

    def __init__(self):
        super().__init__()
        self.user = None
        self.partial_failures = []

    async def connect(self, user) -> bool:
        self.user = user
        has_token = await database_sync_to_async(
            lambda: BybitApiToken.objects.filter(user=user, is_active=True).exists()
        )()
        if not has_token:
            raise BrokerAPIException("No active Bybit token configured")
        return True

    async def disconnect(self) -> None:
        self.user = None

    async def get_transactions(self, account, date_from=None, date_to=None):
        if not self.user:
            raise BrokerAPIException("Not connected to Bybit API")

        token = await database_sync_to_async(
            lambda: account.broker.bybit_tokens.filter(user=self.user, is_active=True).first()
        )()
        if not token:
            raise BrokerAPIException("No active Bybit token for selected broker")

        client = BybitClient(
            api_key=token.api_key,
            api_secret=token.get_api_secret(self.user),
            testnet=token.testnet,
        )
        date_params = _crypto_exchange_date_params(
            date_from, date_to, start_key="startTime", end_key="endTime"
        )

        def _safe(endpoint_name, normalizer, iterator):
            def _gen():
                try:
                    for payload in iterator:
                        event = normalizer(payload)
                        if event is not None:
                            yield event
                except CryptoExchangeAPIError as exc:
                    self.partial_failures.append((endpoint_name, str(exc)))
            return _gen()

        streams = [
            _safe("executions", normalize_bybit_spot_execution, client.iter_executions({"category": "spot", **date_params})),
            _safe("option_executions", normalize_bybit_option_execution, client.iter_option_executions(date_params)),
            _safe("deposits", normalize_bybit_deposit, client.iter_deposits(date_params)),
            _safe("withdrawals", normalize_bybit_withdrawal, client.iter_withdrawals(date_params)),
            _safe("earn", normalize_bybit_reward, client.iter_transaction_log({"type": "Earn", **date_params})),
            _safe("option_settlements", normalize_bybit_option_settlement, client.iter_option_settlements(date_params)),
        ]
        for event in _merge_sorted_events(*[s() for s in streams]):
            yield event
```

Apply the analogous refactor to `OKXAPI.get_transactions` (lines 558-595) using its five streams (spot fills, option fills, deposit-withdraw, earn-lending, option settlements) and `normalize_okx_*` functions.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/unit/api/test_crypto_exchange_clients.py -k "merges_streams" -v`
Expected: PASS

- [ ] **Step 5: Run full client test file**

Run: `pytest tests/unit/api/test_crypto_exchange_clients.py -q --no-cov`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add core/broker_api_utils.py tests/unit/api/test_crypto_exchange_clients.py
git commit -m "feat: unify ByBit/OKX import streams with k-way merge and partial-failure tracking"
```

---

## Task 10: Extend `verify_crypto_import.py` + live-marker test scaffolding

**Files:**
- Modify: `backend/scratch/verify_crypto_import.py` (add option/deposit/withdrawal/reward validation)
- Create: `tests/integration/api/test_crypto_live_import.py` (gated behind `RUN_LIVE_CRYPTO_TESTS=1`)

**Interfaces:**
- Produces: a `live`-marked test module that fetches real data and asserts schema alignment, skipped by default.

- [ ] **Step 1: Add `live` marker to the test module**

Create `tests/integration/api/test_crypto_live_import.py`:

```python
"""Live crypto import verification — only runs when RUN_LIVE_CRYPTO_TESTS=1.

Confirms real exchange payload shapes match the documented fixtures used in
unit tests. Skipped by default.
"""
import os

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_CRYPTO_TESTS") != "1",
        reason="set RUN_LIVE_CRYPTO_TESTS=1 to run live crypto verification",
    ),
]


@pytest.mark.django_db
def test_live_bybit_option_symbols_parse():
    # Placeholder: replaced with a real fetch once venv + keys are available.
    # Asserts that every option symbol returned by ByBit's option-execution
    # endpoint parses without ValueError.
    pytest.skip("live discovery pending restored venv")
```

- [ ] **Step 2: Run to confirm it skips cleanly**

Run: `pytest tests/integration/api/test_crypto_live_import.py -v`
Expected: 1 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/api/test_crypto_live_import.py scratch/verify_crypto_import.py
git commit -m "test: scaffold live crypto import verification (skipped by default)"
```

---

## Task 11: Full regression run + finalize

**Files:** none (verification only)

- [ ] **Step 1: Run the focused crypto test suite (CI subset)**

Run: `pytest tests/integration/workflows/test_crypto_exchange_persistence.py tests/unit/imports/test_crypto_exchange_import.py tests/unit/api/test_crypto_exchange_clients.py tests/integration/api/test_crypto_token_api.py -q --no-cov`
Expected: all pass.

- [ ] **Step 2: Run the full backend suite to confirm no collateral damage**

Run: `pytest -q --no-cov`
Expected: all pass (no new failures vs. baseline).

- [ ] **Step 3: Verify protected-code invariant**

Run: `git diff --name-only main...HEAD -- 'common/models.py' '**/migrations/**' 'core/portfolio_utils.py'`
Expected: empty — no protected files changed.

- [ ] **Step 4: Commit any final scratch updates**

```bash
git add -A
git commit -m "test: crypto non-trade import full regression green" --allow-empty
```
