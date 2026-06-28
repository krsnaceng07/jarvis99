"""JARVIS OS - Workflow Orchestrator.

Manages the execution loop for compiled workflows, resolving step output bindings dynamically,
handling step failures according to recovery policies, and emitting lifecycle events.
"""

import asyncio
import time
from typing import Any, Dict
from uuid import UUID, uuid4

from core.interfaces import EventBusInterface, InterAgentMessage
from core.reasoning.orchestrator import ExecutionOrchestrator
from core.reasoning.planner import ReasoningSession
from core.tools.validator import ANY_TEMPLATE_PATTERN, VAR_PATTERN
from core.tools.workflow_dto import (
    CompiledWorkflow,
    RecoveryPolicy,
    WorkflowMetrics,
    WorkflowState,
    WorkflowStep,
    WorkflowStepState,
)


class WorkflowOrchestrator:
    """Orchestrates compiled workflows, coordinating parallel step runs and recovery actions."""

    def __init__(
        self,
        orchestrator: ExecutionOrchestrator,
        event_bus: EventBusInterface,
    ) -> None:
        """Initialize the WorkflowOrchestrator.

        Args:
            orchestrator: Reasoning execution orchestrator to run individual steps.
            event_bus: Event bus to publish lifecycle events.
        """
        self.orchestrator = orchestrator
        self.event_bus = event_bus

    async def execute_workflow(
        self,
        compiled_workflow: CompiledWorkflow,
        session: ReasoningSession,
    ) -> Dict[str, Any]:
        """Execute a CompiledWorkflow topology wave-by-wave.

        Args:
            compiled_workflow: The compiled immutable workflow plan.
            session: Active ReasoningSession tracking context.

        Returns:
            Dictionary detailing completion status, state, metrics, and step outputs.
        """
        workflow_id = compiled_workflow.workflow_id
        step_outputs: Dict[str, Any] = {}
        total_steps = sum(len(wave) for wave in compiled_workflow.waves)

        metrics = WorkflowMetrics(total_steps=total_steps)
        start_time = time.time()

        # Update and publish initial workflow state
        await self._publish_event(
            "workflow.started",
            session.session_id,
            {
                "workflow_id": str(workflow_id),
                "state": WorkflowState.RUNNING.value,
                "timestamp": time.time(),
            },
        )

        try:
            for wave_idx, wave in enumerate(compiled_workflow.waves):
                # Run all steps in the current wave concurrently
                tasks = [
                    self._execute_step_with_recovery(
                        step, session, step_outputs, metrics
                    )
                    for step in wave
                ]
                await asyncio.gather(*tasks)

            # Success exit path
            duration = time.time() - start_time
            metrics.execution_duration = duration
            if metrics.total_steps > 0:
                metrics.success_rate = (
                    metrics.completed_steps / metrics.total_steps
                ) * 100.0

            await self._publish_event(
                "workflow.completed",
                session.session_id,
                {
                    "workflow_id": str(workflow_id),
                    "state": WorkflowState.COMPLETED.value,
                    "metrics": metrics.model_dump(mode="json"),
                    "timestamp": time.time(),
                },
            )

            return {
                "status": "SUCCESS",
                "state": WorkflowState.COMPLETED,
                "metrics": metrics,
                "step_outputs": step_outputs,
            }

        except Exception as err:
            # Failure exit path
            duration = time.time() - start_time
            metrics.execution_duration = duration
            if metrics.total_steps > 0:
                metrics.success_rate = (
                    metrics.completed_steps / metrics.total_steps
                ) * 100.0

            await self._publish_event(
                "workflow.step.failed"
                if "step" in str(err).lower()
                else "workflow.cancelled",
                session.session_id,
                {
                    "workflow_id": str(workflow_id),
                    "state": WorkflowState.FAILED.value,
                    "error": str(err),
                    "metrics": metrics.model_dump(mode="json"),
                    "timestamp": time.time(),
                },
            )

            return {
                "status": "FAILURE",
                "state": WorkflowState.FAILED,
                "error": str(err),
                "metrics": metrics,
                "step_outputs": step_outputs,
            }

    async def _execute_step_with_recovery(
        self,
        step: WorkflowStep,
        session: ReasoningSession,
        step_outputs: Dict[str, Any],
        metrics: WorkflowMetrics,
    ) -> None:
        """Execute a single step, applying retry/recovery policies if failures occur."""
        # 1. Resolve variable parameter bindings
        try:
            resolved_args = self._resolve_variables(step.arguments, step_outputs)
        except Exception as err:
            raise RuntimeError(
                f"Variable resolution failed for step '{step.name}': {str(err)}"
            )

        # 2. Publish step started event
        await self._publish_event(
            "workflow.step.started",
            session.session_id,
            {
                "step_name": step.name,
                "state": WorkflowStepState.RUNNING.value,
                "timestamp": time.time(),
            },
        )

        attempts = 0
        max_attempts = 3 if step.recovery_policy == RecoveryPolicy.RETRY_STEP else 1

        while attempts < max_attempts:
            attempts += 1
            if attempts > 1:
                metrics.retry_count += 1

            try:
                # Call existing ExecutionOrchestrator helper
                result = await self.orchestrator.execute_task_step(
                    tool_name=step.tool_name,
                    arguments=resolved_args,
                    session=session,
                    caller_id="workflow_orchestrator",
                )

                # Store output variables
                step_outputs[step.name] = result

                # Increment metrics
                metrics.completed_steps += 1

                # Publish step completed event
                await self._publish_event(
                    "workflow.step.completed",
                    session.session_id,
                    {
                        "step_name": step.name,
                        "state": WorkflowStepState.COMPLETED.value,
                        "timestamp": time.time(),
                    },
                )
                return

            except Exception as err:
                if attempts < max_attempts:
                    continue  # Retry

                # Max attempts reached: evaluate recovery policy
                metrics.failed_steps += 1
                await self._publish_event(
                    "workflow.step.failed",
                    session.session_id,
                    {
                        "step_name": step.name,
                        "state": WorkflowStepState.FAILED.value,
                        "error": str(err),
                        "timestamp": time.time(),
                    },
                )

                if step.recovery_policy == RecoveryPolicy.CONTINUE:
                    # Proceed to subsequent waves despite this failure
                    step_outputs[step.name] = {"error": str(err)}
                    return
                else:
                    # Abort execution sequence
                    raise RuntimeError(
                        f"Step '{step.name}' failed after {attempts} attempts: {str(err)}"
                    )

    def _resolve_variables(self, arguments: Any, step_outputs: Dict[str, Any]) -> Any:
        """Resolve templated parameters recursively using execution step outputs."""

        def _resolve(val: Any) -> Any:
            if isinstance(val, str):
                templates = ANY_TEMPLATE_PATTERN.findall(val)
                if not templates:
                    return val

                # If string matches exactly one template, resolve and return the exact object
                if len(templates) == 1 and val.strip() == templates[0]:
                    match = VAR_PATTERN.match(templates[0])
                    if not match:
                        raise ValueError(f"Invalid template format: '{templates[0]}'")
                    ref_step, ref_var = match.group(1), match.group(2)
                    if ref_step not in step_outputs:
                        raise ValueError(f"Step '{ref_step}' has not executed yet.")
                    outputs = step_outputs[ref_step]
                    if ref_var not in outputs:
                        raise ValueError(
                            f"Variable '{ref_var}' missing from step '{ref_step}' outputs."
                        )
                    return outputs[ref_var]

                # String substitution
                res_str = val
                for t in templates:
                    match = VAR_PATTERN.match(t)
                    if not match:
                        raise ValueError(f"Invalid template format: '{t}'")
                    ref_step, ref_var = match.group(1), match.group(2)
                    if ref_step not in step_outputs:
                        raise ValueError(f"Step '{ref_step}' has not executed yet.")
                    outputs = step_outputs[ref_step]
                    if ref_var not in outputs:
                        raise ValueError(
                            f"Variable '{ref_var}' missing from step '{ref_step}' outputs."
                        )
                    res_str = res_str.replace(t, str(outputs[ref_var]))
                return res_str

            elif isinstance(val, dict):
                return {k: _resolve(v) for k, v in val.items()}
            elif isinstance(val, list):
                return [_resolve(item) for item in val]
            return val

        return _resolve(arguments)

    async def _publish_event(
        self,
        topic: str,
        session_id: UUID,
        body: Dict[str, Any],
    ) -> None:
        """Broadcast workflow state updates over the EventBus."""
        msg = InterAgentMessage(
            id=uuid4(),
            correlation_id=session_id,
            sender="workflow_orchestrator",
            receiver="*",
            action=topic,
            body=body,
        )
        await self.event_bus.publish(topic, msg)
