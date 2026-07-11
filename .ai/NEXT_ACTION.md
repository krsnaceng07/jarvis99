# NEXT ACTION

**Step-by-step (when work resumes):**

1. **Confirm next move with the architect** — the 0.9.4 release is SHIPPED to `origin/main` at `ce8ebdb`; the next move is the architect's choice (see `.ai/CURRENT_TASK.md` for the three options).
2. **If cutting the 0.9.4 tag:** verify the tag strategy (recommended: `v0.9.4-...` at `ce8ebdb`; alternative: fold into 0.9.4 proper at its natural boundary), then `git tag -a v0.9.4-... ce8ebdb -m "..."; git push origin v0.9.4-...` and write a brief RELEASE_0.9.4 notes commit.
3. **If starting Phase 45:** first, audit branches `wt/5a39ff05` and `wt/5432577e` for value to cherry-pick vs. start-fresh; second, update `.ai/PROJECT_STATE.md` to set `Current Status: 🟡 IN PROGRESS (Phase 45)`; third, follow the standard spec → plan → implement → freeze lifecycle per `AGENTS.md` §5.
4. **If doing housekeeping:** update the appropriate CR doc, get architect sign-off, then implement + test + freeze per `AGENTS.md` §5.

**Hard rule:** do NOT start a new code task without first confirming the architect's choice on the next move. The previous carry-forward sessions demonstrated the value of explicit architect sign-off before pushing or tagging.
