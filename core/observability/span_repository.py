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

SpanRepository — CRUD adapter for execution trace spans (TraceSpanModel).

Architect constraint C6: Supports retention-based cleanup query by started_at.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import db_manager
from core.observability.dto import TRACE_RETENTION_DAYS, SpanStatus, TraceSpanRecord
from core.observability.models import TraceSpanModel

logger = logging.getLogger("jarvis.core.observability.span_repository")


class SpanRepository:
    """SQLAlchemy-backed persistence adapter for execution trace spans.

    Responsibility: CRUD + paginated queries + retention cleanup.
    No business logic — pure data persistence (per AGENTS.md §7.7).
    """

    def __init__(self, session_factory: Any = None) -> None:
        self._session_factory = session_factory or db_manager.session

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def save(
        self, span: TraceSpanRecord, session: Optional[AsyncSession] = None
    ) -> None:
        """Persist or update a trace span record."""
        if session is not None:
            await self._save_internal(span, session)
        else:
            async with self._session_factory() as sess:
                if not sess.in_transaction():
                    async with sess.begin():
                        await self._save_internal(span, sess)
                else:
                    await self._save_internal(span, sess)

    async def _save_internal(
        self, span: TraceSpanRecord, session: AsyncSession
    ) -> None:
        q = select(TraceSpanModel).where(TraceSpanModel.span_id == span.span_id)
        res = await session.execute(q)
        model = res.scalar_one_or_none()

        if not model:
            model = TraceSpanModel(
                span_id=span.span_id,
                trace_id=span.trace_id,
                parent_span_id=span.parent_span_id,
                session_id=span.session_id,
                task_id=span.task_id,
                agent_id=span.agent_id,
                component=span.component,
                operation=span.operation,
                status=span.status.value,
                duration_ms=span.duration_ms,
                metadata_=span.metadata,
                error=span.error,
                started_at=span.started_at,
                ended_at=span.ended_at,
            )
            session.add(model)
        else:
            model.status = span.status.value
            model.duration_ms = span.duration_ms
            model.error = span.error
            model.ended_at = span.ended_at
            if span.metadata:
                model.metadata_ = span.metadata

        logger.debug("Saved span %s status=%s", span.span_id, span.status.value)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get(
        self, span_id: UUID, session: Optional[AsyncSession] = None
    ) -> Optional[TraceSpanRecord]:
        """Fetch a single span by span_id."""
        async with self._session_factory() as sess:
            q = select(TraceSpanModel).where(TraceSpanModel.span_id == span_id)
            res = await sess.execute(q)
            model = res.scalar_one_or_none()
            return self._to_dto(model) if model else None

    async def list_paginated(
        self,
        limit: int = 20,
        offset: int = 0,
        session: Optional[AsyncSession] = None,
    ) -> List[TraceSpanRecord]:
        """Return paginated list of spans ordered by started_at descending."""
        async with self._session_factory() as sess:
            q = (
                select(TraceSpanModel)
                .order_by(TraceSpanModel.started_at.desc())
                .limit(limit)
                .offset(offset)
            )
            res = await sess.execute(q)
            return [self._to_dto(m) for m in res.scalars().all()]

    async def list_by_trace(
        self, trace_id: UUID, session: Optional[AsyncSession] = None
    ) -> List[TraceSpanRecord]:
        """Return all spans belonging to a trace_id."""
        async with self._session_factory() as sess:
            q = (
                select(TraceSpanModel)
                .where(TraceSpanModel.trace_id == trace_id)
                .order_by(TraceSpanModel.started_at.asc())
            )
            res = await sess.execute(q)
            return [self._to_dto(m) for m in res.scalars().all()]

    # ------------------------------------------------------------------
    # Retention cleanup (Architect constraint C6)
    # ------------------------------------------------------------------

    async def delete_older_than(
        self,
        retention_days: int = TRACE_RETENTION_DAYS,
        session: Optional[AsyncSession] = None,
    ) -> int:
        """Delete span records older than retention_days. Returns rows deleted."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        if session is not None:
            return await self._delete_older_internal(cutoff, session)
        async with self._session_factory() as sess:
            if not sess.in_transaction():
                async with sess.begin():
                    return await self._delete_older_internal(cutoff, sess)
            else:
                return await self._delete_older_internal(cutoff, sess)

    async def _delete_older_internal(
        self, cutoff: datetime, session: AsyncSession
    ) -> int:
        stmt = delete(TraceSpanModel).where(TraceSpanModel.started_at < cutoff)
        result = await session.execute(stmt)
        deleted = getattr(result, "rowcount", 0) or 0
        logger.info(
            "Retention cleanup: deleted %d span records older than %s", deleted, cutoff
        )
        return deleted

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dto(model: TraceSpanModel) -> TraceSpanRecord:
        return TraceSpanRecord(
            span_id=model.span_id,
            trace_id=model.trace_id,
            parent_span_id=model.parent_span_id,
            session_id=model.session_id,
            task_id=model.task_id,
            agent_id=model.agent_id,
            component=model.component,
            operation=model.operation,
            status=SpanStatus(model.status),
            duration_ms=model.duration_ms,
            metadata=model.metadata_,
            error=model.error,
            started_at=model.started_at,
            ended_at=model.ended_at,
        )
