---
Tech details/frontend.md
---

# Frontend — Technical Notes

- **Stack:** Vue 3 + Vite. Use Composition API.
- **State:** Project currently uses composition API; Pinia recommended for global state management if not already used.
- **Forms & validation:** `vee-validate` + `yup` are used for transaction forms and other inputs.
- **Dev server:** `npm run serve` for local dev. HMR via Vite.
- **Long-running UX:** SSE/WebSocket flows for import progress; UI must show progress bars and request confirmations from users when needed (e.g., ambiguous parsed transactions).
- **Security:** Do not trust frontend calculations for authoritative financial outputs; rely on backend for final numbers.

---
