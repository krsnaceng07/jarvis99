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

Module role: Pydantic transport contracts for the FastAPI gateway. All
response payloads are wrapped in the frozen success/error envelopes
mandated by docs/architecture/02_API_CONTRACTS_FREEZE.md (C1/C2).
Frozen core enums/DTOs are re-exported, never redefined, so the API
contract cannot drift from the frozen core. This module imports FROM
core/ only; core/ never imports from api/ (C5).
"""

from datetime import datetime, timezone
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# Frozen core re-exports (rank 6 authority). Do NOT redefine locally.
from core.reasoning.engine_dto import EngineMetrics, FailureType, SessionState
from core.tools.workflow_dto import WorkflowMetrics, WorkflowState, WorkflowStep
from core.version import VERSION

__all__ = [
    # Request DTOs
    "AgentRunRequest",
    "WorkflowSubmitRequest",
    "LoginRequest",
    "RefreshRequest",
    "LogoutRequest",
    "ApiKeyCreateRequest",
    # Response payload DTOs (the "data" field inside SuccessEnvelope)
    "AgentRunAcceptedResponse",
    "AgentRunStatusResponse",
    "WorkflowSubmitResponse",
    "WorkflowStatusResponse",
    "AgentRunsHistoryResponse",
    "WorkflowExecutionsHistoryResponse",
    "HealthResponse",
    "LoginResponse",
    "LogoutResponse",
    "UserProfileResponse",
    "ApiKeyCreateResponse",
    # Error DTO
    "ErrorDetail",
    # Envelope DTOs (frozen wrappers - C1/C2)
    "MetaBlock",
    "SuccessEnvelope",
    "ErrorEnvelope",
    # Re-exported frozen enums/DTOs for route handler convenience
    "SessionState",
    "FailureType",
    "EngineMetrics",
    "WorkflowState",
    "WorkflowStep",
    "WorkflowMetrics",
    # Constants
    "API_VERSION",
    "GATEWAY_PHASE",
]

# --- Frozen constants (CR-001: api_version on every response DTO) -----------
API_VERSION: Literal["v1"] = "v1"
GATEWAY_PHASE: Literal["Phase 14"] = "Phase 14"


# ---------------------------------------------------------------------------
# Request DTOs
# ---------------------------------------------------------------------------


class AgentRunRequest(BaseModel):
    """Inbound request to asynchronously execute an agent goal."""

    goal: str = Field(min_length=1, max_length=4000)
    budget: float = Field(default=10.0, ge=0.0, le=1000.0)


class WorkflowSubmitRequest(BaseModel):
    """Inbound request to validate, compile, and persist a workflow plan.

    Reuses Phase 13's WorkflowStep; the composed WorkflowPlan is built in
    the route handler from these fields (no parallel model in api/).
    """

    name: str = Field(min_length=1)
    steps: list[WorkflowStep]
    version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Response payload DTOs (become the "data" field inside SuccessEnvelope)
# ---------------------------------------------------------------------------


class AgentRunAcceptedResponse(BaseModel):
    """Returned on POST /api/v1/agent/run (HTTP 202). The run executes async."""

    run_id: UUID
    status: Literal["accepted"] = "accepted"
    trace_id: UUID
    api_version: Literal["v1"] = API_VERSION


class AgentRunStatusResponse(BaseModel):
    """Returned on GET /api/v1/agent/runs/{run_id}."""

    run_id: UUID
    state: SessionState
    metrics: EngineMetrics | None = None
    failure_type: FailureType | None = None
    api_version: Literal["v1"] = API_VERSION


class WorkflowSubmitResponse(BaseModel):
    """Returned on POST /api/v1/workflows (HTTP 202)."""

    workflow_id: UUID
    version: int
    status: WorkflowState = WorkflowState.PENDING
    api_version: Literal["v1"] = API_VERSION


class WorkflowStatusResponse(BaseModel):
    """Returned on GET /api/v1/workflows/{workflow_id}."""

    workflow_id: UUID
    state: WorkflowState
    metrics: WorkflowMetrics | None = None
    api_version: Literal["v1"] = API_VERSION


class AgentRunsHistoryResponse(BaseModel):
    """Wrapper DTO carrying a list of AgentRunStatusResponse items."""

    runs: list[AgentRunStatusResponse]
    api_version: Literal["v1"] = API_VERSION


class WorkflowExecutionsHistoryResponse(BaseModel):
    """Wrapper DTO carrying a list of WorkflowStatusResponse items."""

    executions: list[WorkflowStatusResponse]
    api_version: Literal["v1"] = API_VERSION


class HealthResponse(BaseModel):
    """Returned on GET /api/v1/health (200 healthy / 503 degraded).

    CR-001 reshaped for least-privilege: connectivity/resources/registered
    services are NOT exposed. `version` sourced from core.version.VERSION.
    """

    status: Literal["healthy", "degraded"]
    version: str = Field(default=VERSION)
    phase: Literal["Phase 14"] = GATEWAY_PHASE
    uptime_seconds: float
    api_version: Literal["v1"] = API_VERSION


# ---------------------------------------------------------------------------
# Error DTO (the "error" field inside ErrorEnvelope)
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """Sanitized error payload. Never contains stack traces or credentials (C7)."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    api_version: Literal["v1"] = API_VERSION


# ---------------------------------------------------------------------------
# Envelope DTOs (frozen wrappers - required by C1/C2)
# ---------------------------------------------------------------------------


class MetaBlock(BaseModel):
    """Per-response metadata. Always populated by middleware."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: UUID = Field(default_factory=uuid4)


T = TypeVar("T", bound=BaseModel)


class SuccessEnvelope(BaseModel, Generic[T]):
    """Frozen success envelope (C1). Wraps every successful REST response."""

    success: Literal[True] = True
    data: T
    meta: MetaBlock = Field(default_factory=MetaBlock)


class ErrorEnvelope(BaseModel):
    """Frozen error envelope (C2). Wraps every failed REST response."""

    success: Literal[False] = False
    error: ErrorDetail
    meta: MetaBlock = Field(default_factory=MetaBlock)


# ---------------------------------------------------------------------------
# Phase 17 Security DTOs
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Inbound request to login user."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Returned on successful login, containing session tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    api_version: Literal["v1"] = API_VERSION


class RefreshRequest(BaseModel):
    """Inbound request to rotate session tokens using refresh token."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Inbound request to log out session."""

    refresh_token: str


class ApiKeyCreateRequest(BaseModel):
    """Inbound request to generate a new programmatic API Key."""

    name: str


class ApiKeyCreateResponse(BaseModel):
    """Returned on successful API Key creation, containing the single-view raw key."""

    id: UUID
    name: str
    raw_key: str


class LogoutResponse(BaseModel):
    """Returned on successful logout."""

    message: str
    api_version: Literal["v1"] = API_VERSION


class UserProfileResponse(BaseModel):
    """Authenticated user profile returned by GET /api/v1/users/me."""

    user_id: UUID
    username: str
    roles: list[str]
    permissions: list[str]
    authentication_method: Literal["jwt", "api_key"]
    api_version: Literal["v1"] = API_VERSION
