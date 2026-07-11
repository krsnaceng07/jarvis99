# CURRENT TASK

**Goal:** Phase 45 / M6.4 (Distributed Execution) on `phase45/transport`. Continue M6.4 work in spec'd order; address the M6.4.B code-completion gap (REMOTE_PREFERRED + WorkerRegistry task tracking) per `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3 M6.4.B deliverable list.

**Files Allowed (M6.4.B code-completion, additive only):**
- core/mission/distributed_router.py (MODIFY additive — REMOTE_PREFERRED behavior + idempotent route() + idempotent active_tasks)
- core/mission/worker_registry.py (MODIFY additive — mark_task_started / mark_task_completed keyed on wave_run_id)
- core/mission/transports/__init__.py (MODIFY additive — re-export envelope symbols if needed)
- pyproject.toml (no new deps; fakeredis + lupa already pinned)
- tests/test_distributed_router_remote_preferred.py (NEW ≥ 10 tests, per plan §3 M6.4.B)
- docs/reports/PHASE45_M6_4_B_REPORT.md (NEW — milestone report per AGENTS.md §10)

**Files Forbidden:**
- Frozen interface modules (see `docs/60_MASTER_INDEX.md` and the FREEZE_LEDGER)
- `core/runtime/mission.py` and `core/runtime/mission_models.py` (FROZEN Phase 34 — additive columns only, never rename)
- `docs/107_*.md` / `docs/108_*.md` (FROZEN spec/plan)
- Anything that bypasses `DistributedRouter → MissionTransport Protocol` (A-1 invariant)
- Anything that requires a fresh spec/plan amendment (would be CR-6; architect's call)

**Success Criteria (M6.4.B closure):**
- `DistributedRouter.route()` with `policy=REMOTE_PREFERRED` actually publishes the task to the chosen worker via `MissionTransport.publish`, no longer raises `NotImplementedError`.
- `WorkerRegistry.mark_task_started(wave_run_id, ...)` / `mark_task_completed(wave_run_id, ...)` exist; idempotent on duplicate keys.
- `active_tasks` accounting is idempotent under concurrent calls.
- ≥ 10 new tests in `tests/test_distributed_router_remote_preferred.py`.
- All 1985 existing tests still pass; zero regression.
- ruff format + ruff check + mypy --strict clean on touched files.
- `docs/reports/PHASE45_M6_4_B_REPORT.md` per AGENTS.md §10 format.

**Status:** Awaiting architect go/no-go on M6.4.B code-completion. Last completed: governance retrofit at `7e53c69`.
