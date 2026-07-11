# HANDOFF NOTE

**Current Branch:** `phase45/transport` (commit `7e53c69` HEAD)
**Current Milestone:** Phase 45 / M6.4 (Distributed Execution) — M6.4.A + M6.4.B.1 + M6.4.B.2 landed; M6.4.B code-completion gap OPEN (architect decision pending)

**Finished on this branch (in chronological commit order):**
- M6.4.A: MissionTransport Protocol + LocalTransport + WorkerRegistry + DistributedRouter scaffold + WorkerProcess CLI + `/api/v1/distributed/*` REST routes. 168 new tests.
- M6.4.B.1: TransportEnvelope Protocol + EnvelopeV1 codec (D-5 wire-format; msgpack+zstd forward-compat).
- M6.4.B.2: real RemoteTransport over Redis pub/sub + SETNX leases. 56 new tests.
- M6.4 governance retrofit: spec v1.2 / plan v1.1 / CR-4 / state machine brought from `wt/5a39ff05`. 5 files, no code/test changes.

**Finished on `main` (stable):**
- 0.9.4 SHIPPED at `ce8ebdb` (CR-002 + CR-003 + CR-004 + CR-005 all merged)
- 0.9.5-prep housekeeping at `31e6897`

**Open / Pending (architect decision required before further M6.4 work):**
- **M6.4.B code-completion gap** — `DistributedRouter.REMOTE_PREFERRED` is stubbed (raises `NotImplementedError`); `WorkerRegistry` lacks `mark_task_started` / `mark_task_completed`; `tests/test_distributed_router_remote_preferred.py` does not exist. These are plan-listed deliverables in `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3 M6.4.B, NOT a spec amendment — no CR-6 required, but architect should call the priority.
- **M6.4.C (stretch)** — leader election + horizontal scaling tests. Per plan §3 status: STRETCH, deferrable if M6.4.B consumes the time budget.
- **Other Phase 45 sub-milestones** — M6.1.A/B (MissionActor rehydration), M6.2.A/B (Scheduler), M6.3.A/B (Crash recovery), M6.5.A/B (Observability) — separate branches when picked up. M6.1.A is on `wt/5a39ff05` lineage; the others are unstarted.

**Next Agent Instructions:**
- Respect AGENTS.md §6.1 (specification-first resolution). No code without a spec.
- Respect AGENTS.md §6 STOP conditions. The on-disk M6.4 code is now authorized (commit `7e53c69` brought the spec/plan/CR onto the branch); any new code MUST reference an existing FROZEN spec.
- For M6.4.B code-completion: work in `core/mission/distributed_router.py` (additive REMOTE_PREFERRED) and `core/mission/worker_registry.py` (additive mark_task_started/completed). No new dependencies. ≥ 10 new tests in `tests/test_distributed_router_remote_preferred.py`. mypy --strict + ruff clean. Milestone report per AGENTS.md §10.
- For M6.4.C: defer until architect calls priority. STRETCH per plan.
- For non-M6.4 Phase 45 work (M6.1, M6.2, M6.3, M6.5): open a new branch off `wt/5a39ff05` lineage (where M6.1.A already exists) — do NOT branch off `phase45/transport` to keep the M6.4 work stream clean.

**Authority:** per AGENTS.md §1, the architect (User) is Rank 1 for scope decisions; AGENTS.md is Rank 2; spec/plan are Rank 4-5; code is Rank 6.
