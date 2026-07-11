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

The DB schema is **already built for this**: the crypto `Transactions` types
(`Crypto reward`, `Crypto transfer in/out`, `Crypto trade in/out`) and
`Option settlement` exist, the `import_*` idempotency fields work for any
provider, and `OptionMetadata` (strike, expiry, type, underlying, contract
size) already models option contracts. No schema or calc change is required.

The work is in the **fetch + normalize** layer, with one targeted fix to the
persistence dispatcher. Two existing functions are currently **dead code**:
`parse_option_symbol` and `resolve_crypto_option_asset` are never called by
anything. Worse, `persist_crypto_exchange_event` *always* calls
`resolve_crypto_asset` (the crypto-coin resolver) regardless of instrument
type, and `_transaction_type_for_event` has no settlement branch — so options
and expiry settlements cannot be imported correctly today. This design wires
the existing option code in and closes both gaps (see §3 and §4.3).

## 2. Scope

**In scope:**
- External deposits and withdrawals (Group A) — both exchanges.
- Earn / staking / savings rewards (Group C) — both exchanges.
- Options (Group D) — both exchanges. Covers the two option lifecycle events
  the user actually trades: **premium** (buying/selling a contract) and
  **delivery/settlement** (the payoff at expiry). Exchanges: OKX (instId
  `BTC-USD-240315-50000-C`, settlement coin + `YYMMDD` expiry) and ByBit
  (`BTC-27DEC24-75000-C`, `DDMMMYY` expiry).

**Explicitly out of scope (decided in brainstorming):**
- Internal transfers (Group B): funding↔trading↔sub-account moves within one
  exchange are **skipped at normalization**. They are net-zero by nature and
  would distort invested capital / IRR. Internal-transfer rows returned by the
  asset/transaction-log endpoints are filtered out (see §5.3).
- Futures / perpetuals funding fees, PnL, and liquidations (the rest of the
  old Group D). Only spot options are in scope; futures contracts are not.

**Unchanged (protected / high-risk):**
- `common/models.py` — no schema change.
- `_normalize_model_decimal`, the calc layer (`core/portfolio_utils.py`), the
  `Transactions` constraints, migrations, and the frontend.

**Targeted changes to persistence dispatch (not the financial math):**
- `_transaction_type_for_event` gains a `settlement` branch → emits
  `Option settlement`. All other branches unchanged.
- `persist_crypto_exchange_event` resolves the asset via the right resolver
  depending on the leg's instrument kind (crypto coin vs. option contract).
  This is a dispatch fix, not a formula change; all numeric/idempotency
  behavior is preserved.

**Known v1 constraint — option mark-to-market:**
No price feed exists for individual option contracts (no Yahoo ticker), so
open option positions cannot be marked to market. They will show at cost
basis until settled, after which the settlement row realizes the P&L. This
matches the existing app behavior for instruments without a price feed and
is documented, not solved, in this design.

## 3. Approach

**Chosen: explicit `legs[]` events + shared k-way merge.**

`CryptoExchangeEvent` is generalized as: any event is `category` + `legs[]`,
where each leg is `{asset, quantity, price, price_asset, role, instrument}`.
Spot trades remain two legs (base + quote); deposits, withdrawals, rewards,
option premiums, and option settlements are **single-leg** events. A shared
`_merge_sorted_events(*iterables)` utility merges multiple per-endpoint event
generators by `timestamp_ms` into one time-sorted stream that
`persist_crypto_exchange_event` consumes. The only change to persistence is a
dispatch on `instrument` to pick the right asset resolver (see §4.3) and a
new `settlement` category branch in `_transaction_type_for_event`; all
numeric and idempotency behavior is preserved.

Rejected alternatives:
- *Per-adapter ad-hoc merge (Approach 1)* — duplicates merge logic across
  ByBit and OKX and leans on the convention that "a one-element legs list
  means a transfer" rather than making it explicit.
- *New `CryptoLedgerEntry` abstraction (Approach 3)* — rewrites the financial
  persistence path, violates the project's protected-code rules, and gains
  nothing over explicit legs.

**Option instrument parsing.** The existing `parse_option_symbol` handles
ByBit's `DDMMMYY`-expiry format only and crashes on OKX's `YYMMDD` format
(month-lookup `KeyError`). This design replaces it with a single
`parse_option_symbol(symbol)` that detects the format by structure (OKX's
segment 2 is a 3-letter coin; ByBit's segment 2 is a 7-char date) and parses
both, returning the same `{underlying, expiration_date, strike_price,
option_type, settlement_asset?}` shape that the existing (currently dead)
`resolve_crypto_option_asset` already consumes.

**Persistence dispatch.** A leg carries its instrument kind. For crypto-coin
legs, `persist_crypto_exchange_event` calls `resolve_crypto_asset` (as today);
for option legs it calls `resolve_crypto_option_asset` (which creates the
`Assets` row of `type="Option"` plus `OptionMetadata`). This is a dispatch
addition — the row's numeric fields, idempotency keys, and `transaction.atomic`
wrapping are unchanged.

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
| `BybitClient.iter_option_executions(params)`, `iter_option_settlements(params)` | `core/crypto_exchange_clients.py` | Wrappers over `/v5/execution/list` (`category=option`) and `/v5/account/transaction-log` filtered to option-delivery types. |
| `OKXClient.iter_asset_deposits_withdrawals(params)`, `iter_earn_lending_history(params)` | `core/crypto_exchange_clients.py` | Pagination wrappers over `/api/v5/asset/deposit-withdraw` and `/api/v5/finance/savings/lending-history`. |
| `OKXClient.iter_option_fills(params)`, `iter_option_settlements(params)` | `core/crypto_exchange_clients.py` | Wrappers over `/api/v5/trade/fills-history` (`instType=OPTION`) and `/api/v5/public/options-settlements` (or the account settlement-history endpoint). |
| `parse_option_symbol(symbol)` *(rewrite)* | `core/crypto_exchange_import.py` | Parse both ByBit (`DDMMMYY` expiry) and OKX (`YYMMDD` expiry, settlement-coin segment) option symbols into the canonical `{underlying, expiration_date, strike_price, option_type, settlement_asset?}` dict. Format detected by structure. |
| `normalize_bybit_option_execution(payload)` | `core/crypto_exchange_import.py` | ByBit option premium fill → `CryptoExchangeEvent` (`category="trade"`, option leg). |
| `normalize_bybit_option_settlement(payload)` | `core/crypto_exchange_import.py` | ByBit option delivery row → single-leg event (`category="settlement"`). |
| `normalize_okx_option_fill(payload)` | `core/crypto_exchange_import.py` | OKX option premium fill → event (`category="trade"`, option leg). |
| `normalize_okx_option_settlement(payload)` | `core/crypto_exchange_import.py` | OKX option settlement row → single-leg event (`category="settlement"`). |
| `_transaction_type_for_event` *(extend)* | `core/crypto_exchange_import.py` | Add a `settlement` category branch → `Option settlement`. All existing branches (reward/transfer/trade) unchanged. |
| `persist_crypto_exchange_event` *(extend dispatch)* | `core/crypto_exchange_import.py` | Resolve the asset by instrument kind: `resolve_crypto_asset` for coin legs, `resolve_crypto_option_asset` for option legs. Numeric/idempotency behavior unchanged. |
| `BybitAPI.get_transactions` / `OKXAPI.get_transactions` | `core/broker_api_utils.py` | Each now calls N endpoints, feeds all into `_merge_sorted_events`, yields the unified stream. Accumulates per-endpoint failures in `self.partial_failures`. |

### 4.2 Deliberately untouched

- `common/models.py` — schema unchanged (`OptionMetadata` already exists).
- `_normalize_model_decimal` — unchanged.
- The numeric/idempotency behavior inside `persist_crypto_exchange_event`
  (quantization, dedup-key composition, `IntegrityError` catch) — unchanged.
- `core/portfolio_utils.py`, all calc code, `Transactions` constraints,
  migrations, frontend.

### 4.3 Leg instrument kind

Each leg gains an `instrument` key: `"coin"` (default) or `"option"`. Existing
spot/deposit/withdrawal/reward legs carry `"coin"` implicitly (the key defaults
to `"coin"` when absent, so existing normalizers need not change). Option
normalizers set `instrument="option"` plus the parsed symbol so the
persistence dispatcher can pick the right resolver. This keeps the
`CryptoExchangeEvent` shape backward-compatible while making the
instrument-type fact explicit and testable.

## 5. Data flow & mapping

### 5.1 Unified flow

```
BybitAPI.get_transactions(account, from, to)
    ├─ BybitClient.iter_executions({category:spot, from, to})    → normalize_bybit_spot_execution    → [trade]
    ├─ BybitClient.iter_executions({category:option, from, to}) → normalize_bybit_option_execution  → [option trade]
    ├─ BybitClient.iter_deposits({from, to})                     → normalize_bybit_deposit           → [deposit]
    ├─ BybitClient.iter_withdrawals({from, to})                  → normalize_bybit_withdrawal        → [withdrawal]
    ├─ BybitClient.iter_transaction_log({type: earn filter})     → normalize_bybit_reward            → [reward]
    └─ BybitClient.iter_option_settlements({from, to})           → normalize_bybit_option_settlement → [option settlement]
                              │
                              ▼  _merge_sorted_events(*six streams, key=timestamp_ms)
                    unified, time-sorted CryptoExchangeEvent stream
                              │
                              ▼  persist_crypto_exchange_event (with option dispatch)
                 Transactions rows + OptionMetadata
```

OKX has five sources: spot fills, option fills, asset deposit-withdraw,
earn-lending history, and option settlements — merged the same way.

### 5.2 Endpoint → category → TX type

| Exchange | Endpoint | Normalizer | `category` | `raw_type` | → TX type | Legs | Instrument |
|---|---|---|---|---|---|---|---|
| ByBit | `/v5/execution/list` (spot) | `normalize_bybit_spot_execution` | `trade` | `spot_execution` | trade in/out | 2 | coin |
| ByBit | `/v5/execution/list` (option) | `normalize_bybit_option_execution` | `trade` | `option_execution` | trade in/out | 1 | option |
| ByBit | `/v5/asset/deposit/query-record` | `normalize_bybit_deposit` | `deposit` | `deposit` | transfer in | 1 | coin |
| ByBit | `/v5/asset/withdraw/query-record` | `normalize_bybit_withdrawal` | `withdrawal` | `withdrawal` | transfer out | 1 | coin |
| ByBit | `/v5/account/transaction-log` (earn filter) | `normalize_bybit_reward` | `reward` | `earn` | Crypto reward | 1 | coin |
| ByBit | option delivery (transaction-log / settlement) | `normalize_bybit_option_settlement` | `settlement` | `option_delivery` | Option settlement | 1 | option |
| OKX | `/api/v5/trade/fills-history` (SPOT) | `normalize_okx_spot_fill` | `trade` | `spot_fill` | trade in/out | 2 | coin |
| OKX | `/api/v5/trade/fills-history` (OPTION) | `normalize_okx_option_fill` | `trade` | `option_fill` | trade in/out | 1 | option |
| OKX | `/api/v5/asset/deposit-withdraw` | `normalize_okx_deposit_withdrawal` | `deposit`/`withdrawal` | `deposit`/`withdrawal` | transfer in/out | 1 | coin |
| OKX | `/api/v5/finance/savings/lending-history` | `normalize_okx_reward` | `reward` | `earn` | Crypto reward | 1 | coin |
| OKX | options settlement-history | `normalize_okx_option_settlement` | `settlement` | `option_delivery` | Option settlement | 1 | option |

**Option premium leg shape.** An option premium trade is a single leg: the
contract itself (resolved via `resolve_crypto_option_asset` → an `Option`
asset with `OptionMetadata`). The `quantity` is the number of contracts
(positive when buying, negative when selling); `price` is the premium per
contract in the settlement currency, converted to USD via the existing
`_leg_fiat_price` path. Unlike spot, there is no second "quote leg" — the
premium is a cash flow derived at the leg level, mirroring how a stock
purchase is a single security leg in the rest of the app.

**Option settlement leg shape.** At expiry the delivery is a single leg on
the settlement coin (e.g. BTC for a BTC-USD option), `category="settlement"`,
routed by the new `_transaction_type_for_event` branch to
`Option settlement`. The `quantity` is the delivered coin amount (signed by
direction); `price` is the settlement (mark) price of the underlying at
expiry, available in the exchange's settlement payload. The linked option
contract's `provider_event_id` is referenced in `import_group_id` so premium
and settlement are auditable together without colliding on the dedup key.

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

Deposits, rewards, option premiums, and option settlements are all single-leg
events with no counterparty quote asset, yet `persist_crypto_exchange_event`
requires a fiat `price` on every leg. The existing `_leg_fiat_price` already
covers every case:

- **Stablecoin-denominated legs** (USDT/USDC/USD premium or deposit):
  `price = Decimal("1")`, `price_asset = <the stablecoin>`.
  `_leg_fiat_price`'s stablecoin short-circuit returns 1 unchanged.
- **Crypto-denominated legs** (BTC/ETH deposit, BTC-premium option, BTC
  settlement): the leg's `price_asset` is set to the asset itself;
  `_leg_fiat_price` delegates to the existing `_quote_asset_fiat_price`
  (local `Prices` lookup → Yahoo auto-import fallback). Identical to how
  crypto-crypto trades already value their quote leg.
- **Option settlement legs**: the settlement price of the underlying at expiry
  is taken directly from the exchange's settlement payload (already fiat) and
  set as the leg `price`; no lookup needed.

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
| `tests/unit/imports/test_crypto_exchange_import.py` *(extend)* | unit | New coin normalizers: deposit/withdrawal/reward payload → event (category, single-leg shape, sign, `fee=None`). Internal-transfer filtering (payload → no event). `_single_leg`. `_merge_sorted_events` (already-sorted, interleaved, empty streams, single-stream, stable order for equal timestamps). Rewritten `parse_option_symbol`: ByBit (`DDMMMYY`) and OKX (`YYMMDD` + settlement-coin segment) formats, malformed-symbol rejection, call/put/settlement-asset parsing. Option normalizers: premium fill (buy/sell, sign, contract quantity) and settlement (delivery coin, settlement price, `category="settlement"`). |
| `tests/unit/api/test_crypto_exchange_clients.py` *(extend)* | unit + `django_db` | New iterators: pagination, malformed-payload rejection, `get_private` error handling — same style as existing iterator tests. Includes option-specific iterators (`iter_option_executions` / `iter_option_fills`, `iter_option_settlements`). |
| `tests/integration/workflows/test_crypto_exchange_persistence.py` *(extend)* | `django_db` | Single-leg deposit → one row, type `Crypto transfer in`; reward → `Crypto reward`; non-stablecoin reward with missing local price → Yahoo auto-import + rollback on failure; idempotency on re-import; internal-transfer payload → zero rows. **Option regression:** premium trade → one `Transactions` row on an `Option` asset with linked `OptionMetadata` (strike/expiry/type/underlying); settlement → `Option settlement` row, delivery coin quantity, settlement price from payload; premium + settlement linked via `import_group_id`; re-import idempotency for both; persistence-dispatch picks `resolve_crypto_option_asset` for `instrument="option"` legs and `resolve_crypto_asset` for `"coin"` legs. |
| `tests/integration/api/test_crypto_token_api.py` | — | No change (credential flow unchanged). |

### 7.2 Closing the discovery gap

Normalizer tests are written against **documented** payload shapes, not the
account's live data (ByBit account has no history; OKX live discovery was
paused). Mitigation: a `live` pytest marker (already defined in
`pyproject.toml`) gates tests that hit real endpoints behind
`RUN_LIVE_CRYPTO_TESTS=1`, skipped by default. These formalize the
`verify_crypto_import.py` checks as assertions over real payloads and run
only with a working venv + keys. Option-symbol parsing in particular must be
validated against a real OKX option instId and a real ByBit option symbol,
since the formats differ structurally.

### 7.3 Edge cases

- Zero-quantity deposit (dust) → skipped by `quantity == 0` guard, no row.
- Non-stablecoin reward, no local `Prices`, Yahoo failure → event raises,
  partial-failure recorded, no row.
- Stablecoin deposit → price resolves to 1, one row, `Crypto transfer in`.
- Re-import same deposit → zero rows (idempotency).
- Merge with identical timestamps across streams → deterministic stable order.
- Sub-1e-9 reward quantity → `ValueError` on quantization, surfaced, no row.
- Option expired worthless (zero settlement quantity) → no settlement row
  emitted (quantity 0 guard); the premium trade row already records the cost.
- Option exercised ITM → settlement row with delivery coin quantity and
  settlement price; premium and settlement coexist as two rows on the same
  `Option` asset.
- Malformed option symbol (wrong segment count, unparseable date/strike,
  unknown side) → normalizer raises, partial-failure recorded, no row.

## 8. Sequencing recommendation

Implementation order, smallest-confidence-risk first:

1. `_merge_sorted_events` + `_single_leg` (pure, fully testable, no I/O).
2. Rewritten `parse_option_symbol` (both exchange formats) with exhaustive
   unit tests on documented symbols — pure, no I/O.
3. New coin client iterators (`iter_deposits`, `iter_withdrawals`, OKX
   equivalents) with malformed-payload tests.
4. New option client iterators (`iter_option_executions` / `iter_option_fills`,
   `iter_option_settlements`).
5. Coin normalizers + internal-transfer filtering (unit tests on documented
   payloads).
6. Option normalizers (premium + settlement) with unit tests.
7. `_transaction_type_for_event` settlement branch + persistence dispatch
   (option vs. coin resolver) — the only change near protected code; covered
   by the option regression integration tests.
8. Wire `get_transactions` to the unified stream + partial-failure tracking.
9. Integration tests (single-leg persistence, option persistence, idempotency,
   rollback).
10. `live`-marker tests; run `verify_crypto_import.py` (extended with option
    endpoints) against live creds once the venv is restored, to confirm real
    payload shapes match the documented fixtures.

## 9. Open items to confirm during implementation (not blocking design)

- Exact OKX `/asset/deposit-withdraw` response shape (combined stream vs
  per-direction) — confirmed via the `live` test or a single curl.
- ByBit earn `type` codes for the `transaction-log` filter and the
  internal-transfer classification codes — confirmed from a live query.
- API-key read scopes required for each new endpoint (asset-history and
  options read permissions on both exchanges).
- The exact OKX option settlement-history endpoint and its response fields
  (settlement price, delivered quantity, delivered coin) — confirmed from a
  live query or the API docs during implementation step 6.
- ByBit option delivery representation inside `/v5/account/transaction-log`
  (which `type` value, which fields carry the settlement price and delivered
  quantity) — confirmed from a live query.
