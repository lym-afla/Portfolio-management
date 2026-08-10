---
Tasks/backlog.md
---

# Backlog — Initial Tasks

- Migrate from SQLite to PostgreSQL (design plan + tests + data migration)
- Add cache invalidation for `NAV_at_date` when Transactions/Prices/FX change
- Add unit & regression tests for `price_at_date` fallback and `calculate_buy_in_price`
- Harden parsers for CSV/PDF import and add robust validation & user confirmations
- Add CI pipeline: lint, test, build
- Improve broker connectors: token management, sandbox mode, polling vs webhooks

---
