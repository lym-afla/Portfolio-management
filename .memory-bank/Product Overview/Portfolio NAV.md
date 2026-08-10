---
Product Overview/Portfolio NAV.md
---

# Portfolio NAV — Product Overview

**Purpose**

This file explains the role of NAV (Net Asset Value) and associated performance measures in the product. It documents the assumptions and user-visible behavior so product, QA and engineering teams have a shared understanding.

## Audience
- New engineers joining the repo
- QA engineers validating financial outputs
- AI coding agents that will change calculation code (must follow the rules in `Steerings/Calculation Conventions.md`)

## User story (concise)
- As an investor, I want to see my portfolio NAV and performance decomposed into components (BOP_NAV, invested, cash_out, price_change, capital_distribution, commission, tax, fx, EOP_NAV, TSR) so that I can understand what drove my portfolio returns in a given period.

## What is authoritative
- **Transactions** are canonical. Everything else (positions, NAV, IRR, performance breakdown) is derived from transactions and supporting data (Prices, FX, Bond metadata).
- **AnnualPerformance** is a derived aggregation cached in DB for convenience; it can be recomputed if needed.

## Key user-visible behaviors
- NAV is computed for given `user_id`, `account_ids`, `date`, and `target_currency` with optional breakdowns by `asset_type`, `currency`, `asset_class`, and `account`.
- Cash balances are included and converted to the `target_currency` using FX rates valid as of `date`.
- For bonds: prices are stored/treated as **percentage of nominal**. Valuation uses effective notional on the date.
- Short positions are allowed; position sign is preserved and used throughout calculations.

## Example workflows where accuracy matters
- Generating a year-end tax report (must not have silent rounding errors).
- Showing NAV breakdowns for multi-currency portfolios.
- Bond redemption calculations (we must correctly account for notional changes and buy-in prices).

---
