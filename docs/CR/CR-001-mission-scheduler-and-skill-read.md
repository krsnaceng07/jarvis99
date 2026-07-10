# CR-001 — GoalScheduler DI Registration & `skill.read` Permission Seed

**Status:** ✅ APPROVED (2026-07-10) — code merged, validation complete, spec deltas applied
**Date:** 2026-07-10
**Proposer:** Mavis (orchestrator session `mvs_1eef650acaf648eb92f68ce6275350e9`)
**Approver:** Architect (Rank 0) — verbal approval in session after CR review
**Type:** Frozen-phase correction (functional gap, not new feature)
**Frozen phases touched:** Phase 44 (Mission Scheduler), Phase 17 (Authentication & Authorization)
**Spec versions affected:** `docs/106_PHASE_44_*` (v1.0 → v1.1), `docs/78_PHASE_17_*` (v1.0 → v1.1)
**Validation outcome:** Both fixes verified correct; capability-matrix gate stayed red because of a separate, unrelated bug (see §9)

---

## 1. Summary

Two related server-side gaps were discovered while finishing the in-process startup validation work. Neither is a probe or test issue; both are missing wires in the production boot path of frozen phases. Together they make 2 of the 20 capability-matrix probes return 5xx / 401 instead of 200, blocking the validation gate from turning green.

| # | Probe | Symptom | Root cause | Frozen phase |
|---|-------|---------|------------|--------------|
| 1 | `scheduler.list` (`/api/v1/scheduler/queue`) | 500 `SYSTEM_001` | `GoalScheduler` never registered in kernel DI | Phase 44 |
| 2 | `capabilities.discover` (`/api/v1/discover`) | 401 `AUTH_006` | `skill.read` scope not in seed permissions | Phase 17 |

---

## 2. Bug 1 — `GoalScheduler` not registered (Phase 44)

### 2.1 Reproduction

```text
GET /api/v1/scheduler/queue
Authorization: Bearer <admin token>
→ 500 Internal Server Error

{
  "success": false,
  "error": {
    "code": "SYSTEM_001",
    "message": "Failed to resolve dependency for type 'GoalScheduler':
                No service registered for interface 'GoalScheduler'."
  }
}
```

### 2.2 Root cause

`api/routes/mission_scheduler.py:329` declares:

```python
async def get_queue(
    scheduler: Any = Depends(get_goal_scheduler),
) -> List[QueueItemResponse]:
```

`api/dependencies.py:403-409` resolves from the kernel container:

```python
def get_goal_scheduler(kernel: Kernel = Depends(get_kernel)) -> Any:
    from core.mission.mission_scheduler import GoalScheduler
    return kernel.container.resolve(GoalScheduler)
```

`core/kernel.py` `boot()` method registers ~50 services via
`self.container.register_singleton(...)` (lines 75–1005, confirmed via grep), but
**never calls `register_singleton(GoalScheduler, ...)`**. The Phase 44 spec
(`docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md` §2 Architecture diagram)
explicitly positions `GoalScheduler` as the top-level orchestrator that depends on
`GoalDependencyResolver`, `PriorityEngine`, `DeadlineManager`,
`ExecutionBudgetManager`, `MissionRecovery`, `BackgroundGoalRunner`, and
`MissionQueue`. The class exists (`core/mission/mission_scheduler.py:292`) but is
not instantiated or registered.

### 2.3 Proposed fix

Add a new section to `core/kernel.py` `boot()` after the Swarm block (around
line 494) and before the next major block:

```python
# ── Phase 44: Mission & Autonomous Goal Scheduler ──────────────────────
try:
    from core.mission.mission_scheduler import (
        BackgroundGoalRunner,
        DeadlineManager,
        ExecutionBudgetManager,
        GoalDependencyResolver,
        GoalScheduler,
        MissionQueue,
        MissionRecovery,
        PriorityEngine,
    )

    mission_queue = MissionQueue()
    dependency_resolver = GoalDependencyResolver()
    priority_engine = PriorityEngine()
    deadline_manager = DeadlineManager()
    budget_manager = ExecutionBudgetManager()
    mission_recovery = MissionRecovery()

    goal_scheduler = GoalScheduler(
        queue=mission_queue,
        dependency_resolver=dependency_resolver,
        priority_engine=priority_engine,
        deadline_manager=deadline_manager,
        budget_manager=budget_manager,
        recovery=mission_recovery,
        event_bus=event_bus_instance,
    )
    self.container.register_singleton(GoalScheduler, goal_scheduler)
    self.container.register_singleton(MissionQueue, mission_queue)
    self.lifecycle_manager.add_service(goal_scheduler)
except Exception as e:
    logger.warning("Phase 44 MissionScheduler registration failed: %s", str(e))
```

The exact constructor signature must be re-verified against
`core/mission/mission_scheduler.py:292` before merge. If the signature differs,
the change is a 1-line edit inside this block — still CR-gated, but small.

**Wrapped in `try/except` + `logger.warning`** (matching the existing pattern at
`api/main.py:140-141` for dynamic skills registration) so a Phase 44 init failure
does not block kernel boot — the rest of JARVIS stays up, and the route surfaces
the same `SYSTEM_001` 500 it does today, until Phase 44 is fully wired.

### 2.4 Risk & benefit

- **Risk:** LOW. Pure addition; no modification of existing registrations, no
  contract change. The route, dependency function, spec, and class all already
  exist — only the wire is missing.
- **Benefit:** Makes the 7 `/api/v1/scheduler/*` endpoints functional; matches
  the Phase 44 architecture diagram; unblocks `scheduler.list` capability probe;
  enables the BackgroundGoalRunner to start draining the queue (which is the
  whole point of Phase 44).
- **Backward compatibility:** None of the existing 50+ registered services
  change behavior. Routes that 500 today will start returning 200/4xx; routes
  that already 200/4xx are untouched.

---

## 3. Bug 2 — `skill.read` not in default seed (Phase 17)

### 3.1 Reproduction

```text
GET /api/v1/discover
Authorization: Bearer <admin token>
→ 401 Unauthorized

{
  "success": false,
  "error": {
    "code": "AUTH_006",
    "message": "Insufficient permissions to access this resource."
  }
}
```

The admin token *should* grant `skill.read` because the admin role currently
grants every seeded scope (line 65: `"admin": scopes`). But `scopes` (line 45) does
not include `skill.read`.

### 3.2 Root cause

`core/security/seed_service.py:45-53` seeds only:

```python
scopes = [
    "agent.execute",
    "agent.read",
    "workflow.execute",
    "workflow.read",
    "audit.read",
    "vault.admin",
    "platform.admin",
]
```

Phase 41 (`docs/103_PHASE_41_CAPABILITY_REGISTRY_SPECIFICATION.md`) introduced
the `_require_read = require_permissions(["skill.read"])` guard on
`api/routes/capabilities.py:27`. Phase 41 was frozen after Phase 17, so the seed
was never updated to include the new scope. The admin role gets every seeded
scope, but `skill.read` is not seeded, so it doesn't get it.

The `developer` and `viewer` roles are unaffected — they don't get all scopes
and don't need `skill.read` for any documented route. Only the admin role is
broken.

### 3.3 Proposed fix

Add one string to `core/security/seed_service.py:45-53`:

```python
scopes = [
    "agent.execute",
    "agent.read",
    "workflow.execute",
    "workflow.read",
    "audit.read",
    "vault.admin",
    "platform.admin",
    "skill.read",          # ← ADD — Phase 41 capability registry read access
]
```

This is a 1-line addition. Because the admin role's permissions are
re-synced on every boot (line 81: `role.permissions = [permissions_map[s] for s in role_scopes]`),
existing installations will pick up `skill.read` automatically on the next boot —
no DB migration needed, no role re-assignment needed.

The `developer` and `viewer` role definitions are intentionally left alone.
Phase 41's `capabilities.discover` route is documented as admin-tier
infrastructure; non-admin roles can be granted `skill.read` later via RBAC
assignment if a non-admin use case appears.

### 3.4 Risk & benefit

- **Risk:** VERY LOW. Pure addition of one new scope to the seed list. On the
  next boot, the admin role gains `skill.read` — no other change. There is no
  existing route that explicitly forbids `skill.read` for admin (would be
  self-contradictory).
- **Benefit:** Makes `/api/v1/discover` work for admin; unblocks
  `capabilities.discover` capability probe; makes the Phase 41 CapabilityRegistry
  actually discoverable in dev/CI; matches the Phase 41 spec's
  `_require_read` contract.
- **Backward compatibility:** Existing tokens issued before this change do not
  have `skill.read` in their claims. They will continue to fail `skill.read`-gated
  routes until the user re-logs-in (admin role re-evaluation happens on next
  boot, but the token's `permissions` claim is bound at issue time). For local
  dev this is automatic; for production, a one-time token rotation may be
  needed. Documented in the spec delta below.

---

## 4. Files to modify (if approved)

| File | Phase | Status | Change |
|------|-------|--------|--------|
| `core/kernel.py` | 44 | FROZEN | Add new `register_singleton(GoalScheduler, ...)` section (≈30 lines, try/except-wrapped) |
| `core/security/seed_service.py` | 17 | FROZEN | Add 1 line: `"skill.read",` to `scopes` list |

No other files touched. No test files, no API routes, no probe files (the
2 probe-path fixes in `scripts/capability_matrix.py` already merged as a separate
non-frozen edit, see §5).

## 5. Out-of-scope (already done)

The following non-frozen edits are already on disk, uncommitted, and are NOT
part of this CR:

- `scripts/capability_matrix.py` — corrected 2 probe paths:
  - `scheduler.list` → `/api/v1/scheduler/queue` (was probing non-existent `GET /missions`)
  - `capabilities.discover` → `/api/v1/discover` (was probing `/capabilities/discover` which 404s)
- These are probe-spec corrections only; they do not modify any frozen phase.

## 6. Spec deltas to record on approval

Per AGENTS.md §8 step 4 ("Record: CR appended to the affected phase spec; spec
version incremented"):

- `docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md` — add §2.1 "DI
  Registration" subsection stating that `GoalScheduler` must be registered in
  the kernel container at boot time. Bump spec to v1.1.
- `docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md` — add `skill.read`
  to the default permission scope list. Bump spec to v1.1.

## 7. Validation plan (post-approval)

1. Apply §4 edits in a feature branch.
2. Re-run `python scripts/validate_startup.py --in-process` — expect
   `OVERALL: PASS` (15 pass, 0 fail, 5 warn, all 5 warns are documented
   pending-permission cases).
3. Re-run `pytest tests/test_startup_validation.py -q` — must remain green
   (unaffected by these edits).
4. Re-run full test suite — must remain at or above current 1367 baseline.
5. Update `.ai/PROJECT_STATE.md` and Phase 44 freeze status (already FROZEN,
   just append the CR reference).
6. Commit with conventional message and request Gatekeeper re-approval before
   merge.

## 8. STOP & WAIT

Per AGENTS.md §8: **No agent may self-approve a CR. A CR proposal is itself a
STOP-and-wait action.**

This CR is **PROPOSED** until the human architect (Gatekeeper) explicitly
approves. Until then:

- ❌ No code changes to `core/kernel.py` or `core/security/seed_service.py`.
- ✅ The 2 non-frozen probe-path edits in `scripts/capability_matrix.py` may
   remain (they don't touch any frozen phase).
- ✅ The 2 bugs remain open and will continue to cause 500/401 on
   `/api/v1/scheduler/queue` and `/api/v1/discover`.

**Authority invoked:** AGENTS.md §1 Rank 2 (Agent Constitution) → §8 (CR Process)
→ §6.1 (Specification-First Resolution).

---

## 9. Post-Approval Validation Report (2026-07-10)

### 9.1 Mini quality gate (per AGENTS.md §9.1)

| Gate | Tool | Target file | Result |
|------|------|-------------|--------|
| AST parse | `ast.parse` | `core/kernel.py`, `core/security/seed_service.py` | PASS |
| Ruff format | `ruff format --check` | my new code block in `core/kernel.py` | PASS (pre-existing issues elsewhere in the file are out of CR scope) |
| Ruff lint | `ruff check` | both files | PASS (no new violations introduced; 5 pre-existing `I001` import-block warnings remain in `core/kernel.py` at lines 268/343/401/631/771 — out of scope) |
| Mypy strict | `mypy --no-incremental` | both files | PASS — `Success: no issues found in 2 source files` |

### 9.2 Implementation deviation from §2.3

The proposed fix in §2.3 used a hypothetical 7-argument constructor signature
(`queue`, `dependency_resolver`, `priority_engine`, `deadline_manager`,
`budget_manager`, `recovery`, `event_bus`). The actual `GoalScheduler.__init__`
in `core/mission/mission_scheduler.py:302-307` is:

```python
def __init__(
    self,
    config: Optional[SchedulerConfig] = None,
    event_bus: Optional[EventBusInterface] = None,
    executor: Optional[Callable[..., Any]] = None,
) -> None:
```

Internally it instantiates its own `MissionQueue`, `GoalDependencyResolver`,
`PriorityEngine`, `ExecutionBudgetManager`, `DeadlineManager`, and
`MissionRecovery` — none are constructor parameters. The CR's risk note in §2.3
("If the signature differs, the change is a 1-line edit inside this block")
was triggered; the actual implementation is significantly simpler than the
proposed text and omits `lifecycle_manager.add_service(...)` because
`GoalScheduler` does not implement `LifecycleInterface`. Final shape:

```python
# Phase 44 — Mission & Autonomous Goal Scheduler (CR-001)
try:
    from core.mission.mission_scheduler import GoalScheduler

    goal_scheduler = GoalScheduler(event_bus=event_bus)
    self.container.register_singleton(GoalScheduler, goal_scheduler)
except Exception as e:
    logger.warning("Phase 44 GoalScheduler registration failed: %s", str(e))
```

This deviation is **functionally equivalent** to the proposed fix and **safer**
(no attempted calls to a non-existent `LifecycleInterface.add_service`).

### 9.3 Affected test suite

| Suite | Result |
|-------|--------|
| `tests/test_startup_validation.py` | 28/28 PASS |
| `tests/test_mission_scheduler.py` + `tests/test_mission_api.py` + `tests/test_skill_permission_engine.py` | 82/82 PASS |
| Full suite | 1738 passed / 1 failed (pre-existing flake, see §9.5) |

### 9.4 End-to-end probe verification

| Probe | Before CR-001 | After CR-001 (predicted) | After CR-001 (actual) |
|-------|---------------|--------------------------|-----------------------|
| `scheduler.list` → `GET /api/v1/scheduler/queue` | 500 `SYSTEM_001` | 200 | **200** ✅ |
| `capabilities.discover` → `GET /api/v1/discover` | 401 `AUTH_006` | 200 | **404 `SKILL_I007`** (see §9.6) |

The second probe no longer returns 401, which proves the `skill.read` scope is
correctly seeded and granted to the admin role. The new 404 is a separate
issue tracked as **CR-002** (route shadowing by the catch-all skill-dispatch
route).

### 9.5 Pre-existing test flake (NOT a regression)

`tests/test_startup_validation.py::TestInProcessValidation::test_in_process_validation_reports_steps`
fails when run after `tests/test_mission_*` but passes in isolation. Verified
pre-existing by `git stash`-ing the CR-001 changes and reproducing the same
1-fail / 82-pass result on baseline. Root cause: prior tests leave
offset-naive datetimes in the SQLite DB, which crashes
`SwarmResumeManager` during the next in-process boot with
`can't subtract offset-naive and offset-aware datetimes`. Out of scope for
CR-001; recommend a separate test-isolation fix.

### 9.6 Discovered: separate route-shadowing bug (CR-002)

Six of the 20 capability-matrix probes still fail after CR-001 — but for a
**completely different reason** than this CR addressed. Direct probe of
`/api/v1/missions` (with the new admin token that DOES have `skill.read`):

```
HTTP 404
{"success":false,"error":{"code":"SKILL_I007",
 "message":"Skill 'missions' not found.", ...}}
```

Root cause: `GET /api/v1/{skill_id}` (the catch-all skill-dispatch route) is
declared at route-index 29, **before** the real REST routes
(`/api/v1/missions` at 62, `/api/v1/workflows` at 23, etc.). When a request
hits `GET /api/v1/missions`, Starlette matches the parameterized route first
and tries to dispatch to a skill literally named `"missions"`, which does
not exist, returning 404.

Static paths like `GET /api/v1/scheduler/queue` (index 89) happen to win
because Starlette's matcher prefers static segments over parameterized ones
when the path is a single literal segment. Multi-segment paths
(`/missions`, `/workflows`, `/discover`, `/skills`, `/identity`, `/goal`) all
lose to the catch-all.

This is a **separate frozen-phase bug** and will be tracked as **CR-002**
(route-shadowing). CR-001 closes its own scope cleanly and does not
attempt to address CR-002 per AGENTS.md §6.1 (one CR = one concern).

### 9.7 Files actually modified

| File | Phase | Status | Change |
|------|-------|--------|--------|
| `core/kernel.py` | 44 | FROZEN | Added 10-line `register_singleton(GoalScheduler, ...)` block, try/except-wrapped |
| `core/security/seed_service.py` | 17 | FROZEN | Added 1 line: `"skill.read",` to `scopes` list |
| `scripts/capability_matrix.py` | Platform Infra | non-frozen | 2 probe-path corrections (`scheduler.list` → `/api/v1/scheduler/queue`, `capabilities.discover` → `/api/v1/discover`) — pre-existing from earlier session, not part of this CR |
| `docs/CR/CR-001-mission-scheduler-and-skill-read.md` | governance | non-frozen | This document |
| `docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md` | 44 | FROZEN | Bumped to v1.1; added §2.1 "DI Registration" subsection |
| `docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md` | 17 | FROZEN | Bumped to v1.1; added CR-001 row to Change Control Log |

### 9.8 Status

**CLOSED.** Both fixes verified correct, spec deltas applied, validation plan
executed. The capability-matrix gate staying red is a **separate** problem
(CR-002, route shadowing) and is **not** a defect of this CR's deliverables.

---

*End of CR-001*
