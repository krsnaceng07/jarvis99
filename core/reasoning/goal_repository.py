"""
PHASE: 43
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/105_PHASE_43_GOAL_ENGINE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/21be4144-6686-48ed-8e46-74ce7e189cd4/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Module role: Repository — CRUD + filtering for AgentGoalModel. No business
logic, no events. Pure database operations only (Phase invariant §7.7).
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.models import AgentGoalModel


class GoalRepository:
    """CRUD operations for persisted agent goals."""

    async def save_goal(
        self, goal_model: AgentGoalModel, session: AsyncSession
    ) -> None:
        """Insert or merge a goal record."""
        session.add(goal_model)
        await session.flush()

    async def get_goal(
        self, goal_id: UUID, session: AsyncSession
    ) -> Optional[AgentGoalModel]:
        """Fetch a goal by primary key."""
        stmt = select(AgentGoalModel).where(AgentGoalModel.id == goal_id)
        result = await session.execute(stmt)
        return result.scalars().first()

    async def list_goals(
        self,
        session: AsyncSession,
        status: Optional[str] = None,
        identity_id: Optional[UUID] = None,
    ) -> List[AgentGoalModel]:
        """List goals with optional filters on status and identity."""
        stmt = select(AgentGoalModel)
        if status is not None:
            stmt = stmt.where(AgentGoalModel.status == status)
        if identity_id is not None:
            stmt = stmt.where(AgentGoalModel.identity_id == identity_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_goal(
        self,
        goal_id: UUID,
        updates: Dict[str, Any],
        session: AsyncSession,
    ) -> None:
        """Apply a dict of column updates to the specified goal row."""
        stmt = (
            update(AgentGoalModel)
            .where(AgentGoalModel.id == goal_id)
            .values(**updates)
        )
        await session.execute(stmt)
        await session.flush()

    async def delete_goal(
        self, goal_id: UUID, session: AsyncSession
    ) -> bool:
        """Delete a goal by ID. Returns True if a row was deleted."""
        stmt = select(AgentGoalModel).where(AgentGoalModel.id == goal_id)
        result = await session.execute(stmt)
        goal = result.scalars().first()
        if goal:
            await session.delete(goal)
            await session.flush()
            return True
        return False
