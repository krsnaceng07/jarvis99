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

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.reasoning.goal import Goal, GoalAnalysis
from core.reasoning.task import Task


class ExecutionPlan(BaseModel):
    """The final compiled, validated, and scheduled task plan ready for execution."""

    id: UUID = Field(default_factory=uuid4)
    goal: Goal
    analysis: GoalAnalysis
    tasks: List[Task]
    dag: Dict[str, List[str]] = Field(default_factory=dict)
    waves: List[List[UUID]] = Field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_tokens: int = 0
    execution_strategy: str = "parallel"
    risk_assessment: str = "low"
    retry_policy: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    schema_version: Literal["1.0"] = "1.0"


class ExecutionPlanCompiler:
    """Compiles task dependencies and waves into a final validated ExecutionPlan DTO."""

    def compile(
        self,
        goal: Goal,
        analysis: GoalAnalysis,
        tasks: List[Task],
        waves: List[List[UUID]],
    ) -> ExecutionPlan:
        # Calculate sums
        total_cost = sum(t.estimated_cost for t in tasks)
        total_tokens = sum(t.estimated_tokens for t in tasks)

        # Build clean string-based DAG adjacency dictionary for DTO
        dag_dict: Dict[str, List[str]] = {}
        for task in tasks:
            dag_dict[str(task.id)] = [str(d) for d in task.dependencies]

        # Determine risk assessment based on complexity and cost
        risk = "low"
        if analysis.complexity == "high" or total_cost > 5.0:
            risk = "high"
        elif analysis.complexity == "medium":
            risk = "medium"

        # Generate default retry policies
        retry_policy = {
            "max_attempts": 3,
            "backoff_multiplier": 2.0,
            "initial_delay_seconds": 5.0,
        }

        return ExecutionPlan(
            goal=goal,
            analysis=analysis,
            tasks=tasks,
            dag=dag_dict,
            waves=waves,
            estimated_cost=round(total_cost, 4),
            estimated_tokens=total_tokens,
            execution_strategy="parallel" if len(waves) > 1 else "sequential",
            risk_assessment=risk,
            retry_policy=retry_policy,
            metadata={"compiled_at": datetime.now(timezone.utc).isoformat()},
        )
