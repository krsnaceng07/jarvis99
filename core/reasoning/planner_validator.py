"""
PHASE: 21
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 21 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

from typing import List, Set
from uuid import UUID

from core.exceptions import JarvisSystemError
from core.reasoning.dependency_graph import DependencyBuilder
from core.reasoning.goal import Goal, GoalAnalysis
from core.reasoning.task import Task


class PlannerValidator:
    """Enforces structural and budget constraints on generated execution plans before runtime dispatch."""

    def validate_plan(
        self,
        goal: Goal,
        analysis: GoalAnalysis,
        tasks: List[Task],
        waves: List[List[UUID]],
        cost_limit: float = 10.0,
        token_limit: int = 50000,
    ) -> None:
        """Run complete plan audit checking dependencies, constraints, and resource limits.

        Raises:
            JarvisSystemError on validation failure.
        """
        # 1. Structural DAG Validation
        builder = DependencyBuilder(tasks)
        builder.validate_dag()

        # 2. Check for orphan tasks
        orphans = builder.get_orphan_tasks()
        if orphans:
            raise JarvisSystemError(
                code="PLANNER_004",
                message=f"Plan contains disconnected/orphan tasks: {orphans}",
            )

        # 3. Check for duplicates in task list
        seen_ids: Set[UUID] = set()
        seen_payloads = set()
        for task in tasks:
            if task.id in seen_ids:
                raise JarvisSystemError(
                    code="PLANNER_005",
                    message=f"Plan contains duplicate task ID: {task.id}",
                )
            seen_ids.add(task.id)

            payload_str = str(task.payload)
            if payload_str in seen_payloads:
                raise JarvisSystemError(
                    code="PLANNER_006",
                    message="Plan contains duplicate task payload execution actions.",
                )
            seen_payloads.add(payload_str)

        # 4. Wave coverage checks
        wave_task_ids: Set[UUID] = set()
        for w_idx, wave in enumerate(waves):
            if len(wave) > 3:
                raise JarvisSystemError(
                    code="PLANNER_007",
                    message=f"Wave {w_idx} exceeds the parallel task execution limit of 3.",
                )
            for t_id in wave:
                if t_id not in builder.task_map:
                    raise JarvisSystemError(
                        code="PLANNER_008",
                        message=f"Wave {w_idx} references non-existent task ID: {t_id}",
                    )
                wave_task_ids.add(t_id)

        # Confirm all tasks are represented in the execution waves
        if len(wave_task_ids) != len(tasks):
            raise JarvisSystemError(
                code="PLANNER_009",
                message="Execution waves do not include all tasks in the plan.",
            )

        # 5. Cost and Token Limit validations
        total_cost = sum(t.estimated_cost for t in tasks)
        budget_boundary = min(analysis.constraints.budget, cost_limit)
        if total_cost > budget_boundary:
            raise JarvisSystemError(
                code="PLANNER_010",
                message=f"Plan estimated cost ({total_cost:.2f}) exceeds budget boundary limit ({budget_boundary:.2f}).",
            )

        total_tokens = sum(t.estimated_tokens for t in tasks)
        token_boundary = min(analysis.constraints.token_limit, token_limit)
        if total_tokens > token_boundary:
            raise JarvisSystemError(
                code="PLANNER_011",
                message=f"Plan estimated tokens ({total_tokens}) exceeds token limit boundary ({token_boundary}).",
            )
