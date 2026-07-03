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

from typing import List, Set

from core.memory.security_models import UserModel


class RbacService:
    """Manages role-based and permission-based access checks (RBAC/PBAC)."""

    def resolve_permissions(self, user: UserModel) -> List[str]:
        """Collect all scopes assigned to a user (role-inherited + direct permission overrides)."""
        scopes: Set[str] = set()

        # 1. Collect from roles
        for role in user.roles:
            for perm in role.permissions:
                scopes.add(perm.scope)

        # 2. Collect from direct overrides
        for perm in user.direct_permissions:
            scopes.add(perm.scope)

        return sorted(list(scopes))

    def has_permission(
        self, user_permissions: List[str], required_permissions: List[str]
    ) -> bool:
        """Verify if the user permissions list satisfies the required scopes."""
        user_set = set(user_permissions)
        # Check if all required permissions are met by the user
        return all(scope in user_set for scope in required_permissions)
