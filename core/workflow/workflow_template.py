"""
PHASE: 39
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/101_PHASE_39_WORKFLOW_GRAPH_ENGINE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/PHASE_39_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import copy
import logging
from typing import Any, Dict, Optional

from core.memory.procedural_memory import ProceduralMemory
from core.workflow.workflow_graph import WorkflowGraph, WorkflowNode

logger = logging.getLogger(__name__)


class WorkflowTemplate:
    """Named, reusable workflow pattern stored in ProceduralMemory.

    Invariant W-6: WorkflowTemplate reads and writes exclusively via
    ProceduralMemory. It stores workflow definitions only — never
    runtime execution state.

    Template schema stored in ProceduralMemory:
        name:  str  (template name, acts as the procedure name)
        steps: List[Dict]  (serialised WorkflowNode descriptors)
        meta:  Dict[str, Any]  (optional versioning / description)
    """

    def __init__(self, procedural_memory: ProceduralMemory) -> None:
        self._memory = procedural_memory

    async def register(self, name: str, graph: WorkflowGraph) -> None:
        """Serialise and store graph as a named template in ProceduralMemory.

        The template captures node definitions at registration time.
        Runtime state is never persisted here.

        Args:
            name:  Human-readable template name (e.g. "deployment-pipeline").
            graph: The WorkflowGraph whose structure becomes the template.
        """
        steps = [
            {
                "node_id": node.node_id,
                "name": node.name,
                "task_type": node.task_type,
                "parameters": copy.deepcopy(node.parameters),
                "depends_on": list(node.depends_on),
            }
            for node in graph.nodes.values()
        ]
        await self._memory.register_procedure(
            name,
            steps,  # type: ignore[arg-type]
        )
        logger.info(
            "WorkflowTemplate.register: stored template '%s' (%d nodes).",
            name,
            len(steps),
        )

    async def instantiate(
        self,
        name: str,
        parameters: Optional[Dict[str, Any]] = None,
        graph_id: Optional[str] = None,
    ) -> Optional[WorkflowGraph]:
        """Create a runtime WorkflowGraph from a registered template.

        Args:
            name:       Name of the registered template.
            parameters: Per-instantiation parameter overrides merged into
                        each node's parameters dict (shallow merge).
            graph_id:   Optional graph_id for the new instance; defaults to
                        "<name>-instance".

        Returns:
            A new WorkflowGraph, or None if the template is not found.
        """
        proc = await self._memory.get_procedure(name)
        if proc is None:
            logger.warning(
                "WorkflowTemplate.instantiate: template '%s' not found.", name
            )
            return None

        overrides = parameters or {}
        instance_id = graph_id or f"{name}-instance"
        graph = WorkflowGraph(graph_id=instance_id, name=name)

        for step in proc["steps"]:
            merged_params: Dict[str, Any] = {**step["parameters"], **overrides}
            node = WorkflowNode(
                node_id=step["node_id"],
                name=step["name"],
                task_type=step["task_type"],
                parameters=merged_params,
                depends_on=list(step["depends_on"]),
            )
            graph.add_node(node)

        logger.info(
            "WorkflowTemplate.instantiate: created graph '%s' from template '%s'.",
            instance_id,
            name,
        )
        return graph

    async def list_templates(self) -> list[str]:
        """Return names of all registered workflow templates."""
        procedures = getattr(self._memory, "_procedures", [])
        if isinstance(procedures, list):
            return [p["name"] for p in procedures if "name" in p]
        # Fallback for dict-keyed storage
        return list(procedures.keys())
