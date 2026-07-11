# NEXT ACTION

**Step-by-step (M6.4.B code-completion, if architect calls go):**

1. Read `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3 M6.4.B deliverable list + A-1..A-5 invariants.
2. Read `core/mission/distributed_router.py` end-to-end. Identify the exact spot where `REMOTE_PREFERRED` raises `NotImplementedError` (route() early-return path).
3. Implement REMOTE_PREFERRED in `route()`: build a `TransportEnvelope` (msgpack+zstd via `EnvelopeV1`), call `self._transport.publish(<worker_channel>, envelope_bytes)`. Append a routing row with `decision_reason = ROUTED_REMOTE` (new constant).
4. Implement `mark_task_started` + `mark_task_completed` in `core/mission/worker_registry.py`: idempotent on `(worker_id, wave_run_id)`. `active_tasks` adjusts by ±1 with a uniqueness guard.
5. Add `tests/test_distributed_router_remote_preferred.py` (≥ 10 tests, fakeredis-backed). Cover: cross-client publish/subscribe, envelope round-trip, lease acquire/renew/release, dedup via D-3, REMOTE_PREFERRED raises if no transport wired.
6. Run mini quality gate: `ruff format --check core/mission/{distributed_router,worker_registry}.py tests/test_distributed_router_remote_preferred.py`, `ruff check` (same), `mypy --strict` (same), `pytest tests/test_distributed_router_remote_preferred.py tests/test_distributed_router.py tests/test_worker_registry.py tests/test_remote_transport_exhaustive.py -v`.
7. Write `docs/reports/PHASE45_M6_4_B_REPORT.md` per AGENTS.md §10 format.
8. Commit. Surface to architect for review. STOP.

**Step-by-step (alternative — if architect pivots to M6.4.C stretch, M6.1/2/3/5, or main housekeeping):**

- Wait for architect decision. Do not start new sub-milestone work without explicit go.
