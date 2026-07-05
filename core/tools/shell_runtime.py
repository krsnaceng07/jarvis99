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
import time
from typing import Any, Dict

from core.reasoning.task import Task
from core.tools.dto import ToolExecutionResult


class ShellRuntime:
    """Executes system shell commands across platforms (Windows / Linux / macOS)."""

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        start_time = time.perf_counter()
        command = task.payload.get("command") or ""
        timeout = float(task.payload.get("timeout", task.timeout or 30.0))
        cwd = task.payload.get("cwd") or os.getcwd()
        env = task.payload.get("env") or {}

        if not command:
            return ToolExecutionResult(
                task_id=task.id,
                status="FAILURE",
                stdout="",
                stderr="No shell command provided.",
                exit_code=1,
                duration=time.perf_counter() - start_time,
                error="No command to execute",
            )

        # Merge system environment with task specific environment variables
        merged_env = os.environ.copy()
        for k, v in env.items():
            merged_env[str(k)] = str(v)

        try:
            # Enforce shell execution using subprocess shell
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=merged_env,
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
                error_msg = f"Command timed out after {timeout} seconds."
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
