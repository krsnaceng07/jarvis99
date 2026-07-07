"""
PHASE: 44
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md

AUTHORITATIVE:
    NO

Tests: Mission & Autonomous Goal Scheduler (Phase 44)
Covers:
  - MissionTask / Mission DTOs
  - GoalDependencyResolver (topological sort, cycle detection)
  - PriorityEngine (effective priority ordering)
  - DeadlineManager (overdue / due-soon detection)
  - ExecutionBudgetManager (budget consumption, grace, exhaustion)
  - MissionQueue (enqueue, dequeue, remove, re-sort)
  - MissionRecovery (mission retry, task retry)
  - GoalScheduler (schedule, cancel, pause, resume, execute, query)
  - BackgroundGoalRunner (start, stop, running flag)
  - API route handlers
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task(
    name: str = "task",
    depends_on: Optional[list] = None,
    budget: float = 1.0,
    max_retries: int = 0,
) -> Any:
    from core.mission.mission_types import MissionTask

    return MissionTask(
        name=name,
        depends_on=depends_on or [],
        budget=budget,
        max_retries=max_retries,
    )


def _mission(
    priority: int = 5,
    total_budget: float = 100.0,
    max_retries: int = 0,
    tasks: Optional[list] = None,
    due_at: Optional[datetime] = None,
) -> Any:
    from core.mission.mission_types import Mission

    return Mission(
        name="Test Mission",
        priority=priority,
        tasks=tasks or [_task()],
        total_budget=total_budget,
        max_retries=max_retries,
        due_at=due_at,
    )


def _scheduler(executor: Optional[Any] = None) -> Any:
    from core.mission.mission_scheduler import GoalScheduler
    from core.mission.mission_types import SchedulerConfig

    return GoalScheduler(
        config=SchedulerConfig(max_concurrent_missions=5, poll_interval_seconds=0.1),
        event_bus=None,
        executor=executor,
    )


# ===========================================================================
# 1. MissionTask / Mission DTO tests
# ===========================================================================


class TestMissionDTOs:
    """Unit tests for domain DTOs."""

    def test_task_defaults(self) -> None:
        t = _task("work")
        assert t.name == "work"
        assert t.retries == 0
        assert t.max_retries == 0
        assert t.budget == 1.0

    def test_mission_defaults(self) -> None:
        m = _mission()
        assert m.name == "Test Mission"
        assert m.priority == 5
        assert m.used_budget == 0.0
        assert m.retry_count == 0

    def test_mission_remaining_budget(self) -> None:
        from core.mission.mission_types import Mission

        m = Mission(name="B", tasks=[_task()], total_budget=50.0)
        m.used_budget = 20.0
        assert m.remaining_budget == 30.0

    def test_mission_budget_exhausted(self) -> None:
        from core.mission.mission_types import Mission

        m = Mission(name="B", tasks=[_task()], total_budget=10.0)
        m.used_budget = 10.0
        assert m.is_budget_exhausted is True

    def test_mission_progress_empty(self) -> None:
        from core.mission.mission_types import Mission

        m = Mission(name="B", tasks=[])
        assert m.progress == 0.0

    def test_mission_progress_partial(self) -> None:
        from core.mission.mission_types import MissionStatus

        t1 = _task("a")
        t2 = _task("b")
        t1.status = MissionStatus.COMPLETED
        m = _mission(tasks=[t1, t2])
        assert m.progress == 50.0

    def test_mission_priority_validation(self) -> None:
        from pydantic import ValidationError

        from core.mission.mission_types import Mission

        with pytest.raises(ValidationError):
            Mission(name="B", tasks=[_task()], priority=11)

    def test_queue_item_effective_priority_no_deadline(self) -> None:
        from core.mission.mission_types import MissionQueueItem

        item = MissionQueueItem(mission_id=uuid4(), priority=7)
        assert item.effective_priority() == 7.0

    def test_queue_item_effective_priority_overdue(self) -> None:
        from core.mission.mission_types import MissionQueueItem

        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        item = MissionQueueItem(mission_id=uuid4(), priority=5, deadline=past)
        assert item.effective_priority() == 9999.0

    def test_queue_item_effective_priority_urgency_boost(self) -> None:
        from core.mission.mission_types import MissionQueueItem

        soon = datetime.now(timezone.utc) + timedelta(seconds=120)
        item = MissionQueueItem(mission_id=uuid4(), priority=5, deadline=soon)
        # Urgency bonus should push above base 5
        assert item.effective_priority() > 5.0


# ===========================================================================
# 2. GoalDependencyResolver tests
# ===========================================================================


class TestGoalDependencyResolver:
    """Tests for topological wave resolution."""

    def test_single_task_no_deps(self) -> None:
        from core.mission.mission_scheduler import GoalDependencyResolver

        t = _task("a")
        waves = GoalDependencyResolver().resolve([t])
        assert len(waves) == 1
        assert waves[0][0].name == "a"

    def test_linear_chain(self) -> None:
        from core.mission.mission_scheduler import GoalDependencyResolver

        t1 = _task("a")
        t2 = _task("b", depends_on=[t1.id])
        t3 = _task("c", depends_on=[t2.id])
        waves = GoalDependencyResolver().resolve([t1, t2, t3])
        assert len(waves) == 3
        assert waves[0][0].name == "a"
        assert waves[1][0].name == "b"
        assert waves[2][0].name == "c"

    def test_parallel_tasks(self) -> None:
        from core.mission.mission_scheduler import GoalDependencyResolver

        t1 = _task("a")
        t2 = _task("b")
        t3 = _task("c", depends_on=[t1.id, t2.id])
        waves = GoalDependencyResolver().resolve([t1, t2, t3])
        # Wave 0 contains both a and b (no deps), wave 1 has c
        assert len(waves) == 2
        assert len(waves[0]) == 2
        assert len(waves[1]) == 1
        assert waves[1][0].name == "c"

    def test_cycle_raises_value_error(self) -> None:
        from core.mission.mission_scheduler import GoalDependencyResolver
        from core.mission.mission_types import MissionTask

        t1 = MissionTask(name="a")
        t2 = MissionTask(name="b", depends_on=[t1.id])
        # Manually inject cycle
        t1.depends_on = [t2.id]

        with pytest.raises(ValueError, match="cycle"):
            GoalDependencyResolver().resolve([t1, t2])

    def test_unknown_dependency_skipped(self) -> None:
        from core.mission.mission_scheduler import GoalDependencyResolver

        t = _task("a", depends_on=[uuid4()])  # Unknown dep
        # Should not raise; unknown dep is logged and skipped
        waves = GoalDependencyResolver().resolve([t])
        assert len(waves) == 1


# ===========================================================================
# 3. PriorityEngine tests
# ===========================================================================


class TestPriorityEngine:
    def test_sort_by_priority_desc(self) -> None:
        from core.mission.mission_scheduler import PriorityEngine
        from core.mission.mission_types import MissionQueueItem

        low = MissionQueueItem(mission_id=uuid4(), priority=2)
        high = MissionQueueItem(mission_id=uuid4(), priority=9)
        med = MissionQueueItem(mission_id=uuid4(), priority=5)
        engine = PriorityEngine()
        sorted_items = engine.sort_queue([low, high, med])
        assert sorted_items[0].priority == 9
        assert sorted_items[2].priority == 2


# ===========================================================================
# 4. DeadlineManager tests
# ===========================================================================


class TestDeadlineManager:
    def test_get_overdue(self) -> None:
        from core.mission.mission_scheduler import DeadlineManager

        past = datetime.now(timezone.utc) - timedelta(hours=1)
        m = _mission(due_at=past)
        result = DeadlineManager().get_overdue([m])
        assert len(result) == 1
        assert result[0].id == m.id

    def test_no_overdue_when_no_deadline(self) -> None:
        from core.mission.mission_scheduler import DeadlineManager

        m = _mission()
        assert DeadlineManager().get_overdue([m]) == []

    def test_no_overdue_when_completed(self) -> None:
        from core.mission.mission_scheduler import DeadlineManager
        from core.mission.mission_types import MissionStatus

        past = datetime.now(timezone.utc) - timedelta(hours=1)
        m = _mission(due_at=past)
        m.status = MissionStatus.COMPLETED
        assert DeadlineManager().get_overdue([m]) == []

    def test_is_due_soon_within_window(self) -> None:
        from core.mission.mission_scheduler import DeadlineManager

        soon = datetime.now(timezone.utc) + timedelta(seconds=120)
        m = _mission(due_at=soon)
        assert DeadlineManager().is_due_soon(m, window_seconds=300) is True

    def test_not_due_soon_when_far(self) -> None:
        from core.mission.mission_scheduler import DeadlineManager

        far = datetime.now(timezone.utc) + timedelta(hours=10)
        m = _mission(due_at=far)
        assert DeadlineManager().is_due_soon(m, window_seconds=300) is False


# ===========================================================================
# 5. ExecutionBudgetManager tests
# ===========================================================================


class TestExecutionBudgetManager:
    def test_consume_within_budget(self) -> None:
        from core.mission.mission_scheduler import ExecutionBudgetManager

        mgr = ExecutionBudgetManager(overage_grace=1.05)
        m = _mission(total_budget=100.0)
        within = mgr.consume(m, 90.0)
        assert within is True
        assert m.used_budget == 90.0

    def test_consume_within_grace(self) -> None:
        from core.mission.mission_scheduler import ExecutionBudgetManager

        mgr = ExecutionBudgetManager(overage_grace=1.05)
        m = _mission(total_budget=100.0)
        # 104 < 105 (grace ceiling)
        result = mgr.consume(m, 104.0)
        assert result is True

    def test_consume_exceeds_grace(self) -> None:
        from core.mission.mission_scheduler import ExecutionBudgetManager

        mgr = ExecutionBudgetManager(overage_grace=1.05)
        m = _mission(total_budget=100.0)
        result = mgr.consume(m, 106.0)
        assert result is False

    def test_is_exhausted(self) -> None:
        from core.mission.mission_scheduler import ExecutionBudgetManager

        mgr = ExecutionBudgetManager(overage_grace=1.05)
        m = _mission(total_budget=10.0)
        m.used_budget = 11.0
        assert mgr.is_exhausted(m) is True

    def test_remaining(self) -> None:
        from core.mission.mission_scheduler import ExecutionBudgetManager

        mgr = ExecutionBudgetManager(overage_grace=1.0)
        m = _mission(total_budget=100.0)
        m.used_budget = 40.0
        assert mgr.remaining(m) == 60.0


# ===========================================================================
# 6. MissionQueue tests
# ===========================================================================


class TestMissionQueue:
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self) -> None:
        from core.mission.mission_scheduler import MissionQueue
        from core.mission.mission_types import MissionQueueItem

        q = MissionQueue()
        item = MissionQueueItem(mission_id=uuid4(), priority=5)
        await q.enqueue(item)
        assert await q.size() == 1
        dequeued = await q.dequeue()
        assert dequeued is item
        assert await q.size() == 0

    @pytest.mark.asyncio
    async def test_priority_ordering(self) -> None:
        from core.mission.mission_scheduler import MissionQueue
        from core.mission.mission_types import MissionQueueItem

        q = MissionQueue()
        low = MissionQueueItem(mission_id=uuid4(), priority=2)
        high = MissionQueueItem(mission_id=uuid4(), priority=9)
        await q.enqueue(low)
        await q.enqueue(high)
        first = await q.dequeue()
        assert first is not None and first.priority == 9

    @pytest.mark.asyncio
    async def test_remove_existing(self) -> None:
        from core.mission.mission_scheduler import MissionQueue
        from core.mission.mission_types import MissionQueueItem

        q = MissionQueue()
        item = MissionQueueItem(mission_id=uuid4(), priority=5)
        await q.enqueue(item)
        removed = await q.remove(item.mission_id)
        assert removed is True
        assert await q.size() == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self) -> None:
        from core.mission.mission_scheduler import MissionQueue

        q = MissionQueue()
        removed = await q.remove(uuid4())
        assert removed is False

    @pytest.mark.asyncio
    async def test_dequeue_empty_returns_none(self) -> None:
        from core.mission.mission_scheduler import MissionQueue

        q = MissionQueue()
        assert await q.dequeue() is None

    @pytest.mark.asyncio
    async def test_peek_does_not_remove(self) -> None:
        from core.mission.mission_scheduler import MissionQueue
        from core.mission.mission_types import MissionQueueItem

        q = MissionQueue()
        item = MissionQueueItem(mission_id=uuid4(), priority=5)
        await q.enqueue(item)
        peeked = await q.peek()
        assert peeked is item
        assert await q.size() == 1

    @pytest.mark.asyncio
    async def test_all_items(self) -> None:
        from core.mission.mission_scheduler import MissionQueue
        from core.mission.mission_types import MissionQueueItem

        q = MissionQueue()
        for _ in range(3):
            await q.enqueue(MissionQueueItem(mission_id=uuid4(), priority=1))
        items = await q.all_items()
        assert len(items) == 3


# ===========================================================================
# 7. MissionRecovery tests
# ===========================================================================


class TestMissionRecovery:
    def test_should_retry_failed_mission(self) -> None:
        from core.mission.mission_scheduler import MissionRecovery
        from core.mission.mission_types import MissionStatus

        m = _mission(max_retries=3)
        m.status = MissionStatus.FAILED
        m.retry_count = 1
        assert MissionRecovery().should_retry_mission(m) is True

    def test_no_retry_when_exhausted(self) -> None:
        from core.mission.mission_scheduler import MissionRecovery
        from core.mission.mission_types import MissionStatus

        m = _mission(max_retries=2)
        m.status = MissionStatus.FAILED
        m.retry_count = 2
        assert MissionRecovery().should_retry_mission(m) is False

    def test_prepare_retry_increments_count(self) -> None:
        from core.mission.mission_scheduler import MissionRecovery
        from core.mission.mission_types import MissionStatus

        m = _mission(max_retries=3)
        m.status = MissionStatus.FAILED
        m.retry_count = 1
        result = MissionRecovery().prepare_retry(m)
        assert result.retry_count == 2
        assert result.status == MissionStatus.RECOVERING

    def test_prepare_retry_resets_failed_tasks(self) -> None:
        from core.mission.mission_scheduler import MissionRecovery
        from core.mission.mission_types import MissionStatus

        t = _task("x")
        t.status = MissionStatus.FAILED
        m = _mission(tasks=[t], max_retries=3)
        m.status = MissionStatus.FAILED
        MissionRecovery().prepare_retry(m)
        assert m.tasks[0].status == MissionStatus.PENDING

    def test_should_retry_task(self) -> None:
        from core.mission.mission_scheduler import MissionRecovery

        t = _task(max_retries=3)
        t.retries = 2
        assert MissionRecovery().should_retry_task(t) is True

    def test_prepare_task_retry(self) -> None:
        from core.mission.mission_scheduler import MissionRecovery
        from core.mission.mission_types import MissionStatus

        t = _task(max_retries=3)
        t.retries = 1
        t.status = MissionStatus.FAILED
        t.error = "timeout"
        result = MissionRecovery().prepare_task_retry(t)
        assert result.retries == 2
        assert result.status == MissionStatus.PENDING
        assert result.error is None


# ===========================================================================
# 8. GoalScheduler integration tests
# ===========================================================================


class TestGoalScheduler:
    @pytest.mark.asyncio
    async def test_schedule_mission_queues_it(self) -> None:
        sched = _scheduler()
        m = _mission()
        await sched.schedule_mission(m)
        assert await sched.queue_depth() == 1

    @pytest.mark.asyncio
    async def test_get_mission_returns_state(self) -> None:
        sched = _scheduler()
        m = _mission()
        await sched.schedule_mission(m)
        found = await sched.get_mission(m.id)
        assert found is not None
        assert found.id == m.id

    @pytest.mark.asyncio
    async def test_get_mission_unknown_returns_none(self) -> None:
        sched = _scheduler()
        found = await sched.get_mission(uuid4())
        assert found is None

    @pytest.mark.asyncio
    async def test_cancel_queued_mission(self) -> None:
        sched = _scheduler()
        m = _mission()
        await sched.schedule_mission(m)
        success = await sched.cancel_mission(m.id)
        assert success is True
        from core.mission.mission_types import MissionStatus
        found = await sched.get_mission(m.id)
        assert found is not None and found.status == MissionStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_unknown_returns_false(self) -> None:
        sched = _scheduler()
        assert await sched.cancel_mission(uuid4()) is False

    @pytest.mark.asyncio
    async def test_pause_and_resume(self) -> None:
        from core.mission.mission_types import MissionStatus

        sched = _scheduler()
        m = _mission()
        await sched.schedule_mission(m)
        # Force to RUNNING
        async with sched._lock:
            m.status = MissionStatus.RUNNING

        paused = await sched.pause_mission(m.id)
        assert paused is True
        assert (await sched.get_mission(m.id)).status == MissionStatus.PAUSED

        resumed = await sched.resume_mission(m.id)
        assert resumed is True
        assert (await sched.get_mission(m.id)).status == MissionStatus.QUEUED

    @pytest.mark.asyncio
    async def test_list_missions_no_filter(self) -> None:
        sched = _scheduler()
        m1 = _mission()
        m2 = _mission()
        await sched.schedule_mission(m1)
        await sched.schedule_mission(m2)
        missions = await sched.list_missions()
        assert len(missions) == 2

    @pytest.mark.asyncio
    async def test_list_missions_status_filter(self) -> None:
        from core.mission.mission_types import MissionStatus

        sched = _scheduler()
        m = _mission()
        await sched.schedule_mission(m)
        queued = await sched.list_missions(status=MissionStatus.QUEUED)
        assert len(queued) == 1

    @pytest.mark.asyncio
    async def test_run_next_empty_queue_returns_none(self) -> None:
        sched = _scheduler()
        result = await sched.run_next()
        assert result is None

    @pytest.mark.asyncio
    async def test_run_next_succeeds(self) -> None:
        from core.mission.mission_types import MissionStatus

        sched = _scheduler()
        m = _mission()
        await sched.schedule_mission(m)
        result = await sched.run_next()
        assert result is not None
        assert result.status == MissionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_run_next_with_multi_task_mission(self) -> None:
        from core.mission.mission_types import MissionStatus

        t1 = _task("a")
        t2 = _task("b", depends_on=[t1.id])
        sched = _scheduler()
        m = _mission(tasks=[t1, t2])
        await sched.schedule_mission(m)
        result = await sched.run_next()
        assert result is not None
        assert result.status == MissionStatus.COMPLETED
        assert result.tasks_completed == 2

    @pytest.mark.asyncio
    async def test_budget_exhausted_fails_mission(self) -> None:
        from core.mission.mission_types import MissionStatus

        # Executor returns 200 but budget is only 10 — on first consume
        # the result is False (exceeds grace ceiling), then is_exhausted triggers
        async def expensive_executor(mission: Any, task: Any) -> float:
            return 200.0

        # Set overage_grace=1.0 (exact limit) so 200 > 10 * 1.0 triggers immediately
        from core.mission.mission_scheduler import GoalScheduler
        from core.mission.mission_types import SchedulerConfig

        sched = GoalScheduler(
            config=SchedulerConfig(max_concurrent_missions=5, budget_overage_grace=1.0),
            executor=expensive_executor,
        )
        m = _mission(total_budget=10.0)
        await sched.schedule_mission(m)
        result = await sched.run_next()
        assert result is not None
        # After the first task consumes 200 > 10, the next task's pre-check
        # catches exhaustion. With only 1 task the mission completes.
        # To truly trigger exhaustion, we need multiple tasks where the
        # first one already blows the budget before the second runs.
        t1 = _task("a")
        t2 = _task("b")
        m2 = _mission(tasks=[t1, t2], total_budget=10.0)
        sched2 = GoalScheduler(
            config=SchedulerConfig(budget_overage_grace=1.0),
            executor=expensive_executor,
        )
        await sched2.schedule_mission(m2)
        result2 = await sched2.run_next()
        assert result2 is not None
        assert result2.status == MissionStatus.FAILED
        assert result2.error is not None

    @pytest.mark.asyncio
    async def test_task_failure_triggers_mission_fail_when_no_retry(self) -> None:
        from core.mission.mission_types import MissionStatus

        async def failing_executor(mission: Any, task: Any) -> float:
            raise RuntimeError("Simulated task failure")

        sched = _scheduler(executor=failing_executor)
        m = _mission(max_retries=0)
        await sched.schedule_mission(m)
        result = await sched.run_next()
        assert result is not None
        assert result.status == MissionStatus.FAILED

    @pytest.mark.asyncio
    async def test_task_retry_on_failure(self) -> None:
        """Task retries once then succeeds on second attempt."""
        call_count = 0

        async def flaky_executor(mission: Any, task: Any) -> float:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First failure")
            return 1.0

        t = _task(max_retries=2)
        sched = _scheduler(executor=flaky_executor)
        m = _mission(tasks=[t])
        await sched.schedule_mission(m)
        result = await sched.run_next()
        assert result is not None
        from core.mission.mission_types import MissionStatus
        assert result.status == MissionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_event_bus_publish_on_schedule(self) -> None:
        from core.mission.mission_scheduler import GoalScheduler
        from core.mission.mission_types import SchedulerConfig

        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock()
        sched = GoalScheduler(
            config=SchedulerConfig(),
            event_bus=mock_bus,
        )
        m = _mission()
        await sched.schedule_mission(m)
        mock_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_concurrent_cap_respected(self) -> None:
        """Scheduler respects max_concurrent_missions cap."""
        from core.mission.mission_scheduler import GoalScheduler
        from core.mission.mission_types import SchedulerConfig

        sched = GoalScheduler(
            config=SchedulerConfig(max_concurrent_missions=1),
        )
        m = _mission()
        await sched.schedule_mission(m)
        # Artificially mark one as already running
        async with sched._lock:
            sched._running.add(uuid4())

        result = await sched.run_next()
        # Should return None (cap hit)
        assert result is None


# ===========================================================================
# 9. BackgroundGoalRunner tests
# ===========================================================================


class TestBackgroundGoalRunner:
    @pytest.mark.asyncio
    async def test_start_sets_running(self) -> None:
        from core.mission.mission_scheduler import BackgroundGoalRunner

        sched = _scheduler()
        runner = BackgroundGoalRunner(scheduler=sched, poll_interval=0.05)
        await runner.start()
        assert runner.is_running is True
        await runner.stop()
        assert runner.is_running is False

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self) -> None:
        from core.mission.mission_scheduler import BackgroundGoalRunner

        sched = _scheduler()
        runner = BackgroundGoalRunner(scheduler=sched, poll_interval=0.05)
        await runner.start()
        task1 = runner._task
        await runner.start()  # Should no-op
        assert runner._task is task1
        await runner.stop()

    @pytest.mark.asyncio
    async def test_runner_drains_mission(self) -> None:
        from core.mission.mission_scheduler import BackgroundGoalRunner
        from core.mission.mission_types import MissionStatus

        sched = _scheduler()
        m = _mission()
        await sched.schedule_mission(m)

        runner = BackgroundGoalRunner(scheduler=sched, poll_interval=0.05)
        await runner.start()
        # Give runner time to drain the queue
        await asyncio.sleep(0.3)
        await runner.stop()

        found = await sched.get_mission(m.id)
        assert found is not None
        assert found.status == MissionStatus.COMPLETED


# ===========================================================================
# 10. API Route handler tests
# ===========================================================================


class TestMissionSchedulerRoutes:
    """Integration-style tests for mission scheduler route handlers."""

    @pytest.fixture
    def mock_scheduler(self) -> Any:
        return AsyncMock()

    @pytest.fixture
    def client(self, mock_scheduler: Any) -> Any:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.dependencies import get_goal_scheduler
        from api.routes.mission_scheduler import router

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_goal_scheduler] = lambda: mock_scheduler
        return TestClient(app)

    def _mission_payload(self) -> dict:
        return {
            "name": "API Mission",
            "priority": 5,
            "tasks": [{"name": "step1", "budget": 10.0}],
            "total_budget": 100.0,
            "max_retries": 0,
        }


    def test_create_mission_success(self, client: Any, mock_scheduler: Any) -> None:
        mock_scheduler.schedule_mission = AsyncMock()
        response = client.post("/scheduler/missions", json=self._mission_payload())
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "API Mission"
        # Before schedule_mission runs on the real scheduler, Mission starts as 'pending'
        assert data["status"] in ("pending", "queued")

    def test_create_mission_missing_tasks(
        self, client: Any, mock_scheduler: Any
    ) -> None:
        payload = {"name": "Empty", "priority": 5, "tasks": [], "total_budget": 100.0}
        response = client.post("/scheduler/missions", json=payload)
        assert response.status_code == 422

    def test_create_mission_cycle_returns_400(
        self, client: Any, mock_scheduler: Any
    ) -> None:
        with patch(
            "core.mission.mission_scheduler.GoalDependencyResolver.resolve",
            side_effect=ValueError("Dependency cycle"),
        ):
            response = client.post("/scheduler/missions", json=self._mission_payload())
        assert response.status_code == 400

    def test_get_mission_found(self, client: Any, mock_scheduler: Any) -> None:
        m = _mission()
        mock_scheduler.get_mission = AsyncMock(return_value=m)
        response = client.get(f"/scheduler/missions/{m.id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(m.id)

    def test_get_mission_not_found(self, client: Any, mock_scheduler: Any) -> None:
        mock_scheduler.get_mission = AsyncMock(return_value=None)
        response = client.get(f"/scheduler/missions/{uuid4()}")
        assert response.status_code == 404

    def test_cancel_mission_success(self, client: Any, mock_scheduler: Any) -> None:
        mock_scheduler.cancel_mission = AsyncMock(return_value=True)
        response = client.post(f"/scheduler/missions/{uuid4()}/cancel")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_cancel_mission_not_found(self, client: Any, mock_scheduler: Any) -> None:
        mock_scheduler.cancel_mission = AsyncMock(return_value=False)
        response = client.post(f"/scheduler/missions/{uuid4()}/cancel")
        assert response.status_code == 404

    def test_pause_mission_success(self, client: Any, mock_scheduler: Any) -> None:
        mock_scheduler.pause_mission = AsyncMock(return_value=True)
        response = client.post(f"/scheduler/missions/{uuid4()}/pause")
        assert response.status_code == 200

    def test_pause_mission_invalid_state(
        self, client: Any, mock_scheduler: Any
    ) -> None:
        mock_scheduler.pause_mission = AsyncMock(return_value=False)
        response = client.post(f"/scheduler/missions/{uuid4()}/pause")
        assert response.status_code == 400

    def test_resume_mission_success(self, client: Any, mock_scheduler: Any) -> None:
        mock_scheduler.resume_mission = AsyncMock(return_value=True)
        response = client.post(f"/scheduler/missions/{uuid4()}/resume")
        assert response.status_code == 200

    def test_resume_mission_invalid_state(
        self, client: Any, mock_scheduler: Any
    ) -> None:
        mock_scheduler.resume_mission = AsyncMock(return_value=False)
        response = client.post(f"/scheduler/missions/{uuid4()}/resume")
        assert response.status_code == 400

    def test_get_queue_empty(self, client: Any, mock_scheduler: Any) -> None:
        mock_scheduler._queue = MagicMock()
        mock_scheduler._queue.all_items = AsyncMock(return_value=[])
        response = client.get("/scheduler/queue")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_stats(self, client: Any, mock_scheduler: Any) -> None:
        from core.mission.mission_types import SchedulerConfig

        mock_scheduler.queue_depth = AsyncMock(return_value=2)
        mock_scheduler.running_count = AsyncMock(return_value=1)
        mock_scheduler.config = SchedulerConfig(
            max_concurrent_missions=5, poll_interval_seconds=1.0
        )
        response = client.get("/scheduler/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["queue_depth"] == 2
        assert data["running_count"] == 1
        assert data["max_concurrent"] == 5
