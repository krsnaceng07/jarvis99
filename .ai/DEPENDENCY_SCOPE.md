# DEPENDENCY SCOPE

**Current Impact Radius (`phase45/transport` at `7e53c69`):**

M6.4.B.2 commit `337ca64` (RemoteTransport):
- `core/mission/transports/redis.py` affects -> `core/mission/distributed_router.py` (consumes via Protocol), `api/routes/distributed_pool.py` (no direct dep), `tests/test_remote_transport_exhaustive.py`
- Dev deps: `fakeredis>=2.20`, `lupa>=2.0` (fakeredis Lua scripts)

M6.4.A commit `1401b81` (transport + worker registry + router scaffold):
- `core/mission/mission_transport.py` affects -> `core/mission/transports/*`, `core/mission/distributed_router.py`
- `core/mission/transports/local.py` affects -> `core/mission/transports/__init__.py`
- `core/mission/transports/envelope.py` affects -> `core/mission/transports/redis.py` (de)serialization
- `core/mission/worker_registry.py` affects -> `core/runtime/mission_models.py` (ORM), `core/mission/distributed_router.py`
- `core/mission/worker_process.py` affects -> `core/mission/worker_registry.py`
- `core/mission/distributed_router.py` affects -> `core/mission/worker_registry.py` (consumes), `api/routes/distributed_pool.py`
- `api/routes/distributed_pool.py` affects -> `api/dependencies.py`, `api/main.py`
- `core/runtime/mission_models.py` additive only (D-3 unique index on `task_routing_log`)

Governance retrofit commit `7e53c69`:
- 5 docs files only. No code impact.

**Downstream (NOT touched, additive only):**
- `core/runtime/mission.py` (FROZEN Phase 34) — MissionManager unchanged
- `core/runtime/mission_models.py:34` MissionModel, `:58` MissionCheckpointModel — additive columns only (per CR-3.4 / CR-3.5)
- `core/skills/capability_registry.py` (FROZEN Phase 41) — worker `capabilities["skills"]` is opaque to it
- `core/observability/*` (FROZEN Phase 27) — M6.4 reuses EventBusInterface; no parallel event taxonomy
