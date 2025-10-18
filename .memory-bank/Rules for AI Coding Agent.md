# Rules for AI Coding Agent — Portfolio Management App

**Scope:** rules an automated coding agent must follow when making code changes, generating PRs, or producing outputs that affect the codebase, tests, data, or deployment.

> **Approval model:** Any rule marked `REQUIRES APPROVAL` must be explicitly approved by a human reviewer following the process described in "Review & Approval". The AI must present a short justification in the PR and require an `APPROVE` response from an authorized developer before merging.

---

## Table of contents
1. Allowed & disallowed change categories
2. Protected code & file globs
3. Testing & quality gates
4. PR & commit rules
5. Database & migration rules
6. Numeric precision, rounding & numeric safety
7. Runtime & production safety
8. Emergency rollback & remediation
9. Logging, observability & monitoring changes
10. Review & approval process
11. Example allowed/disallowed change scenarios

---

## 1. Allowed & disallowed change categories

**Allowed automated changes (AI may auto-commit if tests pass):**
- Non-functional changes: formatting (black, prettier), imports sorting, comment fixes.
- Low-risk refactors confined to a single file that do not change business logic, with tests unaffected.
- Adding or improving logging, adding type hints, improving docstrings.
- Small bug-fixes in non-protected areas covered by unit tests.
- Adding unit tests for untested helper functions (must not change protected logic behavior).

**Disallowed automated changes (AI must open a PR and require human review):**
- Any change that alters the behavior of protected logic (see next section).
- Changes to numeric formulas for NAV, FX decomposition, buy-in price, bond valuation, tax logic, or AnnualPerformance aggregation.
- Database schema changes that affect canonical models.
- Changes that can affect persisted financial outputs without regression tests and human approval.

**Rationale:** Financial correctness is paramount; automated changes need human oversight where the risk of silent breakage exists.

---

## 2. Protected code & file globs (REQUIRES APPROVAL)
The following are protected and must not be auto-edited without explicit human sign-off:

- `**/models.py` (files containing `Assets`, `Transactions`, `FX`, `AnnualPerformance`, `BondMetadata`, `NotionalHistory`)
- `backend/**/calculations*.py`
- `backend/**/performance*.py`
- `backend/**/services/performance/**`
- `backend/**/services/fx/**`
- `backend/**/services/bonds/**`
- Any file that contains functions/classes: `NAV_at_date`, `calculate_buy_in_price`, `realized_gain_loss`, `unrealized_gain_loss`, `calculate_value_at_date`, `_portfolio_at_date`, `price_at_date`, `FX.get_rate`
- Migration files touching numeric precision, field types, or canonical tables: `backend/**/migrations/**`

**Rationale:** These files implement financial invariants and historical logic; changes must be reproducible and tested.

---

## 3. Testing & quality gates (AI must enforce)
- All changes must pass unit test suite (`pytest`). For changes touching protected logic: include unit tests + regression fixture recreating an expected numeric result.
- Minimum coverage targets:
  - Core calculation modules: **>= 90% unit coverage**
  - Non-critical helpers: coverage encouraged but not strictly gated
- Tests must use `Decimal`, not float, and include at least one edge-case test (e.g., zero quantity, partial redemption, missing price).
- When adding tests, the AI must include test data fixtures and a short explanation of numerical expectations.

**Rationale:** Tests are the only practical guard against silent numerical regressions.

---

## 4. PR & commit rules
- Commit messages must follow the template:
  ```
  <scope>: <short description>

  - What changed:
  - Why:
  - Numerical impact / example:
  - Tests added:
  - Reviewer(s):
  ```
- PR must contain:
  - Short description of domain impact
  - Numerical example(s) showing before/after (if any numeric behavior changed)
  - List of files touched and whether they are protected
  - CI results and coverage report
- Labels to use:
  - `area:calculations` for financial changes
  - `risk:high` for any changes touching protected logic
  - `needs-approval` when `REQUIRES APPROVAL` applies

**Auto-merge rules for AI agent:**
- The AI **may** auto-merge if change is in "Allowed automated changes", tests pass, and the change is not in protected globs.
- For any change touching protected globs or altering behavior, the AI **must** open a PR requiring at least one human reviewer with the `APPROVE` action.

---

## 5. Database & migration rules (REQUIRES APPROVAL)
- Do not perform destructive migrations automatically.
- Backwards-compatible migrations only (adding nullable columns, new indices). Destructive changes (dropping columns, changing precision) must be planned with:
  - DB snapshot/backup plan
  - Migration rollback SQL
  - Validation script to re-compute aggregates and compare
- AI may prepare migration code and PR but must not run migrations in production.

**Rationale:** DB migrations can corrupt persisted financial data irreversibly.

---

## 6. Numeric precision, rounding & numeric safety
- Always use `Decimal` for money and price math.
- Internal precision: keep at least 6 decimal places for prices (prefer higher while computing) and at least 9 decimal places for quantities and FX where fields exist.
- Output rounding:
  - Persisted aggregates (AnnualPerformance.*): round to 2 decimal places (DB columns configured accordingly).
  - UI output: round per `CustomUser.digits` or default 2.
- Rounding mode: `ROUND_HALF_UP` unless otherwise specified.
- Do not cast to `float` for intermediate computations.

**Rationale:** Small rounding/floating errors accumulate and can materially change financial outputs.

---

## 7. Runtime & production safety
- The AI must not change production runtime configuration (deploy manifests, systemd services) without human review.
- When proposing performance-related changes (caching, query optimization), include regression tests and before/after timings on realistic dataset sizes.
- For caching: any cached calculation (like `NAV_at_date`) must have an invalidation strategy; AI must implement/modify caches only if invalidation is safe and documented.

---

## 8. Emergency rollback & remediation (AI must follow)
If a change causes incorrect outputs in production, the AI must:
1. Immediately open an incident PR describing the issue and revert commit(s) — *AI may draft the revert PR but must not merge without human approval*.
2. Provide step-by-step remediation checklist (stop deployment, revert code, restore DB snapshot if needed, recompute derived tables).
3. Produce a post-mortem draft (root cause, fix, regression tests) for human refinement.

**AI must never execute DB restores or server restarts automatically.**

---

## 9. Logging, observability & monitoring changes
- Adding metrics/logging is allowed; the AI must:
  - Follow existing logging format.
  - Add a telemetry entry describing new metrics to `infra.md`.
- Any change adding alerts must provide alert thresholds and rationales.

---

## 10. Review & approval process
- For `REQUIRES APPROVAL` changes the AI must:
  - Open a PR and add the `needs-approval` label.
  - Include a concise "domain rationale" and numeric regression example.
  - Await explicit human `APPROVE` comment (e.g., `APPROVE — <name>`) before merging.
  - If reviewer requests edits, the AI should apply changes and re-run tests.
- Keep an audit trail in PRs of the approval and reviewer identity.

---

## 11. Example scenarios
- Example: change `NAV_at_date` logic to include a new breakdown -> **must** open PR + tests + human approval.
- Example: fix a typo in UI copy -> AI may auto-commit after CI.
- Example: refactor internal helper used by protected code but not changing signatures -> AI must add tests that prove no behavioral change; open PR if anything touches protected globs.

---

## Final line: Approval instruction
This rules file **must** be approved explicitly by the project owner before being treated as enforced.
To approve, a human must add a comment in the PR or reply to the rules doc with: `APPROVE — <your name>`.
