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

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.memory.security_models import (
    ApiKeyModel,
    PermissionModel,
    RefreshTokenModel,
    RevokedTokenModel,
    RoleModel,
    UserModel,
)


class SecurityRepository:
    """Provides pure, CRUD-only database operations for authentication and authorization entities."""

    async def get_user_by_id(
        self, user_id: UUID, session: AsyncSession
    ) -> Optional[UserModel]:
        """Fetch a User by their unique ID, eager loading roles, direct permissions, and api keys."""
        stmt = (
            select(UserModel)
            .where(UserModel.id == user_id)
            .options(
                selectinload(UserModel.roles).selectinload(RoleModel.permissions),
                selectinload(UserModel.direct_permissions),
                selectinload(UserModel.api_keys),
                selectinload(UserModel.refresh_tokens),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_user_by_username(
        self, username: str, session: AsyncSession
    ) -> Optional[UserModel]:
        """Fetch a User by their username, eager loading roles, permissions, and direct overrides."""
        stmt = (
            select(UserModel)
            .where(UserModel.username == username)
            .options(
                selectinload(UserModel.roles).selectinload(RoleModel.permissions),
                selectinload(UserModel.direct_permissions),
                selectinload(UserModel.api_keys),
                selectinload(UserModel.refresh_tokens),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_user(self, user: UserModel, session: AsyncSession) -> None:
        """Persist or update a user account in the database."""
        session.add(user)

    async def get_role_by_name(
        self, name: str, session: AsyncSession
    ) -> Optional[RoleModel]:
        """Fetch a Role by its unique name, eager loading associated permissions."""
        stmt = (
            select(RoleModel)
            .where(RoleModel.name == name)
            .options(selectinload(RoleModel.permissions))
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_permission_by_scope(
        self, scope: str, session: AsyncSession
    ) -> Optional[PermissionModel]:
        """Fetch a Permission by its unique scope name."""
        stmt = select(PermissionModel).where(PermissionModel.scope == scope)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_role(self, role: RoleModel, session: AsyncSession) -> None:
        """Persist or update a Role definition in the database."""
        session.add(role)

    async def save_permission(
        self, permission: PermissionModel, session: AsyncSession
    ) -> None:
        """Persist or update a Permission definition in the database."""
        session.add(permission)

    async def get_api_key_by_hashed(
        self, hashed_key: str, session: AsyncSession
    ) -> Optional[ApiKeyModel]:
        """Fetch an ApiKey record by its unique salted SHA-256 hash."""
        stmt = (
            select(ApiKeyModel)
            .where(ApiKeyModel.hashed_key == hashed_key)
            .options(selectinload(ApiKeyModel.user))
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_api_key(self, api_key: ApiKeyModel, session: AsyncSession) -> None:
        """Persist or update an API Key record in the database."""
        session.add(api_key)

    async def get_refresh_token_by_hash(
        self, token_hash: str, session: AsyncSession
    ) -> Optional[RefreshTokenModel]:
        """Fetch a RefreshToken record by its unique salted SHA-256 hash."""
        stmt = (
            select(RefreshTokenModel)
            .where(RefreshTokenModel.token_hash == token_hash)
            .options(selectinload(RefreshTokenModel.user))
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_refresh_token(
        self, refresh_token: RefreshTokenModel, session: AsyncSession
    ) -> None:
        """Persist or update a Refresh Token record in the database."""
        session.add(refresh_token)

    async def delete_refresh_token(
        self, refresh_token: RefreshTokenModel, session: AsyncSession
    ) -> None:
        """Remove a Refresh Token record from the database."""
        await session.delete(refresh_token)

    async def is_jti_revoked(self, jti: str, session: AsyncSession) -> bool:
        """Check if a JWT identifier has been revoked and exists in the blacklist."""
        stmt = select(RevokedTokenModel).where(RevokedTokenModel.jti == jti)
        res = await session.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def save_revoked_token(
        self, revoked_token: RevokedTokenModel, session: AsyncSession
    ) -> None:
        """Persist a blacklisted JWT identifier in the database."""
        session.add(revoked_token)

    async def cleanup_expired_revoked_tokens(self, session: AsyncSession) -> int:
        """Delete expired blacklisted JWTs from the database and return count of deleted items."""
        now = datetime.now(timezone.utc)
        stmt = delete(RevokedTokenModel).where(RevokedTokenModel.expires_at < now)
        res = await session.execute(stmt)
        return getattr(res, "rowcount", 0)
