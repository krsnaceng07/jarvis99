# 108_PHASE_45_IMPLEMENTATION_PLAN.md

## Status
**STATUS:** IMPLEMENTATION PLAN (**APPROVED + FROZEN** — 2026-07-08, architect-approved with A-1..A-4 immutable architecture invariants + CR-3 spec reconciliation)
**Authority:** Rank 5 (Implementation Plan; **must not** introduce architecture — derives from FROZEN `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` only)
**Bound Spec:** `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` (**v1.2 FROZEN** 2026-07-08, CR-1 + CR-2 + **CR-3** applied)
**Predecessor Milestones:** v0.9.0-rc2 (1711/1711 tests passing, Goals #1-5 + RC fixes, FROZEN 2026-07-08)
**Approval record:** architect-approved 2026-07-08; A-1..A-4 recorded as immutable plan-level invariants; M6.4.A strengthened to require exhaustive LocalTransport testing before M6.4.B; **CR-3 (Phase 34 canonical + additive migration + single event taxonomy) reconciled the spec-vs-implementation Conflict Report surfaced during M6.1.A pre-flight; spec v1.2 is now FROZEN under CR-3.**

> **Spec-first rule:** This plan introduces **no new architecture, contracts, API shapes,
> invariants, or lifecycle rules** beyond what `docs/107` (FROZEN) authorises. If a
> contradiction appears, the spec wins and this plan must be amended with architect
> approval (per AGENTS.md §1 authority ranking and §6.1).

---

## 1. Purpose

Translate the FROZEN Phase 45 spec into an executable, gated milestone plan. Each
milestone is independently shippable with its own quality gate. The plan delivers
Goal #6 — Persistent Autonomous Runtime across five sub-goals (6.1, 6.2, 6.3, 6.4, 6.5).

---

## 2. Build Sequence

The order below is **architect-approved** (2026-07-08): foundational first, distributed
last. Each sub-goal is gated.

```
        ┌─────────────────────┐
        │       M6.1.A        │  MissionActor foundation + frozen event taxonomy
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       M6.1.B        │  MissionManager rehydration + e2e kill-resume
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       M6.3.A        │  MissionRecoveryManager + orphan detection + replay
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       M6.3.B        │  Dead-letter queue + replay REST endpoint
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       M6.2.A        │  ScheduledMissionDispatcher + triggers table
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       M6.2.B        │  Scheduler REST endpoints + idempotency tests
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       M6.5.A        │  Mission dashboard views + REST endpoint (events-first)
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       M6.5.B        │  WebSocket fanout + rich terminal dashboard
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       M6.4.A        │  MissionTransport protocol + LocalTransport + WorkerProcess
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       M6.4.B        │  DistributedRouter + RemoteTransport (Redis)
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       M6.4.C        │  Leader election (stretch) + horizontal scaling tests
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │       FINAL         │  v0.10.0 freeze gate + walkthrough
        └─────────────────────┘
```

**Why this order:**
- **6.1 first** — MissionActor is the SoT for state; nothing else can be principled without it.
- **6.3 before 6.2** — recovery depends on persistence; scheduler fires benefit from recovery.
- **6.2 before 6.5** — dashboard views cover scheduled missions too.
- **6.5 before 6.4** — dashboard is local-only; distributed comes last to keep CI simple.

---

## 3. Milestone Breakdown

Per-milestone contract: each lands a milestone report (AGENTS.md §10) and passes its
**mini quality gate** (`ruff format` + `ruff check` + `mypy` strict + `pytest` on
affected files + `pytest --cov` ≥ 80% on affected modules).

### M6.1.A — MissionActor Foundation

| Field | Value |
|---|---|
| **Goal** | Establish `MissionActor` as the SoT (CR-1). Freeze the 8-event taxonomy. Ship the additive persistence columns (CR-3.4). |
| **Deliverables (CR-3 corrected paths)** | `core/runtime/mission_actor.py` (NEW — write gateway for NEW Phase 45 lifecycle paths per CR-3.2); `core/runtime/mission_events.py` (NEW — frozen 8-event taxonomy + payload dataclasses, A-3); `core/runtime/mission_checkpoint.py` (NEW — msgpack+zstd actor-side serialization, A-4 replay-safe); `alembic/versions/0045_actor_columns.py` (ADDITIVE columns only — never rename existing tables per CR-3.4 / CR-3.5); `tests/test_mission_actor.py` (≥10 unit + event contract + replay); `tests/test_mission_compat.py` (≥5 compatibility tests against Phase 34 MissionManager — legacy direct mutations remain in place); `docs/mission_event_contract.md` (event payload schemas + ordering + versioning + backward-compat); `docs/r1_synthetic_event_review.md` (R1 mitigation: pre-freeze event audit); `docs/mission_state_machine.md` re-marked FROZEN-draft → FROZEN. |
| **Test delta** | ≥ 15 new tests (≥10 actor + ≥5 compat) |
| **Frozen files touched** | NONE — `core/runtime/mission.py` and `core/runtime/mission_models.py` are FROZEN Phase 34; CR-3.1 makes Phase 34 canonical. New code lives alongside, not in place of. |
| **Architect reviewer** | Required at mini-gate; spec §4.1 / §9 (P-1, P-2, P-3) + plan §8.1 (A-1..A-4) must hold |
| **Blockers for next** | event taxonomy must be FROZEN before M6.5 work starts |
| **Coverage target** | ≥ 90% on `core/runtime/mission_actor.py` (security-adjacent: it owns state) |
| **CR-3 alignment** | Spec v1.2 (FROZEN) is the binding source of truth. v1.1's wrong paths (`core/mission/mission_actor.py`, `0045_mission_persistence.py`, "new mission_checkpoints v2 table") are superseded. Single event taxonomy only (the 8 in spec §4.1) — no parallel event system (CR-3.3). Legacy Phase 34 MissionManager direct DB mutations remain in place (CR-3.2 — tracked as Phase 46 technical debt). |

### M6.1.B — Rehydration + Kill-Resume E2E

| Field | Value |
|---|---|
| **Goal** | `MissionManager` rehydrates missions from DB on boot; lossless kill-resume e2e. |
| **Deliverables** | `MissionManager._rehydrate_actors_from_db()` (new method — does not modify existing init); `api/routes/mission_lifecycle.py` (GET `/api/v1/missions/{id}/checkpoint`, POST `/force-checkpoint`); `tests/test_mission_rehydration.py` (≥5 tests including kill-resume e2e). |
| **Test delta** | ≥ 5 new tests |
| **Frozen files touched** | NONE (MissionManager.initialize() gets a new method called at end, no removal/modification of existing calls) |
| **Coverage target** | ≥ 85% on `mission_lifecycle.py` route module |

### M6.3.A — MissionRecoveryManager

| Field | Value |
|---|---|
| **Goal** | Detect orphaned missions (RUNNING with stale heartbeat > 30s) and replay them from last checkpoint via 6.1's checkpoint store. At-least-once semantics. |
| **Deliverables** | `core/mission/mission_recovery.py`; Alembic migration `0047_mission_recovery.py` (mission_recovery_journal table); `tests/test_mission_recovery.py` (≥18 tests; chaos: SIGKILL mid-wave + restart). |
| **Test delta** | ≥ 18 new tests |
| **Coverage target** | ≥ 90% on `mission_recovery.py` (security-adjacent) |
| **Architect reviewer** | Required; must verify R-1 + wave_run_id idempotency |

### M6.3.B — Dead-Letter Queue + Replay Endpoint

| Field | Value |
|---|---|
| **Goal** | After 3 consecutive recovery failures, missions move to `mission_dead_letters`; `/api/v1/missions/{id}/replay` allows manual retry. |
| **Deliverables** | Migration `0047b_mission_dead_letters.py` (mission_dead_letters table — payload_snapshot stored after secret-redaction pass); `POST /api/v1/missions/{id}/replay` endpoint; `tests/test_mission_dead_letter.py` (≥8 tests). |
| **Test delta** | ≥ 8 new tests |
| **Security gate** | Secret-pattern redaction in `payload_snapshot` per docs/29; verified by tests |

### M6.2.A — ScheduledMissionDispatcher + Triggers Table

| Field | Value |
|---|---|
| **Goal** | Schedule missions: ONE_SHOT / CRON / INTERVAL triggers with idempotency (CR-2: scheduler enqueues only). |
| **Deliverables** | `core/mission/scheduled_mission_dispatcher.py`; Alembic migration `0046_scheduler_triggers.py` (scheduler_triggers table); `pyproject.toml` dep `croniter>=2.0` pinned; `tests/test_scheduled_dispatcher.py` (≥12 tests; idempotency stress test). |
| **Test delta** | ≥ 12 new tests |
| **Architect reviewer** | Required; S-3 (CR-2) must hold — scheduler must not import MissionManager's execution methods |

### M6.2.B — Scheduler REST Endpoints + Idempotency Tests

| Field | Value |
|---|---|
| **Goal** | CRUD on `/api/v1/scheduler/triggers`. |
| **Deliverables** | `api/routes/mission_schedule.py` (GET / POST / PATCH / DELETE); `tests/test_scheduler_api.py` (≥6 tests, including idempotency under concurrent fire). |
| **Test delta** | ≥ 6 new tests |

### M6.5.A — Mission Dashboard Views + REST Endpoint

| Field | Value |
|---|---|
| **Goal** | 4 SQL views + REST snapshot. **Hard dependency on M6.1.A event-taxonomy freeze.** |
| **Deliverables** | `db/migrations/versions/0049_mission_dashboard_views.py` (4 read-only views); `api/routes/mission_dashboard.py` (GET `/api/v1/missions/dashboard`); `tests/test_mission_observability.py` (≥10 tests; verifies dashboard output derives only from the 8 frozen events). |
| **Test delta** | ≥ 10 new tests |
| **Architect reviewer** | Required; O-1 (no secrets in views) + O-2 (read-only) must hold |

### M6.5.B — WebSocket Fanout + Terminal Dashboard

| Field | Value |
|---|---|
| **Goal** | Live mission state via WS; rich TUI dashboard. |
| **Deliverables** | WebSocket `/ws/v1/missions/dashboard` (consumes 8 frozen events); `core/cli/mission_dashboard.py` (rich-based TUI); `pyproject.toml` dep `rich>=13.0` pinned; `tests/test_mission_dashboard_ws.py` (≥8 tests). |
| **Test delta** | ≥ 8 new tests |

### M6.4.A — MissionTransport Protocol + LocalTransport + Worker CLI

| Field | Value |
|---|---|
| **Goal** | Transport abstraction. **NO network code yet.** In-process LocalTransport for tests + dev. **Exhaustively test LocalTransport contract BEFORE any network code lands** (architect directive 2026-07-08). |
| **Deliverables** | `core/mission/transports/__init__.py` (re-export protocol); `core/mission/transports/local.py`; `core/mission/mission_transport.py` (protocol definition); `core/mission/worker_process.py` (CLI entry point); `core/mission/worker_registry.py`; Alembic migration `0048_worker_registry.py` (worker_registry table); `tests/test_distributed_router.py` (≥12 tests against LocalTransport); **`tests/test_local_transport_exhaustive.py` (NEW — boundary, ordering, idempotency, lease-acquire, lease-renew, lease-release, payload-serialization edge cases — at least 25 tests covering every protocol method).** |
| **Test delta** | ≥ 12 new tests + ≥ 25 LocalTransport exhaustive tests |
| **Architect reviewer** | Required; verify transport protocol surface matches spec §4.4 |
| **LocalTransport-first contract (architect directive 2026-07-08)** | If LocalTransport contract is correct, RemoteTransport is mostly a serialization problem. M6.4.B MUST NOT start until M6.4.A's exhaustive LocalTransport suite passes AND architect signs off that the protocol surface is final (no shape changes allowed post-M6.4.A). |
| **No Redis dep yet** | Adding `redis>=5.0` is deferred to M6.4.B |

### M6.4.B — DistributedRouter + RemoteTransport (Redis) + Envelope (D-5) + Runtime Idempotency (D-4)

| Field | Value |
|---|---|
| **Goal** | Real network transport; routing policy enforcement; routing log auditability; envelope-versioned wire format; runtime idempotency for at-least-once delivery. |
| **Invariants adopted (CR-4, 2026-07-09)** | **D-4** (transport at-least-once / runtime exactly-once via `wave_run_id` idempotency); **D-5** (versioned transport envelope independent of mission DTOs). |
| **Deliverables** | `core/mission/transports/envelope.py` (NEW — `TransportEnvelope` Protocol + `EnvelopeV1` impl + `EnvelopeV1Dto`); `core/mission/transports/redis.py` (REPLACE STUB → real `RemoteTransport`: publish/subscribe over Redis pub/sub, leases via `SET NX PX` + Lua compare-and-renew, envelope (de)serialization); `core/mission/transports/__init__.py` (MODIFY additive — re-export envelope symbols); `core/mission/distributed_router.py` (MODIFY additive — REMOTE_PREFERRED behavior + idempotent `route()` + idempotent `active_tasks` accounting); `core/mission/worker_registry.py` (MODIFY additive — `mark_task_started` / `mark_task_completed` keyed on `wave_run_id`); `pyproject.toml` — `redis>=5.0.4` already pinned (M6.4.A baseline); add `fakeredis>=2.20` to `[dependency-groups].dev` for hermetic CI; alembic migration co-located in `0049_worker_registry.py` per CR-2 (no new migration needed); `tests/test_transport_envelope.py` (NEW ≥ 10 tests); `tests/test_redis_transport.py` (NEW ≥ 25 tests using `fakeredis`); `tests/test_distributed_router_remote_preferred.py` (NEW ≥ 10 tests). |
| **Test delta** | ≥ 45 new tests (≥ 10 envelope + ≥ 25 redis + ≥ 10 router REMOTE_PREFERRED) |
| **Architect reviewer** | Required; D-4 + D-5 must hold; D-3 (existing) must continue to hold |

### M6.4.C — Leader Election (stretch) + Horizontal Scaling Tests

| Field | Value |
|---|---|
| **Goal** | Optional Redis SETNX-based lease prevents two-leader split-brain. Horizontal scaling acceptance. |
| **Deliverables** | Leader-election hooks in `RemoteTransport.lease/renew_lease/release_lease`; `tests/test_leader_election.py` (≥8 tests including split-brain simulation). |
| **Test delta** | ≥ 8 new tests |
| **Status** | **STRETCH** — may be deferred if M6.4.B consumes the time budget |

### FINAL — v0.10.0 Freeze Gate

| Field | Value |
|---|---|
| **Goal** | All five sub-goals closed; freeze as v0.10.0. |
| **Deliverables** | Full quality gate (ruff format/check, mypy strict, pytest full suite, coverage ≥ 80% / 100% security modules, `scripts/dgv.py` clean, architecture-linter clean); Walkthrough doc; Phase 45 spec STATUS remains FROZEN; AGENTS.md §12 row bumped to v0.10.0 with test count; CHANGELOG entry. |
| **Test delta** | (subsumed; target ≥ 1888 total = 1711 + ≥ 116 new) |
| **Approval gate** | Architect approval required before declaring FINAL closed |

---

## 4. Risk Register

| # | Risk | Mitigation |
|---|------|-----------|
| **R1** | Event-taxonomy freeze becomes too restrictive (forgot an event). | M6.1.A includes a **review pass** before freeze: run a 30-minute synthetic mission, capture every emitted event, compare to the 8 listed in `docs/mission_state_machine.md`. Any gap is a CR (not a silent addition). |
| **R2** | MissionActor DB write-through latency hurts mission throughput. | DB writes happen at state boundaries (events emitted per state change), not per-step. If profile shows M6.1.B > 50ms added per transition, escalate to M6.1.B', not silently re-architect. |
| **R3** | `croniter` adds a dep we later regret. | Pinned in pyproject.toml in M6.2.A; if a future goal wants cron-free scheduling, can be removed under one milestone. |
| **R4** | Redis becomes a hard dep for 6.4. | `RemoteTransport` is one of many transports under `transports/`. CI default is `LocalTransport`. Redis is only required when the user opts into `RemoteTransport`. |
| **R5** | Dead-letter payloads leak secrets. | `payload_snapshot` is run through `core/secrets/redact.py` (`docs/29_SECRET_MANAGEMENT.md`) before persistence; `M6.3.B` includes a test that puts a fake API key in the last checkpoint and asserts it appears as `<redacted>` in the dead letter. |
| **R6** | Concurrent scheduler replicas double-fire a cron. | S-2 invariant + idempotency tests in M6.2.B (concurrent fire with 5 replicas for the same trigger). |
| **R7** | Leader election causes split-brain if Redis goes down. | M6.4.C is **stretch**. The shipped M6.4.B default is single-leader; on Redis loss, leader continues (degraded, no failover). Documented in spec. |

---

## 5. Mini Quality Gate Definition (per AGENTS.md §5 + §9.1)

For every milestone:

1. `ruff format --check core/mission/ tests/test_mission_*.py api/routes/mission_*.py` → clean.
2. `ruff check <touched files>` → zero errors/warnings (use `--fix` for the 5 pre-existing import-sort issues; tracked separately, do not let grow).
3. `mypy --strict core/mission/*actor.py core/mission/*recovery.py core/mission/scheduled_* core/mission/distributed* core/mission/worker_*` → zero errors.
4. `pytest tests/test_mission_actor.py tests/test_mission_rehydration.py tests/test_mission_recovery.py tests/test_mission_dead_letter.py tests/test_scheduled_dispatcher.py tests/test_scheduler_api.py tests/test_mission_observability.py tests/test_mission_dashboard_ws.py tests/test_distributed_router.py tests/test_distributed_redis.py tests/test_leader_election.py tests/test_goal6_integration.py -q` → all pass; suite total ≥ 1711 + cumulative deltas.
5. `pytest --cov=core/mission --cov-report=term-missing` → ≥ 85% line coverage on new modules; ≥ 90% on security-adjacent (mission_recovery, mission_actor, transports/redis).
6. **`scripts/dgv.py` and `architecture-linter`** → zero violations (no new layer-direction errors).
7. **STOP conditions §9 of spec**: not triggered.

---

## 6. Cross-Sub-Goal Regression Discipline

After **each** milestone, all 1711 v0.9.0-rc2 tests MUST still pass. Concrete rule:

```bash
$env:TMPDIR = "<workspace>/.pytest_tmp"  # clean dir per run on Windows
pytest tests/ -q --tb=short -p no:cacheprovider
# expected: 1711 + cumulative_new passed, 0 failed
```

If a milestone regresses an existing test, **STOP** per AGENTS.md §6.

---

## 7. Approval Workflow

| Step | Action | Required approver |
|---|---|---|
| 1 | This plan is approved by architect | **You (now)** |
| 2 | Each milestone emits its report (§10 format) | architect review at mini-gate |
| 3 | FINAL milestone emits v0.10.0 walkthrough | architect final approval |
| 4 | v0.10.0 tag created; AGENTS.md §12 + dashboard bumped | post-freeze |

The agent **will not** write implementation code for any milestone until this plan is
marked APPROVED.

---

## 8. STOP Conditions (plan-level reinforcement)

In addition to spec §9 STOPs, the following halt implementation of *this plan*:

- **M6.1.A** is held until event-taxonomy review pass is completed (see R1).
- **M6.5.B** is held until M6.5.A passes with no event-derived view leak.
- **M6.4.B** is held until M6.4.A passes with no network code present (LocalTransport only).
- **M6.4.C** is held indefinitely if M6.4.B fails its quality gate.
- **FINAL** is held until ALL preceding milestones pass.
- Any change to milestone deliverables, dependencies, or test delta above requires an
  amendment of this plan with architect approval.

---

## 8.1 Architecture Invariants (architect-recorded 2026-07-08 — IMMUTABLE)

The following invariants are recorded as **plan-level immutable rules**. They apply to
every milestone in Phase 45 and bind the agent's runtime behaviour. They are equal in
force to spec §5 invariants (G-1..G-5). They are NOT to be relaxed, modified, or
"interpreted away" during implementation. Any change requires a fresh CR per AGENTS.md §8.

| # | Invariant | Enforcement |
|---|-----------|-------------|
| **A-1** | **MissionActor owns mission state.** Layer rule: `API → MissionManager → MissionActor → Persistence`. No component may mutate mission state by bypassing `MissionActor` (read is allowed; write is forbidden outside actor methods). | Code review at every milestone; linter rule: `mission_state_must_route_through_actor.py` (M6.1.A deliverable). |
| **A-2** | **Event-first architecture.** State change is never silent. The model for Phase 45 is **persist → publish → observers react** (single model, used everywhere — no mixing). Persist checkpoint first; publish event; observers react asynchronously. Event ordering MUST match DB checkpoint order. | MissionActor implementation; `mission_event_contract.md` §"Ordering" pins the model. |
| **A-3** | **Event payload freeze.** Event names AND payload schemas are contracts. Every mission lifecycle event payload carries: `mission_id` (UUID), `state` (str), `timestamp` (ISO-8601 UTC), `correlation_id` (UUID), `source` (str — actor method name), `version` (int — schema version, currently `1`). Adding optional fields is OK with a `version` bump; renaming or removing fields requires a fresh CR. | `core/mission/events.py` constants + dataclasses; `mission_event_contract.md` schema table; tests assert payload shape. |
| **A-4** | **Replay-safe checkpoints.** A checkpoint must be sufficient to recover a mission **without hidden in-memory state**. The checkpoint payload must contain every value needed to reconstruct actor state: `wave_idx`, `goal`, `plan_snapshot`, `agent_assignments`, `lifecycle_timeline`, `checkpoint_seq`. No actor method may rely on a value that is not in the latest checkpoint. | MissionActor implementation + checkpoint tests; review audit at M6.1.A and M6.3.A. |
| **A-5** | **Legacy callers are oblivious.** Legacy Phase 34 code MAY continue reading and writing legacy fields (`status`, `goal`, `plan_data`, `assigned_agents`, `budget_limit`, `budget_used`, `current_step`, `step_index`, `state_data`, etc.). New Phase 45 functionality MUST NOT require legacy callers to understand any new field, event, or column. Phase 45 additive columns MUST NULL gracefully when a Phase 34 caller writes a row (legacy compatibility), and Phase 45 readers MUST treat NULL additive columns as "legacy row, fall back" — never as "data missing". | MissionActor implementation; compat tests in `tests/test_mission_compat.py`; A-5 linter extension at M6.1.B (`mission_state_must_route_through_actor.py` rejects lints that would break legacy obliviousness). |

**Cross-reference:**
- A-1 ≡ spec CR-1 + invariant P-3.
- A-2 ≡ spec invariant P-1 (DB write before cache update).
- A-3 ≡ spec §9 STOP condition (event renaming requires CR); extends it to payload.
- A-4 ≡ spec §4.1 ("rehydrated via `MissionActor`") + R5 risk (no hidden memory in dead-letter payload).
- A-5 ≡ spec §5 (new at M6.1.A approval, 2026-07-08). Backward-compatibility — legacy Phase 34 callers do not need to understand Phase 45 changes.

**Binding decisions:**
- **ADR-45-01** (2026-07-08, architect-approved at M6.1.A gate): `core/runtime/mission_models.py` MAY receive additive SQLAlchemy column declarations. This is **NOT** a Phase 34 modification — the original methods and the original columns are untouched. See `docs/109_ADR_45_01_ADDITIVE_ORM_COLUMNS.md` for the binding clarification.

---

## 8.2 Reporting Cadence (architect directive 2026-07-08)

Every milestone report (mini-gate and FINAL) uses this format, in this order:

```
MILESTONE <ID> REPORT

Milestone:               <M-id + title>
Status:                  <APPROVED / BLOCKED>

Files changed:
  - <path>               <+new / ~modified>  <role>
  ...

Architecture impact:    <additive / refactor / <CR-XXX> / none>
Public interface changes: <none / list with rationale>
Frozen files touched:    <NONE / list — every entry must justify against spec §4 / plan §8.1>

Tests added:             <count>  (<paths>)
Tests passing:           <total>  (<delta>)
Coverage (affected):     <%>      (target ≥85% / ≥90% security-adjacent)

Risk changes:            <list — any new R# added or existing R# updated>
Decision needed:         <none / explicit ask to architect>
```

The format is review-friendly: an architect can read it top-to-bottom in 60 seconds and
make a gate decision. The agent MUST NOT deviate from this format inside Phase 45.

---

## 9. Out-of-Plan Items (deferred)

These were considered and explicitly **NOT** in scope of this plan:

- GraphQL or gRPC interfaces for mission control (REST only; see spec §6).
- Cost-based auto-scaling of distributed workers (Phase 27 cost governance already
  provides per-process budgets; cross-worker scaling is a future goal).
- UI dashboard beyond rich TUI (web frontend deferred; see spec §10).
- A migration downgrade path — new migration scripts are forward-only. A downgrade
  procedure can be authored post-freeze if needed.

---

## 10. Cross-References

- **Spec (FROZEN):** `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md`
- **State Machine (FROZEN-draft → FROZEN at M6.1.A):** `docs/mission_state_machine.md`
- **Goal #6 informal scope:** `docs/goal6_scope.md` (historical; superseded by spec)
- **Sequence diagram (mission lifecycle reference):** `docs/sequence_diagram.md`
- **Predecessor:** v0.9.0-rc2 commit `b3a1e70` — Goals #1-5 + RC fixes
- **Authoritative governance:** `AGENTS.md`
- **Authority ranking:** AGENTS.md §1; rank 5 (this plan) yields to rank 4 (spec).

---

## 11. Plan Sign-Off

This plan is **APPROVED + FROZEN** as of 2026-07-08 (architect-approved with A-1..A-5
immutable invariants recorded in §8.1 — A-5 added at M6.1.A gate review 2026-07-08;
LocalTransport-exhaustive testing added to M6.4.A; reporting cadence pinned in
§8.2; CR-3 reconciled spec-vs-implementation Conflict Report — spec is now v1.2
FROZEN at `docs/107`; ADR-45-01 recorded as binding decision for additive ORM
columns).

**M6.1.A scope is now open** (CR-3 approved 2026-07-08; deliverables and paths
corrected in §3 above). Implementation may begin against spec v1.2; the next gate is
the M6.1.A mini quality gate per AGENTS.md §10.
