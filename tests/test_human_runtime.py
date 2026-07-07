"""
PHASE: 23
STATUS: TEST
SPECIFICATION:
    docs/82_PHASE_22_ORCHESTRATOR_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest

from core.reasoning.task import ExecutorType, Task, TaskType
from core.tools.human_runtime import HumanRuntime


@pytest.mark.asyncio
async def test_human_runtime_auto_approve() -> None:
    runtime = HumanRuntime()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.HUMAN,
        task_type=TaskType.HUMAN,
        payload={
            "prompt": "Test approval request?",
            "auto_approve": True,
        },
    )
    res = await runtime.execute(task, {})
    assert res.status == "SUCCESS"
    assert res.exit_code == 0
    assert res.artifacts["approved"] is True


@pytest.mark.asyncio
async def test_human_runtime_interactive_approve() -> None:
    runtime = HumanRuntime()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.HUMAN,
        task_type=TaskType.HUMAN,
        payload={
            "prompt": "Do you approve?",
            "auto_approve": False,
        },
    )

    # Mock stdin readline to return yes
    with patch("sys.stdin.readline", return_value="approve\n"):
        res = await runtime.execute(task, {})

    assert res.status == "SUCCESS"
    assert res.exit_code == 0
    assert res.artifacts["approved"] is True
    assert res.artifacts["response"] == "approve"


@pytest.mark.asyncio
async def test_human_runtime_interactive_reject() -> None:
    runtime = HumanRuntime()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.HUMAN,
        task_type=TaskType.HUMAN,
        payload={
            "prompt": "Delete file?",
            "auto_approve": False,
        },
    )

    # Mock stdin readline to return no
    with patch("sys.stdin.readline", return_value="no\n"):
        res = await runtime.execute(task, {})

    assert res.status == "FAILURE"
    assert res.exit_code == 1
    assert res.artifacts["approved"] is False
    assert res.artifacts["response"] == "no"
