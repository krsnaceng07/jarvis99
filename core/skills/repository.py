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

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.skills.models import (
    InstalledSkillModel,
    SkillCapabilityModel,
    SkillVersionModel,
)


class SkillRepository:
    """CRUD-only persistence layer for skill records and lookup queries."""

    async def save_installed_skill(
        self,
        skill: InstalledSkillModel,
        session: AsyncSession,
    ) -> None:
        """Create or update an installed skill record."""
        session.add(skill)

    async def get_skill_by_id(
        self, skill_id: str, session: AsyncSession
    ) -> Optional[InstalledSkillModel]:
        """Fetch installed skill by stable ID."""
        stmt = (
            select(InstalledSkillModel)
            .where(InstalledSkillModel.id == skill_id)
            .options(
                selectinload(InstalledSkillModel.capabilities),
                selectinload(InstalledSkillModel.versions),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_skill_by_name(
        self, name: str, session: AsyncSession
    ) -> Optional[InstalledSkillModel]:
        """Fetch installed skill by unique name."""
        stmt = (
            select(InstalledSkillModel)
            .where(InstalledSkillModel.name == name)
            .options(
                selectinload(InstalledSkillModel.capabilities),
                selectinload(InstalledSkillModel.versions),
            )
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_skills(
        self, session: AsyncSession, limit: int = 50, offset: int = 0
    ) -> list[InstalledSkillModel]:
        """List installed skills sorted by install time descending."""
        stmt = (
            select(InstalledSkillModel)
            .order_by(InstalledSkillModel.installed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def update_skill_metadata(
        self,
        skill_id: str,
        session: AsyncSession,
        *,
        version: Optional[str] = None,
        status: Optional[str] = None,
        trust_level: Optional[str] = None,
        manifest_json: Optional[str] = None,
        checksum: Optional[str] = None,
        signature: Optional[str] = None,
        approval_level: Optional[str] = None,
    ) -> Optional[InstalledSkillModel]:
        """Patch selected mutable metadata fields for an installed skill."""
        model = await self.get_skill_by_id(skill_id, session)
        if not model:
            return None

        if version is not None:
            model.version = version
        if status is not None:
            model.status = status
        if trust_level is not None:
            model.trust_level = trust_level
        if manifest_json is not None:
            model.manifest_json = manifest_json
        if checksum is not None:
            model.checksum = checksum
        if signature is not None:
            model.signature = signature
        if approval_level is not None:
            model.approval_level = approval_level
        return model

    async def remove_skill(
        self, skill_id: str, session: AsyncSession
    ) -> Optional[InstalledSkillModel]:
        """Soft-delete by transitioning status to REMOVED."""
        model = await self.get_skill_by_id(skill_id, session)
        if model:
            model.status = "REMOVED"
        return model

    async def list_skills_by_capability(
        self, capability: str, session: AsyncSession
    ) -> list[InstalledSkillModel]:
        """Query skills that expose a given capability key."""
        stmt = (
            select(InstalledSkillModel)
            .join(SkillCapabilityModel)
            .where(SkillCapabilityModel.capability == capability)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def list_skills_by_trust_level(
        self, trust_level: str, session: AsyncSession
    ) -> list[InstalledSkillModel]:
        """Query skills by trust tier."""
        stmt = select(InstalledSkillModel).where(
            InstalledSkillModel.trust_level == trust_level
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def list_skills_by_status(
        self, status: str, session: AsyncSession
    ) -> list[InstalledSkillModel]:
        """Query skills by lifecycle status."""
        stmt = select(InstalledSkillModel).where(InstalledSkillModel.status == status)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def save_skill_capabilities(
        self, skill_id: str, capability_keys: list[str], session: AsyncSession
    ) -> None:
        """Replace normalized capability rows for a skill."""
        model = await self.get_skill_by_id(skill_id, session)
        if model is None:
            return
        model.capabilities = [
            SkillCapabilityModel(skill_id=skill_id, capability=cap)
            for cap in capability_keys
        ]

    async def append_skill_version(
        self,
        skill_id: str,
        version: str,
        status: str,
        session: AsyncSession,
        reason: Optional[str] = None,
    ) -> None:
        """Append version-history record for audit/rollback metadata."""
        session.add(
            SkillVersionModel(
                skill_id=skill_id,
                version=version,
                status=status,
                reason=reason,
            )
        )

    @staticmethod
    def serialize_manifest(manifest: dict) -> str:
        """Serialize manifest payload for persistence storage."""
        return json.dumps(manifest, sort_keys=True)
