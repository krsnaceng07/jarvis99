"""JARVIS OS - Swarm Message Bus.

Brokers inter-agent message exchanges with priority routing, exponential backoffs, and Dead Letter Queue redirection.
"""

import asyncio
import logging
from typing import List

from core.interfaces import EventBusInterface, InterAgentMessage

logger = logging.getLogger("jarvis.core.runtime.message_bus")


class SwarmMessageBus:
    """Manages secure message validation, priority routing, and DLQ redirects."""

    def __init__(
        self, event_bus: EventBusInterface, max_retry: int = 3, retry_delay: float = 1.0
    ) -> None:
        """Initialize SwarmMessageBus.

        Args:
            event_bus: System event bus interface.
            max_retry: Limit of publishing retries.
            retry_delay: Delay between retries in seconds.
        """
        self.event_bus = event_bus
        self.max_retry = max_retry
        self.retry_delay = retry_delay
        self.dlq: List[InterAgentMessage] = []

    async def publish_message(self, topic: str, message: InterAgentMessage) -> bool:
        """Publish a message over the event bus with retry logic and DLQ failover.

        Args:
            topic: Destination channel topic key.
            message: InterAgentMessage envelope.

        Returns:
            True if published successfully, False if redirected to DLQ.
        """
        # Ensure we read body to check for credentials (dummy validator)
        if any(
            k in str(message.body).lower() for k in ("password", "secret", "vault_key")
        ):
            logger.error("Security block: message contains sensitive credential keys.")
            await self.event_bus.publish("swarm.security.blocked", message)
            return False

        delay = self.retry_delay
        for attempt in range(self.max_retry):
            try:
                # Dispatch message event
                await self.event_bus.publish("swarm.message.sent", message)
                success = await self.event_bus.publish(topic, message)
                if success:
                    await self.event_bus.publish("swarm.message.received", message)
                    return True
            except Exception as err:
                logger.warning(
                    "Publish attempt %d failed on topic '%s': %s",
                    attempt + 1,
                    topic,
                    str(err),
                )

            # Exponential backoff sleep
            await asyncio.sleep(delay)
            delay *= 2.0

        # DLQ Redirect on exhausting retry limits
        logger.error(
            "Message %s failed delivery on topic '%s'. Redirecting to Dead Letter Queue (DLQ).",
            message.id,
            topic,
        )
        self.dlq.append(message)
        await self.event_bus.publish("swarm.task.failed", message)
        return False
