"""JARVIS OS - Workflow Automation Repository.

Handles database schema definition, version logging, SHA-256 checksum integrity verification,
soft-delete filters, and transactional CRUD logic.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Uuid, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.models import Base
from core.tools.workflow_dto import WorkflowPlan, WorkflowVersion


class WorkflowModel(Base):  # type: ignore[misc]
    """SQLAlchemy model representing the active workflow plan configurations."""

    __tablename__ = "workflows"

    id: Any = Column(Uuid(as_uuid=True), primary_key=True)
    name: Any = Column(String(255), nullable=False)
    version: Any = Column(Integer, nullable=False, default=1)
    definition: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    checksum: Any = Column(String(64), nullable=False)
    is_deleted: Any = Column(Boolean, default=False, nullable=False)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Any = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class WorkflowVersionModel(Base):  # type: ignore[misc]
    """SQLAlchemy model logging history configurations per workflow version."""

    __tablename__ = "workflow_versions"

    id: Any = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Any = Column(Uuid(as_uuid=True), nullable=False)
    version: Any = Column(Integer, nullable=False)
    definition: Any = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    checksum: Any = Column(String(64), nullable=False)
    created_at: Any = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class WorkflowRepository:
    """Repository layer responsible for persistence, version history tracking, and integrity auditing."""

    async def create_tables(self, session: AsyncSession) -> None:
        """Create database tables dynamically if they do not exist."""
        bind = session.bind
        if bind:
            from typing import cast

            async with cast(Any, bind).connect() as conn:
                await conn.run_sync(Base.metadata.create_all)

    async def save(self, plan: WorkflowPlan, session: AsyncSession) -> WorkflowVersion:
        """Persist a WorkflowPlan config and log a new version snapshot.

        Calculates SHA-256 of the JSON layout. If plan exists but checksum differs,
        increments version count. If checksum is identical, skips write.

        Args:
            plan: The WorkflowPlan model.
            session: SQLAlchemy async database session.

        Returns:
            The saved WorkflowVersion metadata DTO.
        """
        raw_dump = plan.model_dump(mode="json")
        # Canonicalize JSON string for stable SHA-256 calculation
        raw_str = json.dumps(raw_dump, sort_keys=True, default=str)
        checksum = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

        # Check if active workflow exists (including soft-deleted)
        q = select(WorkflowModel).where(WorkflowModel.id == plan.workflow_id)
        res = await session.execute(q)
        model = res.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if not model:
            # Create new workflow record
            model = WorkflowModel(
                id=plan.workflow_id,
                name=plan.name,
                version=plan.version,
                definition=raw_dump,
                checksum=checksum,
                is_deleted=False,
                created_at=now,
                updated_at=now,
            )
            session.add(model)

            # Create version history record
            ver_model = WorkflowVersionModel(
                workflow_id=plan.workflow_id,
                version=plan.version,
                definition=raw_dump,
                checksum=checksum,
                created_at=now,
            )
            session.add(ver_model)
        else:
            # If checksum is unchanged, return existing version directly
            if model.checksum == checksum:
                return WorkflowVersion(
                    workflow_id=model.id,
                    version=model.version,
                    created_at=model.created_at,
                    updated_at=model.updated_at,
                    checksum=model.checksum,
                )

            # Checksum differs: increment version and restore if soft-deleted
            new_version = model.version + 1
            model.name = plan.name
            model.version = new_version
            model.definition = raw_dump
            model.checksum = checksum
            model.is_deleted = False
            model.updated_at = now

            # Create new version record
            ver_model = WorkflowVersionModel(
                workflow_id=plan.workflow_id,
                version=new_version,
                definition=raw_dump,
                checksum=checksum,
                created_at=now,
            )
            session.add(ver_model)

        await session.flush()

        return WorkflowVersion(
            workflow_id=model.id,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
            checksum=model.checksum,
        )

    async def get(
        self, workflow_id: UUID, session: AsyncSession
    ) -> Optional[WorkflowPlan]:
        """Fetch the active WorkflowPlan definition.

        Args:
            workflow_id: UUID target.
            session: SQLAlchemy session.

        Returns:
            The parsed WorkflowPlan model if exists and not soft-deleted, else None.
        """
        q = select(WorkflowModel).where(
            WorkflowModel.id == workflow_id, WorkflowModel.is_deleted.is_(False)
        )
        res = await session.execute(q)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return WorkflowPlan(**model.definition)

    async def get_version(
        self, workflow_id: UUID, version: int, session: AsyncSession
    ) -> Optional[WorkflowPlan]:
        """Fetch a specific historical WorkflowPlan configuration.

        Args:
            workflow_id: UUID target.
            version: Target version index.
            session: SQLAlchemy session.

        Returns:
            The parsed WorkflowPlan model if exists, else None.
        """
        q = select(WorkflowVersionModel).where(
            WorkflowVersionModel.workflow_id == workflow_id,
            WorkflowVersionModel.version == version,
        )
        res = await session.execute(q)
        model = res.scalar_one_or_none()
        if not model:
            return None
        return WorkflowPlan(**model.definition)

    async def list_versions(
        self, workflow_id: UUID, session: AsyncSession
    ) -> List[WorkflowVersion]:
        """List all historical version logs for a workflow.

        Args:
            workflow_id: UUID target.
            session: SQLAlchemy session.

        Returns:
            List of WorkflowVersion DTO objects.
        """
        q = (
            select(WorkflowVersionModel)
            .where(WorkflowVersionModel.workflow_id == workflow_id)
            .order_by(WorkflowVersionModel.version.asc())
        )
        res = await session.execute(q)
        records = res.scalars().all()
        return [
            WorkflowVersion(
                workflow_id=r.workflow_id,
                version=r.version,
                created_at=r.created_at,
                updated_at=r.created_at,
                checksum=r.checksum,
            )
            for r in records
        ]

    async def delete(self, workflow_id: UUID, session: AsyncSession) -> bool:
        """Soft-delete an active workflow configuration.

        Args:
            workflow_id: UUID target.
            session: SQLAlchemy session.

        Returns:
            True if found and soft-deleted, False otherwise.
        """
        q = select(WorkflowModel).where(WorkflowModel.id == workflow_id)
        res = await session.execute(q)
        model = res.scalar_one_or_none()
        if not model or model.is_deleted:
            return False

        model.is_deleted = True
        await session.flush()
        return True

    async def list_active(self, session: AsyncSession) -> List[WorkflowPlan]:
        """List all active (non soft-deleted) workflows.

        Args:
            session: SQLAlchemy session.

        Returns:
            List of parsed WorkflowPlan configurations.
        """
        q = select(WorkflowModel).where(WorkflowModel.is_deleted.is_(False))
        res = await session.execute(q)
        records = res.scalars().all()
        return [WorkflowPlan(**r.definition) for r in records]
