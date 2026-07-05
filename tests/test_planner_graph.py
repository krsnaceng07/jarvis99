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
from core.reasoning.dependency_graph import DependencyBuilder
from core.reasoning.task import ExecutorType, Task, TaskType


def test_dependency_builder_success() -> None:
    goal_id = uuid4()
    t1 = Task(goal_id=goal_id, executor=ExecutorType.PYTHON, task_type=TaskType.FILE_OP)
    t2 = Task(
        goal_id=goal_id,
        executor=ExecutorType.SHELL,
        task_type=TaskType.COMMAND,
        dependencies={t1.id},
    )

    builder = DependencyBuilder([t1, t2])
    builder.validate_dag()
    assert builder.get_missing_dependencies() == set()
    assert builder.get_orphan_tasks() == set()


def test_dependency_builder_cycle() -> None:
    goal_id = uuid4()
    t1 = Task(goal_id=goal_id, executor=ExecutorType.PYTHON, task_type=TaskType.FILE_OP)
    t2 = Task(
        goal_id=goal_id,
        executor=ExecutorType.SHELL,
        task_type=TaskType.COMMAND,
        dependencies={t1.id},
    )
    # create cycle: t1 depends on t2, and t2 depends on t1
    t1.dependencies.add(t2.id)

    builder = DependencyBuilder([t1, t2])
    with pytest.raises(JarvisSystemError) as exc:
        builder.validate_dag()
    assert "cycle" in str(exc.value).lower()


def test_dependency_builder_missing_and_orphans() -> None:
    goal_id = uuid4()
    fake_id = uuid4()
    t1 = Task(
        goal_id=goal_id,
        executor=ExecutorType.PYTHON,
        task_type=TaskType.FILE_OP,
        dependencies={fake_id},
    )
    t2 = Task(goal_id=goal_id, executor=ExecutorType.SHELL, task_type=TaskType.COMMAND)

    builder = DependencyBuilder([t1, t2])
    assert builder.get_missing_dependencies() == {fake_id}
    assert builder.get_orphan_tasks() == {t1.id, t2.id}

    with pytest.raises(JarvisSystemError) as exc:
        builder.validate_dag()
    assert "missing" in str(exc.value).lower()
