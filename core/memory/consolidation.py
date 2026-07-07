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
from typing import Any, Dict, List, Optional, Set

from core.memory.episodic_memory import EpisodicMemory
from core.memory.knowledge_graph import KnowledgeGraph
from core.memory.long_term_memory import LongTermMemory
from core.memory.semantic_memory import SemanticMemory

logger = logging.getLogger(__name__)


class MemoryConsolidation:
    """Asynchronous offline aggregator consolidating episodic records.

    Implements the Phase 38 consolidation cycle: recent episodic memory
    records are persisted into long-term storage, distilled into semantic
    facts, and projected into knowledge-graph entity triples.

    When an LLM runtime is provided, uses it to extract richer semantic
    facts and knowledge graph entities from episode content.
    """

    def __init__(
        self,
        episodic_memory: EpisodicMemory,
        long_term_memory: LongTermMemory,
        semantic_memory: SemanticMemory,
        knowledge_graph: KnowledgeGraph,
        llm_runtime: Optional[Any] = None,
    ) -> None:
        self.episodic_memory = episodic_memory
        self.long_term_memory = long_term_memory
        self.semantic_memory = semantic_memory
        self.knowledge_graph = knowledge_graph
        self.llm_runtime = llm_runtime
        self._consolidated: Set[str] = set()

    @staticmethod
    def _fingerprint(episode: Dict[str, Any]) -> str:
        """Build a stable identity for an episode to keep the cycle idempotent."""
        return repr(sorted(episode.items(), key=lambda item: item[0]))

    async def consolidate(self, limit: int = 50) -> Dict[str, int]:
        """Run one consolidation cycle over recent episodic records.

        Each not-yet-consolidated episode is:
        1. Persisted to long-term memory as an experience record.
        2. Distilled into semantic facts (LLM-enhanced when available).
        3. Projected into knowledge-graph entity triples.
        4. Entity extraction from content for richer KG.

        Returns aggregate counters for the cycle.
        """
        stats: Dict[str, int] = {
            "episodes_processed": 0,
            "facts_created": 0,
            "entities_created": 0,
            "relations_created": 0,
        }

        episodes: List[Dict[str, Any]] = await self.episodic_memory.get_recent_episodes(
            limit=limit
        )
        for episode in episodes:
            fingerprint = self._fingerprint(episode)
            if fingerprint in self._consolidated:
                continue
            self._consolidated.add(fingerprint)

            await self.long_term_memory.save_experience(dict(episode))

            mission_id = str(episode.get("mission_id", "") or "")
            goal = str(episode.get("goal", "") or "")
            outcome = str(episode.get("outcome", "") or "unknown")
            content = str(episode.get("content", "") or "")

            if goal:
                fact = await self._distill_fact(goal, outcome, content)
                await self.semantic_memory.add_fact(fact)
                stats["facts_created"] += 1

            if mission_id:
                await self.knowledge_graph.add_entity(
                    mission_id, "mission", {"outcome": outcome}
                )
                stats["entities_created"] += 1
                if goal:
                    await self.knowledge_graph.add_entity(goal, "goal", {})
                    stats["entities_created"] += 1
                    await self.knowledge_graph.add_relation(
                        mission_id, goal, "PURSUED_GOAL"
                    )
                    stats["relations_created"] += 1

                    if outcome == "SUCCESS":
                        await self.knowledge_graph.add_relation(
                            mission_id, goal, "COMPLETED"
                        )
                        stats["relations_created"] += 1
                    elif outcome in ("FAILED", "ERROR"):
                        await self.knowledge_graph.add_relation(
                            mission_id, goal, "FAILED_AT"
                        )
                        stats["relations_created"] += 1

            entities = await self._extract_entities(goal, content)
            for entity in entities:
                await self.knowledge_graph.add_entity(
                    entity["name"], entity.get("type", "concept"), {}
                )
                stats["entities_created"] += 1
                if goal:
                    await self.knowledge_graph.add_relation(
                        goal, entity["name"], entity.get("relation", "related_to")
                    )
                    stats["relations_created"] += 1

            stats["episodes_processed"] += 1

        logger.info(
            "MemoryConsolidation cycle complete: %d episodes processed.",
            stats["episodes_processed"],
        )
        return stats

    async def _distill_fact(
        self, goal: str, outcome: str, content: str,
    ) -> Dict[str, Any]:
        """Distill an episode into a semantic fact."""
        if self.llm_runtime is not None and content:
            try:
                from core.tools.llm_runtime import LlmRequest

                request = LlmRequest(
                    prompt=(
                        f"Distill this experience into a single reusable fact:\n"
                        f"Goal: {goal}\nOutcome: {outcome}\n"
                        f"Details: {content[:500]}\n\n"
                        f"Return ONE sentence capturing the key lesson or pattern."
                    ),
                    system_prompt="You are a knowledge distillation engine. Be concise.",
                    category="reasoning",
                    max_tokens=100,
                    temperature=0.0,
                )
                response = await self.llm_runtime.generate(request)
                if response.text and not response.error:
                    return {
                        "concept": goal,
                        "details": response.text.strip(),
                        "outcome": outcome,
                    }
            except Exception as e:
                logger.debug("LLM fact distillation failed: %s", e)

        return {"concept": goal, "details": f"Episode outcome: {outcome}"}

    async def _extract_entities(
        self, goal: str, content: str,
    ) -> List[Dict[str, str]]:
        """Extract entities and relationships from episode content."""
        if not content:
            return []
        if self.llm_runtime is None:
            return self._heuristic_entities(goal)

        try:
            import json

            from core.tools.llm_runtime import LlmRequest

            request = LlmRequest(
                prompt=(
                    f"Extract key entities from this goal and context:\n"
                    f"Goal: {goal}\nContext: {content[:500]}\n\n"
                    f"Return a JSON array of objects with 'name', 'type' "
                    f"(concept/tool/technology/skill), and 'relation' "
                    f"(uses/requires/produces/depends_on).\n"
                    f"Max 5 entities. Return ONLY valid JSON."
                ),
                system_prompt="Output ONLY valid JSON. No markdown.",
                category="reasoning",
                max_tokens=300,
                temperature=0.0,
            )
            response = await self.llm_runtime.generate(request)
            if response.text and not response.error:
                text = response.text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                entities = json.loads(text)
                if isinstance(entities, list):
                    return [
                        {
                            "name": e.get("name", ""),
                            "type": e.get("type", "concept"),
                            "relation": e.get("relation", "related_to"),
                        }
                        for e in entities[:5]
                        if e.get("name")
                    ]
        except Exception as e:
            logger.debug("LLM entity extraction failed: %s", e)

        return self._heuristic_entities(goal)

    @staticmethod
    def _heuristic_entities(goal: str) -> List[Dict[str, str]]:
        """Simple keyword extraction as fallback."""
        import re

        words = re.findall(r"[A-Z][a-z]+|[a-z]{4,}", goal)
        seen: Set[str] = set()
        entities: List[Dict[str, str]] = []
        for w in words:
            lower = w.lower()
            if lower not in seen and lower not in (
                "create", "build", "make", "write", "implement", "deploy",
                "test", "check", "find", "search", "that", "this", "with",
            ):
                seen.add(lower)
                entities.append({
                    "name": lower, "type": "concept", "relation": "related_to",
                })
            if len(entities) >= 3:
                break
        return entities
