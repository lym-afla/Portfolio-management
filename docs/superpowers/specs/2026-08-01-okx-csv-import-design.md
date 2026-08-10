# OKX CSV Transaction Import — Design

**Date:** 2026-08-01
**Status:** In design (brainstorming)

## Problem

OKX's API only retains 3 months of trade-fill history, making it impossible to import older spot/option trades via the live API path. The user can download complete transaction history from OKX's web UI as CSV files. This design adds a CSV file-import path for OKX that reuses the existing crypto-exchange normalizers and persistence layer.

Two CSV report types are available:
- **Trading History**: spot trades, option trades/settlements, internal transfers. Columns: `id, Order id, Time, Trade Type, Symbol, Action, Amount, Trading Unit, Filled Price, PnL, Fee, Fee Unit, Position Change, Position Balance, Balance Change, Balance, Balance Unit`.
- **Funding History** (deferred): deposit yields, deposits, stakes, transfers. Columns: `id, Time, Type, Amount, Before Balance, After Balance, Symbol`.

**Scope of this design:** Trading History CSV import. Funding History CSV import is a fast-follow.

## Architecture

### Approach: CSV-to-payload adapter → existing normalizers → existing persistence

Write a thin adapter that maps OKX CSV columns into the OKX REST JSON field names the existing `normalize_okx_*` functions expect. The adapted dict is fed to the normalizer, producing a `CryptoExchangeEvent`, which is persisted by the existing `persist_crypto_exchange_event`. This reuses all the stablecoin-as-cash, single-leg, fee, and idempotency logic without duplication.

### Components

| Component | Location | Responsibility |
|---|---|---|
| `parse_okx_trading_csv` | `services/importer.py` (new async generator) | Read CSV, yield status dicts + persist events. Follows the Charles Stanley parser pattern. |
| `_okx_csv_row_to_payload` | `services/importer.py` (new helper) | Map a CSV row dict → OKX REST JSON dict (rename columns, parse timestamps, synthesize missing fields). |
| OKX branch in `import_transactions_from_file` | `transactions/views.py:686-710` | New `elif` branch dispatching to `parse_okx_trading_csv` when the broker is OKX. |
| Frontend: OKX file-import trigger | `TransactionImportDialog.vue` | Detect OKX broker, send `is_okx: true` flag. |

### CSV row → OKX API payload mapping

Each CSV row has a `Trade Type` (Spot, Option, Transfer) and `Action` (Buy, Sell, Transfer in, Transfer out, Expired OTM). The adapter maps:

**Spot trades** (`Trade Type=Spot`, `Action=Buy/Sell`):
- Each spot trade appears as TWO CSV rows: one for the base side (e.g. BTC, `Trading Unit=BTC`), one for the quote side (e.g. USDT, `Trading Unit=USDT`).
- **Pair them by `Order id`**: rows sharing the same `Order id` are the two legs of one trade.
- Build one `normalize_okx_spot_fill` payload per pair: `instId = Symbol`, `side = Action.lower()`, `fillSz = Amount` (from the base row), `fillPx = Filled Price` (from either row), `fillTime = parse(Time)`, `tradeId = id` (from the base row), `fee = Fee` (from the base row), `feeCcy = Fee Unit`.

**Option trades** (`Trade Type=Option`, `Action=Sell/Buy`):
- Map to `normalize_okx_option_fill` payload: `instId = Symbol`, `side = Action.lower()`, `fillSz = Amount`, `fillPx = Filled Price`, `fillTime = parse(Time)`, `tradeId = id`, `fee = Fee`, `feeCcy = Fee Unit`.

**Option expirations** (`Trade Type=Option`, `Action=Expired OTM`/`Expired ITM`):
- Map to `normalize_okx_option_settlement` payload (bills-archive shape): `ccy = Balance Unit`, `balChg = Position Change`, `px = Filled Price`, `billId = id`, `ts = parse(Time)`.

**Transfers** (`Trade Type=Transfer`, `Action=Transfer in/out`):
- These are internal funding↔trading account transfers. Per the design decision (skip internal transfers), SKIP these rows (yield a "skipped" status). They are net-zero and would distort the portfolio.

### Timestamp parsing

CSV `Time` is `YYYY-MM-DD HH:MM:SS` in UTC+3 (from the header line: `Time Zone:UTC+3`). Convert to UTC ms-epoch: parse the datetime, subtract 3 hours, convert to timestamp_ms.

### Deduplication strategy

**Problem:** the CSV `id` column is OKX's billId, which differs from the `tradeId` the API normalizer uses. So spot trades imported via CSV would NOT dedup against the same trades imported via API — they'd create duplicates.

**Solution:** use the CSV `Order id` + a leg index as the `provider_event_id`, prefixed `csv:` to distinguish from API imports. This means CSV and API imports of the same trade will coexist as separate transactions (different `import_event_id`), which is acceptable as long as the user doesn't import the same period via both methods. Document this limitation.

Alternative considered: try to match CSV `id` to API `tradeId` — but they're different id spaces (billId vs tradeId), so matching is unreliable.

### Fee handling

The CSV has separate `Fee` and `Fee Unit` columns. For spot buys, the fee is typically in the base asset (BTC). The adapter maps these to the `fee`/`feeCcy` fields on the normalizer payload, which the existing `_spot_legs` + `persist_crypto_exchange_event` handle correctly (converting to cash_flow for stablecoin quotes, or to commission field).

### Frontend changes

Minimal: detect when the selected broker is OKX and send `is_okx: true` in the WebSocket `start_file_import` message. The `import_transactions_from_file` view checks this flag (or the broker name) to route to the OKX parser. The existing file-input UI (`v-file-input` accepting `.csv`) works unchanged.

## Testing

- Unit test the CSV-to-payload adapter: feed a sample CSV row, verify the output payload has the correct OKX API field names and values.
- Integration test the full parser: read a sample CSV file (the user's actual file as a test fixture), run `parse_okx_trading_csv`, verify the correct number of `CryptoExchangeEvent`s are created and persisted.
- Test spot-trade pairing: two CSV rows with the same `Order id` produce ONE event (not two).
- Test dedup: importing the same CSV twice produces zero new transactions.
- Test transfer skipping: rows with `Trade Type=Transfer` are skipped.

## Open questions

1. **Transfer handling**: should we skip all transfers, or import `Transfer in` (deposits from funding account) as `Cash in` and `Transfer out` as `Cash out`? Skipping is simpler and matches the "internal transfers are net-zero" design decision. But the user's trading-account USDT starts with a `Transfer in` from the funding account — if we skip it, the trading account's first USDT balance has no source. **Recommend: skip for now (matching the API behavior); revisit if the balance looks wrong.**

2. **Multi-file upload**: OKX limits CSV exports to 3 months per file. A multi-year history requires multiple files. Should the parser accept multiple files in one import, or does the user upload them one at a time? **Recommend: one file at a time for v1 (simplest; dedup handles overlaps).**

3. **The USDT400 discrepancy**: the user noted a discrepancy about a USDT400 inflow. The CSV shows `2025-03-23 11:51:38, Deposit, 400 USDT` in the funding history. In the trading history, the first USDT `Transfer in` is `29994.78` on 2026-06-22. These are different events. The discrepancy may be about which account the 400 USDT landed in (funding vs trading). **Flag for investigation during testing; not a design blocker.**
