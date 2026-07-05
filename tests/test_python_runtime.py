"""
PHASE: 23
STATUS: TEST
SPECIFICATION:
    docs/82_PHASE_22_ORCHASETRATOR_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import os
import tempfile
from uuid import uuid4

import pytest

from core.reasoning.task import ExecutorType, Task, TaskType
from core.tools.python_runtime import PythonRuntime


@pytest.mark.asyncio
async def test_python_runtime_basic_success() -> None:
    runtime = PythonRuntime()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.PYTHON,
        task_type=TaskType.CODE,
        payload={"code": "print(10 + 20)"},
    )
    res = await runtime.execute(task, {})
    assert res.status == "SUCCESS"
    assert res.stdout.strip() == "30"
    assert res.exit_code == 0
    assert res.error is None


@pytest.mark.asyncio
async def test_python_runtime_runtime_error() -> None:
    runtime = PythonRuntime()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.PYTHON,
        task_type=TaskType.CODE,
        payload={"code": "raise ValueError('Custom error message')"},
    )
    res = await runtime.execute(task, {})
    assert res.status == "FAILURE"
    assert res.exit_code != 0
    assert "ValueError" in res.stderr
    assert "Custom error message" in res.error


@pytest.mark.asyncio
async def test_python_runtime_timeout() -> None:
    runtime = PythonRuntime()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.PYTHON,
        task_type=TaskType.CODE,
        payload={"code": "import time\ntime.sleep(2)", "timeout": 0.2},
    )
    res = await runtime.execute(task, {})
    assert res.status == "FAILURE"
    assert res.exit_code == 124  # timeout code
    assert "timed out" in res.error


@pytest.mark.asyncio
async def test_python_runtime_file_path() -> None:
    runtime = PythonRuntime()
    fd, temp_file_path = tempfile.mkstemp(suffix=".py", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write("print('Hello from temp file')")

        task = Task(
            id=uuid4(),
            goal_id=uuid4(),
            executor=ExecutorType.PYTHON,
            task_type=TaskType.CODE,
            payload={"file_path": temp_file_path},
        )
        res = await runtime.execute(task, {})
        assert res.status == "SUCCESS"
        assert res.stdout.strip() == "Hello from temp file"
        assert res.exit_code == 0
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
