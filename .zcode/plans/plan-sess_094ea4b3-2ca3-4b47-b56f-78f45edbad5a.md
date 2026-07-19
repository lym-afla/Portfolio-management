## Goal
Migrate from pip-tools (requirements.in/.txt) to **uv project mode**: a proper `[project]` table in `backend/pyproject.toml`, a real `backend/uv.lock`, and `uv sync` as the single install command. Delete the requirements files entirely. Update CI and docs to match.

Decisions: uv project lives in **`backend/`**; **drop `backend/.github/workflows/`** (keep root CI); **`requires-python = ">=3.12"`**.

---

## 1. Rewrite `backend/pyproject.toml` into a uv project

Add `[project]`, `[build-system]`, `[dependency-groups]`, and `[tool.uv]` sections alongside the existing `[tool.black]` / `[tool.pytest.ini_options]`.

**Build system:** Use `[tool.uv] package = false` — the backend is an application (run via `manage.py`), not a distributable package. This avoids needing `[build-system]`, hatchling, and wheel package selection (which would be painful given the non-standard layout: `manage.py`, `core/`, `users/`, `portfolio_management/` all at `backend/` top level). uv's `package = false` means `uv sync` installs deps into `.venv` without trying to build the project itself. This is the standard uv pattern for Django apps.

**Runtime deps** — move from `requirements.in` (unpinned names):
```
[project]
name = "portfolio-management-backend"
version = "0.1.0"        # static; no setuptools_scm needed for an app
requires-python = ">=3.12"
dependencies = [
    "aiohttp", "asgiref", "Babel", "beautifulsoup4", "channels",
    "chardet", "django-debug-toolbar", "django-cors-headers",
    "cryptography", "Django", "djangorestframework",
    "djangorestframework-simplejwt", "fake_useragent", "filelock",
    "fuzzywuzzy", "lxml", "networkx", "numpy", "openpyxl", "pandas",
    "pyOpenSSL", "python-Levenshtein", "pyxirr", "simplejson",
    "structlog", "t-tech-investments", "uvicorn", "yfinance", "zstandard",
]
```

**Dev deps** — consolidated from `requirements-dev.in` (dedup the trailing duplicate block; fold in `pytest-cov`, `pytest-xdist`, `pytest-mock`, `pytest-benchmark`, `pytest-django`, `requests` that CI currently installs inline):
```
[dependency-groups]
dev = [
    "pytest", "pytest-asyncio", "pytest-cov", "pytest-xdist",
    "pytest-mock", "pytest-benchmark", "pytest-django",
    "factory-boy>=3.3.0", "httpx>=0.28.0", "requests",
    "black>=23.9.1", "isort>=5.12.0", "flake8>=6.1.0",
    "flake8-docstrings>=1.7.0", "flake8-bugbear>=23.9.16",
    "flake8-django", "ruff>=0.14.0", "mypy>=1.6.1", "pre-commit>=3.4.0",
    "bandit>=1.7.5", "safety>=2.3.5",
    "coverage>=7.3.2", "codecov>=2.1.13",
    "sphinx>=7.2.6", "sphinx-rtd-theme>=1.3.0",
    "memory-profiler>=0.61.0", "line-profiler>=4.1.1", "py-spy>=0.3.14",
    "locust>=2.17.0", "prometheus-client>=0.18.0",
    "django-debug-toolbar>=4.2.0", "django-extensions>=3.2.3",
    "ipython>=8.16.1", "jupyter>=1.0.0", "ipykernel",
]
```

**Private index** — the TBank registry for `t-tech-investments`:
```
[[tool.uv.index]]
name = "tbank"
url = "https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple"
explicit = true
```
Plus a `[tool.uv.sources]` entry to pin `t-tech-investments` to that index:
```
[tool.uv.sources]
t-tech-investments = { index = "tbank" }
```

**`.python-version`** — create `backend/.python-version` with `3.12` so `uv sync` resolves consistently.

## 2. Generate `backend/uv.lock`

Run `uv lock` from `backend/`. This produces a real cross-platform lockfile capturing all transitive deps (including the new SDK's `iprotopy`/`grpcio-tools` chain). Delete the 52-byte stub `backend/uv.lock` first.

## 3. Delete requirements files

Remove from `backend/`: `requirements.in`, `requirements.txt`, `requirements-dev.in`, `requirements-dev.txt`. These are fully superseded by pyproject + uv.lock.

## 4. Update root CI workflows

**`.github/workflows/ci.yml`** and **`.github/workflows/pr-checks.yml`** — both have identical `backend-checks` jobs. Change the install steps:
- Replace `setup-python` pip cache + `pip install -r requirements*.txt` with:
  - Install uv: `astral-sh/setup-uv@v6`
  - `uv sync --frozen` (from `backend/` cwd) — installs exact locked deps
- Remove `cache-dependency-path` for requirements; uv cache key uses `uv.lock` hash automatically
- Keep `python manage.py check`, `makemigrations --check`, pytest steps as-is (they run inside the venv uv creates — use `uv run python manage.py check`)

**Delete `backend/.github/workflows/ci-backend.yml`** entirely (the duplicate pipeline). The matrix testing for 3.9–3.11 is dropped per the `>=3.12` decision.

## 5. Update `backend/Makefile`

- `install-dev` target: change `pip install -r requirements-dev.txt` → `uv sync`
- Fix the stale `--line-length=88` in `format`/`lint` targets → `100` (consistent with prior cleanup)
- Prefix commands with `uv run` where they invoke python tools

## 6. Update docs

- **`AGENTS.md` + `CLAUDE.md`** (identical): rewrite the "Virtual environment" section to the uv-project flow:
  - `uv sync` (creates `.venv`, installs all locked deps including dev group)
  - Add a dep: edit `backend/pyproject.toml` `[project.dependencies]` or `[dependency-groups.dev]`, then `uv lock`
  - No more `requirements.in`/`.txt`; the lockfile is `backend/uv.lock`
  - CI uses `uv sync --frozen`
- **`backend/Makefile`** comment if any references requirements
- **`.memory-bank/Tech details/development-environment-setup.md`** — update any pip/requirements references

## 7. Clean up stale `backend/venv`

The old `backend/venv` (created earlier via `uv venv`, outside project mode) conflicts with uv project mode's `.venv`. Delete `backend/venv/`; uv sync will create `backend/.venv/`.

---

## Explicitly NOT changing
- Root `pyproject.toml` — stays as workspace-level tool config (coverage, mypy, bandit, black/isort config for the root). Only removing the stale `requires-python`/`[project]` if it causes confusion; likely leave as-is since it has no deps.
- Django settings paths, manage.py, run_uvicorn.py — unchanged.
- The `.flake8`, `.pre-commit-config.yaml` — already fixed to 100 in prior task.
- Frontend (npm) — out of scope.

## Verification
1. **`uv sync` from `backend/`** — creates `.venv`, installs all deps including dev group + the private SDK from the TBank index. Proves the lockfile is valid.
2. **`uv run python manage.py check`** — Django boots against the new env.
3. **`uv run python -m pytest --collect-only -q`** (excluding pre-existing httpx-broken test) — 713 tests collect.
4. **`uv run python -m pytest tests/test_tinkoff_utils.py tests/test_broker_api_utils.py -q`** — SDK tests pass (proves the private index resolution works end-to-end).
5. **`git status`** — confirm requirements.* deleted, uv.lock + .python-version added, Makefile/CI/docs updated.
6. **YAML lint** — confirm CI workflow YAML is valid (no broken `cache-dependency-path` references).

## Risk note
The `requires-python = ">=3.12"` drops the 3.9–3.11 matrix from `ci-backend.yml`. Since we're deleting that workflow anyway, this is consistent. Django 5.x (currently pinned) requires 3.10+, so 3.12 is a safe floor.