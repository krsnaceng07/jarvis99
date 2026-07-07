# 102_PHASE_40_EVENT_BUS_REACTIVE_ARCHITECTURE_SPECIFICATION.md

## Status
**STATUS:** ✅ FROZEN (2026-07-06)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 39 (Workflow Graph Engine)
**Date:** 2026-07-06
**Test Count (at freeze):** 1215 passed

---

## 1. Problem Statement

While JARVIS contains event bus singletons (`MemoryEventBus` and `RedisEventBus`), the core orchestration layers (BrainKernel, MissionManager, ScaleManager, ConsensusManager, and WorkflowGraphEngine) are still coupled via direct service calls. 

Phase 40 introduces a **fully reactive event-driven model** to decouple these subsystems. Rather than the `BrainKernel` imperatively commanding memory consolidation or scale offloading, subsystems will publish and subscribe to discrete domain events. This enables:
- **Loose Coupling**: Subsystems execute concurrently based on observed state changes rather than tight API references.
- **Dynamic Extensibility**: New plugins or skills can hook into event topics (e.g. `tool.executed`, `mission.completed`) without altering core engine loops.
- **Enhanced Observability**: Every event carries a unified `trace_id`, making execution pathways easy to track, profile, and audit.

---

## 2. System Topology

```
                  [ Brain Kernel ]
                         │
                         ▼ (Publish / Subscribe)
                 =================
                  GLOBAL EVENT BUS (Redis / In-Memory Exchange)
                 =================
       ┌─────────┬───────┼─────────┬─────────┐
       ▼         ▼       ▼         ▼         ▼
    Memory   Workflow Mission    Scale   Consensus
```

---

## 3. Directory Layout & Architecture

New event handlers and reactive controllers reside in standard namespaces:

```text
core/events/
  ├── schemas.py             # Pydantic DTOs for structured domain events
  ├── reactive_router.py     # Event-to-subsystem dispatcher
  ├── publishers/
  │    ├── brain_publisher.py    # Emits AgentLoop, Reflection, and Learning events
  │    └── workflow_publisher.py # Emits DAG wave, step, and cancellation events
  └── handlers/
       ├── memory_handler.py     # Reacts to workflow/mission successes (consolidates KG)
       ├── scale_handler.py      # Reacts to workload alerts (offloads execution)
       └── consensus_handler.py  # Reacts to policy checks (triggers consensus voting)
```

---

## 4. Subsystem Event Schemas

All events must inherit from a common `EventEnvelope` containing tracing metadata:

```python
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from typing import Any, Dict

class EventEnvelope(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    topic: str
    trace_id: UUID
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: Dict[str, Any]
```

### 4.1 Target Event Schemas

| Event Topic | Emitted By | Subscribed By (Reactors) | Purpose |
| :--- | :--- | :--- | :--- |
| `mission.created` | `MissionManager` | `ObservabilityService`, `ConsensusManager` | Logs start budget and validates permissions. |
| `workflow.started` | `WorkflowEngine` | `WorkingMemory`, `ObservabilityService` | Stores checkpoint state & starts span logs. |
| `workflow.completed` | `WorkflowEngine` | `MemoryCoordinator`, `LearningEngine` | Triggers ProceduralMemory update & experience consolidation. |
| `tool.executed` | `ToolRuntime` | `ReflectionEngine`, `AuditLogger` | Initiates diagnostics reflection & signs audit journals. |
| `memory.updated` | `MemoryCoordinator` | `KnowledgeGraph`, `BrainKernel` | Notifies active session of updated context variables. |
| `consensus.reached` | `ConsensusManager` | `BrainKernel`, `MissionManager` | Resolves approval gate blocks on safe/unsafe executions. |
| `reflection.finished` | `ReflectionEngine` | `AgentLoop` | Advises Agent Loop on repair strategies. |
| `learning.completed` | `LearningEngine` | `ProceduralMemory` | Registers optimized skill templates based on historical runs. |

---

## 5. Key Invariants

| # | Invariant |
|---|-----------|
| E-1 | **Non-blocking Dispatch**: Publishers must publish events asynchronously. The execution of event subscribers must never block the publisher's thread loop. |
| E-2 | **Trace Propagation**: Every generated domain event must preserve the original transaction's `trace_id` to enable unified span tracking. |
| E-3 | **Circular Decoupling**: Handlers reacting to events must never publish back to the same topic synchronously (prevents infinite recursive cascades). |
| E-4 | **Failsafe Delivery**: Subscribers handling transactional operations (like DB records or consensus) must use a retry/dead-letter queue if consumption fails. |

---

## 6. Verification & Acceptance Criteria

- **Decoupled Verification**: Verify that shutting down `ConsensusManager` does not crash `MissionManager` when a goal is created; the event `mission.created` should simply queue in Redis.
- **Trace Routing Audit**: Verify that a complete cycle (`mission.created` -> `workflow.started` -> `tool.executed` -> `reflection.finished` -> `workflow.completed`) maintains a single identical `trace_id`.
- **Latency Testing**: The overhead of dispatching a message across the `RedisEventBus` must remain below **5ms** under standard workload loops.
