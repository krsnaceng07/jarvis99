"""
PHASE: 21
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 21 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class GoalConstraints(BaseModel):
    """Operational limits and security bounds for planning and execution."""

    budget: float = 10.0
    deadline_hours: float = 24.0
    token_limit: int = 50000
    security_level: str = "standard"
    allowed_tools: List[str] = Field(default_factory=list)
    forbidden_tools: List[str] = Field(default_factory=list)
    parallel_limit: int = 3
    schema_version: Literal["1.0"] = "1.0"


class Goal(BaseModel):
    """Represents a high-level goal request from the user."""

    id: UUID = Field(default_factory=uuid4)
    goal_text: str
    owner_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: Literal["1.0"] = "1.0"


class GoalAnalysis(BaseModel):
    """Structured analysis parameters derived from a parsed Goal."""

    goal_id: UUID
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    complexity: str = "medium"  # low, medium, high
    preconditions: List[str] = Field(default_factory=list)
    postconditions: List[str] = Field(default_factory=list)
    constraints: GoalConstraints = Field(default_factory=GoalConstraints)
    tags: List[str] = Field(default_factory=list)
    schema_version: Literal["1.0"] = "1.0"


class GoalAnalyzer:
    """Rule-based goal analysis parser. Extracts constraints and metadata from text."""

    def analyze(self, goal: Goal) -> GoalAnalysis:
        text = goal.goal_text.lower()

        # Rule extraction heuristics
        budget = 10.0
        budget_match = re.search(r"(?:budget|cost)\s*=\s*\$?(\d+(?:\.\d+)?)", text)
        if budget_match:
            budget = float(budget_match.group(1))
        elif "$" in text:
            dollar_match = re.search(r"\$(\d+(?:\.\d+)?)", text)
            if dollar_match:
                budget = float(dollar_match.group(1))

        deadline_hours = 24.0
        deadline_match = re.search(r"(?:deadline|time|hours)\s*=\s*(\d+(?:\.\d+)?)", text)
        if deadline_match:
            deadline_hours = float(deadline_match.group(1))

        parallel_limit = 3
        parallel_match = re.search(r"parallel\s*=\s*(\d+)", text)
        if parallel_match:
            parallel_limit = int(parallel_match.group(1))

        # Extract allowed/forbidden tools
        forbidden_tools: List[str] = []
        forbidden_match = re.search(r"forbidden\s*=\s*([a-zA-Z0-9_,]+)", text)
        if forbidden_match:
            forbidden_tools = [t.strip() for t in forbidden_match.group(1).split(",") if t.strip()]

        allowed_tools: List[str] = []
        allowed_match = re.search(r"allowed\s*=\s*([a-zA-Z0-9_,]+)", text)
        if allowed_match:
            allowed_tools = [t.strip() for t in allowed_match.group(1).split(",") if t.strip()]

        # Complexity determination
        complexity = "medium"
        if len(text.split()) > 20 or "complex" in text or "deploy" in text:
            complexity = "high"
        elif len(text.split()) < 5:
            complexity = "low"

        # Tags extraction
        tags = []
        tags_match = re.findall(r"#(\w+)", goal.goal_text)
        if tags_match:
            tags = [t.lower() for t in tags_match]

        constraints = GoalConstraints(
            budget=budget,
            deadline_hours=deadline_hours,
            allowed_tools=allowed_tools,
            forbidden_tools=forbidden_tools,
            parallel_limit=parallel_limit,
        )

        # Pre/Post conditions
        preconditions = []
        if "precondition:" in text:
            pre_match = re.search(r"precondition:\s*([a-zA-Z0-9_,]+)", text)
            if pre_match:
                preconditions = [p.strip() for p in pre_match.group(1).split(",") if p.strip()]

        postconditions = []
        if "postcondition:" in text:
            post_match = re.search(r"postcondition:\s*([a-zA-Z0-9_,]+)", text)
            if post_match:
                postconditions = [p.strip() for p in post_match.group(1).split(",") if p.strip()]

        return GoalAnalysis(
            goal_id=goal.id,
            complexity=complexity,
            preconditions=preconditions,
            postconditions=postconditions,
            constraints=constraints,
            tags=tags,
        )


# ---------------------------------------------------------------------------
# Phase 43 — Persistent Goal Engine additions
# ---------------------------------------------------------------------------

import logging  # noqa: E402
from enum import Enum  # noqa: E402
from typing import Any, Dict  # noqa: E402
from uuid import uuid4  # noqa: E402 (already imported above, re-export fine)

from core.interfaces import EventBusInterface, InterAgentMessage  # noqa: E402

_goal_logger = logging.getLogger("jarvis.core.reasoning.goal")


class GoalStatus(str, Enum):
    """Valid lifecycle states for a persistent agent goal."""

    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PersistentGoal(BaseModel):
    """Pydantic DTO for a persisted agent goal (Phase 43).

    Distinct from the planning-layer ``Goal`` (Phase 21) — this is the
    database-backed goal record with status, priority, and progress.
    """

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(..., description="Short human-readable goal title.")
    description: Optional[str] = Field(
        default=None, description="Detailed goal description."
    )
    status: GoalStatus = Field(
        default=GoalStatus.PENDING, description="Lifecycle state."
    )
    priority: int = Field(
        default=5, ge=1, le=10, description="Priority 1 (lowest) to 10 (highest)."
    )
    progress: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Completion percentage 0–100."
    )
    identity_id: Optional[UUID] = Field(
        default=None, description="Owner identity UUID."
    )
    parent_goal_id: Optional[UUID] = Field(
        default=None, description="Parent goal for hierarchical decomposition."
    )
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    due_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class GoalService:
    """Manages the full lifecycle of persistent agent goals."""

    def __init__(
        self,
        repository: Optional[Any] = None,
        event_bus: Optional[EventBusInterface] = None,
    ) -> None:
        """Initialise GoalService."""
        from core.reasoning.goal_repository import GoalRepository

        self.repository: Any = repository or GoalRepository()
        self.event_bus = event_bus

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_goal(
        self, goal: PersistentGoal, session: Optional[Any] = None
    ) -> PersistentGoal:
        """Persist a new goal and emit goal.created event."""
        from core.memory.models import AgentGoalModel

        model = AgentGoalModel(
            id=goal.id,
            title=goal.title,
            description=goal.description,
            status=goal.status.value,
            priority=goal.priority,
            progress=goal.progress,
            identity_id=goal.identity_id,
            parent_goal_id=goal.parent_goal_id,
            tags=goal.tags,
            metadata_=goal.metadata,
            due_at=goal.due_at,
            completed_at=goal.completed_at,
            created_at=goal.created_at,
            updated_at=goal.updated_at,
        )

        if session is not None:
            await self.repository.save_goal(model, session)
        else:
            from core.memory.database import db_manager

            async with db_manager.session() as sess:
                await self.repository.save_goal(model, sess)
                await sess.commit()

        await self._publish("goal.created", goal)
        _goal_logger.info("Created goal '%s' (id=%s)", goal.title, goal.id)
        return goal

    async def get_goal(
        self, goal_id: UUID, session: Optional[Any] = None
    ) -> Optional[PersistentGoal]:
        """Fetch a single goal by ID. Returns None if not found."""
        from core.memory.models import to_goal_dto

        if session is not None:
            model = await self.repository.get_goal(goal_id, session)
        else:
            from core.memory.database import db_manager

            async with db_manager.session() as sess:
                model = await self.repository.get_goal(goal_id, sess)

        return to_goal_dto(model) if model else None

    async def list_goals(
        self,
        status: Optional[GoalStatus] = None,
        identity_id: Optional[UUID] = None,
        session: Optional[Any] = None,
    ) -> List[PersistentGoal]:
        """List goals, optionally filtered by status and/or identity."""
        from core.memory.models import to_goal_dto

        if session is not None:
            models = await self.repository.list_goals(
                session,
                status=status.value if status else None,
                identity_id=identity_id,
            )
        else:
            from core.memory.database import db_manager

            async with db_manager.session() as sess:
                models = await self.repository.list_goals(
                    sess,
                    status=status.value if status else None,
                    identity_id=identity_id,
                )

        return [to_goal_dto(m) for m in models]

    async def update_goal(
        self,
        goal_id: UUID,
        updates: Dict[str, Any],
        session: Optional[Any] = None,
    ) -> PersistentGoal:
        """Apply partial field updates to a goal. Returns updated DTO."""
        from core.memory.models import to_goal_dto

        if session is not None:
            model = await self.repository.get_goal(goal_id, session)
            if not model:
                raise ValueError(f"Goal {goal_id} not found.")
            await self.repository.update_goal(goal_id, updates, session)
            await session.refresh(model)
            dto = to_goal_dto(model)
        else:
            from core.memory.database import db_manager

            async with db_manager.session() as sess:
                model = await self.repository.get_goal(goal_id, sess)
                if not model:
                    raise ValueError(f"Goal {goal_id} not found.")
                await self.repository.update_goal(goal_id, updates, sess)
                await sess.commit()
                model = await self.repository.get_goal(goal_id, sess)
                dto = to_goal_dto(model)

        await self._publish("goal.updated", dto)
        return dto

    async def activate_goal(
        self, goal_id: UUID, session: Optional[Any] = None
    ) -> PersistentGoal:
        """Set goal status to ACTIVE."""
        return await self.update_goal(
            goal_id,
            {"status": GoalStatus.ACTIVE.value,
             "updated_at": datetime.now(timezone.utc)},
            session,
        )

    async def complete_goal(
        self, goal_id: UUID, session: Optional[Any] = None
    ) -> PersistentGoal:
        """Mark goal COMPLETED, set progress=100 and completed_at."""
        dto = await self.update_goal(
            goal_id,
            {
                "status": GoalStatus.COMPLETED.value,
                "progress": 100.0,
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
            session,
        )
        await self._publish("goal.completed", dto)
        _goal_logger.info("Goal '%s' completed (id=%s)", dto.title, dto.id)
        return dto

    async def cancel_goal(
        self, goal_id: UUID, session: Optional[Any] = None
    ) -> PersistentGoal:
        """Mark goal CANCELLED."""
        return await self.update_goal(
            goal_id,
            {"status": GoalStatus.CANCELLED.value,
             "updated_at": datetime.now(timezone.utc)},
            session,
        )

    async def update_progress(
        self, goal_id: UUID, progress: float, session: Optional[Any] = None
    ) -> PersistentGoal:
        """Update goal progress (0–100). Auto-completes at 100."""
        clamped = max(0.0, min(100.0, progress))
        updates: Dict[str, Any] = {
            "progress": clamped,
            "updated_at": datetime.now(timezone.utc),
        }
        if clamped >= 100.0:
            updates["status"] = GoalStatus.COMPLETED.value
            updates["completed_at"] = datetime.now(timezone.utc)

        dto = await self.update_goal(goal_id, updates, session)
        if clamped >= 100.0:
            await self._publish("goal.completed", dto)
        return dto

    async def delete_goal(
        self, goal_id: UUID, session: Optional[Any] = None
    ) -> bool:
        """Permanently remove a goal. Returns True if deleted."""
        if session is not None:
            deleted = await self.repository.delete_goal(goal_id, session)
        else:
            from core.memory.database import db_manager

            async with db_manager.session() as sess:
                deleted = await self.repository.delete_goal(goal_id, sess)
                await sess.commit()

        if deleted:
            _goal_logger.info("Deleted goal id=%s", goal_id)
        return deleted

    async def get_active_goals(
        self,
        identity_id: Optional[UUID] = None,
        session: Optional[Any] = None,
    ) -> List[PersistentGoal]:
        """List only ACTIVE goals, optionally scoped to an identity."""
        return await self.list_goals(
            status=GoalStatus.ACTIVE, identity_id=identity_id, session=session
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _publish(self, event: str, goal: PersistentGoal) -> None:
        """Emit an event on the bus if configured."""
        if not self.event_bus:
            return
        msg = InterAgentMessage(
            sender="goal_service",
            receiver="all",
            action=event,
            body={
                "goal_id": str(goal.id),
                "title": goal.title,
                "status": goal.status.value,
                "progress": goal.progress,
            },
        )
        await self.event_bus.publish(event, msg)
