"""
PHASE: 31
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/93_PHASE_31_FEDERATION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.dependencies import (
    get_federation_manager,
    get_kernel,
    require_permissions,
)
from api.dto import MetaBlock, SuccessEnvelope
from core.interfaces import EventBusInterface, InterAgentMessage
from core.security.auth_context import RequestContext

router = APIRouter()


class PeerRegisterRequest(BaseModel):
    node_id: str
    base_url: str


class PeerRegisterResponse(BaseModel):
    node_id: str
    base_url: str
    registered_at: str
    last_seen: Optional[str] = None


class PeerListResponse(BaseModel):
    peers: List[PeerRegisterResponse]


class PeerHealthResponse(BaseModel):
    status: str
    latency_ms: Optional[int] = None
    last_seen: Optional[str] = None
    version: Optional[str] = None
    reason: Optional[str] = None


class FederationRouteResponse(BaseModel):
    status: str


async def verify_federation_signature(
    request: Request,
    fed_mgr: Any = Depends(get_federation_manager),
) -> None:
    """FastAPI dependency: Validate headers and P2P HMAC signature of inbound requests."""
    headers = request.headers
    sender_node_id = headers.get("X-Jarvis-Node-Id")
    signature = headers.get("X-Jarvis-Signature")
    timestamp = headers.get("X-Jarvis-Timestamp")
    key_id = headers.get("X-Jarvis-Key-Id")
    created_at = headers.get("X-Jarvis-Created-At")
    message_id = headers.get("X-Jarvis-Message-Id")
    nonce = headers.get("X-Jarvis-Nonce")

    if not all(
        [
            sender_node_id,
            signature,
            timestamp,
            key_id,
            created_at,
            message_id,
            nonce,
        ]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing mandatory federation headers.",
        )

    body_bytes = await request.body()
    is_valid = await fed_mgr.verify_signature(
        sender_node_id=sender_node_id,
        signature=signature,
        timestamp_str=timestamp,
        body_bytes=body_bytes,
        key_id=key_id,
        created_at=created_at,
        message_id=message_id,
        nonce=nonce,
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Federation signature verification failed.",
        )


@router.post("/federation/route", dependencies=[Depends(verify_federation_signature)])
async def route_inbound_message(
    request: Request,
    message: InterAgentMessage,
    kernel: Any = Depends(get_kernel),
) -> Response:
    """POST /api/v1/federation/route

    Receives signed InterAgentMessage from peer and publishes to local event bus.
    """
    event_bus = kernel.container.resolve(EventBusInterface)
    # Publish locally (only after signature is verified)
    await event_bus.publish(f"agent.{message.receiver}.message", message)
    await event_bus.publish("federation.message_received", message)

    data = FederationRouteResponse(status="success")
    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[FederationRouteResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.post("/federation/peers/register")
async def register_peer(
    request: Request,
    body: PeerRegisterRequest,
    _ctx: RequestContext = Depends(require_permissions(["platform.admin"])),
    fed_mgr: Any = Depends(get_federation_manager),
) -> Response:
    """POST /api/v1/federation/peers/register

    Registers a peer node securely on this instance.
    """
    res = await fed_mgr.register_peer(node_id=body.node_id, base_url=body.base_url)
    data = PeerRegisterResponse(
        node_id=res["node_id"],
        base_url=res["base_url"],
        registered_at=res["registered_at"],
        last_seen=res["last_seen"],
    )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[PeerRegisterResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.get("/federation/peers")
async def list_peers(
    request: Request,
    _ctx: RequestContext = Depends(require_permissions(["platform.admin"])),
    fed_mgr: Any = Depends(get_federation_manager),
) -> Response:
    """GET /api/v1/federation/peers

    Lists registered peer nodes and health logs.
    """
    res = await fed_mgr.list_peers()
    peers_list = [
        PeerRegisterResponse(
            node_id=p["node_id"],
            base_url=p["base_url"],
            registered_at=p["registered_at"],
            last_seen=p["last_seen"],
        )
        for p in res
    ]
    data = PeerListResponse(peers=peers_list)

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[PeerListResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))


@router.get("/federation/peers/{node_id}/health")
async def get_peer_health(
    request: Request,
    node_id: str,
    _ctx: RequestContext = Depends(require_permissions(["platform.admin"])),
    fed_mgr: Any = Depends(get_federation_manager),
) -> Response:
    """GET /api/v1/federation/peers/{node_id}/health

    Ping check peer node health status.
    """
    res = await fed_mgr.ping_peer(node_id)
    data = PeerHealthResponse(
        status=res["status"],
        latency_ms=res.get("latency_ms"),
        last_seen=res.get("last_seen"),
        version=res.get("version"),
        reason=res.get("reason"),
    )

    request_id = getattr(request.state, "request_id", None)
    meta = MetaBlock(request_id=request_id) if request_id else MetaBlock()
    envelope = SuccessEnvelope[PeerHealthResponse](data=data, meta=meta)
    return JSONResponse(status_code=200, content=envelope.model_dump(mode="json"))
