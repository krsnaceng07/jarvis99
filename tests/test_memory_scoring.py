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

from datetime import datetime, timedelta, timezone
from uuid import uuid4

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
from core.memory.memory_scoring import MemoryScoring
from core.memory.memory_serializer import MemorySerializer
from core.memory.models import MemoryChunk
from core.memory.scoring import ScoringWeights


def test_scoring_weights_defaults() -> None:
    weights = ScoringWeights()
    assert weights.w_recency == 0.25
    assert weights.w_semantic == 0.20
    assert weights.w_confidence == 0.20
    assert weights.w_importance == 0.15
    assert weights.w_frequency == 0.10
    assert weights.w_trust == 0.05
    assert weights.w_pin == 1.00


def test_calculate_score_and_rank() -> None:
    scoring = MemoryScoring()
    now = datetime.now(timezone.utc)

    prov = MemoryProvenance(
        origin="system",
        created_by="agent",
    )
    meta = MemoryMetadata(
        importance=0.8,
        token_count=100,
        extra={"tier": MemoryTier.LONG_TERM.value},
    )

    r1 = MemoryRecord(
        memory_id=uuid4(),
        memory_type=MemoryType.FACT,
        owner_id=uuid4(),
        visibility=MemoryVisibility.PUBLIC,
        trust_level=MemoryTrustLevel.SYSTEM,
        confidence=0.9,
        importance=0.8,
        created_at=now,
        updated_at=now,
        content="Testing memory score",
        content_hash="hash1",
        version=1,
        provenance=prov,
        metadata=meta,
    )

    r2 = MemoryRecord(
        memory_id=uuid4(),
        memory_type=MemoryType.FACT,
        owner_id=uuid4(),
        visibility=MemoryVisibility.PUBLIC,
        trust_level=MemoryTrustLevel.INFERRED,
        confidence=0.5,
        importance=0.2,
        created_at=now,
        updated_at=now,
        content="Low rank memory",
        content_hash="hash2",
        version=1,
        provenance=prov,
        metadata=meta,
    )

    # 1. Single calculation
    score = scoring.calculate_score(
        r1, access_count=10, semantic_similarity=0.9, now=now
    )
    assert score.final_score > 0.0
    assert score.recency == 1.0  # accessed just now

    # 2. Ranking
    ranked_scores = scoring.rank_records([r2, r1], now=now)
    # r1 should rank higher than r2
    assert len(ranked_scores) == 2
    assert ranked_scores[0].memory_id == r1.memory_id
    assert ranked_scores[1].memory_id == r2.memory_id


def test_serializer_json_dto_db() -> None:
    now = datetime.now(timezone.utc)
    prov = MemoryProvenance(
        origin="user",
        created_by="agent",
        reflection_id=uuid4(),
        workflow_id=uuid4(),
        agent_id=uuid4(),
    )
    meta = MemoryMetadata(
        importance=0.6,
        token_count=10,
        extra={"tier": MemoryTier.LONG_TERM.value, "tags": ["test-tag"]},
    )
    record = MemoryRecord(
        memory_id=uuid4(),
        memory_type=MemoryType.FACT,
        owner_id=uuid4(),
        visibility=MemoryVisibility.PRIVATE,
        trust_level=MemoryTrustLevel.USER_EXPLICIT,
        confidence=1.0,
        importance=0.6,
        created_at=now,
        updated_at=now,
        content="Testing serializer flow",
        content_hash="ser-hash",
        version=1,
        provenance=prov,
        metadata=meta,
    )

    # JSON roundtrip
    js = MemorySerializer.to_json(record)
    parsed = MemorySerializer.from_json(js)
    assert parsed.content == record.content
    assert parsed.memory_id == record.memory_id

    # DTO roundtrip
    dto = MemorySerializer.to_dto(record)
    assert dto.content == "Testing serializer flow"
    from_dto = MemorySerializer.from_dto(dto)
    assert from_dto.content == record.content

    # DB roundtrip
    db_dict = MemorySerializer.to_db(record)
    assert db_dict["content"] == record.content
    from_db = MemorySerializer.from_db(db_dict)
    assert from_db.content == record.content

    # Test conversion using MemoryChunk SQLAlchemy model
    chunk = MemoryChunk(
        id=record.memory_id,
        source_id=dto.source_id,
        content=record.content,
        content_hash=record.content_hash,
        token_count=10,
        metadata_=dto.metadata,
        created_at=now,
        updated_at=now,
        is_deleted=False,
        version=1,
    )
    from_chunk = MemorySerializer.from_db(chunk)
    assert from_chunk.content == record.content


def test_memory_index_operations() -> None:
    index = MemoryIndex()
    now = datetime.now(timezone.utc)
    prov = MemoryProvenance(origin="user", created_by="agent")
    meta = MemoryMetadata(importance=0.5, token_count=5, extra={"tags": ["fast"]})

    r1 = MemoryRecord(
        memory_id=uuid4(),
        memory_type=MemoryType.FACT,
        owner_id=uuid4(),
        visibility=MemoryVisibility.PUBLIC,
        trust_level=MemoryTrustLevel.SYSTEM,
        confidence=1.0,
        importance=0.5,
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
        content="First index record",
        content_hash="h1",
        version=1,
        provenance=prov,
        metadata=meta,
    )

    r2 = MemoryRecord(
        memory_id=uuid4(),
        memory_type=MemoryType.PREFERENCE,
        owner_id=uuid4(),
        visibility=MemoryVisibility.PUBLIC,
        trust_level=MemoryTrustLevel.SYSTEM,
        confidence=1.0,
        importance=0.5,
        created_at=now,
        updated_at=now,
        content="Second index record",
        content_hash="h2",
        version=1,
        provenance=prov,
        metadata=MemoryMetadata(
            importance=0.5, token_count=5, extra={"tags": ["slow"]}
        ),
    )

    # Add
    index.add(r1)
    index.add(r2)

    # Overwrite check
    index.add(r1)

    # Lookups
    assert index.get_by_id(r1.memory_id) == r1
    assert index.get_by_tag("fast") == [r1]
    assert index.get_by_tag("non-existent") == []
    assert index.get_by_type("preference") == [r2]
    assert index.get_by_type("non-existent") == []

    # Time range check
    range_res = index.get_by_time_range(
        now - timedelta(minutes=10), now + timedelta(minutes=10)
    )
    assert len(range_res) == 1
    assert range_res[0].memory_id == r2.memory_id

    # Remove
    index.remove(r1.memory_id)
    assert index.get_by_id(r1.memory_id) is None
    assert index.get_by_tag("fast") == []

    # Clear
    index.clear()
    assert index.get_by_id(r2.memory_id) is None
