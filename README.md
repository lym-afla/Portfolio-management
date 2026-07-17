# Portfolio Management System

A portfolio management application for tracking investments, calculating NAV,
and analyzing performance across multiple brokers and asset classes.

- **Frontend:** Vue 3 + Vite + Pinia + Vuetify 3 + TypeScript
- **Backend:** Django + Django REST Framework + Django Channels
- **Database:** SQLite (local dev)

## Prerequisites

- **Python ≥3.13** + [uv](https://docs.astral.sh/uv/) (package manager)
- **Node.js ≥20** + npm
- Git

## Quick Start

### 1. Clone and set up the backend

```bash
git clone https://github.com/lym-afla/Portfolio-management.git
cd Portfolio-management/backend

# Install all dependencies (creates .venv automatically)
uv sync

# Apply database migrations
uv run python manage.py migrate

# Start the backend server (ASGI via Uvicorn — required for WebSockets)
uv run python run_uvicorn.py
```

The backend will be available at `http://127.0.0.1:8000`.

> **Important:** Use `run_uvicorn.py`, not `manage.py runserver`. The app uses
> Django Channels for WebSocket-based transaction imports, which requires an
> ASGI server. `manage.py runserver` (WSGI) will work for REST endpoints but
> WebSockets will fail.

### 2. Set up the frontend

```bash
cd ../frontend

# Install dependencies
npm install

# Start the dev server (Vite)
npm run dev
```

The frontend will be available at `http://127.0.0.1:8080`.

### 3. Open the app

Navigate to `http://127.0.0.1:8080` in your browser. Register a new account or
log in with existing credentials.

## Environment Configuration

### Frontend (`.env.development`)

```
VITE_API_URL=http://127.0.0.1:8000
```

- The frontend API URL must point to the backend's host:port.
- Vite exposes env vars prefixed with `VITE_` (not `VUE_APP_`).
- Access via `import.meta.env.VITE_API_URL` in code.

### CORS

Django's CORS settings allow these frontend origins:
- `http://localhost:8080`
- `http://127.0.0.1:8080`

If Vite grabs a different port (8081, 8082, etc.) because 8080 is occupied,
the CORS check will fail. Kill the process holding port 8080 first.

### Backend Settings (`backend/portfolio_management/settings.py`)

Key development settings:
- `DEBUG = True`
- `DATABASES`: SQLite (`db.sqlite3`)
- `SECRET_KEY`: set in `.env` or settings — used for JWT signing and token encryption
- `CORS_ALLOWED_ORIGINS`: see above

## NPM Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start Vite dev server with HMR |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Preview the production build locally |
| `npm run test:unit` | Run Vitest unit tests |
| `npm run type-check` | Run `vue-tsc --noEmit` (TypeScript type checking) |
| `npm run lint` | Run ESLint on `src/` |
| `npm run format` | Run Prettier on `src/` |

## Backend Commands

All backend commands run from `backend/` via `uv run`:

| Command | Description |
|---------|-------------|
| `uv sync` | Install/update all dependencies |
| `uv run python run_uvicorn.py` | Start ASGI dev server (port 8000) |
| `uv run python manage.py migrate` | Apply database migrations |
| `uv run python manage.py makemigrations` | Create new migrations |
| `uv run python manage.py createsuperuser` | Create admin user |
| `uv run python manage.py spectacular --format openapi-json` | Generate OpenAPI schema |
| `uv run python -m pytest` | Run the test suite |
| `uv run python -m pytest -q --no-cov` | Run tests quietly without coverage |

## API Type Generation

The frontend has auto-generated TypeScript types from the backend's OpenAPI schema.
To regenerate after backend API changes:

```bash
bash frontend/scripts/generate-api-types.sh
```

This runs `drf-spectacular` on the backend and `openapi-typescript` on the frontend,
producing `frontend/src/types/api.d.ts`.

## Architecture

```
Portfolio-management/
├── backend/
│   ├── services/            # Business logic layer (financial calculations)
│   ├── common/              # Django models (Assets, Transactions, FX, etc.)
│   ├── core/                # Framework-agnostic utilities + table API entrypoints
│   ├── database/            # Securities/brokers/prices/FX management views
│   ├── transactions/        # Transaction CRUD + import views + WebSocket consumer
│   ├── dashboard/           # Dashboard summary + NAV chart APIs
│   ├── users/               # Auth, JWT, broker API token management
│   ├── portfolio_management/# Django settings, URLs, ASGI/WSGI
│   ├── tests/               # Unit, integration, and advanced test suites
│   └── pyproject.toml       # uv project config (runtime + dev dependencies)
├── frontend/
│   ├── src/
│   │   ├── stores/          # Pinia stores (auth.ts, app.ts)
│   │   ├── services/        # API client (api.ts — typed)
│   │   ├── composables/     # Vue composables (useWebSocket, useTableSettings, etc.)
│   │   ├── types/           # Generated API types (api.d.ts)
│   │   ├── components/      # Vue SFCs (dialogs, charts, dashboard widgets)
│   │   ├── views/           # Page-level Vue SFCs
│   │   ├── config/          # Axios instance + interceptors
│   │   └── router/          # Vue Router config
│   ├── vite.config.js       # Vite + Vuetify + Vitest config
│   ├── tsconfig.json        # TypeScript config (gradual typing)
│   └── package.json
├── docs/                    # Architecture specs + implementation plans
└── .memory-bank/            # Project knowledge base
```

## Features

- User authentication (JWT via SimpleJWT)
- Dashboard with portfolio NAV summary and charts
- Open/closed positions tracking with realized/unrealized gain-loss
- Multi-currency support with FX rate graph (networkx shortest-path)
- Bond amortization, ACI (accrued interest), and YTM calculations
- Transaction import from Excel (Charles Stanley, Galaxy) and broker APIs (Tinkoff, Bybit, OKX)
- Corporate actions (mergers, asset transfers, stock splits)
- Broker API token management (encrypted storage with HKDF key derivation)

## Testing

### Backend

```bash
cd backend
uv run python -m pytest                    # Full suite
uv run python -m pytest tests/unit/        # Unit tests only
uv run python -m pytest -k "test_nav"      # Run tests matching pattern
uv run python -m pytest --cov=services     # Coverage for services layer
```

### Frontend

```bash
cd frontend
npm run test:unit                          # Run all Vitest specs
npm run test:unit -- --watch               # Watch mode
```

## Troubleshooting

### CORS error on login

The frontend must be on port 8080 (matching Django's CORS allowlist). If Vite
starts on a different port, kill whatever is holding 8080:

```bash
# Find and kill the process on port 8080
netstat -ano | findstr ":8080.*LISTENING"
taskkill /PID <pid> /F
```

### WebSocket connection fails on Transactions page

The backend must be started with `run_uvicorn.py` (ASGI), not
`manage.py runserver` (WSGI). Also check that port 8000 is free.

### Database locked errors

This is a SQLite limitation during concurrent writes. For local dev, retry the
operation. This would not occur with PostgreSQL (planned for production).

## Documentation

- [Architecture spec](docs/superpowers/specs/2026-07-11-architecture-review-design.md)
- [Phase plans](docs/superpowers/plans/)
- [Project knowledge base](.memory-bank/index.md)
- [API schema](http://localhost:8000/api/schema/) (when backend is running)
