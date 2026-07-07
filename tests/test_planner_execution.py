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

from core.reasoning.execution_plan import ExecutionPlanCompiler
from core.reasoning.goal import Goal, GoalAnalysis
from core.reasoning.task import ExecutorType, Task, TaskType


def test_execution_plan_compiler() -> None:
    goal = Goal(goal_text="Solve general developer issues")
    analysis = GoalAnalysis(goal_id=goal.id, complexity="medium")
    t1 = Task(
        goal_id=goal.id,
        executor=ExecutorType.PYTHON,
        task_type=TaskType.FILE_OP,
        estimated_cost=0.1,
        estimated_tokens=100,
    )
    t2 = Task(
        goal_id=goal.id,
        executor=ExecutorType.SHELL,
        task_type=TaskType.COMMAND,
        dependencies={t1.id},
        estimated_cost=0.2,
        estimated_tokens=200,
    )

    compiler = ExecutionPlanCompiler()
    plan = compiler.compile(goal, analysis, [t1, t2], [[t1.id], [t2.id]])

    assert plan.goal.goal_text == goal.goal_text
    assert plan.estimated_cost == 0.3
    assert plan.estimated_tokens == 300
    assert len(plan.waves) == 2
    assert plan.execution_strategy == "parallel"
    assert plan.risk_assessment == "medium"
    assert plan.dag[str(t2.id)] == [str(t1.id)]

    # 1. Test high risk / complexity and cost
    high_analysis = GoalAnalysis(goal_id=goal.id, complexity="high")
    t_heavy = Task(
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        estimated_cost=6.0,
    )
    high_plan = compiler.compile(goal, high_analysis, [t_heavy], [[t_heavy.id]])
    assert high_plan.risk_assessment == "high"
    assert high_plan.execution_strategy == "sequential"
