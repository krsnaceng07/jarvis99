"""
PHASE: 41
STATUS: IMPLEMENTATION
SPECIFICATION:
    Goal #5 — Autonomous Multi-Agent Collaboration

Architecture:
    AgentRoleAssigner maps mission steps to specialized agent roles.
    It uses CapabilityNegotiator for load-aware assignment and
    AgentRegistry for tracking which agent holds which role.
    Does NOT replace existing negotiator — extends it with role semantics.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Specialized agent roles for mission decomposition."""

    RESEARCH = "research"
    CODING = "coding"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    PLANNING = "planning"
    REVIEW = "review"
    GENERAL = "general"


class RoleAssignment(BaseModel):
    """Maps an agent to a role for a specific mission wave."""

    agent_id: UUID
    role: AgentRole
    task_description: str
    wave_index: int = 0
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


_ROLE_KEYWORDS: Dict[AgentRole, List[str]] = {
    AgentRole.RESEARCH: [
        "research", "search", "find", "gather", "investigate",
        "analyze", "explore", "discover", "study", "survey",
    ],
    AgentRole.CODING: [
        "code", "implement", "build", "develop", "program",
        "create", "write code", "backend", "frontend", "api",
        "function", "class", "module", "refactor",
    ],
    AgentRole.TESTING: [
        "test", "verify", "validate", "check", "assert",
        "unit test", "integration", "qa", "debug", "fix bug",
    ],
    AgentRole.DOCUMENTATION: [
        "document", "readme", "docstring", "comment", "explain",
        "write doc", "specification", "guide", "tutorial",
    ],
    AgentRole.PLANNING: [
        "plan", "design", "architect", "structure", "organize",
        "decompose", "strategy", "roadmap",
    ],
    AgentRole.REVIEW: [
        "review", "audit", "inspect", "evaluate", "assess",
        "feedback", "approve",
    ],
}

_ROLE_CAPABILITIES: Dict[AgentRole, List[str]] = {
    AgentRole.RESEARCH: ["web_access", "memory", "file_read"],
    AgentRole.CODING: ["file_read", "file_write", "cli", "python"],
    AgentRole.TESTING: ["cli", "python", "file_read"],
    AgentRole.DOCUMENTATION: ["file_read", "file_write"],
    AgentRole.PLANNING: ["memory", "file_read"],
    AgentRole.REVIEW: ["file_read", "memory"],
    AgentRole.GENERAL: [],
}


class AgentRoleAssigner:
    """Assigns specialized roles to agents based on task descriptions.

    Uses keyword matching with optional LLM enhancement for ambiguous tasks.
    Integrates with AgentRegistry for capability-aware assignment.
    """

    def __init__(
        self,
        registry: Optional[Any] = None,
        negotiator: Optional[Any] = None,
        llm_runtime: Optional[Any] = None,
    ) -> None:
        self._registry = registry
        self._negotiator = negotiator
        self._llm_runtime = llm_runtime

    def classify_role(self, task_description: str) -> AgentRole:
        """Determine the best role for a task based on its description."""
        desc_lower = task_description.lower()
        scores: Dict[AgentRole, int] = {role: 0 for role in AgentRole}

        for role, keywords in _ROLE_KEYWORDS.items():
            for kw in keywords:
                if kw in desc_lower:
                    scores[role] += 1

        best_role = max(scores, key=lambda r: scores[r])
        if scores[best_role] == 0:
            return AgentRole.GENERAL

        return best_role

    async def classify_role_llm(self, task_description: str) -> AgentRole:
        """LLM-enhanced role classification for ambiguous tasks."""
        rule_role = self.classify_role(task_description)
        if rule_role != AgentRole.GENERAL or self._llm_runtime is None:
            return rule_role

        try:
            from core.tools.llm_runtime import LlmRequest

            roles_list = ", ".join(r.value for r in AgentRole if r != AgentRole.GENERAL)
            request = LlmRequest(
                prompt=(
                    f"Classify this task into one role: {roles_list}\n\n"
                    f"Task: {task_description}\n\n"
                    f"Return ONLY the role name (one word)."
                ),
                system_prompt="You are a task classifier. Return ONLY the role name.",
                category="reasoning",
                max_tokens=20,
                temperature=0.0,
            )
            response = await self._llm_runtime.generate(request)
            if response.text and not response.error:
                chosen = response.text.strip().lower().rstrip(".")
                try:
                    return AgentRole(chosen)
                except ValueError:
                    pass
        except Exception as e:
            logger.debug("LLM role classification failed: %s", e)

        return rule_role

    def get_role_capabilities(self, role: AgentRole) -> List[str]:
        """Return the required capabilities for a given role."""
        return _ROLE_CAPABILITIES.get(role, [])

    def assign_roles_to_wave(
        self,
        steps: List[Dict[str, Any]],
        wave_index: int = 0,
    ) -> List[RoleAssignment]:
        """Assign roles to all steps in a wave.

        Args:
            steps: List of step dicts with 'description' key.
            wave_index: Which wave these steps belong to.

        Returns:
            List of RoleAssignment with agent_id set to a placeholder
            (actual agent selection happens via CapabilityNegotiator).
        """
        from uuid import uuid4

        assignments: List[RoleAssignment] = []
        for step in steps:
            desc = step.get("description", "")
            role = self.classify_role(desc)
            assignments.append(
                RoleAssignment(
                    agent_id=uuid4(),
                    role=role,
                    task_description=desc,
                    wave_index=wave_index,
                    confidence=0.8 if role != AgentRole.GENERAL else 0.4,
                ),
            )
        return assignments

    async def assign_agent_for_role(
        self,
        role: AgentRole,
        task_description: str,
    ) -> Optional[UUID]:
        """Select the best available agent for a role using the negotiator."""
        if self._registry is None or self._negotiator is None:
            return None

        required_caps = self.get_role_capabilities(role)
        agents = self._registry.list_agents()

        best_id: Optional[UUID] = None
        best_score = -1.0

        for agent in agents:
            provided = set(agent.get("capabilities", []))
            if not set(required_caps).issubset(provided):
                continue

            if agent.get("status") == "OFFLINE":
                continue

            from core.runtime.dto import SwarmTask
            from uuid import uuid4

            dummy_task = SwarmTask(
                task_id=uuid4(),
                goal=task_description,
                capabilities=required_caps,
            )
            score = self._negotiator.score_agent(agent, dummy_task)
            if score > best_score:
                best_score = score
                best_id = agent.get("id")

        return best_id
