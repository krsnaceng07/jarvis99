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
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.interfaces import AsyncSessionFactory
from core.skills.dto import SkillMetadata
from core.skills.models import (
    InstalledSkillModel,
    SkillCapabilityModel,
    SkillVersionModel,
)


class SkillRepository:
    """CRUD-only persistence layer for skill records and lookup queries.

    Sessions can be supplied by the caller (e.g. from a request-scoped
    FastAPI dependency) or opened on demand from the bound ``db_manager``.
    When a ``db_manager`` is provided at construction time, every method
    accepts ``session=None`` and opens/commits its own short-lived session
    internally. Callers that already hold a session can still pass it
    explicitly to participate in an outer transaction.
    """

    def __init__(self, db_manager: Optional[AsyncSessionFactory] = None) -> None:
        # ``db_manager`` is typed as the AsyncSessionFactory Protocol
        # (core.interfaces) so a mis-typed factory is caught by mypy at
        # construction time, without coupling to core.memory (no import cycle).
        self._db_manager = db_manager

    @asynccontextmanager
    async def _scoped_session(
        self, session: Optional[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        """Yield the caller's session or open a short-lived one.

        When the repository opens its own session, the operation is committed
        on clean exit and rolled back on any exception (including
        :class:`asyncio.CancelledError`, which is ``BaseException``-derived in
        Python 3.8+ and is therefore not caught by the plain ``except
        Exception`` clause). Cancellation is logged at DEBUG to aid debugging
        of aborted background operations.
        """
        if session is not None:
            yield session
            return
        if self._db_manager is None:
            raise RuntimeError(
                "SkillRepository requires either an explicit AsyncSession or "
                "a bound db_manager (passed at construction time)."
            )
        async with self._db_manager.session() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
            except BaseException as cancel_exc:  # CancelledError, KeyboardInterrupt
                await s.rollback()
                import logging

                _logger = logging.getLogger("jarvis.core.skills.repository")
                _logger.debug(
                    "SkillRepository._scoped_session cancelled: %s", cancel_exc
                )
                raise

    async def save_installed_skill(
        self,
        skill: InstalledSkillModel,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Create or update an installed skill record."""
        async with self._scoped_session(session) as s:
            s.add(skill)

    async def get_skill_by_id(
        self, skill_id: str, session: Optional[AsyncSession] = None
    ) -> Optional[InstalledSkillModel]:
        """Fetch installed skill by stable ID."""
        async with self._scoped_session(session) as s:
            stmt = (
                select(InstalledSkillModel)
                .where(InstalledSkillModel.id == skill_id)
                .options(
                    selectinload(InstalledSkillModel.capabilities),
                    selectinload(InstalledSkillModel.versions),
                )
            )
            res = await s.execute(stmt)
            return res.scalar_one_or_none()

    async def get_skill_by_name(
        self, name: str, session: Optional[AsyncSession] = None
    ) -> Optional[InstalledSkillModel]:
        """Fetch installed skill by unique name."""
        async with self._scoped_session(session) as s:
            stmt = (
                select(InstalledSkillModel)
                .where(InstalledSkillModel.name == name)
                .options(
                    selectinload(InstalledSkillModel.capabilities),
                    selectinload(InstalledSkillModel.versions),
                )
            )
            res = await s.execute(stmt)
            return res.scalar_one_or_none()

    async def list_skills(
        self,
        session: Optional[AsyncSession] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InstalledSkillModel]:
        """List installed skills sorted by install time descending."""
        async with self._scoped_session(session) as s:
            stmt = (
                select(InstalledSkillModel)
                .order_by(InstalledSkillModel.installed_at.desc())
                .limit(limit)
                .offset(offset)
            )
            res = await s.execute(stmt)
            return list(res.scalars().all())

    async def update_skill_metadata(
        self,
        skill_id: str,
        session: Optional[AsyncSession] = None,
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
        async with self._scoped_session(session) as s:
            model = await self.get_skill_by_id(skill_id, s)
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
        self, skill_id: str, session: Optional[AsyncSession] = None
    ) -> Optional[InstalledSkillModel]:
        """Soft-delete by transitioning status to REMOVED."""
        async with self._scoped_session(session) as s:
            model = await self.get_skill_by_id(skill_id, s)
            if model:
                model.status = "REMOVED"
            return model

    async def list_skills_by_capability(
        self, capability: str, session: Optional[AsyncSession] = None
    ) -> list[InstalledSkillModel]:
        """Query skills that expose a given capability key."""
        async with self._scoped_session(session) as s:
            stmt = (
                select(InstalledSkillModel)
                .join(SkillCapabilityModel)
                .where(SkillCapabilityModel.capability == capability)
            )
            res = await s.execute(stmt)
            return list(res.scalars().all())

    async def list_skills_by_trust_level(
        self, trust_level: str, session: Optional[AsyncSession] = None
    ) -> list[InstalledSkillModel]:
        """Query skills by trust tier."""
        async with self._scoped_session(session) as s:
            stmt = select(InstalledSkillModel).where(
                InstalledSkillModel.trust_level == trust_level
            )
            res = await s.execute(stmt)
            return list(res.scalars().all())

    async def list_skills_by_status(
        self, status: str, session: Optional[AsyncSession] = None
    ) -> list[InstalledSkillModel]:
        """Query skills by lifecycle status."""
        async with self._scoped_session(session) as s:
            stmt = select(InstalledSkillModel).where(
                InstalledSkillModel.status == status
            )
            res = await s.execute(stmt)
            return list(res.scalars().all())

    async def save_skill_capabilities(
        self,
        skill_id: str,
        capability_keys: list[str],
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Replace normalized capability rows for a skill."""
        async with self._scoped_session(session) as s:
            model = await self.get_skill_by_id(skill_id, s)
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
        session: Optional[AsyncSession] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Append version-history record for audit/rollback metadata."""
        async with self._scoped_session(session) as s:
            s.add(
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

    async def list_all_as_metadata(
        self, session: Optional[AsyncSession] = None
    ) -> list[SkillMetadata]:
        """Return all installed skills as SkillMetadata records (boot hydration).

        Filters to active lifecycle states (ACTIVE / INSTALLED / REGISTERED) so
        the in-memory SkillRegistry rebuild matches what a fresh process would
        have visible. Returns an empty list on a fresh database.
        """
        active_statuses = ("ACTIVE", "INSTALLED", "REGISTERED")
        async with self._scoped_session(session) as s:
            stmt = select(InstalledSkillModel).where(
                InstalledSkillModel.status.in_(active_statuses)
            )
            res = await s.execute(stmt)
            models = list(res.scalars().all())

        out: list[SkillMetadata] = []
        for m in models:
            capabilities = [
                getattr(c, "capability", None) or "" for c in (m.capabilities or [])
            ]
            capabilities = [c for c in capabilities if c]
            installed_iso = m.installed_at.isoformat() if m.installed_at else None
            updated_iso = m.updated_at.isoformat() if m.updated_at else None
            out.append(
                SkillMetadata(
                    id=m.id,
                    name=m.name,
                    version=m.version,
                    status=m.status,  # type: ignore[arg-type]
                    trust_level=m.trust_level,  # type: ignore[arg-type]
                    capabilities=capabilities,
                    installed_at=installed_iso,
                    updated_at=updated_iso,
                )
            )
        return out
