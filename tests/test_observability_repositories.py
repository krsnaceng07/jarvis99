"""JARVIS OS - Phase 27.A Observability Repository Tests.

Validates SpanRepository and BudgetRepository database CRUD, paginated queries,
daily+monthly cost aggregation, and retention-based cleanup.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.memory.models import Base
from core.observability.budget_repository import BudgetRepository
from core.observability.dto import (
    TRACE_RETENTION_DAYS,
    CostDecision,
    SpanStatus,
    TraceSpanRecord,
)
from core.observability.span_repository import SpanRepository

# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
async def async_db() -> AsyncIterator[AsyncSession]:
    """In-memory SQLite async engine with all observability tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


class _SessionFactory:
    """Wraps a raw AsyncSession in a context-manager-compatible factory."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> Any:
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *args: Any) -> None:
        pass


@pytest.fixture
def span_repo(async_db: AsyncSession) -> SpanRepository:
    return SpanRepository(session_factory=_SessionFactory(async_db))


@pytest.fixture
def budget_repo(async_db: AsyncSession) -> BudgetRepository:
    return BudgetRepository(session_factory=_SessionFactory(async_db))


def _make_span(
    component: str = "AgentLoop",
    operation: str = "task.start",
    status: SpanStatus = SpanStatus.STARTED,
    started_at: datetime | None = None,
) -> TraceSpanRecord:
    return TraceSpanRecord(
        span_id=uuid4(),
        trace_id=uuid4(),
        parent_span_id=None,
        session_id=uuid4(),
        task_id=uuid4(),
        agent_id=uuid4(),
        component=component,
        operation=operation,
        status=status,
        started_at=started_at or datetime.now(timezone.utc),
    )


# ── SpanRepository Tests ──────────────────────────────────────────


class TestSpanRepository:
    """CRUD, pagination, trace lookup, and retention cleanup for SpanRepository."""

    @pytest.mark.asyncio
    async def test_save_and_get_span(
        self, span_repo: SpanRepository, async_db: AsyncSession
    ) -> None:
        """Save a span and retrieve it by span_id."""
        span = _make_span()
        await span_repo.save(span, session=async_db)
        await async_db.flush()

        fetched = await span_repo.get(span.span_id)
        assert fetched is not None
        assert fetched.span_id == span.span_id
        assert fetched.component == "AgentLoop"
        assert fetched.status == SpanStatus.STARTED

    @pytest.mark.asyncio
    async def test_save_updates_existing_span(
        self, span_repo: SpanRepository, async_db: AsyncSession
    ) -> None:
        """Saving a span twice updates status and duration_ms."""
        span = _make_span(status=SpanStatus.STARTED)
        await span_repo.save(span, session=async_db)
        await async_db.flush()

        # Close the span
        span.status = SpanStatus.COMPLETED
        span.duration_ms = 123.4
        span.ended_at = datetime.now(timezone.utc)
        await span_repo.save(span, session=async_db)
        await async_db.flush()

        fetched = await span_repo.get(span.span_id)
        assert fetched is not None
        assert fetched.status == SpanStatus.COMPLETED
        assert fetched.duration_ms == pytest.approx(123.4)

    @pytest.mark.asyncio
    async def test_list_paginated_returns_newest_first(
        self, span_repo: SpanRepository, async_db: AsyncSession
    ) -> None:
        """list_paginated returns spans ordered by started_at descending."""
        base_time = datetime.now(timezone.utc)
        for i in range(5):
            s = _make_span(
                operation=f"op-{i}",
                started_at=base_time + timedelta(seconds=i),
            )
            await span_repo.save(s, session=async_db)
        await async_db.flush()

        page = await span_repo.list_paginated(limit=3, offset=0)
        assert len(page) == 3
        # Newest first
        assert page[0].operation == "op-4"

    @pytest.mark.asyncio
    async def test_list_by_trace_groups_spans(
        self, span_repo: SpanRepository, async_db: AsyncSession
    ) -> None:
        """list_by_trace returns only spans belonging to the given trace_id."""
        trace_id = uuid4()
        spans_in = [
            TraceSpanRecord(
                span_id=uuid4(),
                trace_id=trace_id,
                component="C",
                operation=f"op-{i}",
                status=SpanStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
            )
            for i in range(3)
        ]
        other = _make_span()  # different trace_id
        for s in spans_in:
            await span_repo.save(s, session=async_db)
        await span_repo.save(other, session=async_db)
        await async_db.flush()

        result = await span_repo.list_by_trace(trace_id)
        assert len(result) == 3
        assert all(r.trace_id == trace_id for r in result)

    @pytest.mark.asyncio
    async def test_retention_cleanup_deletes_old_spans(
        self, span_repo: SpanRepository, async_db: AsyncSession
    ) -> None:
        """delete_older_than removes spans older than retention_days."""
        old_time = datetime.now(timezone.utc) - timedelta(days=TRACE_RETENTION_DAYS + 1)
        old_span = _make_span(started_at=old_time)
        new_span = _make_span()

        await span_repo.save(old_span, session=async_db)
        await span_repo.save(new_span, session=async_db)
        await async_db.flush()

        deleted = await span_repo.delete_older_than(
            retention_days=TRACE_RETENTION_DAYS, session=async_db
        )
        assert deleted == 1

        remaining = await span_repo.list_paginated(limit=100)
        assert len(remaining) == 1
        assert remaining[0].span_id == new_span.span_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_span_returns_none(
        self, span_repo: SpanRepository
    ) -> None:
        """Fetching a non-existent span_id returns None."""
        result = await span_repo.get(uuid4())
        assert result is None


# ── BudgetRepository Tests ────────────────────────────────────────


class TestBudgetRepository:
    """Upsert accumulation, daily+monthly totals, and BudgetSummary tiers."""

    TODAY = "2026-07-04"
    MONTH = "2026-07"

    @pytest.mark.asyncio
    async def test_upsert_creates_new_row(
        self, budget_repo: BudgetRepository, async_db: AsyncSession
    ) -> None:
        """First upsert creates a ledger row with correct values."""
        await budget_repo.upsert_ledger(
            self.TODAY, "claude-3-5-sonnet", 1000, 200, 0.006, session=async_db
        )
        await async_db.flush()

        total = await budget_repo.get_daily_total(self.TODAY)
        assert total == pytest.approx(0.006, abs=1e-6)

    @pytest.mark.asyncio
    async def test_upsert_accumulates_existing_row(
        self, budget_repo: BudgetRepository, async_db: AsyncSession
    ) -> None:
        """Multiple upserts accumulate cost on the same date/model row."""
        for _ in range(3):
            await budget_repo.upsert_ledger(
                self.TODAY, "gpt-4o", 500, 100, 0.004, session=async_db
            )
        await async_db.flush()

        total = await budget_repo.get_daily_total(self.TODAY)
        assert total == pytest.approx(0.012, abs=1e-6)

    @pytest.mark.asyncio
    async def test_monthly_total_aggregates_across_days(
        self, budget_repo: BudgetRepository, async_db: AsyncSession
    ) -> None:
        """get_monthly_total sums cost across multiple days in the month."""
        days = ["2026-07-01", "2026-07-02", "2026-07-03"]
        for day in days:
            await budget_repo.upsert_ledger(
                day, "claude-3-5-sonnet", 100, 50, 1.0, session=async_db
            )
        await async_db.flush()

        monthly = await budget_repo.get_monthly_total(self.MONTH)
        assert monthly == pytest.approx(3.0, abs=1e-6)

    @pytest.mark.asyncio
    async def test_budget_summary_allow_tier(
        self, budget_repo: BudgetRepository, async_db: AsyncSession
    ) -> None:
        """BudgetSummary reports ALLOW tier when cost is below warn threshold."""
        await budget_repo.upsert_ledger(
            self.TODAY, "local", 0, 0, 0.0, session=async_db
        )
        await async_db.flush()

        summary = await budget_repo.get_summary(self.TODAY)
        assert summary.tier == CostDecision.ALLOW
        assert summary.date == self.TODAY
        assert summary.month == self.MONTH

    @pytest.mark.asyncio
    async def test_budget_summary_warn_tier(
        self, budget_repo: BudgetRepository, async_db: AsyncSession
    ) -> None:
        """BudgetSummary reports WARN tier when daily cost exceeds 80% threshold."""
        await budget_repo.upsert_ledger(
            self.TODAY, "claude-3-opus", 100000, 20000, 8.5, session=async_db
        )
        await async_db.flush()

        summary = await budget_repo.get_summary(self.TODAY)
        assert summary.tier == CostDecision.WARN
        assert summary.daily_cost_usd == pytest.approx(8.5)

    @pytest.mark.asyncio
    async def test_budget_summary_failover_tier(
        self, budget_repo: BudgetRepository, async_db: AsyncSession
    ) -> None:
        """BudgetSummary reports FAILOVER when daily cost exceeds daily limit."""
        await budget_repo.upsert_ledger(
            self.TODAY, "claude-3-opus", 200000, 50000, 12.0, session=async_db
        )
        await async_db.flush()

        summary = await budget_repo.get_summary(self.TODAY)
        assert summary.tier == CostDecision.FAILOVER

    @pytest.mark.asyncio
    async def test_budget_summary_includes_monthly_totals(
        self, budget_repo: BudgetRepository, async_db: AsyncSession
    ) -> None:
        """BudgetSummary populates both daily_ and monthly_ fields (Architect C7)."""
        # Add cost on a different day in same month
        await budget_repo.upsert_ledger(
            "2026-07-01", "gpt-4o", 1000, 200, 2.0, session=async_db
        )
        await budget_repo.upsert_ledger(
            self.TODAY, "gpt-4o", 500, 100, 1.0, session=async_db
        )
        await async_db.flush()

        summary = await budget_repo.get_summary(self.TODAY)
        assert summary.daily_cost_usd == pytest.approx(1.0)
        assert summary.monthly_cost_usd == pytest.approx(3.0)
        assert summary.call_count_daily == 1
        assert summary.call_count_monthly == 2

    @pytest.mark.asyncio
    async def test_empty_day_returns_zero_cost(
        self, budget_repo: BudgetRepository
    ) -> None:
        """get_daily_total returns 0.0 for a date with no records."""
        total = await budget_repo.get_daily_total("2026-01-01")
        assert total == 0.0
