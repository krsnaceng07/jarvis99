# CHANGESET

**Changed Files (in `phase45/transport` lineage since `main`):**

M6.4 governance retrofit (commit `7e53c69`):
- docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md (NEW — v1.2 FROZEN-amended, 794 lines)
- docs/108_PHASE_45_IMPLEMENTATION_PLAN.md (NEW — v1.1 FROZEN, 375 lines)
- docs/cr/CR-4_phase45_d4_d5_idempotency_envelope.md (NEW — APPROVED 2026-07-09, 133 lines)
- docs/cr/README.md (NEW — CR index, CR-4 status row fixed DRAFT → APPROVED)
- docs/mission_state_machine.md (NEW — FROZEN at M6.1.A, 159 lines)

M6.4.B.2 (commit `337ca64`):
- core/mission/transports/redis.py (REPLACED stub with real RemoteTransport)
- tests/test_remote_transport_exhaustive.py (NEW — 56 tests)
- pyproject.toml (fakeredis>=2.20 + lupa>=2.0 dev deps)

M6.4.A + M6.4.B.1 scaffold (commit `1401b81`, lifted from `wt/5a39ff05` 2405abf + e2cd9fc):
- core/mission/mission_transport.py (NEW — MissionTransport Protocol + 3 exceptions)
- core/mission/transports/{__init__,local,envelope}.py (NEW — LocalTransport + EnvelopeV1 codec)
- core/mission/worker_registry.py (NEW — DB-touching helper)
- core/mission/worker_process.py (NEW — CLI entry point)
- core/mission/distributed_router.py (NEW — leader-side routing)
- api/routes/distributed_pool.py (NEW — 5 endpoints)
- api/dependencies.py (MODIFIED — providers)
- api/main.py (MODIFIED — router registration)
- core/runtime/mission_models.py (MODIFIED — WorkerRegistryModel + TaskRoutingLogModel)
- .gitignore (MODIFIED — 2 test DB patterns)
- 6 new test files: test_transport_envelope / test_local_transport_exhaustive / test_worker_registry / test_distributed_router / test_distributed_pool_route / test_worker_process

**Reason:**
- M6.4 = Goal #6 (Persistent Autonomous Runtime) sub-goal Distributed Execution. The 1401b81 lift was code-only by design (commit message); the spec/plan/CR/state machine that the code headers reference were never migrated with the code. The 7e53c69 retrofit closes that drift and re-authorizes the on-disk code per AGENTS.md §6.1.

**Frozen modules touched:** NONE
**Spec amendments:** NONE (retrofit only brings existing FROZEN artifacts onto the branch)
**New CRs:** NONE (CR-4 already approved on `wt/5a39ff05` lineage; just brought onto this branch)
