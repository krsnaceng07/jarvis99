"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M5 Sandbox)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Literal

from pydantic import BaseModel, Field

SandboxStatus = Literal["PASSED", "FAILED"]


class SandboxViolation(BaseModel):
    """Policy or resource violation captured during sandbox execution."""

    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)


class SandboxResult(BaseModel):
    """Structured sandbox execution output for installer gating."""

    status: SandboxStatus
    exit_code: int
    duration_ms: int = Field(ge=0)
    memory_peak_mb: int = Field(ge=0)
    cpu_time_ms: int = Field(ge=0)
    stdout: str = ""
    stderr: str = ""
    violations: list[SandboxViolation] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
