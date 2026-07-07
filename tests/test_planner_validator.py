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

from uuid import uuid4

import pytest

from core.exceptions import JarvisSystemError
from core.reasoning.goal import Goal, GoalAnalysis, GoalConstraints
from core.reasoning.planner_validator import PlannerValidator
from core.reasoning.task import ExecutorType, Task, TaskType


def test_validator_cost_and_token_bounds() -> None:
    goal = Goal(goal_text="Test validation goal")
    constraints = GoalConstraints(budget=5.0, token_limit=1000)
    analysis = GoalAnalysis(goal_id=goal.id, constraints=constraints)

    # 1. Cost too high
    t_costly = Task(
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        estimated_cost=6.0,
    )
    validator = PlannerValidator()
    with pytest.raises(JarvisSystemError) as exc:
        validator.validate_plan(goal, analysis, [t_costly], [[t_costly.id]])
    assert "budget" in str(exc.value).lower()

    # 2. Tokens too high
    t_heavy = Task(
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        estimated_tokens=2000,
    )
    with pytest.raises(JarvisSystemError) as exc:
        validator.validate_plan(goal, analysis, [t_heavy], [[t_heavy.id]])
    assert "token" in str(exc.value).lower()


def test_validator_duplicate_payloads() -> None:
    goal = Goal(goal_text="Test validation goal")
    analysis = GoalAnalysis(goal_id=goal.id)

    # Two distinct tasks with identical payloads (duplicate action check)
    t1 = Task(
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        payload={"action": "run_test"},
    )
    t2 = Task(
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        payload={"action": "run_test"},
        dependencies={t1.id},
    )

    validator = PlannerValidator()
    with pytest.raises(JarvisSystemError) as exc:
        validator.validate_plan(goal, analysis, [t1, t2], [[t1.id], [t2.id]])
    assert "duplicate" in str(exc.value).lower()


def test_validator_duplicates_orphans_and_wave_errors() -> None:
    goal = Goal(goal_text="Test validation goal")
    analysis = GoalAnalysis(goal_id=goal.id)
    validator = PlannerValidator()

    # 1. Test duplicate task ID
    t1 = Task(
        id=uuid4(),
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        payload={"action": "t1"},
    )
    t2 = Task(
        id=uuid4(),
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        payload={"action": "t2"},
        dependencies={t1.id},
    )
    with pytest.raises(JarvisSystemError) as exc:
        validator.validate_plan(goal, analysis, [t1, t2, t1], [[t1.id], [t2.id]])
    assert "duplicate task id" in str(exc.value).lower()

    # 2. Test orphan tasks error
    t2 = Task(
        id=uuid4(),
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        payload={"action": "t2"},
    )
    # t1 and t2 are not connected
    with pytest.raises(JarvisSystemError) as exc:
        validator.validate_plan(goal, analysis, [t1, t2], [[t1.id], [t2.id]])
    assert "orphan" in str(exc.value).lower()

    # Make t2 depend on t1 for subsequent tests to avoid orphan error
    t2.dependencies.add(t1.id)

    # 3. Test wave size > 3
    t3 = Task(
        id=uuid4(),
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        payload={"action": "t3"},
        dependencies={t1.id},
    )
    t4 = Task(
        id=uuid4(),
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        payload={"action": "t4"},
        dependencies={t1.id},
    )
    t5 = Task(
        id=uuid4(),
        goal_id=goal.id,
        executor=ExecutorType.LLM,
        task_type=TaskType.SYSTEM,
        payload={"action": "t5"},
        dependencies={t1.id},
    )
    with pytest.raises(JarvisSystemError) as exc:
        # Wave contains 4 tasks: t2, t3, t4, t5 (exceeds parallel limit)
        validator.validate_plan(
            goal,
            analysis,
            [t1, t2, t3, t4, t5],
            [[t1.id], [t2.id, t3.id, t4.id, t5.id]],
        )
    assert "exceeds the parallel task execution limit" in str(exc.value).lower()

    # 4. Test wave references non-existent task ID
    with pytest.raises(JarvisSystemError) as exc:
        validator.validate_plan(goal, analysis, [t1, t2], [[t1.id], [uuid4()]])
    assert "references non-existent task" in str(exc.value).lower()

    # 5. Test wave task IDs count mismatch (missing tasks in wave)
    with pytest.raises(JarvisSystemError) as exc:
        validator.validate_plan(goal, analysis, [t1, t2], [[t1.id]])
    assert "do not include all tasks" in str(exc.value).lower()
