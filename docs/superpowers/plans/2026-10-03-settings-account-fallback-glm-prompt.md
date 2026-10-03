# GLM prompt — settings account preservation

Fetch the latest `origin/codex/frontend-modernization`, including merged PR #54 and these handoff documents. Read `AGENTS.md` and `docs/superpowers/plans/2026-10-03-settings-account-fallback-handoff.md`.

Implement this bounded fix on `codex/settings-account-selection-preservation` in a dedicated worktree. Do not switch, reset, stash or commit in the D5 executor's checkout.

Profile Settings currently replaces a saved account missing from its choices with All accounts, so saving unrelated preferences can silently change account scope. Preserve the saved identity separately from the display model, show a safe label and explicit availability message, and block both save operations until a real available selection is resolved. Keep exact input-value coverage from the PR #54 lesson; no raw objects, fake options, implicit replacements or repair requests. Preserve the existing preferences endpoint/context queue and all other form edits.

Follow the plan's RED/GREEN regressions, rendered scenarios and committed-head gates. Keep D5 presentation changes, backend and financial logic out of scope. Update evidence/tracker, push and open a draft PR into `codex/frontend-modernization`; stop for review. Report tested SHA/directory, actual exits, limitations and any D5 integration overlap. Do not merge or deploy.
