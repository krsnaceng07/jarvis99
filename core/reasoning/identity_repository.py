"""
PHASE: 42
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/104_PHASE_42_IDENTITY_ENGINE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/21be4144-6686-48ed-8e46-74ce7e189cd4/implementation_plan.md

AUTHORITATIVE:
    NO
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.models import AgentIdentityModel


class IdentityRepository:
    """Handles CRUD database operations for agent identities/personas."""

    async def save_identity(
        self, identity_model: AgentIdentityModel, session: AsyncSession
    ) -> None:
        """Insert or update an agent identity."""
        session.add(identity_model)
        await session.flush()

    async def get_identity(
        self, identity_id: UUID, session: AsyncSession
    ) -> Optional[AgentIdentityModel]:
        """Fetch an agent identity by ID."""
        stmt = select(AgentIdentityModel).where(AgentIdentityModel.id == identity_id)
        result = await session.execute(stmt)
        return result.scalars().first()

    async def get_active_identity(
        self, session: AsyncSession
    ) -> Optional[AgentIdentityModel]:
        """Fetch the current active agent identity from the database."""
        stmt = select(AgentIdentityModel).where(AgentIdentityModel.is_active.is_(True))
        result = await session.execute(stmt)
        return result.scalars().first()

    async def activate_identity(self, identity_id: UUID, session: AsyncSession) -> None:
        """Atomically sets target identity as active and marks all others inactive."""
        # 1. Mark all inactive
        stmt_deactivate = (
            update(AgentIdentityModel)
            .where(AgentIdentityModel.id != identity_id)
            .values(is_active=False)
        )
        await session.execute(stmt_deactivate)

        # 2. Mark target active
        stmt_activate = (
            update(AgentIdentityModel)
            .where(AgentIdentityModel.id == identity_id)
            .values(is_active=True)
        )
        await session.execute(stmt_activate)
        await session.flush()

    async def list_identities(self, session: AsyncSession) -> List[AgentIdentityModel]:
        """List all registered agent identities."""
        stmt = select(AgentIdentityModel)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def delete_identity(self, identity_id: UUID, session: AsyncSession) -> bool:
        """Delete an agent identity by ID. Returns True if deleted."""
        stmt = select(AgentIdentityModel).where(AgentIdentityModel.id == identity_id)
        result = await session.execute(stmt)
        identity = result.scalars().first()
        if identity:
            await session.delete(identity)
            await session.flush()
            return True
        return False
