---
Tech details/architecture.md
---

# Architecture — High Level

- **Monorepo** with two subfolders: `backend/` (Django) and `frontend/` (Vue 3 + Vite).
- **API layer:** Django REST API (DRF style; some legacy viewsets remain).
- **Realtime updates / progress:** SSE and WebSocket used selectively for one-way vs two-way communication.
- **Background tasks:** Small custom threads for import and sync tasks; no Celery in current version.
- **Runtime:** Uvicorn. Local dev DB: SQLite (file in backend root).
- **Deployment:** Not yet fully defined (local dev only); plan to move to a VPS/VM with Postgres and proper secret management.

---
