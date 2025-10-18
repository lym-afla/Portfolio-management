---
Tech details/infra.md
---

# Infrastructure — Notes & Recommendations

- **Current:** Local dev with `.env` file for secrets.
- **Short-term:** Deploy to VPS/VM; migrate DB to Postgres; store secrets in a secret manager (or `.env` in server with restricted permissions until vault is ready).
- **Long-term:** Use containerization (Docker) + CI/CD (GitHub Actions) + managed Postgres, optional Redis for caching and Celery for background workers.
- **Monitoring:** Add Sentry for errors, Prometheus/Grafana for metrics if scale requires.

---
