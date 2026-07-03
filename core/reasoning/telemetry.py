"""JARVIS OS - Reasoning Telemetry.

Emits structured telemetry events representing model provider call status changes to the EventBus.
"""

from typing import Any, Dict, Optional
from uuid import uuid4

from core.events.base import EventBus
from core.interfaces import InterAgentMessage


class ReasoningTelemetry:
    """Helper class to publish reasoning telemetry events to the global system EventBus."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        """Initialize ReasoningTelemetry.

        Args:
            event_bus: The system-wide global EventBus instance.
        """
        self.event_bus = event_bus

    async def publish_event(
        self,
        action: str,
        provider_name: str,
        model_name: str,
        body: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Construct and publish a model provider lifecycle event to the EventBus.

        Args:
            action: Telemetry event action name (e.g. 'provider.started', 'provider.failed').
            provider_name: The name of the target LLM provider.
            model_name: The targeted model identifier.
            body: Event details.

        Returns:
            True if event was published successfully, False otherwise.
        """
        if not self.event_bus:
            return False

        event_body = {
            "provider_name": provider_name,
            "model_name": model_name,
            **(body or {}),
        }

        # Topic channel: e.g. "reasoning.telemetry.provider.started"
        topic = f"reasoning.telemetry.{action}"

        message = InterAgentMessage(
            id=uuid4(),
            correlation_id=uuid4(),
            sender="reasoning_engine",
            receiver="event_bus",
            action=action,
            body=event_body,
        )

        try:
            return await self.event_bus.publish(topic, message)
        except Exception:
            # Telemetry failures must not crash parent model calls
            return False
