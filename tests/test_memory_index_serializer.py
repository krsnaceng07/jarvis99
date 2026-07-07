"""JARVIS OS - Phase 20 Memory Index & Serializer Tests.

Tests for MemoryIndex (in-memory indexing by UUID, tag, type, time)
and MemorySerializer (MemoryRecord <-> MemoryChunkDTO <-> JSON conversions).

PHASE: 20
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest

from core.memory.dto import (
    MemoryMetadata,
    MemoryProvenance,
    MemoryRecord,
    MemoryTier,
    MemoryTrustLevel,
    MemoryType,
    MemoryVisibility,
)
from core.memory.memory_index import MemoryIndex
from core.memory.memory_serializer import MemorySerializer

# =====================================================================
# Helpers
# =====================================================================

FIXED_NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_record(
    content: str = "test content",
    memory_type: MemoryType = MemoryType.FACT,
    importance: float = 0.5,
    tags: Optional[list[str]] = None,
    created_at: Optional[datetime] = None,
    tier: str = MemoryTier.WORKING.value,
) -> MemoryRecord:
    extra = {"tier": tier, "access_count": 0}
    if tags:
        extra["tags"] = tags
    return MemoryRecord(
        memory_type=memory_type,
        owner_id=uuid4(),
        visibility=MemoryVisibility.PRIVATE,
        trust_level=MemoryTrustLevel.USER_IMPLICIT,
        confidence=0.9,
        importance=importance,
        created_at=created_at or FIXED_NOW,
        updated_at=FIXED_NOW,
        provenance=MemoryProvenance(origin="test", created_by="test"),
        content=content,
        content_hash=f"hash_{uuid4().hex[:8]}",
        metadata=MemoryMetadata(importance=importance, extra=extra),
    )


# =====================================================================
# MemoryIndex Tests
# =====================================================================


class TestMemoryIndex:
    def test_add_and_get_by_id(self) -> None:
        idx = MemoryIndex()
        record = _make_record()
        idx.add(record)
        result = idx.get_by_id(record.memory_id)
        assert result is not None
        assert result.memory_id == record.memory_id

    def test_get_by_id_missing(self) -> None:
        idx = MemoryIndex()
        assert idx.get_by_id(uuid4()) is None

    def test_get_by_type(self) -> None:
        idx = MemoryIndex()
        r1 = _make_record(memory_type=MemoryType.FACT)
        r2 = _make_record(memory_type=MemoryType.TASK)
        r3 = _make_record(memory_type=MemoryType.FACT)
        idx.add(r1)
        idx.add(r2)
        idx.add(r3)
        facts = idx.get_by_type(MemoryType.FACT.value)
        assert len(facts) == 2
        tasks = idx.get_by_type(MemoryType.TASK.value)
        assert len(tasks) == 1

    def test_get_by_tag(self) -> None:
        idx = MemoryIndex()
        r1 = _make_record(tags=["python", "async"])
        r2 = _make_record(tags=["python", "sync"])
        r3 = _make_record(tags=["rust"])
        idx.add(r1)
        idx.add(r2)
        idx.add(r3)
        python_records = idx.get_by_tag("python")
        assert len(python_records) == 2
        rust_records = idx.get_by_tag("rust")
        assert len(rust_records) == 1
        go_records = idx.get_by_tag("go")
        assert len(go_records) == 0

    def test_get_by_time_range(self) -> None:
        idx = MemoryIndex()
        t1 = FIXED_NOW - timedelta(hours=3)
        t2 = FIXED_NOW - timedelta(hours=1)
        t3 = FIXED_NOW
        r1 = _make_record(content="old", created_at=t1)
        r2 = _make_record(content="mid", created_at=t2)
        r3 = _make_record(content="new", created_at=t3)
        idx.add(r1)
        idx.add(r2)
        idx.add(r3)
        # Range covering t2 only
        results = idx.get_by_time_range(
            FIXED_NOW - timedelta(hours=2),
            FIXED_NOW - timedelta(minutes=30),
        )
        assert len(results) == 1
        assert results[0].content == "mid"

    def test_remove(self) -> None:
        idx = MemoryIndex()
        record = _make_record(tags=["removeme"])
        idx.add(record)
        removed = idx.remove(record.memory_id)
        assert removed is not None
        assert idx.get_by_id(record.memory_id) is None
        assert idx.get_by_tag("removeme") == []

    def test_remove_missing_returns_none(self) -> None:
        idx = MemoryIndex()
        assert idx.remove(uuid4()) is None

    def test_clear(self) -> None:
        idx = MemoryIndex()
        for i in range(5):
            idx.add(_make_record(content=f"r{i}"))
        idx.clear()
        # After clear, nothing should be retrievable
        assert idx.get_by_type(MemoryType.FACT.value) == []

    def test_overwrite_on_duplicate_id(self) -> None:
        idx = MemoryIndex()
        record = _make_record(content="original")
        idx.add(record)
        # Create a "new" record with same memory_id
        updated = _make_record(content="updated")
        # Force same ID
        object.__setattr__(updated, "memory_id", record.memory_id)
        idx.add(updated)
        result = idx.get_by_id(record.memory_id)
        assert result is not None
        assert result.content == "updated"


# =====================================================================
# MemorySerializer Tests
# =====================================================================


class TestMemorySerializer:
    def test_to_json_and_back(self) -> None:
        record = _make_record(content="roundtrip test")
        json_str = MemorySerializer.to_json(record)
        restored = MemorySerializer.from_json(json_str)
        assert restored.memory_id == record.memory_id
        assert restored.content == "roundtrip test"

    def test_to_dto(self) -> None:
        record = _make_record(content="dto test", importance=0.8)
        dto = MemorySerializer.to_dto(record)
        assert dto.content == "dto test"
        assert dto.id == record.memory_id
        assert dto.content_hash == record.content_hash

    def test_from_dto_roundtrip(self) -> None:
        original = _make_record(content="roundtrip dto")
        dto = MemorySerializer.to_dto(original)
        restored = MemorySerializer.from_dto(dto)
        assert restored.content == "roundtrip dto"
        assert restored.confidence == original.confidence

    def test_to_db(self) -> None:
        record = _make_record(content="db test")
        db_dict = MemorySerializer.to_db(record)
        assert db_dict["content"] == "db test"
        assert db_dict["id"] == record.memory_id
        assert "content_hash" in db_dict
        assert "metadata" in db_dict

    def test_to_json_contains_all_fields(self) -> None:
        record = _make_record()
        json_str = MemorySerializer.to_json(record)
        assert "content" in json_str
        assert "memory_type" in json_str
        assert "confidence" in json_str
