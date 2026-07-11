"""
PHASE: 34, 45 (additive: WorkerRegistryModel, TaskRoutingLogModel)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/96_PHASE_34_AUTONOMOUS_AGENT_MISSION_SPECIFICATION.md
    Goal #6 — Persistent Autonomous Runtime (Phase 45 / M6.4.A — D-1/D-2/D-3)

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/d42af1e8-69f8-4bf2-a03f-dc029da887c0/implementation_plan.md
    Phase 45 — M6.4.A scaffold (lifted from wt/5a39ff05 @ 2405abf, adapted)

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
    UniqueConstraint,
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
    assigned_agents: Any = Column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
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


# ---------------------------------------------------------------------------
# Phase 45 M6.4.A — additive ORM columns (per ADR-45-01)
#
# These two tables are required by the Phase 45 transport layer
# (WorkerRegistry + DistributedRouter). They are PURELY ADDITIVE:
#   - No existing column is renamed, dropped, or retyped.
#   - No existing constraint is touched.
#   - Schema is portable: SQLite (tests) + PostgreSQL (prod) both work
#     via SQLAlchemy's ``JSON().with_variant(JSONB, "postgresql")`` and
#     ``DateTime(timezone=True)`` patterns.
#
# D-3 dedup index (``ix_task_routing_log_wave_run_id_chosen_worker_id``)
# is declared on the model so ``Base.metadata.create_all()`` (used by the
# test suite) creates the same unique index that production expects.
# ---------------------------------------------------------------------------


class WorkerRegistryModel(Base):  # type: ignore[misc]
    """SQLAlchemy model for ``worker_registry`` (M6.4.A, spec §4.4 D-1).

    D-1 liveness invariant: a worker whose ``last_heartbeat`` is > 15s
    stale is marked ``OFFLINE`` and its in-flight tasks re-routed
    (``WorkerRegistry.list_active`` performs the sweep + read in a
    single transaction).
    """

    __tablename__ = "worker_registry"

    worker_id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    hostname: Any = Column(String(255), nullable=False)
    pid: Any = Column(Integer, nullable=False)
    capabilities: Any = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    status: Any = Column(
        String(16), nullable=False, default="OFFLINE", server_default="OFFLINE"
    )
    active_tasks: Any = Column(Integer, nullable=False, default=0, server_default="0")
    last_heartbeat: Any = Column(DateTime(timezone=True), nullable=True)
    started_at: Any = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TaskRoutingLogModel(Base):  # type: ignore[misc]
    """SQLAlchemy model for ``task_routing_log`` (M6.4.A, spec §4.4 D-2/D-3).

    D-2 (append-only audit): every routing decision is recorded here.
    D-3 (dedup): the unique index on
    ``(wave_run_id, chosen_worker_id)`` enforces "exactly one row per
    pair" at the model layer so ``Base.metadata.create_all()`` creates
    the same index production expects.
    """

    __tablename__ = "task_routing_log"

    route_id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    wave_run_id: Any = Column(Uuid(as_uuid=True), nullable=False, index=True)
    chosen_worker_id: Any = Column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    decision_reason: Any = Column(String(255), nullable=False)
    routed_at: Any = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Any = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "wave_run_id",
            "chosen_worker_id",
            name="ix_task_routing_log_wave_run_id_chosen_worker_id",
        ),
    )
