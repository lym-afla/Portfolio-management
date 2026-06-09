# Portfolio Management App — Project Instructions

## Project Knowledge Base

All project documentation lives in `.memory-bank/`. Start with `.memory-bank/index.md` for the full table of contents.

**Authoritative sources (read before touching related code):**
- `Product Overview/Portfolio NAV.md` — domain & NAV behavior
- `Steerings/Calculation Conventions.md` — financial calculation rules & invariants
- `Tech details/NAV Function and FX Flow.md` — low-level NAV/FX implementation

## AI Agent Rules (mandatory)

Full rules: `.memory-bank/Rules for AI Coding Agent.md`. Key rules summarized below.

### Protected code — requires human approval (PR with `needs-approval` label)
- `**/models.py` (Assets, Transactions, FX, AnnualPerformance, BondMetadata, NotionalHistory)
- `backend/**/calculations*.py`, `backend/**/performance*.py`
- `backend/**/services/performance/**`, `backend/**/services/fx/**`, `backend/**/services/bonds/**`
- Functions: `NAV_at_date`, `calculate_buy_in_price`, `realized_gain_loss`, `unrealized_gain_loss`, `calculate_value_at_date`, `_portfolio_at_date`, `price_at_date`, `FX.get_rate`
- `backend/**/migrations/**`

### Numeric safety
- Always use `Decimal` for money/price math — never `float`.
- Internal precision: >= 6 decimal places for prices, >= 9 for quantities/FX.
- Rounding: `ROUND_HALF_UP`. Persisted aggregates: 2 dp. UI: per `CustomUser.digits` or default 2.

### Virtual environment
- Use virtual environments to isolate project dependencies on the backend. Don't install packages globally.
- Use existing virtual environment saved in '/backend/venv' when running the backend code
- Use poetry to manage dependencies and virtual environment. Run `poetry install` to set up the environment and install dependencies.
- Use `poetry add <package>` to add new dependencies, which will automatically update `pyproject.toml` and `poetry.lock`.
- Use requirements.init to generate `requirements.txt` from `poetry.lock` for any tools that require it (e.g. CI, deployment scripts).
- Use requirements.dev.init to generate `requirements-dev.txt` from `poetry.lock` for development dependencies.
- Keep requirements files up to date by running the init scripts after any changes to dependencies.

### Auto-commit vs PR
- **May auto-commit** (if tests pass): formatting, import sorting, comments, type hints, small bug-fixes with unit tests in non-protected areas.
- **Must open PR**: any change to protected logic, numeric formulas, DB schema, or behavior that affects financial outputs.

### Testing
- All changes must pass `pytest`. Protected logic changes need unit tests + regression fixture with expected numeric result.
- Tests must use `Decimal`, include edge cases (zero quantity, missing price, etc.).
