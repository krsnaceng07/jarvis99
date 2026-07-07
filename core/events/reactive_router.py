"""
PHASE: 40
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/102_PHASE_40_EVENT_BUS_REACTIVE_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/8e27d67d-09cc-4e93-9e3e-d5a4bb653dd9/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import UUID, uuid4

from core.interfaces import EventBusInterface, InterAgentMessage

logger = logging.getLogger("jarvis.core.events.reactive_router")


class ReactiveRouter:
    """Central coordinator managing reactive event subscriptions and publishing wrappers.

    Decouples core modules by routing actions asynchronously via the system EventBus.
    """

    def __init__(self, event_bus: EventBusInterface) -> None:
        """Initialize the ReactiveRouter with a system event bus reference.

        Args:
            event_bus: Singleton matching EventBusInterface.
        """
        self._bus = event_bus
        self._subscription_ids: Dict[str, List[str]] = {}

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[InterAgentMessage], Awaitable[None]],
    ) -> str:
        """Register a callback for a specific event topic.

        Args:
            topic: The target event channel namespace (e.g. 'workflow.completed').
            callback: Async handler callback function.

        Returns:
            The subscription identifier string.
        """
        sub_id = await self._bus.subscribe(topic, callback)
        if topic not in self._subscription_ids:
            self._subscription_ids[topic] = []
        self._subscription_ids[topic].append(sub_id)
        logger.info("ReactiveRouter: registered callback for '%s' (Sub ID: %s)", topic, sub_id)
        return sub_id

    async def unsubscribe(self, topic: str, sub_id: str) -> bool:
        """Unregister a callback subscriber.

        Args:
            topic: The topic channel.
            sub_id: Subscription identifier.

        Returns:
            True if successfully unsubscribed, False otherwise.
        """
        success = await self._bus.unsubscribe(topic, sub_id)
        if success and topic in self._subscription_ids:
            try:
                self._subscription_ids[topic].remove(sub_id)
            except ValueError:
                pass
        return success

    async def publish(
        self,
        topic: str,
        sender: str,
        body: Dict[str, Any],
        correlation_id: Optional[UUID] = None,
    ) -> bool:
        """Helper to package and publish a domain event inside an InterAgentMessage envelope.

        Args:
            topic: Target topic namespace channel.
            sender: Name of the publishing subsystem (e.g. 'workflow_executor').
            body: Structured event payload parameters.
            correlation_id: Optional tracking trace ID to propagate.

        Returns:
            True if event was published successfully, False otherwise.
        """
        trace = correlation_id or uuid4()
        message = InterAgentMessage(
            sender=sender,
            receiver="all",
            action=topic,
            body=body,
            correlation_id=trace,
        )
        logger.info(
            "ReactiveRouter: publishing event '%s' from '%s' [Trace: %s]",
            topic,
            sender,
            trace,
        )
        return await self._bus.publish(topic, message)

    async def shutdown(self) -> None:
        """Clean up active subscription links."""
        for topic, sub_ids in list(self._subscription_ids.items()):
            for sub_id in list(sub_ids):
                await self.unsubscribe(topic, sub_id)
        self._subscription_ids.clear()
        logger.info("ReactiveRouter shutdown complete.")
