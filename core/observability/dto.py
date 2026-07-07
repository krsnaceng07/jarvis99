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

Pydantic DTOs for the Observability, Cost Governance & Live Streaming layer.

Architect constraints incorporated:
- C1: Full trace ID propagation (trace_id, session_id, task_id, agent_id, span_id, parent_span_id)
- C3: TelemetryEnvelope includes schema_version
- C7: BudgetSummary tracks daily AND monthly totals
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SpanStatus(str, Enum):
    """Lifecycle status of an execution trace span."""

    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CostDecision(str, Enum):
    """Budget tier decision returned by CostGovernor after each token usage event.

    Architect constraint C2: CostGovernor must never block EventBus.
    This enum is returned asynchronously and callers log-and-continue on BLOCK/FAILOVER.
    """

    ALLOW = "ALLOW"  # Under 80% daily threshold — proceed normally
    WARN = "WARN"  # 80–100% daily threshold — alert raised, proceed
    BLOCK = "BLOCK"  # Single call cost > $0.50 — log for review, proceed
    FAILOVER = "FAILOVER"  # Daily budget exhausted — route to local model


class ComponentStatus(str, Enum):
    """Health status of a monitored JARVIS component."""

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


# ---------------------------------------------------------------------------
# Trace / Span DTOs
# ---------------------------------------------------------------------------


class SpanSummary(BaseModel):
    """Lightweight span summary included in TelemetryEnvelope (non-sensitive)."""

    schema_version: str = "1.0"
    span_id: UUID
    trace_id: UUID
    component: str
    operation: str
    status: SpanStatus
    duration_ms: Optional[float] = None
    started_at: datetime


class TraceSpanRecord(BaseModel):
    """Full trace span record stored in SpanRepository.

    Architect constraint C1: Full trace ID propagation.
    """

    schema_version: str = "1.0"
    span_id: UUID
    trace_id: UUID
    parent_span_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    component: str = Field(..., max_length=100)
    operation: str = Field(..., max_length=255)
    status: SpanStatus = SpanStatus.STARTED
    duration_ms: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = Field(default=None, max_length=1000)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Budget / Cost DTOs
# ---------------------------------------------------------------------------


class BudgetSummary(BaseModel):
    """Current cost summary returned by CostGovernor.

    Architect constraint C7: tracks both daily AND monthly totals.
    """

    schema_version: str = "1.0"
    date: str  # YYYY-MM-DD
    month: str  # YYYY-MM
    daily_cost_usd: float  # Accumulated cost for today
    monthly_cost_usd: float  # Accumulated cost for the current month
    daily_limit_usd: float  # Configured daily max (default $10.00)
    warn_threshold_usd: float  # 80% of daily limit (default $8.00)
    tier: CostDecision  # Current budget tier
    call_count_daily: int  # LLM API calls today
    total_tokens_daily: int  # Combined input + output tokens today
    call_count_monthly: int  # LLM API calls this month
    total_tokens_monthly: int  # Combined tokens this month


# ---------------------------------------------------------------------------
# Health DTOs
# ---------------------------------------------------------------------------


class ComponentHealthRecord(BaseModel):
    """Health state for a single monitored component."""

    schema_version: str = "1.0"
    component_id: str
    status: ComponentStatus
    last_heartbeat: datetime
    metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Telemetry Envelope (WebSocket stream payload)
# ---------------------------------------------------------------------------


class TelemetryEnvelope(BaseModel):
    """Real-time telemetry snapshot broadcast to WebSocket subscribers every 2 seconds.

    Architect constraint C8: schema_version included for dashboard compatibility.
    """

    schema_version: str = "1.0"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Swarm runtime metrics
    active_agents: int = 0
    queued_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    # Cost metrics
    cost_today_usd: float = 0.0
    cost_month_usd: float = 0.0
    cost_tier: str = CostDecision.ALLOW.value

    # Health
    component_health: Dict[str, str] = Field(default_factory=dict)

    # Recent spans (last 10, non-sensitive)
    recent_spans: List[SpanSummary] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Retention configuration constant (Architect constraint C6)
# ---------------------------------------------------------------------------

#: Span records older than this many days are eligible for cleanup.
TRACE_RETENTION_DAYS: int = 30
