"""
PHASE: 45 (M6.4.A)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§6 REST API Contracts — 6.4 sub-goal: GET /api/v1/distributed/workers, POST .../heartbeat, POST .../route)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.A — distributed_pool REST routes)

AUTHORITATIVE:
    NO

Distributed pool REST routes (Phase 45 — M6.4.A).

Endpoints (spec §6 + plan §3 M6.4.A):

* ``GET    /api/v1/distributed/workers``
  — list every worker in ``worker_registry``. Auth: ``platform.admin``.

* ``POST   /api/v1/distributed/workers/{id}/heartbeat``
  — bump heartbeat; auto-promote OFFLINE -> ONLINE on a re-registered
    worker's first heartbeat. Auth: ``platform.admin``.

* ``POST   /api/v1/distributed/tasks/route``
  — leader-side routing decision. The leader's ``DistributedRouter``
    picks a worker, records a ``task_routing_log`` row (D-2 append-only),
    and returns the chosen worker (or 404 if none eligible under the
    supplied policy). Auth: ``platform.admin``.

* ``GET    /api/v1/distributed/routing?wave_run_id=...``
  — list every routing decision recorded for ``wave_run_id`` (D-2
    append-only audit). Auth: ``platform.admin``.

* ``POST   /api/v1/distributed/routing/{route_id}/complete``
  — mark a routing row's ``completed_at`` timestamp. Audit trail; the
    row remains in the table forever (D-2). Auth: ``platform.admin``.

Layer direction (per AGENTS.md / architecture freeze):

    API  →  DistributedRouter  →  WorkerRegistry  →  Persistence

The route does NOT write directly to the DB; routing decisions go
through the router (which writes the ``task_routing_log`` row) so the
D-2 invariant holds.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.dependencies import (
    get_distributed_router,
    require_permissions,
)

router = APIRouter(prefix="/api/v1/distributed", tags=["distributed-pool"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class HeartbeatRequest(BaseModel):
    """Body of ``POST /api/v1/distributed/workers/{id}/heartbeat``.

    ``active_tasks`` is OPTIONAL — the heartbeat updates
    ``last_heartbeat`` regardless. When supplied, ``active_tasks`` is
    stored on the worker row (load metric for the router's tiebreak).
    """

    active_tasks: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "Optional current load count. When supplied, the worker's "
            "active_tasks is updated to this value (the leader uses "
            "the smallest active_tasks as the routing tiebreak)."
        ),
    )


class RouteRequest(BaseModel):
    """Body of ``POST /api/v1/distributed/tasks/route``.

    ``wave_run_id`` is REQUIRED — it is the D-3 dedup key + audit trail.
    Either or both of ``required_platform`` / ``required_skill`` may be
    supplied; an empty request effectively means "any active worker".
    ``policy`` defaults to ``ANY`` (M6.4.A scope).
    """

    wave_run_id: UUID = Field(
        ...,
        description=(
            "D-3 dedup key + audit. Two route() calls with the same "
            "wave_run_id + same chosen worker_id yield the SAME "
            "task_routing_log row (R-1 idempotency contract)."
        ),
    )
    required_platform: Optional[str] = Field(
        default=None,
        max_length=64,
        description=(
            "Optional platform name to require (e.g. 'linux', 'macos', "
            "'windows'). Must appear in the worker's capabilities JSONB."
        ),
    )
    required_skill: Optional[str] = Field(
        default=None,
        max_length=255,
        description=(
            "Optional skill namespace to require (e.g. "
            "'core.skills.git_clone'). Must appear in the worker's "
            "capabilities JSONB."
        ),
    )
    policy: str = Field(
        default="ANY",
        description=(
            "Routing policy. One of: LOCAL_ONLY | REMOTE_PREFERRED | "
            "ANY. REMOTE_PREFERRED raises 501 in M6.4.A (M6.4.B scope)."
        ),
    )
    allow_no_worker: bool = Field(
        default=False,
        description=(
            "When true and no worker matches, return 200 with "
            "worker=null + decision_reason='NO_ELIGIBLE_WORKER' "
            "instead of 404. Useful for soft-routing flows."
        ),
    )


class CompleteRoutingRequest(BaseModel):
    """Body of ``POST /api/v1/distributed/routing/{route_id}/complete``.

    The body is currently empty (no fields). Kept as a class so the
    request surface is forward-compatible — a future field (e.g.
    completion_status) lands here without changing the route shape.
    """

    notes: Optional[str] = Field(
        default=None,
        max_length=4000,
        description="Optional free-text audit notes.",
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/workers",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List every registered worker + status",
)
async def list_workers(
    router_dep: Any = Depends(get_distributed_router),
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
) -> List[Dict[str, Any]]:
    """Return every row of ``worker_registry``.

    The response is the full ``worker_registry`` table — operators see
    ONLINE, BUSY, AND OFFLINE workers. Liveness sweeps run lazily on
    the next ``list_active`` call.
    """
    workers = await router_dep.registry.list_all()
    return [w.to_dict() for w in workers]


@router.post(
    "/workers/{worker_id}/heartbeat",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Heartbeat a worker (bump last_heartbeat, optional active_tasks)",
)
async def heartbeat_worker(
    worker_id: UUID,
    payload: HeartbeatRequest,
    router_dep: Any = Depends(get_distributed_router),
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
) -> Dict[str, Any]:
    """Heartbeat handler invoked by ``WorkerProcess`` and the operator UI.

    Returns ``status`` of the worker post-update (``ONLINE`` if
    promoted from ``OFFLINE``).
    """
    post_status = await router_dep.registry.heartbeat(
        worker_id=worker_id,
        active_tasks=payload.active_tasks,
    )
    if post_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"worker_id {worker_id} is not registered. "
                "The worker must call register() before its first heartbeat."
            ),
        )
    return {"worker_id": str(worker_id), "status": post_status}


@router.post(
    "/tasks/route",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Leader-side routing decision (records task_routing_log row)",
)
async def route_task(
    payload: RouteRequest,
    router_dep: Any = Depends(get_distributed_router),
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
) -> Dict[str, Any]:
    """Decide the worker that should handle a wave.

    Returns a ``RoutingDecision`` JSON dict (the worker's snapshot is
    inlined when present). The route always appends a row to
    ``task_routing_log`` (D-2 invariant).

    Status codes:
        200 — routing decision recorded (worker may be null when
              ``allow_no_worker=true`` and no worker matched).
        404 — no eligible worker AND ``allow_no_worker=false``.
        501 — ``policy=REMOTE_PREFERRED`` invoked in M6.4.A (M6.4.B
              scope; see docs/108 §3 M6.4.B).
    """
    # Resolve the policy string into the enum before delegating to the
    # router, so we can map ``REMOTE_PREFERRED`` to 501 cleanly here.
    try:
        from core.mission.distributed_router import (
            RemoteTransportNotImplementedError,
            RoutingPolicy,
        )
    except ImportError as exc:  # pragma: no cover — install-time
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DistributedRouter module is unavailable.",
        ) from exc

    try:
        policy_enum = RoutingPolicy(payload.policy)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"policy must be one of "
                f"{[p.value for p in RoutingPolicy]} (got "
                f"{payload.policy!r})."
            ),
        ) from exc

    try:
        decision = await router_dep.route(
            wave_run_id=payload.wave_run_id,
            required_platform=payload.required_platform,
            required_skill=payload.required_skill,
            policy=policy_enum,
            allow_no_worker=payload.allow_no_worker,
        )
    except RemoteTransportNotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        # NoEligibleWorkerError + any future routing errors. The router
        # signals "no worker matched" with this exception class so the
        # route can map to 404.
        if exc.__class__.__name__ == "NoEligibleWorkerError":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        raise

    return decision.to_dict()  # type: ignore[no-any-return]


@router.get(
    "/routing",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Routing decisions recorded for a wave_run_id",
)
async def list_routing_for_wave(
    wave_run_id: UUID = Query(..., description="D-3 dedup key to audit."),
    router_dep: Any = Depends(get_distributed_router),
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
) -> List[Dict[str, Any]]:
    """Audit-only listing of routing decisions for ``wave_run_id``.

    The endpoint is D-2 compliant: it only SELECTs from
    ``task_routing_log`` and never modifies it.
    """
    decisions = await router_dep.get_routing_for_wave(wave_run_id=wave_run_id)
    return [d.to_dict() for d in decisions]


@router.post(
    "/routing/{route_id}/complete",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Mark a routing decision complete (audit only, append-only preserved)",
)
async def complete_routing(
    route_id: UUID,
    payload: CompleteRoutingRequest = CompleteRoutingRequest(),
    router_dep: Any = Depends(get_distributed_router),
    auth_context: Any = Depends(require_permissions(["platform.admin"])),
) -> Dict[str, Any]:
    """Mark ``route_id`` as completed; the row remains in the table.

    Returns ``{"route_id": ..., "completed": true|false}``. ``completed``
    is false when the row does not exist OR was already completed
    (idempotent — the row is left untouched in either case to preserve
    D-2 append-only semantics).
    """
    updated = await router_dep.mark_routing_complete(route_id=route_id)
    return {"route_id": str(route_id), "completed": bool(updated)}


__all__ = ["router"]
