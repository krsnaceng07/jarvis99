# CHECKPOINT

**Completed (since last .ai/ state refresh on 2026-07-11):**

- ✅ 0.9.4 release SHIPPED to `origin/main` at `ce8ebdb` (3 commits since the prior HEAD `8455b8b`):
  - `3d7383b` — polish(skills): address 7 CR-002 static analysis findings (CR-004 path A)
  - `506e275` — fix(persistence): use SAVEPOINT for race-recovery in save_task (CR-005)
  - `ce8ebdb` — docs(0.9.4): close 0.9.4 bookkeeping — CR-005 approved, dashboard refreshed
- ✅ All 5 CRs (CR-001 through CR-005) merged, approved where required, and on `origin/main`
- ✅ Pre-existing flakes resolved (`test_concurrent_save_task_no_pk_violation` by CR-005; `test_vault_manager_encryption_decryption` was transient and now passes)
- ✅ Test count: 1761 passed, 2 skipped, 0 failed on `ce8ebdb`
- ✅ `.ai/` state files refreshed to reflect post-0.9.4 reality (this commit + the prior 0.9.4 ship)
- ✅ `JARVIS_EXECUTIVE_DASHBOARD.md` updated to show 0.9.4 as SHIPPED
- ✅ `AGENTS.md` §12 updated to include Phase 42/43/44 in the phase status board (per §14 modification policy)

**Pending (architect decision):**

- ⏳ **0.9.4 tag** — cut `v0.9.4-...` at `ce8ebdb` or fold into 0.9.4 natural boundary (recommended: defer)
- ⏳ **Phase 45 ramp-up** — pre-work on `wt/5a39ff05` (TransportEnvelope) and `wt/5432577e` (auth admin recovery) needs architect decision (cherry-pick, merge, or start fresh)
- ⏳ **Housekeeping backlog** — Unit-of-Work refactor for `DbSwarmPersistence`, `SELECT ... FOR UPDATE` upgrade (Postgres-specific, unfreezes Phase 26), capability-matrix probe expansion — all candidates for a separate "0.9.5 cleanup" cycle

**Not Started:**

- (none — the 0.9.4 cycle is complete; the next cycle is the architect's choice)
