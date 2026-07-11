# IMPACT GRAPH

*Rule: Use this to determine exactly which tests to rerun based on file changes.*

**If `core/mission/mission_transport.py` changes:**
- Need to rerun: ALL M6.4 tests (transport envelope, local, redis, router, registry, worker_process, distributed_pool)
- Need NOT rerun: Mission runtime tests (Phase 34 frozen)

**If `core/mission/transports/local.py` changes:**
- Need to rerun: `tests/test_local_transport_exhaustive.py`, `tests/test_transport_envelope.py` (in-process envelope round-trip)
- Need NOT rerun: Redis-specific tests, registry tests, router tests

**If `core/mission/transports/redis.py` changes:**
- Need to rerun: `tests/test_remote_transport_exhaustive.py` (fakeredis), `tests/test_transport_envelope.py` (de)serialization
- Need NOT rerun: Local-only tests, registry tests

**If `core/mission/transports/envelope.py` changes:**
- Need to rerun: `tests/test_transport_envelope.py` (all 39), `tests/test_remote_transport_exhaustive.py` (envelope round-trip)
- Need NOT rerun: Registry tests, worker_process tests

**If `core/mission/worker_registry.py` changes:**
- Need to rerun: `tests/test_worker_registry.py`, `tests/test_distributed_router.py` (router uses registry), `tests/test_distributed_pool_route.py` (REST uses registry via router)
- Need NOT rerun: Transport tests, envelope tests, worker_process tests

**If `core/mission/worker_process.py` changes:**
- Need to rerun: `tests/test_worker_process.py`
- Need NOT rerun: Router tests, transport tests

**If `core/mission/distributed_router.py` changes:**
- Need to rerun: `tests/test_distributed_router.py`, `tests/test_distributed_pool_route.py` (REST routes), `tests/test_worker_registry.py` (router ↔ registry interaction)
- Need NOT rerun: Transport-impl tests (router speaks to the Protocol, not concrete impls)

**If `api/routes/distributed_pool.py` changes:**
- Need to rerun: `tests/test_distributed_pool_route.py`
- Need NOT rerun: Core-mission tests (routes depend on the router via DI)

**If `core/runtime/mission_models.py` changes (additive columns only):**
- Need to rerun: ALL M6.4 tests + Phase 34 mission tests (regression)
- Need NOT rerun: Skills, observability, vault tests

**If any `docs/107`, `docs/108`, `docs/mission_state_machine.md`, or `docs/cr/CR-4` changes:**
- Re-read the affected doc; verify the code's docstring headers + invariants still match. No tests to rerun (docs are not executable).

**If `pyproject.toml` (dev deps) changes:**
- Re-run the full M6.4 test set (fakeredis + lupa versions can change Lua-script semantics).
