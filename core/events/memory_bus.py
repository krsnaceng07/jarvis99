"""JARVIS OS - Memory Event Bus.

In-memory event bus implementation for development and testing profiles.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Dict, List
from uuid import uuid4

from core.events.base import EventBus
from core.interfaces import InterAgentMessage

logger = logging.getLogger("jarvis.core.events.memory_bus")


class MemoryEventBus(EventBus):
    """Local, in-memory implementation of the global system event bus."""

    def __init__(self) -> None:
        """Initialize the MemoryEventBus."""
        self._subscribers: Dict[
            str, List[tuple[str, Callable[[InterAgentMessage], Awaitable[None]]]]
        ] = {}
        self._active: bool = False

    async def initialize(self) -> None:
        """Initialize subscriptions map."""
        self._subscribers = {}
        self._active = False

    async def start(self) -> None:
        """Activate event processing loop."""
        self._active = True
        logger.info("MemoryEventBus started.")

    async def stop(self) -> None:
        """Deactivate event processing."""
        self._active = False
        logger.info("MemoryEventBus stopped.")

    async def shutdown(self) -> None:
        """Clear all active subscriptions."""
        self._subscribers.clear()
        self._active = False
        logger.info("MemoryEventBus shutdown complete.")

    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        """Publish a message to all registered subscriber callbacks for the topic.

        Args:
            topic: The namespace topic (e.g. 'agent.task.started').
            message: The InterAgentMessage envelope.

        Returns:
            True if published successfully, False otherwise.
        """
        if not self._active:
            logger.warning("Event bus is not active. Message dropped: %s", topic)
            return False

        logger.info("EventBus [Memory] Publish to '%s': %s", topic, message.action)

        # Get subscribers for exact topic
        listeners = self._subscribers.get(topic, [])
        for sub_id, callback in listeners:
            # Run subscriber callback in a background task to prevent blocking publisher
            asyncio.create_task(self._safe_dispatch(callback, message, sub_id, topic))

        return True

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[InterAgentMessage], Awaitable[None]],
    ) -> str:
        """Subscribe an async callback to a topic.

        Args:
            topic: The topic namespace.
            callback: The async callback function.

        Returns:
            A unique subscription ID for unregistering.
        """
        sub_id = str(uuid4())
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append((sub_id, callback))
        logger.debug("Subscribed to '%s' with ID: %s", topic, sub_id)
        return sub_id

    async def unsubscribe(self, topic: str, sub_id: str) -> bool:
        """Unsubscribe a callback from a topic.

        Args:
            topic: The topic namespace.
            sub_id: The unique subscription ID.

        Returns:
            True if unsubscribe succeeded, False otherwise.
        """
        if topic in self._subscribers:
            listeners = self._subscribers[topic]
            for i, (listener_id, _) in enumerate(listeners):
                if listener_id == sub_id:
                    listeners.pop(i)
                    logger.debug("Unsubscribed ID %s from topic %s", sub_id, topic)
                    return True
        return False

    async def _safe_dispatch(
        self,
        callback: Callable[[InterAgentMessage], Awaitable[None]],
        message: InterAgentMessage,
        sub_id: str,
        topic: str,
    ) -> None:
        """Safely execute subscriber callback and intercept exceptions."""
        try:
            await callback(message)
        except Exception as err:
            logger.error(
                "Subscriber callback '%s' failed on topic '%s': %s",
                sub_id,
                topic,
                str(err),
            )
