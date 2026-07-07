# 87_PHASE_26_MULTI_AGENT_PERSISTENT_RECOVERY_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 26: Multi-Agent Runtime & Persistent Session Recovery**. It transitions the in-memory swarm orchestration structures to a production-grade database-backed runtime. It implements dynamic task execution, inter-agent message journaling, and a startup recovery protocol to seamlessly resume swarm operations after system interruptions.

## Status
**STATUS:** SPECIFICATION (PROPOSED)  
**Authority:** Rank 4 (Phase Specification)  
**Dependencies:** Phases 1–25  

---

## 1. Architectural Position

The persistent multi-agent runtime integrates the Event Bus, Swarm Orchestrator, and database layers to coordinate sandboxed subagents:

```
                            Gateway (FastAPI / WebSockets)
                                          │
                                          ▼
                                   SwarmOrchestrator
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
          SwarmTaskQueue                                  SwarmMessageBus
         (Db-backed FIFO)                              (Schema Validation)
                  │                                               │
                  ▼                                               ▼
          Subagent Workers                                 SwarmRepository
      (AgentLoop.run() Execution)                     (PostgreSQL / SQLite ORM)
                  │                                               │
                  └───────────────────────┬───────────────────────┘
                                          ▼
                                   Database Engine
```

---

## 2. Scope & Boundaries

### In Scope
- **Persistent storage schemas** for Swarm Tasks, Subagents, Swarm Snapshots, Inter-Agent Messages, and Agent Loop Iteration Journals.
- **Dynamic Task Dequeuing & Worker Loop:** Background worker loop inside `SwarmOrchestrator` to dequeue tasks from the `SwarmTaskQueue` and delegate execution to the designated subagents using `AgentLoop`.
- **Database-Backed Repository:** `DbSwarmPersistence` class persisting swarm states, snapshots, message streams, and iteration journals to relational database tables using SQLAlchemy.
- **Persistent Session Recovery:** Recovery logic on system boot that scans the database, clears/re-registers subagent container processes, transitions stuck tasks to failed/retryable states, and initializes the in-memory `SwarmTaskQueue` from pending DB tasks.
- **REST Endpoints:** Paginated REST endpoints to query historical swarm tasks, subagents, and snapshots.

### Out of Scope (Non-Goals)
- ❌ Dynamic creation of new subagent container images (reuses existing Mock/Docker/Process adapters).
- ❌ Modifying the core `AgentLoop` execution flow (remains frozen).
- ❌ Persistence of raw LLM prompts (complying with the Phase 25 no-raw-prompts journal constraint).

---

## 3. Database Schema Specifications

The database models are implemented as SQLAlchemy declarative schemas extending `Base` (imported from `core.memory.models`).

### 3.1 Swarm Tasks Table (`swarm_tasks`)
Stores persistent task states assigned to the swarm.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `task_id` | `Uuid` | Primary Key | Task UUID |
| `goal` | `String(4000)` | Not Null | Task goal description |
| `priority` | `String(50)` | Not Null | Priority: `CRITICAL`, `HIGH`, `NORMAL`, `LOW`, `SYSTEM` |
| `status` | `String(50)` | Not Null | Status: `Pending`, `Running`, `Waiting`, `Completed`, `Failed`, `Cancelled` |
| `capabilities` | `JSONB` | Nullable | Required worker capabilities |
| `timeout` | `Float` | Not Null, Default 900.0 | Maximum execution time in seconds |
| `retry` | `Integer` | Not Null, Default 0 | Current retry count |
| `dependencies` | `JSONB` | Nullable | List of task dependency UUIDs |
| `metadata` | `JSONB` | Nullable | Execution metadata, variables, or environment scopes |
| `created_at` | `DateTime` | Not Null, Default UTC | Creation timestamp |
| `updated_at` | `DateTime` | Not Null, Default UTC | Last updated timestamp |

### 3.2 Swarm Agents Table (`swarm_agents`)
Stores subagent registration status and active telemetry.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `agent_id` | `Uuid` | Primary Key | Mapped subagent UUID |
| `name` | `String(255)` | Not Null | Human-friendly name |
| `status` | `String(50)` | Not Null | Status: `ONLINE`, `WORKING`, `WAITING`, `DESTROYED` |
| `capabilities` | `JSONB` | Nullable | Registered capability list |
| `permissions` | `JSONB` | Nullable | Allowed permission manifest list |
| `cpu_load` | `Float` | Not Null, Default 0.0 | Telemetry CPU usage |
| `memory` | `Float` | Not Null, Default 0.0 | Telemetry RAM usage in megabytes |
| `recent_failures` | `Integer` | Not Null, Default 0 | Cumulative failure count |
| `created_at` | `DateTime` | Not Null, Default UTC | Creation timestamp |
| `updated_at` | `DateTime` | Not Null, Default UTC | Last updated timestamp |

### 3.3 Swarm Snapshots Table (`swarm_snapshots`)
Stores periodic swarm status metric snapshots for dashboards.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, Autoincrement | Snapshot primary key ID |
| `running_agents` | `Integer` | Not Null | Count of active subagents |
| `queued_tasks` | `Integer` | Not Null | Count of pending tasks |
| `completed_tasks` | `Integer` | Not Null | Count of successfully finished tasks |
| `failed_tasks` | `Integer` | Not Null | Count of failed tasks |
| `message_rate` | `Float` | Not Null | Messages per second metric |
| `cpu_usage` | `Float` | Not Null | Mapped total CPU utilization |
| `memory_usage` | `Float` | Not Null | Mapped total RAM utilization |
| `cluster_status` | `String(50)` | Not Null | `HEALTHY`, `DEGRADED`, `CRITICAL` |
| `timestamp` | `DateTime` | Not Null, Default UTC | Snapshot creation timestamp |

### 3.4 Swarm Messages Table (`swarm_messages`)
Logs all inter-agent messages routed through the event bus.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Uuid` | Primary Key | Message envelope UUID |
| `correlation_id` | `Uuid` | Not Null | Workflow trace identifier |
| `sender` | `String(255)` | Not Null | Sender identifier |
| `receiver` | `String(255)` | Not Null | Receiver identifier |
| `action` | `String(255)` | Not Null | Action verb/topic |
| `body` | `JSONB` | Nullable | Message parameters payload |
| `timestamp` | `DateTime` | Not Null, Default UTC | Message dispatch timestamp |

### 3.5 Agent Loop Journals Table (`agent_loop_journals`)
Persists iteration-by-iteration records from the `ExecutionJournal` to enable replaying execution sessions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `Integer` | PK, Autoincrement | Record entry index ID |
| `session_id` | `Uuid` | Not Null | Mapped task or agent run session UUID |
| `iteration` | `Integer` | Not Null | 1-based loop cycle index |
| `goal_description` | `String(4000)`| Not Null | High-level iteration goal description |
| `chosen_executor` | `String(50)` | Not Null | Selected executor (PYTHON, BROWSER, SHELL, etc.) |
| `reasoning` | `String(4000)`| Not Null | Short decision reasoning summary (no raw prompts) |
| `output_summary` | `String(4000)`| Not Null | Truncated output summary (~200 chars) |
| `reflection_category`| `String(100)`| Nullable | Mapped reflection failure category |
| `next_action` | `String(50)` | Not Null | Loop decision: `CONTINUE`, `REPLAN`, `ABORT`, `SUCCESS` |
| `timestamp` | `DateTime` | Not Null | Time when the iteration record was written |

---

## 4. Repository & Services Contracts

### 4.1 Swarm Repository Database Adapter
A SQLAlchemy-backed implementation of `SwarmPersistence` replaces `SwarmRepository`'s in-memory storage.

```python
class DbSwarmPersistence(SwarmPersistence):
    """SQLAlchemy database persistence adapter for swarm orchestration states."""

    async def save_task(self, task: SwarmTask, session: AsyncSession) -> None:
        """Persist or update a swarm task."""
        pass

    async def save_agent(self, agent_id: UUID, agent_data: Dict[str, Any], session: AsyncSession) -> None:
        """Persist or update subagent registration data."""
        pass

    async def save_snapshot(self, snapshot: SwarmSnapshot, session: AsyncSession) -> None:
        """Persist a global swarm telemetry snapshot."""
        pass

    async def load_snapshot(self, session: AsyncSession) -> Optional[SwarmSnapshot]:
        """Load the latest global swarm snapshot from database records."""
        pass

    async def save_history(self, session_id: UUID, history: List[Dict[str, Any]], session: AsyncSession) -> None:
        """Persist message logs and iteration records for the session."""
        pass
```

### 4.2 Swarm Worker Loop
An async background task is introduced in `SwarmOrchestrator` to consume tasks:
1. Loops continuously with a sleep delay (e.g. 0.1s).
2. Dequeues `SwarmTask` from `SwarmTaskQueue`.
3. Selects or spawns the best subagent via `CapabilityNegotiator`.
4. Spawns an async worker context converting `SwarmTask` properties to reasoning `Task` DTOs, executes the sandboxed `AgentLoop.run()`, and captures output metrics.
5. Updates task status to `Completed` / `Failed` and saves outputs to the database.
6. Frees the subagent back to the registry.

### 4.3 Swarm Session Recovery Protocol (`SwarmResumeManager`)
A recovery manager is registered to run during kernel boot:
1. **Reset Stuck Workers:** Finds subagents stuck in `WORKING`/`WAITING` state, verifies if active container/processes are still alive, and terminates or resets them to `DESTROYED`/`ONLINE`.
2. **Handle Stuck Tasks:** Finds `SwarmTask`s stuck in `Running` or `Pending`. Re-enqueues `Pending` tasks into the queue. Transitions `Running` tasks to `Failed` (due to system restart/timeout) or re-enqueues them if retry bounds permit.
3. **Queue Re-Seeding:** Populates the in-memory `SwarmTaskQueue` with unresolved `Pending` tasks ordered by priority and timestamp on boot.

---

## 5. API Gateway Interface Changes

The swarm REST endpoints query the DB persistence layer.

### Modified Endpoints
1. `POST /api/v1/swarm/spawn`
   - Enqueues task and immediately commits a new database record in `Pending` state.
2. `POST /api/v1/swarm/terminate`
   - Terminates executing container processes, marks task as `Cancelled` in database.
3. `GET /api/v1/swarm/tasks` (NEW paginated query endpoint)
   - Fetches historical swarm tasks. Query parameters: `limit: int = 20`, `offset: int = 0`.
4. `GET /api/v1/swarm/agents` (NEW paginated query endpoint)
   - Fetches all subagents list and status records.

---

## 6. Verification and Acceptance Criteria

### Automated Test Requirements
- **Swarm DB mapping tests:** 100% database write/read coverage for tasks, agents, snapshots, messages, and journals.
- **Worker dequeue & execution test:** Mock tasks enqueued in `SwarmTaskQueue` are successfully consumed by the worker loop, run through a simulated `AgentLoop`, and persisted as `Completed`.
- **System restart recovery test:** Simulates boot state recovery verifying stuck subagents are cleared and pending tasks re-seeded into the active task queue.
- **All Quality Gates Pass:** Zero lint errors, strict MyPy type checking, and zero regressions (986/986 tests pass).

---

## 7. Security Considerations
- Message logs and journals are checked for passwords, secrets, or keys by the `SwarmMessageBus` before database insertion. Mapped items with sensitive keywords are blocked and logged.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [13_MULTI_AGENT_PROTOCOL.md](file:///e:/jarvis/docs/13_MULTI_AGENT_PROTOCOL.md)
- [14_SUBAGENT_ORCHESTRATION.md](file:///e:/jarvis/docs/14_SUBAGENT_ORCHESTRATION.md)
- [72_RECOVERY_MODE.md](file:///e:/jarvis/docs/72_RECOVERY_MODE.md)
- [77_PHASE_15_PERSISTENT_EXECUTION_SPECIFICATION.md](file:///e:/jarvis/docs/77_PHASE_15_PERSISTENT_EXECUTION_SPECIFICATION.md)
- [86_PHASE_25_BROWSER_RUNTIME_SPECIFICATION.md](file:///e:/jarvis/docs/86_PHASE_25_BROWSER_RUNTIME_SPECIFICATION.md)
- [60_MASTER_INDEX.md](file:///e:/jarvis/docs/60_MASTER_INDEX.md)
