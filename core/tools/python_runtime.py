"""
PHASE: 23
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/82_PHASE_22_ORCHESTRATOR_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import asyncio
import os
import sys
import tempfile
import time
from typing import Any, Dict

from core.reasoning.task import Task
from core.tools.dto import ToolExecutionResult


class PythonRuntime:
    """Executes arbitrary Python code safely using a subprocess runner in the active environment."""

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        start_time = time.perf_counter()
        code = task.payload.get("code") or task.payload.get("instruction") or ""
        timeout = float(task.payload.get("timeout", task.timeout or 30.0))

        # Handle file execution case if code is not provided but file_path is
        if not code and "file_path" in task.payload:
            file_path = task.payload["file_path"]
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    code = f.read()
            else:
                return ToolExecutionResult(
                    task_id=task.id,
                    status="FAILURE",
                    stdout="",
                    stderr=f"File not found: {file_path}",
                    exit_code=1,
                    duration=time.perf_counter() - start_time,
                    error=f"File not found: {file_path}",
                )

        if not code:
            return ToolExecutionResult(
                task_id=task.id,
                status="FAILURE",
                stdout="",
                stderr="No python code provided to execute.",
                exit_code=1,
                duration=time.perf_counter() - start_time,
                error="No code to execute",
            )

        # Write code to a temporary file
        fd, temp_file_path = tempfile.mkstemp(suffix=".py", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                tmp.write(code)

            # Use active python environment executable
            python_exe = sys.executable

            # Run python subprocess
            proc = await asyncio.create_subprocess_exec(
                python_exe,
                temp_file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                exit_code = proc.returncode or 0
                error_msg = None
                if exit_code != 0:
                    error_msg = stderr_bytes.decode("utf-8", errors="replace").strip()
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                stdout_bytes, stderr_bytes = await proc.communicate()
                await proc.wait()
                exit_code = 124  # timeout code
                error_msg = f"Execution timed out after {timeout} seconds."
            else:
                if proc.returncode is None:
                    await proc.wait()

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Output limits truncation (e.g. 1MB)
            limit = 1024 * 1024
            truncated = False
            if len(stdout) > limit:
                stdout = stdout[:limit] + "\n[OUTPUT TRUNCATED]"
                truncated = True
            if len(stderr) > limit:
                stderr = stderr[:limit] + "\n[OUTPUT TRUNCATED]"
                truncated = True

            return ToolExecutionResult(
                task_id=task.id,
                status="SUCCESS" if exit_code == 0 else "FAILURE",
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration=time.perf_counter() - start_time,
                truncated=truncated,
                error=error_msg,
            )

        except Exception as e:
            return ToolExecutionResult(
                task_id=task.id,
                status="FAILURE",
                stdout="",
                stderr=str(e),
                exit_code=1,
                duration=time.perf_counter() - start_time,
                error=str(e),
            )
        finally:
            try:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
            except Exception:
                pass
