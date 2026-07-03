"""
PHASE: 17
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from api.dependencies import require_permissions
from api.dto import MetaBlock, SuccessEnvelope, UserProfileResponse
from core.security.auth_context import RequestContext

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me")
async def get_current_user(
    request: Request,
    ctx: RequestContext = Depends(require_permissions([])),
) -> Response:
    """GET /api/v1/users/me — return the authenticated user's profile metadata."""
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id is not None else MetaBlock()

    profile = UserProfileResponse(
        user_id=ctx.user_id,
        username=ctx.username,
        roles=ctx.roles,
        permissions=ctx.permissions,
        authentication_method=ctx.authentication_method,
    )
    envelope = SuccessEnvelope[UserProfileResponse](data=profile, meta=meta)
    return JSONResponse(
        status_code=200,
        content=envelope.model_dump(mode="json"),
    )
