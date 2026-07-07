"""
PHASE: 44
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md

IMPLEMENTATION PLAN:
    Phase 44 approved plan — Mission & Autonomous Goal Scheduler

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Module role: FastAPI route handlers for the Mission Scheduler (Phase 44).
Exposes endpoints for submitting, pausing, resuming, cancelling missions,
and inspecting scheduler queue state under /api/v1/scheduler.
All business logic delegated to GoalScheduler singleton via DI.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import get_goal_scheduler

logger = logging.getLogger("jarvis.api.routes.mission_scheduler")

router = APIRouter(prefix="/scheduler", tags=["Mission Scheduler"])


# ---------------------------------------------------------------------------
# Request / Response DTOs
# ---------------------------------------------------------------------------


class CreateMissionTaskRequest(BaseModel):
    """Payload to add an atomic task to a new mission."""

    name: str
    description: Optional[str] = None
    depends_on: List[UUID] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)
    max_retries: int = Field(default=3, ge=0)
    budget: float = Field(default=10.0, ge=0.0)


class CreateMissionRequest(BaseModel):
    """Payload for submitting a new autonomous mission."""

    name: str
    description: Optional[str] = None
    goal_id: Optional[UUID] = None
    identity_id: Optional[UUID] = None
    priority: int = Field(default=5, ge=1, le=10)
    tasks: List[CreateMissionTaskRequest] = Field(..., min_length=1)
    total_budget: float = Field(default=100.0, ge=0.0)
    max_retries: int = Field(default=3, ge=0)
    due_at: Optional[str] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MissionTaskResponse(BaseModel):
    """Serialised state of a MissionTask."""

    id: UUID
    name: str
    description: Optional[str]
    status: str
    depends_on: List[UUID]
    payload: Dict[str, Any]
    retries: int
    max_retries: int
    budget: float
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]


class MissionResponse(BaseModel):
    """Serialised state of a Mission."""

    id: UUID
    name: str
    description: Optional[str]
    goal_id: Optional[UUID]
    identity_id: Optional[UUID]
    status: str
    priority: int
    tasks: List[MissionTaskResponse]
    total_budget: float
    used_budget: float
    max_retries: int
    retry_count: int
    progress: float
    due_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str


class QueueItemResponse(BaseModel):
    """Serialised queue entry descriptor."""

    mission_id: UUID
    priority: int
    deadline: Optional[str]
    enqueued_at: str
    effective_priority: float


class SchedulerStatsResponse(BaseModel):
    """High-level metrics for scheduler queue health."""

    queue_depth: int
    running_count: int
    max_concurrent: int
    poll_interval: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_task_response(task: Any) -> MissionTaskResponse:
    return MissionTaskResponse(
        id=task.id,
        name=task.name,
        description=task.description,
        status=task.status.value,
        depends_on=task.depends_on,
        payload=task.payload,
        retries=task.retries,
        max_retries=task.max_retries,
        budget=task.budget,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        error=task.error,
    )


def _to_mission_response(m: Any) -> MissionResponse:
    return MissionResponse(
        id=m.id,
        name=m.name,
        description=m.description,
        goal_id=m.goal_id,
        identity_id=m.identity_id,
        status=m.status.value,
        priority=m.priority,
        tasks=[_to_task_response(t) for t in m.tasks],
        total_budget=m.total_budget,
        used_budget=m.used_budget,
        max_retries=m.max_retries,
        retry_count=m.retry_count,
        progress=m.progress,
        due_at=m.due_at.isoformat() if m.due_at else None,
        started_at=m.started_at.isoformat() if m.started_at else None,
        completed_at=m.completed_at.isoformat() if m.completed_at else None,
        error=m.error,
        metadata=m.metadata,
        created_at=m.created_at.isoformat(),
        updated_at=m.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/missions",
    response_model=MissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enqueue a new mission",
)
async def create_mission(
    payload: CreateMissionRequest,
    scheduler: Any = Depends(get_goal_scheduler),
) -> MissionResponse:
    """POST /api/v1/scheduler/missions — submit a mission to the queue."""
    from datetime import datetime

    from core.mission.mission_types import Mission, MissionTask

    due = None
    if payload.due_at:
        try:
            due = datetime.fromisoformat(payload.due_at)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid due_at format: {exc}",
            ) from exc

    tasks = [
        MissionTask(
            name=t.name,
            description=t.description,
            depends_on=t.depends_on,
            payload=t.payload,
            max_retries=t.max_retries,
            budget=t.budget,
        )
        for t in payload.tasks
    ]

    mission = Mission(
        name=payload.name,
        description=payload.description,
        goal_id=payload.goal_id,
        identity_id=payload.identity_id,
        priority=payload.priority,
        tasks=tasks,
        total_budget=payload.total_budget,
        max_retries=payload.max_retries,
        due_at=due,
        metadata=payload.metadata,
    )

    try:
        # Resolve topological sort validity early to raise cycle error on POST
        from core.mission.mission_scheduler import GoalDependencyResolver

        GoalDependencyResolver().resolve(mission.tasks)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await scheduler.schedule_mission(mission)
    return _to_mission_response(mission)


@router.get(
    "/missions/{mission_id}",
    response_model=MissionResponse,
    summary="Get mission details",
)
async def get_mission(
    mission_id: UUID,
    scheduler: Any = Depends(get_goal_scheduler),
) -> MissionResponse:
    """GET /api/v1/scheduler/missions/{mission_id}."""
    mission = await scheduler.get_mission(mission_id)
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission {mission_id} not found.",
        )
    return _to_mission_response(mission)


@router.post(
    "/missions/{mission_id}/cancel",
    response_model=Dict[str, Any],
    summary="Cancel a mission",
)
async def cancel_mission(
    mission_id: UUID,
    scheduler: Any = Depends(get_goal_scheduler),
) -> Dict[str, Any]:
    """POST /api/v1/scheduler/missions/{mission_id}/cancel."""
    success = await scheduler.cancel_mission(mission_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission {mission_id} not found or not running/queued.",
        )
    return {"success": True, "message": f"Mission {mission_id} cancelled."}


@router.post(
    "/missions/{mission_id}/pause",
    response_model=Dict[str, Any],
    summary="Pause a mission",
)
async def pause_mission(
    mission_id: UUID,
    scheduler: Any = Depends(get_goal_scheduler),
) -> Dict[str, Any]:
    """POST /api/v1/scheduler/missions/{mission_id}/pause."""
    success = await scheduler.pause_mission(mission_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mission {mission_id} could not be paused (must be RUNNING).",
        )
    return {"success": True, "message": f"Mission {mission_id} paused."}


@router.post(
    "/missions/{mission_id}/resume",
    response_model=Dict[str, Any],
    summary="Resume a mission",
)
async def resume_mission(
    mission_id: UUID,
    scheduler: Any = Depends(get_goal_scheduler),
) -> Dict[str, Any]:
    """POST /api/v1/scheduler/missions/{mission_id}/resume."""
    success = await scheduler.resume_mission(mission_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mission {mission_id} could not be resumed (must be PAUSED).",
        )
    return {"success": True, "message": f"Mission {mission_id} resumed."}


@router.get(
    "/queue",
    response_model=List[QueueItemResponse],
    summary="Get scheduler queue items",
)
async def get_queue(
    scheduler: Any = Depends(get_goal_scheduler),
) -> List[QueueItemResponse]:
    """GET /api/v1/scheduler/queue — list all queued items sorted by priority."""
    items = await scheduler._queue.all_items()
    return [
        QueueItemResponse(
            mission_id=i.mission_id,
            priority=i.priority,
            deadline=i.deadline.isoformat() if i.deadline else None,
            enqueued_at=i.enqueued_at.isoformat(),
            effective_priority=i.effective_priority(),
        )
        for i in items
    ]


@router.get(
    "/stats",
    response_model=SchedulerStatsResponse,
    summary="Get scheduler stats",
)
async def get_stats(
    scheduler: Any = Depends(get_goal_scheduler),
) -> SchedulerStatsResponse:
    """GET /api/v1/scheduler/stats — get queue depth and running task counts."""
    return SchedulerStatsResponse(
        queue_depth=await scheduler.queue_depth(),
        running_count=await scheduler.running_count(),
        max_concurrent=scheduler.config.max_concurrent_missions,
        poll_interval=scheduler.config.poll_interval_seconds,
    )
