"""
PHASE: 20
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 20 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set
from uuid import UUID

from core.memory.dto import MemoryRecord


class MemoryIndex:
    """In-memory indexing engine for high-speed retrieval of working memory (L1).

    Indexes memory records by UUID, tag, type, and timestamp to enable O(1) lookups
    and efficient filtering before executing heavy DB or vector searches.
    """

    def __init__(self) -> None:
        self._id_index: Dict[UUID, MemoryRecord] = {}
        self._tag_index: Dict[str, Set[UUID]] = defaultdict(set)
        self._type_index: Dict[str, Set[UUID]] = defaultdict(set)
        self._timestamp_index: List[tuple[datetime, UUID]] = []

    def add(self, record: MemoryRecord) -> None:
        """Add and index a MemoryRecord. Overwrites if UUID already exists."""
        if record.memory_id in self._id_index:
            self.remove(record.memory_id)

        # Index by UUID
        self._id_index[record.memory_id] = record

        # Index by Type
        mtype = (
            str(record.memory_type.value)
            if hasattr(record.memory_type, "value")
            else str(record.memory_type)
        )
        self._type_index[mtype].add(record.memory_id)

        # Index by Tags (from metadata.extra tags if present)
        tags = record.metadata.extra.get("tags", []) if record.metadata else []
        if isinstance(tags, (list, set)):
            for tag in tags:
                self._tag_index[str(tag)].add(record.memory_id)

        # Index by Timestamp
        self._timestamp_index.append((record.created_at, record.memory_id))
        self._timestamp_index.sort(key=lambda x: x[0])

    def remove(self, memory_id: UUID) -> Optional[MemoryRecord]:
        """Remove a MemoryRecord from all indexes. Returns the removed record if found."""
        record = self._id_index.pop(memory_id, None)
        if not record:
            return None

        # Clean type index
        mtype = (
            str(record.memory_type.value)
            if hasattr(record.memory_type, "value")
            else str(record.memory_type)
        )
        self._type_index[mtype].discard(memory_id)

        # Clean tag index
        tags = record.metadata.extra.get("tags", []) if record.metadata else []
        if isinstance(tags, (list, set)):
            for tag in tags:
                self._tag_index[str(tag)].discard(memory_id)

        # Clean timestamp index
        self._timestamp_index = [x for x in self._timestamp_index if x[1] != memory_id]
        return record

    def get_by_id(self, memory_id: UUID) -> Optional[MemoryRecord]:
        """Get a record by its UUID."""
        return self._id_index.get(memory_id)

    def get_by_tag(self, tag: str) -> List[MemoryRecord]:
        """Get all records matching a specific tag."""
        ids = self._tag_index.get(tag, set())
        return [self._id_index[mid] for mid in ids if mid in self._id_index]

    def get_by_type(self, memory_type: str) -> List[MemoryRecord]:
        """Get all records matching a specific memory type."""
        ids = self._type_index.get(memory_type, set())
        return [self._id_index[mid] for mid in ids if mid in self._id_index]

    def get_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> List[MemoryRecord]:
        """Get all records created within a specific timestamp range (inclusive)."""
        results = []
        for ts, mid in self._timestamp_index:
            if start_time <= ts <= end_time:
                if mid in self._id_index:
                    results.append(self._id_index[mid])
        return results

    def clear(self) -> None:
        """Clear all indexes."""
        self._id_index.clear()
        self._tag_index.clear()
        self._type_index.clear()
        self._timestamp_index.clear()
