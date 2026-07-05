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

from core.reasoning.dependency_graph import DependencyBuilder
from core.reasoning.scheduler import ExecutionScheduler
from core.reasoning.task import ExecutorType, Task, TaskType


def test_scheduler_wave_limits() -> None:
    goal_id = uuid4()
    # 4 tasks with 0 dependencies (should naturally form 1 wave, but scheduler must split it because limit is 3)
    t1 = Task(goal_id=goal_id, executor=ExecutorType.LLM, task_type=TaskType.SYSTEM)
    t2 = Task(goal_id=goal_id, executor=ExecutorType.LLM, task_type=TaskType.SYSTEM)
    t3 = Task(goal_id=goal_id, executor=ExecutorType.LLM, task_type=TaskType.SYSTEM)
    t4 = Task(goal_id=goal_id, executor=ExecutorType.LLM, task_type=TaskType.SYSTEM)

    builder = DependencyBuilder([t1, t2, t3, t4])
    scheduler = ExecutionScheduler(builder)
    waves = scheduler.schedule_waves()

    assert len(waves) == 2
    assert len(waves[0]) == 3
    assert len(waves[1]) == 1


def test_scheduler_resource_mutex() -> None:
    goal_id = uuid4()
    # 2 tasks requiring 'browser' resource. Should be scheduled in different waves.
    t1 = Task(
        goal_id=goal_id,
        executor=ExecutorType.BROWSER,
        task_type=TaskType.SYSTEM,
        payload={"resource": "browser"},
    )
    t2 = Task(
        goal_id=goal_id,
        executor=ExecutorType.BROWSER,
        task_type=TaskType.SYSTEM,
        payload={"resource": "browser"},
    )

    # 3. Task with a custom payload resource key
    t3 = Task(
        goal_id=goal_id,
        executor=ExecutorType.PYTHON,
        task_type=TaskType.CODE,
        payload={"resource": "db_mutex"},
    )
    t4 = Task(
        goal_id=goal_id,
        executor=ExecutorType.PYTHON,
        task_type=TaskType.CODE,
        payload={"resource": "db_mutex"},
    )

    builder = DependencyBuilder([t1, t2, t3, t4])
    scheduler = ExecutionScheduler(builder)
    waves = scheduler.schedule_waves()

    # t1 and t3 can run in Wave 1.
    # t2 and t4 are delayed to Wave 2.
    assert len(waves) == 2
    assert len(waves[0]) == 2
    assert len(waves[1]) == 2


def test_scheduler_cycle_break_and_fallback() -> None:
    goal_id = uuid4()
    # 1. Cycle condition (scheduler candidates loop break)
    t1 = Task(goal_id=goal_id, executor=ExecutorType.PYTHON, task_type=TaskType.FILE_OP)
    t2 = Task(
        goal_id=goal_id,
        executor=ExecutorType.SHELL,
        task_type=TaskType.COMMAND,
        dependencies={t1.id},
    )
    t1.dependencies.add(t2.id)  # Cycle!

    builder = DependencyBuilder([t1, t2])
    scheduler = ExecutionScheduler(builder)
    waves = scheduler.schedule_waves()
    # Should exit loop safely and return empty or partial waves
    assert waves == []

    # 2. Assert resource mutex separation for BROWSER tasks
    f1 = Task(
        goal_id=goal_id,
        executor=ExecutorType.BROWSER,
        task_type=TaskType.SYSTEM,
    )
    f2 = Task(
        goal_id=goal_id,
        executor=ExecutorType.BROWSER,
        task_type=TaskType.SYSTEM,
    )
    builder2 = DependencyBuilder([f1, f2])
    scheduler2 = ExecutionScheduler(builder2)
    waves2 = scheduler2.schedule_waves()

    assert len(waves2) == 2
    assert len(waves2[0]) == 1
    assert len(waves2[1]) == 1
