"""
PHASE: 30
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/92_PHASE_30_CLOUD_SYNC_HIGH_AVAILABILITY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.dependencies import get_sync_manager, require_permissions
from api.dto import MetaBlock, SuccessEnvelope
from core.security.auth_context import RequestContext

router = APIRouter()


class SyncPushResponse(BaseModel):
    status: str
    sync_id: str
    vector_clock: Dict[str, int]


class SyncPullResponse(BaseModel):
    status: str
    applied: bool
    sync_id: Optional[str] = None
    vector_clock: Dict[str, int]


class SyncStatusResponse(BaseModel):
    client_id: str
    vector_clock: Dict[str, int]
    last_sync_timestamp: Optional[str] = None


@router.post("/sync/push")
async def push_state(
    request: Request,
    _ctx: RequestContext = Depends(require_permissions(["platform.admin"])),
    sync_manager: Any = Depends(get_sync_manager),
) -> Response:
    """POST /api/v1/sync/push

    Encrypts local vault & database state, and uploads to cloud storage.
    """
    res = await sync_manager.push_state()
    data = SyncPushResponse(
        status=res["status"],
        sync_id=res["sync_id"],
        vector_clock=res["vector_clock"],
    )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[SyncPushResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.post("/sync/pull")
async def pull_state(
    request: Request,
    _ctx: RequestContext = Depends(require_permissions(["platform.admin"])),
    sync_manager: Any = Depends(get_sync_manager),
) -> Response:
    """POST /api/v1/sync/pull

    Pulls remote sync payload, decrypts, resolves conflicts, and applies state atomically.
    """
    res = await sync_manager.pull_state()
    data = SyncPullResponse(
        status=res["status"],
        applied=res["applied"],
        sync_id=res.get("sync_id"),
        vector_clock=res["vector_clock"]
        if "vector_clock" in res
        else sync_manager.vector_clock,
    )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[SyncPullResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.get("/sync/status")
async def get_sync_status(
    request: Request,
    _ctx: RequestContext = Depends(require_permissions(["platform.admin"])),
    sync_manager: Any = Depends(get_sync_manager),
) -> Response:
    """GET /api/v1/sync/status

    Retrieves the sync client ID, vector clocks, and last sync timestamp.
    """
    data = SyncStatusResponse(
        client_id=sync_manager.client_id,
        vector_clock=sync_manager.vector_clock,
        last_sync_timestamp=sync_manager.last_sync_timestamp,
    )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[SyncStatusResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))
