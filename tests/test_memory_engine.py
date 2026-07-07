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

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.interfaces import EventBusInterface
from core.memory.dto import MemoryTier
from core.memory.interfaces import (
    IEmbeddingGenerator,
    IMemoryRepository,
    IVectorStoreRepository,
    MemoryChunkDTO,
)
from core.memory.memory_context import MemoryContextBuilder
from core.memory.memory_engine import MemoryEngine
from core.memory.memory_scoring import MemoryScoring
from core.memory.memory_search import MemorySearch


@pytest.mark.asyncio
async def test_memory_engine_flow_and_lru() -> None:
    mock_repo = AsyncMock(spec=IMemoryRepository)
    mock_vector = AsyncMock(spec=IVectorStoreRepository)
    mock_embed = AsyncMock(spec=IEmbeddingGenerator)
    mock_bus = AsyncMock(spec=EventBusInterface)

    scoring = MemoryScoring()
    search = MemorySearch(mock_repo, mock_vector, mock_embed, scoring)
    context_builder = MemoryContextBuilder()

    # Initialize Engine with L1 max size of 2 for testing LRU
    engine = MemoryEngine(
        memory_repo=mock_repo,
        scoring=scoring,
        search=search,
        context_builder=context_builder,
        event_bus=mock_bus,
        l1_max_items=2,
    )

    mock_repo.get_chunk_by_hash.return_value = None

    # 1. Test Store
    m1_id = await engine.store(
        content="First memory record content", source_type="user_input"
    )
    m2_id = await engine.store(
        content="Second memory record content", source_type="user_input"
    )
    assert len(engine.lru_order) == 2
    assert engine.lru_order == [m1_id, m2_id]
    mock_bus.publish.assert_called()

    # Add a third item to trigger LRU eviction of m1_id
    m3_id = await engine.store(
        content="Third memory record content", source_type="user_input"
    )
    assert len(engine.lru_order) == 2
    assert engine.lru_order == [m2_id, m3_id]
    # m1_id should be evicted from working memory cache
    assert engine.working_memory.get_by_id(m1_id) is None
    assert engine.working_memory.get_by_id(m2_id) is not None

    # 2. Test Retrieve from cache
    record2 = await engine.retrieve(m2_id)
    assert record2 is not None
    assert record2.content == "Second memory record content"

    # 3. Test Update
    mock_repo.update_chunk.return_value = MagicMock(version=2)
    updated = await engine.update(m2_id, content="Updated second memory content")
    assert updated is True
    record2_updated = await engine.retrieve(m2_id)
    assert record2_updated.content == "Updated second memory content"

    # 4. Test Delete
    mock_repo.soft_delete_chunk.return_value = True
    deleted = await engine.delete(m2_id)
    assert deleted is True
    assert engine.working_memory.get_by_id(m2_id) is None


@pytest.mark.asyncio
async def test_memory_engine_deduplication_and_retrieve_db() -> None:
    mock_repo = AsyncMock(spec=IMemoryRepository)
    mock_vector = AsyncMock(spec=IVectorStoreRepository)
    mock_embed = AsyncMock(spec=IEmbeddingGenerator)
    mock_bus = AsyncMock(spec=EventBusInterface)

    scoring = MemoryScoring()
    search = MemorySearch(mock_repo, mock_vector, mock_embed, scoring)
    context_builder = MemoryContextBuilder()

    engine = MemoryEngine(
        memory_repo=mock_repo,
        scoring=scoring,
        search=search,
        context_builder=context_builder,
        event_bus=mock_bus,
    )

    now = datetime.now(timezone.utc)
    chunk_dto = MemoryChunkDTO(
        id=uuid4(),
        source_id=uuid4(),
        content="Existing duplicate content",
        content_hash="dup-hash",
        token_count=3,
        metadata={
            "importance": 0.5,
            "confidence": 1.0,
            "tier": MemoryTier.WORKING.value,
            "owner_id": str(uuid4()),
            "visibility": "private",
            "trust_level": "user_implicit",
            "origin": "user",
            "created_by": "agent",
        },
        created_at=now,
        updated_at=now,
    )

    # Mock deduplication hit
    mock_repo.get_chunk_by_hash.return_value = chunk_dto
    mock_repo.update_chunk.return_value = chunk_dto

    m_id = await engine.store("Existing duplicate content")
    assert m_id == chunk_dto.id
    mock_repo.update_chunk.assert_called()

    # Clear L1 cache to test DB retrieve fallback
    engine.working_memory.clear()
    engine.lru_order.clear()

    # Mock DB hit
    mock_repo.get_chunk.return_value = chunk_dto
    record = await engine.retrieve(chunk_dto.id)
    assert record is not None
    assert record.content == "Existing duplicate content"
    mock_repo.get_chunk.assert_called_with(chunk_dto.id)


@pytest.mark.asyncio
async def test_memory_engine_forget_and_list() -> None:
    mock_repo = AsyncMock(spec=IMemoryRepository)
    mock_vector = AsyncMock(spec=IVectorStoreRepository)
    mock_embed = AsyncMock(spec=IEmbeddingGenerator)
    mock_bus = AsyncMock(spec=EventBusInterface)

    scoring = MemoryScoring()
    search = MemorySearch(mock_repo, mock_vector, mock_embed, scoring)
    context_builder = MemoryContextBuilder()

    engine = MemoryEngine(
        memory_repo=mock_repo,
        scoring=scoring,
        search=search,
        context_builder=context_builder,
        event_bus=mock_bus,
    )

    now = datetime.now(timezone.utc)
    c1 = MemoryChunkDTO(
        id=uuid4(),
        source_id=uuid4(),
        content="Listed working memory",
        content_hash="h1",
        token_count=3,
        metadata={
            "importance": 0.5,
            "confidence": 1.0,
            "tier": MemoryTier.WORKING.value,
            "owner_id": str(uuid4()),
            "visibility": "private",
            "trust_level": "user_implicit",
            "origin": "user",
            "created_by": "agent",
        },
        created_at=now,
        updated_at=now,
    )

    # 1. Test forget (cascade soft delete)
    mock_repo.soft_delete_chunk.return_value = True
    forgot = await engine.forget(c1.id, reason="test forgetting", cascade=True)
    assert forgot is True
    mock_repo.soft_delete_chunk.assert_called_with(c1.id)

    # 2. Test list_records
    mock_repo.keyword_search_chunks.return_value = [c1]
    recs = await engine.list_records(tier=MemoryTier.WORKING)
    assert len(recs) == 1
    assert recs[0].content == "Listed working memory"

    # Test listing with non-matching tier
    recs_empty = await engine.list_records(tier=MemoryTier.LONG_TERM)
    assert len(recs_empty) == 0


@pytest.mark.asyncio
async def test_memory_engine_failures_and_edge_cases() -> None:
    mock_repo = AsyncMock(spec=IMemoryRepository)
    mock_vector = AsyncMock(spec=IVectorStoreRepository)
    mock_embed = AsyncMock(spec=IEmbeddingGenerator)
    mock_bus = AsyncMock(spec=EventBusInterface)

    scoring = MemoryScoring()
    search = MemorySearch(mock_repo, mock_vector, mock_embed, scoring)
    context_builder = MemoryContextBuilder()

    engine = MemoryEngine(
        memory_repo=mock_repo,
        scoring=scoring,
        search=search,
        context_builder=context_builder,
        event_bus=mock_bus,
    )

    non_existent_id = uuid4()

    # 1. Retrieve returns None if not in L1 and not in DB (line 214)
    mock_repo.get_chunk.return_value = None
    record = await engine.retrieve(non_existent_id)
    assert record is None

    # 2. Update returns False if record not found (line 225)
    updated = await engine.update(non_existent_id, content="updated content")
    assert updated is False

    # 3. Metadata-only update triggers lines 236-238
    now = datetime.now(timezone.utc)
    chunk_dto = MemoryChunkDTO(
        id=uuid4(),
        source_id=uuid4(),
        content="Stable content",
        content_hash="stable-hash",
        token_count=2,
        metadata={
            "importance": 0.5,
            "confidence": 1.0,
            "tier": MemoryTier.WORKING.value,
            "owner_id": str(uuid4()),
            "visibility": "private",
        },
        created_at=now,
        updated_at=now,
    )
    # Put in L1 Working Memory
    from core.memory.memory_serializer import MemorySerializer

    rec = MemorySerializer.from_dto(chunk_dto)
    engine.working_memory.add(rec)
    engine.lru_order.append(rec.memory_id)

    # Perform metadata-only update
    mock_repo.update_chunk.return_value = chunk_dto
    updated_meta = await engine.update(rec.memory_id, metadata={"new_key": "new_val"})
    assert updated_meta is True
    updated_record = await engine.retrieve(rec.memory_id)
    assert updated_record.metadata.extra.get("new_key") == "new_val"

    # 4. Update returns False if repository update returns None (line 256)
    mock_repo.update_chunk.return_value = None
    updated_fail = await engine.update(rec.memory_id, content="Change again")
    assert updated_fail is False

    # 5. Delete returns False if repository delete returns False (line 277)
    mock_repo.soft_delete_chunk.return_value = False
    deleted_fail = await engine.delete(rec.memory_id)
    assert deleted_fail is False
