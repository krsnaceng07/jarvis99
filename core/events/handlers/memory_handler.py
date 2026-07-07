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

from core.interfaces import InterAgentMessage
from core.memory.memory_coordinator import MemoryCoordinator

logger = logging.getLogger("jarvis.core.events.handlers.memory_handler")


class MemoryEventHandler:
    """Reactive subscriber coordinating memory updates in response to global events."""

    def __init__(self, memory_coordinator: MemoryCoordinator) -> None:
        """Initialize with memory coordinator reference.

        Args:
            memory_coordinator: Memory coordinator singleton.
        """
        self._coordinator = memory_coordinator

    async def handle_workflow_completed(self, message: InterAgentMessage) -> None:
        """Consolidate completed workflow outcomes into EpisodicMemory.

        Args:
            message: Enveloped event payload.
        """
        body = message.body
        graph_id = body.get("graph_id", "unknown")
        success = body.get("success", False)
        logger.info(
            "MemoryEventHandler: workflow.completed event received for '%s' [Success: %s]",
            graph_id,
            success,
        )

        try:
            episode = {
                "type": "workflow_execution",
                "graph_id": graph_id,
                "success": success,
                "completed_nodes": body.get("completed_nodes", []),
                "outputs": body.get("outputs", {}),
                "error": body.get("error"),
                "correlation_id": str(message.correlation_id),
            }
            await self._coordinator.episodic_memory.record_episode(episode)
            logger.info("MemoryEventHandler: successfully archived workflow run episode.")
        except Exception as e:
            logger.error("MemoryEventHandler: failed saving workflow run episode: %s", e)

    async def handle_mission_completed(self, message: InterAgentMessage) -> None:
        """Consolidate finalized mission milestones into SemanticMemory.

        Args:
            message: Enveloped event payload.
        """
        body = message.body
        mission_id = body.get("mission_id", "unknown")
        status = body.get("status", "unknown")
        logger.info(
            "MemoryEventHandler: mission.completed event received for '%s' [Status: %s]",
            mission_id,
            status,
        )

        try:
            fact = {
                "concept": f"mission_{mission_id}",
                "details": f"Durable mission {mission_id} resolved with status: {status}.",
                "mission_id": mission_id,
                "status": status,
                "correlation_id": str(message.correlation_id),
            }
            await self._coordinator.semantic_memory.add_fact(fact)
            logger.info("MemoryEventHandler: successfully archived mission concept fact.")
        except Exception as e:
            logger.error("MemoryEventHandler: failed saving mission fact: %s", e)
