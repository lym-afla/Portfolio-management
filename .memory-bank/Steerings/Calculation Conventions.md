---
Steerings/Calculation Conventions.md
---

# Calculation Conventions (rules for developers & AI agents)

**Scope:** This file defines the engineering and guardrail rules for changing financial computation code. It must be consulted and followed by any human or automated agent that touches calculation code.

> **Important:** The following sections include rules that require explicit human approval. AI agents must present these rules to a human reviewer and receive `APPROVE` before making changes to protected code areas.

## 1. Data of record
- **Source of truth:** `Transactions` model (plus `Prices`, `FX`, `NotionalHistory`, `BondCouponSchedule`).
- Derived tables (e.g., `AnnualPerformance`) are caches and may be regenerated; however, regeneration must follow a tested and reproducible procedure.

## 2. Protected logic (DO NOT auto-change)
These files and logic are **protected** and require explicit human sign-off to modify:

- Any code that implements **NAV calculation**, **FX decomposition**, **buy-in price**, **bond notional handling**, or **tax logic**.
- Example globs (update to match actual repo paths if different):
  - `portfolio_management/common/models.py` (particularly classes: `Assets`, `Transactions`, `FX`, `AnnualPerformance`, `BondMetadata`, `NotionalHistory`)
  - `portfolio_management/core/portfolio_utils.py`
  - `portfolio_management/core/securities_utils.py`
  - `portfolio_management/core/summary_utils.py`
  - `portfolio_management/core/tinkoff_utils.py`
  - `portfolio_management/core/transactions_utils.py`

Rationale: changing these areas without domain approval risks incorrect financial statements and regulatory/tax errors.

## 3. Numeric types, precision & rounding
- Use `Decimal` for all monetary and price computations.
- Internal calculation precision: keep **at least 6 decimal places** for prices, and **at least 9 decimal places** for quantities and FX where those fields exist.
- Output rounding policy:
  - UI / exported reports: round to 2 decimal places (unless the user’s `digits` setting requires different precision).
  - Persisted aggregated fields (e.g., `AnnualPerformance.*`): use `decimal_places=2` as per model. When writing into DB, round using `ROUND_HALF_UP`.
- Never convert to float for calculations; conversion to float is allowed only for visualization after careful rounding.

## 4. Buy-in price & realized gains
- The system uses **average (weighted) buy-in price** logic across transactions as implemented in `calculate_buy_in_price`.
- For long/short detection: the sign of the cumulative position determines whether we use the "long" or "short" buy-in logic.
- When computing realized gain for sales/redemptions, the code must:
  - compute `buy_in_price` (in local currency and in target currency)
  - apply FX conversion at the transaction date for cash flows
  - for bonds, use notional at the transaction date

## 5. FX decomposition
- FX effect = Total G/L (in reporting currency) - Price appreciation translated into reporting currency.
- For unrealized and realized: compute buy-in in both LCL and target currency, compute local price changes and translate appropriately to isolate FX.
- Use `FX.get_rate(from_currency, to_currency, date)` to obtain the FX factor. The function must be audited if changed.

## 6. Bonds
- Bond prices are stored/treated as percentage of nominal (e.g., `98.5` means `98.5%` of nominal).
- Valuation: `value = position * (price% / 100) * effective_notional`.
- `NotionalHistory` drives effective notional per date. The system accepts a daily notional schedule and resolves ambiguities in application logic (match by date proximity and amount).
- Coupon schedule from external provider is cached in `BondCouponSchedule`.

## 7. Position determination & partial sells
- A position is considered *closed* when cumulative quantity up to the date is zero.
- Partial sells leave an open position; partial realized gain is calculated on quantity sold.
- The average buy-in algorithm must be preserved unless explicitly replaced following a test-backed migration.

## 8. Tests & PR policy (for AI agents)
- Any change touching protected logic must include:
  - unit tests for the changed function covering normal and edge cases;
  - regression test that reproduces an example from production or from a real ticket (fixtures encouraged);
  - a short explanation in the PR description describing the domain rationale and expected numerical effects.
- AI agent rules:
  - **Allowed automated changes:** formatting, linting, non-business refactors (when behavior is unchanged), adding logging, small bugfixes in non-protected areas with tests.
  - **Disallowed automated changes (without human approval):** altering NAV, FX decomposition, buy-in algorithm, bond valuation, AnnualPerformance aggregation logic, tax logic, DB schema of canonical models.

## 9. Migration & DB rules
- Backwards-compatible migrations only. Destructive migrations (dropping columns, changing numeric precision) must be approved and executed via a safe deployment plan (backups + rollback SQLs).
- Do not assume zero-downtime for heavy migrations (SQLite is not suitable for heavy concurrent usage — plan to use PostgreSQL in production).

## 10. Emergency procedures
- If a deployment changes performance outputs or corrupts calculated values, the rollback process is:
  1. Revert the release in the deployment system (or stop the process on the server).
  2. Restore DB from snapshot if necessary.
  3. Recompute derived caches (`AnnualPerformance`) from canonical `Transactions` after verifying restored DB.
- AI agents must never perform a database restore operation automatically; only provide the steps and require human execution.

## 11. CI / Test requirements (quick checklist)
- `pytest` runs with coverage. Protect core calculation functions with `>=90%` test coverage in unit scope.
- Linting with `flake8` / `black` enforced on commits.

---
