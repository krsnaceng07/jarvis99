"""JARVIS OS - Tool Runtime Engine.

Orchestrates the tool execution lifecycle, verifying permissions, injecting secrets, triggering sandboxes, and logging audits.
"""

import time
from typing import Any, Dict, Optional
from uuid import uuid4

from core.exceptions import JarvisSkillError
from core.interfaces import EventBusInterface, InterAgentMessage
from core.tools.base import ToolExecutionResult
from core.tools.registry import ToolRegistry
from core.tools.sandbox import ISandbox
from core.tools.security import PermissionGatekeeper


class ToolRuntime:
    """Core runtime coordinating whitelisted sandbox runs, human approvals, and immutable log commits."""

    def __init__(
        self,
        registry: ToolRegistry,
        sandbox: ISandbox,
        gatekeeper: PermissionGatekeeper,
        event_bus: EventBusInterface,
        audit_logger: Optional[Any] = None,
    ) -> None:
        """Initialize ToolRuntime.

        Args:
            registry: The tool discoverability registry.
            sandbox: Container or subprocess executor sandbox.
            gatekeeper: Checks permission levels and digital signatures.
            event_bus: The global event bus dispatcher.
            audit_logger: Optional immutable audit logger.
        """
        self.registry = registry
        self.sandbox = sandbox
        self.gatekeeper = gatekeeper
        self.event_bus = event_bus
        self.audit_logger = audit_logger

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        caller_id: str,
        system_env: Optional[Dict[str, str]] = None,
    ) -> ToolExecutionResult:
        """Verify permissions, inject scoped secrets, run whitelisted sandbox, and commit write-once logs.

        Args:
            tool_name: Registered skill/tool name.
            arguments: Dictionary parameter payload. Must specify 'command' for sandbox execute.
            caller_id: Requester agent ID.
            system_env: Global system environment variables.

        Returns:
            Strongly typed ToolExecutionResult DTO.

        Raises:
            JarvisSkillError: If permissions are denied, timeouts occur, or registry errors happen.
        """
        # 1. Discover tool manifest
        manifest = self.registry.get_skill(tool_name)
        if not manifest:
            raise JarvisSkillError(
                code="SKILL_008",
                message=f"Tool '{tool_name}' is not registered in the system.",
            )

        # 2. Check Permission gates (L0-L3 approval protocol)
        for permission in manifest.permissions:
            await self.gatekeeper.verify_permissions(tool_name, permission, caller_id)

        # 3. Extract whitelisted configuration keys to inject as scoped secrets
        scoped_env = self.gatekeeper.inject_scoped_secrets(
            manifest.dependencies, system_env or {}
        )

        # 4. Sandbox invocation
        # Since dynamic imports are disabled, we run command scripts inside the whitelisted shell image
        command = arguments.get("command") or [
            "python",
            "-c",
            f"print('Executed {tool_name}')",
        ]
        image = arguments.get("image") or "python:3.12-slim"
        timeout = float(arguments.get("timeout", 10.0))

        start_time = time.time()
        sandbox_res = await self.sandbox.run(
            image=image,
            command=command,
            env=scoped_env,
            timeout=timeout,
            network_access=manifest.network_access,
        )
        duration = time.time() - start_time

        audit_id = uuid4()

        # 5. Commit audit logs
        if self.audit_logger:
            await self.audit_logger.log_invocation(
                audit_id=audit_id,
                tool_name=tool_name,
                caller_id=caller_id,
                arguments=arguments,
                result=sandbox_res,
            )

        # 6. Instantiate return DTO
        result_dto = ToolExecutionResult(
            stdout=sandbox_res.get("stdout", ""),
            stderr=sandbox_res.get("stderr", ""),
            exit_code=sandbox_res.get("exit_code", 0),
            duration=sandbox_res.get("duration", duration),
            memory_usage=sandbox_res.get("memory_usage", 0),
            cpu_usage=sandbox_res.get("cpu_usage", 0.0),
            truncated=sandbox_res.get("truncated", False),
            audit_id=audit_id,
        )

        # 7. Notify system event bus
        event_msg = InterAgentMessage(
            id=uuid4(),
            correlation_id=uuid4(),
            sender="tool_runtime",
            receiver="system_broadcast",
            action="system.tool.executed",
            body={
                "tool_name": tool_name,
                "caller_id": caller_id,
                "exit_code": result_dto.exit_code,
                "duration": result_dto.duration,
                "audit_id": str(audit_id),
            },
        )
        await self.event_bus.publish("system.tool.executed", event_msg)

        # Publish tool.executed event asynchronously for Phase 40
        if self.event_bus:
            try:
                status_str = "SUCCESS" if result_dto.exit_code == 0 else "FAILURE"
                tool_executed_msg = InterAgentMessage(
                    sender="tool_runtime",
                    receiver="all",
                    action="tool.executed",
                    body={
                        "node_id": caller_id,
                        "task_type": "tool",
                        "status": status_str,
                        "exit_code": result_dto.exit_code,
                        "stdout": result_dto.stdout,
                        "stderr": result_dto.stderr,
                        "error": None,
                    },
                    correlation_id=uuid4(),
                )
                await self.event_bus.publish("tool.executed", tool_executed_msg)
            except Exception as e:
                import logging
                logging.getLogger("jarvis.core.tools.runtime").error(
                    "Failed to publish tool.executed event: %s", e
                )

        return result_dto
