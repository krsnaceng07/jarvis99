"""JARVIS OS - Swarm Agent Registry.

Maintains centralized registration indices and permission manifest mappings for active subagents.
"""

from typing import Any, Dict, List, Set
from uuid import UUID

from core.exceptions import JarvisAgentError


class AgentPermissionManifest:
    """Specifies gated execution authorization zones for a subagent."""

    def __init__(self, permissions: Set[str]) -> None:
        """Initialize AgentPermissionManifest.

        Args:
            permissions: Allowed permission codes: 'Browser', 'Filesystem', 'Shell', etc.
        """
        self.allowed_permissions = permissions

    def has_permission(self, permission: str) -> bool:
        """Check if target permission is allowed.

        Args:
            permission: Permission identifier name.

        Returns:
            True if permission is permitted.
        """
        return permission in self.allowed_permissions


class AgentRegistry:
    """Tracks subagent profiles, capabilities, permissions, and active statuses."""

    def __init__(self) -> None:
        """Initialize AgentRegistry."""
        self.agents: Dict[UUID, Dict[str, Any]] = {}

    def register_agent(
        self,
        agent_id: UUID,
        name: str,
        capabilities: List[str],
        permissions: Set[str],
    ) -> None:
        """Add a subagent record to the registry.

        Args:
            agent_id: Subagent UUID.
            name: Human-friendly name.
            capabilities: Advertised functional capabilities.
            permissions: Gated manifest permission items.
        """
        self.agents[agent_id] = {
            "id": agent_id,
            "name": name,
            "capabilities": capabilities,
            "manifest": AgentPermissionManifest(permissions),
            "status": "ONLINE",
            "cpu_load": 0.0,
            "memory": 0.0,
            "recent_failures": 0,
        }

    def unregister_agent(self, agent_id: UUID) -> None:
        """Remove a subagent record from the registry.

        Args:
            agent_id: Subagent UUID.
        """
        self.agents.pop(agent_id, None)

    def get_agent(self, agent_id: UUID) -> Dict[str, Any]:
        """Fetch subagent record details.

        Args:
            agent_id: Target subagent ID.

        Returns:
            Agent record dictionary.

        Raises:
            JarvisAgentError: If agent record is missing.
        """
        agent = self.agents.get(agent_id)
        if not agent:
            raise JarvisAgentError(
                code="AGENT_999",
                message=f"Agent {agent_id} not registered.",
            )
        return agent

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all currently registered subagent records.

        Returns:
            List of agent records.
        """
        return list(self.agents.values())

    def update_status(self, agent_id: UUID, status: str) -> None:
        """Update active status code for registered agent.

        Args:
            agent_id: Target agent.
            status: Status string (e.g. 'IDLE', 'WORKING').
        """
        agent = self.agents.get(agent_id)
        if agent:
            agent["status"] = status
