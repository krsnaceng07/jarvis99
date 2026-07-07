"""
PHASE: 44
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md

IMPLEMENTATION PLAN:
    Phase 44 approved plan — Mission & Autonomous Goal Scheduler

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Module role: Mission Scheduler core. Contains:
  - GoalDependencyResolver  — topological task ordering
  - PriorityEngine          — computes effective queue position
  - DeadlineManager         — tracks and escalates due-soon missions
  - ExecutionBudgetManager  — enforces per-mission token/compute budgets
  - MissionQueue            — in-memory priority queue
  - MissionRecovery         — retry and restart logic
  - GoalScheduler           — top-level orchestrator
  - BackgroundGoalRunner    — asyncio background runner loop
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID

from core.interfaces import EventBusInterface, InterAgentMessage
from core.mission.mission_types import (
    Mission,
    MissionQueueItem,
    MissionResult,
    MissionStatus,
    MissionTask,
    SchedulerConfig,
)

logger = logging.getLogger("jarvis.core.mission.scheduler")


# ---------------------------------------------------------------------------
# GoalDependencyResolver
# ---------------------------------------------------------------------------


class GoalDependencyResolver:
    """Resolves MissionTask execution order via topological sort (Kahn's algorithm).

    Invariant: Repository-free — pure in-memory ordering logic only.
    """

    def resolve(self, tasks: List[MissionTask]) -> List[List[MissionTask]]:
        """Return tasks grouped into sequentially executable waves.

        Wave N tasks may only start after all Wave N-1 tasks complete.
        Tasks within the same wave are independent and can run in parallel.

        Raises:
            ValueError: If a dependency cycle is detected.
        """
        task_map: Dict[UUID, MissionTask] = {t.id: t for t in tasks}
        in_degree: Dict[UUID, int] = {t.id: 0 for t in tasks}
        adj: Dict[UUID, List[UUID]] = {t.id: [] for t in tasks}

        for task in tasks:
            for dep_id in task.depends_on:
                if dep_id not in task_map:
                    logger.warning(
                        "Task %s references unknown dependency %s — skipping",
                        task.id,
                        dep_id,
                    )
                    continue
                adj[dep_id].append(task.id)
                in_degree[task.id] += 1

        waves: List[List[MissionTask]] = []
        queued: Set[UUID] = set()
        ready = [t_id for t_id, deg in in_degree.items() if deg == 0]

        while ready:
            wave_ids = list(ready)
            for t_id in wave_ids:
                queued.add(t_id)
            waves.append([task_map[t_id] for t_id in wave_ids])

            ready = []
            for t_id in wave_ids:
                for neighbour in adj[t_id]:
                    in_degree[neighbour] -= 1
                    if in_degree[neighbour] == 0 and neighbour not in queued:
                        ready.append(neighbour)

        if len(queued) < len(tasks):
            cycle_tasks = [str(t.id) for t in tasks if t.id not in queued]
            raise ValueError(
                f"Dependency cycle detected in mission tasks: {cycle_tasks}"
            )

        return waves


# ---------------------------------------------------------------------------
# PriorityEngine
# ---------------------------------------------------------------------------


class PriorityEngine:
    """Computes the effective scheduling weight for a MissionQueueItem."""

    def score(self, item: MissionQueueItem) -> float:
        """Higher score → run sooner."""
        return item.effective_priority()

    def sort_queue(self, items: List[MissionQueueItem]) -> List[MissionQueueItem]:
        """Return items sorted by descending effective priority."""
        return sorted(items, key=self.score, reverse=True)


# ---------------------------------------------------------------------------
# DeadlineManager
# ---------------------------------------------------------------------------


class DeadlineManager:
    """Tracks missions with deadlines and flags overdue ones."""

    def get_overdue(self, missions: List[Mission]) -> List[Mission]:
        """Return all missions past their deadline that are not yet done."""
        now = datetime.now(timezone.utc)
        return [
            m
            for m in missions
            if m.due_at
            and m.due_at < now
            and m.status not in (
                MissionStatus.COMPLETED,
                MissionStatus.CANCELLED,
                MissionStatus.FAILED,
            )
        ]

    def is_due_soon(self, mission: Mission, window_seconds: float = 300.0) -> bool:
        """Return True if the mission deadline falls within `window_seconds`."""
        if not mission.due_at:
            return False
        remaining = (mission.due_at - datetime.now(timezone.utc)).total_seconds()
        return 0 < remaining <= window_seconds


# ---------------------------------------------------------------------------
# ExecutionBudgetManager
# ---------------------------------------------------------------------------


class ExecutionBudgetManager:
    """Tracks and enforces per-mission compute/token budgets."""

    def __init__(self, overage_grace: float = 1.05) -> None:
        """Initialise budget manager.

        Args:
            overage_grace: Fraction above total_budget allowed before hard-stop.
        """
        self._overage_grace = overage_grace

    def consume(self, mission: Mission, amount: float) -> bool:
        """Deduct `amount` from the mission's remaining budget.

        Returns:
            True if within budget (including grace), False if exhausted.
        """
        mission.used_budget += amount
        return mission.used_budget <= mission.total_budget * self._overage_grace

    def is_exhausted(self, mission: Mission) -> bool:
        """True if mission has exceeded its budget (including grace)."""
        return mission.used_budget > mission.total_budget * self._overage_grace

    def remaining(self, mission: Mission) -> float:
        """Available budget before the grace ceiling."""
        ceiling = mission.total_budget * self._overage_grace
        return max(0.0, ceiling - mission.used_budget)


# ---------------------------------------------------------------------------
# MissionQueue
# ---------------------------------------------------------------------------


class MissionQueue:
    """Thread-safe async priority queue of MissionQueueItems."""

    def __init__(self, priority_engine: Optional[PriorityEngine] = None) -> None:
        self._engine = priority_engine or PriorityEngine()
        self._items: List[MissionQueueItem] = []
        self._lock = asyncio.Lock()

    async def enqueue(self, item: MissionQueueItem) -> None:
        """Add a mission to the queue and re-sort by priority."""
        async with self._lock:
            self._items.append(item)
            self._items = self._engine.sort_queue(self._items)

    async def dequeue(self) -> Optional[MissionQueueItem]:
        """Remove and return the highest-priority mission."""
        async with self._lock:
            if not self._items:
                return None
            return self._items.pop(0)

    async def peek(self) -> Optional[MissionQueueItem]:
        """Return the top item without removing it."""
        async with self._lock:
            return self._items[0] if self._items else None

    async def remove(self, mission_id: UUID) -> bool:
        """Remove a specific mission from the queue."""
        async with self._lock:
            before = len(self._items)
            self._items = [i for i in self._items if i.mission_id != mission_id]
            return len(self._items) < before

    async def size(self) -> int:
        """Return current queue depth."""
        async with self._lock:
            return len(self._items)

    async def all_items(self) -> List[MissionQueueItem]:
        """Return a copy of all queued items."""
        async with self._lock:
            return list(self._items)


# ---------------------------------------------------------------------------
# MissionRecovery
# ---------------------------------------------------------------------------


class MissionRecovery:
    """Handles retry and recovery logic for failed missions and tasks."""

    def should_retry_mission(self, mission: Mission) -> bool:
        """Return True if the mission can be retried."""
        return (
            mission.status == MissionStatus.FAILED
            and mission.retry_count < mission.max_retries
        )

    def prepare_retry(self, mission: Mission) -> Mission:
        """Increment retry counter and reset mission to RECOVERING state."""
        mission.retry_count += 1
        mission.status = MissionStatus.RECOVERING
        mission.error = None
        # Reset failed tasks to PENDING so they re-execute
        for task in mission.tasks:
            if task.status == MissionStatus.FAILED:
                task.status = MissionStatus.PENDING
                task.error = None
        logger.info(
            "Mission %s entering recovery (attempt %d/%d)",
            mission.id,
            mission.retry_count,
            mission.max_retries,
        )
        return mission

    def should_retry_task(self, task: MissionTask) -> bool:
        """Return True if an individual task can be retried."""
        return task.retries < task.max_retries

    def prepare_task_retry(self, task: MissionTask) -> MissionTask:
        """Increment task retry counter and reset to PENDING."""
        task.retries += 1
        task.status = MissionStatus.PENDING
        task.error = None
        return task


# ---------------------------------------------------------------------------
# GoalScheduler
# ---------------------------------------------------------------------------


class GoalScheduler:
    """Top-level orchestrator for autonomous mission execution.

    Wires together MissionQueue, DependencyResolver, BudgetManager,
    DeadlineManager, and MissionRecovery.  Missions are submitted via
    ``schedule_mission`` and executed by the BackgroundGoalRunner.

    Invariant: No direct DB access — persistence delegated to callers.
    """

    def __init__(
        self,
        config: Optional[SchedulerConfig] = None,
        event_bus: Optional[EventBusInterface] = None,
        executor: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config or SchedulerConfig()
        self.event_bus = event_bus
        self._executor = executor  # Optional task-level executor callback

        self._queue = MissionQueue()
        self._resolver = GoalDependencyResolver()
        self._priority_engine = PriorityEngine()
        self._budget_manager = ExecutionBudgetManager(
            overage_grace=self.config.budget_overage_grace
        )
        self._deadline_manager = DeadlineManager()
        self._recovery = MissionRecovery()

        # In-memory mission registry: id → Mission
        self._missions: Dict[UUID, Mission] = {}
        self._running: Set[UUID] = set()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    async def schedule_mission(self, mission: Mission) -> None:
        """Enqueue a mission for execution."""
        async with self._lock:
            self._missions[mission.id] = mission
            mission.status = MissionStatus.QUEUED
            mission.updated_at = datetime.now(timezone.utc)

        item = MissionQueueItem(
            mission_id=mission.id,
            priority=mission.priority,
            deadline=mission.due_at,
        )
        await self._queue.enqueue(item)
        await self._publish("mission.queued", mission)
        logger.info("Scheduled mission %s (priority=%d)", mission.id, mission.priority)

    async def cancel_mission(self, mission_id: UUID) -> bool:
        """Cancel a queued or running mission."""
        await self._queue.remove(mission_id)
        async with self._lock:
            mission = self._missions.get(mission_id)
            if not mission:
                return False
            if mission.status in (
                MissionStatus.COMPLETED,
                MissionStatus.FAILED,
                MissionStatus.CANCELLED,
            ):
                return False
            mission.status = MissionStatus.CANCELLED
            mission.updated_at = datetime.now(timezone.utc)
            self._running.discard(mission_id)

        await self._publish("mission.cancelled", mission)
        logger.info("Cancelled mission %s", mission_id)
        return True

    async def pause_mission(self, mission_id: UUID) -> bool:
        """Pause a running mission."""
        async with self._lock:
            mission = self._missions.get(mission_id)
            if not mission or mission.status != MissionStatus.RUNNING:
                return False
            mission.status = MissionStatus.PAUSED
            mission.updated_at = datetime.now(timezone.utc)

        await self._publish("mission.paused", mission)
        return True

    async def resume_mission(self, mission_id: UUID) -> bool:
        """Re-queue a paused mission."""
        async with self._lock:
            mission = self._missions.get(mission_id)
            if not mission or mission.status != MissionStatus.PAUSED:
                return False
            mission.status = MissionStatus.QUEUED
            mission.updated_at = datetime.now(timezone.utc)

        item = MissionQueueItem(
            mission_id=mission_id,
            priority=mission.priority,
            deadline=mission.due_at,
        )
        await self._queue.enqueue(item)
        await self._publish("mission.resumed", mission)
        return True

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run_next(self) -> Optional[MissionResult]:
        """Dequeue and execute the highest-priority queued mission.

        Returns:
            MissionResult on completion, None if queue is empty or concurrency
            limit reached.
        """
        async with self._lock:
            if len(self._running) >= self.config.max_concurrent_missions:
                return None

        item = await self._queue.dequeue()
        if not item:
            return None

        async with self._lock:
            mission = self._missions.get(item.mission_id)

        if not mission or mission.status == MissionStatus.CANCELLED:
            return None

        return await self._execute_mission(mission)

    async def _execute_mission(self, mission: Mission) -> MissionResult:
        """Drive a mission through its task waves."""
        start = datetime.now(timezone.utc)
        async with self._lock:
            mission.status = MissionStatus.RUNNING
            mission.started_at = start
            mission.updated_at = start
            self._running.add(mission.id)

        await self._publish("mission.started", mission)

        try:
            # Resolve task execution order
            waves = self._resolver.resolve(mission.tasks)
            tasks_completed = 0
            tasks_failed = 0

            for wave in waves:
                for task in wave:
                    # Check cancellation between tasks
                    current = self._missions.get(mission.id)
                    if current and current.status == MissionStatus.CANCELLED:
                        return self._make_result(
                            mission, start, tasks_completed, tasks_failed,
                            error="Cancelled"
                        )

                    # Check pause
                    if current and current.status == MissionStatus.PAUSED:
                        # Re-queue remaining — return partial result
                        return self._make_result(
                            mission, start, tasks_completed, tasks_failed,
                            error="Paused"
                        )

                    # Budget check
                    if self._budget_manager.is_exhausted(mission):
                        mission.status = MissionStatus.FAILED
                        mission.error = "Budget exhausted"
                        await self._publish("mission.budget_exhausted", mission)
                        return self._make_result(
                            mission, start, tasks_completed, tasks_failed,
                            error="Budget exhausted"
                        )

                    success = await self._execute_task(mission, task)
                    if success:
                        tasks_completed += 1
                    else:
                        tasks_failed += 1
                        # Task retry handled inside _execute_task; if task still
                        # failed after retries, check mission retry policy
                        if not self._recovery.should_retry_mission(mission):
                            mission.status = MissionStatus.FAILED
                            mission.error = task.error
                            await self._publish("mission.failed", mission)
                            return self._make_result(
                                mission, start, tasks_completed, tasks_failed,
                                error=task.error
                            )
                        # Mission-level retry
                        mission = self._recovery.prepare_retry(mission)
                        await self._queue.enqueue(
                            MissionQueueItem(
                                mission_id=mission.id,
                                priority=mission.priority,
                                deadline=mission.due_at,
                            )
                        )
                        await self._publish("mission.recovering", mission)
                        return self._make_result(
                            mission, start, tasks_completed, tasks_failed,
                            error=f"Recovering (attempt {mission.retry_count})"
                        )

            # All waves done
            mission.status = MissionStatus.COMPLETED
            mission.completed_at = datetime.now(timezone.utc)
            mission.updated_at = mission.completed_at
            await self._publish("mission.completed", mission)
            return self._make_result(mission, start, tasks_completed, tasks_failed)

        except Exception as exc:
            mission.status = MissionStatus.FAILED
            mission.error = str(exc)
            mission.updated_at = datetime.now(timezone.utc)
            await self._publish("mission.failed", mission)
            logger.exception("Mission %s failed: %s", mission.id, exc)
            return self._make_result(mission, start, 0, 0, error=str(exc))

        finally:
            async with self._lock:
                self._running.discard(mission.id)

    async def _execute_task(self, mission: Mission, task: MissionTask) -> bool:
        """Execute a single task, with per-task retry logic."""
        while True:
            try:
                task.status = MissionStatus.RUNNING
                task.started_at = datetime.now(timezone.utc)

                if self._executor:
                    cost = await self._executor(mission, task)
                    self._budget_manager.consume(mission, float(cost or 0.0))
                else:
                    # Default: simulate small cost per task
                    self._budget_manager.consume(mission, task.budget or 1.0)

                task.status = MissionStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc)
                logger.debug("Task %s completed (mission %s)", task.id, mission.id)
                return True

            except Exception as exc:
                task.error = str(exc)
                logger.warning(
                    "Task %s failed (attempt %d): %s", task.id, task.retries + 1, exc
                )
                if self._recovery.should_retry_task(task):
                    self._recovery.prepare_task_retry(task)
                    await asyncio.sleep(0.1)  # Brief back-off
                else:
                    task.status = MissionStatus.FAILED
                    return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_mission(self, mission_id: UUID) -> Optional[Mission]:
        """Return in-memory mission state."""
        async with self._lock:
            return self._missions.get(mission_id)

    async def list_missions(
        self, status: Optional[MissionStatus] = None
    ) -> List[Mission]:
        """Return all known missions, optionally filtered by status."""
        async with self._lock:
            missions = list(self._missions.values())
        if status:
            missions = [m for m in missions if m.status == status]
        return missions

    async def queue_depth(self) -> int:
        """Return the number of queued missions."""
        return await self._queue.size()

    async def running_count(self) -> int:
        """Return the number of currently executing missions."""
        async with self._lock:
            return len(self._running)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_result(
        self,
        mission: Mission,
        start: datetime,
        completed: int,
        failed: int,
        error: Optional[str] = None,
    ) -> MissionResult:
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        return MissionResult(
            mission_id=mission.id,
            status=mission.status,
            tasks_completed=completed,
            tasks_failed=failed,
            budget_used=mission.used_budget,
            duration_seconds=duration,
            error=error,
        )

    async def _publish(self, event: str, mission: Mission) -> None:
        """Emit a mission lifecycle event on the bus."""
        if not self.event_bus:
            return
        msg = InterAgentMessage(
            sender="goal_scheduler",
            receiver="all",
            action=event,
            body={
                "mission_id": str(mission.id),
                "name": mission.name,
                "status": mission.status.value,
                "priority": mission.priority,
            },
        )
        try:
            await self.event_bus.publish(event, msg)
        except Exception as exc:
            logger.warning("Failed to publish event '%s': %s", event, exc)


# ---------------------------------------------------------------------------
# BackgroundGoalRunner
# ---------------------------------------------------------------------------


class BackgroundGoalRunner:
    """Asyncio background loop that continuously drains the GoalScheduler queue.

    Start with ``start()`` and stop cleanly with ``stop()``.
    """

    def __init__(
        self,
        scheduler: GoalScheduler,
        poll_interval: float = 1.0,
    ) -> None:
        self._scheduler = scheduler
        self._poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Launch the background drain loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="background_goal_runner")
        logger.info("BackgroundGoalRunner started (poll=%.1fs)", self._poll_interval)

    async def stop(self) -> None:
        """Gracefully stop the background loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("BackgroundGoalRunner stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _loop(self) -> None:
        """Drain queue, check for overdue, sleep, repeat."""
        while self._running:
            try:
                result = await self._scheduler.run_next()
                if result:
                    logger.info(
                        "Mission %s finished: %s (%.2fs)",
                        result.mission_id,
                        result.status.value,
                        result.duration_seconds,
                    )
            except Exception as exc:
                logger.exception("BackgroundGoalRunner loop error: %s", exc)

            await asyncio.sleep(self._poll_interval)
