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
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from core.memory.dto import MemoryTier, MemoryVisibility
from core.memory.interfaces import (
    IEmbeddingGenerator,
    IMemoryRepository,
    IVectorStoreRepository,
    MemoryChunkDTO,
)
from core.memory.memory_scoring import MemoryScoring
from core.memory.memory_search import MemorySearch


@pytest.mark.asyncio
async def test_search_keyword_and_semantic() -> None:
    # Set up mocks
    mock_repo = AsyncMock(spec=IMemoryRepository)
    mock_vector = AsyncMock(spec=IVectorStoreRepository)
    mock_embed = AsyncMock(spec=IEmbeddingGenerator)
    scoring = MemoryScoring()

    now = datetime.now(timezone.utc)
    chunk_dto = MemoryChunkDTO(
        id=uuid4(),
        source_id=uuid4(),
        content="Semantic memory test content",
        content_hash="checksum123",
        token_count=5,
        metadata={
            "importance": 0.9,
            "confidence": 1.0,
            "tier": MemoryTier.LONG_TERM.value,
            "owner_id": str(uuid4()),
            "visibility": MemoryVisibility.PUBLIC.value,
            "trust_level": "user_explicit",
            "origin": "user",
            "created_by": "agent",
        },
        created_at=now,
        updated_at=now,
    )

    mock_repo.keyword_search_chunks.return_value = [chunk_dto]
    mock_repo.get_chunk.return_value = chunk_dto
    mock_vector.search_vector.return_value = [{"id": chunk_dto.id, "score": 0.85}]
    mock_embed.generate_embedding.return_value = [0.1, 0.2, 0.3]

    search_engine = MemorySearch(mock_repo, mock_vector, mock_embed, scoring)

    # 1. Test Keyword Search
    kw_results = await search_engine.search_keyword("keyword query")
    assert len(kw_results) == 1
    assert kw_results[0].content == "Semantic memory test content"

    # 2. Test Semantic Search
    sem_results = await search_engine.search_semantic("semantic query")
    assert len(sem_results) == 1
    record, similarity = sem_results[0]
    assert record.content == "Semantic memory test content"
    assert similarity == 0.85

    # 3. Test Hybrid Search
    hybrid_results = await search_engine.search_hybrid("hybrid query")
    assert len(hybrid_results) == 1
    assert hybrid_results[0].content == "Semantic memory test content"


@pytest.mark.asyncio
async def test_search_filters_and_truncation() -> None:
    mock_repo = AsyncMock(spec=IMemoryRepository)
    mock_vector = AsyncMock(spec=IVectorStoreRepository)
    mock_embed = AsyncMock(spec=IEmbeddingGenerator)
    scoring = MemoryScoring()

    now = datetime.now(timezone.utc)
    owner_id = uuid4()

    # 1. Record owned by requesting user
    c1 = MemoryChunkDTO(
        id=uuid4(),
        source_id=uuid4(),
        content="Owned chunk content",
        content_hash="hash1",
        token_count=3,
        metadata={
            "importance": 0.8,
            "confidence": 1.0,
            "tier": MemoryTier.WORKING.value,
            "owner_id": str(owner_id),
            "visibility": MemoryVisibility.PRIVATE.value,
        },
        created_at=now,
        updated_at=now,
    )

    # 2. Record with tier NOT matching tier_filter
    c2 = MemoryChunkDTO(
        id=uuid4(),
        source_id=uuid4(),
        content="Long term chunk content",
        content_hash="hash2",
        token_count=3,
        metadata={
            "importance": 0.9,
            "confidence": 1.0,
            "tier": MemoryTier.LONG_TERM.value,
            "owner_id": str(uuid4()),
            "visibility": MemoryVisibility.PUBLIC.value,
        },
        created_at=now,
        updated_at=now,
    )

    mock_repo.keyword_search_chunks.return_value = [c1, c2]
    mock_vector.search_vector.return_value = []
    search_engine = MemorySearch(mock_repo, mock_vector, mock_embed, scoring)

    # Search with owner_id filter and tier_filter = [WORKING]
    results = await search_engine.search_hybrid(
        query="test query",
        owner_id=owner_id,
        tier_filter=[MemoryTier.WORKING],
        min_score=0.1,
        limit=1,
    )

    # c2 is public, but c2 is excluded because tier is LONG_TERM (tier_filter only allows WORKING)
    # c1 is private, but c1 is included because it's owned by owner_id and its tier is WORKING
    # limit = 1 ensures we truncate if we have multiple results
    assert len(results) == 1
    assert results[0].memory_id == c1.id

    # Test min_score filtering
    no_results = await search_engine.search_hybrid(
        query="test query",
        owner_id=owner_id,
        tier_filter=[MemoryTier.WORKING],
        min_score=0.99,  # too high
    )
    assert len(no_results) == 0
