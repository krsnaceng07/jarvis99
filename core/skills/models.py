"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M2 Repository)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship

from core.memory.models import Base


class InstalledSkillModel(Base):  # type: ignore[misc]
    """CRUD-only persistence model for installed skills."""

    __tablename__ = "installed_skills"

    id: Any = Column(String(100), primary_key=True)
    name: Any = Column(String(100), unique=True, nullable=False, index=True)
    version: Any = Column(String(20), nullable=False)
    status: Any = Column(String(30), nullable=False, index=True)
    trust_level: Any = Column(String(20), nullable=False, index=True)
    manifest_json: Any = Column(Text, nullable=False)
    checksum: Any = Column(String(64), nullable=False)
    signature: Any = Column(String(512), nullable=False)
    approval_level: Any = Column(String(5), nullable=False, default="L0")
    installed_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    capabilities: Mapped[list["SkillCapabilityModel"]] = relationship(
        "SkillCapabilityModel",
        back_populates="skill",
        cascade="all, delete-orphan",
    )
    versions: Mapped[list["SkillVersionModel"]] = relationship(
        "SkillVersionModel",
        back_populates="skill",
        cascade="all, delete-orphan",
    )


class SkillCapabilityModel(Base):  # type: ignore[misc]
    """Normalized capability index for fast capability search queries."""

    __tablename__ = "skill_capabilities"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    skill_id: Any = Column(
        String(100),
        ForeignKey("installed_skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability: Any = Column(String(120), nullable=False, index=True)

    skill: Mapped[InstalledSkillModel] = relationship(
        "InstalledSkillModel",
        back_populates="capabilities",
    )


class SkillVersionModel(Base):  # type: ignore[misc]
    """Append-only version history model for rollback/reproducibility metadata."""

    __tablename__ = "skill_versions"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    skill_id: Any = Column(
        String(100),
        ForeignKey("installed_skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Any = Column(String(20), nullable=False)
    status: Any = Column(String(30), nullable=False)
    reason: Any = Column(String(255), nullable=True)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    skill: Mapped[InstalledSkillModel] = relationship(
        "InstalledSkillModel",
        back_populates="versions",
    )
