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

ExecutionTracer — subscribes to task lifecycle events and records trace spans.

Architect constraints incorporated:
- C1: Full trace ID propagation (trace_id, session_id, task_id, agent_id, span_id, parent_span_id)
- C2: Never blocks the EventBus — all DB writes are fire-and-forget background tasks
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from core.observability.dto import SpanStatus, SpanSummary, TraceSpanRecord
from core.observability.span_repository import SpanRepository

logger = logging.getLogger("jarvis.core.observability.tracer")

# Maximum recent spans kept in memory for TelemetryEnvelope
_MAX_RECENT_SPANS: int = 10


class ExecutionTracer:
    """Records task/agent lifecycle trace spans to SpanRepository.

    All database writes are dispatched as fire-and-forget asyncio tasks to
    avoid blocking the EventBus or any caller (Architect constraint C2).

    Integrates via event-bus subscriptions in ObservabilityService —
    no frozen interface is modified.
    """

    def __init__(self, span_repository: SpanRepository) -> None:
        self._repo = span_repository
        # In-memory ring buffer of recent spans (non-persistent, for envelope)
        self._recent_spans: list[TraceSpanRecord] = []

    # ------------------------------------------------------------------
    # Public span API
    # ------------------------------------------------------------------

    async def start_span(
        self,
        component: str,
        operation: str,
        trace_id: Optional[UUID] = None,
        parent_span_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        task_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        span_id: Optional[UUID] = None,
    ) -> UUID:
        """Open a new trace span.

        Returns the span_id for later closure via end_span().
        Architect constraint C1: all context IDs are propagated into the record.
        """
        span = TraceSpanRecord(
            span_id=span_id or uuid4(),
            trace_id=trace_id or uuid4(),
            parent_span_id=parent_span_id,
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            component=component,
            operation=operation,
            status=SpanStatus.STARTED,
            metadata=metadata,
            started_at=datetime.now(timezone.utc),
        )
        self._add_recent(span)
        self._fire_and_forget_save(span)
        return span.span_id

    async def end_span(
        self,
        span_id: UUID,
        status: SpanStatus = SpanStatus.COMPLETED,
        error: Optional[str] = None,
    ) -> None:
        """Close an open span with a terminal status and persist the update.

        Architect constraint C2: DB write is fire-and-forget.
        """
        ended_at = datetime.now(timezone.utc)

        # Find the in-memory copy for duration calculation
        span = self._find_recent(span_id)
        if span is None:
            # Span not in memory (older span or recovered session) — create minimal update record
            span = TraceSpanRecord(
                span_id=span_id,
                trace_id=uuid4(),  # unknown — DB record already has correct value
                component="unknown",
                operation="unknown",
                status=status,
                error=error[:1000] if error else None,
                started_at=ended_at,  # duration will be None
                ended_at=ended_at,
            )
        else:
            duration_ms = (ended_at - span.started_at).total_seconds() * 1000
            span.status = status
            span.duration_ms = duration_ms
            span.error = error[:1000] if error else None
            span.ended_at = ended_at

        self._fire_and_forget_save(span)
        logger.debug(
            "Closed span %s → %s (%.1fms)", span_id, status.value, span.duration_ms or 0
        )

    # ------------------------------------------------------------------
    # Event bus handler (called by ObservabilityService subscriptions)
    # ------------------------------------------------------------------

    async def on_task_event(
        self, event_body: Dict[str, Any], operation: str, status: SpanStatus
    ) -> None:
        """Handle a task lifecycle event from the event bus.

        Architect constraint C1: Extracts all available trace IDs from the event body.
        Architect constraint C2: Does not block — fire-and-forget.
        """
        try:
            task_id_raw = event_body.get("task_id")
            session_id_raw = event_body.get("session_id")
            agent_id_raw = event_body.get("agent_id")
            trace_id_raw = event_body.get("trace_id")
            span_id_raw = event_body.get("span_id")

            task_id = UUID(str(task_id_raw)) if task_id_raw else None
            session_id = UUID(str(session_id_raw)) if session_id_raw else None
            agent_id = UUID(str(agent_id_raw)) if agent_id_raw else None
            trace_id = UUID(str(trace_id_raw)) if trace_id_raw else None
            span_id = UUID(str(span_id_raw)) if span_id_raw else None

            if span_id and status != SpanStatus.STARTED:
                # Closing an existing span
                await self.end_span(span_id, status=status)
            else:
                # Opening a new span
                await self.start_span(
                    component=event_body.get("component", "SwarmOrchestrator"),
                    operation=operation,
                    trace_id=trace_id,
                    session_id=session_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    span_id=span_id,
                )
        except Exception as exc:
            # Never let tracer crash propagate to the event bus
            logger.warning("ExecutionTracer.on_task_event error (ignored): %s", exc)

    # ------------------------------------------------------------------
    # Recent span buffer (for TelemetryEnvelope)
    # ------------------------------------------------------------------

    def get_recent_summaries(self) -> list[SpanSummary]:
        """Return the last N spans as lightweight summaries for the telemetry envelope."""
        return [
            SpanSummary(
                span_id=s.span_id,
                trace_id=s.trace_id,
                component=s.component,
                operation=s.operation,
                status=s.status,
                duration_ms=s.duration_ms,
                started_at=s.started_at,
            )
            for s in self._recent_spans[-_MAX_RECENT_SPANS:]
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_recent(self, span: TraceSpanRecord) -> None:
        self._recent_spans.append(span)
        if len(self._recent_spans) > _MAX_RECENT_SPANS * 2:
            # Trim to keep memory bounded
            self._recent_spans = self._recent_spans[-_MAX_RECENT_SPANS:]

    def _find_recent(self, span_id: UUID) -> Optional[TraceSpanRecord]:
        for s in reversed(self._recent_spans):
            if s.span_id == span_id:
                return s
        return None

    def _fire_and_forget_save(self, span: TraceSpanRecord) -> None:
        """Dispatch a fire-and-forget background task to persist the span.

        Architect constraint C2: Never blocks caller. Errors are logged-and-dropped.
        """

        async def _persist() -> None:
            try:
                await self._repo.save(span)
            except Exception as exc:
                logger.warning("Span persistence failed (non-fatal): %s", exc)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_persist())
        except RuntimeError:
            logger.warning(
                "No running event loop — span %s not persisted", span.span_id
            )
