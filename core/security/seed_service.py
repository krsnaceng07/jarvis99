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

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.security_models import PermissionModel, RoleModel, UserModel
from core.security.configuration_service import ConfigurationService
from core.security.password_service import PasswordService
from core.tools.security_repository import SecurityRepository


class SecuritySeedService:
    """Handles seeding of default permission scopes, roles, and development admin accounts."""

    def __init__(
        self,
        repo: SecurityRepository,
        password_service: PasswordService,
        config: ConfigurationService,
    ) -> None:
        """Initialize the seed service with dependencies."""
        self.repo = repo
        self.password_service = password_service
        self.config = config

    async def seed_defaults(self, session: AsyncSession) -> None:
        """Seed roles, permissions, and development admins if not present."""
        # 1. Define default permissions
        scopes = [
            "agent.execute",
            "agent.read",
            "workflow.execute",
            "workflow.read",
            "audit.read",
            "vault.admin",
            "platform.admin",
            "skill.read",  # Phase 41 Capability Registry read (CR-001)
        ]
        permissions_map = {}
        for scope in scopes:
            perm = await self.repo.get_permission_by_scope(scope, session)
            if not perm:
                perm = PermissionModel(scope=scope)
                await self.repo.save_permission(perm, session)
            permissions_map[scope] = perm
        await session.flush()

        # 2. Define default roles and link permissions
        role_definitions = {
            "admin": scopes,
            "developer": [
                "agent.execute",
                "agent.read",
                "workflow.execute",
                "workflow.read",
            ],
            "viewer": ["agent.read", "workflow.read"],
        }
        roles_map = {}
        for role_name, role_scopes in role_definitions.items():
            role = await self.repo.get_role_by_name(role_name, session)
            if not role:
                role = RoleModel(name=role_name)
                await self.repo.save_role(role, session)
            # Ensure permissions are synced
            role.permissions = [permissions_map[s] for s in role_scopes]
            roles_map[role_name] = role
        await session.flush()

        # 3. Provision development seed administrator account
        if self.config.environment == "development":
            # Check if any user exists
            stmt = select(UserModel)
            res = await session.execute(stmt)
            existing_user = res.scalar()
            if not existing_user:
                # Seed admin user
                hashed = self.password_service.hash_password(self.config.admin_password)
                admin_user = UserModel(
                    id=uuid4(),
                    username=self.config.admin_username,
                    email="admin@jarvis.local",
                    hashed_password=hashed,
                    is_active=True,
                )
                admin_user.roles.append(roles_map["admin"])
                await self.repo.save_user(admin_user, session)
                await session.flush()
