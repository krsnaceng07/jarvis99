"""JARVIS OS - Task Scheduler.

Implements extensible scheduling strategies and the core TaskScheduler queue coordinator.
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.runtime.dto import SwarmTask


class ScheduledTask(BaseModel):
    """Pydantic model representing a scheduled task in the runtime queue."""

    id: UUID
    priority: int = Field(
        default=0, description="Task priority value. Higher runs first."
    )
    deadline: Optional[datetime] = Field(
        default=None, description="Optional time constraint boundary."
    )
    cost: float = Field(default=0.0, description="Estimated compute or resource cost.")
    payload: Dict[str, Any] = Field(
        default_factory=dict, description="Metadata and input variables."
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ISchedulerStrategy(ABC):
    """Abstract base contract defining task queue sorting and prioritization strategies."""

    @abstractmethod
    async def schedule(self, tasks: List[ScheduledTask]) -> List[ScheduledTask]:
        """Prioritize and order a list of pending scheduled tasks.

        Args:
            tasks: List of active pending ScheduledTask models.

        Returns:
            Sorted list of tasks, where index 0 is scheduled to run next.
        """
        pass


class FIFOSchedulerStrategy(ISchedulerStrategy):
    """First-In, First-Out (FIFO) queue scheduler sorting tasks by creation timestamp."""

    async def schedule(self, tasks: List[ScheduledTask]) -> List[ScheduledTask]:
        return sorted(tasks, key=lambda t: t.created_at)


class PrioritySchedulerStrategy(ISchedulerStrategy):
    """Priority queue scheduler sorting tasks by priority value descending."""

    async def schedule(self, tasks: List[ScheduledTask]) -> List[ScheduledTask]:
        # High priority first, fallback to FIFO for tie-breakers
        return sorted(tasks, key=lambda t: (-t.priority, t.created_at))


class DeadlineSchedulerStrategy(ISchedulerStrategy):
    """Deadline-first scheduler strategy (Stub)."""

    async def schedule(self, tasks: List[ScheduledTask]) -> List[ScheduledTask]:
        def sort_key(t: ScheduledTask) -> datetime:
            return t.deadline or datetime.max.replace(tzinfo=timezone.utc)

        return sorted(tasks, key=sort_key)


class RoundRobinSchedulerStrategy(ISchedulerStrategy):
    """Round-Robin fair share scheduler strategy (Stub)."""

    async def schedule(self, tasks: List[ScheduledTask]) -> List[ScheduledTask]:
        # Placeholder returning list as is
        return tasks


class CostAwareSchedulerStrategy(ISchedulerStrategy):
    """Cost-Aware optimization scheduler strategy (Stub)."""

    async def schedule(self, tasks: List[ScheduledTask]) -> List[ScheduledTask]:
        # Sorts ascending by estimated run cost
        return sorted(tasks, key=lambda t: t.cost)


class TaskScheduler:
    """Async task coordinator managing active priority queues using swappable strategies."""

    def __init__(self, strategy: Optional[ISchedulerStrategy] = None) -> None:
        """Initialize TaskScheduler.

        Args:
            strategy: Custom scheduler strategy. Defaults to FIFOSchedulerStrategy.
        """
        self.strategy = strategy or FIFOSchedulerStrategy()
        self._queue: List[ScheduledTask] = []
        self._lock = asyncio.Lock()

    async def set_strategy(self, strategy: ISchedulerStrategy) -> None:
        """Change queue sorting strategy dynamically.

        Args:
            strategy: Concrete ISchedulerStrategy instance.
        """
        async with self._lock:
            self.strategy = strategy
            self._queue = await self.strategy.schedule(self._queue)

    async def add_task(self, task: ScheduledTask) -> None:
        """Enqueue a task and trigger sorting sequence.

        Args:
            task: Target ScheduledTask model.
        """
        async with self._lock:
            self._queue.append(task)
            self._queue = await self.strategy.schedule(self._queue)

    async def get_next_task(self) -> Optional[ScheduledTask]:
        """Dequeue and return the next highest priority task.

        Returns:
            The ScheduledTask if queue is not empty, None otherwise.
        """
        async with self._lock:
            if not self._queue:
                return None
            return self._queue.pop(0)

    async def get_all_tasks(self) -> List[ScheduledTask]:
        """Return a copy of all currently pending tasks.

        Returns:
            List of ScheduledTask models.
        """
        async with self._lock:
            return list(self._queue)


class CapabilityNegotiator:
    """Evaluates agent loads and selects the optimal assignee for a given task."""

    def score_agent(self, agent: Dict[str, Any], task: SwarmTask) -> float:
        """Score agent viability based on capacity, memory, priority and history.

        Returns:
            Calculated score, higher is better.
        """
        # availability: 1.0 if idle, 0.5 if busy, 0.0 if offline
        status = agent.get("status", "ONLINE")
        availability = (
            1.0 if status == "ONLINE" else 0.5 if status == "WORKING" else 0.0
        )

        # resource constraints: inverse of CPU and RAM loads
        cpu_score = 1.0 - min(float(agent.get("cpu_load", 0.0)), 1.0)
        mem_score = 1.0 - min(float(agent.get("memory", 0.0)) / 1024.0, 1.0)

        # reliability constraints: inverse of failure count
        recent_failures = int(agent.get("recent_failures", 0))
        failure_score = 1.0 / (1.0 + recent_failures)

        return float(
            (availability * 0.4)
            + (cpu_score * 0.2)
            + (mem_score * 0.2)
            + (failure_score * 0.2)
        )

    def select_best_agent(
        self, agents: List[Dict[str, Any]], task: SwarmTask
    ) -> Optional[UUID]:
        """Select the highest scoring agent that satisfies the task requirements.

        Args:
            agents: List of active agent descriptors.
            task: Target SwarmTask.

        Returns:
            Best agent UUID or None.
        """
        best_agent_id: Optional[UUID] = None
        best_score = -1.0

        for agent in agents:
            # Capability check: agent must provide all required capabilities
            provided = set(agent.get("capabilities", []))
            required = set(task.capabilities)
            if not required.issubset(provided):
                continue

            score = self.score_agent(agent, task)
            if score > best_score:
                best_score = score
                best_agent_id = agent.get("id")

        return best_agent_id
