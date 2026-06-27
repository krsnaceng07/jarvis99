"""JARVIS OS - Execution Orchestrator.

Mediates planning steps and physical tool executions under permissions, auditing, and cancellation contexts.
"""

import asyncio
import time
from typing import Any, Dict, Optional

from core.config import Settings
from core.exceptions import JarvisSkillError
from core.reasoning.planner import ReasoningSession
from core.tools.base import ToolExecutionResult
from core.tools.runtime import ToolRuntime


class ExecutionOrchestrator:
    """Mediator separating Planner logic from direct tool/sandbox runtime executions."""

    def __init__(self, tool_runtime: ToolRuntime, settings: Settings) -> None:
        """Initialize ExecutionOrchestrator.

        Args:
            tool_runtime: Fully initialized ToolRuntime instance.
            settings: Settings configuration instance.
        """
        self.tool_runtime = tool_runtime
        self.settings = settings

    async def execute_task_step(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session: ReasoningSession,
        caller_id: str = "orchestrator",
        system_env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Execute a single plan step using the ToolRuntime, incorporating retries and tracing.

        Args:
            tool_name: Registered skill/tool name.
            arguments: Parameter mapping.
            session: Active ReasoningSession context tracker.
            caller_id: Caller agent identification.
            system_env: Optional environment key-value mappings.

        Returns:
            Dictionary payload summary of tool execution.
        """
        attempts = 0
        max_retries = 2
        last_error = None
        start_time = time.perf_counter()

        while attempts <= max_retries:
            try:
                # Direct tool run
                result: ToolExecutionResult = await self.tool_runtime.execute_tool(
                    tool_name=tool_name,
                    arguments=arguments,
                    caller_id=caller_id,
                    system_env=system_env,
                )

                duration_ms = (time.perf_counter() - start_time) * 1000.0
                session.latency_ms += duration_ms

                # Record tool trace log
                trace_entry = {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "status": "success" if result.exit_code == 0 else "failure",
                    "exit_code": result.exit_code,
                    "duration_s": result.duration,
                    "error": None if result.exit_code == 0 else "Non-zero exit code",
                }
                session.tool_calls.append(trace_entry)

                return {
                    "status": "SUCCESS" if result.exit_code == 0 else "FAILURE",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                }

            except JarvisSkillError as err:
                attempts += 1
                last_error = err
                await asyncio.sleep(0.01)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        session.latency_ms += duration_ms

        # Record failed tool trace log
        trace_entry = {
            "tool_name": tool_name,
            "arguments": arguments,
            "status": "error",
            "exit_code": -1,
            "duration_s": 0.0,
            "error": str(last_error),
        }
        session.tool_calls.append(trace_entry)

        return {
            "status": "ERROR",
            "error": str(last_error),
            "exit_code": -1,
        }
