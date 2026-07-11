"""JARVIS OS - Core Interface Definitions.

Provides abstract base classes for subsystem lifecycles and event bus contracts.
"""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


class InterAgentMessage(BaseModel):
    """Pydantic model representing a unified inter-agent message envelope."""

    id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID = Field(default_factory=uuid4)
    sender: str
    receiver: str
    action: str
    body: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LifecycleInterface(ABC):
    """Abstract base class enforcing standard subsystem lifecycle methods."""

    @abstractmethod
    async def initialize(self) -> None:
        """Perform initial setup, config parsing, and resource allocation.

        Raises:
            JarvisSystemError: If initialization fails.
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """Activate the service to begin processing tasks.

        Raises:
            JarvisSystemError: If starting the service fails.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop processing and release external connections.

        Raises:
            JarvisSystemError: If stopping the service fails.
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Deallocate all resources and finalize teardown.

        Raises:
            JarvisSystemError: If teardown fails.
        """
        pass


class EventBusInterface(LifecycleInterface, ABC):
    """Abstract contract for publishing and subscribing to event streams."""

    @abstractmethod
    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        """Publish a structured inter-agent message to a specific topic.

        Args:
            topic: The event topic channel namespace (e.g. 'agent.task.started').
            message: The InterAgentMessage data envelope.

        Returns:
            True if the publish operation succeeded, False otherwise.

        Raises:
            JarvisSystemError: If the message broker is unreachable.
        """
        pass

    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        callback: Callable[[InterAgentMessage], Awaitable[None]],
    ) -> str:
        """Register a callback listener on an event topic.

        Args:
            topic: The event topic channel namespace.
            callback: An asynchronous callback function triggered on new events.

        Returns:
            A unique subscription identifier string for unregistering.

        Raises:
            JarvisSystemError: If the subscription fails.
        """
        pass


class AsyncSessionFactory(Protocol):
    """Structural type for any object that yields an :class:`AsyncSession` as an
    async context manager.

    Implemented by :class:`core.memory.database.DatabaseSessionManager` and any
    test/mock that wants to satisfy the same contract. Used by repositories
    that need to open short-lived sessions internally (e.g. ``SkillRepository``
    when called from background jobs, the installer, or CLI flows that do not
    own a request-scoped session).

    A repository that accepts ``db_manager: AsyncSessionFactory`` at
    construction time can later open its own session via
    ``async with db_manager.session() as s: ...`` without importing
    ``core.memory`` (the previous "loose ``object``" type was used to dodge
    an import cycle; this Protocol replaces it with a real type contract).
    """

    def session(self) -> AbstractAsyncContextManager[AsyncSession]: ...
