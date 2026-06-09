# Crypto Exchange Brokers Design

Date: 2026-06-07
Branch: `codex/add-crypto-exchange-brokers`

## Goal

Add a design for importing broker data from crypto exchanges Bybit and OKX. The eventual implementation will let users create Bybit and OKX brokers, store exchange API credentials through User Settings, create broker accounts, and fetch exchange activity into the existing portfolio transaction model.

The design includes spot crypto trades, stablecoins, earn/funding rewards, deposits, withdrawals, transfers, fees, and BTC options.

## Project Constraints

The project documentation states that transactions are canonical. NAV, positions, summary tables, and Security pages are derived from transactions plus supporting prices, FX, and instrument metadata.

This feature touches protected areas:

- `backend/**/models.py`
- transaction types and persisted schema
- gain/loss, capital distribution, cost basis, and summary behavior
- migrations
- broker API credential storage

Implementation must therefore go through a PR with `needs-approval`, regression tests, and fixed Decimal expectations for financial outputs.

## External API Anchors

Context7 documentation was checked for both exchanges.

Bybit:

- Use `/v5/account/transaction-log` for account movements, rewards, interest, settlement, delivery, transfers, and other account log events.
- Use `/v5/execution/list` with categories such as `spot` and `option` for fills.
- Auth uses HMAC-SHA256 over `timestamp + api_key + recv_window + query_or_body`, with `X-BAPI-API-KEY`, `X-BAPI-TIMESTAMP`, `X-BAPI-RECV-WINDOW`, and `X-BAPI-SIGN`.
- Pagination uses cursors such as `nextPageCursor`.

OKX:

- Use `/api/v5/trade/fills-history` for spot and option fills.
- Use account/funding bills history for rewards, interest, transfers, and asset movements.
- Use deposit and withdrawal history endpoints for external movements.
- Auth uses `OK-ACCESS-KEY`, `OK-ACCESS-SIGN`, `OK-ACCESS-TIMESTAMP`, and `OK-ACCESS-PASSPHRASE`; the signature is Base64-encoded HMAC-SHA256 over `timestamp + method + requestPath + body`.
- Pagination uses cursor-style request parameters such as `before` and `after`.

## Recommended Approach

Use an asset-led crypto model.

Every exchange-held instrument is an `Assets` row:

- BTC, ETH, USDT, USDC, and other coins or tokens use `type="Crypto"`.
- Stablecoins are crypto assets, not fiat currencies and not `FXTransaction` currencies.
- BTC options use `type="Option"` and the existing `OptionMetadata` model.

Do not create a parallel crypto ledger. Do not treat crypto pairs such as `BTC/USDT` as fiat FX. Exchange activity should become canonical asset-linked transactions so existing positions, NAV, Security pages, and summary tables continue to work from the same source of truth.

## Domain Model

Add or extend constants and choices for crypto-aware behavior:

- Asset type: `Crypto`.
- Transaction types for crypto-specific events, with final names decided during implementation:
  - `Crypto reward`
  - `Crypto transfer in`
  - `Crypto transfer out`
  - `Crypto trade in`
  - `Crypto trade out`
  - `Option settlement`

Provider import data needs a durable external identity. Add an import grouping/event identity concept so rows created from the same exchange fill or bill can be reconciled and deduplicated. The exact schema should be chosen during implementation, but it must support:

- provider name
- provider account id
- provider event id, trade id, bill id, or transaction id
- group id for multi-leg events
- raw event category

## Credential UX

Extend the existing User Settings broker API workflow rather than creating a separate credential entry path.

Frontend:

- Extend `BrokerTokenManager.vue`.
- Add Bybit and OKX to supported provider sections.
- Render provider-specific fields in the Add Token dialog.
- Show only safe metadata after save: provider, broker, active status, sandbox/demo flag, created date, and verification status if added.
- Never return API secrets to the frontend.

Backend:

- Add `BybitApiToken` and `OKXApiToken` models extending `BaseApiToken`.
- Bybit token fields: API key, API secret, testnet flag.
- OKX token fields: API key, API secret, passphrase, simulated-trading flag.
- Add serializers, viewsets, URLs, revoke/delete/test-connection handling, and aggregate token listing.
- Update broker filtering so Direct Import sees brokers with active Bybit/OKX credentials, not only TBank credentials.

Connection verification:

- Bybit: signed lightweight private account request.
- OKX: signed lightweight private account or funding request.

## Import Architecture

Keep the existing provider-oriented flow:

1. Provider API client fetches raw exchange data.
2. Provider normalizer converts raw payloads into internal import events.
3. Mapping layer converts normalized events into canonical transactions.
4. Existing import UI/progress flow persists and reports results.

Add provider clients:

- `BybitAPI`
- `OKXAPI`

Each client should:

- authenticate with encrypted credentials for the selected broker/user
- support production and test/demo modes
- fetch by date range
- page through results safely
- apply retry/backoff and rate-limit-aware delays
- yield normalized events rather than writing database rows directly

Normalized events should include:

- provider
- provider account id
- provider event id
- timestamp
- category: trade, reward, transfer, fee, settlement, deposit, withdrawal
- asset symbols and quantity deltas
- fee asset and amount
- price or mark fields when available
- raw payload reference for debugging

## Crypto Pair Trades

For asset pairs such as `BTC/USDT`, do not use `FXTransaction`.

Represent the exchange fill as linked asset movements:

- BTC leg: buy or sell BTC.
- USDT leg: opposite movement in USDT.
- Fee leg: reduce the asset used to pay the fee, whether BTC, USDT, OKB, or another token.
- Shared provider event/group id ties the legs to one exchange fill.

Example: buy `0.1 BTC` for `6000 USDT` with `3 USDT` fee.

- BTC position increases by `0.1`.
- USDT position decreases by `6003`.
- The event group records that both rows came from the same fill.
- Fiat reporting comes from price data at the relevant date, not from treating USDT as fiat cash.

Crypto-crypto pairs such as `ETH/BTC` need an explicit fiat valuation step before persistence. The transaction `price` field is consumed by downstream NAV, realized gain/loss, and basis calculations as a fiat-denominated price. Therefore an exchange price such as `1 ETH = 0.05 BTC` must not be stored directly as `price=0.05`, because that would be interpreted as `0.05 USD`.

The approved approach is conservative quote-asset valuation:

- Resolve the quote asset as a crypto `Assets` row.
- Look up the quote asset fiat price at the trade timestamp, for example BTC/USD.
- Derive the base leg fiat price from `base/quote * quote/USD`.
- Persist the quote leg at the same quote asset fiat price.
- If the quote asset fiat price is missing for the trade date, reject the event with a clear import error that names the missing quote asset/date instead of persisting unsafe rows.

Example: buy `1.5 ETH` for `0.075 BTC` when BTC/USD is `60000`.

- ETH leg uses derived fiat price `0.05 * 60000 = 3000 USD`.
- BTC leg uses fiat price `60000 USD`.
- Both legs remain canonical asset transactions linked by provider group id.
- No `FXTransaction` is created, and no BTC-denominated price is stored in a USD-valued field.

## Rewards And Cost Basis

Rewards should behave like scrip-dividend-style income.

`Crypto reward` should:

- link to the rewarded crypto asset as `security`
- store positive native `quantity`
- increase the asset position
- capture event-date fiat value for capital distribution reporting
- not create fiat cash movement
- preserve provider reward type in comment or import metadata

`Crypto reward` should not use `cash_flow` as a fiat cash movement. Account cash balances are derived from transaction cash flow, so storing reward value in `cash_flow` would incorrectly create fiat cash. Instead, reward fiat value should be derived from `quantity * price` at the event date, with `price` representing event-date value per rewarded unit in the transaction valuation currency.

Summary behavior:

- Include reward fiat value in `capital_distribution`, alongside dividends and coupons.
- Convert to selected fiat currency using the same Decimal and FX/price discipline used elsewhere.

Open-position behavior:

- Current position includes rewarded quantity.
- Current value includes rewarded quantity at current price.
- Paid entry price/value must not be silently distorted by reward lots.
- Gain/loss logic needs an explicit economic basis for reward lots equal to market value at receipt, otherwise rewards can be double-counted as both capital distribution and price gain.
- Principal transfers between wallets/accounts are neutral by default. They move asset quantity into or out of a selected account, but should not create realized gain/loss unless the exchange event is explicitly a trade, fee, settlement, reward, or taxable disposal.

Security page behavior:

- Show native rewards, for example `0.012345 BTC`.
- Show fiat rewards matching capital distribution.
- Show native and fiat yield separately for selected account/date range.

## BTC Options

Use existing option architecture:

- Create/find an `Assets` row with `type="Option"`.
- Create/find the underlying BTC `Assets` row.
- Fill `OptionMetadata` with underlying asset, strike price, expiration date, call/put type, and contract size.
- Import option buys/sells as transactions against the option asset.
- Import settlement, delivery, and expiry as explicit option lifecycle transactions.

Bybit options use `category=option` execution and transaction log records. Symbols such as `BTC-...-C` or `BTC-...-P` should be parsed into option metadata where exchange metadata is insufficient.

In the first implementation, support option trades and settlement/expiry records needed by real imported data. Full margin, assignment, Greeks, and advanced derivatives analytics should remain out of scope unless a real fixture requires them for correctness.

## Reporting And UI

Summary tables:

- Rewards appear in `capital_distribution` in selected fiat currency.
- Crypto price movement appears in `price_change`.
- Fees appear in `commission`.
- Stablecoin holdings appear as crypto positions, not cash balances.

Open Positions table:

- Show crypto assets and stablecoins as positions.
- Current position includes rewards.
- Current value uses current market price.
- Entry/basis labeling should be clarified so paid entry, reward basis, and total economic basis are not conflated.

Security page:

- Add crypto reward/yield section.
- Show native reward quantity by date range/account.
- Show fiat reward value matching capital distribution.
- Show option metadata for option assets.

Transaction history:

- Add descriptions for crypto rewards, crypto transfers, asset-pair trade legs, fees, and option settlements.

## Testing

Use Decimal for expected values. Add tests for:

- Bybit signing, cursor pagination, and mocked response normalization.
- OKX signing, cursor pagination, and mocked response normalization.
- Token save/test/revoke/delete flows for Bybit and OKX.
- Brokers with active Bybit/OKX tokens appearing in Direct Import.
- Duplicate detection using provider event ids.
- `BTC/USDT` spot trade import as linked asset movements.
- `ETH/BTC` spot trade import using existing BTC/USD price to derive fiat leg prices.
- Missing quote asset fiat price rejection for crypto-crypto pairs.
- Stablecoins as `Asset(type="Crypto")`, not cash.
- Crypto reward import increasing native position.
- Crypto reward fiat value appearing in capital distribution.
- Reward lots not corrupting paid entry price.
- Reward lots not double-counting total return.
- Fee paid in a third crypto asset.
- BTC option asset creation with `OptionMetadata`.
- Option trade and settlement import.
- Security page reward totals in native and fiat terms.
- Summary/open/security page consistency for one fixed fixture.

Run focused backend tests first, then broader backend pytest if feasible. Run frontend unit tests for token manager/import UI changes when implemented.

## Implementation Phases

1. Domain foundation:
   - crypto asset type
   - crypto/reward/option transaction constants
   - import event/group identifiers
   - migrations
   - capital distribution and reward cost-basis behavior

2. Credential UX:
   - Bybit and OKX token models
   - serializers, viewsets, URLs
   - User Settings token manager updates
   - connection verification

3. Exchange clients:
   - Bybit REST client and normalizer
   - OKX REST client and normalizer

4. Import mapping:
   - spot pair trades
   - crypto-crypto quote-asset fiat valuation
   - rewards/earn/funding
   - deposits, withdrawals, transfers
   - fees
   - options, settlement, expiry

5. Reporting/UI:
   - open positions basis clarity
   - Security page native/fiat rewards
   - transaction descriptions

6. Regression hardening:
   - fixture payloads
   - fixed Decimal expected values
   - summary/open/security consistency tests

## Implementation Decisions To Preserve

- Provider event ids and import grouping are required. Exact field names can be chosen during implementation, but duplicate detection must be provider-id based for exchange imports.
- `Crypto reward` must have no fiat cash-flow side effect. Reward value is derived from event-date quantity and price.
- Crypto-crypto pairs must not persist quote-denominated prices into fiat-valued transaction fields. Use existing quote asset fiat prices, or reject the event when the needed price is missing.
- Crypto principal transfers are neutral by default.
- Add fixtures for both Bybit and OKX in the first implementation plan, with Bybit implemented first only if sequencing is needed.
