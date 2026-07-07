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

import asyncio
import logging
from typing import Any, Callable, Dict, Optional, Set
from uuid import UUID, uuid4

from core.interfaces import InterAgentMessage
from core.workflow.dag_scheduler import DAGScheduler
from core.workflow.retry_policy import RetryPolicy
from core.workflow.workflow_engine import WorkflowResult
from core.workflow.workflow_graph import WorkflowGraph, WorkflowNode

logger = logging.getLogger(__name__)

# Node handler signature: async fn(node) -> Any
NodeHandler = Callable[[WorkflowNode], Any]


class WorkflowExecutor:
    """Drives asynchronous, parallel wave execution of a WorkflowGraph.

    Responsibilities:
    - Receives ready-node waves from DAGScheduler (no graph traversal here).
    - Executes all nodes in a wave concurrently with asyncio.gather.
    - Applies RetryPolicy per node.
    - Waits for the entire wave to complete before advancing (parallel safety).
    - Maintains thread-safe completed set between waves.
    - Never modifies the graph (Invariant W-2).
    """

    def __init__(
        self,
        scheduler: DAGScheduler,
        retry_policy: Optional[RetryPolicy] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._scheduler = scheduler
        self._retry_policy = retry_policy or RetryPolicy()
        self._event_bus = event_bus
        # Optional per-task-type dispatch table (wired externally)
        self._handlers: Dict[str, NodeHandler] = {}

    def register_handler(self, task_type: str, handler: NodeHandler) -> None:
        """Register an async handler for a specific task_type string."""
        self._handlers[task_type] = handler

    async def _execute_node(
        self,
        node: WorkflowNode,
        outputs: Dict[str, Any],
        lock: asyncio.Lock,
    ) -> None:
        """Execute a single node using its registered handler with retry."""
        handler = self._handlers.get(node.task_type)

        async def run() -> Any:
            if handler is not None:
                return await handler(node)
            # Default: no-op placeholder for unregistered task types
            logger.debug(
                "WorkflowExecutor: no handler for task_type '%s', skipping node '%s'",
                node.task_type,
                node.node_id,
            )
            return None

        result = await self._retry_policy.execute_with_retry(
            fn=run,
            context=node.node_id,
        )

        async with lock:
            outputs[node.node_id] = result

    async def execute(
        self,
        graph: WorkflowGraph,
        initial_completed: Optional[Set[str]] = None,
    ) -> WorkflowResult:
        """Drive the DAG from roots (or checkpoint) to completion.

        Args:
            graph:              The validated WorkflowGraph to execute.
            initial_completed:  Pre-completed node set for checkpoint-resume.

        Returns:
            WorkflowResult with success flag and per-node outputs.
        """
        completed: Set[str] = set(initial_completed or [])
        outputs: Dict[str, Any] = {}
        lock = asyncio.Lock()

        # Publish workflow.started event
        if self._event_bus:
            try:
                try:
                    trace_id = UUID(graph.graph_id)
                except ValueError:
                    trace_id = uuid4()

                msg = InterAgentMessage(
                    sender="workflow_executor",
                    receiver="all",
                    action="workflow.started",
                    body={
                        "graph_id": graph.graph_id,
                        "name": graph.name,
                    },
                    correlation_id=trace_id,
                )
                await self._event_bus.publish("workflow.started", msg)
            except Exception as e:
                logger.error("Failed to publish workflow.started event: %s", e)

        try:
            async for wave in self._scheduler.schedule(graph):
                # Filter out nodes already completed (checkpoint-resume)
                pending_wave = [n for n in wave if n.node_id not in completed]
                if not pending_wave:
                    continue

                logger.info(
                    "WorkflowExecutor: executing wave [%s]",
                    ", ".join(n.node_id for n in pending_wave),
                )

                # Execute all nodes in the wave concurrently
                tasks = [
                    self._execute_node(node, outputs, lock) for node in pending_wave
                ]
                await asyncio.gather(*tasks)

                # Mark the full wave complete after gather (wave-safety)
                for node in pending_wave:
                    completed.add(node.node_id)

        except Exception as exc:
            failed_node = next(
                (nid for nid in graph.nodes if nid not in completed), None
            )
            logger.error(
                "WorkflowExecutor: workflow '%s' failed on node '%s': %s",
                graph.graph_id,
                failed_node,
                exc,
            )

            # Publish workflow.completed event (failure path)
            if self._event_bus:
                try:
                    try:
                        trace_id = UUID(graph.graph_id)
                    except ValueError:
                        trace_id = uuid4()

                    msg = InterAgentMessage(
                        sender="workflow_executor",
                        receiver="all",
                        action="workflow.completed",
                        body={
                            "graph_id": graph.graph_id,
                            "success": False,
                            "completed_nodes": list(completed),
                            "outputs": outputs,
                            "error": str(exc),
                        },
                        correlation_id=trace_id,
                    )
                    await self._event_bus.publish("workflow.completed", msg)
                except Exception as e:
                    logger.error("Failed to publish workflow.completed failed event: %s", e)

            return WorkflowResult(
                graph_id=graph.graph_id,
                success=False,
                completed_nodes=list(completed),
                failed_node=failed_node,
                error=str(exc),
                outputs=outputs,
            )

        # Publish workflow.completed event (success path)
        if self._event_bus:
            try:
                try:
                    trace_id = UUID(graph.graph_id)
                except ValueError:
                    trace_id = uuid4()

                msg = InterAgentMessage(
                    sender="workflow_executor",
                    receiver="all",
                    action="workflow.completed",
                    body={
                        "graph_id": graph.graph_id,
                        "success": True,
                        "completed_nodes": list(completed),
                        "outputs": outputs,
                        "error": None,
                    },
                    correlation_id=trace_id,
                )
                await self._event_bus.publish("workflow.completed", msg)
            except Exception as e:
                logger.error("Failed to publish workflow.completed success event: %s", e)

        return WorkflowResult(
            graph_id=graph.graph_id,
            success=True,
            completed_nodes=list(completed),
            outputs=outputs,
        )
