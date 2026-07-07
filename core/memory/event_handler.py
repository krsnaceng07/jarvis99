"""JARVIS OS - Phase 19 Memory Event Handler.

Subscribes to frozen memory event topics (spec §2.4) and handles them:
- Logs all memory lifecycle events for observability
- Updates WorkingMemory cache on create/delete/promote

PHASE: 19
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md
"""

import logging
from typing import Any, Optional

from core.interfaces import EventBusInterface, InterAgentMessage

logger = logging.getLogger(__name__)


class MemoryEventHandler:
    """Handles Phase 19 frozen memory event topics."""

    def __init__(
        self,
        event_bus: EventBusInterface,
        working_memory: Optional[Any] = None,
    ) -> None:
        self.event_bus = event_bus
        self.working_memory = working_memory

    async def initialize(self) -> None:
        """Subscribe to all frozen memory event topics."""
        topics = [
            ("memory.created", self._on_memory_created),
            ("memory.updated", self._on_memory_updated),
            ("memory.promoted", self._on_memory_promoted),
            ("memory.archived", self._on_memory_archived),
            ("memory.deleted", self._on_memory_deleted),
            ("memory.retrieved", self._on_memory_retrieved),
            ("memory.reflected", self._on_memory_reflected),
            ("memory.indexed", self._on_memory_indexed),
        ]
        for topic, handler in topics:
            try:
                await self.event_bus.subscribe(topic, handler)
            except Exception as e:
                logger.debug("Could not subscribe to %s: %s", topic, e)

    async def _on_memory_created(self, msg: InterAgentMessage) -> None:
        chunk_id = msg.body.get("chunk_id", "?")
        logger.info("Memory created: %s", chunk_id)
        if self.working_memory and hasattr(self.working_memory, "add"):
            try:
                self.working_memory.add(
                    f"memory:{chunk_id}",
                    {"event": "created", "chunk_id": chunk_id},
                )
            except Exception:
                pass

    async def _on_memory_updated(self, msg: InterAgentMessage) -> None:
        logger.info("Memory updated: %s", msg.body.get("chunk_id", "?"))

    async def _on_memory_promoted(self, msg: InterAgentMessage) -> None:
        chunk_id = msg.body.get("chunk_id", "?")
        target = msg.body.get("target_tier", "?")
        logger.info("Memory promoted: %s → %s", chunk_id, target)

    async def _on_memory_archived(self, msg: InterAgentMessage) -> None:
        logger.info("Memory archived: %s", msg.body.get("chunk_id", "?"))

    async def _on_memory_deleted(self, msg: InterAgentMessage) -> None:
        chunk_id = msg.body.get("chunk_id", "?")
        logger.info("Memory deleted: %s", chunk_id)
        if self.working_memory and hasattr(self.working_memory, "remove"):
            try:
                self.working_memory.remove(f"memory:{chunk_id}")
            except Exception:
                pass

    async def _on_memory_retrieved(self, msg: InterAgentMessage) -> None:
        logger.debug("Memory retrieved: %s", msg.body.get("chunk_id", "?"))

    async def _on_memory_reflected(self, msg: InterAgentMessage) -> None:
        logger.info("Memory reflected: %s", msg.body.get("chunk_id", "?"))

    async def _on_memory_indexed(self, msg: InterAgentMessage) -> None:
        logger.debug("Memory indexed: %s", msg.body.get("chunk_id", "?"))
