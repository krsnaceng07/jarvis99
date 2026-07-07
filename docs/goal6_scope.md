# Goal #6 — Persistent Autonomous Runtime

**Prerequisite:** v0.9.0-rc1 (Goals #1-5 complete, production gate passed)  
**Scope:** Make JARVIS OS survive restarts, run missions on schedules, recover from crashes, scale horizontally, and provide live observability.  
**Constraint:** Build on existing architecture. No rewrites of Goals #1-5 components.

---

## 6.1 Mission Persistence

**Problem:** Missions live only in memory. Process exit = lost state.

**Deliverables:**

- Mission state fully serialized to database (SQLite/PostgreSQL)
- All in-flight data (wave progress, agent outputs, merged results) persisted per step
- On restart, MissionManager loads incomplete missions from DB
- Resume from exact point of interruption (not from scratch)

**Key Changes:**
- Extend MissionModel with serialized wave state, agent outputs
- MissionManager.initialize() auto-loads interrupted missions
- Checkpoint auto-creation after each wave completion

**Test:** Kill process mid-wave → restart → mission resumes from last checkpoint

---

## 6.2 Scheduler

**Problem:** Missions are user-triggered only. No automation.

**Deliverables:**

- `MissionScheduler` service: delayed, cron/periodic, and one-shot missions
- Background queue with priority ordering
- Configurable concurrency limit (max simultaneous missions)
- Schedule persistence across restarts

**Key Changes:**
- New `core/mission/scheduler.py` (extend existing `mission_scheduler.py` if viable)
- Integration with MissionManager.create_mission + start_mission
- APScheduler or custom cron parser for scheduling

**Test:** Schedule mission for +5s → verify it fires. Set cron → verify it repeats. Kill/restart → verify schedule survives.

---

## 6.3 Crash Recovery

**Problem:** Process crash leaves missions in inconsistent state.

**Deliverables:**

- WAL-based transaction safety for all mission state changes
- Startup recovery scan: detect RUNNING missions with no active process
- Replay incomplete work from last checkpoint
- Dead letter queue for permanently failed missions (max retry exceeded)
- Idempotent step execution (re-running a step produces same outcome)

**Key Changes:**
- MissionManager startup: `_recover_interrupted_missions()`
- Checkpoint validation on load (detect corrupted state)
- Supervisor: detect zombie agents from previous process

**Test:** Crash mid-wave (SIGKILL) → restart → verify mission completes. Corrupt a checkpoint → verify graceful degradation.

---

## 6.4 Distributed Execution

**Problem:** Single process = single machine ceiling.

**Deliverables:**

- Worker process model: leader (MissionManager) + N workers (executors)
- Remote executor protocol (gRPC or Redis-based task queue)
- Task routing: assign tasks to workers by capability
- Horizontal scaling: add workers without restarting leader
- Worker health monitoring and automatic re-assignment on failure

**Key Changes:**
- SwarmOrchestrator.spawn_task() routes to local or remote executor
- New `core/runtime/worker.py` — standalone worker process
- Redis/RabbitMQ task queue adapter (optional, configurable)
- Leader election for HA (stretch goal)

**Test:** Start 3 worker processes → submit mission → verify tasks distributed across workers. Kill 1 worker → verify tasks re-assigned.

---

## 6.5 Observability

**Problem:** No visibility into running system. Debugging requires log reading.

**Deliverables:**

- Structured metrics: mission count, step latency, success rate, queue depth
- OpenTelemetry tracing: full request trace from BrainKernel → completion
- Live mission status API endpoint
- Simple dashboard (terminal or web) showing active missions, wave progress, agent states
- Alert hooks: webhook/callback on mission failure or budget exceeded

**Key Changes:**
- Instrument key methods with OpenTelemetry spans
- New `core/observability/metrics.py` — Prometheus-compatible counters/histograms
- API endpoint: `GET /missions/{id}/status` → real-time wave/agent state
- Optional: terminal dashboard with `rich` library

**Test:** Run mission → verify traces emitted. Check Prometheus endpoint returns metrics. Verify dashboard renders live state.

---

## Implementation Order

```
6.1 Mission Persistence  ←── FIRST (foundation for everything else)
        │
        ▼
6.3 Crash Recovery       ←── depends on persistence
        │
        ▼
6.2 Scheduler            ←── depends on persistence + recovery
        │
        ▼
6.5 Observability        ←── can start in parallel with 6.2
        │
        ▼
6.4 Distributed Exec     ←── LAST (highest complexity, needs all above)
```

## Success Criteria

All of these must be true before Goal #6 is complete:

1. Mission survives process restart (no data loss)
2. Scheduled mission fires on time (±1s)
3. SIGKILL recovery completes interrupted mission
4. At least 2 workers can process tasks from same mission
5. Dashboard shows live mission progress
6. All existing tests (1600+) still pass (no regression)
7. New Goal #6 tests pass (target: 50+ tests)
