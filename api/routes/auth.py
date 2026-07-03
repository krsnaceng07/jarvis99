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

import time
from uuid import uuid4

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (
    get_authentication_service,
    get_db_session,
    get_kernel,
    get_security_repository,
    require_permissions,
)
from api.dto import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    SuccessEnvelope,
)
from core.exceptions import AuthenticationError
from core.interfaces import EventBusInterface, InterAgentMessage
from core.memory.security_models import ApiKeyModel
from core.security.api_key_service import ApiKeyService
from core.security.auth_context import RequestContext
from core.security.auth_service import AuthenticationService
from core.tools.security_repository import SecurityRepository

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=SuccessEnvelope[LoginResponse])
async def login(
    request: LoginRequest,
    auth_service: AuthenticationService = Depends(get_authentication_service),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessEnvelope[LoginResponse]:
    """Authenticate account credentials and return access and refresh tokens."""
    tokens = await auth_service.login_user(request.username, request.password, session)
    if not tokens:
        raise AuthenticationError(
            code="AUTH_004", message="Invalid username or password."
        )

    access_token, refresh_token = tokens
    return SuccessEnvelope(
        data=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )
    )


@router.post("/refresh", response_model=SuccessEnvelope[LoginResponse])
async def refresh(
    request: RefreshRequest,
    auth_service: AuthenticationService = Depends(get_authentication_service),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessEnvelope[LoginResponse]:
    """Rotate session tokens using a valid refresh token."""
    tokens = await auth_service.refresh_session(request.refresh_token, session)
    if not tokens:
        raise AuthenticationError(
            code="AUTH_007", message="Invalid or expired refresh token."
        )

    access_token, refresh_token = tokens
    return SuccessEnvelope(
        data=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )
    )


@router.post("/logout", response_model=SuccessEnvelope[LogoutResponse])
async def logout(
    request: LogoutRequest,
    authorization: str = Header(...),
    auth_service: AuthenticationService = Depends(get_authentication_service),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessEnvelope[LogoutResponse]:
    """Revoke active tokens and log out the requesting session context."""
    if not authorization.startswith("Bearer "):
        raise AuthenticationError(
            code="AUTH_003", message="Invalid authorization format for logout."
        )

    access_token = authorization[7:]
    await auth_service.logout_session(access_token, request.refresh_token, session)
    return SuccessEnvelope(data=LogoutResponse(message="Logged out successfully."))


@router.post("/keys", response_model=SuccessEnvelope[ApiKeyCreateResponse])
async def create_api_key(
    request: ApiKeyCreateRequest,
    ctx: "RequestContext" = Depends(require_permissions([])),  # Any authenticated user
    repo: SecurityRepository = Depends(get_security_repository),
    session: AsyncSession = Depends(get_db_session),
) -> SuccessEnvelope[ApiKeyCreateResponse]:
    """Create a new programmatic API Key for the authenticated user."""
    kernel = get_kernel()
    api_key_service = kernel.container.resolve(ApiKeyService)
    event_bus = kernel.container.resolve(EventBusInterface)  # type: ignore[type-abstract]

    raw_key, hashed_key = api_key_service.generate_api_key(prefix="jvs_live_")

    key_id = uuid4()
    api_key_model = ApiKeyModel(
        id=key_id,
        user_id=ctx.user_id,
        name=request.name,
        prefix="jvs_live_",
        hashed_key=hashed_key,
        is_active=True,
    )

    await repo.save_api_key(api_key_model, session)

    # Publish audit event
    msg = InterAgentMessage(
        sender="auth_routes",
        receiver="*",
        action="apikey.created",
        body={
            "key_id": str(key_id),
            "user_id": str(ctx.user_id),
            "timestamp": time.time(),
        },
    )
    await event_bus.publish("apikey.created", msg)

    return SuccessEnvelope(
        data=ApiKeyCreateResponse(
            id=key_id,
            name=request.name,
            raw_key=raw_key,
        )
    )
