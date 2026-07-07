"""JARVIS OS - Security and Permission Gatekeeper.

Defines the PermissionGatekeeper supporting human-in-the-loop approvals, secret injection, and SHA-256 signatures.
"""

import asyncio
import hashlib
import os
from typing import Dict, List, Set
from uuid import UUID, uuid4

from core.exceptions import JarvisSkillError
from core.interfaces import EventBusInterface, InterAgentMessage


class PermissionGatekeeper:
    """Inspects permission levels, handles human approval flows, and validates cryptographic signatures."""

    def __init__(
        self, event_bus: EventBusInterface, approval_timeout: float = 1800.0
    ) -> None:
        """Initialize PermissionGatekeeper.

        Args:
            event_bus: System event bus to publish approval requests.
            approval_timeout: Timeout in seconds to wait for human approval (default 30 minutes).
        """
        self.event_bus = event_bus
        self.approval_timeout = approval_timeout
        self._pending_approvals: Dict[UUID, asyncio.Future[bool]] = {}
        self.granted_permissions: Set[str] = set()

    def get_permission_level(self, permission_name: str) -> str:
        """Map a permission capability to its matching L0-L3 tier level.

        Args:
            permission_name: String capability (e.g. 'file_read', 'cli').

        Returns:
            Permission tier level ('L0', 'L1', 'L2', 'L3').
        """
        p_lower = permission_name.lower().strip()
        if p_lower in {"file_read", "database_query", "log_view", "network"}:
            return "L0"
        elif p_lower in {"file_write", "cache_write"}:
            return "L1"
        elif p_lower in {"database_schema_modify", "config_write"}:
            return "L2"
        elif p_lower in {"host_cli_exec", "browser_payment", "file_delete", "cli"}:
            return "L3"
        return "L3"  # Secure default fallback for unknown permissions

    async def verify_permissions(
        self, tool_name: str, permission_name: str, caller_id: str
    ) -> None:
        """Verify if a tool action is authorized, triggering human confirmation loops for L2/L3 actions.

        Args:
            tool_name: Target tool name.
            permission_name: Requested capability.
            caller_id: The UUID/ID of the requesting agent.

        Raises:
            JarvisSkillError: If the permission is rejected, or request times out.
        """
        cache_key = f"{tool_name}:{permission_name}:{caller_id}"
        if cache_key in self.granted_permissions:
            return

        level = self.get_permission_level(permission_name)
        if level in {"L0", "L1"}:
            return  # Autonomously authorized

        # Trigger human-in-the-loop confirmation loop
        correlation_id = uuid4()
        future = asyncio.get_running_loop().create_future()
        self._pending_approvals[correlation_id] = future

        try:
            request_msg = InterAgentMessage(
                id=uuid4(),
                correlation_id=correlation_id,
                sender="permission_gatekeeper",
                receiver="user_interface",
                action="tool.approval.requested",
                body={
                    "tool_name": tool_name,
                    "permission_name": permission_name,
                    "caller_id": caller_id,
                    "level": level,
                },
            )
            await self.event_bus.publish("tool.approval.requested", request_msg)

            # Await response with timeout
            approved = await asyncio.wait_for(future, timeout=self.approval_timeout)
            if not approved:
                raise JarvisSkillError(
                    code="SKILL_004",
                    message=f"Human permission request REJECTED for tool '{tool_name}' ({permission_name}).",
                )
            self.granted_permissions.add(cache_key)
        except asyncio.TimeoutError:
            raise JarvisSkillError(
                code="SKILL_004",
                message=f"Permission approval TIMEOUT ({self.approval_timeout}s) for tool '{tool_name}'.",
            )
        finally:
            self._pending_approvals.pop(correlation_id, None)

    def receive_approval_response(self, correlation_id: UUID, approved: bool) -> None:
        """Receive and process a human response from the Event Bus.

        Args:
            correlation_id: Correlation UUID of the request.
            approved: True if user approved execution, False otherwise.
        """
        future = self._pending_approvals.get(correlation_id)
        if future and not future.done():
            future.set_result(approved)

    def inject_scoped_secrets(
        self, allowed_keys: List[str], system_env: Dict[str, str]
    ) -> Dict[str, str]:
        """Extract only permitted secret keys to prevent full host environment exposure.

        Args:
            allowed_keys: List of config keys whitelisted for this tool.
            system_env: Global system environment dictionary.

        Returns:
            Dictionary containing only whitelisted environment keys.
        """
        return {k: system_env[k] for k in allowed_keys if k in system_env}

    @staticmethod
    def calculate_directory_hash(dir_path: str) -> str:
        """Compute a deterministic SHA-256 hash of all directory file contents, skipping manifest.json.

        Args:
            dir_path: Path to the target skill directory.

        Returns:
            Hex string of the SHA-256 checksum.
        """
        hasher = hashlib.sha256()
        for root, _, files in sorted(os.walk(dir_path)):
            for file in sorted(files):
                if file == "manifest.json":
                    continue
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "rb") as f:
                        while chunk := f.read(8192):
                            hasher.update(chunk)
                except Exception:
                    pass
        return hasher.hexdigest()

    @classmethod
    def verify_signature(cls, dir_path: str, expected_signature: str) -> bool:
        """Validate if a skill package's files match its registered signature.

        Args:
            dir_path: Path to the target skill directory.
            expected_signature: SHA-256 signature string.

        Returns:
            True if signatures match, False otherwise.
        """
        calculated = cls.calculate_directory_hash(dir_path)
        return calculated == expected_signature
