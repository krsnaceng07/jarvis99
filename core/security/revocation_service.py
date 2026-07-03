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

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.security_models import RevokedTokenModel
from core.tools.security_repository import SecurityRepository


class RevocationService:
    """Manages JWT revocation checks using the database repository."""

    def __init__(self, repo: SecurityRepository) -> None:
        """Initialize the revocation service with the security repository."""
        self.repo = repo

    async def revoke_token(
        self, jti: str, expires_at: datetime, session: AsyncSession
    ) -> None:
        """Save a blacklisted JWT identifier in the database."""
        revoked = RevokedTokenModel(jti=jti, expires_at=expires_at)
        await self.repo.save_revoked_token(revoked, session)

    async def is_token_revoked(self, jti: str, session: AsyncSession) -> bool:
        """Check if a JWT identifier has been blacklisted."""
        return await self.repo.is_jti_revoked(jti, session)

    async def purge_expired_revocations(self, session: AsyncSession) -> int:
        """Clean up expired blacklisted token records to save database space."""
        return await self.repo.cleanup_expired_revoked_tokens(session)
