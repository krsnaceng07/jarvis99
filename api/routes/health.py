"""
PHASE: 14
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/76_PHASE_14_API_GATEWAY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from api.dependencies import get_health_monitor
from api.dto import HealthResponse, MetaBlock, SuccessEnvelope
from core.health import HealthMonitor
from core.version import VERSION

router = APIRouter()


@router.get("/health")
async def health(
    request: Request,
    health_monitor: HealthMonitor = Depends(get_health_monitor),
) -> Response:
    """GET /api/v1/health endpoint.

    Retrieves diagnostic health status from the core HealthMonitor and wraps
    it in the generic SuccessEnvelope. Degraded status returns HTTP 503.
    """
    health_status = await health_monitor.check_health()
    status_str = health_status.get("status", "degraded")
    uptime = health_status.get("uptime_seconds", 0.0)

    health_data = HealthResponse(
        status=status_str,
        version=VERSION,
        uptime_seconds=uptime,
    )

    request_id = getattr(request.state, "request_id", None)
    if request_id is not None:
        meta = MetaBlock(request_id=request_id)
    else:
        meta = MetaBlock()

    envelope = SuccessEnvelope[HealthResponse](data=health_data, meta=meta)

    status_code = 200 if status_str == "healthy" else 503
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
    )
