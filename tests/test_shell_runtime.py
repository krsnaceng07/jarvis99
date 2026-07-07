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

from uuid import uuid4

import pytest

from core.reasoning.task import ExecutorType, Task, TaskType
from core.tools.shell_runtime import ShellRuntime


@pytest.mark.asyncio
async def test_shell_runtime_basic_success() -> None:
    runtime = ShellRuntime()
    # Cross platform friendly command
    command = "echo hello_shell"
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.SHELL,
        task_type=TaskType.COMMAND,
        payload={"command": command},
    )
    res = await runtime.execute(task, {})
    assert res.status == "SUCCESS"
    assert "hello_shell" in res.stdout.strip()
    assert res.exit_code == 0
    assert res.error is None


@pytest.mark.asyncio
async def test_shell_runtime_command_failure() -> None:
    runtime = ShellRuntime()
    # Bad command resulting in error
    command = "exit 1"
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.SHELL,
        task_type=TaskType.COMMAND,
        payload={"command": command},
    )
    res = await runtime.execute(task, {})
    assert res.status == "FAILURE"
    assert res.exit_code != 0


@pytest.mark.asyncio
async def test_shell_runtime_env_variables() -> None:
    runtime = ShellRuntime()
    # Echo environment variable
    command = "echo %MY_TEST_VAR%"
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.SHELL,
        task_type=TaskType.COMMAND,
        payload={
            "command": command,
            "env": {"MY_TEST_VAR": "EnvironmentLoaded"},
        },
    )
    res = await runtime.execute(task, {})
    assert res.status == "SUCCESS"
    assert "EnvironmentLoaded" in res.stdout.strip()
