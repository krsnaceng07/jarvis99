"""
PHASE: 34
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/96_PHASE_34_AUTONOMOUS_AGENT_MISSION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/d42af1e8-69f8-4bf2-a03f-dc029da887c0/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, get_mission_manager, require_permissions
from core.runtime.mission_models import (
    MissionCheckpointModel,
    MissionModel,
    MissionTimelineModel,
)

router = APIRouter(tags=["missions"])


class CreateMissionRequest(BaseModel):
    """Schema representing goal details to initialize a long-running mission."""

    goal: str = Field(..., max_length=4000)
    budget_limit: Optional[float] = Field(None, ge=0.0)


@router.post(
    "/api/v1/missions",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
)
async def create_mission(
    payload: CreateMissionRequest,
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    mission_mgr: Any = Depends(get_mission_manager),
) -> Dict[str, Any]:
    """Create and automatically run a new autonomous mission. Protected by platform.admin."""
    res = await mission_mgr.create_mission(payload.goal, payload.budget_limit)
    start_res = await mission_mgr.start_mission(res["mission_id"])
    return {
        "mission_id": str(res["mission_id"]),
        "status": start_res["status"],
        "goal": res["goal"],
        "budget_limit": res["budget_limit"],
    }


@router.get("/api/v1/missions", response_model=List[Dict[str, Any]])
async def list_missions(
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Retrieve all mission states. Protected by platform.admin."""
    stmt = select(MissionModel).order_by(MissionModel.created_at.desc())
    res = await session.execute(stmt)
    missions = res.scalars().all()
    return [
        {
            "mission_id": str(m.mission_id),
            "goal": m.goal,
            "status": m.status,
            "budget_limit": m.budget_limit,
            "budget_used": m.budget_used,
            "current_step": m.current_step,
            "created_at": m.created_at.isoformat(),
        }
        for m in missions
    ]


@router.get("/api/v1/missions/{id}", response_model=Dict[str, Any])
async def get_mission(
    id: UUID,
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Retrieve details for a single mission. Protected by platform.admin."""
    stmt = select(MissionModel).where(MissionModel.mission_id == id)
    res = await session.execute(stmt)
    mission = res.scalar_one_or_none()
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mission {id} not found.",
        )
    return {
        "mission_id": str(mission.mission_id),
        "goal": mission.goal,
        "status": mission.status,
        "budget_limit": mission.budget_limit,
        "budget_used": mission.budget_used,
        "current_step": mission.current_step,
        "plan_data": mission.plan_data,
        "created_at": mission.created_at.isoformat(),
    }


@router.post("/api/v1/missions/{id}/pause", response_model=Dict[str, Any])
async def pause_mission(
    id: UUID,
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    mission_mgr: Any = Depends(get_mission_manager),
) -> Dict[str, Any]:
    """Pause execution of a running mission. Protected by platform.admin."""
    try:
        res = await mission_mgr.pause_mission(id)
        return {"mission_id": str(res["mission_id"]), "status": res["status"]}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/api/v1/missions/{id}/resume", response_model=Dict[str, Any])
async def resume_mission(
    id: UUID,
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    mission_mgr: Any = Depends(get_mission_manager),
) -> Dict[str, Any]:
    """Resume a paused mission. Protected by platform.admin."""
    try:
        res = await mission_mgr.resume_mission(id)
        return {"mission_id": str(res["mission_id"]), "status": res["status"]}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/api/v1/missions/{id}/cancel", response_model=Dict[str, Any])
async def cancel_mission(
    id: UUID,
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    mission_mgr: Any = Depends(get_mission_manager),
) -> Dict[str, Any]:
    """Cancel execution of a mission. Protected by platform.admin."""
    try:
        res = await mission_mgr.cancel_mission(id)
        return {"mission_id": str(res["mission_id"]), "status": res["status"]}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/api/v1/missions/{id}/timeline", response_model=List[Dict[str, Any]]
)
async def get_timeline(
    id: UUID,
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Retrieve immutable logs of events for a mission. Protected by platform.admin."""
    stmt = (
        select(MissionTimelineModel)
        .where(MissionTimelineModel.mission_id == id)
        .order_by(MissionTimelineModel.timestamp.asc())
    )
    res = await session.execute(stmt)
    events = res.scalars().all()
    return [
        {
            "event_id": str(e.event_id),
            "event_type": e.event_type,
            "description": e.description,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in events
    ]


@router.get(
    "/api/v1/missions/{id}/checkpoints", response_model=List[Dict[str, Any]]
)
async def get_checkpoints(
    id: UUID,
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
    session: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Retrieve checkpoints list for a mission. Protected by platform.admin."""
    stmt = (
        select(MissionCheckpointModel)
        .where(MissionCheckpointModel.mission_id == id)
        .order_by(MissionCheckpointModel.step_index.asc())
    )
    res = await session.execute(stmt)
    checkpoints = res.scalars().all()
    return [
        {
            "checkpoint_id": str(c.checkpoint_id),
            "step_index": c.step_index,
            "created_at": c.created_at.isoformat(),
        }
        for c in checkpoints
    ]
