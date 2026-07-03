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

import contextvars
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class RequestContext(BaseModel):
    """Pydantic model representing standard metadata for the authenticated request."""

    user_id: UUID
    username: str
    roles: List[str]
    permissions: List[str]
    authentication_method: Literal["jwt", "api_key"]
    request_id: Optional[UUID] = None


# Thread-safe ContextVar containing the active RequestContext
active_context: contextvars.ContextVar[Optional[RequestContext]] = (
    contextvars.ContextVar("active_context", default=None)
)
