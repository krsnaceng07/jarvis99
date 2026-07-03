"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M6 Permission Engine)

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M6 Permission Engine)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from core.interfaces import EventBusInterface, InterAgentMessage
from core.tools.security import PermissionGatekeeper

PermissionDecision = Literal[
    "AUTO_APPROVED", "AWAITING_APPROVAL", "REJECTED", "TIMEOUT"
]


@dataclass(frozen=True)
class PermissionEvaluation:
    """Result of evaluating a skill's declared permissions."""

    decision: PermissionDecision
    highest_level: str
    required_approvals: list[str]


class SkillPermissionEngine:
    """
    Evaluates skill permission declarations and coordinates with PermissionGatekeeper
    for human-in-the-loop approval of L2/L3 permissions.

    Responsibility: Evaluation and gating ONLY.
    - No database writes
    - No skill installation
    - No signature verification
    """

    def __init__(
        self,
        gatekeeper: PermissionGatekeeper,
        event_bus: EventBusInterface,
    ) -> None:
        self._gatekeeper = gatekeeper
        self._event_bus = event_bus

    def evaluate(self, permissions: list[str]) -> PermissionEvaluation:
        """
        Evaluate a skill's declared permissions without triggering approval flows.

        Returns:
            PermissionEvaluation with decision, highest level, and which permissions
            require human approval.
        """
        if not permissions:
            return PermissionEvaluation(
                decision="REJECTED",
                highest_level="L0",
                required_approvals=[],
            )

        levels = [self._gatekeeper.get_permission_level(p) for p in permissions]
        level_order = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
        highest = max(levels, key=lambda level: level_order.get(level, 3))

        requires_approval = [
            p for p, level in zip(permissions, levels) if level in {"L2", "L3"}
        ]

        if requires_approval:
            decision: PermissionDecision = "AWAITING_APPROVAL"
        elif highest in {"L0", "L1"}:
            decision = "AUTO_APPROVED"
        else:
            decision = "REJECTED"

        return PermissionEvaluation(
            decision=decision,
            highest_level=highest,
            required_approvals=requires_approval,
        )

    async def request_approvals(
        self,
        skill_id: str,
        caller_id: str,
        permissions: list[str],
    ) -> PermissionDecision:
        """
        Trigger human approval flow for L2/L3 permissions via PermissionGatekeeper.

        Publishes skill.approval.waiting and skill.approval.granted events per spec.
        Returns final decision after all approvals complete or timeout.
        """
        evaluation = self.evaluate(permissions)

        if evaluation.decision == "AUTO_APPROVED":
            return "AUTO_APPROVED"

        if evaluation.decision == "REJECTED":
            return "REJECTED"

        # Publish skill.approval.waiting event per spec §18.2
        waiting_msg = InterAgentMessage(
            id=uuid4(),
            correlation_id=uuid4(),
            sender="skill_permission_engine",
            receiver="user_interface",
            action="skill.approval.waiting",
            body={
                "skill_id": skill_id,
                "required_level": evaluation.highest_level,
                "permissions": evaluation.required_approvals,
                "caller_id": caller_id,
            },
        )
        await self._event_bus.publish("skill.approval.waiting", waiting_msg)

        # Trigger approval for each L2/L3 permission
        for perm in evaluation.required_approvals:
            try:
                await self._gatekeeper.verify_permissions(skill_id, perm, caller_id)
            except Exception:
                return "REJECTED"

        # Publish skill.approval.granted event
        granted_msg = InterAgentMessage(
            id=uuid4(),
            correlation_id=uuid4(),
            sender="skill_permission_engine",
            receiver="user_interface",
            action="skill.approval.granted",
            body={
                "skill_id": skill_id,
                "approved_level": evaluation.highest_level,
                "permissions": evaluation.required_approvals,
            },
        )
        await self._event_bus.publish("skill.approval.granted", granted_msg)

        return "AUTO_APPROVED"
