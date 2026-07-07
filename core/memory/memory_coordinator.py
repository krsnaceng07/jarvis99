"""
PHASE: 38
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/100_PHASE_38_UNIFIED_MEMORY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/PHASE_38_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import logging
from typing import Any, Dict, List

from core.memory.episodic_memory import EpisodicMemory
from core.memory.knowledge_graph import KnowledgeGraph
from core.memory.long_term_memory import LongTermMemory
from core.memory.procedural_memory import ProceduralMemory
from core.memory.semantic_memory import SemanticMemory
from core.memory.working_memory import WorkingMemory

logger = logging.getLogger(__name__)


class MemoryCoordinator:
    """Orchestrates memory retrieval priorities, confidence ranking, and graph lookups."""

    def __init__(
        self,
        working_memory: WorkingMemory,
        long_term_memory: LongTermMemory,
        knowledge_graph: KnowledgeGraph,
        episodic_memory: EpisodicMemory,
        semantic_memory: SemanticMemory,
        procedural_memory: ProceduralMemory,
    ) -> None:
        self.working_memory = working_memory
        self.long_term_memory = long_term_memory
        self.knowledge_graph = knowledge_graph
        self.episodic_memory = episodic_memory
        self.semantic_memory = semantic_memory
        self.procedural_memory = procedural_memory

    async def retrieve_context(self, query: str) -> Dict[str, Any]:
        """Sequence, query, rank, and traverse memory modules for context assembly."""
        logger.info(
            "MemoryCoordinator executing sequential retrieval for query: %s", query
        )

        # 1. Working Memory
        working_data = self.working_memory.export() if self.working_memory else {}

        # 2. Knowledge Graph traversal
        graph_entities = self.knowledge_graph.nodes if self.knowledge_graph else []

        # 3. Semantic Memory & Long-Term Memory search
        semantic_facts = (
            await self.semantic_memory.query_facts(query, limit=3)
            if self.semantic_memory
            else []
        )
        long_term_records = (
            await self.long_term_memory.search_semantic(query, limit=3)
            if self.long_term_memory
            else []
        )
        recent_episodes = (
            await self.episodic_memory.get_recent_episodes(limit=3)
            if self.episodic_memory
            else []
        )

        # 4. Rank results with confidence/relevance metadata
        ranked_memories: List[Dict[str, Any]] = []
        for fact in semantic_facts:
            ranked_memories.append(
                {
                    "type": "semantic_fact",
                    "content": fact,
                    "confidence": 0.90,
                    "relevance": 0.95,
                }
            )
        for record in long_term_records:
            ranked_memories.append(
                {
                    "type": "long_term_record",
                    "content": record,
                    "confidence": 0.85,
                    "relevance": 0.80,
                }
            )

        return {
            "working_memory": working_data,
            "ranked_memories": ranked_memories,
            "episodic_episodes": recent_episodes,
            "graph_entities_count": len(graph_entities),
        }
