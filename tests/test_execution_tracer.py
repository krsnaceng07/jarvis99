"""JARVIS OS - Phase 27.B ExecutionTracer Tests.

Validates start_span, end_span, fire-and-forget saving, recent span buffer,
and event bus subscriber helper.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.observability.dto import SpanStatus
from core.observability.tracer import ExecutionTracer


@pytest.fixture
def mock_span_repo() -> MagicMock:
    repo = MagicMock()
    repo.save = AsyncMock()
    return repo


@pytest.fixture
def tracer(mock_span_repo: MagicMock) -> ExecutionTracer:
    return ExecutionTracer(mock_span_repo)


class TestExecutionTracer:
    """ExecutionTracer verification suite (Architect constraint: non-blocking DB writes)."""

    @pytest.mark.asyncio
    async def test_start_span_creates_record(
        self, tracer: ExecutionTracer, mock_span_repo: MagicMock
    ) -> None:
        """start_span returns a UUID, adds to recent spans, and triggers async save."""
        trace_id = uuid4()
        session_id = uuid4()
        task_id = uuid4()

        span_id = await tracer.start_span(
            component="AgentLoop",
            operation="test.run",
            trace_id=trace_id,
            session_id=session_id,
            task_id=task_id,
        )

        assert span_id is not None
        # Allow async task to run
        await asyncio.sleep(0.05)

        mock_span_repo.save.assert_called_once()
        saved_record = mock_span_repo.save.call_args[0][0]
        assert saved_record.span_id == span_id
        assert saved_record.trace_id == trace_id
        assert saved_record.session_id == session_id
        assert saved_record.task_id == task_id
        assert saved_record.component == "AgentLoop"
        assert saved_record.operation == "test.run"
        assert saved_record.status == SpanStatus.STARTED

    @pytest.mark.asyncio
    async def test_end_span_closes_span(
        self, tracer: ExecutionTracer, mock_span_repo: MagicMock
    ) -> None:
        """end_span transitions status, computes duration_ms, and triggers async save."""
        span_id = await tracer.start_span(component="AgentLoop", operation="test.run")
        await asyncio.sleep(0.1)  # Simulate elapsed duration

        await tracer.end_span(span_id, status=SpanStatus.COMPLETED)
        await asyncio.sleep(0.05)

        # Called twice (start + end)
        assert mock_span_repo.save.call_count == 2
        last_record = mock_span_repo.save.call_args[0][0]
        assert last_record.span_id == span_id
        assert last_record.status == SpanStatus.COMPLETED
        assert last_record.duration_ms >= 100.0

    @pytest.mark.asyncio
    async def test_end_span_with_error(
        self, tracer: ExecutionTracer, mock_span_repo: MagicMock
    ) -> None:
        """end_span logs truncated error messages when status is FAILED."""
        span_id = await tracer.start_span(component="AgentLoop", operation="test.run")
        large_error = "Err" * 500

        await tracer.end_span(span_id, status=SpanStatus.FAILED, error=large_error)
        await asyncio.sleep(0.05)

        last_record = mock_span_repo.save.call_args[0][0]
        assert last_record.status == SpanStatus.FAILED
        assert len(last_record.error) == 1000
        assert last_record.error.startswith("Err")

    @pytest.mark.asyncio
    async def test_end_span_non_existent(
        self, tracer: ExecutionTracer, mock_span_repo: MagicMock
    ) -> None:
        """Ending a non-existent span performs a fire-and-forget save with no duration."""
        fake_id = uuid4()
        await tracer.end_span(fake_id, status=SpanStatus.COMPLETED)
        await asyncio.sleep(0.05)

        mock_span_repo.save.assert_called_once()
        record = mock_span_repo.save.call_args[0][0]
        assert record.span_id == fake_id
        assert record.status == SpanStatus.COMPLETED
        assert record.duration_ms is None

    @pytest.mark.asyncio
    async def test_recent_summaries_contains_buffer(
        self, tracer: ExecutionTracer
    ) -> None:
        """get_recent_summaries returns up to _MAX_RECENT_SPANS lightweight summaries."""
        for i in range(15):
            await tracer.start_span(component="AgentLoop", operation=f"run-{i}")

        summaries = tracer.get_recent_summaries()
        assert len(summaries) == 10
        assert summaries[-1].operation == "run-14"
        assert summaries[0].operation == "run-5"

    @pytest.mark.asyncio
    async def test_on_task_event_start(
        self, tracer: ExecutionTracer, mock_span_repo: MagicMock
    ) -> None:
        """on_task_event handles starting a span from event payload."""
        task_id = uuid4()
        event = {
            "task_id": str(task_id),
            "component": "SwarmOrchestrator",
            "operation": "execute_task",
        }
        await tracer.on_task_event(
            event, operation="execute_task", status=SpanStatus.STARTED
        )
        await asyncio.sleep(0.05)

        mock_span_repo.save.assert_called_once()
        record = mock_span_repo.save.call_args[0][0]
        assert record.task_id == task_id
        assert record.component == "SwarmOrchestrator"
        assert record.operation == "execute_task"
        assert record.status == SpanStatus.STARTED

    @pytest.mark.asyncio
    async def test_on_task_event_end(
        self, tracer: ExecutionTracer, mock_span_repo: MagicMock
    ) -> None:
        """on_task_event closes span if span_id is in event payload."""
        span_id = await tracer.start_span(
            component="SwarmOrchestrator", operation="execute_task"
        )
        await asyncio.sleep(0.05)

        event = {"span_id": str(span_id)}
        await tracer.on_task_event(
            event, operation="execute_task", status=SpanStatus.COMPLETED
        )
        await asyncio.sleep(0.05)

        assert mock_span_repo.save.call_count == 2
        record = mock_span_repo.save.call_args[0][0]
        assert record.span_id == span_id
        assert record.status == SpanStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_error_resilience_never_crashes_on_bad_event(
        self, tracer: ExecutionTracer
    ) -> None:
        """on_task_event swallows errors instead of raising (Architect C2)."""
        bad_event = {"task_id": "not-a-valid-uuid"}
        # Should not raise ValueError
        await tracer.on_task_event(
            bad_event, operation="run", status=SpanStatus.STARTED
        )
