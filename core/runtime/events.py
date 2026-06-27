"""JARVIS OS - Agent Runtime State Persistence and Event Integration.

Defines the IStateStore contract, InMemory and Redis store implementations, and event bus notifiers.
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, cast
from uuid import UUID, uuid4

import redis.asyncio as aioredis

from core.exceptions import JarvisSystemError
from core.interfaces import EventBusInterface, InterAgentMessage


class IStateStore(ABC):
    """Abstract interface contract for persisting active agent runtime states."""

    @abstractmethod
    async def get_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored state details for a given agent.

        Args:
            agent_id: Target agent ID.

        Returns:
            Dictionary payload if state exists, None otherwise.
        """
        pass

    @abstractmethod
    async def set_state(self, agent_id: str, state_data: Dict[str, Any]) -> None:
        """Save or overwrite active state details for a given agent.

        Args:
            agent_id: Target agent ID.
            state_data: Dictionary payload representing new state details.
        """
        pass

    @abstractmethod
    async def delete_state(self, agent_id: str) -> None:
        """Deallocate and delete stored state details for a given agent.

        Args:
            agent_id: Target agent ID.
        """
        pass


class InMemoryStateStore(IStateStore):
    """Local, in-memory implementation of the state store for testing and fallback scenarios."""

    def __init__(self) -> None:
        self._states: Dict[str, Dict[str, Any]] = {}

    async def get_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self._states.get(agent_id)

    async def set_state(self, agent_id: str, state_data: Dict[str, Any]) -> None:
        self._states[agent_id] = state_data

    async def delete_state(self, agent_id: str) -> None:
        self._states.pop(agent_id, None)


class RedisStateStore(IStateStore):
    """Production-grade Redis hash storage implementation of IStateStore."""

    def __init__(self, client: aioredis.Redis) -> None:
        """Initialize RedisStateStore.

        Args:
            client: An active async Redis client.
        """
        self.client = client

    def _key(self, agent_id: str) -> str:
        return f"jarvis:state:agent:{agent_id}"

    async def get_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        try:
            data = await self.client.get(self._key(agent_id))
            if data:
                return cast(Optional[Dict[str, Any]], json.loads(data))
            return None
        except Exception as err:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Failed to get agent state from Redis: {str(err)}",
            )

    async def set_state(self, agent_id: str, state_data: Dict[str, Any]) -> None:
        try:
            await self.client.set(self._key(agent_id), json.dumps(state_data))
        except Exception as err:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Failed to set agent state in Redis: {str(err)}",
            )

    async def delete_state(self, agent_id: str) -> None:
        try:
            await self.client.delete(self._key(agent_id))
        except Exception as err:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Failed to delete agent state from Redis: {str(err)}",
            )


class AgentRuntimeNotifier:
    """Dispatches state transition events to the global system Event Bus."""

    def __init__(
        self, event_bus: EventBusInterface, sender_name: str = "agent_runtime"
    ) -> None:
        """Initialize AgentRuntimeNotifier.

        Args:
            event_bus: The system EventBus instance.
            sender_name: Identity name of the sender.
        """
        self.event_bus = event_bus
        self.sender_name = sender_name

    async def notify_state_changed(
        self,
        agent_id: UUID,
        previous_state: str,
        current_state: str,
        correlation_id: Optional[UUID] = None,
    ) -> bool:
        """Publish an agent state changed notification envelope.

        Args:
            agent_id: The UUID of the subagent or runner.
            previous_state: Prior state string representation.
            current_state: New state string representation.
            correlation_id: Optional correlation identifier.

        Returns:
            True if publication succeeded, False otherwise.
        """
        message = InterAgentMessage(
            id=uuid4(),
            correlation_id=correlation_id or uuid4(),
            sender=self.sender_name,
            receiver="system_broadcast",
            action="agent_state_changed",
            body={
                "agent_id": str(agent_id),
                "previous_state": previous_state,
                "current_state": current_state,
            },
        )
        return await self.event_bus.publish("agent.state.changed", message)
