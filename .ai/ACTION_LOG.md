# ACTION LOG

- 2026-07-08 (wt/5a39ff05 lineage): Phase 45 spec v1.0 → v1.2 + plan v1.0 → v1.1 frozen; CR-1/2/3 applied; M6.1.A landed (MissionActor + 8-event taxonomy + state machine).
- 2026-07-09 (wt/5a39ff05 lineage): CR-4 approved (D-4 runtime idempotency + D-5 versioned envelope); M6.4.A + M6.4.B.1 lifted in 2405abf + e2cd9fc; M6.4.B.1 envelope codec added.
- 2026-07-10 17:18 NPT (`phase45/transport` commit `1401b81`): M6.4.A transport layer + worker registry + distributed router scaffold lifted from `wt/5a39ff05` to `phase45/transport` (18 files, code-only, no spec/plan/CR/alembic).
- 2026-07-10–11: 0.9.4 shipped to `main` at `ce8ebdb` (CR-002/003/004/005 merged).
- 2026-07-11 16:55 NPT (`main` commit `31e6897`): 0.9.5-prep housekeeping — refresh .ai/ state, fix AGENTS.md §12 + dashboard drift, prune orphan worktrees.
- 2026-07-11 17:35 NPT (`phase45/transport` commit `337ca64`): M6.4.B.2 — real `RemoteTransport` over Redis pub/sub + SETNX leases (56 new tests, 1985 passed / 2 skipped / 0 failed).
- 2026-07-11 17:50 NPT (`phase45/transport` commit `7e53c69`): M6.4 governance retrofit — bring spec v1.2 / plan v1.1 / CR-4 / state machine from `wt/5a39ff05` to `phase45/transport` (resolves AGENTS.md §6.1 STOP — code that pointed to a missing spec is now authorized). 5 files / +1496 lines / no code/test changes.

**Open follow-up (architect decision pending):**
- M6.4.B code-completion gap: DistributedRouter.REMOTE_PREFERRED stubbed; WorkerRegistry missing `mark_task_started`/`mark_task_completed`; `tests/test_distributed_router_remote_preferred.py` missing. Per `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3 M6.4.B these are plan-listed deliverables, not a spec amendment — no CR-6 required, but architect should call priority before further M6.4 work.
