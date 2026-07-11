# CONTEXT INDEX

*Rule: Do NOT scan the repo. Find what you need here.*

**Phase 45 (Goal #6 — Persistent Autonomous Runtime):**
- Spec: `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` (v1.2 FROZEN-amended)
- Plan: `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` (v1.1 FROZEN)
- CR-4: `docs/cr/CR-4_phase45_d4_d5_idempotency_envelope.md` (APPROVED 2026-07-09)
- State machine: `docs/mission_state_machine.md` (FROZEN at M6.1.A)
- Scope sketch: `docs/goal6_scope.md` (Goal #6 deliverable checklist)
- Audit: `docs/r1_synthetic_event_review.md` (M6.1.A gate review, COMPLETED)

**M6.4 (Distributed Execution) — current branch `phase45/transport`:**
- `core/mission/mission_transport.py` — MissionTransport Protocol + exceptions
- `core/mission/transports/{__init__,local,redis,envelope}.py` — LocalTransport + RemoteTransport + EnvelopeV1
- `core/mission/worker_registry.py` — DB-touching worker liveness helper
- `core/mission/worker_process.py` — CLI entry point
- `core/mission/distributed_router.py` — leader-side routing decision
- `api/routes/distributed_pool.py` — REST endpoints under `/api/v1/distributed/`
- `core/runtime/mission_models.py` — WorkerRegistryModel + TaskRoutingLogModel

**Other JARVIS subsystems (Phase 34/41 + 26/27 etc.):**
- Mission runtime: `core/runtime/mission.py` + `core/runtime/mission_models.py` (FROZEN Phase 34)
- Skill runtime: `core/skills/` (FROZEN Phase 41)
- Observability: `core/observability/` (FROZEN Phase 27)
- API gateway: `api/main.py` + `api/routes/` (FROZEN Phase 14)
- Auth: see `core/security/` (FROZEN Phase 17)

**Governance / tools:**
- `AGENTS.md` — agent constitution (boot sequence, authority ranking, STOP protocol)
- `docs/60_MASTER_INDEX.md` — document locator
- `JARVIS_EXECUTIVE_DASHBOARD.md` — high-level progress tracker (read-only mirror of AGENTS.md §12 + milestone reports)
- `scripts/dgv.py` — dependency-graph validator
- `scripts/architecture_linter.py` — layer direction / repository / engine linter
- `scripts/quality_gate.py` — quality gate pipeline
