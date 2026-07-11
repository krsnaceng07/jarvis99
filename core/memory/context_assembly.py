"""
PHASE: 38
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/100_PHASE_38_UNIFIED_MEMORY_SPECIFICATION.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import logging
from typing import Any, Dict, Optional

from core.memory.memory_coordinator import MemoryCoordinator

logger = logging.getLogger(__name__)


class ContextAssembly:
    """Façade assembling context from multiple memory subsystems for the BrainKernel."""

    def __init__(
        self,
        memory_coordinator: MemoryCoordinator,
        memory_orchestrator: Optional[Any] = None,
    ) -> None:
        self.memory_coordinator = memory_coordinator
        self.memory_orchestrator = memory_orchestrator

    async def assemble_context(self, query: str) -> Dict[str, Any]:
        """Aggregate Working, Episodic, Semantic, Procedural, and Graph details into unified context."""
        logger.info("ContextAssembly delegating to MemoryCoordinator.")
        coordinated_data = await self.memory_coordinator.retrieve_context(query)

        result: Dict[str, Any] = {
            "query": query,
            "working_memory": coordinated_data.get("working_memory", {}),
            "ranked_memories": coordinated_data.get("ranked_memories", []),
            "episodic_memory": coordinated_data.get("episodic_episodes", []),
            "knowledge_graph_entities_count": coordinated_data.get(
                "graph_entities_count", 0
            ),
        }

        # Phase 19 — enrich with scored retrieval from MemoryOrchestrator
        if self.memory_orchestrator:
            try:
                from core.memory.dto import RetrievalRequest

                request = RetrievalRequest(query=query, max_chunks=10, min_score=0.0)
                response = await self.memory_orchestrator.recall(request)
                scored_memories = [
                    {
                        "memory_id": str(c.memory_id),
                        "content": c.content,
                        "content_hash": c.content_hash,
                    }
                    for c in response.chunks
                ]
                result["scored_memories"] = scored_memories
                result["scored_memory_count"] = len(scored_memories)
            except Exception as e:
                logger.debug("Phase 19 scored recall in ContextAssembly skipped: %s", e)

        return result
