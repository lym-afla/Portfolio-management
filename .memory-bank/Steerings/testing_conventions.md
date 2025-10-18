---
Steerings/testing_conventions.md
---

# Testing Conventions

**Purpose:** Define expectations and patterns for tests so numerical correctness is preserved.

- **Test framework:** `pytest` for backend.
- **Fixtures:** Use realistic fixtures that mimic production transactions for regression tests.
- **Data types:** Tests must use `Decimal` consistently for numeric values.
- **Coverage:** Aim for high unit coverage on calculation modules — **>=90%** for core computations.
- **Test types:**
  - Unit tests for calculation helpers and small services.
  - Integration tests for API endpoints with DB fixtures.
  - Regression tests that reproduce historical production outputs.
- **CI:** Run tests and linters on each PR.

---
