"""
PHASE: 24
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/84_PHASE_24_AUTONOMOUS_AGENT_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/85_PHASE_24_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Architecture (Architect-mandated, Phase 24 Condition 3):
    AgentLoop is the SINGLE top-level controller.
    No other module may bypass AgentLoop to reach Dispatcher or Memory.

    Observe → Think (DecisionEngine) → Plan → Execute (Dispatcher)
          ↑                                         ↓
          └──────────── Reflect (ReflectionEngine) ←┘
                              ↓ (if failure)
                           Replan → Planner inserts repair task
                              ↓
                        Continue / Finish
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from core.reasoning.decision_engine import DecisionEngine
from core.reasoning.dispatcher import ToolDispatcher
from core.reasoning.journal import ExecutionJournal
from core.reasoning.reflection import ReflectionEngine
from core.reasoning.task import AgentTerminationReason, ExecutorType, Task
from core.tools.dto import ToolExecutionResult

# ── Result DTO ───────────────────────────────────────────────────────────────


class AgentLoopResult(BaseModel):
    """Final outcome of a complete agent execution loop."""

    termination_reason: AgentTerminationReason = Field(
        ..., description="Why the loop ended."
    )
    iterations_used: int = Field(
        default=0, description="Number of Observe-Execute-Reflect cycles performed."
    )
    tasks_completed: int = Field(
        default=0, description="Count of tasks that reached SUCCESS status."
    )
    tasks_failed: int = Field(
        default=0, description="Count of tasks that ultimately failed."
    )
    final_outputs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Collected stdout/artifact payloads from successful tasks.",
    )
    memory_updates: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Memory entries queued for persistence post-loop.",
    )
    journal: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Execution journal records (serialised IterationRecord dicts).",
    )
    error: Optional[str] = Field(
        default=None, description="Error detail if loop was aborted."
    )


# ── Agent Loop ───────────────────────────────────────────────────────────────


class AgentLoop:
    """Autonomous Observe-Think-Plan-Execute-Reflect-Replan execution controller.

    Architect Constraints (Phase 24):
    1. AgentLoop is the sole controller — nothing bypasses it.
    2. ReflectionEngine only analyses results; never calls tools.
    3. DecisionEngine selects tools; never executes them.
    4. All LLM calls (if triggered for replanning) pass through LlmRuntime.
    5. Iteration cap + explicit termination reasons are mandatory.
    6. Memory updates use confidence/tentative flags for failures.
    """

    MAX_ITERATIONS = 10

    def __init__(
        self,
        dispatcher: ToolDispatcher,
        reflection_engine: ReflectionEngine,
        decision_engine: DecisionEngine,
        max_iterations: int = MAX_ITERATIONS,
        journal: Optional[ExecutionJournal] = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.reflection = reflection_engine
        self.decision = decision_engine
        self.max_iterations = max_iterations
        self._journal = journal

    async def run(
        self,
        tasks: List[Task],
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentLoopResult:
        """Run the autonomous agent loop over a list of tasks.

        Observe → Think → Execute → Reflect → [Replan] → Continue/Finish.

        Args:
            tasks: Ordered list of Task objects to execute.
            context: Shared execution context (services, memory, flags).

        Returns:
            AgentLoopResult with termination reason and collected outputs.
        """
        ctx = context or {}
        iteration = 0
        completed = 0
        failed = 0
        final_outputs: List[Dict[str, Any]] = []
        memory_updates: List[Dict[str, Any]] = []
        # Local retry counter — keyed by task.id (avoids mutating frozen Task model)
        retry_counts: Dict[Any, int] = {}

        # Work queue — mutable copy so we can append repair tasks
        queue: List[Task] = list(tasks)
        idx = 0

        while idx < len(queue):
            # ── Iteration guard ──────────────────────────────────────────────
            if iteration >= self.max_iterations:
                return AgentLoopResult(
                    termination_reason=AgentTerminationReason.ITERATION_LIMIT,
                    iterations_used=iteration,
                    tasks_completed=completed,
                    tasks_failed=failed,
                    final_outputs=final_outputs,
                    memory_updates=memory_updates,
                )

            task = queue[idx]
            iteration += 1

            # ── OBSERVE: check if task is already aborted/cancelled ──────────
            if task.executor == ExecutorType.HUMAN:
                # Human tasks with auto_approve=False in non-interactive mode
                # default to auto-approve via context flag
                if not ctx.get("auto_approve", False) and not task.payload.get(
                    "auto_approve"
                ):
                    task.payload["auto_approve"] = ctx.get("auto_approve_human", False)

            # ── THINK: let DecisionEngine validate/override executor choice ──
            if task.payload.get("description"):
                selection = self.decision.select_tool(task.payload["description"], ctx)
                # Only override if confidence is high enough and executor differs
                if (
                    selection.confidence >= 0.85
                    and selection.executor_type != task.executor
                ):
                    task = task.model_copy(update={"executor": selection.executor_type})

            # ── EXECUTE: dispatch to appropriate runtime ─────────────────────
            result: ToolExecutionResult = await self.dispatcher.dispatch(task, ctx)

            # ── REFLECT: analyse outcome ─────────────────────────────────────
            reflection_out = self.reflection.analyze(result)

            if reflection_out.success:
                # ── SUCCESS path ─────────────────────────────────────────────
                completed += 1
                final_outputs.append(
                    {
                        "task_id": str(task.id),
                        "task_type": str(task.task_type),
                        "stdout": result.stdout,
                        "artifacts": result.artifacts,
                    }
                )
                # Memory update (Architect Constraint 4 — success = high confidence)
                memory_updates.append(
                    {
                        "task_id": str(task.id),
                        "status": "success",
                        "confidence": 0.95,
                        "tentative": False,
                        "content": result.stdout[:500],
                        "metadata": {
                            "executor": str(task.executor),
                            "iteration": iteration,
                        },
                    }
                )
                # Journal: record success iteration
                self._record_journal(
                    iteration=iteration,
                    task=task,
                    output_summary=result.stdout[:200],
                    next_action="CONTINUE" if idx + 1 < len(queue) else "SUCCESS",
                )
                idx += 1

            elif reflection_out.should_abort:
                # ── UNRECOVERABLE FAILURE path ────────────────────────────────
                failed += 1
                memory_updates.append(
                    {
                        "task_id": str(task.id),
                        "status": "failure",
                        "confidence": 0.10,
                        "tentative": True,
                        "content": reflection_out.failure_summary[:500],
                        "metadata": {
                            "executor": str(task.executor),
                            "failure_category": str(reflection_out.failure_category),
                            "iteration": iteration,
                            "retry_count": retry_counts.get(task.id, 0),
                        },
                    }
                )
                # Journal: record abort iteration
                self._record_journal(
                    iteration=iteration,
                    task=task,
                    output_summary=reflection_out.failure_summary[:200]
                    if reflection_out.failure_summary
                    else "",
                    reflection_category=str(reflection_out.failure_category)
                    if reflection_out.failure_category
                    else None,
                    next_action="ABORT",
                )
                return AgentLoopResult(
                    termination_reason=AgentTerminationReason.FAILED,
                    iterations_used=iteration,
                    tasks_completed=completed,
                    tasks_failed=failed,
                    final_outputs=final_outputs,
                    memory_updates=memory_updates,
                    journal=self._export_journal(),
                    error=reflection_out.failure_summary,
                )

            elif reflection_out.should_replan and reflection_out.repair_strategy:
                # ── REPLAN path ───────────────────────────────────────────────
                strategy = reflection_out.repair_strategy
                failed += 1

                # Record failure memory with tentative flag (Constraint 4)
                memory_updates.append(
                    {
                        "task_id": str(task.id),
                        "status": "failure",
                        "confidence": 0.25,
                        "tentative": True,
                        "content": reflection_out.failure_summary[:500],
                        "metadata": {
                            "executor": str(task.executor),
                            "failure_category": str(reflection_out.failure_category),
                            "iteration": iteration,
                            "retry_count": retry_counts.get(task.id, 0),
                        },
                    }
                )

                # Build a repair task and insert it immediately after current position
                repair_payload = dict(task.payload)
                repair_payload.update(strategy.suggested_payload_patch)
                repair_payload["description"] = strategy.strategy

                repair_executor = (
                    ExecutorType(strategy.suggested_executor)
                    if strategy.suggested_executor
                    else task.executor
                )

                repair_task = Task(
                    id=uuid4(),
                    goal_id=task.goal_id,
                    executor=repair_executor,
                    task_type=task.task_type,
                    payload=repair_payload,
                )

                # Insert repair task after current, then re-attempt the original
                retry_task = deepcopy(task)
                # Track retry count locally
                retry_counts[retry_task.id] = retry_counts.get(task.id, 0) + 1

                queue.insert(idx + 1, repair_task)
                queue.insert(idx + 2, retry_task)
                # Journal: record replan iteration
                self._record_journal(
                    iteration=iteration,
                    task=task,
                    output_summary=reflection_out.failure_summary[:200]
                    if reflection_out.failure_summary
                    else "",
                    reflection_category=str(reflection_out.failure_category)
                    if reflection_out.failure_category
                    else None,
                    next_action="REPLAN",
                )
                idx += 1  # advance past the current failed task

            else:
                # Generic failure with no replan advice
                failed += 1
                memory_updates.append(
                    {
                        "task_id": str(task.id),
                        "status": "failure",
                        "confidence": 0.15,
                        "tentative": True,
                        "content": reflection_out.failure_summary[:500],
                        "metadata": {
                            "executor": str(task.executor),
                            "iteration": iteration,
                        },
                    }
                )
                # Journal: record generic failure iteration
                self._record_journal(
                    iteration=iteration,
                    task=task,
                    output_summary=reflection_out.failure_summary[:200]
                    if reflection_out.failure_summary
                    else "",
                    reflection_category=str(reflection_out.failure_category)
                    if reflection_out.failure_category
                    else None,
                    next_action="CONTINUE",
                )
                idx += 1

        # ── All tasks processed ───────────────────────────────────────────────
        termination = (
            AgentTerminationReason.SUCCESS
            if failed == 0
            else AgentTerminationReason.FAILED
        )
        return AgentLoopResult(
            termination_reason=termination,
            iterations_used=iteration,
            tasks_completed=completed,
            tasks_failed=failed,
            final_outputs=final_outputs,
            memory_updates=memory_updates,
            journal=self._export_journal(),
        )

    # ── Journal helpers ──────────────────────────────────────────────────────

    def _record_journal(
        self,
        *,
        iteration: int,
        task: Task,
        output_summary: str = "",
        reflection_category: Optional[str] = None,
        next_action: str = "CONTINUE",
    ) -> None:
        """Append one record to the journal if it exists."""
        if self._journal is None:
            return
        self._journal.record_iteration(
            iteration=iteration,
            goal_description=task.payload.get("description", str(task.task_type)),
            chosen_executor=str(task.executor),
            reasoning=task.payload.get("reasoning", ""),
            output_summary=output_summary,
            reflection_category=reflection_category,
            next_action=next_action,
        )

    def _export_journal(self) -> List[Dict[str, Any]]:
        """Export journal records as serialisable dicts."""
        if self._journal is None:
            return []
        return [rec.model_dump(mode="json") for rec in self._journal.export()]
