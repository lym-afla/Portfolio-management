---
Steerings/dev_conventions.md
---

# Development Conventions

**Purpose:** Short, developer-facing conventions to follow when working on the project.

- **Language & frameworks:** Python (Django), JavaScript (Vue 3 + Vite).
- **Formatting & linting:**
  - Backend: `black`, `isort`, `flake8`.
  - Frontend: `prettier`, `eslint`.
  - Use pre-commit hooks to enforce formatting/linting on commits.
- **Numeric handling:** `Decimal` for money/prices; avoid `float` in calculation code.
- **Branching:** Feature branches: `feat/<short>`, bugfix branches: `fix/<short>`, hotfix: `hotfix/<short>`.
- **Commit messages:** Use scope: short summary + bullet list in body.
- **Caching:** Expensive results (e.g., `NAV_at_date`) may be cached, but any cache must have invalidation triggers on relevant model changes.
- **Protected logic:** Core finance functions (NAV, FX decomposition, buy-in price, bond valuation, AnnualPerformance) are protected — see `Rules for AI Coding Agent.md`.

---
