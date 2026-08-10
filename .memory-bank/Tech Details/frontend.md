---
Tech details/frontend.md
---

# Frontend — Technical Notes

> **Note:** This doc describes the current stack. Modernization to Vite + Pinia + `<script setup>` + TypeScript is planned (see `docs/superpowers/specs/2026-07-11-architecture-review-design.md`).

- **Stack:** Vue 3 with vue-cli 5 / webpack (Vite migration planned). Mix of Options API (`export default {}`) and Composition API (`setup()`); no `<script setup>` yet. Plain JavaScript (TypeScript adoption planned).
- **State:** Vuex 4, single global store (`frontend/src/store/index.js`). Pinia migration planned.
- **UI library:** Vuetify 3 + MDI icons. Charts via chart.js + vue-chartjs.
- **Forms & validation:** `vee-validate` + `yup` are used for transaction forms and other inputs.
- **HTTP client:** axios with a shared instance (`frontend/src/config/axiosConfig.js`) handling JWT auth + token-refresh queue.
- **Dev server:** `npm run serve` (vue-cli) for local dev on `127.0.0.1:8080`.
- **Long-running UX:** SSE/WebSocket flows for import progress; UI must show progress bars and request confirmations from users when needed (e.g., ambiguous parsed transactions).
- **Security:** Do not trust frontend calculations for authoritative financial outputs; rely on backend for final numbers.

---
