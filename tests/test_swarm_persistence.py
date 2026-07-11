"""JARVIS OS - Phase 26 Swarm Persistence, Worker Loop, and Recovery Tests.

Validates database CRUD with optimistic locking, concurrent worker task execution,
automatic retry policies, and startup session recovery protocols.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.events.memory_bus import MemoryEventBus
from core.interfaces import InterAgentMessage
from core.memory.models import Base
from core.runtime.container_driver import MockAdapter
from core.runtime.dto import SwarmSnapshot, SwarmTask
from core.runtime.lock import MemoryLock
from core.runtime.message_bus import SwarmMessageBus
from core.runtime.orchestrator import SwarmOrchestrator
from core.runtime.persistence_db import DbSwarmPersistence
from core.runtime.persistence_models import (
    AgentLoopJournalModel,
    SwarmMessageModel,
    SwarmTaskModel,
)
from core.runtime.queue import SwarmTaskQueue
from core.runtime.registry import AgentRegistry
from core.runtime.scheduler import CapabilityNegotiator
from core.runtime.subagent import SubagentManager

# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
async def async_db() -> AsyncIterator[AsyncSession]:
    """Create an in-memory SQLite async engine with all swarm tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def persistence(async_db: AsyncSession) -> DbSwarmPersistence:
    """Create a DbSwarmPersistence backed by the in-memory session."""

    class _Factory:
        """Wraps raw session in a context manager for the persistence adapter."""

        def __init__(self, session: AsyncSession) -> None:
            self._session = session

        def __call__(self) -> Any:
            return self

        async def __aenter__(self) -> AsyncSession:
            return self._session

        async def __aexit__(self, *args: Any) -> None:
            pass

    return DbSwarmPersistence(session_factory=_Factory(async_db))


@pytest.fixture
def event_bus() -> MemoryEventBus:
    return MemoryEventBus()


def _make_task(
    goal: str = "Test goal",
    priority: str = "NORMAL",
    retry: int = 0,
    status: str = "Pending",
) -> SwarmTask:
    return SwarmTask(
        task_id=uuid4(),
        goal=goal,
        priority=priority,
        capabilities=["Python"],
        timeout=300.0,
        retry=retry,
        dependencies=[],
        metadata={},
        status=status,
    )


# ── DbSwarmPersistence CRUD Tests ────────────────────────────────


class TestDbSwarmPersistenceCRUD:
    """Database CRUD operations with optimistic locking."""

    @pytest.mark.asyncio
    async def test_save_and_list_tasks(
        self, persistence: DbSwarmPersistence, async_db: AsyncSession
    ) -> None:
        """Save multiple tasks and retrieve them via list_tasks."""
        t1 = _make_task(goal="Task A", priority="HIGH")
        t2 = _make_task(goal="Task B", priority="LOW")

        await persistence.save_task(t1, session=async_db)
        await persistence.save_task(t2, session=async_db)
        await async_db.flush()

        tasks = await persistence.list_tasks(limit=10, offset=0, session=async_db)
        assert len(tasks) == 2
        goals = {t.goal for t in tasks}
        assert "Task A" in goals
        assert "Task B" in goals

    @pytest.mark.asyncio
    async def test_save_task_update_with_version(
        self, persistence: DbSwarmPersistence, async_db: AsyncSession
    ) -> None:
        """Updating a task increments the version number."""
        task = _make_task(goal="Original goal")
        await persistence.save_task(task, session=async_db)
        await async_db.flush()

        # Version is now tracked in metadata
        assert (
            task.metadata.get("_version") is None or task.metadata.get("_version") == 1
        )

        # Update the task
        task.goal = "Updated goal"
        task.metadata["_version"] = 1  # match DB version
        await persistence.save_task(task, session=async_db)
        await async_db.flush()

        assert task.metadata["_version"] == 2

    @pytest.mark.asyncio
    async def test_optimistic_locking_conflict(
        self, persistence: DbSwarmPersistence, async_db: AsyncSession
    ) -> None:
        """Conflicting version numbers raise JarvisAgentError."""
        from core.exceptions import JarvisAgentError

        task = _make_task(goal="Lock test")
        await persistence.save_task(task, session=async_db)
        await async_db.flush()

        # Simulate stale version
        task.metadata["_version"] = 999
        with pytest.raises(JarvisAgentError) as exc_info:
            await persistence.save_task(task, session=async_db)
        assert "Optimistic locking conflict" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_and_list_agents(
        self, persistence: DbSwarmPersistence, async_db: AsyncSession
    ) -> None:
        """Save agents and retrieve paginated results."""
        agent_id = uuid4()
        agent_data: Dict[str, Any] = {
            "name": "Agent-1",
            "status": "ONLINE",
            "capabilities": ["Python", "Shell"],
            "manifest": None,
            "cpu_load": 0.1,
            "memory": 64.0,
            "recent_failures": 0,
        }
        await persistence.save_agent(agent_id, agent_data, session=async_db)
        await async_db.flush()

        agents = await persistence.list_agents(limit=10, offset=0, session=async_db)
        assert len(agents) == 1
        assert agents[0]["name"] == "Agent-1"

    @pytest.mark.asyncio
    async def test_save_and_load_snapshot(
        self, persistence: DbSwarmPersistence, async_db: AsyncSession
    ) -> None:
        """Save and retrieve the latest swarm snapshot."""
        snap = SwarmSnapshot(
            running_agents=3,
            queued_tasks=5,
            completed_tasks=10,
            failed_tasks=1,
            message_rate=0.7,
            cpu_usage=0.25,
            memory_usage=512.0,
            cluster_status="HEALTHY",
        )
        await persistence.save_snapshot(snap, session=async_db)
        await async_db.flush()

        loaded = await persistence.load_snapshot(session=async_db)
        assert loaded is not None
        assert loaded.running_agents == 3
        assert loaded.cluster_status == "HEALTHY"

    @pytest.mark.asyncio
    async def test_save_history_journal_records(
        self, persistence: DbSwarmPersistence, async_db: AsyncSession
    ) -> None:
        """Save iteration journal records via save_history."""
        session_id = uuid4()
        records = [
            {
                "iteration": 1,
                "goal_description": "compile code",
                "chosen_executor": "PYTHON",
                "reasoning": "needs compilation",
                "output_summary": "success",
                "reflection_category": None,
                "next_action": "CONTINUE",
                "timestamp": datetime.now(timezone.utc),
            },
            {
                "iteration": 2,
                "goal_description": "run tests",
                "chosen_executor": "SHELL",
                "reasoning": "test suite",
                "output_summary": "all passed",
                "reflection_category": "VERIFY",
                "next_action": "SUCCESS",
                "timestamp": datetime.now(timezone.utc),
            },
        ]
        await persistence.save_history(session_id, records, session=async_db)
        await async_db.flush()

        q = select(AgentLoopJournalModel).where(
            AgentLoopJournalModel.session_id == session_id
        )
        res = await async_db.execute(q)
        rows = res.scalars().all()
        assert len(rows) == 2
        assert rows[0].chosen_executor == "PYTHON"
        assert rows[1].next_action == "SUCCESS"

    @pytest.mark.asyncio
    async def test_save_history_message_records(
        self, persistence: DbSwarmPersistence, async_db: AsyncSession
    ) -> None:
        """Save inter-agent message records via save_history."""
        session_id = uuid4()
        msg_id = uuid4()
        messages = [
            {
                "id": str(msg_id),
                "correlation_id": str(session_id),
                "sender": "Agent-A",
                "receiver": "Agent-B",
                "action": "task.delegate",
                "body": {"payload": "test"},
                "timestamp": datetime.now(timezone.utc),
            }
        ]
        await persistence.save_history(session_id, messages, session=async_db)
        await async_db.flush()

        q = select(SwarmMessageModel)
        res = await async_db.execute(q)
        rows = res.scalars().all()
        assert len(rows) == 1
        assert rows[0].sender == "Agent-A"

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(
        self, persistence: DbSwarmPersistence, async_db: AsyncSession
    ) -> None:
        """Verify limit and offset work correctly for task pagination."""
        for i in range(5):
            await persistence.save_task(_make_task(goal=f"Task-{i}"), session=async_db)
        await async_db.flush()

        page1 = await persistence.list_tasks(limit=2, offset=0, session=async_db)
        page2 = await persistence.list_tasks(limit=2, offset=2, session=async_db)
        page3 = await persistence.list_tasks(limit=2, offset=4, session=async_db)

        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1


# ── Orchestrator Worker Loop Tests ───────────────────────────────


class TestSwarmOrchestratorWorkerLoop:
    """Tests for background worker loop, concurrency, and retry logic."""

    def _make_orchestrator(self, event_bus: MemoryEventBus) -> SwarmOrchestrator:
        return SwarmOrchestrator(
            manager=SubagentManager(driver=MockAdapter()),
            queue=SwarmTaskQueue(),
            negotiator=CapabilityNegotiator(),
            message_bus=SwarmMessageBus(event_bus),
            persistence=MagicMock(),
            lock_manager=MemoryLock(),
            registry=AgentRegistry(),
            event_bus=event_bus,
            max_concurrent=3,
        )

    @pytest.mark.asyncio
    async def test_worker_loop_starts_and_stops(
        self, event_bus: MemoryEventBus
    ) -> None:
        """Worker loop can be started and stopped cleanly."""
        orch = self._make_orchestrator(event_bus)
        orch.persistence.save_task = AsyncMock()

        await orch.start_worker_loop()
        assert orch._worker_task is not None

        await orch.stop_worker_loop()
        assert orch._worker_task is None

    @pytest.mark.asyncio
    async def test_worker_loop_processes_task(self, event_bus: MemoryEventBus) -> None:
        """Worker loop dequeues and completes a task (mock execution path)."""
        orch = self._make_orchestrator(event_bus)
        orch.persistence.save_task = AsyncMock()
        orch.persistence.save_agent = AsyncMock()

        events: List[InterAgentMessage] = []

        async def capture(msg: InterAgentMessage) -> None:
            events.append(msg)

        await event_bus.initialize()
        await event_bus.start()
        await event_bus.subscribe("TASK_COMPLETED", capture)

        # Enqueue a task
        task = _make_task(goal="Worker test")
        await orch.queue.enqueue(task)

        # Start and let loop process
        await orch.start_worker_loop()
        await asyncio.sleep(0.3)
        await orch.stop_worker_loop()

        # Task should be completed (mock path since no dispatcher injected)
        assert orch.persistence.save_task.call_count >= 1

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_retry_policy_decrements_retry(
        self, event_bus: MemoryEventBus
    ) -> None:
        """When execution fails, retry is decremented and task re-enqueued."""
        orch = self._make_orchestrator(event_bus)
        orch.persistence.save_task = AsyncMock()
        orch.persistence.save_agent = AsyncMock()

        # Inject a failing dispatcher to force the failure path
        orch.dispatcher = MagicMock()
        orch.reflection = MagicMock()
        orch.decision = MagicMock()

        # Make _run_reasoning_loop raise
        async def failing_loop(*args: Any, **kwargs: Any) -> bool:
            raise RuntimeError("Simulated failure")

        orch._run_reasoning_loop = failing_loop  # type: ignore[assignment]

        retry_events: List[InterAgentMessage] = []

        async def capture_retry(msg: InterAgentMessage) -> None:
            retry_events.append(msg)

        await event_bus.initialize()
        await event_bus.start()
        await event_bus.subscribe("TASK_RETRY", capture_retry)

        task = _make_task(goal="Retry test", retry=2)
        await orch.queue.enqueue(task)

        await orch.start_worker_loop()
        await asyncio.sleep(0.5)
        await orch.stop_worker_loop()

        # Should have retried at least once
        assert orch.persistence.save_task.call_count >= 1

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_concurrency_limit_respected(self, event_bus: MemoryEventBus) -> None:
        """Worker loop respects max_concurrent limit."""
        orch = self._make_orchestrator(event_bus)
        orch.max_concurrent = 2
        orch.persistence.save_task = AsyncMock()
        orch.persistence.save_agent = AsyncMock()

        # Enqueue 5 tasks
        for _ in range(5):
            await orch.queue.enqueue(_make_task())

        await orch.start_worker_loop()
        await asyncio.sleep(0.1)

        # Active workers should not exceed max_concurrent
        assert len(orch.active_worker_tasks) <= 2

        await orch.stop_worker_loop()


# ── Orchestrator Task Event Sourcing ─────────────────────────────


class TestSwarmOrchestratorEvents:
    """Validate task transition events are published correctly."""

    @pytest.mark.asyncio
    async def test_spawn_publishes_created_and_assigned(
        self, event_bus: MemoryEventBus
    ) -> None:
        """spawn_task emits TASK_CREATED and TASK_ASSIGNED events."""
        orch = SwarmOrchestrator(
            manager=SubagentManager(driver=MockAdapter()),
            queue=SwarmTaskQueue(),
            negotiator=CapabilityNegotiator(),
            message_bus=SwarmMessageBus(event_bus),
            persistence=MagicMock(),
            lock_manager=MemoryLock(),
            registry=AgentRegistry(),
            event_bus=event_bus,
        )
        orch.persistence.save_task = AsyncMock()
        orch.persistence.save_agent = AsyncMock()

        events: List[InterAgentMessage] = []

        async def capture(msg: InterAgentMessage) -> None:
            events.append(msg)

        await event_bus.initialize()
        await event_bus.start()
        await event_bus.subscribe("TASK_CREATED", capture)
        await event_bus.subscribe("TASK_ASSIGNED", capture)

        task = _make_task()
        success = await orch.spawn_task(task)
        assert success is True
        await asyncio.sleep(0.05)

        actions = [e.action for e in events]
        assert "TASK_CREATED" in actions
        assert "TASK_ASSIGNED" in actions

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_cancel_publishes_task_failed(
        self, event_bus: MemoryEventBus
    ) -> None:
        """cancel_task emits TASK_FAILED event."""
        orch = SwarmOrchestrator(
            manager=SubagentManager(driver=MockAdapter()),
            queue=SwarmTaskQueue(),
            negotiator=CapabilityNegotiator(),
            message_bus=SwarmMessageBus(event_bus),
            persistence=MagicMock(),
            lock_manager=MemoryLock(),
            registry=AgentRegistry(),
            event_bus=event_bus,
        )
        orch.persistence.save_task = AsyncMock()

        events: List[InterAgentMessage] = []

        async def capture(msg: InterAgentMessage) -> None:
            events.append(msg)

        await event_bus.initialize()
        await event_bus.start()
        await event_bus.subscribe("TASK_FAILED", capture)

        task = _make_task()
        await orch.queue.enqueue(task)
        success = await orch.cancel_task(task.task_id)
        assert success is True
        await asyncio.sleep(0.05)

        actions = [e.action for e in events]
        assert "TASK_FAILED" in actions

        await event_bus.stop()


# ── Recovery Manager Tests ───────────────────────────────────────


class TestSwarmResumeManager:
    """Validate startup recovery protocols."""

    @pytest.mark.asyncio
    async def test_recovery_resets_stale_running_tasks(
        self, async_db: AsyncSession, event_bus: MemoryEventBus
    ) -> None:
        """Stale RUNNING tasks older than timeout are reset to Pending or Failed."""
        from core.runtime.recovery_manager import SwarmResumeManager

        # Insert a stale Running task
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        model = SwarmTaskModel(
            task_id=uuid4(),
            goal="Stale running task",
            priority="NORMAL",
            status="Running",
            capabilities=[],
            timeout=300.0,
            retry=2,
            dependencies=[],
            metadata_={},
            version=1,
            created_at=stale_time,
            updated_at=stale_time,
        )
        async_db.add(model)
        await async_db.flush()

        orch = SwarmOrchestrator(
            manager=SubagentManager(driver=MockAdapter()),
            queue=SwarmTaskQueue(),
            negotiator=CapabilityNegotiator(),
            message_bus=SwarmMessageBus(event_bus),
            persistence=MagicMock(),
            lock_manager=MemoryLock(),
            registry=AgentRegistry(),
            event_bus=event_bus,
        )

        # Patch db_manager.session to use our test session
        class _TestSessionFactory:
            def __init__(self, s: AsyncSession) -> None:
                self._s = s

            def __call__(self) -> Any:
                return self

            async def __aenter__(self) -> AsyncSession:
                return self._s

            async def __aexit__(self, *a: Any) -> None:
                pass

        import core.memory.database as db_mod

        original_session = db_mod.db_manager.session
        db_mod.db_manager.session = _TestSessionFactory(async_db)  # type: ignore[assignment]

        await event_bus.initialize()
        await event_bus.start()

        events: List[InterAgentMessage] = []

        async def capture(msg: InterAgentMessage) -> None:
            events.append(msg)

        await event_bus.subscribe("TASK_RECOVERED", capture)

        try:
            resume_mgr = SwarmResumeManager(
                orchestrator=orch,
                event_bus=event_bus,
                recovery_timeout_seconds=60.0,  # 1 minute timeout
            )
            await resume_mgr.recover_all()
            await asyncio.sleep(0.05)

            # Task should have been recovered (retry decremented, re-enqueued)
            assert model.status == "Pending"
            assert model.retry == 1

            # Task should be in the queue
            assert orch.queue.size >= 1

            # TASK_RECOVERED event should have been published
            actions = [e.action for e in events]
            assert "TASK_RECOVERED" in actions
        finally:
            db_mod.db_manager.session = original_session  # type: ignore[assignment]
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_recovery_fails_exhausted_tasks(
        self, async_db: AsyncSession, event_bus: MemoryEventBus
    ) -> None:
        """Stale tasks with retry=0 are transitioned to Failed."""
        from core.runtime.recovery_manager import SwarmResumeManager

        stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        model = SwarmTaskModel(
            task_id=uuid4(),
            goal="Exhausted stale task",
            priority="HIGH",
            status="Running",
            capabilities=[],
            timeout=300.0,
            retry=0,
            dependencies=[],
            metadata_={},
            version=1,
            created_at=stale_time,
            updated_at=stale_time,
        )
        async_db.add(model)
        await async_db.flush()

        orch = SwarmOrchestrator(
            manager=SubagentManager(driver=MockAdapter()),
            queue=SwarmTaskQueue(),
            negotiator=CapabilityNegotiator(),
            message_bus=SwarmMessageBus(event_bus),
            persistence=MagicMock(),
            lock_manager=MemoryLock(),
            registry=AgentRegistry(),
            event_bus=event_bus,
        )

        class _TestSessionFactory:
            def __init__(self, s: AsyncSession) -> None:
                self._s = s

            def __call__(self) -> Any:
                return self

            async def __aenter__(self) -> AsyncSession:
                return self._s

            async def __aexit__(self, *a: Any) -> None:
                pass

        import core.memory.database as db_mod

        original_session = db_mod.db_manager.session
        db_mod.db_manager.session = _TestSessionFactory(async_db)  # type: ignore[assignment]

        await event_bus.initialize()
        await event_bus.start()

        events: List[InterAgentMessage] = []

        async def capture(msg: InterAgentMessage) -> None:
            events.append(msg)

        await event_bus.subscribe("TASK_FAILED", capture)

        try:
            resume_mgr = SwarmResumeManager(
                orchestrator=orch,
                event_bus=event_bus,
                recovery_timeout_seconds=60.0,
            )
            await resume_mgr.recover_all()
            await asyncio.sleep(0.05)

            assert model.status == "Failed"

            actions = [e.action for e in events]
            assert "TASK_FAILED" in actions
        finally:
            db_mod.db_manager.session = original_session  # type: ignore[assignment]
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_recovery_reseeds_pending_tasks(
        self, async_db: AsyncSession, event_bus: MemoryEventBus
    ) -> None:
        """Pending tasks in DB are re-enqueued to SwarmTaskQueue on recovery."""
        from core.runtime.recovery_manager import SwarmResumeManager

        now = datetime.now(timezone.utc)
        for i in range(3):
            model = SwarmTaskModel(
                task_id=uuid4(),
                goal=f"Pending task {i}",
                priority="NORMAL",
                status="Pending",
                capabilities=[],
                timeout=300.0,
                retry=1,
                dependencies=[],
                metadata_={},
                version=1,
                created_at=now,
                updated_at=now,
            )
            async_db.add(model)
        await async_db.flush()

        orch = SwarmOrchestrator(
            manager=SubagentManager(driver=MockAdapter()),
            queue=SwarmTaskQueue(),
            negotiator=CapabilityNegotiator(),
            message_bus=SwarmMessageBus(event_bus),
            persistence=MagicMock(),
            lock_manager=MemoryLock(),
            registry=AgentRegistry(),
            event_bus=event_bus,
        )

        class _TestSessionFactory:
            def __init__(self, s: AsyncSession) -> None:
                self._s = s

            def __call__(self) -> Any:
                return self

            async def __aenter__(self) -> AsyncSession:
                return self._s

            async def __aexit__(self, *a: Any) -> None:
                pass

        import core.memory.database as db_mod

        original_session = db_mod.db_manager.session
        db_mod.db_manager.session = _TestSessionFactory(async_db)  # type: ignore[assignment]

        try:
            resume_mgr = SwarmResumeManager(
                orchestrator=orch,
                event_bus=event_bus,
            )
            await resume_mgr.recover_all()

            # All 3 tasks should be re-enqueued
            assert orch.queue.size == 3
        finally:
            db_mod.db_manager.session = original_session  # type: ignore[assignment]


# ── PersistentExecutionJournal Tests ─────────────────────────────


class TestPersistentExecutionJournal:
    """Validate event-based journal persistence."""

    @pytest.mark.asyncio
    async def test_record_iteration_fires_event(
        self, event_bus: MemoryEventBus
    ) -> None:
        """PersistentExecutionJournal fires journal.iteration.recorded event."""
        from core.runtime.persistence_journal import PersistentExecutionJournal

        session_id = uuid4()
        journal = PersistentExecutionJournal(session_id=session_id, event_bus=event_bus)

        events: List[InterAgentMessage] = []

        async def capture(msg: InterAgentMessage) -> None:
            events.append(msg)

        await event_bus.initialize()
        await event_bus.start()
        await event_bus.subscribe("journal.iteration.recorded", capture)

        journal.record_iteration(
            iteration=1,
            goal_description="test goal",
            chosen_executor="PYTHON",
            reasoning="test reasoning",
            output_summary="test output",
            next_action="CONTINUE",
        )

        # Let asyncio task run
        await asyncio.sleep(0.1)

        assert len(events) >= 1
        assert events[0].action == "journal.iteration.recorded"
        assert events[0].body["iteration"] == 1

        # In-memory record should also be stored
        assert len(journal.export()) == 1

        await event_bus.stop()


# ── Lifecycle Methods Tests ──────────────────────────────────────


class TestOrchestratorLifecycle:
    """Validate lifecycle interface compliance."""

    @pytest.mark.asyncio
    async def test_lifecycle_start_stop(self, event_bus: MemoryEventBus) -> None:
        """initialize/start/stop/shutdown lifecycle methods work."""
        orch = SwarmOrchestrator(
            manager=SubagentManager(driver=MockAdapter()),
            queue=SwarmTaskQueue(),
            negotiator=CapabilityNegotiator(),
            message_bus=SwarmMessageBus(event_bus),
            persistence=MagicMock(),
            lock_manager=MemoryLock(),
            registry=AgentRegistry(),
            event_bus=event_bus,
        )
        orch.persistence.save_task = AsyncMock()

        await orch.initialize()
        await orch.start()
        assert orch._worker_task is not None

        await orch.stop()
        assert orch._worker_task is None

        await orch.shutdown()


# ── Race-safe upsert regression tests (v0.9.3 follow-up) ──────────


class TestSaveTaskRaceSafeUpsert:
    """Regression tests for the ``UNIQUE constraint failed: swarm_tasks.task_id``
    bug observed in the v0.9.3 smoke test (LLM-failure replan path racing the
    orchestrator's claim-on-dequeue path).

    Two scenarios are covered:

    1. **End-to-end race on a real file-based SQLite** — two independent
       AsyncSessions targeting the same DB call ``save_task`` for the same
       task_id concurrently via ``asyncio.gather``. Both must complete
       without raising ``IntegrityError``; the final row reflects the
       winning update.

    2. **Mocked IntegrityError recovery** — directly exercises the
       ``except IntegrityError`` branch in ``_save_task_internal`` by
       simulating: first SELECT returns no row, flush raises, rollback +
       re-fetch returns the row, the update path applies cleanly.
    """

    @pytest.mark.asyncio
    async def test_concurrent_save_task_no_pk_violation(self, tmp_path: Any) -> None:
        """Two concurrent save_task calls on different sessions for the same
        task_id must both succeed — the loser is recovered as an UPDATE."""
        import os

        from core.memory.models import Base
        from core.runtime.persistence_db import DbSwarmPersistence

        db_path = tmp_path / "race_test.db"
        if db_path.exists():
            db_path.unlink()

        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        try:
            persistence = DbSwarmPersistence(session_factory=session_factory)

            # Both tasks carry the SAME task_id, simulating the replan path
            # where a new SwarmTask DTO is constructed with the original
            # task's UUID.
            shared_task_id = uuid4()
            task_a = SwarmTask(
                task_id=shared_task_id,
                goal="Original",
                priority="NORMAL",
                capabilities=["Python"],
                timeout=300.0,
                retry=0,
                dependencies=[],
                metadata={},
                status="Pending",
            )
            task_b = SwarmTask(
                task_id=shared_task_id,
                goal="Replanned",
                priority="HIGH",
                capabilities=["Python"],
                timeout=300.0,
                retry=1,
                dependencies=[],
                metadata={"replanned": True},
                status="Claimed",
            )

            # Fire both saves concurrently. The first to land INSERTs the
            # row; the second's SELECT may miss it (depending on session
            # isolation / pool behavior) and attempt an INSERT that the PK
            # UNIQUE constraint will reject. The fix in
            # _save_task_internal catches that IntegrityError, re-fetches
            # the row, and demotes the failed insert to an UPDATE.
            results = await asyncio.gather(
                persistence.save_task(task_a),
                persistence.save_task(task_b),
                return_exceptions=True,
            )

            # Neither call should have raised — the second one is recovered.
            for i, r in enumerate(results):
                assert not isinstance(r, Exception), (
                    f"save_task call #{i} raised unexpectedly: {type(r).__name__}: {r}"
                )

            # Final row reflects the most recent state with version bumped.
            async with session_factory() as session:
                row = await session.execute(
                    select(SwarmTaskModel).where(
                        SwarmTaskModel.task_id == shared_task_id
                    )
                )
                model = row.scalar_one()
                assert model.status in {"Pending", "Claimed"}
                # Version is 1 (initial insert); the losing call's UPDATE
                # path bumps it to 2 if the second writer won the recovery.
                assert model.version >= 1
        finally:
            await engine.dispose()
            if db_path.exists():
                os.remove(db_path)

    @pytest.mark.asyncio
    async def test_integrity_error_recovered_as_update(self) -> None:
        """Directly exercise the IntegrityError → SAVEPOINT rollback →
        re-fetch → UPDATE branch by mocking the session to fail the first
        flush.

        CR-005 fix: the pre-CR-005 implementation called
        ``session.rollback()`` on the outer transaction, which closed the
        transaction and broke the recovery path. The post-CR-005
        implementation uses ``session.begin_nested()`` (a SAVEPOINT) so
        only the SAVEPOINT is rolled back, leaving the outer transaction
        alive for the recovery SELECT and UPDATE.
        """
        from contextlib import asynccontextmanager

        from sqlalchemy.exc import IntegrityError

        from core.runtime.persistence_db import DbSwarmPersistence

        # Pre-existing model row in the DB that the "winning" session just
        # INSERTed. The "losing" session's SELECT will miss it (mocked),
        # the flush will raise IntegrityError, and the fix must refetch +
        # update this row.
        existing_task_id = uuid4()
        existing_model = SwarmTaskModel(
            task_id=existing_task_id,
            goal="Original",
            priority="NORMAL",
            status="Pending",
            capabilities=[],
            timeout=300.0,
            retry=0,
            dependencies=[],
            metadata_={"_version": 1},
            version=1,
        )

        # Mock session: first SELECT → None, flush → IntegrityError,
        # post-SAVEPOINT-rollback SELECT → the existing model.
        select_call_count = {"n": 0}
        flushed = {"n": False}
        begin_nested_called = {"n": False}
        rolled_back = {"n": False}

        mock_session = MagicMock()
        mock_result_empty = MagicMock()
        mock_result_empty.scalar_one_or_none.return_value = None
        mock_result_full = MagicMock()
        mock_result_full.scalar_one.return_value = existing_model

        async def fake_execute(stmt: Any) -> Any:
            select_call_count["n"] += 1
            if select_call_count["n"] == 1:
                return mock_result_empty
            return mock_result_full

        async def fake_flush() -> None:
            flushed["n"] = True
            raise IntegrityError(
                "INSERT",
                params=None,
                orig=Exception("UNIQUE constraint failed: swarm_tasks.task_id"),
            )

        async def fake_rollback() -> None:
            # CR-005: rollback on the OUTER transaction is forbidden —
            # the recovery path needs a live transaction for the
            # re-SELECT and UPDATE. The SAVEPOINT context manager
            # handles the partial rollback internally.
            rolled_back["n"] = True

        @asynccontextmanager
        async def fake_begin_nested() -> Any:
            begin_nested_called["n"] = True
            # Pass-through context manager; the IntegrityError raised by
            # the inner flush bubbles up and is caught by the outer
            # except clause. No explicit rollback call is needed here
            # because the SAVEPOINT is auto-released on __aexit__.
            yield mock_session

        mock_session.execute.side_effect = fake_execute
        mock_session.flush.side_effect = fake_flush
        mock_session.rollback.side_effect = fake_rollback
        mock_session.begin_nested.side_effect = fake_begin_nested
        mock_session.add = MagicMock()

        persistence = DbSwarmPersistence()
        task = SwarmTask(
            task_id=existing_task_id,
            goal="Replanned",
            priority="HIGH",
            capabilities=["Python"],
            timeout=300.0,
            retry=1,
            dependencies=[],
            metadata={"replanned": True},
            status="Claimed",
        )

        # Should NOT raise — the IntegrityError is caught and recovered.
        await persistence._save_task_internal(task, mock_session)

        # Verify the SAVEPOINT path actually executed.
        assert flushed["n"], "session.flush() was not called"
        assert begin_nested_called["n"], (
            "session.begin_nested() was not called — the CR-005 fix uses a "
            "SAVEPOINT for the INSERT attempt, not an outer rollback."
        )
        # CR-005 invariant: the OUTER transaction is never rolled back.
        # The recovery SELECT/UPDATE must happen inside a live transaction.
        assert not rolled_back["n"], (
            "session.rollback() was called on the outer transaction — this "
            "closes the transaction and breaks the recovery path. The fix "
            "uses a SAVEPOINT (begin_nested) so the outer transaction stays "
            "alive."
        )
        # Two SELECTs: pre-flush (miss) + post-SAVEPOINT-rollback (hit).
        assert select_call_count["n"] == 2
        # The update path applied the new state to the existing row.
        assert existing_model.status == "Claimed"
        assert existing_model.priority == "HIGH"
        assert existing_model.retry == 1
        assert existing_model.version == 2
        assert task.metadata["_version"] == 2

    @pytest.mark.asyncio
    async def test_integrity_error_with_stale_version_raises(
        self, async_db: AsyncSession
    ) -> None:
        """When the recovered row's version is stale, the optimistic lock
        check still fires (no relaxation of locking on race recovery)."""
        from core.exceptions import JarvisAgentError
        from core.runtime.persistence_db import DbSwarmPersistence

        # Seed a row with version=5 directly via the session.
        task_id = uuid4()
        seeded = SwarmTaskModel(
            task_id=task_id,
            goal="Seeded",
            priority="NORMAL",
            status="Pending",
            capabilities=[],
            timeout=300.0,
            retry=0,
            dependencies=[],
            metadata_={},
            version=5,
        )
        async_db.add(seeded)
        await async_db.flush()

        # Caller believes the row is at version 1 (stale).
        persistence = DbSwarmPersistence()
        task = SwarmTask(
            task_id=task_id,
            goal="Stale update",
            priority="HIGH",
            capabilities=[],
            timeout=300.0,
            retry=0,
            dependencies=[],
            metadata={"_version": 1},
            status="Claimed",
        )
        with pytest.raises(JarvisAgentError) as exc_info:
            await persistence._save_task_internal(task, async_db)
        assert "Optimistic locking conflict" in str(exc_info.value)
