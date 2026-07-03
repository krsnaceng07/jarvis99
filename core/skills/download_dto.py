"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M4 Downloader)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Immutable download source contract — arbitrary URLs are NOT accepted at this
layer. Sources must be marketplace ID, trusted repository, or local package.
"""

from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

DownloadSourceKind = Literal["marketplace", "trusted_repository", "local_package"]


class MarketplaceSkillSource(BaseModel):
    """Resolve package via official marketplace catalog by skill ID."""

    kind: Literal["marketplace"] = "marketplace"
    skill_id: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=100)
    version: Optional[str] = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")


class TrustedRepositorySkillSource(BaseModel):
    """Resolve package via an allowlisted trusted repository."""

    kind: Literal["trusted_repository"] = "trusted_repository"
    repository_id: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=100)
    skill_id: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=100)
    version: Optional[str] = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")


class LocalPackageSkillSource(BaseModel):
    """Use a pre-existing local package archive (offline / dev installs)."""

    kind: Literal["local_package"] = "local_package"
    package_path: str = Field(min_length=1, max_length=500)


SkillDownloadSource = Annotated[
    Union[
        MarketplaceSkillSource, TrustedRepositorySkillSource, LocalPackageSkillSource
    ],
    Field(discriminator="kind"),
]


class ResolvedPackageReference(BaseModel):
    """Provider-resolved fetch target used internally by the downloader."""

    source_kind: DownloadSourceKind
    skill_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    expected_checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    fetch_uri: str = Field(min_length=1, max_length=1000)


class DownloadedPackage(BaseModel):
    """Download result returned to higher-level install orchestration."""

    skill_id: str = Field(pattern=r"^[a-z0-9_-]+$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    source_kind: DownloadSourceKind
    package_path: str = Field(min_length=1, max_length=1000)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=1)

    @property
    def path(self) -> Path:
        """Convenience accessor for filesystem operations in later milestones."""
        return Path(self.package_path)
