"""JARVIS OS - Phase 27.E Observability Integration Tests.

Validates end-to-end event-driven integration of tracer, cost governor,
and health probe via MemoryEventBus subscriptions.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.broadcaster import TelemetryBroadcaster
from core.events.memory_bus import MemoryEventBus
from core.interfaces import InterAgentMessage
from core.memory.models import Base
from core.observability.budget_repository import BudgetRepository
from core.observability.cost_governor import CostGovernor
from core.observability.dto import SpanStatus
from core.observability.health_probe import HealthProbe
from core.observability.service import ObservabilityService
from core.observability.span_repository import SpanRepository


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
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> Any:
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *args: Any) -> None:
        pass


@pytest.fixture
def event_bus() -> MemoryEventBus:
    return MemoryEventBus()


@pytest.fixture
def service(async_db: AsyncSession, event_bus: MemoryEventBus) -> ObservabilityService:
    span_repo = SpanRepository(session_factory=_SessionFactory(async_db))
    budget_repo = BudgetRepository(session_factory=_SessionFactory(async_db))
    cost_gov = CostGovernor(budget_repository=budget_repo)
    health_probe = HealthProbe(heartbeat_timeout_seconds=0.5)
    broadcaster = TelemetryBroadcaster()

    return ObservabilityService(
        event_bus=event_bus,
        span_repo=span_repo,
        cost_gov=cost_gov,
        health_probe=health_probe,
        broadcaster=broadcaster,
    )


class TestObservabilityIntegration:
    """End-to-end integration tests verifying event subscriptions and persistence (Architect Q1 & C2)."""

    @pytest.mark.asyncio
    async def test_end_to_end_span_creation_on_event(
        self,
        service: ObservabilityService,
        event_bus: MemoryEventBus,
        async_db: AsyncSession,
    ) -> None:
        """Publishing swarm.task.started creates a database trace span record (Architect C2)."""
        await event_bus.initialize()
        await event_bus.start()
        await service.initialize()
        await service.start()

        span_id = uuid4()
        trace_id = uuid4()
        task_id = uuid4()

        body = {
            "span_id": str(span_id),
            "trace_id": str(trace_id),
            "task_id": str(task_id),
            "component": "SwarmOrchestrator",
            "operation": "execute_task",
        }
        msg = InterAgentMessage(
            sender="Test",
            receiver="Observability",
            action="started",
            body=body,
        )

        await event_bus.publish("swarm.task.started", msg)
        # Yield to allow async event handling and tracer background persistence task to complete
        await asyncio.sleep(0.1)

        # Verify in DB
        fetched = await service.span_repo.get(span_id)
        assert fetched is not None
        assert fetched.trace_id == trace_id
        assert fetched.task_id == task_id
        assert fetched.component == "SwarmOrchestrator"
        assert fetched.status == SpanStatus.STARTED

        # Now close it
        close_msg = InterAgentMessage(
            sender="Test",
            receiver="Observability",
            action="completed",
            body={"span_id": str(span_id)},
        )
        await event_bus.publish("swarm.task.completed", close_msg)
        await asyncio.sleep(0.1)

        fetched_closed = await service.span_repo.get(span_id)
        assert fetched_closed is not None
        assert fetched_closed.status == SpanStatus.COMPLETED

        await service.stop()
        await service.shutdown()
        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_end_to_end_cost_governor_on_event(
        self,
        service: ObservabilityService,
        event_bus: MemoryEventBus,
        async_db: AsyncSession,
    ) -> None:
        """Publishing llm.response updates CostGovernor ledger (Architect Q1)."""
        await event_bus.initialize()
        await event_bus.start()
        await service.initialize()
        await service.start()

        body = {
            "model": "claude-3-5-sonnet",
            "input_tokens": 1000,
            "output_tokens": 200,
        }
        msg = InterAgentMessage(
            sender="LLM",
            receiver="Observability",
            action="response",
            body=body,
        )

        await event_bus.publish("llm.response", msg)
        await asyncio.sleep(0.1)

        # Verify ledger accumulation
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        total = await service.cost_gov._repo.get_daily_total(today)
        # 1000 in ($0.003) + 200 out ($0.003) = $0.006 total
        assert total == pytest.approx(0.006)

        await service.stop()
        await service.shutdown()
        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_end_to_end_heartbeat_on_event(
        self, service: ObservabilityService, event_bus: MemoryEventBus
    ) -> None:
        """Publishing kernel.heartbeat registers component as ONLINE."""
        await event_bus.initialize()
        await event_bus.start()
        await service.initialize()
        await service.start()

        msg = InterAgentMessage(
            sender="AgentLoop",
            receiver="Observability",
            action="heartbeat",
            body={"component_id": "AgentLoop"},
        )
        await event_bus.publish("kernel.heartbeat", msg)
        await asyncio.sleep(0.1)

        statuses = await service.health_probe.get_health_status()
        assert statuses.get("AgentLoop") == "ONLINE"

        # Test offline timeout transition (0.5s timeout configured in fixture)
        await asyncio.sleep(0.5)
        statuses_after = await service.health_probe.get_health_status()
        assert statuses_after.get("AgentLoop") == "OFFLINE"

        await service.stop()
        await service.shutdown()
        await event_bus.stop()
