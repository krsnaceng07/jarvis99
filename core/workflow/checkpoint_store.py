"""
PHASE: 39
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/101_PHASE_39_WORKFLOW_GRAPH_ENGINE_SPECIFICATION.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import logging
from typing import Any, Dict, Optional

from core.memory.working_memory import WorkingMemory

logger = logging.getLogger(__name__)

# Namespace prefix used to isolate workflow checkpoints in WorkingMemory
_CHECKPOINT_PREFIX = "__workflow_checkpoint__"


class CheckpointStore:
    """Persists and restores mid-workflow execution state via UnifiedMemory.

    Invariant W-4: CheckpointStore writes only through UnifiedMemory
    (specifically WorkingMemory). It never writes directly to any database.

    Checkpoint schema stored per graph_id:
        {
            "graph_id": str,
            "completed_nodes": List[str],
            "outputs": Dict[str, Any],
        }
    """

    def __init__(self, working_memory: WorkingMemory) -> None:
        self._memory = working_memory

    def _key(self, graph_id: str) -> str:
        """Return the namespaced key used in WorkingMemory."""
        return f"{_CHECKPOINT_PREFIX}{graph_id}"

    async def save(self, graph_id: str, state: Dict[str, Any]) -> None:
        """Persist the workflow checkpoint for graph_id.

        Args:
            graph_id: The workflow graph identifier.
            state:    Dict containing at minimum:
                      - "completed_nodes": List[str]
                      - "outputs": Dict[str, Any]
        """
        payload: Dict[str, Any] = {
            "graph_id": graph_id,
            **state,
        }
        self._memory.set(self._key(graph_id), payload)
        logger.info(
            "CheckpointStore.save: checkpoint written for graph '%s' "
            "(%d completed nodes).",
            graph_id,
            len(state.get("completed_nodes", [])),
        )

    async def load(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve saved checkpoint for graph_id.

        Returns:
            The checkpoint dict, or None if no checkpoint exists.
        """
        result: Optional[Dict[str, Any]] = self._memory.get(self._key(graph_id))
        if result is None:
            logger.debug(
                "CheckpointStore.load: no checkpoint found for graph '%s'.",
                graph_id,
            )
        else:
            logger.info(
                "CheckpointStore.load: checkpoint restored for graph '%s' "
                "(%d completed nodes).",
                graph_id,
                len(result.get("completed_nodes", [])),
            )
        return result

    async def delete(self, graph_id: str) -> None:
        """Remove a checkpoint after successful workflow completion."""
        key = self._key(graph_id)
        if self._memory.get(key) is not None:
            self._memory.set(key, None)
            logger.info(
                "CheckpointStore.delete: checkpoint cleared for graph '%s'.",
                graph_id,
            )
