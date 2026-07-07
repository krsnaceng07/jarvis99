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

import logging
from typing import AsyncIterator, List, Set

from core.workflow.workflow_graph import WorkflowGraph, WorkflowNode

logger = logging.getLogger(__name__)


class DAGScheduler:
    """Produces parallel waves of WorkflowNodes via topological sort.

    Each call to schedule() yields a list (wave) of nodes that can run
    concurrently — all their dependencies in prior waves are complete.

    Invariant W-2: a node is never yielded before all its depends_on appear
    in a prior wave.
    """

    async def schedule(self, graph: WorkflowGraph) -> AsyncIterator[List[WorkflowNode]]:
        """Yield waves of nodes that can run in parallel."""
        completed: Set[str] = set()
        remaining = set(graph.nodes.keys())

        while remaining:
            wave = [
                graph.nodes[nid]
                for nid in remaining
                if all(dep in completed for dep in graph.nodes[nid].depends_on)
            ]

            if not wave:
                # No progress — should never happen on a validated DAG
                raise RuntimeError(
                    "DAGScheduler stalled: no nodes ready but remaining set non-empty. "
                    "Ensure graph.validate() was called before scheduling."
                )

            # Sort by node_id for deterministic ordering of equal-priority nodes
            wave.sort(key=lambda n: n.node_id)

            logger.info(
                "DAGScheduler wave: [%s]",
                ", ".join(n.node_id for n in wave),
            )

            yield wave

            for node in wave:
                completed.add(node.node_id)
                remaining.discard(node.node_id)
