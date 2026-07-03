"""JARVIS OS - Relational Memory Storage Repository.

Implements PostgresMemoryRepository conforming to the IMemoryRepository contract.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.interfaces import IMemoryRepository, MemoryChunkDTO, MemorySourceDTO
from core.memory.models import (
    MemoryChunk,
    MemorySource,
    to_chunk_dto,
    to_source_dto,
)


class PostgresMemoryRepository(IMemoryRepository):
    """Database repository implementing relational persistent storage for memories."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with active session.

        Args:
            session: Active database AsyncSession.
        """
        self.session = session

    async def get_source(self, source_id: UUID) -> Optional[MemorySourceDTO]:
        """Retrieve a memory source metadata record by ID."""
        stmt = select(MemorySource).where(MemorySource.id == source_id)
        res = await self.session.execute(stmt)
        source = res.scalar_one_or_none()
        if source:
            return to_source_dto(source)
        return None

    async def create_source(self, source: MemorySourceDTO) -> MemorySourceDTO:
        """Store a new memory source metadata record."""
        db_source = MemorySource(
            id=source.id,
            source_type=source.source_type,
            uri=source.uri,
            timestamp=source.timestamp,
            agent_id=source.agent_id,
            confidence=source.confidence,
            version=source.version,
        )
        self.session.add(db_source)
        # Flush to persist transaction without final commit
        await self.session.flush()
        return to_source_dto(db_source)

    async def get_chunk(self, chunk_id: UUID) -> Optional[MemoryChunkDTO]:
        """Retrieve a single active memory chunk by ID."""
        stmt = select(MemoryChunk).where(
            MemoryChunk.id == chunk_id, MemoryChunk.is_deleted.is_(False)
        )
        res = await self.session.execute(stmt)
        chunk = res.scalar_one_or_none()
        if chunk:
            return to_chunk_dto(chunk)
        return None

    async def get_chunk_by_hash(self, content_hash: str) -> Optional[MemoryChunkDTO]:
        """Check for identical content hash to prevent duplicate writes."""
        stmt = select(MemoryChunk).where(
            MemoryChunk.content_hash == content_hash,
            MemoryChunk.is_deleted.is_(False),
        )
        res = await self.session.execute(stmt)
        chunk = res.scalar_one_or_none()
        if chunk:
            return to_chunk_dto(chunk)
        return None

    async def create_chunk(self, chunk: MemoryChunkDTO) -> MemoryChunkDTO:
        """Store a new memory chunk record."""
        db_chunk = MemoryChunk(
            id=chunk.id,
            source_id=chunk.source_id,
            content=chunk.content,
            content_hash=chunk.content_hash,
            token_count=chunk.token_count,
            metadata_=chunk.metadata,
            created_at=chunk.created_at,
            updated_at=chunk.updated_at,
            is_deleted=chunk.is_deleted,
            version=chunk.version,
        )
        self.session.add(db_chunk)
        await self.session.flush()
        return to_chunk_dto(db_chunk)

    async def update_chunk(
        self, chunk_id: UUID, current_version: int, updated_fields: Dict[str, Any]
    ) -> Optional[MemoryChunkDTO]:
        """Update a chunk with optimistic concurrency lock checks."""
        stmt = select(MemoryChunk).where(
            MemoryChunk.id == chunk_id, MemoryChunk.is_deleted.is_(False)
        )
        res = await self.session.execute(stmt)
        db_chunk = res.scalar_one_or_none()

        if db_chunk is None:
            return None

        # Concurrency check: verify version match
        if db_chunk.version != current_version:
            return None

        # Update properties dynamically
        for field, value in updated_fields.items():
            if field == "metadata":
                db_chunk.metadata_ = value
            elif hasattr(db_chunk, field):
                setattr(db_chunk, field, value)

        # Increment version and update stamp
        db_chunk.version = current_version + 1  # type: ignore[assignment]
        db_chunk.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]

        self.session.add(db_chunk)
        await self.session.flush()
        return to_chunk_dto(db_chunk)

    async def soft_delete_chunk(self, chunk_id: UUID) -> bool:
        """Flag the target chunk as soft deleted."""
        stmt = select(MemoryChunk).where(
            MemoryChunk.id == chunk_id, MemoryChunk.is_deleted.is_(False)
        )
        res = await self.session.execute(stmt)
        db_chunk = res.scalar_one_or_none()

        if db_chunk is None:
            return False

        db_chunk.is_deleted = True  # type: ignore[assignment]
        db_chunk.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]

        self.session.add(db_chunk)
        await self.session.flush()
        return True

    async def keyword_search_chunks(
        self, query: str, limit: int
    ) -> list[MemoryChunkDTO]:
        """Perform exact text search on memory chunks content."""
        stmt = (
            select(MemoryChunk)
            .where(
                MemoryChunk.content.ilike(f"%{query}%"),
                MemoryChunk.is_deleted.is_(False),
            )
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        chunks = res.scalars().all()
        return [to_chunk_dto(c) for c in chunks]


class PersonalMemoryRepository:
    """Database repository implementing relational persistent storage for user personal memories."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with active session.

        Args:
            session: Active database AsyncSession.
        """
        self.session = session

    async def add_memory(self, memory: Any) -> Any:
        """Insert a new personal memory node or version.

        Args:
            memory: The PersonalMemory model instance.

        Returns:
            The inserted PersonalMemory model instance.
        """
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def get_memory(
        self, memory_id: UUID, version: Optional[int] = None
    ) -> Optional[Any]:
        """Retrieve a personal memory record by memory_id, optionally fetching a historical version.

        Args:
            memory_id: Target memory UUID.
            version: Optional historical version number.

        Returns:
            The PersonalMemory model instance if found, None otherwise.
        """
        from core.memory.personal import PersonalMemory

        if version is not None:
            stmt = select(PersonalMemory).where(
                PersonalMemory.memory_id == str(memory_id),
                PersonalMemory.version == version,
            )
        else:
            stmt = select(PersonalMemory).where(
                PersonalMemory.memory_id == str(memory_id),
                PersonalMemory.is_active.is_(True),
                PersonalMemory.is_deleted.is_(False),
            )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_memories(
        self,
        namespace: Optional[str] = None,
        active_only: bool = True,
        include_deleted: bool = False,
    ) -> list[Any]:
        """List personal memories under filtered criteria.

        Args:
            namespace: Optional namespace partition.
            active_only: Filter active versions only.
            include_deleted: Include soft-deleted memories.

        Returns:
            List of PersonalMemory model instances.
        """
        from core.memory.personal import PersonalMemory

        stmt = select(PersonalMemory)
        conditions = []

        if namespace is not None:
            conditions.append(PersonalMemory.namespace == namespace)
        if active_only:
            conditions.append(PersonalMemory.is_active.is_(True))
        if not include_deleted:
            conditions.append(PersonalMemory.is_deleted.is_(False))

        if conditions:
            stmt = stmt.where(*conditions)

        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_versions(self, memory_id: UUID) -> list[Any]:
        """List all version history records for the target memory_id.

        Args:
            memory_id: Target memory UUID.

        Returns:
            List of PersonalMemory records sorted by version ascending.
        """
        from core.memory.personal import PersonalMemory

        stmt = (
            select(PersonalMemory)
            .where(PersonalMemory.memory_id == str(memory_id))
            .order_by(PersonalMemory.version.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def forget(self, memory_id: UUID) -> bool:
        """Flag all versions of the target memory_id as soft deleted.

        Args:
            memory_id: Target memory UUID.

        Returns:
            True if records were updated, False otherwise.
        """
        from core.memory.personal import PersonalMemory

        stmt = select(PersonalMemory).where(PersonalMemory.memory_id == str(memory_id))
        res = await self.session.execute(stmt)
        records = res.scalars().all()

        if not records:
            return False

        for record in records:
            setattr(record, "is_deleted", True)
            setattr(record, "is_active", False)
            setattr(
                record,
                "updated_at",
                (
                    datetime.now(timezone.utc)
                    if hasattr(record, "updated_at")
                    else datetime.now(timezone.utc)
                ),
            )
            self.session.add(record)

        await self.session.flush()
        return True

    async def purge(self, memory_id: UUID) -> bool:
        """Physically delete all versions of the target memory_id from the database.

        Args:
            memory_id: Target memory UUID.

        Returns:
            True if records were deleted, False otherwise.
        """
        from sqlalchemy import delete

        from core.memory.personal import PersonalMemory

        stmt = delete(PersonalMemory).where(PersonalMemory.memory_id == str(memory_id))
        res = await self.session.execute(stmt)
        await self.session.flush()
        return (res.rowcount or 0) > 0  # type: ignore[attr-defined]

    async def confirm(self, memory_id: UUID) -> bool:
        """Update last_confirmed_at stamp and increment frequency metric.

        Args:
            memory_id: Target memory UUID.

        Returns:
            True if updated successfully, False otherwise.
        """

        # Fetch the active, non-deleted version of the memory
        active_memory = await self.get_memory(memory_id)
        if not active_memory:
            return False

        from datetime import timezone

        active_memory.last_confirmed_at = datetime.now(timezone.utc)
        active_memory.frequency = (active_memory.frequency or 0) + 1
        # Increment importance (up to 100 limit ceiling)
        active_memory.importance = min(100, (active_memory.importance or 50) + 5)
        active_memory.updated_at = datetime.now(timezone.utc)

        self.session.add(active_memory)
        await self.session.flush()
        return True
