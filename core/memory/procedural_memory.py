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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProceduralMemory:
    """Manages reusable execution plans, skill recipes, and logic workflows."""

    def __init__(self) -> None:
        self._procedures: List[Dict[str, Any]] = []

    async def register_procedure(self, name: str, steps: List[str]) -> None:
        """Register a procedural workflow sequence."""
        logger.info("ProceduralMemory registering procedure: %s", name)
        self._procedures.append({"name": name, "steps": steps})

    async def get_procedure(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific procedure by name."""
        for proc in self._procedures:
            if proc["name"] == name:
                return proc
        return None
