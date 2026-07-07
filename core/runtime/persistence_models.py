"""JARVIS OS - Swarm Persistence Database Models.

SQLAlchemy database models for swarm tasks, subagents, snapshots, messages, and iteration journals.
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


class SwarmTaskModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a swarm task and its execution state."""

    __tablename__ = "swarm_tasks"

    task_id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    goal: Any = Column(String(4000), nullable=False)
    priority: Any = Column(String(50), nullable=False)
    status: Any = Column(String(50), nullable=False)
    capabilities: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    timeout: Any = Column(Float, nullable=False, default=900.0)
    retry: Any = Column(Integer, nullable=False, default=0)
    dependencies: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    metadata_: Any = Column("metadata", JSON().with_variant(JSONB, "postgresql"), nullable=True)
    version: Any = Column(Integer, nullable=False, default=1)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SwarmAgentModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a registered subagent and its active metrics."""

    __tablename__ = "swarm_agents"

    agent_id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    name: Any = Column(String(255), nullable=False)
    status: Any = Column(String(50), nullable=False)
    capabilities: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    permissions: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    cpu_load: Any = Column(Float, nullable=False, default=0.0)
    memory: Any = Column(Float, nullable=False, default=0.0)
    recent_failures: Any = Column(Integer, nullable=False, default=0)
    version: Any = Column(Integer, nullable=False, default=1)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SwarmSnapshotModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing a periodic global swarm snapshot."""

    __tablename__ = "swarm_snapshots"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    running_agents: Any = Column(Integer, nullable=False)
    queued_tasks: Any = Column(Integer, nullable=False)
    completed_tasks: Any = Column(Integer, nullable=False)
    failed_tasks: Any = Column(Integer, nullable=False)
    message_rate: Any = Column(Float, nullable=False)
    cpu_usage: Any = Column(Float, nullable=False)
    memory_usage: Any = Column(Float, nullable=False)
    cluster_status: Any = Column(String(50), nullable=False)
    timestamp: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class SwarmMessageModel(Base):  # type: ignore[misc]
    """SQLAlchemy model logging inter-agent messages routing."""

    __tablename__ = "swarm_messages"

    id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    correlation_id: Any = Column(Uuid(as_uuid=True), nullable=False)
    sender: Any = Column(String(255), nullable=False)
    receiver: Any = Column(String(255), nullable=False)
    action: Any = Column(String(255), nullable=False)
    body: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    timestamp: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class AgentLoopJournalModel(Base):  # type: ignore[misc]
    """SQLAlchemy model persisting individual AgentLoop iteration records."""

    __tablename__ = "agent_loop_journals"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    session_id: Any = Column(Uuid(as_uuid=True), nullable=False)
    iteration: Any = Column(Integer, nullable=False)
    goal_description: Any = Column(String(4000), nullable=False)
    chosen_executor: Any = Column(String(50), nullable=False)
    reasoning: Any = Column(String(4000), nullable=False)
    output_summary: Any = Column(String(4000), nullable=False)
    reflection_category: Any = Column(String(100), nullable=True)
    next_action: Any = Column(String(50), nullable=False)
    timestamp: Any = Column(DateTime, nullable=False)
