"""
PHASE: 42
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/104_PHASE_42_IDENTITY_ENGINE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/21be4144-6686-48ed-8e46-74ce7e189cd4/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Module role: FastAPI route handlers for the Identity Engine. Exposes CRUD
operations and the activation endpoint under /api/v1/identities. All business
logic is delegated to IdentityService (resolved via DI). No DB access here.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import get_identity_service

logger = logging.getLogger("jarvis.api.routes.identity")

router = APIRouter(prefix="/identities", tags=["Identity Engine"])


# ---------------------------------------------------------------------------
# Request / Response DTOs (API-layer only; not shared with core)
# ---------------------------------------------------------------------------


class CreateIdentityRequest(BaseModel):
    """Payload for creating a new agent identity."""

    name: str = Field(..., description="Unique human-readable name of the persona.")
    role: str = Field(..., description="Target role (e.g. 'developer', 'researcher').")
    system_prompt: str = Field(..., description="LLM system instructions for this identity.")
    personality: Optional[str] = Field(default=None, description="Behavioral characteristics.")
    communication_style: Optional[str] = Field(default=None, description="Tone/formatting guidelines.")
    allowed_capabilities: List[str] = Field(default_factory=list, description="Permitted capability tags.")
    default_model: Optional[str] = Field(default=None, description="Default LLM model identifier.")
    memory_scope: Optional[str] = Field(default=None, description="Memory retrieval scope boundary.")
    permission_profile: Optional[str] = Field(default=None, description="Security permission profile.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom key-value settings.")
    is_active: bool = Field(default=False, description="Whether to immediately activate this identity.")


class IdentityResponse(BaseModel):
    """Serialised representation of an AgentIdentity returned by the API."""

    id: UUID
    name: str
    role: str
    system_prompt: str
    personality: Optional[str]
    communication_style: Optional[str]
    allowed_capabilities: List[str]
    default_model: Optional[str]
    memory_scope: Optional[str]
    permission_profile: Optional[str]
    metadata: Dict[str, Any]
    is_active: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ActivateIdentityResponse(BaseModel):
    """Response for identity activation endpoint."""

    success: bool
    identity: IdentityResponse
    message: str


# ---------------------------------------------------------------------------
# Endpoint helpers
# ---------------------------------------------------------------------------


def _to_response(identity: Any) -> IdentityResponse:
    """Map an AgentIdentity DTO to the API IdentityResponse."""
    return IdentityResponse(
        id=identity.id,
        name=identity.name,
        role=identity.role,
        system_prompt=identity.system_prompt,
        personality=identity.personality,
        communication_style=identity.communication_style,
        allowed_capabilities=identity.allowed_capabilities,
        default_model=identity.default_model,
        memory_scope=identity.memory_scope,
        permission_profile=identity.permission_profile,
        metadata=identity.metadata,
        is_active=identity.is_active,
        created_at=identity.created_at.isoformat(),
        updated_at=identity.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=List[IdentityResponse],
    summary="List all agent identities",
    description="Returns all configured agent identities ordered by creation date.",
)
async def list_identities(
    identity_service: Any = Depends(get_identity_service),
) -> List[IdentityResponse]:
    """GET /api/v1/identities — list all configured identities."""
    try:
        identities = await identity_service.list_identities()
        return [_to_response(i) for i in identities]
    except Exception as exc:
        logger.exception("Failed to list identities: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list identities: {exc}",
        ) from exc


@router.post(
    "",
    response_model=IdentityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agent identity",
    description="Creates a new agent persona. If `is_active` is true, immediately activates it.",
)
async def create_identity(
    payload: CreateIdentityRequest,
    identity_service: Any = Depends(get_identity_service),
) -> IdentityResponse:
    """POST /api/v1/identities — create a new identity record."""
    from core.reasoning.identity import AgentIdentity

    identity = AgentIdentity(
        name=payload.name,
        role=payload.role,
        system_prompt=payload.system_prompt,
        personality=payload.personality,
        communication_style=payload.communication_style,
        allowed_capabilities=payload.allowed_capabilities,
        default_model=payload.default_model,
        memory_scope=payload.memory_scope,
        permission_profile=payload.permission_profile,
        metadata=payload.metadata,
        is_active=payload.is_active,
    )

    try:
        created = await identity_service.create_identity(identity)
        logger.info("Created identity '%s' (id=%s)", created.name, created.id)
        return _to_response(created)
    except Exception as exc:
        logger.exception("Failed to create identity: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create identity: {exc}",
        ) from exc


@router.get(
    "/active",
    response_model=IdentityResponse,
    summary="Get the currently active identity",
    description="Returns the identity currently marked as active, or the system default.",
)
async def get_active_identity(
    identity_service: Any = Depends(get_identity_service),
) -> IdentityResponse:
    """GET /api/v1/identities/active — fetch active identity."""
    try:
        identity = await identity_service.get_active_identity()
        return _to_response(identity)
    except Exception as exc:
        logger.exception("Failed to get active identity: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get active identity: {exc}",
        ) from exc


@router.post(
    "/{identity_id}/activate",
    response_model=ActivateIdentityResponse,
    summary="Activate a specific identity",
    description=(
        "Atomically sets the target identity as active and marks all others "
        "as inactive. Triggers working-memory flush and context update."
    ),
)
async def activate_identity(
    identity_id: UUID,
    identity_service: Any = Depends(get_identity_service),
) -> ActivateIdentityResponse:
    """POST /api/v1/identities/{identity_id}/activate — switch active identity."""
    try:
        activated = await identity_service.activate_identity(identity_id)
        logger.info("Activated identity '%s' (id=%s)", activated.name, activated.id)
        return ActivateIdentityResponse(
            success=True,
            identity=_to_response(activated),
            message=f"Identity '{activated.name}' is now active.",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to activate identity %s: %s", identity_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate identity: {exc}",
        ) from exc


@router.delete(
    "/{identity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an agent identity",
    description=(
        "Permanently removes the identity record. If the deleted identity was "
        "active the system falls back to the default identity."
    ),
)
async def delete_identity(
    identity_id: UUID,
    identity_service: Any = Depends(get_identity_service),
) -> None:
    """DELETE /api/v1/identities/{identity_id} — remove an identity."""
    try:
        deleted = await identity_service.delete_identity(identity_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Identity with ID {identity_id} not found.",
            )
        logger.info("Deleted identity id=%s", identity_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete identity %s: %s", identity_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete identity: {exc}",
        ) from exc
