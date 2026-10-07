# GLM-5.3 prompt — D8

Pull the latest `origin/codex/frontend-modernization` (PR #60 merged at `9d369af7`; include the newer D8 handoff). Read AGENTS.md, the tracker and `docs/superpowers/plans/2026-10-07-final-qa-d8-handoff.md` plus its linked specification.

Execute D8 tasks 0–3 in a dedicated worktree on `codex/frontend-final-qa-d8`. Audit every route and critical workflow on a genuinely unflagged default-on build; the standard all-false browser matrix is rollback coverage, not default-on acceptance. Preserve it and add the explicit default-on matrix. Inspect real screenshots, keyboard/focus, dense tables, mobile/native 200% zoom, charts, imports, brokers and settings. Fix bounded defects with meaningful RED-first regressions, preserve exact financial values and merged lifecycle fixes, and record actual exit codes on committed code.

Update evidence and tracker, push and open a draft PR into `codex/frontend-modernization`, then stop for review. Do not remove Chart.js, change backend/financial logic, merge or deploy. C5b still requires an owner-accepted release validation cycle and separate removal approval; local QA must not claim that cycle occurred. Screen-reader work remains out of scope. Report any failed acceptance honestly.
