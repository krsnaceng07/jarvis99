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

import os
import tempfile
from uuid import uuid4

import pytest

from core.reasoning.task import ExecutorType, Task, TaskType
from core.tools.file_runtime import FileRuntime


@pytest.mark.asyncio
async def test_file_runtime_write_and_read() -> None:
    runtime = FileRuntime()
    # Temp file target
    fd, temp_file_path = tempfile.mkstemp(suffix=".txt", text=True)
    os.close(fd)  # close descriptor to let runtime write cleanly
    try:
        content_to_write = "JARVIS OS File System Test Content"

        # 1. Write
        task_write = Task(
            id=uuid4(),
            goal_id=uuid4(),
            executor=ExecutorType.FILE,
            task_type=TaskType.FILE_OP,
            payload={
                "operation": "write",
                "path": temp_file_path,
                "content": content_to_write,
            },
        )
        res_write = await runtime.execute(task_write, {})
        assert res_write.status == "SUCCESS"
        assert res_write.exit_code == 0

        # 2. Read
        task_read = Task(
            id=uuid4(),
            goal_id=uuid4(),
            executor=ExecutorType.FILE,
            task_type=TaskType.FILE_OP,
            payload={
                "operation": "read",
                "path": temp_file_path,
            },
        )
        res_read = await runtime.execute(task_read, {})
        assert res_read.status == "SUCCESS"
        assert res_read.stdout == content_to_write
        assert res_read.exit_code == 0
        assert res_read.artifacts["size"] == len(content_to_write)
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@pytest.mark.asyncio
async def test_file_runtime_move_and_info() -> None:
    runtime = FileRuntime()
    # Temp file setup
    fd, src_path = tempfile.mkstemp(suffix=".txt", text=True)
    os.close(fd)
    dst_path = src_path + ".moved"
    try:
        # Write content first
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("Move me")

        # 1. Move/Rename
        task_move = Task(
            id=uuid4(),
            goal_id=uuid4(),
            executor=ExecutorType.FILE,
            task_type=TaskType.FILE_OP,
            payload={
                "operation": "move",
                "source": src_path,
                "destination": dst_path,
            },
        )
        res_move = await runtime.execute(task_move, {})
        assert res_move.status == "SUCCESS"
        assert not os.path.exists(src_path)
        assert os.path.exists(dst_path)

        # 2. Info check
        task_info = Task(
            id=uuid4(),
            goal_id=uuid4(),
            executor=ExecutorType.FILE,
            task_type=TaskType.FILE_OP,
            payload={
                "operation": "info",
                "path": dst_path,
            },
        )
        res_info = await runtime.execute(task_info, {})
        assert res_info.status == "SUCCESS"
        assert res_info.artifacts["is_file"] is True
        assert res_info.artifacts["size"] == len("Move me")
    finally:
        if os.path.exists(src_path):
            os.remove(src_path)
        if os.path.exists(dst_path):
            os.remove(dst_path)


@pytest.mark.asyncio
async def test_file_runtime_search() -> None:
    runtime = FileRuntime()
    temp_dir = tempfile.mkdtemp()
    try:
        # Create a matching file
        test_file = os.path.join(temp_dir, "matching_test_file.log")
        with open(test_file, "w") as f:
            f.write("Log file content")

        task = Task(
            id=uuid4(),
            goal_id=uuid4(),
            executor=ExecutorType.FILE,
            task_type=TaskType.FILE_OP,
            payload={
                "operation": "search",
                "directory": temp_dir,
                "pattern": "*.log",
            },
        )
        res = await runtime.execute(task, {})
        assert res.status == "SUCCESS"
        assert test_file in res.artifacts["matches"]
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
        os.rmdir(temp_dir)
