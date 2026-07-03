"""
PHASE: 16
STATUS: IMPLEMENTATION
SPECIFICATION:
    AGENTS.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from abc import ABC, abstractmethod

from audit.report import AuditResult


class Audit(ABC):
    """Abstract Base Class representing a single compliance/quality check.

    Every audit check must subclass this and implement the run method.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The short unique name/identifier for the audit check."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A brief description of what the audit check validates."""
        pass

    @abstractmethod
    async def run(self) -> AuditResult:
        """Execute the audit logic.

        Returns:
            An AuditResult detailing the outcome.
        """
        pass
