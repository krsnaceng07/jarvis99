"""JARVIS OS - Agent Runtime Engine.

Orchestrates the generic execution loop, coordinating DTO updates, cancellation tokens, and checkpoints.
"""

from typing import Any, Awaitable, Callable, Dict, Optional

from core.exceptions import JarvisAgentError
from core.runtime.context import AgentContextManager
from core.runtime.dto import CancellationToken, CheckpointDTO
from core.runtime.scheduler import ScheduledTask
from core.runtime.state import AgentExecutionState, AgentStateTransitionManager


class AgentRuntime:
    """Coordinates generic execution steps, tracking runtime states and enforcing budgets/resilience gates."""

    def __init__(
        self,
        context: Optional[AgentContextManager] = None,
        token: Optional[CancellationToken] = None,
    ) -> None:
        """Initialize AgentRuntime.

        Args:
            context: Context manager tracking variables and budgets.
            token: CancellationToken for checking pauses and interrupts.
        """
        self.state = AgentExecutionState.IDLE
        self.context = context or AgentContextManager()
        self.token = token or CancellationToken()
        self.checkpoint: Optional[CheckpointDTO] = None
        self._transition_manager = AgentStateTransitionManager()
        self.current_task: Optional[ScheduledTask] = None

    def transition_to(self, target: AgentExecutionState) -> None:
        """Move runtime state to the target execution state after checking transition validity.

        Args:
            target: Intended target AgentExecutionState.

        Raises:
            JarvisAgentError: If transition is invalid.
        """
        self._transition_manager.validate_execution_transition(self.state, target)
        self.state = target

    async def run_task(
        self,
        task: ScheduledTask,
        step_executor: Callable[
            [ScheduledTask, int, AgentContextManager], Awaitable[Dict[str, Any]]
        ],
        steps: int = 1,
    ) -> Dict[str, Any]:
        """Execute a task over a series of steps, managing loop transitions.

        Args:
            task: ScheduledTask to run.
            step_executor: Async callback function executing a single task step.
            steps: Total number of sequential steps to execute.

        Returns:
            Dictionary summary containing execution results and status.

        Raises:
            JarvisAgentError: If cancellation or budget violations interrupt the loop.
            Exception: Re-raises any error encountered during step execution.
        """
        self.current_task = task
        results = []
        start_step = 0

        # Load from checkpoint if valid for this task
        if self.checkpoint and self.checkpoint.task_id == task.id:
            start_step = self.checkpoint.step_index
            saved_variables = self.checkpoint.state_data.get("variables", {})
            self.context.variables.update(saved_variables)
            results = self.checkpoint.state_data.get("results", [])

        for step_idx in range(start_step, steps):
            try:
                # 1. LOAD State
                self.transition_to(AgentExecutionState.LOAD)
                self.context.check_all_budgets()
                if self.token.is_cancelled:
                    raise JarvisAgentError(
                        code="AGENT_004", message="Task execution cancelled."
                    )

                # 2. DISPATCH State
                self.transition_to(AgentExecutionState.DISPATCH)
                if self.token.is_cancelled:
                    raise JarvisAgentError(
                        code="AGENT_004", message="Task execution cancelled."
                    )

                # Create step coroutine execution reference
                step_coro = step_executor(task, step_idx, self.context)

                # 3. WAIT State
                self.transition_to(AgentExecutionState.WAIT)
                await self.token.check_paused()
                if self.token.is_cancelled:
                    raise JarvisAgentError(
                        code="AGENT_004", message="Task execution cancelled."
                    )

                # Await execution step
                step_result = await step_coro
                results.append(step_result)

                # 4. VERIFY State
                self.transition_to(AgentExecutionState.VERIFY)
                # Verify outputs (stub/mock placeholder checks)
                self.context.check_all_budgets()

                # 5. PERSIST State
                self.transition_to(AgentExecutionState.PERSIST)
                self.checkpoint = CheckpointDTO(
                    task_id=task.id,
                    step_index=step_idx + 1,
                    state_data={
                        "results": results,
                        "variables": self.context.variables,
                    },
                )

                # 6. SLEEP State
                self.transition_to(AgentExecutionState.SLEEP)
                # Reset to Idle state for next iteration
                self.state = AgentExecutionState.IDLE

            except Exception as exc:
                # Handle unexpected interrupts, route through PERSIST -> SLEEP -> IDLE
                if self.state not in (
                    AgentExecutionState.IDLE,
                    AgentExecutionState.PERSIST,
                    AgentExecutionState.SLEEP,
                ):
                    self.state = AgentExecutionState.PERSIST

                # Record error inside checkpoints dictionary
                self.checkpoint = CheckpointDTO(
                    task_id=task.id,
                    step_index=step_idx,
                    state_data={
                        "error": str(exc),
                        "results": results,
                        "variables": self.context.variables,
                    },
                )
                self.state = AgentExecutionState.SLEEP
                self.state = AgentExecutionState.IDLE
                raise exc

        return {"status": "SUCCESS", "results": results}
