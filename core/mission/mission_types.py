"""
PHASE: 44
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md

IMPLEMENTATION PLAN:
    Phase 44 approved plan — Mission & Autonomous Goal Scheduler

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Module role: Domain types for the Mission Scheduler. DTOs, enums, and
lightweight data contracts only. No business logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MissionStatus(str, Enum):
    """Lifecycle states of a Mission."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECOVERING = "recovering"


class MissionPriority(int, Enum):
    """Named priority tiers (maps to integer scheduling weight)."""

    CRITICAL = 10
    HIGH = 8
    NORMAL = 5
    LOW = 3
    BACKGROUND = 1


class MissionTask(BaseModel):
    """An atomic executable unit within a Mission."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: Optional[str] = None
    status: MissionStatus = MissionStatus.PENDING
    depends_on: List[UUID] = Field(
        default_factory=list,
        description="IDs of MissionTasks that must complete first.",
    )
    payload: Dict[str, Any] = Field(default_factory=dict)
    retries: int = Field(default=0, ge=0)
    max_retries: int = Field(default=3, ge=0)
    budget: float = Field(
        default=0.0, ge=0.0, description="Token/compute budget for this task."
    )
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class Mission(BaseModel):
    """A high-level autonomous mission composed of MissionTasks."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: Optional[str] = None
    goal_id: Optional[UUID] = Field(
        default=None,
        description="Associated PersistentGoal this mission fulfils.",
    )
    identity_id: Optional[UUID] = Field(
        default=None, description="Identity that owns this mission."
    )
    status: MissionStatus = MissionStatus.PENDING
    priority: int = Field(
        default=MissionPriority.NORMAL,
        ge=1,
        le=10,
        description="Scheduling priority 1-10.",
    )
    tasks: List[MissionTask] = Field(default_factory=list)
    total_budget: float = Field(
        default=100.0, ge=0.0, description="Maximum allowed budget for the mission."
    )
    used_budget: float = Field(default=0.0, ge=0.0)
    max_retries: int = Field(default=3, ge=0)
    retry_count: int = Field(default=0, ge=0)
    due_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def remaining_budget(self) -> float:
        """Budget remaining for the mission."""
        return max(0.0, self.total_budget - self.used_budget)

    @property
    def is_budget_exhausted(self) -> bool:
        """True if the mission has consumed all available budget."""
        return self.used_budget >= self.total_budget

    @property
    def progress(self) -> float:
        """Overall task completion percentage."""
        if not self.tasks:
            return 0.0
        done = sum(
            1 for t in self.tasks if t.status == MissionStatus.COMPLETED
        )
        return round(done / len(self.tasks) * 100.0, 2)


class MissionQueueItem(BaseModel):
    """Internal priority-queue entry linking a Mission to its schedule weight."""

    mission_id: UUID
    priority: int
    deadline: Optional[datetime] = None
    enqueued_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def effective_priority(self) -> float:
        """Compute effective scheduling weight (higher = run sooner).

        Incorporates both nominal priority and deadline urgency so that
        imminent deadlines boost a mission's position in the queue.
        """
        base = float(self.priority)
        if self.deadline:
            now = datetime.now(timezone.utc)
            seconds_remaining = (self.deadline - now).total_seconds()
            if seconds_remaining <= 0:
                return 9999.0  # Overdue — run immediately
            # Urgency bonus: 0→+5 as deadline approaches within 1 hour
            urgency = max(0.0, 5.0 * (1.0 - seconds_remaining / 3600.0))
            base += urgency
        return base


class MissionResult(BaseModel):
    """Outcome record produced after a Mission finishes."""

    mission_id: UUID
    status: MissionStatus
    tasks_completed: int
    tasks_failed: int
    budget_used: float
    duration_seconds: float
    error: Optional[str] = None
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class SchedulerConfig(BaseModel):
    """Tunable parameters for the Mission Scheduler."""

    max_concurrent_missions: int = Field(
        default=5, ge=1, description="Maximum parallel running missions."
    )
    poll_interval_seconds: float = Field(
        default=1.0, ge=0.1, description="Background runner poll cadence."
    )
    default_budget: float = Field(
        default=100.0, ge=0.0, description="Default mission budget."
    )
    default_max_retries: int = Field(default=3, ge=0)
    budget_overage_grace: float = Field(
        default=1.05,
        ge=1.0,
        description="Allow up to X% budget overage before hard-stopping.",
    )
