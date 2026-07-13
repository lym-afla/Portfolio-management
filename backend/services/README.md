# Services Layer

This package owns the portfolio management system's business logic. It sits
between the Django ORM (data access) and the API/views layer (HTTP).

## Conventions

- **Services are plain-Python modules.** Each module owns a domain workflow.
- **Services call the ORM for I/O** (read/write) but contain the sequencing
  and formulas. Heavy math should be pure functions taking plain values where
  feasible.
- **Model classes are thin schema + simple accessors.** No business logic
  methods on models. If a method does computation beyond returning a field or
  a simple related object, it belongs here.
- **Protected globs:** `backend/services/**` is protected per AGENTS.md.
  Changes require PR with approval + regression fixtures.
- **Numeric safety:** `Decimal` everywhere for money/prices. Never `float`.
  `ROUND_HALF_UP`. >=6 dp prices, >=9 dp quantities/FX.

## Module map

- `fx.py` — FX rate lookup (networkx currency graph), FX fetching from CBR/Yahoo
- `pricing.py` — price_at_date, calculate_value_at_date, split adjustment
- `positions.py` — position, entry/exit dates, accounts with positions
- `realized.py` — calculate_buy_in_price, get_economic_basis, realized/unrealized gain_loss
- `bonds.py` — bond notional, accrued interest, YTM, cash-flow projection
- `capital.py` — capital distributions (dividends, coupons, rewards), commission
- `accounts.py` — account balance, currencies
- `transactions.py` — transaction cash flow, pricing, classification, notional/split history
- `nav.py` — NAV assembly, portfolio_at_date, portfolio cash
- `performance.py` — performance calculation, account selection
- `corporate_actions.py` — mergers, asset transfers
- `importer.py` — broker import pipeline (Excel + API)

See Phase 1 plan: `docs/superpowers/plans/2026-07-11-phase1-service-layer.md`
