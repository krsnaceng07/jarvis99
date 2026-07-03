"""
PHASE: 15
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/77_PHASE_15_PERSISTENT_EXECUTION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Integer, Numeric, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from core.memory.models import Base


class AgentRunModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a persistent Agent Run execution configuration and status."""

    __tablename__ = "agent_runs"

    id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    goal: Any = Column(String(4000), nullable=False)
    budget: Any = Column(Numeric(10, 4), nullable=False)
    state: Any = Column(String(50), nullable=False)
    metrics: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    failure_type: Any = Column(String(100), nullable=True)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class WorkflowExecutionModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a persistent Workflow Execution configuration and status."""

    __tablename__ = "workflow_executions"

    id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    workflow_id: Any = Column(Uuid(as_uuid=True), nullable=False)
    version: Any = Column(Integer, nullable=False)
    state: Any = Column(String(50), nullable=False)
    metrics: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class WorkflowStepExecutionModel(Base):  # type: ignore[misc]
    """SQLAlchemy model tracking run-level wave steps, attempts, and outcomes."""

    __tablename__ = "workflow_step_executions"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    execution_id: Any = Column(Uuid(as_uuid=True), nullable=False)
    step_name: Any = Column(String(255), nullable=False)
    state: Any = Column(String(50), nullable=False)
    output: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    error: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    attempts: Any = Column(Integer, default=1, nullable=False)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
