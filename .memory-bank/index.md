---
.memory-bank/index.md
---

# .memory-bank — Table of Contents

This repository of `.md` files is the canonical memory bank for the portfolio management application. Use these files as contextual input for AI coding agents and for onboarding new developers.

**Authoritative core (canonical sources):**

- `Product Overview/Portfolio NAV.md` — *Primary product & domain description* (source of truth for NAV behavior and user-facing expectations).
- `Steerings/Calculation Conventions.md` — *Authoritative rules for calculations and protected logic* (source of truth for financial invariants and guardrails).
- `Tech details/NAV Function and FX Flow.md` — *Low-level technical mapping of NAV and FX code* (source of truth for implementation details).

**Complementary drafts (expanders & operational docs):**

- `Rules for AI Coding Agent.md` — Formal rules the automated coding agent must follow (PRs, approvals, protected globs).

- Product Overview/
  - `user_stories.md` — user stories derived from product goals and interview.
  - `features.md` — feature list and capabilities.

- Steerings/
  - `dev_conventions.md` — developer-facing coding & branching conventions (short form).
  - `testing_conventions.md` — testing expectations and CI guidance.

- Tech details/
  - `architecture.md` — high-level architecture summary (monorepo, API, realtime choices).
  - `backend.md` — backend technical notes and key modules mapping.
  - `frontend.md` — frontend technical notes and UX for long-running tasks.
  - `infra.md` — infrastructure recommendations and migration notes.
  - `effective-date-architecture.md` — session-based effective current date implementation.
  - `decimal-precision-standards.md` — financial precision requirements and decimal handling standards.
  - `bond-amortization-domain.md` — bond amortization business logic and data models.
  - `external-api-patterns.md` — external API integration patterns and best practices.
  - `transaction-processing-patterns.md` — unified transaction processing architecture and DRY implementation.

- Tasks/
  - `backlog.md` — initial backlog items derived from the interview.
  - `roadmap.md` — suggested milestones for short/medium term work.

**Usage guidance:**
- For authoring or changing financial computation code, consult `Steerings/Calculation Conventions.md` and `Tech details/NAV Function and FX Flow.md` first; any change touching protected logic must follow `Rules for AI Coding Agent.md`.
- For onboarding new developers: start with `Product Overview/Portfolio NAV.md`, then `Tech details/architecture.md` and `Steerings/dev_conventions.md`.
- For AI agents: always include `Rules for AI Coding Agent.md` in the prompt context; include canonical calculation files when the task relates to NAV/FX.

---
