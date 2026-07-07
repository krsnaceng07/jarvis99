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


class EpisodicMemory:
    """Manages sequential execution journals, tool outcomes, and run snapshots."""

    def __init__(self) -> None:
        self._episodes: List[Dict[str, Any]] = []

    async def record_episode(self, episode: Dict[str, Any]) -> None:
        """Store a new execution episode record."""
        logger.info("EpisodicMemory recording new episode.")
        self._episodes.append(episode)

    async def get_recent_episodes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve recent execution episodes."""
        return self._episodes[-limit:]
