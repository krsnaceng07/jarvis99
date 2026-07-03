"""
PHASE: 15
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/77_PHASE_15_PERSISTENT_EXECUTION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import contextvars
from typing import Dict, Optional
from uuid import UUID

from core.interfaces import EventBusInterface, InterAgentMessage, LifecycleInterface
from core.memory.database import db_manager
from core.tools.execution_repository import ExecutionRepository

# Context variable to correlate the API run_id to the engine's trace_id
active_run_id: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar(
    "active_run_id", default=None
)


class PersistenceService(LifecycleInterface):
    """Listens to EventBus execution telemetry and persists state changes to the database."""

    def __init__(
        self,
        repository: ExecutionRepository,
        event_bus: EventBusInterface,
    ) -> None:
        """Initialize the PersistenceService.

        Args:
            repository: ExecutionRepository instance.
            event_bus: EventBus Interface.
        """
        self.repository = repository
        self.event_bus = event_bus
        self._trace_to_run_map: Dict[UUID, UUID] = {}

    async def initialize(self) -> None:
        """Subscribe to all execution and workflow telemetry events on the EventBus."""
        await self.event_bus.subscribe(
            "engine.state.transition", self.handle_engine_transition
        )
        await self.event_bus.subscribe("workflow.started", self.handle_workflow_started)
        await self.event_bus.subscribe(
            "workflow.completed", self.handle_workflow_completed
        )
        await self.event_bus.subscribe(
            "workflow.step.started", self.handle_step_started
        )
        await self.event_bus.subscribe(
            "workflow.step.completed", self.handle_step_completed
        )
        await self.event_bus.subscribe("workflow.step.failed", self.handle_step_failed)

    async def handle_engine_transition(self, msg: InterAgentMessage) -> None:
        """Process agent execution transition events."""
        trace_id = msg.correlation_id
        body = msg.body or {}
        state = body.get("state")
        if not state:
            return

        run_id = active_run_id.get()
        if run_id:
            self._trace_to_run_map[trace_id] = run_id
        else:
            run_id = self._trace_to_run_map.get(trace_id, trace_id)

        async with db_manager.session() as session:
            async with session.begin():
                await self.repository.update_agent_run_state(
                    run_id=run_id,
                    state=state,
                    session=session,
                )

    async def handle_workflow_started(self, msg: InterAgentMessage) -> None:
        """Process workflow execution starting events."""
        execution_id = msg.correlation_id
        body = msg.body or {}
        workflow_id_str = body.get("workflow_id")
        state = body.get("state", "RUNNING")
        if not workflow_id_str:
            return

        try:
            workflow_id = UUID(workflow_id_str)
        except ValueError:
            return

        async with db_manager.session() as session:
            async with session.begin():
                # Resolve active version of workflow or default to 1
                from core.tools.repository import WorkflowRepository

                wf_repo = WorkflowRepository()
                plan = await wf_repo.get(workflow_id, session)
                version = plan.version if plan else 1

                await self.repository.save_workflow_execution(
                    execution_id=execution_id,
                    workflow_id=workflow_id,
                    version=version,
                    state=state,
                    session=session,
                )

    async def handle_workflow_completed(self, msg: InterAgentMessage) -> None:
        """Process workflow execution completed events."""
        execution_id = msg.correlation_id
        body = msg.body or {}
        state = body.get("state")
        metrics = body.get("metrics")
        if not state:
            return

        async with db_manager.session() as session:
            async with session.begin():
                await self.repository.update_workflow_execution(
                    execution_id=execution_id,
                    state=state,
                    metrics=metrics,
                    session=session,
                )

    async def handle_step_started(self, msg: InterAgentMessage) -> None:
        """Process step execution started events."""
        execution_id = msg.correlation_id
        body = msg.body or {}
        step_name = body.get("step_name")
        state = body.get("state")
        if not step_name or not state:
            return

        async with db_manager.session() as session:
            async with session.begin():
                await self.repository.save_step_execution(
                    execution_id=execution_id,
                    step_name=step_name,
                    state=state,
                    attempts=1,
                    session=session,
                )

    async def handle_step_completed(self, msg: InterAgentMessage) -> None:
        """Process step execution success completion events."""
        execution_id = msg.correlation_id
        body = msg.body or {}
        step_name = body.get("step_name")
        state = body.get("state")
        output = body.get("output")
        if not step_name or not state:
            return

        async with db_manager.session() as session:
            async with session.begin():
                await self.repository.save_step_execution(
                    execution_id=execution_id,
                    step_name=step_name,
                    state=state,
                    attempts=1,
                    output=output,
                    session=session,
                )

    async def handle_step_failed(self, msg: InterAgentMessage) -> None:
        """Process step execution failed events."""
        execution_id = msg.correlation_id
        body = msg.body or {}
        step_name = body.get("step_name")
        state = body.get("state")
        error_msg = body.get("error")
        if not step_name or not state:
            return

        error = {"error": error_msg} if error_msg else None

        async with db_manager.session() as session:
            async with session.begin():
                await self.repository.save_step_execution(
                    execution_id=execution_id,
                    step_name=step_name,
                    state=state,
                    attempts=1,
                    error=error,
                    session=session,
                )

    async def start(self) -> None:
        """Start the PersistenceService."""
        pass

    async def stop(self) -> None:
        """Stop the PersistenceService."""
        pass

    async def shutdown(self) -> None:
        """Shutdown the PersistenceService."""
        pass
