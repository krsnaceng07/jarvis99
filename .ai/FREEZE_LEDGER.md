# FREEZE LEDGER

*Rule: Build skill MUST check this before editing. Frozen files/interfaces CANNOT be touched.*

**Workflow State:**
- **AGENTS.md v1.0: FROZEN** (2026-07-29 — post-Phase 16 freeze)
- **Phase 16 (AGENTS.md):** FROZEN 2026-06-29 at 193 tests

**Approved Milestones (post-Phase 41, as of 2026-07-11):**
- Phase 42 (Identity Engine) — FROZEN 2026-07-06 at 1259 tests
- Phase 43 (Goal Engine) — FROZEN 2026-07-06 at 1259 tests (per AGENTS.md §12 row 43)
- Phase 44 (Mission Scheduler) — FROZEN 2026-07-06 at 1259 tests (per AGENTS.md §12 row 44)
- Phase 45 (Persistent Autonomous Runtime) — IN DEVELOPMENT on `phase45/transport` branch
  - Spec: `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` v1.2 FROZEN-amended (2026-07-08, CR-1/2/3/4 applied)
  - Plan: `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` v1.1 FROZEN (2026-07-08, A-1..A-4 invariants)
  - CR-4: `docs/cr/CR-4_phase45_d4_d5_idempotency_envelope.md` APPROVED 2026-07-09

**Phase 45 / M6.4 sub-milestones (per `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3):**
- M6.1.A — MissionActor Foundation (NOT on this branch; landed on `wt/5a39ff05` lineage)
- M6.4.A — MissionTransport Protocol + LocalTransport + WorkerProcess — ✅ LANDED at `1401b81` (commit on `phase45/transport`); REPORT lifted at `eb54911`; **architect-approval recorded in report (delegated mandate 2026-07-09); ready for freeze on merge to main**
- M6.4.B — DistributedRouter + RemoteTransport (Redis) + Envelope (D-5) + Runtime Idempotency (D-4) — ✅ COMPLETE on `phase45/transport`:
  - B.1 envelope codec: `1401b81`
  - B.2 real Redis transport: `337ca64`
  - Code-completion (REMOTE_PREFERRED + task tracking + 23 tests): `0e1b593`
  - Report: `docs/reports/PHASE45_M6_4_B_REPORT.md` (156 lines)
  - **Gate status: ✅ PASS** — 2008 passed / 2 skipped / 0 failed (+23 net new vs 1985 pre-M6.4.B); ruff + mypy clean; A-1 AST-verified
- M6.4.C — Leader Election (stretch) + Horizontal Scaling Tests — ✅ COMPLETE on `phase45/transport`:
  - LeaderElection state machine + LeaderRole enum: `fff4daa`
  - 33 tests in `tests/test_leader_election.py` (412% of plan §3 floor of ≥ 8)
  - Report: `docs/reports/PHASE45_M6_4_C_REPORT.md` (188 lines)
  - **Gate status: ✅ PASS** — 2041 passed / 2 skipped / 0 failed (+33 net new vs 2008 pre-M6.4.C); ruff + mypy clean; A-1 verified

**Frozen Files (Phase 45 contracts — DO NOT MODIFY):**
- `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` (v1.2 FROZEN)
- `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` (v1.1 FROZEN)
- `docs/mission_state_machine.md` (FROZEN at M6.1.A — 8-event taxonomy + state diagram)
- `docs/mission_event_contract.md` (FROZEN at M6.1.A — envelope schema; not on this branch)
- `docs/cr/CR-4_phase45_d4_d5_idempotency_envelope.md` (APPROVED 2026-07-09)
- `docs/cr/CR-1_phase45_state_orphan_typo.md` (DRAFT, M6.3.A gate)
- `docs/cr/CR-2_phase45_plan_path_typos.md` (DRAFT, M6.3.A gate)
- `docs/cr/CR-3_phase45_phase26_additive_column.md` (DRAFT, M6.3.A gate)
- `core/mission/mission_transport.py` (M6.4.A — Protocol surface; A-1 architecture invariant)
- `core/mission/transports/__init__.py` (M6.4.A — re-exports)
- `core/mission/transports/envelope.py` (M6.4.B.1 — EnvelopeV1 codec; D-5; **bug-fixed at `0e1b593`** — pydantic 2.13.4 `model_dump(mode='json')` was failing on `bytes` fields; switched to `model_dump()` + UUID→str coercion. On-wire bytes unchanged; the fix produces the same shape the design intended)
- `core/mission/transports/redis.py` (M6.4.B.2 — real RemoteTransport; cross-client delivery + Lua-script atomicity contract; **the lease primitives the M6.4.C LeaderElection consumes**)
- `core/mission/transports/local.py` (M6.4.A — in-process transport; also consumed by M6.4.C tests)
- `core/mission/worker_registry.py` (M6.4.A — D-1 15s grace; idempotent register/heartbeat; `list_active` sweep+read single-txn; **extended at `0e1b593`** — additive `mark_task_started` / `mark_task_completed` keyed on `(worker_id, wave_run_id)` for D-4 idempotency)
- `core/mission/worker_process.py` (M6.4.A — CLI; no secret-on-cmdline per spec §8.3; default heartbeat 10s)
- `core/mission/distributed_router.py` (M6.4.A — A-1 invariant; speaks only to MissionTransport Protocol; D-2 append-only; D-3 dedup; **extended at `0e1b593`** — additive `_route_remote` + `REASON_ROUTED_REMOTE` for REMOTE_PREFERRED behavior)
- `core/mission/leader_election.py` (M6.4.C — NEW `LeaderElection` state machine + `LeaderRole` enum + `LeaderElectionError`. Single-DC only per spec §10. Speaks only to `MissionTransport` Protocol per A-1.)
- `api/routes/distributed_pool.py` (M6.4.A — REST endpoints; auth `platform.admin`)
- `core/runtime/mission_models.py` (additive `WorkerRegistryModel` + `TaskRoutingLogModel` + D-3 unique index)
- `tests/test_distributed_router_remote_preferred.py` (M6.4.B — NEW 23 tests; REMOTE_PREFERRED + task accounting + A-1 AST inspection; landed at `0e1b593`)
- `tests/test_leader_election.py` (M6.4.C — NEW 33 tests across 14 classes; landed at `fff4daa`)

**Frozen Interfaces (M6.4 contracts — A-1..A-5 plan-level invariants; do not bypass):**
- A-1: `DistributedRouter` AND `LeaderElection` must speak only to `MissionTransport` Protocol + `WorkerRegistry`. NEVER import a concrete `LocalTransport` / `RemoteTransport` / `EnvelopeV1`. Even M6.4.A's local-mode routing uses the worker registry as the single source of truth. **AST-verified by `tests/test_distributed_router_remote_preferred.py::TestA1NoConcreteTransportImport` and by static inspection of `core/mission/leader_election.py` (only `MissionTransport` is imported).**
- A-2: Event-first architecture (reused from `MissionActor` plan; not a M6.4 file directly).
- A-3: 8-event taxonomy frozen (referenced via `docs/mission_state_machine.md`).
- A-4: Replay-safe checkpoints (referenced via `MissionActor` plan; not a M6.4 file directly).
- A-5: Legacy callers oblivious. New M6.4 functionality MUST NOT require legacy Phase 34 callers to understand new columns. Additive columns NULL gracefully.
- D-1: Worker grace = 15s. Stale workers sweep to OFFLINE on next `list_active`.
- D-2: `task_routing_log` append-only.
- D-3: One routing log row per `(wave_run_id, chosen_worker_id)` pair (enforced by unique index).
- D-4 (CR-4): Runtime exactly-once, transport at-least-once. `WaveRunId` idempotency on receive. **Honoured by `WorkerRegistry.mark_task_started` / `mark_task_completed` idempotency on `(worker_id, wave_run_id)` (M6.4.B code-completion).**
- D-5 (CR-4): All remote messages travel in a versioned `TransportEnvelope` (msgpack+zstd; `extra='ignore'` forward-compat). **Codec now correctly round-trips binary payloads after the `0e1b593` `model_dump()` fix.**

**Pre-Phase 45 frozen files:** see earlier entries (Phases 1-44) — the FREEZE_LEDGER retains them but the active M6.4 work only references the Phase 45 entries above.

**Updated:** 2026-07-11 19:30 NPT — post-`fff4daa` M6.4.C closure
