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

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


@dataclass
class WorkflowNode:
    """A single step in a workflow DAG."""

    node_id: str
    name: str
    task_type: str  # "tool" | "mission" | "skill" | "llm" | "condition"
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)  # upstream node_ids


class WorkflowGraph:
    """Directed Acyclic Graph of WorkflowNodes.

    Invariant W-1: graph must pass validate() before execution.
    The graph is immutable once execution begins (Invariant W-2).
    """

    def __init__(
        self, graph_id: str, name: str, metadata: Dict[str, Any] | None = None
    ) -> None:
        self.graph_id = graph_id
        self.name = name
        self.nodes: Dict[str, WorkflowNode] = {}
        self.metadata: Dict[str, Any] = metadata or {}

    def add_node(self, node: WorkflowNode) -> None:
        """Register a node in the graph."""
        self.nodes[node.node_id] = node

    def validate(self) -> bool:
        """Assert no cycles and all dependency references exist.

        Returns True if valid; raises ValueError otherwise.
        """
        # Verify all depends_on references exist
        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    raise ValueError(
                        f"Node '{node.node_id}' depends on unknown node '{dep}'."
                    )

        # Detect cycles via DFS coloring (white=0, grey=1, black=2)
        color: Dict[str, int] = {nid: 0 for nid in self.nodes}

        def dfs(nid: str) -> None:
            color[nid] = 1  # grey — being visited
            for dep in self.nodes[nid].depends_on:
                if color[dep] == 1:
                    raise ValueError(f"Cycle detected involving node '{dep}'.")
                if color[dep] == 0:
                    dfs(dep)
            color[nid] = 2  # black — done

        for nid in self.nodes:
            if color[nid] == 0:
                dfs(nid)

        return True

    def get_roots(self) -> List[WorkflowNode]:
        """Return nodes that have no dependencies (execution entry points)."""
        return [n for n in self.nodes.values() if not n.depends_on]

    def get_ready_nodes(self, completed: Set[str]) -> List[WorkflowNode]:
        """Return nodes whose all dependencies are satisfied and not yet completed."""
        ready = []
        for node in self.nodes.values():
            if node.node_id in completed:
                continue
            if all(dep in completed for dep in node.depends_on):
                ready.append(node)
        return ready
