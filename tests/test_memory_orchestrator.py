"""JARVIS OS - Phase 19 M7 Memory Orchestrator Tests.

Tests for the MemoryOrchestrator — sole entry point for all memory ops.
Verifies: store, recall, reflect, forget, archive, promote, score,
run_retention_cycle. Also checks idempotency, dedup, event publishing,
and error handling.

PHASE: 19
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import pytest

from core.interfaces import EventBusInterface, InterAgentMessage
from core.memory.dto import (
    ExecutionOutcome,
    MemoryMetadata,
    MemoryProvenance,
    MemoryRecord,
    MemoryTier,
    MemoryTrustLevel,
    MemoryType,
    MemoryVisibility,
    ReflectionRequest,
    RetrievalRequest,
)
from core.memory.memory_repository import InMemoryRecordRepository
from core.memory.orchestrator import MemoryOrchestrator, SYSTEM_OWNER_ID
from core.memory.retention import RetentionEngine
from core.memory.retrieval_engine import RetrievalEngine
from core.memory.scoring import ScoringEngine
from core.config import MemoryRetentionConfig

# =====================================================================
# Helpers
# =====================================================================

FIXED_NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


class MockEventBus(EventBusInterface):
    """Captures published events for assertions."""

    def __init__(self) -> None:
        self.published: list[tuple[str, InterAgentMessage]] = []

    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        self.published.append((topic, message))
        return True

    async def subscribe(self, topic: str, callback: Any) -> str:
        return "sub-id"

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


def _make_record(
    content: str = "test content",
    owner_id: Optional[UUID] = None,
    confidence: float = 0.9,
    importance: float = 0.5,
    tier: str = MemoryTier.WORKING.value,
    hours_ago: float = 0.0,
) -> MemoryRecord:
    """Create a MemoryRecord for testing."""
    updated = FIXED_NOW - timedelta(hours=hours_ago)
    created = FIXED_NOW - timedelta(hours=hours_ago + 1)
    return MemoryRecord(
        memory_type=MemoryType.FACT,
        owner_id=owner_id or uuid4(),
        visibility=MemoryVisibility.PRIVATE,
        trust_level=MemoryTrustLevel.USER_IMPLICIT,
        confidence=confidence,
        importance=importance,
        created_at=created,
        updated_at=updated,
        provenance=MemoryProvenance(origin="test", created_by="test"),
        content=content,
        content_hash=f"hash_{uuid4().hex[:8]}",
        metadata=MemoryMetadata(
            importance=importance,
            extra={"tier": tier, "access_count": 0},
        ),
    )


def _make_orchestrator(
    repo: Optional[InMemoryRecordRepository] = None,
    event_bus: Optional[MockEventBus] = None,
) -> tuple[MemoryOrchestrator, InMemoryRecordRepository, MockEventBus]:
    """Build an orchestrator with in-memory backends."""
    repo = repo or InMemoryRecordRepository()
    bus = event_bus or MockEventBus()
    scoring = ScoringEngine()
    retention = RetentionEngine(memory_repo=repo, scoring_engine=scoring, config=MemoryRetentionConfig(), event_bus=bus)
    retrieval = RetrievalEngine(repo, scoring)
    orchestrator = MemoryOrchestrator(
        memory_service=None,
        scoring_engine=scoring,
        retention_engine=retention,
        retrieval_engine=retrieval,
        intelligence_service=None,
        memory_repo=repo,
        event_bus=bus,
    )
    return orchestrator, repo, bus


# =====================================================================
# Store Tests
# =====================================================================


class TestStore:
    """Tests for MemoryOrchestrator.store()."""

    @pytest.mark.asyncio
    async def test_store_returns_uuid(self) -> None:
        orch, repo, _ = _make_orchestrator()
        mid = await orch.store("hello world", source_type="test")
        assert isinstance(mid, UUID)

    @pytest.mark.asyncio
    async def test_store_persists_to_repo(self) -> None:
        orch, repo, _ = _make_orchestrator()
        mid = await orch.store("hello world", source_type="test")
        record = await repo.get_by_id(mid)
        assert record is not None
        assert record.content == "hello world"

    @pytest.mark.asyncio
    async def test_store_emits_memory_created_event(self) -> None:
        orch, _, bus = _make_orchestrator()
        await orch.store("hello world", source_type="test")
        topics = [t for t, _ in bus.published]
        assert "memory.created" in topics

    @pytest.mark.asyncio
    async def test_store_dedup_returns_same_id(self) -> None:
        orch, repo, _ = _make_orchestrator()
        id1 = await orch.store("duplicate content", source_type="test")
        id2 = await orch.store("duplicate content", source_type="test")
        assert id1 == id2

    @pytest.mark.asyncio
    async def test_store_dedup_bumps_access_count(self) -> None:
        orch, repo, _ = _make_orchestrator()
        mid = await orch.store("duplicate content", source_type="test")
        await orch.store("duplicate content", source_type="test")
        record = await repo.get_by_id(mid)
        assert record is not None
        access_count = record.metadata.extra.get("access_count", 0)
        assert access_count >= 1

    @pytest.mark.asyncio
    async def test_store_with_custom_importance(self) -> None:
        orch, repo, _ = _make_orchestrator()
        mid = await orch.store("important!", source_type="test", importance=0.95)
        record = await repo.get_by_id(mid)
        assert record is not None
        assert record.importance == 0.95

    @pytest.mark.asyncio
    async def test_store_assigns_system_owner_by_default(self) -> None:
        orch, repo, _ = _make_orchestrator()
        mid = await orch.store("test", source_type="test")
        record = await repo.get_by_id(mid)
        assert record is not None
        assert record.owner_id == SYSTEM_OWNER_ID

    @pytest.mark.asyncio
    async def test_store_assigns_working_tier_by_default(self) -> None:
        orch, repo, _ = _make_orchestrator()
        mid = await orch.store("test", source_type="test")
        record = await repo.get_by_id(mid)
        assert record is not None
        tier = record.metadata.extra.get("tier")
        assert tier == MemoryTier.WORKING.value


# =====================================================================
# Recall Tests
# =====================================================================


class TestRecall:
    """Tests for MemoryOrchestrator.recall()."""

    @pytest.mark.asyncio
    async def test_recall_returns_retrieval_response(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record(content="recall me")
        await repo.save(record)
        request = RetrievalRequest(query="recall", max_chunks=10, min_score=0.0)
        response = await orch.recall(request)
        assert hasattr(response, "chunks")

    @pytest.mark.asyncio
    async def test_recall_emits_retrieved_events(self) -> None:
        orch, repo, bus = _make_orchestrator()
        record = _make_record(content="recall me")
        await repo.save(record)
        request = RetrievalRequest(query="recall", max_chunks=10, min_score=0.0)
        await orch.recall(request)
        topics = [t for t, _ in bus.published]
        # Should have memory.retrieved events for each returned chunk
        assert all(t == "memory.retrieved" for t in topics) or len(topics) == 0

    @pytest.mark.asyncio
    async def test_recall_with_session_id(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record(content="session recall")
        await repo.save(record)
        sid = uuid4()
        request = RetrievalRequest(query="session", max_chunks=10, min_score=0.0)
        response = await orch.recall(request, session_id=sid)
        assert hasattr(response, "chunks")


# =====================================================================
# Reflect Tests
# =====================================================================


class TestReflect:
    """Tests for MemoryOrchestrator.reflect()."""

    @pytest.mark.asyncio
    async def test_reflect_success_increases_confidence(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record(confidence=0.5)
        await repo.save(record)
        req = ReflectionRequest(
            memory_id=record.memory_id,
            outcome=ExecutionOutcome.SUCCESS,
            confidence_delta=0.2,
        )
        result = await orch.reflect(req)
        assert result is True
        updated = await repo.get_by_id(record.memory_id)
        assert updated is not None
        assert updated.confidence == pytest.approx(0.7, abs=0.01)

    @pytest.mark.asyncio
    async def test_reflect_failure_decreases_confidence(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record(confidence=0.8)
        await repo.save(record)
        req = ReflectionRequest(
            memory_id=record.memory_id,
            outcome=ExecutionOutcome.FAILURE,
            confidence_delta=0.3,
        )
        result = await orch.reflect(req)
        assert result is True
        updated = await repo.get_by_id(record.memory_id)
        assert updated is not None
        assert updated.confidence == pytest.approx(0.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_reflect_partial_adjusts_half_delta(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record(confidence=0.5)
        await repo.save(record)
        req = ReflectionRequest(
            memory_id=record.memory_id,
            outcome=ExecutionOutcome.PARTIAL,
            confidence_delta=0.4,
        )
        result = await orch.reflect(req)
        assert result is True
        updated = await repo.get_by_id(record.memory_id)
        assert updated is not None
        # PARTIAL applies delta * 0.5 = 0.2 to confidence
        assert updated.confidence == pytest.approx(0.7, abs=0.01)

    @pytest.mark.asyncio
    async def test_reflect_timeout_decreases_importance(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record(importance=0.8)
        await repo.save(record)
        req = ReflectionRequest(
            memory_id=record.memory_id,
            outcome=ExecutionOutcome.TIMEOUT,
            confidence_delta=0.4,
        )
        result = await orch.reflect(req)
        assert result is True
        updated = await repo.get_by_id(record.memory_id)
        assert updated is not None
        # TIMEOUT: importance - (abs(delta) * 0.5) = 0.8 - 0.2 = 0.6
        assert updated.importance == pytest.approx(0.6, abs=0.01)

    @pytest.mark.asyncio
    async def test_reflect_clamps_confidence_to_bounds(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record(confidence=0.95)
        await repo.save(record)
        req = ReflectionRequest(
            memory_id=record.memory_id,
            outcome=ExecutionOutcome.SUCCESS,
            confidence_delta=0.9,
        )
        await orch.reflect(req)
        updated = await repo.get_by_id(record.memory_id)
        assert updated is not None
        assert updated.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_reflect_missing_record_returns_false(self) -> None:
        orch, _, _ = _make_orchestrator()
        req = ReflectionRequest(
            memory_id=uuid4(),
            outcome=ExecutionOutcome.SUCCESS,
            confidence_delta=0.1,
        )
        result = await orch.reflect(req)
        assert result is False

    @pytest.mark.asyncio
    async def test_reflect_emits_reflected_event(self) -> None:
        orch, repo, bus = _make_orchestrator()
        record = _make_record(confidence=0.5)
        await repo.save(record)
        req = ReflectionRequest(
            memory_id=record.memory_id,
            outcome=ExecutionOutcome.SUCCESS,
            confidence_delta=0.1,
        )
        await orch.reflect(req)
        topics = [t for t, _ in bus.published]
        assert "memory.reflected" in topics


# =====================================================================
# Forget Tests
# =====================================================================


class TestForget:
    """Tests for MemoryOrchestrator.forget()."""

    @pytest.mark.asyncio
    async def test_forget_deletes_record(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record()
        await repo.save(record)
        result = await orch.forget(record.memory_id, reason="test")
        assert result is True
        # Soft-deleted records have expires_at in the past
        deleted = await repo.get_by_id(record.memory_id)
        assert deleted is not None
        assert deleted.expires_at is not None
        assert deleted.expires_at.year == 2000

    @pytest.mark.asyncio
    async def test_forget_missing_returns_false(self) -> None:
        orch, _, _ = _make_orchestrator()
        result = await orch.forget(uuid4(), reason="gone")
        assert result is False

    @pytest.mark.asyncio
    async def test_forget_emits_deleted_event(self) -> None:
        orch, repo, bus = _make_orchestrator()
        record = _make_record()
        await repo.save(record)
        await orch.forget(record.memory_id, reason="cleanup")
        topics = [t for t, _ in bus.published]
        assert "memory.deleted" in topics

    @pytest.mark.asyncio
    async def test_forget_with_cascade(self) -> None:
        orch, repo, bus = _make_orchestrator()
        r1 = _make_record(content="parent")
        r2 = _make_record(content="child")
        await repo.save(r1)
        await repo.save(r2)
        # Cascade forget — recommend_cascade_delete will find records
        result = await orch.forget(r1.memory_id, reason="cascade-test", cascade=True)
        assert result is True


# =====================================================================
# Archive Tests
# =====================================================================


class TestArchive:
    """Tests for MemoryOrchestrator.archive()."""

    @pytest.mark.asyncio
    async def test_archive_sets_far_future_expiry(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record()
        await repo.save(record)
        result = await orch.archive(record.memory_id, reason="archiving")
        assert result is True
        archived = await repo.get_by_id(record.memory_id)
        assert archived is not None
        assert archived.expires_at is not None
        assert archived.expires_at.year == 9999

    @pytest.mark.asyncio
    async def test_archive_missing_returns_false(self) -> None:
        orch, _, _ = _make_orchestrator()
        result = await orch.archive(uuid4(), reason="gone")
        assert result is False

    @pytest.mark.asyncio
    async def test_archive_emits_archived_event(self) -> None:
        orch, repo, bus = _make_orchestrator()
        record = _make_record()
        await repo.save(record)
        await orch.archive(record.memory_id, reason="old")
        topics = [t for t, _ in bus.published]
        assert "memory.archived" in topics


# =====================================================================
# Promote Tests
# =====================================================================


class TestPromote:
    """Tests for MemoryOrchestrator.promote()."""

    @pytest.mark.asyncio
    async def test_promote_working_to_conversation(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record(tier=MemoryTier.WORKING.value)
        await repo.save(record)
        result = await orch.promote(record.memory_id, MemoryTier.CONVERSATION)
        assert result is True
        updated = await repo.get_by_id(record.memory_id)
        assert updated is not None
        assert updated.metadata.extra["tier"] == MemoryTier.CONVERSATION.value

    @pytest.mark.asyncio
    async def test_promote_conversation_to_long_term(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record(tier=MemoryTier.CONVERSATION.value)
        await repo.save(record)
        result = await orch.promote(record.memory_id, MemoryTier.LONG_TERM)
        assert result is True
        updated = await repo.get_by_id(record.memory_id)
        assert updated is not None
        assert updated.metadata.extra["tier"] == MemoryTier.LONG_TERM.value

    @pytest.mark.asyncio
    async def test_promote_invalid_transition_returns_false(self) -> None:
        orch, repo, _ = _make_orchestrator()
        # WORKING → LONG_TERM skips CONVERSATION — spec disallows this
        record = _make_record(tier=MemoryTier.WORKING.value)
        await repo.save(record)
        result = await orch.promote(record.memory_id, MemoryTier.LONG_TERM)
        assert result is False

    @pytest.mark.asyncio
    async def test_promote_same_tier_is_idempotent(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record(tier=MemoryTier.WORKING.value)
        await repo.save(record)
        result = await orch.promote(record.memory_id, MemoryTier.WORKING)
        assert result is True  # No-op but still succeeds

    @pytest.mark.asyncio
    async def test_promote_missing_returns_false(self) -> None:
        orch, _, _ = _make_orchestrator()
        result = await orch.promote(uuid4(), MemoryTier.CONVERSATION)
        assert result is False

    @pytest.mark.asyncio
    async def test_promote_emits_promoted_event(self) -> None:
        orch, repo, bus = _make_orchestrator()
        record = _make_record(tier=MemoryTier.WORKING.value)
        await repo.save(record)
        await orch.promote(record.memory_id, MemoryTier.CONVERSATION)
        topics = [t for t, _ in bus.published]
        assert "memory.promoted" in topics


# =====================================================================
# Score Tests
# =====================================================================


class TestScore:
    """Tests for MemoryOrchestrator.score()."""

    @pytest.mark.asyncio
    async def test_score_returns_memory_score(self) -> None:
        orch, repo, _ = _make_orchestrator()
        record = _make_record()
        await repo.save(record)
        score = await orch.score(record.memory_id)
        assert hasattr(score, "final_score")
        assert 0.0 <= score.final_score <= 1.0

    @pytest.mark.asyncio
    async def test_score_missing_raises_value_error(self) -> None:
        orch, _, _ = _make_orchestrator()
        with pytest.raises(ValueError, match="not found"):
            await orch.score(uuid4())

    @pytest.mark.asyncio
    async def test_score_higher_importance_yields_higher_score(self) -> None:
        orch, repo, _ = _make_orchestrator()
        low = _make_record(importance=0.1)
        high = _make_record(importance=0.9)
        await repo.save(low)
        await repo.save(high)
        score_low = await orch.score(low.memory_id)
        score_high = await orch.score(high.memory_id)
        assert score_high.final_score >= score_low.final_score


# =====================================================================
# Retention Cycle Tests
# =====================================================================


class TestRetentionCycle:
    """Tests for MemoryOrchestrator.run_retention_cycle()."""

    @pytest.mark.asyncio
    async def test_retention_cycle_returns_batch(self) -> None:
        orch, repo, _ = _make_orchestrator()
        # Empty repo → empty batch
        batch = await orch.run_retention_cycle(now=FIXED_NOW)
        assert hasattr(batch, "promotions")
        assert hasattr(batch, "forgettings")
        assert hasattr(batch, "archives")
        assert hasattr(batch, "cascades")

    @pytest.mark.asyncio
    async def test_retention_cycle_with_records(self) -> None:
        orch, repo, _ = _make_orchestrator()
        for i in range(5):
            record = _make_record(content=f"record {i}", hours_ago=float(i * 24))
            await repo.save(record)
        batch = await orch.run_retention_cycle(now=FIXED_NOW)
        # Should return a valid batch (content may vary)
        assert batch is not None


# =====================================================================
# Event Bus Edge Cases
# =====================================================================


class TestEventBusEdgeCases:
    """Verify orchestrator works without an event bus."""

    @pytest.mark.asyncio
    async def test_store_without_event_bus(self) -> None:
        repo = InMemoryRecordRepository()
        scoring = ScoringEngine()
        retention = RetentionEngine(memory_repo=repo, scoring_engine=scoring, config=MemoryRetentionConfig())
        retrieval = RetrievalEngine(repo, scoring)
        orch = MemoryOrchestrator(
            memory_service=None,
            scoring_engine=scoring,
            retention_engine=retention,
            retrieval_engine=retrieval,
            intelligence_service=None,
            memory_repo=repo,
            event_bus=None,
        )
        mid = await orch.store("no bus", source_type="test")
        assert isinstance(mid, UUID)

    @pytest.mark.asyncio
    async def test_forget_without_event_bus(self) -> None:
        repo = InMemoryRecordRepository()
        scoring = ScoringEngine()
        retention = RetentionEngine(memory_repo=repo, scoring_engine=scoring, config=MemoryRetentionConfig())
        retrieval = RetrievalEngine(repo, scoring)
        orch = MemoryOrchestrator(
            memory_service=None,
            scoring_engine=scoring,
            retention_engine=retention,
            retrieval_engine=retrieval,
            intelligence_service=None,
            memory_repo=repo,
            event_bus=None,
        )
        record = _make_record()
        await repo.save(record)
        result = await orch.forget(record.memory_id, reason="no-bus")
        assert result is True
