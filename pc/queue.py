"""JARVIS OS - PC Execution Queue.

Serializes mouse/keyboard automation sequences to prevent parallel conflicts.
"""

import asyncio
from typing import Any, Awaitable, Callable, Dict, List


class PCExecutionQueue:
    """FIFO queue coordinating sequential execution and priority overrides."""

    def __init__(self) -> None:
        """Initialize PCExecutionQueue."""
        self._queue: List[Any] = []
        self._paused: bool = False
        self._lock = asyncio.Lock()

    async def enqueue(self, action: Any, priority: bool = False) -> None:
        """Append or prepend a task action.

        Args:
            action: PCAction DTO.
            priority: True to prepend action for priority bypass.
        """
        async with self._lock:
            if priority:
                self._queue.insert(0, action)
            else:
                self._queue.append(action)

    async def process_next(
        self, executor_callback: Callable[[Any], Awaitable[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """Process next task in line if queue is active.

        Args:
            executor_callback: Callback running target action.

        Returns:
            Dictionary mapped completion result.
        """
        async with self._lock:
            if self._paused or not self._queue:
                return {"status": "SKIPPED", "message": "Queue is paused or empty."}

            action = self._queue.pop(0)

        # Execute action outside the queue list lock to prevent blocking enqueues
        try:
            return await executor_callback(action)
        except Exception as err:
            return {"status": "ERROR", "message": f"Execution error: {str(err)}"}

    def pause(self) -> None:
        """Pause queue execution processing."""
        self._paused = True

    def resume(self) -> None:
        """Resume queue execution processing."""
        self._paused = False

    def cancel_all(self) -> None:
        """Discard all pending actions from the queue."""
        self._queue.clear()

    @property
    def size(self) -> int:
        """Get pending queue depth.

        Returns:
            Count of items in queue.
        """
        return len(self._queue)
