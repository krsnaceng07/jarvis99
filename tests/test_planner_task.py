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

from core.reasoning.goal import Goal, GoalAnalyzer
from core.reasoning.task import ExecutorType, TaskGenerator, TaskType


def test_task_generator_decomposition() -> None:
    goal = Goal(
        goal_text="search for python bugs, read file src/main.py, run command: pytest tests/"
    )
    analyzer = GoalAnalyzer()
    analysis = analyzer.analyze(goal)

    generator = TaskGenerator()
    tasks = generator.decompose(analysis, goal.goal_text)

    # We expect 3 parsed tasks in sequence
    assert len(tasks) == 3

    # Task 1: Search
    assert tasks[0].task_type == TaskType.SEARCH
    assert tasks[0].executor == ExecutorType.MEMORY
    assert tasks[0].payload["query"] == "python bugs"

    # Task 2: File Operation
    assert tasks[1].task_type == TaskType.FILE_OP
    assert tasks[1].executor == ExecutorType.PYTHON
    assert tasks[1].payload["file_path"] == "src/main.py"
    # Verify dependency chain mapping
    assert tasks[0].id in tasks[1].dependencies

    # Task 3: Command Execution
    assert tasks[2].task_type == TaskType.COMMAND
    assert tasks[2].executor == ExecutorType.SHELL
    assert tasks[2].payload["command"] == "pytest tests/"
    assert tasks[1].id in tasks[2].dependencies


def test_task_generator_fallback() -> None:
    goal = Goal(goal_text="solve general programming problems")
    analyzer = GoalAnalyzer()
    analysis = analyzer.analyze(goal)

    generator = TaskGenerator()
    tasks = generator.decompose(analysis, goal.goal_text)

    assert len(tasks) == 1
    assert tasks[0].task_type == TaskType.SYSTEM
    assert tasks[0].executor == ExecutorType.LLM
