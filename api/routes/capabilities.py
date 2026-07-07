"""
PHASE: 41
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/103_PHASE_41_CAPABILITY_REGISTRY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/8e27d67d-09cc-4e93-9e3e-d5a4bb653dd9/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from api.dependencies import get_kernel, require_permissions
from api.dto import MetaBlock
from core.kernel import Kernel
from core.skills.capability_registry import CapabilityRegistry

router = APIRouter(tags=["capabilities"])

_require_read = require_permissions(["skill.read"])


def _success_response(
    data: object, meta: MetaBlock, status_code: int = 200
) -> JSONResponse:
    """Build a manual success JSON response to avoid python 3.14 generic pydantic issues."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "meta": meta.model_dump(mode="json"),
        },
    )


def _get_capability_registry(
    kernel: Kernel = Depends(get_kernel),
) -> CapabilityRegistry:
    """Resolve CapabilityRegistry from the Kernel DI container."""
    return kernel.container.resolve(CapabilityRegistry)


@router.get("/discover")
async def discover_capabilities(
    request: Request,
    q: str = "",
    registry: CapabilityRegistry = Depends(_get_capability_registry),
    _auth: object = Depends(_require_read),
) -> Response:
    """GET /api/v1/capabilities/discover — Search or list registered capabilities."""
    if q:
        results = registry.search_capabilities(q)
    else:
        results = registry.list_all()

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()

    return _success_response(
        data={
            "capabilities": [c.model_dump() for c in results],
            "total": len(results),
        },
        meta=meta,
    )
