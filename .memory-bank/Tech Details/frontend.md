---
Tech details/frontend.md
---

# Frontend — Technical Notes

> **Note:** Updated for the frontend modernization (implementation branch `codex/frontend-modernization`, not yet merged to main). Current acceptance status: `docs/design/frontend-final-qa.md`.

- **Stack:** Vue 3 on Vite (rolldown-vite). New workspace components use `<script setup>`; TypeScript is adopted in `src/features/`, `src/services/` and shared utils, with the legacy Options-API views still plain JavaScript. Vuetify 3 workspace design system in `src/components/workspace/` (WorkspacePage/Section/Actions/table toolbar — one `h1` per route, committed context in the app bar, presentation components request-free).
- **State:** Pinia (`frontend/src/stores/`) — the portfolio context store (account selection, effective date, currency, digits) bootstraps from strictly validated `/users/api/user_settings/` + `/users/api/dashboard_settings/` reads (`src/services/api/context.ts`) and is the only writer of committed values.
- **Charts:** `src/features/charts/` — a validated chart-v2 boundary (`contracts.ts` + `parseChartEnvelope.ts`, decimal strings end to end), request ownership in `chartApi.ts` + `usePortfolioRequest` composables, renderer policy `rendererPolicy.ts`: the three ECharts families (NAV pilot, three allocation pies, security histories) are **default on when their `VITE_*_ECHARTS_ENABLED` build flags are absent** (exact `'false'` = rollback; build-time flags, not runtime switches). Chart.js remains the lazy compatibility fallback and rollback renderer; its removal (C5b) awaits an owner-accepted release validation cycle. Exact-value tables accompany every chart; server display strings render verbatim.
- **Forms & validation:** vee-validate + yup unchanged for transaction/import forms; dialogs share `defineAppDialog` + `useDialogFormFocus` (visible section labels, named Cancel, focus entry/return).
- **HTTP client:** axios with a shared instance (`frontend/src/config/axiosConfig.ts`, JWT auth + token-refresh queue); `VITE_API_URL` is the axios `baseURL` and must be provided at build time in test artifacts.
- **Dev server:** `npm run dev` (Vite). The backend dev server remains `uv run python run_uvicorn.py` (Django Channels ASGI).
- **Test harness:** `frontend/tests/browser/run-smoke.mjs` (agent-browser) — the all-false base matrix is the rollback acceptance; `--case final-qa-d8` builds its own unflagged default-on artifact and runs the labeled default-on route/workflow matrix (the D8 record documents both). Focused cases per workstream; delivery budgets in `scripts/measure-route-bundles.mjs`.
- **Long-running UX:** WebSocket import progress over the loopback protocol with stale-event containment; UI shows progress and asks for confirmation on ambiguous parsed transactions.
- **Security:** Do not trust frontend calculations for authoritative financial outputs; rely on backend for final numbers.

---
