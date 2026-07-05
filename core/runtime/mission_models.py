"""
PHASE: 34
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/96_PHASE_34_AUTONOMOUS_AGENT_MISSION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/d42af1e8-69f8-4bf2-a03f-dc029da887c0/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

from core.memory.models import Base


class MissionModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a durable long-running mission."""

    __tablename__ = "missions"

    mission_id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    goal: Any = Column(String(4000), nullable=False)
    status: Any = Column(String(50), nullable=False, default="CREATED")
    assigned_agents: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    budget_limit: Any = Column(Float, nullable=True)
    budget_used: Any = Column(Float, nullable=False, default=0.0)
    plan_data: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    current_step: Any = Column(Integer, nullable=False, default=0)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class MissionCheckpointModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing an immutable state checkpoint for rollback."""

    __tablename__ = "mission_checkpoints"

    checkpoint_id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    mission_id: Any = Column(Uuid(as_uuid=True), nullable=False, index=True)
    step_index: Any = Column(Integer, nullable=False)
    state_data: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class MissionTimelineModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing an append-only timeline event log."""

    __tablename__ = "mission_timeline"

    event_id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    mission_id: Any = Column(Uuid(as_uuid=True), nullable=False, index=True)
    event_type: Any = Column(String(100), nullable=False)
    description: Any = Column(String(1000), nullable=False)
    timestamp: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
