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

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class AuditStatus(str, Enum):
    """Execution status for an audit check."""

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class AuditResult(BaseModel):
    """Outcome of a single audit check module execution."""

    name: str = Field(..., description="Unique check identifier (e.g. 'architecture')")
    status: AuditStatus = Field(..., description="Result severity")
    message: str = Field(..., description="Summary message of the outcome")
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Metadata and raw issues found"
    )
    duration_seconds: float = Field(0.0, description="Time taken to execute the audit")


class AuditReport(BaseModel):
    """Aggregated compliance report containing all check results."""

    overall_status: AuditStatus = Field(
        ..., description="Overall status (FAIL if any individual check failed)"
    )
    results: List[AuditResult] = Field(
        default_factory=list, description="List of all run audits"
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ISO-8601 UTC timestamp of audit completion",
    )
