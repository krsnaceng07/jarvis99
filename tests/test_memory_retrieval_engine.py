"""JARVIS OS - Phase 19 M4 Retrieval Engine Tests.

Tests for the Memory Retrieval Engine. Verifies:
- Frozen pipeline order
- Permission filtering
- Metadata filtering
- Scoring integration
- Top-K selection
- Deterministic results
- No writes, no side effects

PHASE: 19
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

import pytest

from core.memory.dto import (
    MemoryProvenance,
    MemoryRecord,
    MemoryTrustLevel,
    MemoryType,
    MemoryVisibility,
    RetrievalRequest,
    RetrievalResponse,
)
from core.memory.memory_repository import InMemoryRecordRepository
from core.memory.retrieval_engine import (
    RetrievalEngine,
    filter_by_metadata,
    filter_by_permission,
)
from core.memory.scoring import ScoringEngine

# =====================================================================
# Helpers
# =====================================================================

FIXED_NOW = datetime(2026, 6, 30, 12, 0, 0)


def _make_record(
    content: str = "test content",
    owner_id: Optional[UUID] = None,
    visibility: MemoryVisibility = MemoryVisibility.PRIVATE,
    trust_level: MemoryTrustLevel = MemoryTrustLevel.USER_IMPLICIT,
    confidence: float = 0.9,
    importance: float = 0.5,
    memory_type: MemoryType = MemoryType.FACT,
    hours_ago: float = 0.0,
) -> MemoryRecord:
    updated = FIXED_NOW - timedelta(hours=hours_ago)
    created = FIXED_NOW - timedelta(hours=hours_ago + 1)
    return MemoryRecord(
        memory_type=memory_type,
        owner_id=owner_id or uuid4(),
        visibility=visibility,
        trust_level=trust_level,
        confidence=confidence,
        importance=importance,
        created_at=created,
        updated_at=updated,
        provenance=MemoryProvenance(origin="test", created_by="test"),
        content=content,
        content_hash=f"hash_{uuid4().hex[:8]}",
    )


def _make_request(
    query: str = "test",
    max_chunks: int = 10,
    owner_id: Optional[UUID] = None,
    min_score: float = 0.0,
) -> RetrievalRequest:
    return RetrievalRequest(
        query=query,
        max_chunks=max_chunks,
        min_score=min_score,
        owner_id=owner_id,
    )


# =====================================================================
# Permission Filter Tests
# =====================================================================


class TestPermissionFilter:
    """Verify permission filtering."""

    def test_owner_sees_own_records(self) -> None:
        owner = uuid4()
        record = _make_record(owner_id=owner)
        result = filter_by_permission([record], owner_id=owner)
        assert len(result) == 1

    def test_owner_does_not_see_others_private(self) -> None:
        owner = uuid4()
        other = uuid4()
        record = _make_record(owner_id=other, visibility=MemoryVisibility.PRIVATE)
        result = filter_by_permission([record], owner_id=owner)
        assert len(result) == 0

    def test_public_visible_to_all(self) -> None:
        record = _make_record(visibility=MemoryVisibility.PUBLIC)
        result = filter_by_permission([record], owner_id=uuid4())
        assert len(result) == 1

    def test_system_visible_to_all(self) -> None:
        record = _make_record(visibility=MemoryVisibility.SYSTEM)
        result = filter_by_permission([record], owner_id=uuid4())
        assert len(result) == 1

    def test_agent_visible_to_all(self) -> None:
        record = _make_record(visibility=MemoryVisibility.AGENT)
        result = filter_by_permission([record], owner_id=uuid4())
        assert len(result) == 1


# =====================================================================
# Metadata Filter Tests
# =====================================================================


class TestMetadataFilter:
    """Verify metadata filtering."""

    def test_filter_by_type(self) -> None:
        records = [
            _make_record(memory_type=MemoryType.FACT),
            _make_record(memory_type=MemoryType.PREFERENCE),
        ]
        result = filter_by_metadata(records, memory_type=MemoryType.FACT)
        assert len(result) == 1

    def test_filter_by_confidence(self) -> None:
        records = [
            _make_record(confidence=0.3),
            _make_record(confidence=0.9),
        ]
        result = filter_by_metadata(records, min_confidence=0.5)
        assert len(result) == 1

    def test_exclude_archived_by_default(self) -> None:
        record = _make_record()
        record.expires_at = datetime(9999, 12, 31)
        result = filter_by_metadata([record], include_archived=False)
        assert len(result) == 0

    def test_include_archived_when_requested(self) -> None:
        record = _make_record()
        record.expires_at = datetime(9999, 12, 31)
        result = filter_by_metadata([record], include_archived=True)
        assert len(result) == 1


# =====================================================================
# Retrieval Engine Tests
# =====================================================================


class TestRetrievalEngine:
    """Verify retrieval pipeline."""

    @pytest.mark.asyncio
    async def test_basic_retrieval(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        record = _make_record(content="Python is great")
        await repo.save(record)

        request = _make_request(query="Python")
        response = await engine.retrieve(request, now=FIXED_NOW)

        assert isinstance(response, RetrievalResponse)
        assert response.metadata.chunks_searched >= 1

    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        request = _make_request(query="nonexistent")
        response = await engine.retrieve(request, now=FIXED_NOW)

        assert response.metadata.chunks_searched == 0

    @pytest.mark.asyncio
    async def test_permission_filtering(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        owner = uuid4()
        record = _make_record(
            content="secret",
            owner_id=owner,
            visibility=MemoryVisibility.PRIVATE,
        )
        await repo.save(record)

        request = _make_request(query="secret", owner_id=uuid4())
        response = await engine.retrieve(request, now=FIXED_NOW)

        assert response.metadata.chunks_searched == 1
        assert response.metadata.budget_used == 0

    @pytest.mark.asyncio
    async def test_max_chunks_limit(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        for i in range(20):
            await repo.save(_make_record(content=f"item {i}"))

        request = _make_request(query="item", max_chunks=5)
        response = await engine.retrieve(request, now=FIXED_NOW)

        assert response.metadata.budget_used <= 5

    @pytest.mark.asyncio
    async def test_scoring_applied(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        r1 = _make_record(content="high confidence", confidence=0.95)
        r2 = _make_record(content="low confidence", confidence=0.3)
        await repo.save(r1)
        await repo.save(r2)

        request = _make_request(query="confidence")
        response = await engine.retrieve(request, now=FIXED_NOW)

        if len(response.scores) >= 2:
            assert response.scores[0].final_score >= response.scores[1].final_score

    @pytest.mark.asyncio
    async def test_metrics_populated(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        await repo.save(_make_record(content="test"))

        request = _make_request(query="test")
        response = await engine.retrieve(request, now=FIXED_NOW)

        assert response.metadata.query_time_ms >= 0
        assert response.metadata.chunks_searched >= 1

    @pytest.mark.asyncio
    async def test_no_writes(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        initial_count = await repo.count()
        await repo.save(_make_record(content="test"))

        request = _make_request(query="test")
        await engine.retrieve(request, now=FIXED_NOW)

        final_count = await repo.count()
        assert final_count == initial_count + 1


# =====================================================================
# Determinism Tests
# =====================================================================


class TestRetrievalDeterminism:
    """Verify retrieval is deterministic."""

    @pytest.mark.asyncio
    async def test_same_request_same_response(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        await repo.save(_make_record(content="test"))

        request = _make_request(query="test")
        r1 = await engine.retrieve(request, now=FIXED_NOW)
        r2 = await engine.retrieve(request, now=FIXED_NOW)

        assert r1.metadata.chunks_searched == r2.metadata.chunks_searched
        assert r1.metadata.budget_used == r2.metadata.budget_used

    @pytest.mark.asyncio
    async def test_ranking_stable(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        for i in range(5):
            await repo.save(_make_record(content=f"item {i}"))

        request = _make_request(query="item")
        r1 = await engine.retrieve(request, now=FIXED_NOW)
        r2 = await engine.retrieve(request, now=FIXED_NOW)

        if len(r1.scores) >= 2:
            assert [s.memory_id for s in r1.scores] == [s.memory_id for s in r2.scores]


# =====================================================================
# Metrics Tests
# =====================================================================


class TestRetrievalMetrics:
    """Verify retrieval metrics."""

    @pytest.mark.asyncio
    async def test_candidate_count(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        for i in range(5):
            await repo.save(_make_record(content=f"test item {i}"))

        request = _make_request(query="test")
        response = await engine.retrieve(request, now=FIXED_NOW)

        assert response.metadata.chunks_searched >= 5

    @pytest.mark.asyncio
    async def test_permission_metrics(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        owner = uuid4()
        await repo.save(_make_record(content="mine", owner_id=owner))
        await repo.save(
            _make_record(
                content="secret",
                owner_id=uuid4(),
                visibility=MemoryVisibility.PRIVATE,
            )
        )

        request = _make_request(query="mine", owner_id=owner)
        response = await engine.retrieve(request, now=FIXED_NOW)

        assert response.metadata.budget_used >= 1


# =====================================================================
# Telemetry, Deduplication, and Validation Tests
# =====================================================================
from core.interfaces import EventBusInterface, InterAgentMessage


class MockEventBus(EventBusInterface):
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        self.published.append((topic, message))
        return True

    async def subscribe(self, topic: str, callback: any) -> str:
        return "sub-id"

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class TestRetrievalPipelineDetails:
    """Verify deduplication, validation clamping, and event publishing."""

    @pytest.mark.asyncio
    async def test_deduplication_by_content_hash(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        # Save duplicate records with same content hash
        r1 = _make_record(
            content="duplicate content", visibility=MemoryVisibility.PUBLIC
        )
        r2 = _make_record(
            content="duplicate content", visibility=MemoryVisibility.PUBLIC
        )
        r2.content_hash = r1.content_hash

        await repo.save(r1)
        await repo.save(r2)

        request = _make_request(query="duplicate")
        response = await engine.retrieve(request, now=FIXED_NOW)

        # Deduplication must return only one chunk
        assert len(response.chunks) == 1
        assert len(response.scores) == 1

    @pytest.mark.asyncio
    async def test_request_validation_clamping(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetrievalEngine(repo, ScoringEngine())

        await repo.save(
            _make_record(content="valid item", visibility=MemoryVisibility.PUBLIC)
        )

        # Test request with max_chunks exceeding hard max 100
        request = _make_request(query="valid", max_chunks=200)
        response = await engine.retrieve(request, now=FIXED_NOW)

        # Remaining budget check to confirm clamped logic
        assert response.metadata.budget_remaining == 100 - len(response.chunks)

    @pytest.mark.asyncio
    async def test_telemetry_events_publishing(self) -> None:
        repo = InMemoryRecordRepository()
        bus = MockEventBus()
        engine = RetrievalEngine(repo, ScoringEngine(), event_bus=bus)

        await repo.save(
            _make_record(content="telemetry check", visibility=MemoryVisibility.PUBLIC)
        )

        request = _make_request(query="telemetry")
        await engine.retrieve(request, now=FIXED_NOW)

        # Verify started and completed events are published
        assert len(bus.published) == 2
        assert bus.published[0][0] == "memory.retrieve.started"
        assert bus.published[1][0] == "memory.retrieve.completed"

    @pytest.mark.asyncio
    async def test_candidate_provider_integration(self) -> None:
        class DummyCandidateProvider:
            @property
            def name(self) -> str:
                return "dummy"

            def supports(self, tier: MemoryTier) -> bool:
                return True

            async def search(
                self,
                query: str,
                owner_id: Optional[UUID] = None,
                limit: int = 200,
            ) -> List[MemoryRecord]:
                return [
                    _make_record(
                        content="dummy provider hit",
                        visibility=MemoryVisibility.PUBLIC,
                    )
                ]

        repo = InMemoryRecordRepository()
        provider = DummyCandidateProvider()
        engine = RetrievalEngine(repo, ScoringEngine(), candidate_provider=provider)

        request = _make_request(query="dummy")
        response = await engine.retrieve(request, now=FIXED_NOW)

        # Verify search method on provider was called and returned the record
        assert len(response.chunks) == 1
        assert response.chunks[0].content == "dummy provider hit"
        # Verify RetrievalReason is correctly populated inside metadata
        assert response.chunks[0].metadata.extra["retrieval_reason"] == "keyword"
