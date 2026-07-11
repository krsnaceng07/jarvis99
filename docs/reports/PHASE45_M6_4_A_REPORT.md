# PHASE45 M6.4.A ΓÇö Distributed Execution Scaffold Report

**Date:** 2026-07-09 (Asia/Katmandu)
**Architect authority:** Mavis (delegated, per user "everything is your
decision" mandate 2026-07-09)
**Gate status:** M6.4.A SCAFFOLD COMPLETE ΓåÆ AWAITING ARCHITECT APPROVAL
**Spec authority:** `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md`
**Plan authority:** `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` ┬º3 M6.4.A

---

## Summary

M6.4.A landed the leader-side distributed execution surface that the
M6.3.A/B stack has been building toward:

* `MissionTransport` Protocol ΓÇö transport-agnostic surface for
  cross-process task routing (no concrete Redis/socket/gRPC class is
  imported by the router).
* `LocalTransport` ΓÇö in-process implementation with per-channel
  per-subscriber FIFO queues, in-memory leases with TTL (token =
  uuid4, constant-time `hmac.compare_digest` for renew/release).
* `RemoteTransport` stub ΓÇö raises `NotImplementedError` on `__init__`
  so accidental wiring in M6.4.A fails loud; real Redis pub/sub +
  SETNX variant lands in M6.4.B.
* `WorkerRegistry` ΓÇö DB-touching helper for `worker_registry`
  (D-1 liveness: 15s grace sweep, idempotent register, OFFLINE
  promotion, status auto-promote on heartbeat).
* `WorkerProcess` CLI ΓÇö `python -m core.mission.worker_process`
  registers + heartbeats every 10s + shuts down on SIGTERM. CLI is
  security-aligned (no secrets on cmdline ΓÇö env-vars only).
* `DistributedRouter` ΓÇö leader-side routing decision maker. Uses
  `WorkerRegistry` as the single source of truth (A-1 architect
  invariant: speaks only to `MissionTransport` Protocol + `WorkerRegistry`,
  never imports `LocalTransport` / `RemoteTransport` directly).
* `task_routing_log` table ΓÇö D-2 append-only audit + D-3 dedup on
  `(wave_run_id, chosen_worker_id)`. Co-located in
  `0049_worker_registry.py` per CR-2.
* REST endpoints (per spec ┬º6):
  * `GET    /api/v1/distributed/workers`
  * `POST   /api/v1/distributed/workers/{id}/heartbeat`
  * `POST   /api/v1/distributed/tasks/route`
  * `GET    /api/v1/distributed/routing?wave_run_id=...`
  * `POST   /api/v1/distributed/routing/{route_id}/complete`

**No network code in M6.4.A.** CI default is `LocalTransport` end-to-end.
M6.4.B's `RemoteTransport` is the next gate after M6.4.A architect
approval.

---

## Files Modified

### NEW
| File | Responsibility |
|------|----------------|
| `core/mission/mission_transport.py` | `MissionTransport` Protocol + `TransportError` / `TransportClosedError` / `LeaseLostError` exceptions. |
| `core/mission/transports/__init__.py` | Re-export `MissionTransport` + `LocalTransport` + `RemoteTransport`. |
| `core/mission/transports/local.py` | `LocalTransport` in-process implementation. Per-channel per-subscriber FIFO, in-memory leases with TTL, constant-time token compare. |
| `core/mission/transports/redis.py` | `RemoteTransport` stub (M6.4.B scope; raises `NotImplementedError` on `__init__`). |
| `core/mission/worker_registry.py` | `WorkerRegistry` DB-touching helper. D-1 liveness sweep + idempotent register. |
| `core/mission/worker_process.py` | `WorkerProcess` CLI entry point + `WorkerProcessConfig` + `build_arg_parser` + `main`. |
| `core/mission/distributed_router.py` | `DistributedRouter` leader-side routing decision maker. `RoutingPolicy` enum (`LOCAL_ONLY`/`REMOTE_PREFERRED`/`ANY`). D-2 audit + D-3 dedup. |
| `api/routes/distributed_pool.py` | REST endpoints for the distributed pool. Auth = `platform.admin`. |
| `alembic/versions/0049_worker_registry.py` | Co-located `worker_registry` + `task_routing_log` migration. Down-revision `0048_mission_dead_letters`. |
| `tests/test_local_transport_exhaustive.py` | 45 tests: boundary, ordering, idempotency, leases (acquire / renew / release), payload serialization edge cases, close semantics, async context manager. |
| `tests/test_distributed_router.py` | 21 tests: happy path, capability filter, load-aware routing, stale-worker drops, REMOTE_PREFERRED 501, D-3 dedup, D-2 audit, round-trip read+complete, A-1 invariant (no concrete transport import). |
| `tests/test_worker_registry.py` | 22 tests: register / heartbeat / list_active sweep / mark_offline / idempotent re-register / status auto-promote / null last_heartbeat exclusion. |
| `tests/test_worker_process.py` | 28 tests: CLI parsing + env-var precedence + lifecycle (start, stop, run_once, run, signal handler, heartbeat loop). |
| `tests/test_distributed_pool_route.py` | 13 tests: 200 / 404 / 422 / 501 status mapping for the REST endpoints. |

### MODIFIED (additive only ΓÇö ADR-45-01)
| File | Change |
|------|--------|
| `core/runtime/mission_models.py` | Added `WorkerRegistryModel` + `TaskRoutingLogModel` (additive classes ΓÇö no existing class touched). `UniqueConstraint("wave_run_id", "chosen_worker_id")` declared on `TaskRoutingLogModel` so `Base.metadata.create_all()` (used by tests) creates the same D-3 unique index that `alembic/versions/0049_worker_registry.py` creates in production. |
| `api/dependencies.py` | Added `get_distributed_router()` provider (additive ΓÇö never touches existing providers). Lazy imports avoid circular dependency. |
| `api/main.py` | Registered `distributed_pool.router` (additive ΓÇö never touches existing routers). |
| `docs/diagrams/dependency_graph.dot` | Regenerated by DGV after M6.4.A. |
| `.gitignore` | Added `test_worker_proc_*.db`, `test_router_*.db` so per-test SQLite artifacts do not pollute the working tree. |

---

## Mini Quality Gate

| Gate | Tool | Result |
|------|------|--------|
| Format | `ruff format --check` (12 M6.4.A files) | Γ£à all clean |
| Lint | `ruff check` (12 M6.4.A files) | Γ£à 0 errors |
| Types | `mypy --strict` (7 core + 1 model + 1 route = 9 files) | Γ£à all clean |
| Tests | `pytest tests/test_worker_registry.py tests/test_worker_process.py tests/test_local_transport_exhaustive.py tests/test_distributed_router.py tests/test_distributed_pool_route.py` | Γ£à 129/129 passed |
| Coverage | `pytest --cov` (M6.4.A core modules) | Γ£à 95% / 95% / 95% / 96% (router / transport / worker_process / worker_registry). Targets: ΓëÑ 90% on transport, ΓëÑ 85% on router/worker_process/worker_registry. **All exceeded.** |
| Architecture | `python scripts/architecture_linter.py` | Γ£à no NEW violations introduced by M6.4.A files. (Pre-existing violations in `mission_types.py` are unchanged from M6.3.B gate.) |
| DGV | `python -m scripts.dgv` | Γ£à no NEW violations introduced by M6.4.A modules. |
| Regression | `pytest tests/` (full suite) | Γ£à 1882 baseline + 129 M6.4.A = **2011 passed** (zero regression). |

---

## Test count roll-up

| Suite | Count |
|-------|-------|
| Baseline (post-M6.3.B) | 1882 |
| M6.4.A additions | 129 |
| **Total** | **2011** |

M6.4.A test breakdown:
- `test_worker_registry.py`: 22
- `test_worker_process.py`: 28
- `test_local_transport_exhaustive.py`: 45
- `test_distributed_router.py`: 21
- `test_distributed_pool_route.py`: 13

---

## Invariants verified

| # | Invariant | Verified by |
|---|-----------|-------------|
| A-1 | `DistributedRouter` speaks only to `MissionTransport` Protocol + `WorkerRegistry`; never imports `LocalTransport` / `RemoteTransport` directly. | `tests/test_distributed_router.py::TestArchitectInvariant::test_router_does_not_import_concrete_transport` (architect-recommendation 2026-07-08). |
| D-1 | Worker grace = 15s. Stale workers sweep to OFFLINE before `list_active` returns. | `tests/test_worker_registry.py::TestListActiveStaleSweep` + spec ┬º4.4 cross-check. |
| D-2 | `task_routing_log` is append-only ΓÇö no update / delete methods on the model; the helper only inserts. | `tests/test_distributed_router.py::TestAppendOnlyAudit::test_routing_log_has_one_row_per_decision` + code review. |
| D-3 | One row per `(wave_run_id, chosen_worker_id)` pair enforced via the unique index + `INSERT ... ON CONFLICT DO NOTHING` (Postgres) / `IntegrityError` catch (SQLite). | `tests/test_distributed_router.py::TestIdempotencyD3` + `TestAppendOnlyAudit::test_dedup_hit_appends_no_new_row`. |
| G-6 | Legacy obliviousness ΓÇö router never requires legacy mission columns. `last_heartbeat = NULL` is correctly excluded by `WorkerRegistry.list_active`. | `tests/test_worker_registry.py::TestNullLastHeartbeat` + router integration test. |
| No network code | `LocalTransport` has no `redis` / socket / async client imports. `RemoteTransport` is a `NotImplementedError` stub. | Static analysis + `ruff check` + explicit `tests/test_distributed_router.py::TestArchitectInvariant::test_no_redis_imported`. |

---

## Layer direction audit (architecture freeze compliance)

| Edge | Direction | Status |
|------|-----------|--------|
| `api/routes/distributed_pool.py` ΓåÆ `core/mission/distributed_router.py` | `api/ ΓåÆ core/` | Γ£à |
| `api/routes/distributed_pool.py` ΓåÆ `core/mission/worker_registry.py` | `api/ ΓåÆ core/` | Γ£à |
| `api/routes/distributed_pool.py` ΓåÆ `core/runtime/mission_models.py` | `api/ ΓåÆ core/` | Γ£à |
| `api/dependencies.py` ΓåÆ `core/mission/distributed_router.py` | `api/ ΓåÆ core/` | Γ£à |
| `core/mission/distributed_router.py` ΓåÆ `core/mission/worker_registry.py` | `core/ ΓåÆ core/` | Γ£à |
| `core/mission/distributed_router.py` ΓåÆ `core/runtime/mission_models.py` | `core/ ΓåÆ core/` | Γ£à |
| `core/mission/worker_registry.py` ΓåÆ `core/runtime/mission_models.py` | `core/ ΓåÆ core/` | Γ£à |
| `core/mission/worker_process.py` ΓåÆ `core/mission/worker_registry.py` | `core/ ΓåÆ core/` | Γ£à |
| `core/mission/transports/__init__.py` ΓåÆ `core/mission/transports/local.py` | `core/ ΓåÆ core/` | Γ£à |
| `core/mission/transports/__init__.py` ΓåÆ `core/mission/transports/redis.py` | `core/ ΓåÆ core/` | Γ£à |

`DistributedRouter` does NOT import `LocalTransport` or `RemoteTransport`
(anywhere). Verified by `tests/test_distributed_router.py::TestArchitectInvariant`.

---

## Open architect decisions (carry-forward into M6.4.B)

None blocking. Three forward-looking CRs queued from M6.3.B gate
(CR-1, CR-2, CR-3) are documentation-only and do not block M6.4.B
implementation.

---

## Next Milestone (gated on M6.4.A architect approval)

- **M6.4.B** ΓÇö `RemoteTransport` (Redis pub/sub) +
  `DistributedRouter`-driven cross-node routing +
  `REMOTE_PREFERRED` policy behavior. Adds `redis>=5.0` to
  `pyproject.toml`. The transport-stub currently raises
  `NotImplementedError` ΓÇö M6.4.B ships the real Redis-backed
  implementation. Migration is co-located with the M6.4.A worker
  registry migration per CR-2; M6.4.B's schema additions (if any)
  land in `0050_*.py` or later.

---

## Files Added (this milestone)

```
core/mission/mission_transport.py                  (NEW, 177 lines)
core/mission/transports/__init__.py                (NEW,  42 lines)
core/mission/transports/local.py                   (NEW, 452 lines)
core/mission/transports/redis.py                   (NEW,  87 lines)
core/mission/worker_registry.py                    (NEW, 548 lines)
core/mission/worker_process.py                     (NEW, 690 lines)
core/mission/distributed_router.py                 (NEW, 636 lines)
api/routes/distributed_pool.py                     (NEW, 329 lines)
alembic/versions/0049_worker_registry.py           (NEW, 208 lines)
tests/test_local_transport_exhaustive.py           (NEW,  45 tests)
tests/test_distributed_router.py                   (NEW,  21 tests)
tests/test_worker_registry.py                      (NEW,  22 tests)
tests/test_worker_process.py                       (NEW,  28 tests)
tests/test_distributed_pool_route.py               (NEW,  13 tests)
docs/reports/PHASE45_M6_4_A_REPORT.md              (NEW ΓÇö this file)
```

---

**Awaiting architect approval before proceeding to M6.4.B. Not
proceeding.**
