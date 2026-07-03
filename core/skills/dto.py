"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M0 DTO)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

TrustLevel = Literal["OFFICIAL", "VERIFIED", "COMMUNITY", "LOCAL"]
ApprovalLevel = Literal["L0", "L1", "L2", "L3"]
IsolationMode = Literal["process", "container", "vm"]
FilesystemMode = Literal["sandbox"]
SkillStatus = Literal[
    "DISCOVERED",
    "DOWNLOADED",
    "VERIFIED",
    "SANDBOX_TESTED",
    "APPROVED",
    "INSTALLED",
    "ACTIVE",
    "DISABLED",
    "REMOVED",
    "FAILED",
]


class SkillDependency(BaseModel):
    """Cross-skill dependency declaration with semver constraint."""

    skill: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=32)


class SkillCapability(BaseModel):
    """Single planner-discoverable capability in dotted namespace format."""

    key: str = Field(
        pattern=r"^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$",
        min_length=3,
        max_length=120,
    )
    description: Optional[str] = Field(default=None, max_length=300)


class SkillLimits(BaseModel):
    """Resource limits enforced by the sandbox runtime."""

    memory: str = Field(pattern=r"^\d+(MB|GB)$")
    cpu: str = Field(pattern=r"^\d+(\.\d+)?$")
    timeout: int = Field(ge=1, le=3600)
    network: bool = Field(default=False)
    filesystem: FilesystemMode = Field(default="sandbox")


class SkillCompatibility(BaseModel):
    """Platform/runtime compatibility matrix for install-time enforcement."""

    platforms: list[Literal["windows", "linux"]] = Field(min_length=1)
    architectures: list[Literal["x64", "arm64"]] = Field(min_length=1)
    python: str = Field(min_length=5, max_length=32)
    jarvis_runtime: str = Field(min_length=4, max_length=32)


class SkillManifest(BaseModel):
    """Frozen skill package metadata contract for Phase 18."""

    id: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    author: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    entrypoint: str = Field(default="main.py", min_length=1, max_length=120)
    permissions: list[str] = Field(min_length=1)
    dependencies: list[SkillDependency] = Field(default_factory=list)
    signature: str = Field(min_length=16, max_length=512)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    jarvis_api_version: str = Field(pattern=r"^\d+\.\d+$")
    min_runtime_version: str = Field(pattern=r"^\d+\.\d+$")
    approval_level: ApprovalLevel = Field(default="L0")
    trust_level: TrustLevel
    capabilities: list[SkillCapability] = Field(min_length=1)
    compatibility: SkillCompatibility
    limits: SkillLimits
    isolation: IsolationMode = Field(default="container")


class SkillMetadata(BaseModel):
    """Installed-skill metadata exposed via registry/API list endpoints."""

    id: str = Field(pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: SkillStatus
    trust_level: TrustLevel
    capabilities: list[str] = Field(default_factory=list)
    installed_at: Optional[str] = None
    updated_at: Optional[str] = None


class InstallSkillRequest(BaseModel):
    """Install request contract (M0 DTO only)."""

    skill_name: str = Field(pattern=r"^[a-z0-9_-]+$")
    source_url: Optional[str] = Field(default=None, max_length=500)
    version: Optional[str] = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    force: bool = Field(default=False)


class InstallSkillResponse(BaseModel):
    """Install response contract (M0 DTO only)."""

    skill_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: SkillStatus
    installed: bool = True


class RemoveSkillRequest(BaseModel):
    """Remove request contract (M0 DTO only)."""

    skill_name: str = Field(pattern=r"^[a-z0-9_-]+$")
    purge: bool = Field(default=False)


class UpdateSkillRequest(BaseModel):
    """Update request contract (M0 DTO only)."""

    skill_name: str = Field(pattern=r"^[a-z0-9_-]+$")
    target_version: Optional[str] = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")


class SearchSkillRequest(BaseModel):
    """Search request contract (M0 DTO only)."""

    query: str = Field(min_length=1, max_length=120)
    source: Literal["local", "remote", "all"] = "all"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchSkillResponse(BaseModel):
    """Search response contract (M0 DTO only)."""

    results: list[SkillMetadata] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
