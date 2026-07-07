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

from core.reasoning.dependency_graph import DependencyBuilder
from core.reasoning.execution_plan import ExecutionPlanCompiler
from core.reasoning.goal import Goal, GoalAnalyzer
from core.reasoning.planner_validator import PlannerValidator
from core.reasoning.scheduler import ExecutionScheduler
from core.reasoning.task import TaskGenerator


def test_planner_pipeline_end_to_end() -> None:
    # 1. User Goal
    goal = Goal(
        goal_text="search for python bugs, read file src/main.py, run command: pytest tests/ #dev budget=$15"
    )

    # 2. Goal Analyzer
    analyzer = GoalAnalyzer()
    analysis = analyzer.analyze(goal)
    assert analysis.constraints.budget == 15.0
    assert "dev" in analysis.tags

    # 3. Task Generator
    generator = TaskGenerator()
    tasks = generator.decompose(analysis, goal.goal_text)
    assert len(tasks) == 3

    # 4. Dependency Builder & Validation
    builder = DependencyBuilder(tasks)
    builder.validate_dag()

    # 5. Execution Scheduler
    scheduler = ExecutionScheduler(builder)
    waves = scheduler.schedule_waves()
    assert len(waves) == 3  # sequential dependency chain means 3 waves of 1 task each

    # 6. Planner Validator
    validator = PlannerValidator()
    validator.validate_plan(goal, analysis, tasks, waves)

    # 7. Execution Plan Compiler
    compiler = ExecutionPlanCompiler()
    plan = compiler.compile(goal, analysis, tasks, waves)

    assert plan.goal.goal_text == goal.goal_text
    assert len(plan.waves) == 3
    assert plan.estimated_cost == 0.08  # 0.01 + 0.02 + 0.05
    assert plan.estimated_tokens == 800  # 100 + 200 + 500
    assert plan.execution_strategy == "parallel"
    assert plan.risk_assessment == "medium"
