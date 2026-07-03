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
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces import EventBusInterface, InterAgentMessage
from core.memory.security_models import RefreshTokenModel
from core.security.api_key_service import ApiKeyService
from core.security.configuration_service import ConfigurationService
from core.security.jwt_service import JWTService
from core.security.password_service import PasswordService
from core.security.rbac_service import RbacService
from core.security.revocation_service import RevocationService
from core.tools.security_repository import SecurityRepository


class AuthenticationService:
    """Orchestrates authentication flows, coordinating passwords, tokens, keys, and security telemetry."""

    def __init__(
        self,
        repo: SecurityRepository,
        password_service: PasswordService,
        jwt_service: JWTService,
        revocation_service: RevocationService,
        api_key_service: ApiKeyService,
        rbac_service: RbacService,
        config: ConfigurationService,
        event_bus: EventBusInterface,
    ) -> None:
        """Initialize the authentication coordinator with required sub-services."""
        self.repo = repo
        self.password_service = password_service
        self.jwt_service = jwt_service
        self.revocation_service = revocation_service
        self.api_key_service = api_key_service
        self.rbac_service = rbac_service
        self.config = config
        self.event_bus = event_bus

    async def _publish_security_event(self, action: str, body: dict) -> None:
        """Publish a secure identity event to the EventBus."""
        msg = InterAgentMessage(
            sender="auth_service",
            receiver="*",
            action=action,
            body={
                **body,
                "timestamp": time.time(),
            },
        )
        await self.event_bus.publish(action, msg)

    async def login_user(
        self, username: str, password: str, session: AsyncSession
    ) -> Optional[Tuple[str, str]]:
        """Authenticate a user account, issue access/refresh tokens on success, or update failed counters."""
        user = await self.repo.get_user_by_username(username, session)
        if not user:
            await self._publish_security_event(
                "user.auth_failed", {"username": username, "reason": "User not found"}
            )
            return None

        # Lockout check
        now = datetime.now(timezone.utc)
        if user.locked_until and user.locked_until > now:
            await self._publish_security_event(
                "user.auth_failed", {"username": username, "reason": "Account locked"}
            )
            return None

        # Validate password
        if not self.password_service.verify_password(password, user.hashed_password):
            # Increment failed attempts
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                # Lock for 15 minutes
                user.locked_until = now + timedelta(minutes=15)
                await self._publish_security_event(
                    "user.auth_failed",
                    {
                        "username": username,
                        "reason": "Max failed attempts reached, account locked",
                    },
                )
            else:
                await self._publish_security_event(
                    "user.auth_failed",
                    {"username": username, "reason": "Incorrect password"},
                )
            await self.repo.save_user(user, session)
            return None

        # Reset counters on success
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login = now
        await self.repo.save_user(user, session)

        # Generate JWT access token
        jti = str(uuid4())
        roles = [r.name for r in user.roles]
        permissions = self.rbac_service.resolve_permissions(user)
        access_token = self.jwt_service.sign_token(
            user_id=str(user.id),
            username=user.username,
            roles=roles,
            permissions=permissions,
            jti=jti,
        )

        # Generate Refresh Token
        raw_refresh = secrets.token_hex(64)
        token_hash = hashlib.sha256(raw_refresh.encode("utf-8")).hexdigest()
        expires_at = now + timedelta(days=self.config.refresh_token_expire_days)

        refresh_model = RefreshTokenModel(
            id=uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            is_revoked=False,
            expires_at=expires_at,
        )
        await self.repo.save_refresh_token(refresh_model, session)

        await self._publish_security_event(
            "user.login", {"user_id": str(user.id), "username": username}
        )

        return access_token, raw_refresh

    async def refresh_session(
        self, raw_refresh_token: str, session: AsyncSession
    ) -> Optional[Tuple[str, str]]:
        """Validate an active refresh token, rotate keys, and issue new access/refresh tokens."""
        token_hash = hashlib.sha256(raw_refresh_token.encode("utf-8")).hexdigest()
        refresh_model = await self.repo.get_refresh_token_by_hash(token_hash, session)

        if not refresh_model or refresh_model.is_revoked:
            return None

        now = datetime.now(timezone.utc)
        if refresh_model.expires_at < now:
            # Delete expired token
            await self.repo.delete_refresh_token(refresh_model, session)
            return None

        # Invalidate the old refresh token (rotate keys)
        user = refresh_model.user
        await self.repo.delete_refresh_token(refresh_model, session)

        # Generate new JWT access token
        jti = str(uuid4())
        roles = [r.name for r in user.roles]
        permissions = self.rbac_service.resolve_permissions(user)
        access_token = self.jwt_service.sign_token(
            user_id=str(user.id),
            username=user.username,
            roles=roles,
            permissions=permissions,
            jti=jti,
        )

        # Generate new Refresh Token
        new_raw_refresh = secrets.token_hex(64)
        new_token_hash = hashlib.sha256(new_raw_refresh.encode("utf-8")).hexdigest()
        new_expires_at = now + timedelta(days=self.config.refresh_token_expire_days)

        new_refresh_model = RefreshTokenModel(
            id=uuid4(),
            user_id=user.id,
            token_hash=new_token_hash,
            is_revoked=False,
            expires_at=new_expires_at,
        )
        await self.repo.save_refresh_token(new_refresh_model, session)

        await self._publish_security_event(
            "user.login",
            {"user_id": str(user.id), "username": user.username, "flow": "refresh"},
        )

        return access_token, new_raw_refresh

    async def logout_session(
        self, raw_access_token: str, raw_refresh_token: str, session: AsyncSession
    ) -> bool:
        """Revoke active tokens and log out the requesting session context."""
        # 1. Invalidate Refresh Token
        token_hash = hashlib.sha256(raw_refresh_token.encode("utf-8")).hexdigest()
        refresh_model = await self.repo.get_refresh_token_by_hash(token_hash, session)
        if refresh_model:
            await self.repo.delete_refresh_token(refresh_model, session)

        # 2. Extract and blacklist JWT JTI
        user_id = "unknown"
        try:
            claims = self.jwt_service.decode_token_unverified(raw_access_token)
            jti = claims.get("jti")
            exp = claims.get("exp")
            user_id = claims.get("sub", "unknown")
            if jti and exp:
                expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
                await self.revocation_service.revoke_token(jti, expires_at, session)
        except Exception:
            pass

        await self._publish_security_event("user.logout", {"user_id": user_id})
        return True
