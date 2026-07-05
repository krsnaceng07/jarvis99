# 96_PHASE_34_AUTONOMOUS_AGENT_MISSION_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 34: Autonomous Mission Engine & Long-Running Agents**. It defines the persistent MissionManager coordinator, goal decomposition plans, rollback checkpoints, append-only timeline events, and platform REST APIs.

## Status
**STATUS:** ✅ FROZEN (2026-07-05, 1126 tests passed)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 33

---

## 1. Architectural Position

The Autonomous Mission Engine coordinates long-running goals by acting as an orchestrator above the existing SwarmOrchestrator and Planner:

```
                  ┌──────────────────────────────────────────────┐
                  │                 Mission REST                 │
                  │                 API Gateway                  │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │                MissionManager                │
                  │        (State Machine & Checkpoints)         │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │             SwarmOrchestrator                │
                  │           (Task Execution Loops)             │
                  └──────────────────────────────────────────────┘
```

---

## 2. Component Contracts

### 2.1 MissionManager

```python
class MissionManager:
    """Coordinates durable long-running missions and checkpoint states."""

    def __init__(
        self,
        settings: Any,
        db_manager: Any,
        event_bus: Any,
        vault_manager: Any,
        orchestrator: Any,
        planner: Any,
    ) -> None:
        """Initialize MissionManager with system dependencies."""

    async def create_mission(self, goal: str, budget_limit: float | None = None) -> Dict[str, Any]:
        """Create and persist a new mission in CREATED state."""

    async def start_mission(self, mission_id: UUID) -> Dict[str, Any]:
        """Decompose goal and transition mission to PLANNING/RUNNING state."""

    async def pause_mission(self, mission_id: UUID) -> Dict[str, Any]:
        """Suspend active task generation and execution for a mission."""

    async def resume_mission(self, mission_id: UUID) -> Dict[str, Any]:
        """Reload the latest checkpoint and resume execution."""

    async def cancel_mission(self, mission_id: UUID) -> Dict[str, Any]:
        """Abort execution and mark mission as CANCELLED."""

    async def create_checkpoint(self, mission_id: UUID, step_index: int, state_data: Dict[str, Any]) -> Dict[str, Any]:
        """Write an immutable checkpoint state for rollback."""

    async def rollback_to_checkpoint(self, mission_id: UUID, checkpoint_id: UUID) -> Dict[str, Any]:
        """Roll back the mission to the specified checkpoint state."""

    async def append_timeline_event(self, mission_id: UUID, event_type: str, description: str) -> None:
        """Write an append-only timeline event log."""
```

---

## 3. Mission State Machine

```text
  CREATED
     │
     ▼
  PLANNING
     │
     ▼
  WAITING_APPROVAL
     │
     ▼
  RUNNING ◄───► PAUSED
     │
     ├─► COMPLETED
     ├─► FAILED
     └─► CANCELLED
```

---

## 4. REST Endpoint Specifications

All endpoints are mounted under `/api/v1/missions` and require `"platform.admin"` or equivalent RBAC permission context:

### 4.1 Create Mission
- **Path**: `POST /api/v1/missions`
- **Request**: `{ "goal": "Deploy app to production", "budget_limit": 50.0 }`
- **Response**: `{ "mission_id": "...", "status": "CREATED", "goal": "..." }`

### 4.2 List Missions
- **Path**: `GET /api/v1/missions`
- **Response**: `[{ "mission_id": "...", "status": "RUNNING" }]`

### 4.3 Get Mission Details
- **Path**: `GET /api/v1/missions/{id}`
- **Response**: `{ "mission_id": "...", "status": "RUNNING", "plan": {...} }`

### 4.4 Pause Mission
- **Path**: `POST /api/v1/missions/{id}/pause`
- **Response**: `{ "status": "PAUSED" }`

### 4.5 Resume Mission
- **Path**: `POST /api/v1/missions/{id}/resume`
- **Response**: `{ "status": "RUNNING" }`

### 4.6 Cancel Mission
- **Path**: `POST /api/v1/missions/{id}/cancel`
- **Response**: `{ "status": "CANCELLED" }`

### 4.7 Retrieve Timeline
- **Path**: `GET /api/v1/missions/{id}/timeline`
- **Response**: `[{ "event_type": "Mission Created", "timestamp": "..." }]`

### 4.8 Retrieve Checkpoints
- **Path**: `GET /api/v1/missions/{id}/checkpoints`
- **Response**: `[{ "checkpoint_id": "...", "step_index": 2 }]`

---

## 5. Verification and Acceptance Criteria
- **State transitions**: Verify states shift correctly through the state machine.
- **Rollback**: Verify rollback sets the current execution plan state back to the checkpointed step data.
- **Recovery**: Verify system crash simulation successfully restarts active missions from their latest checkpoints.
