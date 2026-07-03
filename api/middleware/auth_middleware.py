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

import hashlib
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from api.dependencies import get_kernel
from api.middleware import map_exception_to_envelope
from core.exceptions import AuthenticationError, JarvisError
from core.security.api_key_service import ApiKeyService
from core.security.auth_context import RequestContext, active_context
from core.security.jwt_service import JWTService
from core.security.rbac_service import RbacService
from core.security.revocation_service import RevocationService
from core.tools.security_repository import SecurityRepository


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware parsing Authorization header, validating JWT/API Keys, and propagating RequestContext."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process incoming requests, verify authorization headers, and execute downstream handlers."""
        auth_header = request.headers.get("Authorization")
        request_id = getattr(request.state, "request_id", uuid.uuid4())

        ctx_token = None

        if auth_header:
            try:
                # 1. Bearer JWT Authentication
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
                    kernel = get_kernel()
                    jwt_service = kernel.container.resolve(JWTService)
                    revocation_service = kernel.container.resolve(RevocationService)

                    # Verify signature and expiration
                    claims = jwt_service.verify_token(token)
                    jti = claims.get("jti")

                    # Verify revocation blacklist status
                    from core.memory.database import db_manager

                    async with db_manager.session() as session:
                        if jti and await revocation_service.is_token_revoked(
                            jti, session
                        ):
                            raise AuthenticationError(
                                code="AUTH_001",
                                message="Access token has been revoked.",
                            )

                    # Bind active ContextVar
                    req_ctx = RequestContext(
                        user_id=uuid.UUID(claims["sub"]),
                        username=claims["username"],
                        roles=claims["roles"],
                        permissions=claims["permissions"],
                        authentication_method="jwt",
                        request_id=request_id,
                    )
                    ctx_token = active_context.set(req_ctx)

                # 2. Key Programmatic API Key Authentication
                elif auth_header.startswith("Key "):
                    raw_key = auth_header[4:]
                    kernel = get_kernel()
                    api_key_service = kernel.container.resolve(ApiKeyService)
                    security_repository = kernel.container.resolve(SecurityRepository)
                    rbac_service = kernel.container.resolve(RbacService)

                    # Compute candidate hash lookup
                    hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

                    from core.memory.database import db_manager

                    async with db_manager.session() as session:
                        key_model = await security_repository.get_api_key_by_hashed(
                            hashed_key, session
                        )
                        if not key_model or not key_model.is_active:
                            raise AuthenticationError(
                                code="AUTH_002", message="Invalid or inactive API Key."
                            )

                        # Constant-time verify the raw key
                        if not api_key_service.verify_api_key(
                            raw_key, key_model.hashed_key
                        ):
                            raise AuthenticationError(
                                code="AUTH_002", message="Invalid API Key."
                            )

                        user = key_model.user
                        roles = [r.name for r in user.roles]
                        permissions = rbac_service.resolve_permissions(user)

                        # Bind active ContextVar
                        req_ctx = RequestContext(
                            user_id=user.id,
                            username=user.username,
                            roles=roles,
                            permissions=permissions,
                            authentication_method="api_key",
                            request_id=request_id,
                        )
                        ctx_token = active_context.set(req_ctx)

                else:
                    raise AuthenticationError(
                        code="AUTH_003",
                        message="Unsupported authentication method prefix.",
                    )

            except Exception as exc:
                # Map exception safely to standard JSON error envelopes
                wrapped_exc = exc
                if not isinstance(exc, JarvisError):
                    wrapped_exc = AuthenticationError(
                        code="AUTH_999", message=f"Authentication failed: {str(exc)}"
                    )

                status_code, envelope = map_exception_to_envelope(
                    wrapped_exc, request_id
                )
                return JSONResponse(
                    status_code=status_code, content=envelope.model_dump(mode="json")
                )

        try:
            return await call_next(request)
        finally:
            if ctx_token is not None:
                active_context.reset(ctx_token)
