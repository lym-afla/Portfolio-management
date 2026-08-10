---
Product Overview/features.md
---

# Features — Portfolio Management App

- Transaction ingestion:
  - Manual form entry
  - File imports (CSV/PDF) with dedicated parsers per provider
  - Broker API connectors with token management
- Position and holdings view:
  - Open and closed positions
  - Drill-down per security with realized/unrealized G/L
- Performance & analytics:
  - NAV (BOP/EOP), invested, cash_in/out, price_change, capital_distribution, commission, tax, FX effect, TSR, IRR
  - Breakdowns by asset type, account, currency, and asset class
- Bonds & fixed income:
  - Bond metadata, notional history, coupon schedules, amortization handling
  - Bond pricing in percentage of nominal and redemption handling
- User preferences and personalization:
  - Default currency, digits, chart frequency/timeline, NAV breakdown defaults
- Exports & reports:
  - Yearly tax/performance reports, CSV and PDF exports
- Developer & ops features:
  - LRU-cached expensive calculations, hooks for cache invalidation, local dev with `.env` support

---
