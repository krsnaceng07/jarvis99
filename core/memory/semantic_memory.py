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

logger = logging.getLogger(__name__)


class SemanticMemory:
    """Manages persistent conceptual knowledge, facts, and generalized rules."""

    def __init__(self) -> None:
        self._concepts: List[Dict[str, Any]] = []

    async def add_fact(self, fact: Dict[str, Any]) -> None:
        """Store a semantic fact."""
        logger.info("SemanticMemory adding fact: %s", fact.get("concept"))
        self._concepts.append(fact)

    async def query_facts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Query conceptual facts matching criteria."""
        return [
            fact
            for fact in self._concepts
            if query.lower() in fact.get("concept", "").lower()
            or query.lower() in fact.get("details", "").lower()
        ][:limit]
