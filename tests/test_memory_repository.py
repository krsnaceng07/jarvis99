"""JARVIS OS - Phase 19 M2 Repository Tests.

Tests for the Memory Repository. Verifies:
- CRUD operations work correctly
- Optimistic concurrency control
- Soft delete and archive
- Search and filtering
- No business logic in repository

PHASE: 19
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.memory.dto import (
    MemoryProvenance,
    MemoryRecord,
    MemoryTrustLevel,
    MemoryType,
    MemoryVisibility,
)
from core.memory.memory_repository import InMemoryRecordRepository

# =====================================================================
# Helpers
# =====================================================================


def _make_record(
    content: str = "test content",
    content_hash: str | None = None,
    owner_id: uuid4 | None = None,
    memory_type: MemoryType = MemoryType.FACT,
    visibility: MemoryVisibility = MemoryVisibility.PRIVATE,
) -> MemoryRecord:
    """Create a test MemoryRecord."""
    return MemoryRecord(
        memory_type=memory_type,
        owner_id=owner_id or uuid4(),
        visibility=visibility,
        trust_level=MemoryTrustLevel.USER_IMPLICIT,
        confidence=0.9,
        provenance=MemoryProvenance(
            origin="test",
            created_by="test_agent",
        ),
        content=content,
        content_hash=content_hash or f"hash_{uuid4().hex[:8]}",
    )


# =====================================================================
# Save & Get Tests
# =====================================================================


class TestSaveAndGet:
    """Verify save and get_by_id operations."""

    @pytest.mark.asyncio
    async def test_save_and_get(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)
        fetched = await repo.get_by_id(record.memory_id)
        assert fetched is not None
        assert fetched.memory_id == record.memory_id
        assert fetched.content == record.content

    @pytest.mark.asyncio
    async def test_get_nonexistent(self) -> None:
        repo = InMemoryRecordRepository()
        fetched = await repo.get_by_id(uuid4())
        assert fetched is None

    @pytest.mark.asyncio
    async def test_save_preserves_id(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        original_id = record.memory_id
        await repo.save(record)
        fetched = await repo.get_by_id(original_id)
        assert fetched is not None
        assert fetched.memory_id == original_id


# =====================================================================
# Hash Deduplication Tests
# =====================================================================


class TestHashDedup:
    """Verify content hash deduplication."""

    @pytest.mark.asyncio
    async def test_get_by_hash(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record(content_hash="unique_hash_123")
        await repo.save(record)
        fetched = await repo.get_by_hash("unique_hash_123")
        assert fetched is not None
        assert fetched.memory_id == record.memory_id

    @pytest.mark.asyncio
    async def test_get_by_hash_nonexistent(self) -> None:
        repo = InMemoryRecordRepository()
        fetched = await repo.get_by_hash("nonexistent_hash")
        assert fetched is None


# =====================================================================
# Update Tests
# =====================================================================


class TestUpdate:
    """Verify update with optimistic concurrency."""

    @pytest.mark.asyncio
    async def test_update_success(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)

        updated = await repo.update(
            record.memory_id,
            version=record.version,
            fields={"content": "updated content"},
        )
        assert updated is not None
        assert updated.content == "updated content"
        assert updated.version == record.version + 1

    @pytest.mark.asyncio
    async def test_update_version_conflict(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)

        updated = await repo.update(
            record.memory_id,
            version=record.version + 1,
            fields={"content": "should fail"},
        )
        assert updated is None

    @pytest.mark.asyncio
    async def test_update_nonexistent(self) -> None:
        repo = InMemoryRecordRepository()
        updated = await repo.update(
            uuid4(),
            version=1,
            fields={"content": "should fail"},
        )
        assert updated is None

    @pytest.mark.asyncio
    async def test_update_preserves_id(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)

        updated = await repo.update(
            record.memory_id,
            version=record.version,
            fields={"content": "updated"},
        )
        assert updated is not None
        assert updated.memory_id == record.memory_id

    @pytest.mark.asyncio
    async def test_update_content_hash(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record(content_hash="old_hash")
        await repo.save(record)

        updated = await repo.update(
            record.memory_id,
            version=record.version,
            fields={"content_hash": "new_hash"},
        )
        assert updated is not None
        assert updated.content_hash == "new_hash"

        fetched_by_new = await repo.get_by_hash("new_hash")
        assert fetched_by_new is not None
        assert fetched_by_new.memory_id == record.memory_id

        fetched_by_old = await repo.get_by_hash("old_hash")
        assert fetched_by_old is None


# =====================================================================
# Delete Tests
# =====================================================================


class TestDelete:
    """Verify soft delete operations."""

    @pytest.mark.asyncio
    async def test_delete_success(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)

        deleted = await repo.delete(record.memory_id)
        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self) -> None:
        repo = InMemoryRecordRepository()
        deleted = await repo.delete(uuid4())
        assert deleted is False

    @pytest.mark.asyncio
    async def test_deleted_not_in_list(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)
        await repo.delete(record.memory_id)

        records = await repo.list_records()
        assert len(records) == 0


# =====================================================================
# Archive Tests
# =====================================================================


class TestArchive:
    """Verify archive operations."""

    @pytest.mark.asyncio
    async def test_archive_success(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)

        archived = await repo.archive(record.memory_id)
        assert archived is True

    @pytest.mark.asyncio
    async def test_archive_nonexistent(self) -> None:
        repo = InMemoryRecordRepository()
        archived = await repo.archive(uuid4())
        assert archived is False

    @pytest.mark.asyncio
    async def test_archived_excluded_by_default(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)
        await repo.archive(record.memory_id)

        records = await repo.list_records()
        assert len(records) == 0

    @pytest.mark.asyncio
    async def test_archived_included_when_requested(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)
        await repo.archive(record.memory_id)

        records = await repo.list_records(include_archived=True)
        assert len(records) == 1


# =====================================================================
# List & Filter Tests
# =====================================================================


class TestListFilter:
    """Verify list and filter operations."""

    @pytest.mark.asyncio
    async def test_list_all(self) -> None:
        repo = InMemoryRecordRepository()
        for i in range(5):
            await repo.save(_make_record(content=f"record_{i}"))

        records = await repo.list_records()
        assert len(records) == 5

    @pytest.mark.asyncio
    async def test_list_by_owner(self) -> None:
        repo = InMemoryRecordRepository()
        owner1 = uuid4()
        owner2 = uuid4()

        await repo.save(_make_record(owner_id=owner1))
        await repo.save(_make_record(owner_id=owner1))
        await repo.save(_make_record(owner_id=owner2))

        records = await repo.list_records(owner_id=owner1)
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_list_by_type(self) -> None:
        repo = InMemoryRecordRepository()
        await repo.save(_make_record(memory_type=MemoryType.FACT))
        await repo.save(_make_record(memory_type=MemoryType.PREFERENCE))
        await repo.save(_make_record(memory_type=MemoryType.FACT))

        records = await repo.list_records(memory_type=MemoryType.FACT)
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_list_by_visibility(self) -> None:
        repo = InMemoryRecordRepository()
        await repo.save(_make_record(visibility=MemoryVisibility.PRIVATE))
        await repo.save(_make_record(visibility=MemoryVisibility.PUBLIC))

        records = await repo.list_records(visibility=MemoryVisibility.PUBLIC)
        assert len(records) == 1

    @pytest.mark.asyncio
    async def test_list_with_limit(self) -> None:
        repo = InMemoryRecordRepository()
        for i in range(10):
            await repo.save(_make_record(content=f"record_{i}"))

        records = await repo.list_records(limit=3)
        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_list_with_offset(self) -> None:
        repo = InMemoryRecordRepository()
        for i in range(5):
            await repo.save(_make_record(content=f"record_{i}"))

        records = await repo.list_records(limit=2, offset=2)
        assert len(records) == 2


# =====================================================================
# Search Tests
# =====================================================================


class TestSearch:
    """Verify search operations."""

    @pytest.mark.asyncio
    async def test_search_by_content(self) -> None:
        repo = InMemoryRecordRepository()
        await repo.save(_make_record(content="Python is great"))
        await repo.save(_make_record(content="Java is okay"))
        await repo.save(_make_record(content="I love Python"))

        results = await repo.search_metadata("Python")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self) -> None:
        repo = InMemoryRecordRepository()
        await repo.save(_make_record(content="HELLO world"))

        results = await repo.search_metadata("hello")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_with_limit(self) -> None:
        repo = InMemoryRecordRepository()
        for i in range(10):
            await repo.save(_make_record(content=f"test item {i}"))

        results = await repo.search_metadata("test", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_no_match(self) -> None:
        repo = InMemoryRecordRepository()
        await repo.save(_make_record(content="hello"))

        results = await repo.search_metadata("nonexistent")
        assert len(results) == 0


# =====================================================================
# Exists & Count Tests
# =====================================================================


class TestExistsCount:
    """Verify exists and count operations."""

    @pytest.mark.asyncio
    async def test_exists_true(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)

        assert await repo.exists(record.memory_id) is True

    @pytest.mark.asyncio
    async def test_exists_false(self) -> None:
        repo = InMemoryRecordRepository()
        assert await repo.exists(uuid4()) is False

    @pytest.mark.asyncio
    async def test_count_all(self) -> None:
        repo = InMemoryRecordRepository()
        for i in range(5):
            await repo.save(_make_record(content=f"record_{i}"))

        count = await repo.count()
        assert count == 5

    @pytest.mark.asyncio
    async def test_count_by_owner(self) -> None:
        repo = InMemoryRecordRepository()
        owner = uuid4()
        await repo.save(_make_record(owner_id=owner))
        await repo.save(_make_record(owner_id=owner))
        await repo.save(_make_record(owner_id=uuid4()))

        count = await repo.count(owner_id=owner)
        assert count == 2

    @pytest.mark.asyncio
    async def test_count_by_type(self) -> None:
        repo = InMemoryRecordRepository()
        await repo.save(_make_record(memory_type=MemoryType.FACT))
        await repo.save(_make_record(memory_type=MemoryType.PREFERENCE))

        count = await repo.count(memory_type=MemoryType.FACT)
        assert count == 1

    @pytest.mark.asyncio
    async def test_count_excludes_deleted(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)
        await repo.delete(record.memory_id)

        count = await repo.count()
        assert count == 0


# =====================================================================
# Immutability Tests
# =====================================================================


class TestImmutability:
    """Verify Memory ID is immutable across operations."""

    @pytest.mark.asyncio
    async def test_id_immutable_after_save(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        original_id = record.memory_id
        await repo.save(record)
        fetched = await repo.get_by_id(original_id)
        assert fetched is not None
        assert fetched.memory_id == original_id

    @pytest.mark.asyncio
    async def test_id_immutable_after_update(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)
        original_id = record.memory_id

        updated = await repo.update(
            record.memory_id,
            version=record.version,
            fields={"content": "updated"},
        )
        assert updated is not None
        assert updated.memory_id == original_id

    @pytest.mark.asyncio
    async def test_id_immutable_after_delete(self) -> None:
        repo = InMemoryRecordRepository()
        record = _make_record()
        await repo.save(record)
        original_id = record.memory_id

        await repo.delete(record.memory_id)
        fetched = await repo.get_by_id(original_id)
        assert fetched is not None
        assert fetched.memory_id == original_id
