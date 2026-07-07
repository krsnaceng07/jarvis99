"""JARVIS OS - Swarm Router.

Exposes REST APIs and WebSocket endpoints for distributed subagent task management and real-time telemetry streaming.
"""

import asyncio
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.runtime.dto import SwarmTask
from core.runtime.orchestrator import SwarmOrchestrator

# Global orchestrator instance holder for FastAPI route dependencies
_global_orchestrator: Optional[SwarmOrchestrator] = None


def set_orchestrator(orchestrator: SwarmOrchestrator) -> None:
    """Set the active global orchestrator instance for routes.

    Args:
        orchestrator: Active SwarmOrchestrator instance.
    """
    global _global_orchestrator
    _global_orchestrator = orchestrator


swarm_router = APIRouter(prefix="/api/v1/swarm", tags=["swarm"])
ws_router = APIRouter(prefix="/ws/v1", tags=["swarm"])


class SpawnResponse(BaseModel):
    """Pydantic model representing success status outcome."""

    status: str
    message: str


class TerminateRequest(BaseModel):
    """Pydantic model requesting task cancel operations."""

    task_id: UUID


def _require_orchestrator() -> SwarmOrchestrator:
    """Retrieve global orchestrator or raise 503."""
    if not _global_orchestrator:
        raise HTTPException(
            status_code=503, detail="Swarm Orchestrator service unavailable."
        )
    return _global_orchestrator


@swarm_router.post("/spawn", response_model=SpawnResponse)
async def spawn_task(task: SwarmTask) -> Dict[str, Any]:
    """Trigger goal-decomposition and execute a task inside a subagent container."""
    orch = _require_orchestrator()

    success = await orch.spawn_task(task)
    if not success:
        raise HTTPException(
            status_code=409,
            detail="Failed to spawn task: Lock acquisition failure or scheduling conflict.",
        )

    return {
        "status": "SUCCESS",
        "message": f"Task {task.task_id} enqueued successfully.",
    }


@swarm_router.post("/terminate", response_model=SpawnResponse)
async def terminate_task(request: TerminateRequest) -> Dict[str, Any]:
    """Force cancel and abort execution of a task."""
    orch = _require_orchestrator()

    success = await orch.cancel_task(request.task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task ID context not found.")

    return {
        "status": "SUCCESS",
        "message": f"Task {request.task_id} successfully cancelled.",
    }


@swarm_router.get("/tasks")
async def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """Query paginated swarm task records from persistence."""
    _require_orchestrator()

    from core.runtime.persistence_db import DbSwarmPersistence

    persistence = DbSwarmPersistence()
    tasks = await persistence.list_tasks(limit=limit, offset=offset)
    return {
        "tasks": [t.model_dump(mode="json") for t in tasks],
        "limit": limit,
        "offset": offset,
    }


@swarm_router.get("/agents")
async def list_agents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """Query paginated swarm agent registration records from persistence."""
    _require_orchestrator()

    from core.runtime.persistence_db import DbSwarmPersistence

    persistence = DbSwarmPersistence()
    agents = await persistence.list_agents(limit=limit, offset=offset)
    return {
        "agents": agents,
        "limit": limit,
        "offset": offset,
    }


@swarm_router.get("/status")
async def get_status() -> Dict[str, Any]:
    """Fetch live swarm orchestrator status snapshot."""
    orch = _require_orchestrator()
    return await orch.get_status()


@ws_router.websocket("/swarm")
async def websocket_swarm_telemetry(websocket: WebSocket) -> None:
    """Websocket connection streaming active subagent telemetry periodically to dashboard clients."""
    await websocket.accept()
    try:
        while True:
            if _global_orchestrator:
                status_data = await _global_orchestrator.get_status()
                await websocket.send_json(status_data)
            else:
                await websocket.send_json({"error": "Orchestrator offline"})
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except RuntimeError:
            pass
