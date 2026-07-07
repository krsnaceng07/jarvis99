"""
PHASE: 43
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/105_PHASE_43_GOAL_ENGINE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/21be4144-6686-48ed-8e46-74ce7e189cd4/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Module role: FastAPI route handlers for the Goal Engine (Phase 43).
Exposes CRUD + lifecycle operations under /api/v1/goals.
All business logic delegated to GoalService via DI.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import get_goal_service

logger = logging.getLogger("jarvis.api.routes.goal")

router = APIRouter(prefix="/goals", tags=["Goal Engine"])


# ---------------------------------------------------------------------------
# Request / Response DTOs
# ---------------------------------------------------------------------------


class CreateGoalRequest(BaseModel):
    """Payload for creating a new persistent goal."""

    title: str = Field(..., description="Short human-readable goal title.")
    description: Optional[str] = Field(default=None)
    priority: int = Field(default=5, ge=1, le=10)
    identity_id: Optional[UUID] = Field(default=None)
    parent_goal_id: Optional[UUID] = Field(default=None)
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    due_at: Optional[str] = Field(
        default=None, description="ISO-8601 deadline (optional)."
    )


class UpdateGoalRequest(BaseModel):
    """Payload for partial goal updates."""

    title: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    priority: Optional[int] = Field(default=None, ge=1, le=10)
    tags: Optional[List[str]] = Field(default=None)
    metadata: Optional[Dict[str, Any]] = Field(default=None)
    due_at: Optional[str] = Field(default=None)


class UpdateProgressRequest(BaseModel):
    """Payload for updating goal completion percentage."""

    progress: float = Field(..., ge=0.0, le=100.0)


class GoalResponse(BaseModel):
    """Serialised representation of a PersistentGoal."""

    id: UUID
    title: str
    description: Optional[str]
    status: str
    priority: int
    progress: float
    identity_id: Optional[UUID]
    parent_goal_id: Optional[UUID]
    tags: List[str]
    metadata: Dict[str, Any]
    due_at: Optional[str]
    completed_at: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(goal: Any) -> GoalResponse:
    """Convert PersistentGoal DTO to GoalResponse."""
    return GoalResponse(
        id=goal.id,
        title=goal.title,
        description=goal.description,
        status=goal.status.value if hasattr(goal.status, "value") else goal.status,
        priority=goal.priority,
        progress=goal.progress,
        identity_id=goal.identity_id,
        parent_goal_id=goal.parent_goal_id,
        tags=goal.tags,
        metadata=goal.metadata,
        due_at=goal.due_at.isoformat() if goal.due_at else None,
        completed_at=goal.completed_at.isoformat() if goal.completed_at else None,
        created_at=goal.created_at.isoformat(),
        updated_at=goal.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=List[GoalResponse],
    summary="List all goals",
    description="Returns all goals, optionally filtered by status.",
)
async def list_goals(
    status_filter: Optional[str] = None,
    identity_id: Optional[UUID] = None,
    goal_service: Any = Depends(get_goal_service),
) -> List[GoalResponse]:
    """GET /api/v1/goals — list goals with optional filters."""
    from core.reasoning.goal import GoalStatus

    goal_status: Optional[GoalStatus] = None
    if status_filter is not None:
        try:
            goal_status = GoalStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status value: {status_filter!r}",
            )
    try:
        goals = await goal_service.list_goals(
            status=goal_status, identity_id=identity_id
        )
        return [_to_response(g) for g in goals]
    except Exception as exc:
        logger.exception("Failed to list goals: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list goals: {exc}",
        ) from exc


@router.post(
    "",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new goal",
)
async def create_goal(
    payload: CreateGoalRequest,
    goal_service: Any = Depends(get_goal_service),
) -> GoalResponse:
    """POST /api/v1/goals — create a new persistent goal."""
    from datetime import datetime

    from core.reasoning.goal import PersistentGoal

    due = None
    if payload.due_at:
        try:
            due = datetime.fromisoformat(payload.due_at)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid due_at format: {exc}",
            ) from exc

    goal = PersistentGoal(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        identity_id=payload.identity_id,
        parent_goal_id=payload.parent_goal_id,
        tags=payload.tags,
        metadata=payload.metadata,
        due_at=due,
    )
    try:
        created = await goal_service.create_goal(goal)
        return _to_response(created)
    except Exception as exc:
        logger.exception("Failed to create goal: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create goal: {exc}",
        ) from exc


@router.get(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Get a goal by ID",
)
async def get_goal(
    goal_id: UUID,
    goal_service: Any = Depends(get_goal_service),
) -> GoalResponse:
    """GET /api/v1/goals/{goal_id} — fetch a single goal."""
    goal = await goal_service.get_goal(goal_id)
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goal {goal_id} not found.",
        )
    return _to_response(goal)


@router.patch(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Partially update a goal",
)
async def update_goal(
    goal_id: UUID,
    payload: UpdateGoalRequest,
    goal_service: Any = Depends(get_goal_service),
) -> GoalResponse:
    """PATCH /api/v1/goals/{goal_id} — apply partial field updates."""
    from datetime import datetime

    updates: Dict[str, Any] = {}
    if payload.title is not None:
        updates["title"] = payload.title
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.priority is not None:
        updates["priority"] = payload.priority
    if payload.tags is not None:
        updates["tags"] = payload.tags
    if payload.metadata is not None:
        updates["metadata_"] = payload.metadata
    if payload.due_at is not None:
        try:
            updates["due_at"] = datetime.fromisoformat(payload.due_at)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid due_at: {exc}",
            ) from exc

    try:
        updated = await goal_service.update_goal(goal_id, updates)
        return _to_response(updated)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to update goal: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update goal: {exc}",
        ) from exc


@router.post(
    "/{goal_id}/activate",
    response_model=GoalResponse,
    summary="Activate a goal",
)
async def activate_goal(
    goal_id: UUID,
    goal_service: Any = Depends(get_goal_service),
) -> GoalResponse:
    """POST /api/v1/goals/{goal_id}/activate — set status to ACTIVE."""
    try:
        updated = await goal_service.activate_goal(goal_id)
        return _to_response(updated)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to activate goal: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate goal: {exc}",
        ) from exc


@router.post(
    "/{goal_id}/complete",
    response_model=GoalResponse,
    summary="Complete a goal",
)
async def complete_goal(
    goal_id: UUID,
    goal_service: Any = Depends(get_goal_service),
) -> GoalResponse:
    """POST /api/v1/goals/{goal_id}/complete — mark COMPLETED."""
    try:
        updated = await goal_service.complete_goal(goal_id)
        return _to_response(updated)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to complete goal: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete goal: {exc}",
        ) from exc


@router.post(
    "/{goal_id}/cancel",
    response_model=GoalResponse,
    summary="Cancel a goal",
)
async def cancel_goal(
    goal_id: UUID,
    goal_service: Any = Depends(get_goal_service),
) -> GoalResponse:
    """POST /api/v1/goals/{goal_id}/cancel — mark CANCELLED."""
    try:
        updated = await goal_service.cancel_goal(goal_id)
        return _to_response(updated)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to cancel goal: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel goal: {exc}",
        ) from exc


@router.post(
    "/{goal_id}/progress",
    response_model=GoalResponse,
    summary="Update goal progress",
)
async def update_progress(
    goal_id: UUID,
    payload: UpdateProgressRequest,
    goal_service: Any = Depends(get_goal_service),
) -> GoalResponse:
    """POST /api/v1/goals/{goal_id}/progress — update percentage completion."""
    try:
        updated = await goal_service.update_progress(goal_id, payload.progress)
        return _to_response(updated)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to update goal progress: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update progress: {exc}",
        ) from exc


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a goal",
)
async def delete_goal(
    goal_id: UUID,
    goal_service: Any = Depends(get_goal_service),
) -> None:
    """DELETE /api/v1/goals/{goal_id} — permanently remove a goal."""
    try:
        deleted = await goal_service.delete_goal(goal_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Goal {goal_id} not found.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete goal: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete goal: {exc}",
        ) from exc
