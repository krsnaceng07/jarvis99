# 107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md

## Status
**STATUS:** FROZEN (2026-07-08 — architect-approved with CR-1, CR-2, CR-3, CR-4 applied)
**Authority:** Rank 4 (Phase Specification)
**Change Log:**
- v1.0 DRAFT (2026-07-08) — initial spec drafted; `docs/goal6_scope.md` formalized into a contract.
- v1.1 FROZEN (2026-07-08) — CR-1 (MissionActor is the single source of truth for mutable mission state) and CR-2 (Scheduler enqueues only; never executes) applied; transport-abstraction (6.4), event-taxonomy-first freeze, and `mission_state_machine.md` cross-reference added.
- v1.2 FROZEN (2026-07-08) — CR-3 applied (Phase 34 Mission Runtime is canonical; MissionActor is write-gateway for NEW flows only; no second event system — reuse EventBusInterface; additive migrations only — never rename existing tables; Compatibility Matrix added). Path A of the v1.1 Conflict Report.
- v1.2 FROZEN-amended (2026-07-08, post-M6.1.A gate review) — CR-4 applied: **A-5 / G-6 legacy obliviousness** added to §5; event envelope freeze in §4.1 row Payload keys carries the architect-frozen envelope shape. ADR-45-01 recorded for additive ORM columns.
**Dependencies:** Phase 26 (Multi-Agent Persistent Recovery — `docs/87`), Phase 27 (Observability & Cost Governance — `docs/88`), Phase 34 (Autonomous Agent Mission — `docs/96`), Phase 43 (Goal Engine — `docs/105`), Phase 44 (Mission Scheduler — `docs/106`)
**Implements:** Goal #6 — Persistent Autonomous Runtime
**Prerequisite:** v0.9.0-rc2 (Goals #1-5 complete + RC fixes, 1711/1711 tests passing)
**Supersedes:** `docs/goal6_scope.md` (kept as historical scope reference; this spec is the binding contract)

---

## 1. Problem Statement

JARVIS OS v0.9.0-rc2 runs missions in-memory inside a single Python process. This is acceptable for
research and end-to-end demos, but it is **not a runtime** — it is a runner. Five operational gaps
keep JARVIS from being usable as always-on autonomous infrastructure:

| # | Gap | Symptom |
|---|-----|---------|
| 1 | **No mission persistence beyond a single process lifecycle.** | Process kill = mission lost. Restart from `MissionManager.initialize()` shows zero state. |
| 2 | **No scheduling.** | Every mission is user-initiated via API. No cron, no recurring jobs, no delayed-start queues. |
| 3 | **No crash recovery at the mission layer.** | Phase 26 `SwarmResumeManager` recovers swarm tasks; nothing recovers *mission waves*. |
| 4 | **Single-machine scale ceiling.** | One Python process = one CPU budget. Adding cores does nothing. |
| 5 | **No mission-level live UI.** | Phase 27 has telemetry primitives, but `MissionManager` does not publish wave/agent state at mission granularity. |

Goal #6 closes all five gaps. It does **not** rewrite Goals #1-5 components — every change is
additive and hooks through the existing event bus (per `docs/40_PERFORMANCE_STANDARD.md` and
`docs/architecture/01_ARCHITECTURE_FREEZE.md`).

---

## 2. Architecture & Design

### 2.1 Layer Position

```
                          ┌──────────────────────────────────────┐
                          │  v0.9.0-rc2 Runtime (FROZEN)         │
                          │  BrainKernel → MissionManager → ...   │
                          └──────────────┬───────────────────────┘
                                         │  event-bus hooks (additive only)
                ┌────────────┬───────────┼───────────┬──────────────┐
                ▼            ▼           ▼           ▼              ▼
           ┌──────┐   ┌────────────┐ ┌──────────┐ ┌──────────────┐ ┌─────────────┐
           │ 6.1  │   │   6.2      │ │   6.3    │ │    6.5       │ │    6.4      │
           │Pers. │   │Scheduler   │ │ Recovery │ │Observability │ │Distributed  │
           └──────┘   └────────────┘ └──────────┘ └──────────────┘ └─────────────┘
              ▲             ▲              ▲              ▲               ▲
              └─────────────┴──────────────┴──────────────┴───────────────┘
                                  MissionLifecycleBus (new in 6.1)
```

The five sub-goals are **co-equal first-class features** layered on top of v0.9.0-rc2.
They share infrastructure introduced by 6.1 (MissionLifecycleBus, mission checkpoint store)
and are ordered only by *implementation dependency*, not by importance.

### 2.2 Mission Lifecycle (refined from `docs/sequence_diagram.md`)

The current sequence diagram already shows the happy path. Goal #6 adds the **fault-tolerance
wrap**:

```
   ┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │ Persisted   │    │   Scheduled  │    │   Recovered  │    │  Observable  │
   │ (6.1)       │    │   (6.2)      │    │   (6.3)      │    │  (6.5)       │
   └─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

A mission in v0.9.5 (post-Goal-6) is a *durable, schedulable, recoverable, observable* object.
The single in-memory `Mission` instance is replaced by a `MissionActor` that reads/writes a
single source of truth (the DB) and emits lifecycle events.

### 2.3 What Already Exists (No Rewrites) — **v1.2 corrected file paths (CR-3.1)**

| Component | Actual location | Existing since | What Goal #6 does with it |
|---|---|---|---|
| Mission runtime + DB model | `core/runtime/mission.py` (`MissionManager`) + `core/runtime/mission_models.py` (`MissionModel`, `MissionCheckpointModel`, `MissionTimelineModel`) | Phase 34 | **CR-3.1**: Phase 34 Mission Runtime is the canonical implementation. Phase 45 extends it through additive architecture. Existing runtime modules are normative unless explicitly superseded by a future approved CR. |
| Mission scheduler | `core/mission/mission_scheduler.py` (`GoalScheduler`, `BackgroundGoalRunner`) + `core/mission/mission_types.py` (DTOs) | Phase 44 | Wrap with `ScheduledMissionDispatcher` adding cron/delayed triggers (6.2). CR-2: scheduler enqueues only. |
| Swarm recovery | `core/runtime/recovery_manager.py` (`SwarmResumeManager`) | Phase 26 | Generalize into `MissionRecoveryManager` that handles both swarm tasks AND mission waves (6.3). |
| Event bus | `core/interfaces.py` (`EventBusInterface` + `InterAgentMessage`) + `core/events/{base,memory_bus,redis_bus,reactive_router}.py` | Phase 26 (extended through Phase 40) | **CR-3.3**: Reuse existing event bus. Do not create a parallel event taxonomy. MissionActor owns lifecycle semantics; EventBus owns transport. Single taxonomy (the 8 frozen events in §4.1). |
| Telemetry / observability | `core/observability/{__init__,broadcaster,metrics,tracer}.py` (Phase 27) + `core/runtime/execution_tracer.py` (Phase 26) | Phase 27 | Add `mission-level` views: per-mission spans, wave progress events (6.5). |
| ORM Base | `core/memory/models.py:Base` | Phase 19 | Reuse as ORM base for new tables (if any) — but per CR-3.4 we prefer additive columns on existing tables. |

### 2.4 Compatibility Matrix (CR-3)

The table below is the canonical reference for which Phase 34 / 44 / 26 components are
**Legacy Supported** (frozen, untouched), **Extended** (additive columns only), **Wrapped**
(new layer on top), **Reused** (consumed as-is), or **New** (introduced by Phase 45).

| Component | Actual location | Status (CR-3) | Notes |
|---|---|---|---|
| `MissionManager` (Phase 34) | `core/runtime/mission.py` | **Legacy Supported** | Frozen Phase 34 implementation. Existing lifecycle methods untouched. Legacy direct DB mutations remain in place; Phase 46 may migrate callers. |
| `MissionModel` (Phase 34) | `core/runtime/mission_models.py:34` | **Extended** | Frozen shape; M6.1.A adds `wave_state`, `checkpoint_seq`, `last_actor_heartbeat` columns via additive migration. No rename. |
| `MissionCheckpointModel` (Phase 34) | `core/runtime/mission_models.py:58` | **Extended** | Frozen shape; M6.1.A adds `seq`, `wave_idx`, `payload`, `state` columns via additive migration. Existing `state_data` JSON retained. |
| `MissionTimelineModel` (Phase 34) | `core/runtime/mission_models.py:72` | **Reused** | MissionActor writes to it; no schema change. |
| `SwarmResumeManager` (Phase 26) | `core/runtime/recovery_manager.py:22` | **Reused** | MissionRecoveryManager wraps it; no modification. |
| `GoalScheduler` (Phase 44) | `core/mission/mission_scheduler.py` | **Wrapped** | ScheduledMissionDispatcher wraps it (6.2); scheduler enqueues only (CR-2). |
| `EventBusInterface` (Phase 26+) | `core/interfaces.py:66` | **Reused** | Single event transport. MissionActor publishes 8 frozen events through it. No second taxonomy (CR-3.3). |
| `InterAgentMessage` | `core/interfaces.py:14` | **Reused** | Envelope shape unchanged. |
| `MissionActor` (Phase 45, M6.1.A) | `core/runtime/mission_actor.py` | **New** | Write gateway for NEW Phase 45 lifecycle paths. SoT for new flows. |
| `ScheduledMissionDispatcher` (Phase 45, M6.2.A) | `core/mission/scheduled_mission_dispatcher.py` | **New** | Cron/delayed triggers; enqueues only. |
| `MissionRecoveryManager` (Phase 45, M6.3.A) | `core/runtime/mission_recovery.py` | **New** | Mission-wave orphan detection; wraps `SwarmResumeManager`. |
| `MissionTransport` (Phase 45, M6.4.A) | `core/mission/transports/__init__.py` | **New** | Protocol abstraction. `LocalTransport` first; `RemoteTransport` (Redis) in M6.4.B. |
| `DistributedRouter` (Phase 45, M6.4.B) | `core/mission/distributed_router.py` | **New** | Speaks only to `MissionTransport` protocol. |
| `WorkerProcess` (Phase 45, M6.4.A) | `core/mission/worker_process.py` | **New** | Standalone worker CLI; registers in `worker_registry`. |
| `worker_registry` table (Phase 45, M6.4.A) | `alembic/versions/0048_*.py` | **New table** | OK because no Phase 34 / 26 / 44 component owns this table name. |
| `task_routing_log` table (Phase 45, M6.4.B) | `alembic/versions/0048b_*.py` | **New table** | Append-only routing audit. No conflict with Phase 34. |
| `scheduler_triggers` table (Phase 45, M6.2.A) | `alembic/versions/0046_*.py` | **New table** | Trigger registry. No conflict with Phase 44 (which has no persistent trigger table). |
| `mission_recovery_journal` table (Phase 45, M6.3.A) | `alembic/versions/0047_*.py` | **New table** | Recovery audit. No conflict with Phase 26. |
| `mission_dead_letters` table (Phase 45, M6.3.B) | `alembic/versions/0047b_*.py` | **New table** | Dead-letter queue. No conflict with Phase 26. |
| Dashboard SQL views (Phase 45, M6.5.A) | `alembic/versions/0049_*.py` | **New views** | Read-only views over existing tables. No conflict. |
| Telemetry / observability (Phase 27) | `core/observability/` | **Reused** | Mission-level spans + dashboard events built on Phase 27 primitives. |

**Status legend:**
- **Legacy Supported** — frozen, no modification, no new writes from Phase 45 actors.
- **Extended** — additive column(s) only; no row shape change to existing rows.
- **Wrapped** — new layer added on top; underlying component is unmodified.
- **Reused** — consumed as-is.
- **New** — introduced by Phase 45; no overlap with frozen code.

### 2.5 New Event Topics (additive)

| Topic | Publisher | Subscriber(s) | Stage |
|---|---|---|---|
| `mission.lifecycle.created` | MissionActor | TelemetryBroadcaster, HealthProbe | 6.1 |
| `mission.lifecycle.checkpoint` | MissionActor | MissionRecoveryManager, ExecutionTracer | 6.1 |
| `mission.lifecycle.completed` | MissionActor | TelemetryBroadcaster | 6.1 |
| `scheduler.fire` | MissionScheduler | MissionManager.create_mission | 6.2 |
| `mission.recovery.replay` | MissionRecoveryManager | MissionActor, SwarmOrchestrator | 6.3 |
| `mission.distributed.route` | DistributedRouter | WorkerPool | 6.4 |
| `worker.heartbeat` | WorkerProcess | WorkerRegistry | 6.4 |

No existing topic is renamed, deleted, or repurposed.

---

## 3. Directory Layout (v1.2 — CR-3 corrected)

```text
core/runtime/                              # EXTENDS existing (Phase 34)
  ├── mission_actor.py                     # NEW — durable state machine (6.1) — write gateway for NEW Phase 45 flows (CR-3.2). Lives alongside `mission.py` (Phase 34).
  ├── mission_events.py                    # NEW (6.1) — frozen lifecycle event taxonomy (8 events) + payload dataclasses (A-3). Reuses EventBusInterface for transport (CR-3.3).
  ├── mission_checkpoint.py                # NEW — msgpack+zstd actor-side checkpoint serialization (6.1, A-4 replay-safe). Reads/writes Phase 34 `MissionCheckpointModel` + new additive columns.
  ├── mission_recovery.py                  # NEW (6.3) — mission-wave orphan detection; wraps `SwarmResumeManager` (Phase 26). New `mission_recovery_journal` table; new `mission_dead_letters` table.
  └── mission.py                           # FROZEN Phase 34 — untouched.

core/mission/                              # EXTENDS existing (Phase 44 scheduler)
  ├── scheduled_mission_dispatcher.py      # NEW — cron/delayed dispatcher (6.2) — enqueues only, never executes (CR-2)
  ├── distributed_router.py                # NEW — leader-side task routing (6.4)
  ├── worker_process.py                    # NEW — standalone worker CLI (6.4)
  ├── worker_registry.py                   # NEW — worker liveness helper (6.4) — wraps new `worker_registry` table
  ├── transports/                          # NEW (6.4) — MissionTransport implementations
  │   ├── __init__.py                      # protocol re-export
  │   ├── local.py                         # LocalTransport (in-process; default for tests + dev)
  │   └── redis.py                         # RemoteTransport (Redis pub/sub + leases; M6.4.B)
  ├── mission_observability.py             # NEW — mission-level views (6.5)
  ├── mission_scheduler.py                 # FROZEN Phase 44 — wrapped, not modified.
  └── mission_types.py                     # FROZEN Phase 44 — untouched.

api/routes/
  ├── mission_lifecycle.py                 # NEW — /api/v1/missions/{id}/checkpoint, /replay (6.1, 6.3)
  ├── mission_schedule.py                  # NEW — /api/v1/scheduler/triggers (6.2)
  ├── distributed_pool.py                  # NEW — /api/v1/distributed/workers (6.4)
  └── mission_dashboard.py                 # NEW — /api/v1/missions/dashboard (6.5)

alembic/versions/
  ├── 0045_actor_columns.py                # alembic — 6.1 ADDITIVE columns on missions + mission_checkpoints (CR-3.4). NO new tables.
  ├── 0046_scheduler_triggers.py           # alembic — 6.2 NEW table
  ├── 0047_mission_recovery.py             # alembic — 6.3 NEW tables (mission_recovery_journal, mission_dead_letters)
  ├── 0048_worker_registry.py              # alembic — 6.4 NEW tables (worker_registry, task_routing_log)
  └── 0049_mission_dashboard_views.py      # alembic — 6.5 NEW views (read-only)

tests/
  ├── test_mission_actor.py                # 6.1 (≥10) — MissionActor unit + event contract + replay
  ├── test_mission_compat.py               # 6.1 (≥5) — Phase 34 MissionManager compatibility
  ├── test_scheduled_dispatcher.py         # 6.2 (≥8)
  ├── test_mission_recovery.py             # 6.3 (≥10)
  ├── test_distributed_router.py           # 6.4 (≥12)
  ├── test_local_transport_exhaustive.py   # 6.4 (≥25) — exhaustive LocalTransport contract tests
  ├── test_worker_process.py               # 6.4 (≥6)
  ├── test_mission_observability.py        # 6.5 (≥6)
  └── test_goal6_integration.py            # cross-stage smoke (≥3)

docs/
  ├── 107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  # THIS FILE
  ├── mission_event_contract.md            # NEW (M6.1.A) — event payload schemas + ordering + versioning + backward-compat
  ├── mission_state_machine.md             # NEW (M6.1.A) — companion state diagram; re-marked FROZEN at M6.1.A gate
  └── r1_synthetic_event_review.md         # NEW (M6.1.A) — R1 mitigation: pre-freeze event audit
```

No file under `api/` is deleted. No file under `core/memory/`, `core/reasoning/`, or
`core/runtime/` (existing modules) is modified except the additive extension points
listed in §2.3 and §4. **Per CR-3.5, Phase 34 persistence models and their existing
columns are immutable — only additive migrations are permitted.**

---

## 4. Sub-Goal Specifications

### 4.1 Goal #6.1 — Mission Persistence

**Problem** (recap from `docs/goal6_scope.md`): mission state lives in process memory.
Process exit = lost state.

**Solution shape — CR-1 enforced:**

```
            MissionManager            (orchestration only — never mutates state)
                  │
                  ▼
            MissionActor              (single source of truth for mutable mission state)
                  │
                  ▼
            Persistence               (DB writes are the only place state is durably written)
```

> **CR-1 (architect-approved 2026-07-08):** `MissionActor` is the **only** component that
> mutates mission state. `MissionManager` may *invoke* `MissionActor` methods and read
> actor state, but it **must not** hold its own mutable copy. This eliminates split-brain
> between in-memory and persisted state.

- A `MissionActor` replaces the in-memory `Mission` object as the single source of truth.
  All reads/writes flow through the actor, which holds an in-memory cache *revalidated
  from the DB on every state read at a 5s TTL* and writes through.
- A `mission_checkpoints` table stores serialized `wave_state` blobs (msgpack + zstd) at
  every state transition and at wave boundaries.
- `MissionManager.initialize()` is extended to scan for missions with `status IN
  (RUNNING, WAITING_APPROVAL, PLAN_PENDING)` on boot and rehydrate them via `MissionActor`.

**Frozen file touched:** NONE. `MissionManager.initialize()` gets a *new method*
`_rehydrate_actors_from_db()` called at end of init — not a modification of the existing init
flow. Mission state-write code paths elsewhere in `MissionManager` are routed through
`MissionActor` (a thin wrapper, not a duplicate).

**MissionActor scope (CR-3.2):** MissionActor is the **write gateway for NEW Phase 45
lifecycle transitions**. Legacy Phase 34 `MissionManager.start_mission()` /
`pause_mission()` / `resume_mission()` / `cancel_mission()` paths remain supported and
unchanged (they are frozen Phase 34 code). MissionActor provides an alternative path
that:

1. Persists the state transition durably via the additive columns on `missions` +
   `mission_checkpoints` (above).
2. Emits exactly one of the 8 frozen lifecycle events via the existing
   `EventBusInterface` (no parallel event system — CR-3.3).
3. Holds a 5s-TTL in-memory cache revalidated from the DB on every read (P-1).

Legacy direct DB mutations from Phase 34 `MissionManager` are tracked as technical debt
for Phase 46 (when `MissionManager` may be migrated to call `MissionActor` as a thin
wrapper). **No migration of Phase 34 callers happens in Phase 45.**

```text
Phase 45 (additive; new lifecycle paths)
─────────────────────────────────────
              MissionActor
                   │
                   ▼
              Mission tables (missions, mission_checkpoints, mission_timeline)

Legacy Phase 34 (frozen; existing paths)
─────────────────────────────────────
              MissionManager
                   │
                   ▼
              Mission tables (missions, mission_checkpoints, mission_timeline)
```

**Layer direction (unchanged from CR-1):** `api/ → MissionActor → Persistence`. The
**only** mutation path Phase 45 introduces for new flows is MissionActor. Phase 34's
legacy mutation path remains in place (frozen).

**Event Taxonomy Freeze (precursor to M6.1.B and a hard dependency for 6.5):**

Before any REST/WebSocket/Metrics code is written against mission lifecycle, the following
8 event names are **frozen** in `core/runtime/mission_events.py` (NEW; the file is
implemented at `core/runtime/mission_events.py` per CR-3 corrected paths):

**Frozen event envelope (architect-approved 2026-07-08):**

Every payload carries these envelope fields in this exact order:

```text
event_id        UUID       — unique per emission (default uuid4)
event_version   int=1      — payload schema version
mission_id      UUID       — the mission the event refers to
actor_id        str        — actor method that produced the event (e.g. "MissionActor.start")
timestamp       str        — ISO-8601 UTC, captured at publish time
correlation_id  UUID       — groups related events across publisher/subscribers
causation_id    UUID|null  — the upstream event_id that caused this event (null for head events)
payload         dict       — event-specific extras (see per-event rows below)
```

These eight fields together are the **frozen envelope**. Once frozen, adding OPTIONAL
fields is allowed without a CR (the field is added to the envelope and older readers
keep working because `extra="forbid"` is **lifted** to `extra="ignore"` for the envelope
itself; downstream code that asserts specific fields is unaffected). Adding REQUIRED
fields, renaming, or removing any field requires a fresh CR per AGENTS.md §8.

**Frozen 8 event names + per-event extras:**

| Event | Trigger | Payload (envelope + extras) |
|---|---|---|
| `mission.created` | actor is constructed | envelope + `goal`, `created_at` |
| `mission.started` | state → RUNNING | envelope + `wave_idx` |
| `mission.paused` | state → PAUSED | envelope + `reason` |
| `mission.resumed` | state → RUNNING from PAUSED | envelope + `wave_idx` |
| `mission.completed` | state → COMPLETED | envelope + `duration_ms`, `checkpoint_seq` |
| `mission.failed` | state → FAILED | envelope + `error`, `wave_idx` |
| `mission.recovered` | rehydration on boot OR replay path | envelope + `wave_run_id`, `from_seq` |
| `mission.cancelled` | explicit cancel | envelope + `reason` |

Once frozen in `M6.1.A`, **no event topic in this list may be renamed** without a fresh
Change Request per AGENTS.md §8 (added to STOP conditions §9).

**Database (CR-3.4 — additive migration only, never rename existing tables):**

The Phase 34 `MissionCheckpointModel` already exists at `core/runtime/mission_models.py:58`
with shape `(checkpoint_id UUID PK, mission_id UUID, step_index INTEGER, state_data JSON,
created_at DATETIME)`. Per CR-3.4, Phase 45 does NOT create a duplicate table; it adds
the following additive columns via the M6.1.A migration `0045_actor_columns.py`:

| Table | New columns (additive) | Purpose |
|---|---|---|
| `missions` | `wave_state` (BLOB, nullable) | msgpack+zstd of wave-level runtime state for replay |
| `missions` | `checkpoint_seq` (INTEGER, nullable, default 0) | Monotonic counter mirroring `MAX(seq)` of `mission_checkpoints` for that mission — used by P-2 consistency check |
| `missions` | `last_actor_heartbeat` (DATETIME, nullable) | Liveness signal for M6.3.A orphan detection (Phase 34 `MissionTimelineModel` already covers timeline; we add heartbeat on the parent row to avoid an extra join) |
| `mission_checkpoints` | `seq` (INTEGER, nullable) | Monotonic actor-side sequence (1, 2, 3, …); matches `missions.checkpoint_seq` |
| `mission_checkpoints` | `wave_idx` (INTEGER, nullable) | Wave boundary marker; supersedes Phase 34's `step_index` for actor-side reads (legacy `step_index` retained for back-compat) |
| `mission_checkpoints` | `payload` (BLOB, nullable) | msgpack+zstd actor-side replay snapshot (A-4); legacy `state_data` JSON retained for back-compat |
| `mission_checkpoints` | `state` (VARCHAR(32), nullable) | Actor state at checkpoint time — RUNNING / COMPLETED / RECOVERED / FAILED |

**No NEW tables are created in M6.1.A.** Phase 34's `mission_timeline` table is reused
as-is for timeline events. Per CR-3.4 + CR-3.5, no Phase 34 persistence model is removed,
renamed, or rewritten.

**Migration safety:** all new columns are nullable with `NULL` default for back-compat
with pre-M6.1.A rows. The actor treats `NULL` `seq` / `payload` / `state` as "legacy
checkpoint, no actor snapshot" and falls back to reading `state_data` JSON for those
rows. A future M6.x milestone may backfill `payload` from `state_data`; that is out of
scope here.

**Key invariant (6.1):**

| # | Invariant |
|---|-----------|
| **P-1** | Every state transition emitted by `MissionActor` is durably written to `mission_checkpoints` *before* the in-memory cache is updated. |
| **P-2** | A mission whose `checkpoint_seq` differs from `MAX(seq)` of `mission_checkpoints` is treated as **inconsistent** and refused to start. |
| **P-3** | **(CR-1)** A path that mutates mission state without going through `MissionActor` is a STOP condition. `MissionManager` and any other coordinator are read-only on state. |

---

### 4.2 Goal #6.2 — Scheduler (cron + periodic)

**Problem:** all missions are user-initiated.

**Solution shape — CR-2 enforced:**

```
   ScheduledMissionDispatcher
              │
              ▼
        enqueue mission         ← Scheduler's ONLY output
              │
              ▼
        MissionManager
              │
              ▼
        MissionActor             ← execution flows through here, NEVER through Scheduler
```

> **CR-2 (architect-approved 2026-07-08):** The scheduler's role is **enqueue + dispatch**.
> It must never become an execution layer. All mission execution flows through
> `MissionManager` → `MissionActor`. This makes the scheduler trivially horizontally
> scalable (multiple scheduler replicas can share the same queue) and keeps scheduling
> logic out of the critical execution path.

- `ScheduledMissionDispatcher` wraps the existing `MissionScheduler`. On boot it reads
  `scheduler_triggers` and re-arms them.
- Three trigger types: `ONE_SHOT` (delayed start), `CRON` (cron expression), `INTERVAL`
  (every N seconds).
- Trigger evaluation uses `croniter` library (existing dependency check at `pyproject.toml`).
- Trigger firing is **idempotent**: a trigger that fires while the previous instance is still
  running does NOT enqueue a duplicate (tracked via `last_fired_at` + `last_instance_id`).
- When a trigger fires, the dispatcher publishes `scheduler.fire` and lets
  `MissionManager.create_mission()` be the actual entry point. **The scheduler does not
  call any execution-layer method directly** (added invariant S-3 below).

**Database (new table):**

| Table | `scheduler_triggers` |
|---|---|
| `trigger_id` | UUID PK |
| `name` | VARCHAR(255) — human label, unique |
| `kind` | VARCHAR(16) — ONE_SHOT / CRON / INTERVAL |
| `expression` | VARCHAR(255) — cron/ISO-time/duration (depending on kind) |
| `mission_template_id` | UUID (FK → missions.id, nullable — template mission to clone) |
| `enabled` | BOOLEAN |
| `max_concurrent` | INTEGER (default 1; reject fires if currently-running count ≥ this) |
| `last_fired_at` | DATETIME (nullable) |
| `last_instance_id` | UUID (nullable — for idempotency) |
| `next_fire_at` | DATETIME — indexed, what the dispatcher polls |
| `metadata` | JSONB |

**Key invariant (6.2):**

| # | Invariant |
|---|-----------|
| **S-1** | A `CRON` trigger that fires within `±1s` of its scheduled time is considered compliant; deviation > 5s is logged at WARN. |
| **S-2** | A trigger with `max_concurrent=1` MUST NOT enqueue a new mission while a previous instance is in `RUNNING` or `WAITING_APPROVAL`. |
| **S-3** | **(CR-2)** `ScheduledMissionDispatcher` MUST NOT call any method on `MissionManager`, `MissionActor`, `SwarmOrchestrator`, or any executor. Its only outputs are (a) the `scheduler.fire` event and (b) `MissionManager.create_mission()` invocation (via the existing public API). |

**Frozen file touched:** NONE. Wraps, does not modify, `MissionScheduler`.

---

### 4.3 Goal #6.3 — Crash Recovery

**Problem:** mission state can be inconsistent after `SIGKILL` or hard reboot.

**Solution shape:**

- `MissionRecoveryManager` runs at end of `MissionManager.initialize()`. It calls
  `_rehydrate_actors_from_db()` (from 6.1) then sweeps `mission_checkpoints` for:
  - Missions with `state=RUNNING` whose `created_at < now() - heartbeat_grace` AND no
    `last_actor_heartbeat` update for >30s → flip to `state=ORPHANED`.
  - Re-enqueue orphan missions via a replay path: load last `wave_state` checkpoint, mark
    wave as `RECOVERED`, re-emit the wave via `SwarmOrchestrator.spawn_task()`.
- Idempotency: each wave carries a `wave_run_id` (UUID). The replay path checks
  `agent_loop_journals.wave_run_id` (Phase 26 table) and skips waves already executed for
  that ID.

**Database (new table):**

| Table | `mission_recovery_journal` |
|---|---|
| `journal_id` | UUID PK |
| `mission_id` | UUID, FK → missions.id |
| `wave_run_id` | UUID — matches the wave execution token |
| `action` | VARCHAR(32) — RECOVERED / SKIPPED / FAILED |
| `checkpoint_seq` | INTEGER |
| `reason` | VARCHAR(255) |
| `recorded_at` | DATETIME |

**Key invariant (6.3):**

| # | Invariant |
|---|-----------|
| **R-1** | Recovery is **at-least-once**: a wave may re-execute, but the outcome is idempotent (no duplicate side effects). |
| **R-2** | Dead-letter queue: any mission that fails recovery 3 consecutive times is moved to `mission_dead_letters` (new table) and emits `mission.recovery.dead_letter` event. |

| Table | `mission_dead_letters` (new) |
|---|---|
| `mission_id` | UUID PK |
| `first_failure_at` | DATETIME |
| `last_failure_at` | DATETIME |
| `failure_count` | INTEGER |
| `last_error` | TEXT |
| `payload_snapshot` | BLOB (last checkpoint payload) |

**Frozen file touched:** NONE. `SwarmResumeManager` (Phase 26) is reused as-is. Goal #6.3
adds a layer *above* it for mission-wave grain.

---

### 4.4 Goal #6.4 — Distributed Execution

**Problem:** single process = single machine.

**Solution shape — Transport-first (architect recommendation 2026-07-08):**

Before any network code is written, the **`MissionTransport` protocol** is introduced as
a thin abstraction so transport swap is config-only.

```
                DistributedRouter
                        │
                        ▼
                MissionTransport        ← protocol (interface)
                  /            \
                 ▼              ▼
          LocalTransport    RemoteTransport
          (in-process)      (Redis default;
                            RabbitMQ/NATS/gRPC
                            are future packages)
```

> **Transport abstraction (architect recommendation 2026-07-08):** `DistributedRouter`
> must speak only to the `MissionTransport` protocol — never to a concrete Redis / RabbitMQ
> / gRPC client. New transports are drop-in modules under `core/mission/transports/`. This
> keeps the leader's network surface small and unit-testable.

**Build order within 6.4:**

1. **M6.4.A** — `MissionTransport` protocol + `LocalTransport` + `WorkerProcess` CLI + `worker_registry` table. **No network code yet.** The router uses `LocalTransport` for development and CI.
2. **M6.4.B** — `RemoteTransport` (Redis pub/sub implementation) + Redis dependencies added + routing policy tests.
3. **M6.4.C** *(stretch, optional)* — leader election (Redis SETNX lease) + horizontal scaling acceptance tests.

**Components:**

- A leader process runs `MissionActor` (from 6.1) and `DistributedRouter` (new).
- A pool of `N` worker processes run `WorkerProcess` (new), each registered in
  `worker_registry` with periodic heartbeats.
- `DistributedRouter` decides for each wave execution **local vs. remote** based on:
  - Worker capability match (Phase 41 capability registry).
  - Worker load (current active task count).
  - Routing policy: `LOCAL_ONLY` / `REMOTE_PREFERRED` / `ANY`.
- Leadership: an optional leader-election (Redis SETNX-based lease) prevents two leaders
  from running simultaneously. **Stretch goal** in M6.4.C — the required delivery is
  single-leader with operator-controlled failover (the user restarts the leader).

**MissionTransport protocol:**

```python
class MissionTransport(Protocol):
    """Transport-agnostic surface for cross-process task routing."""

    async def publish(self, channel: str, payload: bytes) -> None: ...
    async def subscribe(self, channel: str) -> AsyncIterator[bytes]: ...
    async def lease(self, key: str, ttl_seconds: int) -> Optional[str]: ...
    async def renew_lease(self, key: str, token: str, ttl_seconds: int) -> bool: ...
    async def release_lease(self, key: str, token: str) -> None: ...
```

Each transport module under `core/mission/transports/` implements this protocol. The
leader does not know which one is active.

**Database (new tables):**

| Table | `worker_registry` |
|---|---|
| `worker_id` | UUID PK |
| `hostname` | VARCHAR(255) |
| `pid` | INTEGER |
| `capabilities` | JSONB |
| `status` | VARCHAR(16) — ONLINE / BUSY / OFFLINE |
| `active_tasks` | INTEGER |
| `last_heartbeat` | DATETIME |
| `started_at` | DATETIME |

| Table | `task_routing_log` |
|---|---|
| `route_id` | UUID PK |
| `wave_run_id` | UUID |
| `chosen_worker_id` | UUID |
| `decision_reason` | VARCHAR(255) |
| `routed_at` | DATETIME |
| `completed_at` | DATETIME (nullable) |

**Key invariant (6.4):**

| # | Invariant |
|---|-----------|
| **D-1** | A worker whose `last_heartbeat` is >15s stale is marked `OFFLINE` and its in-flight tasks re-routed. |
| **D-2** | `task_routing_log` MUST be append-only — no UPDATE or DELETE. |
| **D-3** | For any given `wave_run_id`, exactly one row exists in `task_routing_log` per worker that handled (parts of) the wave. |
| **D-4** (CR-4, 2026-07-09) | **Transport = at-least-once; Runtime = exactly-once.** The transport MAY deliver zero, one, or N copies of any given message. The runtime MUST guarantee exactly-once execution via `wave_run_id` idempotency — the same wave never produces side effects twice regardless of duplicate delivery. `WaveRunId` is the foundation for this guarantee; mission execution MUST remain correct under all three delivery scenarios (0/1/N). |
| **D-5** (CR-4, 2026-07-09) | **Versioned transport envelope.** All remote messages travel in a versioned `TransportEnvelope` independent of mission DTOs. The envelope carries `envelope_version` (int, currently `1`), `payload_type` (string), `payload_bytes` (opaque msgpack+zstd), `idempotency_key` (UUID — defaults to `wave_run_id` for mission-domain messages), `producer_id` (string), `created_at` (ISO-8601 UTC). Adding OPTIONAL envelope fields does not require a CR; adding REQUIRED fields, renaming, or removing any field requires a fresh CR per AGENTS.md §8. Older readers MUST tolerate unknown OPTIONAL fields (`extra="ignore"` discipline). `LocalTransport` is exempt (no remote wire-format at the local level); D-5 applies to `RemoteTransport` and any future remote transport. |

**Frozen file touched:** NONE. `SwarmOrchestrator.spawn_task()` is wrapped, not modified.

---

### 4.5 Goal #6.5 — Mission Observability

**Problem:** Phase 27 has telemetry primitives; nothing surfaces **mission-level** state.

**Solution shape — Events-first (architect recommendation 2026-07-08):**

> **Events-first principle:** REST, WebSocket, metrics, and dashboard are all **derived
> views** of the 8 mission lifecycle events frozen in M6.1.A. They consume events; they
> do not introduce new ones. This is what makes the contract stable and prevents
> schema-drift fanout.

- Add 4 new SQL views (read-only, no schema change) over existing Phase 27 tables +
  new Goal #6 tables.
- Add `GET /api/v1/missions/dashboard` endpoint that returns a real-time snapshot per
  running mission.
- WebSocket topic `/ws/v1/missions/dashboard` fans out per-mission state updates every 2s
  (matches Phase 27 telemetry cadence).
- Optional terminal dashboard using `rich` library (`pip install rich` — added to
  `pyproject.toml`).
- Hard dependency: M6.5 cannot start until M6.1.A delivers the frozen event taxonomy.

**Database (views, not tables):**

```sql
CREATE VIEW v_mission_dashboard AS
SELECT
  m.id, m.goal, m.status, m.created_at, m.last_actor_heartbeat,
  COUNT(DISTINCT c.checkpoint_id)   AS checkpoint_count,
  COUNT(DISTINCT j.journal_id)      AS recovery_count,
  COUNT(DISTINCT r.route_id)        AS routings,
  (m.wave_state IS NOT NULL)        AS has_wave_state
FROM missions m
LEFT JOIN mission_checkpoints c ON c.mission_id = m.id
LEFT JOIN mission_recovery_journal j ON j.mission_id = m.id
LEFT JOIN task_routing_log r ON r.wave_run_id IN (...)
GROUP BY m.id;

-- plus v_wave_progress, v_scheduler_upcoming, v_worker_pool_status, v_dead_letters
```

**Key invariant (6.5):**

| # | Invariant |
|---|-----------|
| **O-1** | Dashboard payloads MUST NOT include raw prompt text, file content, secrets, or model arguments — only status, counts, IDs, durations, and timestamps. |
| **O-2** | Views are read-only. No `INSERT`/`UPDATE`/`DELETE` permissions for the API role on view definitions. |

**Frozen file touched:** NONE. Uses Phase 27 components via composition.

---

## 5. Cross-Sub-Goal Invariants

| # | Invariant |
|---|-----------|
| **G-1** | **No frozen file modification.** Every change is additive — new modules, new tables, new event topics. Phases 1-44 interfaces untouched. (See ADR-45-01 for the binding clarification on additive ORM column declarations.) |
| **G-2** | **Layer direction.** `api/` may import from `core/`, never reverse. New distributed worker reuses `core/` modules unchanged. |
| **G-3** | **Single source of truth.** `MissionActor` writes through to DB before state is observable. |
| **G-4** | **Quality bar:** per-sub-goal — ruff format, ruff check, mypy strict, ≥85% coverage on new modules, ≥90% on security-sensitive modules (recovery, distributed). |
| **G-5** | **No regression:** all 1711 v0.9.0-rc2 tests continue to pass after each sub-goal milestone. |
| **G-6 (CR-4, 2026-07-08)** | **Legacy obliviousness (A-5 — plan §8.1).** Legacy Phase 34 code MAY continue reading and writing legacy columns (`status`, `goal`, `plan_data`, `assigned_agents`, `budget_limit`, `budget_used`, `current_step`, `step_index`, `state_data`, etc.) unchanged. New Phase 45 functionality MUST NOT require legacy callers to understand any new field, event, or column. Phase 45 additive columns MUST NULL gracefully when a Phase 34 caller writes a row, and Phase 45 readers MUST treat NULL additive columns as "legacy row, fall back" — never as "data missing". This protects backward compatibility indefinitely. |

---

## 6. REST API Contracts (additions only)

| Method | Path | Sub-goal | Description |
|---|---|---|---|
| `GET` | `/api/v1/missions/{id}/checkpoint` | 6.1 | Return latest checkpoint payload + seq |
| `POST` | `/api/v1/missions/{id}/force-checkpoint` | 6.1 | Manual checkpoint trigger |
| `GET` | `/api/v1/scheduler/triggers` | 6.2 | List all triggers (paginated) |
| `POST` | `/api/v1/scheduler/triggers` | 6.2 | Create trigger |
| `PATCH` | `/api/v1/scheduler/triggers/{id}` | 6.2 | Update trigger (enable/disable/edit) |
| `DELETE` | `/api/v1/scheduler/triggers/{id}` | 6.2 | Delete trigger |
| `GET` | `/api/v1/missions/{id}/recovery` | 6.3 | Recovery journal for mission |
| `POST` | `/api/v1/missions/{id}/replay` | 6.3 | Force replay from last checkpoint |
| `GET` | `/api/v1/distributed/workers` | 6.4 | List workers + status |
| `GET` | `/api/v1/distributed/routing?wave_run_id=...` | 6.4 | Routing decisions for a wave |
| `GET` | `/api/v1/missions/dashboard` | 6.5 | Real-time dashboard snapshot |
| `WS` | `/ws/v1/missions/dashboard` | 6.5 | Live updates every 2s |

---

## 7. Implementation Milestones

Per AGENTS.md §5 lifecycle, after this SPECIFICATION is **APPROVED**, milestones are
drafted in a separate Implementation Plan (`docs/108_PHASE_45_IMPLEMENTATION_PLAN.md`).
Proposed milestone breakdown (subject to refinement after approval):

| Milestone | Sub-goal | Approx. test delta | Gate |
|---|---|---|---|
| **M6.1.A** | 6.1 — MissionActor + checkpoints table + tests | +15 | mini |
| **M6.1.B** | 6.1 — MissionManager rehydration + e2e test | +5 | mini |
| **M6.3.A** | 6.3 — MissionRecoveryManager + recovery journal | +18 | mini |
| **M6.3.B** | 6.3 — Dead-letter queue + replay endpoint | +8 | mini |
| **M6.2.A** | 6.2 — ScheduledMissionDispatcher + triggers table | +12 | mini |
| **M6.2.B** | 6.2 — REST endpoints + idempotency tests | +6 | mini |
| **M6.5.A** | 6.5 — Mission dashboard views + REST endpoint | +10 | mini |
| **M6.5.B** | 6.5 — WebSocket fanout + rich terminal dashboard | +8 | mini |
| **M6.4.A** | 6.4 — WorkerRegistry + WorkerProcess CLI | +12 | mini |
| **M6.4.B** | 6.4 — DistributedRouter + Redis adapter | +14 | mini |
| **M6.4.C** | 6.4 — Leader election (stretch) + routing invariant tests | +8 | mini |
| **FINAL** | All five — full quality gate + walkthrough | (subsumed) | final |

**Total tests at goal closure:** ≥ 1888 (1711 + 116+ new). Test count remains monotonic; no
test deletion.

---

## 8. Verification & Acceptance Criteria

### 8.1 Per-Sub-Goal (from `docs/goal6_scope.md`)

1. **6.1 Persistence:** Kill process mid-wave → restart → mission resumes from last checkpoint (lossless for `wave_state`).
2. **6.2 Scheduler:** Schedule mission for `+5s` → fires; set cron `*/1 * * * *` → repeats; kill/restart → schedule survives.
3. **6.3 Recovery:** `SIGKILL` mid-wave → restart → mission completes via replay; corrupt a checkpoint → mission moves to dead-letter queue.
4. **6.4 Distributed:** Start 3 worker processes → submit mission → tasks distributed across workers; kill 1 worker → tasks re-assigned.
5. **6.5 Observability:** Run mission → traces emitted; Prometheus endpoint returns metrics; dashboard renders live state.

### 8.2 Cross-Sub-Goal

- All 1711 v0.9.0-rc2 tests still pass after **each** milestone (no regression).
- New Goal #6 tests pass (target: ≥ 116 new tests).
- ruff / mypy / coverage gates green (`docs/47_QUALITY_GATES.md`).
- Architecture audit (`scripts/dgv.py` + architecture-linter) clean.
- Walkthrough generated and reviewed.

### 8.3 Security

- Dead-letter payloads stored in `mission_dead_letters.payload_snapshot` are scanned for
  secret-pattern matches (`docs/29_SECRET_MANAGEMENT.md`) and redacted before persistence.
- WorkerProcess reads config from env-vars only — no command-line secret passing.
- Dashboard views exclude secrets by column whitelist, not by regex (regex is best-effort;
  whitelist is correct-by-construction).

---

## 9. STOP Conditions (per AGENTS.md §6)

The following are **STOPs during implementation**:

- A `MissionManager.initialize()` modification that **removes** an existing call.
- A `SwarmOrchestrator.spawn_task()` modification that changes its public signature.
- A new dependency that has not been added to `pyproject.toml` and pinned.
- A migration script that mutates columns added by Phases 26/27/43/44 in a backwards-incompatible way.
- An attempt to write a dashboard that requires raw prompt text in its view.
- **(CR-1, 2026-07-08)** Any code path that mutates mission state outside of `MissionActor`
  methods. This includes `MissionManager`, the scheduler, the recovery manager, and the
  distributed router. They may **invoke** actor methods; they may **not** write to DB
  directly for mission state.
- **(CR-2, 2026-07-08)** Any code in `ScheduledMissionDispatcher` (or any successor) that
  calls a method on `MissionManager`, `MissionActor`, `SwarmOrchestrator`, or any
  executor. The scheduler's only outputs are the `scheduler.fire` event and
  `MissionManager.create_mission()` invocation.
- **(architect recommendation 2026-07-08)** Renaming, deleting, or repurposing any of the
  8 mission lifecycle event topics in §4.1 once they are frozen in M6.1.A. Any change
  must be a fresh CR per AGENTS.md §8.
- **(architect recommendation 2026-07-08)** `DistributedRouter` (or any consumer) speaking
  to a concrete network client (Redis/RabbitMQ/gRPC) instead of the `MissionTransport`
  protocol. New transports must be added under `core/mission/transports/`.
- **(CR-3.5, 2026-07-08)** Any removal, rename, or rewrite of an existing Phase 34
  persistence model (`MissionModel`, `MissionCheckpointModel`, `MissionTimelineModel`)
  or of an existing Phase 34 column on those tables. Phase 45 migrations are
  additive-only. Schema-shape changes to Phase 34 columns require an explicit CR
  approved by the architect.
- **(CR-3.3, 2026-07-08)** Any introduction of a second event taxonomy alongside the 8
  frozen events in §4.1. MissionActor owns lifecycle semantics; the existing
  `EventBusInterface` (`core/interfaces.py`) owns transport. Single taxonomy.

---

## 10. Out of Scope (Non-Goals)

- ❌ Rewriting Goals #1-5 components.
- ❌ Distributed tracing across multiple hosts (single-leader scope).
- ❌ Multi-region leader election (single-region only; stretch covers single-DC).
- ❌ A web frontend dashboard. Terminal + REST + WebSocket only.
- ❌ Live LLM API pricing lookups — use static pricing map from Phase 27.
- ❌ Skill/sandbox changes — Phase 18 container isolation remains the security boundary.

---

## 11. Future Extension (post-Goal-#6)

- **6.6 Multi-region Federation:** Cross-DC leader election (Phase 31 hints at this).
- **6.7 Adaptive Scheduler:** ML-driven trigger-time prediction.
- **6.8 State Diffing:** Snapshot-based mission branching & replay UI.

---

## 12. Related Documents

- [60_MASTER_INDEX.md](file:///e:/jarvis/docs/60_MASTER_INDEX.md)
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [08_AI_AGENT_CONSTITUTION.md](file:///e:/jarvis/docs/08_AI_AGENT_CONSTITUTION.md)
- [39_OBSERVABILITY_STANDARD.md](file:///e:/jarvis/docs/39_OBSERVABILITY_STANDARD.md)
- [40_PERFORMANCE_STANDARD.md](file:///e:/jarvis/docs/40_PERFORMANCE_STANDARD.md)
- [41_TESTING_STANDARD.md](file:///e:/jarvis/docs/41_TESTING_STANDARD.md)
- [44_GIT_WORKFLOW.md](file:///e:/jarvis/docs/44_GIT_WORKFLOW.md)
- [47_QUALITY_GATES.md](file:///e:/jarvis/docs/47_QUALITY_GATES.md)
- [48_FAILSAFE_AND_ROLLBACK.md](file:///e:/jarvis/docs/48_FAILSAFE_AND_ROLLBACK.md)
- [72_RECOVERY_MODE.md](file:///e:/jarvis/docs/72_RECOVERY_MODE.md)
- [73_HEALTH_MONITORING.md](file:///e:/jarvis/docs/73_HEALTH_MONITORING.md)
- [87_PHASE_26_MULTI_AGENT_PERSISTENT_RECOVERY_SPECIFICATION.md](file:///e:/jarvis/docs/87_PHASE_26_MULTI_AGENT_PERSISTENT_RECOVERY_SPECIFICATION.md)
- [88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md](file:///e:/jarvis/docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md)
- [106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md](file:///e:/jarvis/docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md)
- `docs/goal6_scope.md` (informal scope — superseded by this spec)
- `docs/sequence_diagram.md` (mission lifecycle reference)
- **`docs/mission_state_machine.md` (authored in M6.1.A — the canonical state diagram
  for the 8 lifecycle events above; required reading for any future contributor working
  on mission lifecycle code).**

---

## 13. State Machine Reference

The full mission state diagram is documented in `docs/mission_state_machine.md`,
authored in M6.1.A. It captures:

- The 8 lifecycle events listed in §4.1 (frozen once written).
- The transitions: `CREATED → QUEUED → RUNNING ↔ PAUSED → COMPLETED`, plus the
  `FAILED → RECOVERING → RUNNING` recovery loop.
- A Mermaid diagram so future contributors have the canonical picture without
  re-deriving it from code.

The state-machine doc is the source of truth for **what is and isn't a valid transition**.
Any future change to a state shape MUST be coordinated through it.
