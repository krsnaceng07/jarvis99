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
import sys
import time
from typing import Any, Dict

from core.reasoning.task import Task
from core.tools.dto import ToolExecutionResult


class HumanRuntime:
    """Handles Human-in-the-loop approvals and direct interactive input prompts."""

    async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
        start_time = time.perf_counter()
        prompt = (
            task.payload.get("prompt")
            or task.payload.get("instruction")
            or "Approval required."
        )
        timeout = float(task.payload.get("timeout", task.timeout or 300.0))

        # Check if auto-approve is active via task payload or global context config
        auto_approve = task.payload.get("auto_approve")
        if auto_approve is None:
            auto_approve = context.get("auto_approve", False)

        stdout = ""
        stderr = ""
        exit_code = 0
        error_msg = None
        artifacts: Dict[str, Any] = {}

        if auto_approve:
            stdout = f"Auto-approved: {prompt}"
            artifacts["approved"] = True
            artifacts["approver"] = "system_auto_approve"
            artifacts["timestamp"] = time.time()
        else:
            # Interactive read via a thread-pool to keep event loop responsive
            loop = asyncio.get_running_loop()
            print(f"\n[JARVIS HUMAN APPROVAL REQUIRED] {prompt}", file=sys.stderr)
            print(
                "Type 'yes' / 'approve' to proceed, or anything else to reject: ",
                end="",
                file=sys.stderr,
                flush=True,
            )

            def _get_input() -> str:
                try:
                    return sys.stdin.readline().strip()
                except Exception as e:
                    return f"error: {str(e)}"

            try:
                user_input = await asyncio.wait_for(
                    loop.run_in_executor(None, _get_input), timeout=timeout
                )
                if user_input.lower() in ("yes", "y", "approve", "ok"):
                    stdout = f"Human approved: {prompt}"
                    artifacts["approved"] = True
                    artifacts["approver"] = "human_user"
                    artifacts["response"] = user_input
                else:
                    exit_code = 1
                    stdout = f"Human rejected request: {prompt}"
                    error_msg = f"Rejected by user: {user_input}"
                    stderr = error_msg
                    artifacts["approved"] = False
                    artifacts["response"] = user_input
            except asyncio.TimeoutError:
                exit_code = 1
                error_msg = f"Human approval timed out after {timeout} seconds."
                stderr = error_msg
                stdout = f"Timeout waiting for approval: {prompt}"
                artifacts["approved"] = False
                artifacts["timeout"] = True

        return ToolExecutionResult(
            task_id=task.id,
            status="SUCCESS" if exit_code == 0 else "FAILURE",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration=time.perf_counter() - start_time,
            artifacts=artifacts,
            error=error_msg,
        )
