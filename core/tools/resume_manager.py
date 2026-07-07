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

import time
from datetime import datetime, timezone

from core.interfaces import EventBusInterface, InterAgentMessage
from core.memory.database import db_manager
from core.tools.execution_repository import ExecutionRepository


class ResumeManager:
    """Scans and recovers stale active execution runs during system startup."""

    def __init__(
        self,
        repository: ExecutionRepository,
        event_bus: EventBusInterface,
    ) -> None:
        """Initialize the ResumeManager.

        Args:
            repository: ExecutionRepository instance.
            event_bus: EventBusInterface.
        """
        self.repository = repository
        self.event_bus = event_bus

    async def resume_all(self) -> None:
        """Scan both agent runs and workflow executions and clean up stale states."""
        async with db_manager.session() as session:
            async with session.begin():
                # 1. Recover active agent runs stuck in Planning/Executing
                active_agent_ids = await self.repository.get_active_agent_run_ids(
                    session
                )
                for run_id in active_agent_ids:
                    await self.repository.update_agent_run_state(
                        run_id=run_id,
                        state="Failed",
                        session=session,
                        failure_type="TimeoutFailure",
                    )
                    # Broadcast transition event
                    msg = InterAgentMessage(
                        sender="resume_manager",
                        receiver="*",
                        action="engine.state.transition",
                        correlation_id=run_id,
                        body={
                            "state": "Failed",
                            "failure_type": "TimeoutFailure",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "run_id": str(run_id),
                        },
                    )
                    await self.event_bus.publish("engine.state.transition", msg)

                # 2. Recover active workflow executions stuck in RUNNING
                active_workflow_ids = await self.repository.get_active_workflow_run_ids(
                    session
                )
                for exec_id in active_workflow_ids:
                    await self.repository.update_workflow_execution(
                        execution_id=exec_id,
                        state="FAILED",
                        session=session,
                    )
                    # Fail active steps of this execution
                    steps = await self.repository.get_step_executions(exec_id, session)
                    for step in steps:
                        if step.state == "RUNNING":
                            await self.repository.save_step_execution(
                                execution_id=exec_id,
                                step_name=step.step_name,
                                state="FAILED",
                                attempts=step.attempts,
                                error={"error": "System interrupted during execution"},
                                session=session,
                            )
                            # Broadcast step failed event
                            step_failed_msg = InterAgentMessage(
                                sender="resume_manager",
                                receiver="*",
                                action="workflow.step.failed",
                                correlation_id=exec_id,
                                body={
                                    "step_name": step.step_name,
                                    "state": "FAILED",
                                    "error": "System interrupted during execution",
                                    "timestamp": time.time(),
                                    "run_id": str(exec_id),
                                },
                            )
                            await self.event_bus.publish(
                                "workflow.step.failed", step_failed_msg
                            )

                    # Broadcast workflow completed (FAILED) event
                    wf_failed_msg = InterAgentMessage(
                        sender="resume_manager",
                        receiver="*",
                        action="workflow.completed",
                        correlation_id=exec_id,
                        body={
                            "state": "FAILED",
                            "timestamp": time.time(),
                            "run_id": str(exec_id),
                        },
                    )
                    await self.event_bus.publish("workflow.completed", wf_failed_msg)
