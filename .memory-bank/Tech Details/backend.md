---
Tech details/backend.md
---

# Backend — Technical Notes

## Main responsibilities
- Business logic: transaction processing, position computation, performance calculation
- API endpoints for frontend consumption
- Background processing for imports and broker sync

## Key modules & functions
- `NAV_at_date(...)` — entry point for NAV and breakdowns
- `_portfolio_at_date(...)` — asset query by date/account
- `Assets.price_at_date(...)` — price lookup with fallback to last transaction
- `Assets.calculate_value_at_date(...)` — valuation logic (bond vs non-bond)
- `Assets.calculate_buy_in_price(...)` — average buy-in algorithm
- `Assets.realized_gain_loss(...)` / `unrealized_gain_loss(...)` — decomposition logic
- Import parsers per broker and file type

## Data store
- Models: `CustomUser`, `Brokers`, `Accounts`, `Assets`, `Transactions`, `Prices`, `FX`, `AnnualPerformance`, `BondMetadata`, `NotionalHistory`, `BondCouponSchedule`
- Derived caches: `AnnualPerformance` — aggregated yearly performance stored in DB

## Notes
- `price_at_date` fallback (last transaction) must be clearly understood by QA and documented in tests.
- Current DB (SQLite) suitable only for local dev; plan Postgres for production.

---
