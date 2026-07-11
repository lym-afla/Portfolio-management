# Crypto Non-Trade Transaction Import — Design

**Date:** 2026-07-10
**Status:** Approved (brainstorming complete), pending implementation plan
**Scope owner:** backend crypto import layer
**Predecessor:** `2026-06-07-crypto-exchange-brokers-design.md`

## 1. Problem

The crypto exchange import (`core/crypto_exchange_import.py`,
`core/broker_api_utils.py`) currently imports **spot trades only**:

- ByBit: `BybitAPI.get_transactions()` calls `BybitClient.iter_executions()`
  (`/v5/execution/list`, `category=spot`) and nothing else.
  `BybitClient.iter_transaction_log()` (`/v5/account/transaction-log`) exists
  but is **never called** by the adapter.
- OKX: `OKXAPI.get_transactions()` calls `OKXClient.iter_fills_history()`
  (`/api/v5/trade/fills-history`, `instType=SPOT`) and nothing else.

Consequence: deposits, withdrawals, and earn/staking rewards are silently
absent from the portfolio. This distorts cost basis (deposits set the
economic basis of a position), understates position growth (rewards), and
leaves on/off-ramp money movement entirely unmodeled.

The DB schema and calc layer are **already built for this**: the five crypto
`Transactions` types (`Crypto reward`, `Crypto transfer in/out`, `Crypto trade
in/out`) exist, the `import_*` idempotency fields work for any provider, and
`_transaction_type_for_event` already routes `reward` / `deposit` / `withdrawal`
/ `transfer` categories to the correct type. No schema or calc change is
required. The work is entirely in the **fetch + normalize** layer.

## 2. Scope

**In scope:**
- External deposits and withdrawals (Group A) — both exchanges.
- Earn / staking / savings rewards (Group C) — both exchanges.

**Explicitly out of scope (decided in brainstorming):**
- Internal transfers (Group B): funding↔trading↔sub-account moves within one
  exchange are **skipped at normalization**. They are net-zero by nature and
  would distort invested capital / IRR. Internal-transfer rows returned by the
  asset/transaction-log endpoints are filtered out (see §5.3).
- Derivatives / futures / options funding fees, PnL, and settlements (Group D).

**Unchanged (protected / high-risk):**
- `common/models.py` — no schema change.
- `persist_crypto_exchange_event`, `_transaction_type_for_event`,
  `_normalize_model_decimal`, the calc layer (`core/portfolio_utils.py`), the
  `Transactions` constraints, migrations, and the frontend.

## 3. Approach

**Chosen: explicit `legs[]` events + shared k-way merge.**

`CryptoExchangeEvent` is generalized as: any event is `category` + `legs[]`,
where each leg is `{asset, quantity, price, price_asset, role}`. Spot trades
remain two legs (base + quote); deposits, withdrawals, and rewards are
**single-leg** events. A shared `_merge_sorted_events(*iterables)` utility
merges multiple per-endpoint event generators by `timestamp_ms` into one
time-sorted stream that the unchanged `persist_crypto_exchange_event` consumes.

Rejected alternatives:
- *Per-adapter ad-hoc merge (Approach 1)* — duplicates merge logic across
  ByBit and OKX and leans on the convention that "a one-element legs list
  means a transfer" rather than making it explicit.
- *New `CryptoLedgerEntry` abstraction (Approach 3)* — rewrites the financial
  persistence path, violates the project's protected-code rules, and gains
  nothing over explicit legs.

## 4. Components & boundaries

All new units live in the fetch + normalize layer. Each does one thing,
communicates through the `CryptoExchangeEvent` interface, and is testable
independently.

### 4.1 New / changed units

| Unit | Location | Responsibility |
|---|---|---|
| `_single_leg(asset, quantity, price_asset, role)` | `core/crypto_exchange_import.py` | Build a one-element `legs` list for deposits / withdrawals / rewards. Mirrors the existing `_spot_legs()`. |
| `normalize_bybit_deposit(payload)` | `core/crypto_exchange_import.py` | ByBit deposit payload → single-leg `CryptoExchangeEvent` (`category="deposit"`). |
| `normalize_bybit_withdrawal(payload)` | `core/crypto_exchange_import.py` | ByBit withdrawal payload → single-leg event (`category="withdrawal"`). |
| `normalize_bybit_reward(payload)` | `core/crypto_exchange_import.py` | ByBit earn row → single-leg event (`category="reward"`). Filters out internal-transfer rows (see §5.3). |
| `normalize_okx_deposit_withdrawal(payload)` | `core/crypto_exchange_import.py` | OKX `/asset/deposit-withdraw` row → single-leg event; direction (`deposit` vs `withdrawal`) read from the payload `type` field. |
| `normalize_okx_reward(payload)` | `core/crypto_exchange_import.py` | OKX earn-lending row → single-leg event (`category="reward"`). |
| `_merge_sorted_events(*iterables)` | `core/crypto_exchange_import.py` | K-way merge of event generators by `timestamp_ms`. Pure, no DB, no I/O. |
| `BybitClient.iter_deposits(params)`, `iter_withdrawals(params)` | `core/crypto_exchange_clients.py` | Thin pagination wrappers over `/v5/asset/deposit/query-record` and `/v5/asset/withdraw/query-record`, same shape as `iter_executions`. |
| `OKXClient.iter_asset_deposits_withdrawals(params)`, `iter_earn_lending_history(params)` | `core/crypto_exchange_clients.py` | Pagination wrappers over `/api/v5/asset/deposit-withdraw` and `/api/v5/finance/savings/lending-history`. |
| `BybitAPI.get_transactions` / `OKXAPI.get_transactions` | `core/broker_api_utils.py` | Each now calls N endpoints, feeds all into `_merge_sorted_events`, yields the unified stream. Accumulates per-endpoint failures in `self.partial_failures`. |

### 4.2 Deliberately untouched

- `common/models.py` — schema unchanged.
- `persist_crypto_exchange_event` — works unchanged because it iterates
  `event.legs` generically and routes via the unchanged
  `_transaction_type_for_event`.
- `core/portfolio_utils.py`, all calc code, `Transactions` constraints,
  migrations, frontend.

## 5. Data flow & mapping

### 5.1 Unified flow

```
BybitAPI.get_transactions(account, from, to)
    ├─ BybitClient.iter_executions({category:spot, from, to})   → normalize_bybit_spot_execution   → [trade]
    ├─ BybitClient.iter_deposits({from, to})                    → normalize_bybit_deposit          → [deposit]
    ├─ BybitClient.iter_withdrawals({from, to})                 → normalize_bybit_withdrawal       → [withdrawal]
    └─ BybitClient.iter_transaction_log({type: earn filter})    → normalize_bybit_reward           → [reward]
                              │
                              ▼  _merge_sorted_events(*four streams, key=timestamp_ms)
                    unified, time-sorted CryptoExchangeEvent stream
                              │
                              ▼  (unchanged)
                 persist_crypto_exchange_event  →  Transactions rows
```

OKX has three sources (no separate reward endpoint beyond earn-lending):
trade fills, asset deposit-withdraw, and earn-lending history, merged the same
way.

### 5.2 Endpoint → category → TX type

| Exchange | Endpoint | Normalizer | `category` | `raw_type` | → TX type | Legs |
|---|---|---|---|---|---|---|
| ByBit | `/v5/execution/list` (spot) | `normalize_bybit_spot_execution` | `trade` | `spot_execution` | trade in/out | 2 |
| ByBit | `/v5/asset/deposit/query-record` | `normalize_bybit_deposit` | `deposit` | `deposit` | transfer in | 1 |
| ByBit | `/v5/asset/withdraw/query-record` | `normalize_bybit_withdrawal` | `withdrawal` | `withdrawal` | transfer out | 1 |
| ByBit | `/v5/account/transaction-log` (earn filter) | `normalize_bybit_reward` | `reward` | `earn` | Crypto reward | 1 |
| OKX | `/api/v5/trade/fills-history` (SPOT) | `normalize_okx_spot_fill` | `trade` | `spot_fill` | trade in/out | 2 |
| OKX | `/api/v5/asset/deposit-withdraw` | `normalize_okx_deposit_withdrawal` | `deposit`/`withdrawal` | `deposit`/`withdrawal` | transfer in/out | 1 |
| OKX | `/api/v5/finance/savings/lending-history` | `normalize_okx_reward` | `reward` | `earn` | Crypto reward | 1 |

### 5.3 Internal-transfer filtering

Internal transfers (funding↔trading within one exchange) are **not emitted**.
Mechanism: the reward / asset-history normalizers filter out rows whose `type` /
`subType` matches an internal-transfer classification. Filter membership is
declared in named constants
(`SKIPPED_BYBIT_INTERNAL_TRANSFER_TYPES`,
`SKIPPED_OKX_INTERNAL_TRANSFER_TYPES`) so the filter is documented and
testable. A debug-level count of skipped rows is logged. No event emitted
implies no row written.

### 5.4 Single-leg price handling

Deposits and rewards have no counterparty quote asset, but
`persist_crypto_exchange_event` requires a fiat `price` on every leg. The
existing `_leg_fiat_price` already covers both cases:

- **Stablecoin deposits/rewards** (USDT/USDC/USD): `price = Decimal("1")`,
  `price_asset = <the stablecoin>`. `_leg_fiat_price`'s stablecoin
  short-circuit returns 1 unchanged.
- **Non-stablecoin deposits/rewards** (BTC, ETH, …): the leg's `price_asset`
  is set to the asset itself; `_leg_fiat_price` delegates to the existing
  `_quote_asset_fiat_price` (local `Prices` lookup → Yahoo auto-import
  fallback). Identical to how crypto-crypto trades already value their quote
  leg.

`_single_leg` sets `price_asset` to the asset symbol; no new price logic.

## 6. Error handling & idempotency

### 6.1 Per-endpoint isolation

With multiple endpoints per import, a failure on one must not abort the rest:

1. Each endpoint call is wrapped in its own `try/except CryptoExchangeAPIError`.
   A failed endpoint yields nothing; the adapter appends `(endpoint, error)`
   to `self.partial_failures`.
2. `_merge_sorted_events` runs over the surviving streams; the import completes
   for available data.
3. The WebSocket consumer (`transactions/views.py`) checks
   `adapter.partial_failures` after the generator exhausts and, if non-empty,
   sends a warning listing which endpoints failed. Already-persisted rows are
   not rolled back (each has its own idempotency key).
4. `connect()` failures (no token, bad auth on the primary trade endpoint)
   still raise `BrokerAPIException` immediately.

Rationale: an API key scoped to trades-only (a common safety pattern) will
403 on asset-history endpoints; with this design trades still import and the
user gets a visible warning rather than a silent full failure.

### 6.2 Idempotency

- Each new normalizer sets `provider_event_id` to the exchange's own unique id
  (ByBit deposit `txId`, withdrawal `withdrawId`; OKX `billId`; reward bill id).
  The dedup key `(investor, account, provider, import_account_id,
  import_event_id)` is unchanged.
- A single-leg event produces `…:0` as its only leg key.
- Re-import re-queries all endpoints; already-persisted rows are skipped by the
  existing pre-check + `IntegrityError` catch. No change needed.
- OKX direction-prefixed ids: the normalizer sets
  `provider_event_id = f"{direction}:{billId}"` so a deposit and withdrawal
  can never collide on the dedup key.

### 6.3 Decimal & precision

Single-leg quantities quantize to 9 dp via the unchanged
`_normalize_model_decimal`. Sub-1e-9 dust raises `ValueError`, is surfaced in
the partial-failure list, and produces no row — identical to today's behavior
for oversized trades.

## 7. Testing strategy

Per `AGENTS.md`: `Decimal` everywhere, edge cases (zero quantity, missing
price). The normalize layer is not protected-calc, so unit tests cover the
mapping; the unchanged persistence path is re-asserted with single-leg
integration tests.

### 7.1 Test files

| File | Type | Coverage |
|---|---|---|
| `tests/unit/imports/test_crypto_exchange_import.py` *(extend)* | unit | New normalizers: deposit/withdrawal/reward payload → event (category, single-leg shape, sign, `fee=None`). Internal-transfer filtering (payload → no event). `_single_leg`. `_merge_sorted_events` (already-sorted, interleaved, empty streams, single-stream, stable order for equal timestamps). |
| `tests/unit/api/test_crypto_exchange_clients.py` *(extend)* | unit + `django_db` | New iterators: pagination, malformed-payload rejection, `get_private` error handling — same style as existing iterator tests. |
| `tests/integration/workflows/test_crypto_exchange_persistence.py` *(extend)* | `django_db` | Single-leg deposit → one row, type `Crypto transfer in`; reward → `Crypto reward`; non-stablecoin reward with missing local price → Yahoo auto-import + rollback on failure; idempotency on re-import; internal-transfer payload → zero rows. |
| `tests/integration/api/test_crypto_token_api.py` | — | No change (credential flow unchanged). |

### 7.2 Closing the discovery gap

Normalizer tests are written against **documented** payload shapes, not the
account's live data (ByBit account has no history; OKX live discovery was
paused). Mitigation: a `live` pytest marker (already defined in
`pyproject.toml`) gates tests that hit real endpoints behind
`RUN_LIVE_CRYPTO_TESTS=1`, skipped by default. These formalize the
`verify_crypto_import.py` checks as assertions over real payloads and run
only with a working venv + keys.

### 7.3 Edge cases

- Zero-quantity deposit (dust) → skipped by `quantity == 0` guard, no row.
- Non-stablecoin reward, no local `Prices`, Yahoo failure → event raises,
  partial-failure recorded, no row.
- Stablecoin deposit → price resolves to 1, one row, `Crypto transfer in`.
- Re-import same deposit → zero rows (idempotency).
- Merge with identical timestamps across streams → deterministic stable order.
- Sub-1e-9 reward quantity → `ValueError` on quantization, surfaced, no row.

## 8. Sequencing recommendation

Implementation order, smallest-confidence-risk first:

1. `_merge_sorted_events` + `_single_leg` (pure, fully testable, no I/O).
2. New client iterators (`iter_deposits`, `iter_withdrawals`, OKX equivalents)
   with malformed-payload tests.
3. New normalizers + internal-transfer filtering (unit tests on documented
   payloads).
4. Wire `get_transactions` to the unified stream + partial-failure tracking.
5. Integration tests (single-leg persistence, idempotency, rollback).
6. `live`-marker tests; run `verify_crypto_import.py` (extended) against live
   creds once the venv is restored, to confirm real payload shapes match the
   documented fixtures.

## 9. Open items to confirm during implementation (not blocking design)

- Exact OKX `/asset/deposit-withdraw` response shape (combined stream vs
  per-direction) — confirmed via the `live` test or a single curl.
- ByBit earn `type` codes for the `transaction-log` filter and the
  internal-transfer classification codes — confirmed from a live query.
- API-key read scopes required for each new endpoint (asset-history read
  permissions on both exchanges).
