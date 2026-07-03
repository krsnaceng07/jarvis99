"""JARVIS OS - Phase 19 Memory Repository.

CRUD + query layer for MemoryRecord persistence. No business logic.
No scoring, no promotion, no retention, no retrieval, no orchestration.

PHASE: 19
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/81_PHASE_19_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from core.memory.dto import MemoryRecord, MemoryType, MemoryVisibility

# =====================================================================
# Abstract Repository Interface
# =====================================================================


class IMemoryRecordRepository(ABC):
    """Abstract interface for MemoryRecord persistence.

    Responsibility: CRUD + query ONLY.
    Forbidden: scoring, promotion, retention, reflection, orchestration.
    """

    @abstractmethod
    async def save(self, record: MemoryRecord) -> MemoryRecord:
        """Persist a new MemoryRecord. Memory ID is immutable after creation."""
        ...

    @abstractmethod
    async def get_by_id(self, memory_id: UUID) -> Optional[MemoryRecord]:
        """Retrieve a MemoryRecord by ID. Returns None if not found."""
        ...

    @abstractmethod
    async def get_by_hash(self, content_hash: str) -> Optional[MemoryRecord]:
        """Retrieve a MemoryRecord by content hash for deduplication."""
        ...

    @abstractmethod
    async def update(
        self, memory_id: UUID, version: int, fields: Dict[str, object]
    ) -> Optional[MemoryRecord]:
        """Update a MemoryRecord with optimistic concurrency. Returns updated record or None."""
        ...

    @abstractmethod
    async def delete(self, memory_id: UUID) -> bool:
        """Soft-delete a MemoryRecord. Returns True if deleted."""
        ...

    @abstractmethod
    async def archive(self, memory_id: UUID) -> bool:
        """Archive a MemoryRecord. Returns True if archived."""
        ...

    @abstractmethod
    async def list_records(
        self,
        owner_id: Optional[UUID] = None,
        memory_type: Optional[MemoryType] = None,
        visibility: Optional[MemoryVisibility] = None,
        session_id: Optional[UUID] = None,
        include_deleted: bool = False,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MemoryRecord]:
        """List records with optional filters."""
        ...

    @abstractmethod
    async def search_metadata(
        self,
        query: str,
        limit: int = 50,
    ) -> List[MemoryRecord]:
        """Search records by content or metadata text."""
        ...

    @abstractmethod
    async def exists(self, memory_id: UUID) -> bool:
        """Check if a record exists by ID."""
        ...

    @abstractmethod
    async def count(
        self,
        owner_id: Optional[UUID] = None,
        memory_type: Optional[MemoryType] = None,
    ) -> int:
        """Count records with optional filters."""
        ...


# =====================================================================
# In-Memory Implementation (for testing)
# =====================================================================


class InMemoryRecordRepository(IMemoryRecordRepository):
    """In-memory implementation of IMemoryRecordRepository for testing."""

    def __init__(self) -> None:
        self._records: Dict[UUID, MemoryRecord] = {}
        self._hash_index: Dict[str, UUID] = {}

    async def save(self, record: MemoryRecord) -> MemoryRecord:
        """Persist a new MemoryRecord."""
        self._records[record.memory_id] = record
        self._hash_index[record.content_hash] = record.memory_id
        return record

    async def get_by_id(self, memory_id: UUID) -> Optional[MemoryRecord]:
        """Retrieve a MemoryRecord by ID."""
        return self._records.get(memory_id)

    async def get_by_hash(self, content_hash: str) -> Optional[MemoryRecord]:
        """Retrieve a MemoryRecord by content hash."""
        memory_id = self._hash_index.get(content_hash)
        if memory_id is not None:
            return self._records.get(memory_id)
        return None

    async def update(
        self, memory_id: UUID, version: int, fields: Dict[str, object]
    ) -> Optional[MemoryRecord]:
        """Update a MemoryRecord with optimistic concurrency."""
        record = self._records.get(memory_id)
        if record is None:
            return None

        if record.version != version:
            return None

        updated_data = record.model_dump()
        for key, value in fields.items():
            if key in updated_data and key not in (
                "memory_id",
                "created_at",
                "schema_version",
            ):
                updated_data[key] = value

        updated_data["version"] = version + 1
        updated_data["updated_at"] = datetime.now(timezone.utc)

        updated_record = MemoryRecord.model_validate(updated_data)
        self._records[memory_id] = updated_record

        if "content_hash" in fields:
            old_hash = record.content_hash
            if old_hash in self._hash_index:
                del self._hash_index[old_hash]
            self._hash_index[fields["content_hash"]] = memory_id

        return updated_record

    async def delete(self, memory_id: UUID) -> bool:
        """Soft-delete a MemoryRecord by setting expires_at to past."""
        record = self._records.get(memory_id)
        if record is None:
            return False

        updated_data = record.model_dump()
        updated_data["expires_at"] = datetime(2000, 1, 1)
        updated_data["updated_at"] = datetime.now(timezone.utc)
        updated_data["version"] = record.version + 1

        self._records[memory_id] = MemoryRecord.model_validate(updated_data)
        return True

    async def archive(self, memory_id: UUID) -> bool:
        """Archive a MemoryRecord by setting expires_at to a far-future sentinel."""
        record = self._records.get(memory_id)
        if record is None:
            return False

        updated_data = record.model_dump()
        updated_data["expires_at"] = datetime(9999, 12, 31, 23, 59, 59)
        updated_data["updated_at"] = datetime.now(timezone.utc)
        updated_data["version"] = record.version + 1

        self._records[memory_id] = MemoryRecord.model_validate(updated_data)
        return True

    async def list_records(
        self,
        owner_id: Optional[UUID] = None,
        memory_type: Optional[MemoryType] = None,
        visibility: Optional[MemoryVisibility] = None,
        session_id: Optional[UUID] = None,
        include_deleted: bool = False,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MemoryRecord]:
        """List records with optional filters."""
        results: List[MemoryRecord] = []
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for record in self._records.values():
            if (
                not include_deleted
                and record.expires_at is not None
                and record.expires_at < now
            ):
                continue

            if not include_archived and record.expires_at == datetime(
                9999, 12, 31, 23, 59, 59
            ):
                continue

            if owner_id is not None and record.owner_id != owner_id:
                continue

            if memory_type is not None and record.memory_type != memory_type:
                continue

            if visibility is not None and record.visibility != visibility:
                continue

            if session_id is not None:
                if record.provenance.workflow_id != session_id:
                    continue

            results.append(record)

        return results[offset : offset + limit]

    async def search_metadata(
        self,
        query: str,
        limit: int = 50,
    ) -> List[MemoryRecord]:
        """Search records by content text (case-insensitive contains)."""
        query_lower = query.lower()
        results: List[MemoryRecord] = []

        for record in self._records.values():
            if query_lower in record.content.lower():
                results.append(record)
                if len(results) >= limit:
                    break

        return results

    async def exists(self, memory_id: UUID) -> bool:
        """Check if a record exists by ID."""
        return memory_id in self._records

    async def count(
        self,
        owner_id: Optional[UUID] = None,
        memory_type: Optional[MemoryType] = None,
    ) -> int:
        """Count records with optional filters."""
        count = 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for record in self._records.values():
            if record.expires_at is not None and record.expires_at < now:
                continue

            if owner_id is not None and record.owner_id != owner_id:
                continue

            if memory_type is not None and record.memory_type != memory_type:
                continue

            count += 1

        return count
