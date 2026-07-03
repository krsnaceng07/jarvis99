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
from typing import Any, List

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Uuid,
)
from sqlalchemy.orm import Mapped, relationship

from core.memory.models import Base

# Association Table: Role <-> Permission
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

# Association Table: User <-> Role
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

# Association Table: User <-> Direct Permission Override
user_permissions = Table(
    "user_permissions",
    Base.metadata,
    Column(
        "user_id",
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class UserModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a User Account."""

    __tablename__ = "users"

    id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    username: Any = Column(String(255), unique=True, nullable=False, index=True)
    email: Any = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Any = Column(String(255), nullable=False)
    is_active: Any = Column(Boolean, nullable=False, default=True)
    tenant_id: Any = Column(Uuid(as_uuid=True), nullable=True)
    failed_login_count: Any = Column(Integer, nullable=False, default=0)
    locked_until: Any = Column(DateTime, nullable=True)
    password_changed_at: Any = Column(DateTime, nullable=True)
    last_login: Any = Column(DateTime, nullable=True)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    roles: Mapped[List["RoleModel"]] = relationship(
        "RoleModel",
        secondary=user_roles,
        back_populates="users",
    )

    direct_permissions: Mapped[List["PermissionModel"]] = relationship(
        "PermissionModel",
        secondary=user_permissions,
        back_populates="direct_users",
    )

    api_keys: Mapped[List["ApiKeyModel"]] = relationship(
        "ApiKeyModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    refresh_tokens: Mapped[List["RefreshTokenModel"]] = relationship(
        "RefreshTokenModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class RoleModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a User Role."""

    __tablename__ = "roles"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    name: Any = Column(String(100), unique=True, nullable=False, index=True)

    users: Mapped[List[UserModel]] = relationship(
        "UserModel",
        secondary=user_roles,
        back_populates="roles",
    )

    permissions: Mapped[List["PermissionModel"]] = relationship(
        "PermissionModel",
        secondary=role_permissions,
        back_populates="roles",
    )


class PermissionModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a permission scope."""

    __tablename__ = "permissions"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    scope: Any = Column(String(100), unique=True, nullable=False, index=True)

    roles: Mapped[List[RoleModel]] = relationship(
        "RoleModel",
        secondary=role_permissions,
        back_populates="permissions",
    )

    direct_users: Mapped[List[UserModel]] = relationship(
        "UserModel",
        secondary=user_permissions,
        back_populates="direct_permissions",
    )


class ApiKeyModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing programmatic access API Keys."""

    __tablename__ = "api_keys"

    id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    user_id: Any = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Any = Column(String(100), nullable=False)
    prefix: Any = Column(String(16), nullable=False)
    hashed_key: Any = Column(String(255), unique=True, nullable=False, index=True)
    is_active: Any = Column(Boolean, nullable=False, default=True)
    expires_at: Any = Column(DateTime, nullable=True)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user: Mapped[UserModel] = relationship("UserModel", back_populates="api_keys")


class RefreshTokenModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a user session refresh token."""

    __tablename__ = "refresh_tokens"

    id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    user_id: Any = Column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Any = Column(String(255), unique=True, nullable=False, index=True)
    is_revoked: Any = Column(Boolean, nullable=False, default=False)
    expires_at: Any = Column(DateTime, nullable=False)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user: Mapped[UserModel] = relationship("UserModel", back_populates="refresh_tokens")


class RevokedTokenModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing blacklisted JWT JTIs."""

    __tablename__ = "revoked_tokens"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    jti: Any = Column(String(255), unique=True, nullable=False, index=True)
    expires_at: Any = Column(DateTime, nullable=False)
