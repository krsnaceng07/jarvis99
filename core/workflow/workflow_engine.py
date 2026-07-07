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
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from core.workflow.dag_scheduler import DAGScheduler
from core.workflow.workflow_graph import WorkflowGraph

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """Outcome of a workflow execution."""

    graph_id: str
    success: bool
    completed_nodes: list[str] = field(default_factory=list)
    failed_node: Optional[str] = None
    error: Optional[str] = None
    outputs: Dict[str, Any] = field(default_factory=dict)


class WorkflowEngine:
    """Single public façade for the Workflow Graph Engine.

    Invariant W-5: WorkflowEngine is the only class exposed outside
    core/workflow/. External callers access only:
        run()
        resume()
        register_template()
        status()
        cancel()

    All scheduling, execution, retry, checkpointing, and template management
    are coordinated internally; sub-components are never exposed to callers.
    """

    def __init__(self, scheduler: DAGScheduler) -> None:
        self._scheduler = scheduler
        self._executor: Any = None
        self._checkpoint_store: Any = None
        self._template_registry: Any = None
        # In-memory cancellation flags  {graph_id: bool}
        self._cancelled: Dict[str, bool] = {}

    # ── Setter injection (called by kernel during boot) ─────────────────────

    def set_executor(self, executor: Any) -> None:
        """Wire the WorkflowExecutor (M2)."""
        self._executor = executor

    def set_checkpoint_store(self, store: Any) -> None:
        """Wire the CheckpointStore (M3)."""
        self._checkpoint_store = store

    def set_template_registry(self, registry: Any) -> None:
        """Wire the WorkflowTemplate registry (M3)."""
        self._template_registry = registry

    # ── Public API ───────────────────────────────────────────────────────────

    async def run(self, graph: WorkflowGraph) -> WorkflowResult:
        """Validate and execute a workflow graph.

        Saves a checkpoint after each wave so resume() can continue from
        the last safe point on failure.

        Args:
            graph: A WorkflowGraph. Must pass validate() (W-1).
        """
        logger.info("WorkflowEngine.run() called for graph '%s'", graph.graph_id)

        # Invariant W-1: validate before execution
        graph.validate()

        self._cancelled[graph.graph_id] = False

        if self._executor is not None:
            result = await self._executor.execute(graph)
            # Persist final checkpoint so resume() has context after completion
            await self._save_checkpoint(
                graph.graph_id,
                result.completed_nodes,
                result.outputs,
            )
            return result

        # Skeleton dry-run (no executor wired — should not occur in production)
        completed: list[str] = []
        async for wave in self._scheduler.schedule(graph):
            for node in wave:
                completed.append(node.node_id)
            await self._save_checkpoint(graph.graph_id, completed, {})

        return WorkflowResult(
            graph_id=graph.graph_id,
            success=True,
            completed_nodes=completed,
        )

    async def resume(self, graph: WorkflowGraph) -> WorkflowResult:
        """Resume a workflow from its last checkpoint.

        Guarantees:
        - Completed nodes are never re-executed (deterministic resume).
        - Execution continues from the first pending ready node.

        Args:
            graph: The same WorkflowGraph that was originally run.
        """
        logger.info("WorkflowEngine.resume() called for graph '%s'", graph.graph_id)

        if self._checkpoint_store is None:
            return WorkflowResult(
                graph_id=graph.graph_id,
                success=False,
                error="CheckpointStore not configured.",
            )

        state = await self._checkpoint_store.load(graph.graph_id)
        if state is None:
            return WorkflowResult(
                graph_id=graph.graph_id,
                success=False,
                error=f"No checkpoint found for graph '{graph.graph_id}'.",
            )

        already_done: Set[str] = set(state.get("completed_nodes", []))
        prior_outputs: Dict[str, Any] = state.get("outputs", {})

        logger.info(
            "WorkflowEngine.resume: restoring %d completed nodes for graph '%s'.",
            len(already_done),
            graph.graph_id,
        )

        # Validate before resuming — graph must still be a valid DAG (W-1)
        graph.validate()

        if self._executor is not None:
            result = await self._executor.execute(graph, initial_completed=already_done)
            # Merge prior outputs with new outputs
            merged_outputs = {**prior_outputs, **result.outputs}
            await self._save_checkpoint(
                graph.graph_id,
                result.completed_nodes,
                merged_outputs,
            )
            result.outputs = merged_outputs
            return result

        # Dry-run resume skeleton
        return WorkflowResult(
            graph_id=graph.graph_id,
            success=True,
            completed_nodes=list(already_done),
            outputs=prior_outputs,
        )

    async def register_template(self, name: str, graph: WorkflowGraph) -> None:
        """Store graph as a named, reusable workflow template.

        Args:
            name:  Template identifier (e.g. "deployment-pipeline").
            graph: The WorkflowGraph whose structure becomes the template.
        """
        if self._template_registry is None:
            logger.warning(
                "WorkflowEngine.register_template: template registry not configured."
            )
            return
        await self._template_registry.register(name, graph)

    def status(self, graph_id: str) -> Dict[str, Any]:
        """Return lightweight execution metadata for a workflow.

        Returns a dict with keys: graph_id, cancelled.
        Extended status (completed_nodes) requires CheckpointStore.
        """
        return {
            "graph_id": graph_id,
            "cancelled": self._cancelled.get(graph_id, False),
        }

    def cancel(self, graph_id: str) -> None:
        """Signal that a workflow should be cancelled.

        Sets the cancellation flag; the executor checks this flag
        between waves in future implementations.
        """
        self._cancelled[graph_id] = True
        logger.info("WorkflowEngine.cancel() flagged for graph '%s'.", graph_id)

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _save_checkpoint(
        self,
        graph_id: str,
        completed_nodes: list[str],
        outputs: Dict[str, Any],
    ) -> None:
        """Persist a checkpoint through CheckpointStore if configured."""
        if self._checkpoint_store is None:
            return
        await self._checkpoint_store.save(
            graph_id,
            {"completed_nodes": completed_nodes, "outputs": outputs},
        )
