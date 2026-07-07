"""
PHASE: 27
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/89_PHASE_27_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

SQLAlchemy declarative models for the Observability layer.

Architect constraints incorporated:
- C1: Full trace ID columns (trace_id, session_id, task_id, agent_id, span_id, parent_span_id)
- C6: TraceSpanModel has `started_at` enabling retention cleanup by TRACE_RETENTION_DAYS
- C7: BudgetLedgerModel has both date (daily) AND month (monthly) columns
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

from core.memory.models import Base


class TraceSpanModel(Base):  # type: ignore[misc]
    """SQLAlchemy model for execution trace spans.

    Architect constraint C1: full trace ID propagation columns.
    Architect constraint C6: started_at enables efficient retention-based cleanup.
    """

    __tablename__ = "trace_spans"

    span_id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    trace_id: Any = Column(Uuid(as_uuid=True), nullable=False, index=True)
    parent_span_id: Any = Column(Uuid(as_uuid=True), nullable=True)
    session_id: Any = Column(Uuid(as_uuid=True), nullable=True, index=True)
    task_id: Any = Column(Uuid(as_uuid=True), nullable=True, index=True)
    agent_id: Any = Column(Uuid(as_uuid=True), nullable=True)
    component: Any = Column(String(100), nullable=False)
    operation: Any = Column(String(255), nullable=False)
    status: Any = Column(String(50), nullable=False, default="STARTED")
    duration_ms: Any = Column(Float, nullable=True)
    metadata_: Any = Column(
        "metadata", JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    error: Any = Column(String(1000), nullable=True)
    started_at: Any = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    ended_at: Any = Column(DateTime, nullable=True)

    __table_args__ = (
        # Composite index for retention cleanup queries: DELETE WHERE started_at < cutoff
        Index("ix_trace_spans_started_at_status", "started_at", "status"),
    )


class BudgetLedgerModel(Base):  # type: ignore[misc]
    """SQLAlchemy model for the LLM API cost ledger.

    Architect constraint C7: tracks both daily (date) AND monthly (month) aggregates.
    Upserted per (date, month, model) to allow efficient daily and monthly queries.
    """

    __tablename__ = "budget_ledger"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    date: Any = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    month: Any = Column(String(7), nullable=False, index=True)  # YYYY-MM
    model: Any = Column(String(100), nullable=False)
    input_tokens: Any = Column(Integer, nullable=False, default=0)
    output_tokens: Any = Column(Integer, nullable=False, default=0)
    cost_usd: Any = Column(Float, nullable=False, default=0.0)
    call_count: Any = Column(Integer, nullable=False, default=0)
    updated_at: Any = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        # Composite index for upsert lookups by date+model and month+model
        Index("ix_budget_ledger_date_model", "date", "model", unique=True),
        Index("ix_budget_ledger_month_model", "month", "model"),
    )


class ComponentHealthModel(Base):  # type: ignore[misc]
    """SQLAlchemy model for component health state records."""

    __tablename__ = "component_health"

    component_id: Any = Column(String(100), primary_key=True)
    status: Any = Column(String(50), nullable=False, default="ONLINE")
    last_heartbeat: Any = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    metadata_: Any = Column(
        "metadata", JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
