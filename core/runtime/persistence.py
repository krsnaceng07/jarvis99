"""JARVIS OS - Swarm Persistence.

Abstracts storage operations for distributed swarm tasks and telemetry snapshots.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID

from core.runtime.dto import SwarmSnapshot, SwarmTask


class SwarmPersistence(ABC):
    """Abstract interface defining swarm data persistence engines."""

    @abstractmethod
    async def save_task(self, task: SwarmTask) -> None:
        """Persist a swarm task record.

        Args:
            task: Target SwarmTask.
        """
        pass

    @abstractmethod
    async def save_agent(self, agent_id: UUID, agent_data: Dict[str, Any]) -> None:
        """Persist a subagent registration record.

        Args:
            agent_id: Mapped subagent ID.
            agent_data: Subagent metadata properties.
        """
        pass

    @abstractmethod
    async def save_snapshot(self, snapshot: SwarmSnapshot) -> None:
        """Persist a global swarm snapshot record.

        Args:
            snapshot: SwarmSnapshot telemetry.
        """
        pass

    @abstractmethod
    async def load_snapshot(self) -> Optional[SwarmSnapshot]:
        """Load the last saved swarm snapshot.

        Returns:
            SwarmSnapshot telemetry or None.
        """
        pass

    @abstractmethod
    async def save_history(
        self, session_id: UUID, history: List[Dict[str, Any]]
    ) -> None:
        """Persist subagent message execution histories.

        Args:
            session_id: Target session ID.
            history: List of trace events.
        """
        pass


class SwarmRepository(SwarmPersistence):
    """InMemory/SQLAlchemy repository adapter for persistent swarm states."""

    def __init__(self) -> None:
        """Initialize SwarmRepository."""
        self._tasks: Dict[UUID, SwarmTask] = {}
        self._agents: Dict[UUID, Dict[str, Any]] = {}
        self._snapshots: List[SwarmSnapshot] = []
        self._histories: Dict[UUID, List[Dict[str, Any]]] = {}

    async def save_task(self, task: SwarmTask) -> None:
        self._tasks[task.task_id] = task

    async def save_agent(self, agent_id: UUID, agent_data: Dict[str, Any]) -> None:
        self._agents[agent_id] = agent_data

    async def save_snapshot(self, snapshot: SwarmSnapshot) -> None:
        self._snapshots.append(snapshot)

    async def load_snapshot(self) -> Optional[SwarmSnapshot]:
        if self._snapshots:
            return self._snapshots[-1]
        return None

    async def save_history(
        self, session_id: UUID, history: List[Dict[str, Any]]
    ) -> None:
        self._histories[session_id] = history
