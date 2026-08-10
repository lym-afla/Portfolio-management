---
Tech details/architecture.md
---

# Architecture — High Level

- **Monorepo** with two subfolders: `backend/` (Django) and `frontend/` (Vue 3, vue-cli / webpack; Vite migration planned).
- **API layer:** Django REST API via DRF (~80 endpoints, mix of `@api_view` function-based views and `ModelViewSet`/`ViewSet` classes).
- **Realtime updates / progress:** SSE and WebSocket used selectively for one-way vs two-way communication. See "Realtime / progress streaming" below.
- **Background tasks:** Small custom threads for import and sync tasks; no Celery in current version.
- **Runtime:** Uvicorn. Local dev DB: SQLite (file in backend root). Dependencies managed with uv project mode (`backend/pyproject.toml` + `backend/uv.lock`).
- **Deployment:** Not yet fully defined (local dev only); plan to move to a VPS/VM with Postgres and proper secret management.

## Realtime / progress streaming

The app uses two transports, deliberately:

- **WebSocket** (`channels.generic.websocket.AsyncWebsocketConsumer`) — for bidirectional progress during **transaction import**. The frontend connects via native `WebSocket` in `frontend/src/composables/useWebSocket.js`, authenticating with the JWT access token as a query parameter. See `backend/transactions/consumers.py:TransactionConsumer`.
- **Server-Sent Events** (`channels.generic.http.AsyncHttpConsumer`) — for one-way progress streaming during **price and FX imports** and **account-performance recalculation**. See `backend/database/consumers.py` (`UpdateAccountPerformanceConsumer`, `PriceImportConsumer`, `FXImportConsumer`).

Socket.io is **not** used. (A legacy `socket.io-client` dependency was removed in Phase 0.)

---
