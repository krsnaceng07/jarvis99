"""JARVIS OS - Swarm Task Queue.

Serializes subagent workflow tasks using FIFO scheduling and priority sorting constraints.
"""

import asyncio
from typing import Dict, List, Optional
from uuid import UUID

from core.exceptions import JarvisAgentError
from core.runtime.dto import SwarmTask


class SwarmTaskQueue:
    """Centralized priority task queue for distributed swarm agents coordination."""

    def __init__(self) -> None:
        """Initialize SwarmTaskQueue."""
        self._queue: List[SwarmTask] = []
        self._tasks: Dict[UUID, SwarmTask] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, task: SwarmTask) -> None:
        """Add a SwarmTask and execute priority sorting.

        Args:
            task: Structured SwarmTask DTO.
        """
        # Map priorities to numeric values for sorting
        priority_map = {
            "CRITICAL": 5,
            "HIGH": 4,
            "NORMAL": 3,
            "LOW": 2,
            "SYSTEM": 1,
        }

        async with self._lock:
            task.status = "Pending"
            self._tasks[task.task_id] = task
            self._queue.append(task)

            # Sort queue: higher priority score runs first
            self._queue.sort(
                key=lambda t: priority_map.get(t.priority, 3),
                reverse=True,
            )

    async def dequeue(self) -> Optional[SwarmTask]:
        """Fetch the next highest priority pending task.

        Returns:
            The highest priority SwarmTask or None.
        """
        async with self._lock:
            for task in self._queue:
                if task.status == "Pending":
                    task.status = "Running"
                    return task
            return None

    async def update_task_status(self, task_id: UUID, status: str) -> None:
        """Update active execution state for target task.

        Args:
            task_id: Unique task identifier.
            status: Valid SwarmTask state code.

        Raises:
            JarvisAgentError: If task is missing.
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise JarvisAgentError(
                    code="AGENT_999",
                    message=f"Task {task_id} not found in swarm queue.",
                )
            task.status = status

    async def get_task(self, task_id: UUID) -> Optional[SwarmTask]:
        """Fetch task details by identifier.

        Args:
            task_id: Unique task identifier.

        Returns:
            SwarmTask DTO or None.
        """
        async with self._lock:
            return self._tasks.get(task_id)

    @property
    def size(self) -> int:
        """Get total pending queue size.

        Returns:
            Count of pending tasks.
        """
        return len([t for t in self._queue if t.status == "Pending"])
