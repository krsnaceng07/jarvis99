# 106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md

## Status
**STATUS:** FROZEN (2026-07-06)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 43 (Goal Engine)
**Date:** 2026-07-06
**Tests at freeze:** 71 (1367 total)

---

## 1. Problem Statement

To run complex multi-step objectives autonomously, JARVIS OS needs a Mission and Autonomous Goal Scheduler. This engine resolves dependencies between goal tasks, prioritizes task waves dynamically based on priority weight and deadline urgency, monitors resource and token budgets, handles transient failures via retry/recovery managers, and executes everything on an asynchronous background runner loop.

---

## 2. Architecture & Design

```text
      Identity (Active context)
            │
            ▼
       BrainKernel
            │
            ▼
       Goal Engine (Persistence)
            │
            ▼
    =============================
       MISSION SCHEDULER
    =============================
      ├─ GoalDependencyResolver (Topological waves)
      ├─ PriorityEngine (Effective weight calculation)
      ├─ DeadlineManager (Escalation & tracking)
      ├─ ExecutionBudgetManager (Grace-bound safety checks)
      ├─ MissionRecovery (Retries & restarts)
      ├─ BackgroundGoalRunner (Async polling execution)
      └─ MissionQueue (In-memory priority queue)
            │
            ▼ (Submits wave tasks)
      Workflow Engine / Event Bus / Unified Memory
```

---

## 3. Directory Layout

The Mission Scheduler components are organized as follows:

```text
core/mission/
  ├── mission_types.py        # Enums, Mission/Task DTOs, Queue/Result payloads
  ├── mission_scheduler.py    # Scheduler core logic, resolver, recovery, background loop
api/routes/
  └── mission_scheduler.py    # REST API endpoints for scheduler and queues (/api/v1/scheduler)
```

---

## 4. Key Invariants

| # | Invariant |
|---|-----------|
| MS-1 | **Wave Sequence**: A task in Wave N must not run until all tasks in Wave N-1 have completed successfully. |
| MS-2 | **Budget Boundary**: A mission exceeding its budget limit beyond the allowed grace threshold must be immediately halted and set to `FAILED` with `Budget exhausted`. |
| MS-3 | **Safe Recovery**: Task and mission failures must trigger retry logic if retry counts remain within configured limits, transitioning tasks through recovery states. |

---

## 5. REST API Contracts

### `POST /api/v1/scheduler/missions`
* Enqueues a new mission. Returns `201 Created` with serialised mission state.

### `GET /api/v1/scheduler/missions/{id}`
* Fetch a mission's current state and status. Returns `200 OK`.

### `POST /api/v1/scheduler/missions/{id}/cancel`
* Cancels a queued or running mission. Returns `200 OK`.

### `POST /api/v1/scheduler/missions/{id}/pause`
* Pauses execution of a running mission. Returns `200 OK`.

### `POST /api/v1/scheduler/missions/{id}/resume`
* Resumes a paused mission. Returns `200 OK`.

### `GET /api/v1/scheduler/queue`
* Returns current queue items and scheduler statistics. Returns `200 OK`.
