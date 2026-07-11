# Phase 1 — Backend Service Layer Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract all financial business logic out of `common/models.py` (3,708 lines) and `core/*_utils.py` into a well-bounded `services/` package, updating every caller (views, core, tests, consumers) to call services directly. Model classes become thin schema + simple accessors.

**Architecture:** Full move — no shims, no delegation. Logic moves to `services/`; model methods are deleted; all callers updated. Services are plain-Python modules owning a workflow (read via ORM → compute → return/persist). Heavy math migrates to pure functions taking plain values where feasible.

**Tech Stack:** Django ORM (persistence boundary), Python 3.13, pytest + pytest-django, uv project mode.

## Global Constraints

- **Virtual environment:** All backend commands from `backend/` via `uv run <cmd>`. Dependencies in `backend/pyproject.toml` + `backend/uv.lock`.
- **Numeric safety:** `Decimal` for money/price math — never `float`. Internal precision ≥6 dp prices, ≥9 dp quantities/FX. `ROUND_HALF_UP`. Persisted aggregates 2 dp.
- **Protected code:** This phase touches protected financial logic (`calculate_buy_in_price`, `realized_gain_loss`, `NAV_at_date`, `FX.get_rate`, etc.). Per `Rules for AI Coding Agent.md`: unit tests + regression fixtures with expected numeric results, explicit human APPROVE workflow per PR.
- **No schema changes:** Phase 1 moves logic, does NOT touch `models.py` field definitions. `makemigrations --check --dry-run` must report "No changes detected" after every task.
- **No behavior changes:** Every existing test must pass with the same expected numeric values after extraction. The test assertions are the regression contract.
- **Branch:** `phase1/service-layer`. Merges to `main` only at the end of all phases (Phase 1 + 2 + 3 + 4).
- **Extraction depth:** Full move + update all callers. Model methods deleted, not shimmed.

## Service Package Structure (target)

```
backend/services/
├── __init__.py
├── fx.py              # FX.get_rate, FX.update_fx_rate, CBR/Yahoo fetchers, CBRRateLimitError
├── nav.py             # NAV_at_date, _portfolio_at_date, calculate_portfolio_cash, IRR, get_fx_rate
├── positions.py       # position, entry_dates, exit_dates, get_accounts_with_positions, split-adjustment trio
├── pricing.py         # price_at_date, calculate_value_at_date, get_split_adjusted_price
├── realized.py        # calculate_buy_in_price, get_economic_basis, realized_gain_loss, unrealized_gain_loss
├── capital.py         # get_capital_distribution, get_commission
├── bonds.py           # get_current_notional, get_current_aci, get_total_aci_for_position, _build_bond_cash_flows, calculate_bond_ytm
├── accounts.py        # balance, get_currencies
├── transactions.py    # total_cash_flow, get_price, classification helpers, _create_notional_history, _create_split_history
├── importer.py        # import pipeline (from core/import_utils.py + tinkoff_utils.py cycle break)
├── performance.py     # calculate_performance, get_selected_account_ids, get_last_exit_date_for_accounts
└── corporate_actions.py  # merger workflow (from database/views.py:api_create_merger), transfer_asset
```

**Rationale for split:** The four "engine" methods (`calculate_buy_in_price`, `get_economic_basis`, `realized_gain_loss`, `unrealized_gain_loss`) are tightly interconnected and all live on `Assets` — they move together to `realized.py`. NAV assembly (`NAV_at_date` etc.) is already partially separated in `core/portfolio_utils.py` and moves to `nav.py`. FX moves first because everything depends on it.

---

## Task Sequencing

The order is dictated by the dependency graph: FX → pricing → positions → realized → bonds → nav → everything else.

| Task | Service | What moves | Risk | Depends on |
|------|---------|------------|------|------------|
| 1 | Package scaffold | Create `services/__init__.py` + conventions doc | low | — |
| 2 | Test gap fill | Add direct tests for `calculate_value_at_date` + strengthen `NAV_at_date` tests | medium | — |
| 3 | `services/fx.py` | `FX.get_rate`, `FX.update_fx_rate`, `FX.get_investor_fx_entries`, module-level FX fetchers, `CBRRateLimitError` | high | 1 |
| 4 | `services/pricing.py` | `Assets.price_at_date`, `calculate_value_at_date`, split-adjustment trio (`get_cumulative_split_factor`, `get_split_adjusted_price`, `reverse_split_adjustment`) | medium | 3 |
| 5 | `services/positions.py` | `Assets.position`, `entry_dates`, `exit_dates`, `get_accounts_with_positions`, `investment_date` | medium | 3 |
| 6 | `services/realized.py` | `Assets.calculate_buy_in_price`, `get_economic_basis`, `realized_gain_loss`, `unrealized_gain_loss` | **highest** | 3, 4, 5 |
| 7 | `services/bonds.py` | `BondMetadata.get_current_notional`, `get_current_aci`, `get_total_aci_for_position`; `securities_utils._build_bond_cash_flows`, `calculate_bond_ytm` | high | 4, 5 |
| 8 | `services/capital.py` | `Assets.get_capital_distribution`, `get_commission` | medium | 6 |
| 9 | `services/accounts.py` + `services/transactions.py` | `Accounts.balance`/`get_currencies`; `Transactions.total_cash_flow`/`get_price`/classifiers/`_create_notional_history`/`_create_split_history` | medium | 3 |
| 10 | `services/nav.py` + `services/performance.py` | `NAV_at_date`, `_portfolio_at_date`, `calculate_portfolio_cash`, `IRR`, `calculate_performance`, helpers (from `core/portfolio_utils.py`) | high | 3, 4, 5 |
| 11 | `services/corporate_actions.py` | Merger workflow (from `database/views.py:api_create_merger`), `transfer_asset` workflow (from `transactions/views.py`) | high | 6, 9 |
| 12 | `services/importer.py` | Import pipeline (from `core/import_utils.py` + `tinkoff_utils.py` — break cycle) | high | 9 |
| 13 | Slim viewsets | `transactions/views.py` `save_single_transaction`/`save_transactions`/`import_transactions_from_api` → call services; `transactions/consumers.py:process_import` dispatch table | medium | 11, 12 |
| 14 | Decompose `core/` | Move remaining `core/*` to appropriate homes or leave as framework-agnostic utils; clean up `_utils` naming | medium | all |
| 15 | Final verification | Full suite + complexity check + regression fixtures + migrations check | — | all |

---

## Task 1: Create the services package scaffold

**Files:**
- Create: `backend/services/__init__.py`
- Create: `backend/services/README.md` (conventions doc)

**Interfaces:** none (this task establishes the package)

- [ ] **Step 1: Create the package**

Create `backend/services/__init__.py` (empty file — makes `services` a Python package).

- [ ] **Step 2: Write the conventions doc**

Create `backend/services/README.md`:

```markdown
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
  `ROUND_HALF_UP`. ≥6 dp prices, ≥9 dp quantities/FX.

## Module map

See Phase 1 plan: `docs/superpowers/plans/2026-07-11-phase1-service-layer.md`
```

- [ ] **Step 3: Verify Django still loads**

Run: `cd backend && uv run python manage.py check`
Expected: no issues.

- [ ] **Step 4: Commit**

```bash
git add backend/services/__init__.py backend/services/README.md
git commit -m "feat(services): scaffold services package with conventions"
```

---

## Task 2: Fill test gaps (calculate_value_at_date + NAV_at_date)

**Files:**
- Create: `backend/tests/unit/calculations/test_value_and_nav.py`

**Why this comes first:** `calculate_value_at_date` has zero direct tests and `NAV_at_date` has only 3 smoke calls. Before extracting either, we need a regression contract. These tests capture CURRENT behavior (characterization tests) — they document what the code does today, not what it "should" do.

**Interfaces:**
- Consumes: `Assets.calculate_value_at_date` (common/models.py:544), `core.portfolio_utils.NAV_at_date`

- [ ] **Step 1: Write characterization tests for calculate_value_at_date**

Create `backend/tests/unit/calculations/test_value_and_nav.py`. These test the CURRENT model methods (pre-extraction). After Task 6 moves `calculate_value_at_date` to `services/pricing.py`, these tests will be updated to call the service function instead — the assertions stay identical.

```python
"""Characterization tests for calculate_value_at_date and NAV_at_date.

These capture CURRENT behavior before the service-layer extraction.
Assertions document what the code does today (regression contract).
After extraction, tests are updated to call services.* but assertions
remain identical.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from common.models import Accounts, Assets, Brokers, FX, Prices, Transactions

CustomUser = get_user_model()


@pytest.fixture
def investor(db):
    return CustomUser.objects.create_user(username="valtest", password="pw")


@pytest.fixture
def broker(investor):
    return Brokers.objects.create(name="TestBroker", investor=investor)


@pytest.fixture
def account(broker, investor):
    return Accounts.objects.create(name="TestAcct", broker=broker, investor=investor, currency="USD")


@pytest.fixture
def usd_stock(investor):
    return Assets.objects.create(
        name="Test Stock", ISIN="US0000000000", type="Stock", currency="USD", exposure="Equity"
    )


@pytest.mark.django_db
def test_calculate_value_at_date_simple_position(account, usd_stock, investor):
    """Position * price for a simple stock."""
    Transactions.objects.create(
        account=account, security=usd_stock, investor=investor,
        date=date(2024, 1, 1), quantity=Decimal("100"), price=Decimal("50"),
        transaction_type="Buy",
    )
    Prices.objects.create(
        security=usd_stock, date=date(2024, 1, 31), price=Decimal("55"),
    )
    usd_stock.investors.add(investor)

    value = usd_stock.calculate_value_at_date(date(2024, 1, 31), investor)
    assert value == Decimal("5500")  # 100 shares * $55


@pytest.mark.django_db
def test_calculate_value_at_date_zero_position(account, usd_stock, investor):
    """Zero position → zero value (edge case)."""
    usd_stock.investors.add(investor)
    value = usd_stock.calculate_value_at_date(date(2024, 1, 31), investor)
    assert value == Decimal("0")


@pytest.mark.django_db
def test_calculate_value_at_date_no_price(account, usd_stock, investor):
    """Position exists but no price → value is zero or handled gracefully."""
    Transactions.objects.create(
        account=account, security=usd_stock, investor=investor,
        date=date(2024, 1, 1), quantity=Decimal("100"), price=Decimal("50"),
        transaction_type="Buy",
    )
    usd_stock.investors.add(investor)
    # No Prices row — capture current behavior (likely returns 0 or raises)
    value = usd_stock.calculate_value_at_date(date(2024, 1, 31), investor)
    # Document current behavior: if it returns None or 0, assert that
    assert value is not None
    assert value >= Decimal("0")


@pytest.mark.django_db
def test_calculate_value_at_date_bond(account, investor):
    """Bond value = position * price * notional / 100."""
    from common.models import BondMetadata

    bond = Assets.objects.create(
        name="Test Bond", ISIN="US1111111111", type="Bond", currency="USD", exposure="FI"
    )
    bond.investors.add(investor)
    BondMetadata.objects.create(
        asset=bond, initial_notional=Decimal("1000"), nominal_currency="USD",
    )
    Transactions.objects.create(
        account=account, security=bond, investor=investor,
        date=date(2024, 1, 1), quantity=Decimal("5"), price=Decimal("100"),
        transaction_type="Buy",
    )
    Prices.objects.create(security=bond, date=date(2024, 1, 31), price=Decimal("99"))

    value = bond.calculate_value_at_date(date(2024, 1, 31), investor)
    # Bond: 5 bonds * 99% * 1000 notional / 100 = 5 * 990 = 4950
    assert value == Decimal("4950")


@pytest.mark.django_db
def test_calculate_value_at_date_multi_currency(account, usd_stock, investor):
    """Value FX-converted when asset currency differs from target."""
    FX.objects.create(
        date=date(2024, 1, 30), from_currency="USD", to_currency="EUR",
        exchange_rate=Decimal("0.9"),
    )
    FX.objects.create(
        date=date(2024, 1, 30), from_currency="EUR", to_currency="USD",
        exchange_rate=Decimal("1.1111"),
    )
    Transactions.objects.create(
        account=account, security=usd_stock, investor=investor,
        date=date(2024, 1, 1), quantity=Decimal("100"), price=Decimal("50"),
        transaction_type="Buy",
    )
    Prices.objects.create(security=usd_stock, date=date(2024, 1, 31), price=Decimal("55"))
    usd_stock.investors.add(investor)

    value = usd_stock.calculate_value_at_date(date(2024, 1, 31), investor, target_currency="EUR")
    # 100 * 55 = 5500 USD * 0.9 = 4950 EUR
    assert value == Decimal("4950")
```

- [ ] **Step 2: Run tests — some will fail (capturing gaps)**

Run: `cd backend && uv run python -m pytest tests/unit/calculations/test_value_and_nav.py -v --no-cov`
Expected: some tests may fail because of fixture setup issues (field names, required fields). Fix the fixtures until tests pass against the CURRENT model methods. The goal is a green characterization suite.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/unit/calculations/test_value_and_nav.py
git commit -m "test: add characterization tests for calculate_value_at_date (pre-extraction)"
```

---

## Tasks 3–14: Service extraction (pattern)

Each extraction task follows the same TDD + move pattern. For each service:

### Per-task extraction discipline

1. **Read the current method(s)** — understand every line, every ORM call, every external dependency
2. **Write characterization tests** if coverage is thin (the assertions are the regression contract)
3. **Create the service module** — move the logic, adapting signatures:
   - Model methods become module-level functions taking the model instance (or its ID) as first arg
   - `self.transactions.filter(...)` → `asset.transactions.filter(...)` (same ORM, different receiver)
   - `self.field` → `asset.field` or passed as plain value
4. **Update ALL callers** — grep for every call site:
   - `asset.calculate_buy_in_price(...)` → `from services.realized import calculate_buy_in_price; calculate_buy_in_price(asset, ...)`
   - Views, core/, tests, consumers, templates — everywhere
5. **Delete the model method** — it's now fully in the service
6. **Run the full test suite** — every test must pass with identical assertions
7. **Verify no schema change** — `makemigrations --check --dry-run` → "No changes detected"
8. **Commit**

### Key signatures (to maintain consistency across tasks)

```python
# services/fx.py
def get_rate(from_currency: str, to_currency: str, date_as_of, investor=None) -> dict: ...
def update_fx_rate(date, investor, base=None, target=None) -> None: ...
def get_investor_fx_entries(investor) -> QuerySet: ...

# services/pricing.py
def price_at_date(asset, target_date, investor=None, account_ids=None, target_currency=None) -> Decimal | None: ...
def calculate_value_at_date(asset, target_date, investor, account_ids=None, target_currency=None) -> Decimal: ...
def get_cumulative_split_factor(asset, start_date, end_date) -> Decimal: ...
def get_split_adjusted_price(asset, price, start_date, end_date) -> Decimal: ...
def reverse_split_adjustment(asset, adjusted_price, start_date, end_date) -> Decimal: ...

# services/positions.py
def position(asset, target_date, investor, account_ids=None) -> Decimal: ...
def entry_dates(asset, investor, start_date=None, end_date=None, account_ids=None) -> list: ...
def exit_dates(asset, investor, end_date, start_date=None, account_ids=None) -> list: ...
def get_accounts_with_positions(asset, target_date, investor) -> list: ...
def investment_date(asset, investor) -> date | None: ...

# services/realized.py
def calculate_buy_in_price(asset, target_date, investor, currency=None, account_ids=None, exclude_transaction=None) -> Decimal: ...
def get_economic_basis(asset, target_date, investor, account_ids=None) -> dict: ...
def realized_gain_loss(asset, end_date, investor, start_date=None, account_ids=None) -> dict: ...
def unrealized_gain_loss(asset, target_date, investor, start_date=None, account_ids=None, target_currency=None) -> dict: ...

# services/bonds.py
def get_current_notional(bond_meta, target_date, investor=None, target_currency=None) -> Decimal: ...
def get_current_aci(bond_meta, target_date, investor=None, target_currency=None) -> dict: ...
def get_total_aci_for_position(bond_meta, target_date, investor, target_currency=None) -> Decimal: ...
def build_bond_cash_flows(bond_meta, ...) -> list: ...  # pure function
def calculate_bond_ytm(cash_flows, ...) -> Decimal: ...  # pure function

# services/nav.py
def nav_at_date(target_date, investor, account_ids=None, target_currency=None) -> dict: ...
def portfolio_at_date(target_date, investor, account_ids=None) -> QuerySet: ...
def calculate_portfolio_cash(target_date, investor, account_ids, target_currency=None) -> dict: ...
def irr(cash_flows: list, ...) -> Decimal: ...  # pure function

# services/accounts.py
def balance(account, target_date, target_currency=None) -> dict: ...
def get_currencies(account) -> set: ...

# services/transactions.py
def total_cash_flow(transaction, target_currency=None) -> Decimal: ...
def get_price(transaction) -> Decimal: ...
def create_notional_history(transaction) -> None: ...
def create_split_history(transaction) -> None: ...

# services/capital.py
def get_capital_distribution(asset, start_date, end_date, investor, account_ids=None, target_currency=None) -> dict: ...
def get_commission(asset, end_date, investor, account_ids=None, target_currency=None) -> Decimal: ...

# services/corporate_actions.py
def execute_merger(user, old_security_id, new_security_id, merger_date, conversion_ratio, cash_per_share) -> dict: ...
def execute_transfer(investor, security_id, from_account_id, to_account_id, quantity, transfer_date) -> dict: ...

# services/performance.py
def calculate_performance(investor, start_date, end_date, account_ids=None, target_currency=None) -> dict: ...
def get_selected_account_ids(request) -> list: ...
def get_last_exit_date_for_accounts(investor, account_ids) -> date | None: ...
```

### Task 3: Extract services/fx.py (HIGH RISK — everything depends on FX)

**What moves from common/models.py:**
- `FX.get_rate` (classmethod, lines 72–261, ~190 LOC) → `services.fx.get_rate(from_currency, to_currency, date_as_of, investor=None)`
- `FX.update_fx_rate` (classmethod, lines 264–314) → `services.fx.update_fx_rate(date, investor, ...)`
- `FX.get_investor_fx_entries` (classmethod, lines 317–319) → `services.fx.get_investor_fx_entries(investor)`
- Module-level: `is_yahoo_finance_available` (2442–2466), `update_FX_from_Yahoo` (2469–2543), `update_FX_from_CBR` (2565–2726), `_extract_cbr_rate` (2729–2766), `CBRRateLimitError` (2561–2562), CBR_* constants (2547–2558)

**Callers to update** (grep `FX.get_rate\|FX.update_fx_rate\|update_FX_from\|CBRRateLimitError`):
- `common/models.py` — `Assets.price_at_date`, `calculate_buy_in_price`, `realized_gain_loss`, `unrealized_gain_loss`, `get_capital_distribution`, `Transactions.total_cash_flow`, `Accounts.balance`, `BondMetadata.get_current_notional`/`get_current_aci` — ALL call `FX.get_rate`
- `core/portfolio_utils.py` — `get_fx_rate` wrapper
- `database/views.py` — `FXViewSet.get_rate`
- `database/management/commands/backfill_rubusd_from_cbr.py`
- All test files calling `FX.get_rate`

**Discipline:** After move, `FX` model retains only field definitions + `__str__`. The classmethod `get_rate` is deleted. Every caller imports from `services.fx`.

- [ ] **Step 1: Read FX.get_rate and all FX module-level functions** — understand the networkx graph construction, edge-walking, rate inversion
- [ ] **Step 2: Verify existing FX tests pass** — `uv run python -m pytest tests/unit/calculations/test_fx_calculations.py -v --no-cov`
- [ ] **Step 3: Create services/fx.py** — move all FX logic, adapt signatures
- [ ] **Step 4: Update common/models.py** — delete FX methods + module functions, keep model fields
- [ ] **Step 5: Grep and update ALL callers** — views, core, tests, management commands
- [ ] **Step 6: Run full test suite** — every test must pass
- [ ] **Step 7: Verify no schema change** — `makemigrations --check --dry-run`
- [ ] **Step 8: Commit** — `feat(services): extract FX logic to services/fx.py`

---

### Tasks 4–14 follow the same pattern.

**Task 4: pricing.py** — `price_at_date`, `calculate_value_at_date`, split trio. Depends on Task 3 (FX).

**Task 5: positions.py** — `position`, `entry_dates`, `exit_dates`, `get_accounts_with_positions`, `investment_date`. Depends on Task 3.

**Task 6: realized.py (HIGHEST RISK)** — the four interconnected engine methods. Depends on Tasks 3, 4, 5. This is the single most dangerous extraction: `realized_gain_loss` is 411 lines and calls `calculate_buy_in_price`, `get_economic_basis`, `FX.get_rate`, `get_effective_notional`. All four must move together. Run the full `test_gain_loss.py` (77 tests) + `test_buy_in_price.py` (25 tests) + `test_crypto_rewards.py` after.

**Task 7: bonds.py** — `BondMetadata` methods + bond cash-flow/YTM math from `securities_utils`. Depends on Tasks 4, 5.

**Task 8: capital.py** — `get_capital_distribution`, `get_commission`. Depends on Task 6.

**Task 9: accounts.py + transactions.py** — `Accounts.balance`, `Transactions.total_cash_flow` + classifiers + notional/split history creation. Depends on Task 3.

**Task 10: nav.py + performance.py** — moves from `core/portfolio_utils.py`. Depends on Tasks 3, 4, 5.

**Task 11: corporate_actions.py** — merger + transfer workflows from viewsets. Depends on Tasks 6, 9.

**Task 12: importer.py** — import pipeline from `core/import_utils.py` + `tinkoff_utils.py` (break cycle). Depends on Task 9. Largest single move (~3,600 lines combined).

**Task 13: Slim viewsets** — `save_single_transaction`/`save_transactions`/`import_transactions_from_api` → call services; `process_import` → dispatch table. Depends on Tasks 11, 12.

**Task 14: Decompose core/** — move/clean remaining `core/*` files.

---

## Task 15: Final verification

- [ ] **Step 1: Full test suite** — `uv run python -m pytest -q` — all pass, no new failures vs Phase 0 baseline (745 passed, 4 skipped, 2 pre-existing failures)
- [ ] **Step 2: Django check** — `uv run python manage.py check` — no issues
- [ ] **Step 3: Migrations** — `uv run python manage.py makemigrations --check --dry-run` — "No changes detected"
- [ ] **Step 4: Complexity check** — verify worst functions are now ≤20 (per complexity-management.md targets)
- [ ] **Step 5: Line count check** — `wc -l common/models.py` — target: under ~1,000 lines (down from 3,708)
- [ ] **Step 6: Protected globs verification** — confirm `services/**` now contains real code matching the protected globs in AGENTS.md

---

## Risk notes

- **Task 6 (realized.py) is the critical path.** The four engine methods are 1,046 lines combined, tightly interconnected, and protected. The existing test suite (77 gain/loss + 25 buy_in_price + crypto rewards tests) is the safety net. If any test fails after extraction, the move is wrong — do not adjust assertions to make tests pass.
- **Task 12 (importer) breaks a circular import.** `import_utils` ↔ `tinkoff_utils` reference each other. Both must be extracted together into `services/importer.py` (or split along the `_find_or_create_security` seam).
- **No new features.** Every task is a pure move. If a task discovers a bug, note it but do NOT fix it in the same change — fix bugs separately to keep the diff auditable.
- **Tests are the regression contract.** If the existing tests pass with identical assertions after the move, the extraction is correct. Do not weaken assertions.
