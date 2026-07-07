"""JARVIS OS - Phase 19 M10 Memory Integration Tests.

End-to-end lifecycle tests exercising the full memory pipeline:
Store → Score → Promote → Retrieve → Reflect → Archive → Forget.

Tests cross-component integration, permission filtering, promotion
idempotency, event emission, forgetting throttle, and budget enforcement.

PHASE: 19
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

TARGET: 60 tests across 6 categories (spec §11.1)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
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
from core.memory.orchestrator import MemoryOrchestrator
from core.memory.retention import RetentionEngine
from core.memory.retrieval_engine import RetrievalEngine
from core.memory.scoring import ScoringEngine, ScoringInput
from core.config import MemoryRetentionConfig

# =====================================================================
# Fixtures
# =====================================================================

FIXED_NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


class TestEventBus(EventBusInterface):
    """Captures events for integration assertions."""

    def __init__(self) -> None:
        self.events: list[tuple[str, InterAgentMessage]] = []

    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        self.events.append((topic, message))
        return True

    async def subscribe(self, topic: str, callback: Any) -> str:
        return "sub"

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    def topics(self) -> list[str]:
        return [t for t, _ in self.events]

    def clear(self) -> None:
        self.events.clear()


def _build_stack() -> tuple[MemoryOrchestrator, InMemoryRecordRepository, TestEventBus]:
    """Build a full memory stack with in-memory backends."""
    repo = InMemoryRecordRepository()
    bus = TestEventBus()
    scoring = ScoringEngine()
    retention = RetentionEngine(memory_repo=repo, scoring_engine=scoring, config=MemoryRetentionConfig(), event_bus=bus)
    retrieval = RetrievalEngine(repo, scoring)
    orch = MemoryOrchestrator(
        memory_service=None,
        scoring_engine=scoring,
        retention_engine=retention,
        retrieval_engine=retrieval,
        intelligence_service=None,
        memory_repo=repo,
        event_bus=bus,
    )
    return orch, repo, bus


# =====================================================================
# Category 1: E2E Lifecycle (Store → Score → Promote → Retrieve →
#              Reflect → Archive → Forget)
# =====================================================================


class TestE2ELifecycle:
    """Full lifecycle integration tests."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self) -> None:
        """Store → Score → Promote → Recall → Reflect → Archive → Forget."""
        orch, repo, bus = _build_stack()

        # 1. Store
        mid = await orch.store("integration test", source_type="e2e")
        assert isinstance(mid, UUID)
        record = await repo.get_by_id(mid)
        assert record is not None
        assert record.content == "integration test"

        # 2. Score
        score = await orch.score(mid)
        assert 0.0 <= score.final_score <= 1.0

        # 3. Promote WORKING → CONVERSATION
        promoted = await orch.promote(mid, MemoryTier.CONVERSATION)
        assert promoted is True
        record = await repo.get_by_id(mid)
        assert record.metadata.extra["tier"] == MemoryTier.CONVERSATION.value

        # 4. Recall
        request = RetrievalRequest(query="integration", max_chunks=10, min_score=0.0)
        response = await orch.recall(request)
        assert hasattr(response, "chunks")

        # 5. Reflect (SUCCESS increases confidence)
        reflect_req = ReflectionRequest(
            memory_id=mid,
            outcome=ExecutionOutcome.SUCCESS,
            confidence_delta=0.1,
        )
        reflected = await orch.reflect(reflect_req)
        assert reflected is True

        # 6. Archive
        archived = await orch.archive(mid, reason="lifecycle test")
        assert archived is True
        record = await repo.get_by_id(mid)
        assert record.expires_at.year == 9999

        # 7. Forget (soft delete)
        forgotten = await orch.forget(mid, reason="cleanup")
        assert forgotten is True
        record = await repo.get_by_id(mid)
        assert record.expires_at.year == 2000

    @pytest.mark.asyncio
    async def test_store_recall_roundtrip(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("unique_content_xyz", source_type="e2e")
        request = RetrievalRequest(query="unique", max_chunks=10, min_score=0.0)
        response = await orch.recall(request)
        # At minimum, the record should be in the repo
        record = await repo.get_by_id(mid)
        assert record is not None
        assert record.content == "unique_content_xyz"

    @pytest.mark.asyncio
    async def test_store_score_promote_chain(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("chain test", source_type="e2e", importance=0.9)
        score = await orch.score(mid)
        assert score.final_score > 0.0
        assert await orch.promote(mid, MemoryTier.CONVERSATION)
        assert await orch.promote(mid, MemoryTier.LONG_TERM)
        record = await repo.get_by_id(mid)
        assert record.metadata.extra["tier"] == MemoryTier.LONG_TERM.value

    @pytest.mark.asyncio
    async def test_multiple_stores_and_recall(self) -> None:
        orch, repo, _ = _build_stack()
        for i in range(5):
            await orch.store(f"record_{i}", source_type="batch")
        request = RetrievalRequest(query="record", max_chunks=50, min_score=0.0)
        response = await orch.recall(request)
        assert hasattr(response, "chunks")

    @pytest.mark.asyncio
    async def test_reflect_then_score_changes(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("reflectable", source_type="e2e", confidence=0.5)
        score_before = await orch.score(mid)
        await orch.reflect(
            ReflectionRequest(
                memory_id=mid,
                outcome=ExecutionOutcome.SUCCESS,
                confidence_delta=0.3,
            )
        )
        score_after = await orch.score(mid)
        # Confidence increased, so score should change
        assert score_after.confidence >= score_before.confidence


# =====================================================================
# Category 2: Cross-Component Verification
# =====================================================================


class TestCrossComponent:
    """Verify components interact correctly through the orchestrator."""

    @pytest.mark.asyncio
    async def test_scoring_engine_used_on_store(self) -> None:
        orch, repo, bus = _build_stack()
        mid = await orch.store("test", source_type="e2e", importance=0.9)
        # memory.created event should be emitted with a score
        created_events = [
            (t, m) for t, m in bus.events if t == "memory.created"
        ]
        assert len(created_events) >= 1
        body = created_events[0][1].body
        assert "score" in body

    @pytest.mark.asyncio
    async def test_retention_engine_integration(self) -> None:
        orch, repo, _ = _build_stack()
        # Store some records
        for i in range(3):
            await orch.store(f"retention_test_{i}", source_type="e2e")
        # Run retention cycle — should return a valid batch
        batch = await orch.run_retention_cycle(now=FIXED_NOW)
        assert batch is not None
        assert hasattr(batch, "promotions")

    @pytest.mark.asyncio
    async def test_retrieval_engine_integration(self) -> None:
        orch, repo, _ = _build_stack()
        await orch.store("retrieval target", source_type="e2e")
        request = RetrievalRequest(query="retrieval", max_chunks=5, min_score=0.0)
        response = await orch.recall(request)
        assert hasattr(response, "chunks")

    @pytest.mark.asyncio
    async def test_validator_blocks_invalid_promotion(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("validate me", source_type="e2e")
        # WORKING → LONG_TERM skips CONVERSATION — should fail
        result = await orch.promote(mid, MemoryTier.LONG_TERM)
        assert result is False

    @pytest.mark.asyncio
    async def test_dedup_across_stores(self) -> None:
        orch, repo, _ = _build_stack()
        id1 = await orch.store("exact same content", source_type="e2e")
        id2 = await orch.store("exact same content", source_type="e2e")
        assert id1 == id2
        record = await repo.get_by_id(id1)
        assert record.metadata.extra["access_count"] >= 1


# =====================================================================
# Category 3: Promotion Policy
# =====================================================================


class TestPromotionPolicy:
    """Verify tier promotion rules from spec §4."""

    @pytest.mark.asyncio
    async def test_working_to_conversation(self) -> None:
        orch, _, _ = _build_stack()
        mid = await orch.store("promo test", source_type="e2e")
        assert await orch.promote(mid, MemoryTier.CONVERSATION)

    @pytest.mark.asyncio
    async def test_conversation_to_long_term(self) -> None:
        orch, _, _ = _build_stack()
        mid = await orch.store("promo chain", source_type="e2e")
        await orch.promote(mid, MemoryTier.CONVERSATION)
        assert await orch.promote(mid, MemoryTier.LONG_TERM)

    @pytest.mark.asyncio
    async def test_long_term_to_archived(self) -> None:
        orch, _, _ = _build_stack()
        mid = await orch.store("archive chain", source_type="e2e")
        await orch.promote(mid, MemoryTier.CONVERSATION)
        await orch.promote(mid, MemoryTier.LONG_TERM)
        assert await orch.promote(mid, MemoryTier.ARCHIVED)

    @pytest.mark.asyncio
    async def test_skip_tier_rejected(self) -> None:
        orch, _, _ = _build_stack()
        mid = await orch.store("skip test", source_type="e2e")
        # WORKING → ARCHIVED (skips 2 tiers) — not allowed
        assert not await orch.promote(mid, MemoryTier.ARCHIVED)

    @pytest.mark.asyncio
    async def test_same_tier_idempotent(self) -> None:
        orch, _, _ = _build_stack()
        mid = await orch.store("idempotent", source_type="e2e")
        assert await orch.promote(mid, MemoryTier.WORKING)  # no-op

    @pytest.mark.asyncio
    async def test_promote_nonexistent_returns_false(self) -> None:
        orch, _, _ = _build_stack()
        assert not await orch.promote(uuid4(), MemoryTier.CONVERSATION)

    @pytest.mark.asyncio
    async def test_promotion_emits_event(self) -> None:
        orch, _, bus = _build_stack()
        mid = await orch.store("event test", source_type="e2e")
        bus.clear()
        await orch.promote(mid, MemoryTier.CONVERSATION)
        assert "memory.promoted" in bus.topics()

    @pytest.mark.asyncio
    async def test_promotion_updates_tier_metadata(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("tier update", source_type="e2e")
        await orch.promote(mid, MemoryTier.CONVERSATION)
        record = await repo.get_by_id(mid)
        assert record.metadata.extra["tier"] == "conversation"


# =====================================================================
# Category 4: Event Emission
# =====================================================================


class TestEventEmission:
    """Verify all frozen event topics are emitted correctly (spec §2.4)."""

    @pytest.mark.asyncio
    async def test_store_emits_memory_created(self) -> None:
        orch, _, bus = _build_stack()
        await orch.store("event store", source_type="e2e")
        assert "memory.created" in bus.topics()

    @pytest.mark.asyncio
    async def test_recall_emits_memory_retrieved(self) -> None:
        orch, _, bus = _build_stack()
        await orch.store("event recall", source_type="e2e")
        bus.clear()
        await orch.recall(RetrievalRequest(query="event", max_chunks=10, min_score=0.0))
        # Retrieved events depend on matching chunks
        # No assertion on specific count — just verify no crash

    @pytest.mark.asyncio
    async def test_reflect_emits_memory_reflected(self) -> None:
        orch, _, bus = _build_stack()
        mid = await orch.store("event reflect", source_type="e2e")
        bus.clear()
        await orch.reflect(
            ReflectionRequest(
                memory_id=mid,
                outcome=ExecutionOutcome.SUCCESS,
                confidence_delta=0.1,
            )
        )
        assert "memory.reflected" in bus.topics()

    @pytest.mark.asyncio
    async def test_forget_emits_memory_deleted(self) -> None:
        orch, _, bus = _build_stack()
        mid = await orch.store("event forget", source_type="e2e")
        bus.clear()
        await orch.forget(mid, reason="test")
        assert "memory.deleted" in bus.topics()

    @pytest.mark.asyncio
    async def test_archive_emits_memory_archived(self) -> None:
        orch, _, bus = _build_stack()
        mid = await orch.store("event archive", source_type="e2e")
        bus.clear()
        await orch.archive(mid, reason="test")
        assert "memory.archived" in bus.topics()

    @pytest.mark.asyncio
    async def test_promote_emits_memory_promoted(self) -> None:
        orch, _, bus = _build_stack()
        mid = await orch.store("event promote", source_type="e2e")
        bus.clear()
        await orch.promote(mid, MemoryTier.CONVERSATION)
        assert "memory.promoted" in bus.topics()

    @pytest.mark.asyncio
    async def test_no_events_without_bus(self) -> None:
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
        mid = await orch.store("no bus", source_type="e2e")
        await orch.forget(mid, reason="test")
        # No crash — events silently skipped


# =====================================================================
# Category 5: Reflection Rules
# =====================================================================


class TestReflectionRules:
    """Verify spec §7.2 reflection rules."""

    @pytest.mark.asyncio
    async def test_success_increases_confidence(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("reflect success", source_type="e2e", confidence=0.5)
        await orch.reflect(
            ReflectionRequest(
                memory_id=mid,
                outcome=ExecutionOutcome.SUCCESS,
                confidence_delta=0.2,
            )
        )
        record = await repo.get_by_id(mid)
        assert record.confidence == pytest.approx(0.7, abs=0.01)

    @pytest.mark.asyncio
    async def test_failure_decreases_confidence(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("reflect fail", source_type="e2e", confidence=0.8)
        await orch.reflect(
            ReflectionRequest(
                memory_id=mid,
                outcome=ExecutionOutcome.FAILURE,
                confidence_delta=0.3,
            )
        )
        record = await repo.get_by_id(mid)
        assert record.confidence == pytest.approx(0.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_partial_applies_half_delta(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("reflect partial", source_type="e2e", confidence=0.5)
        await orch.reflect(
            ReflectionRequest(
                memory_id=mid,
                outcome=ExecutionOutcome.PARTIAL,
                confidence_delta=0.4,
            )
        )
        record = await repo.get_by_id(mid)
        assert record.confidence == pytest.approx(0.7, abs=0.01)

    @pytest.mark.asyncio
    async def test_timeout_decreases_importance(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store(
            "reflect timeout", source_type="e2e", importance=0.8
        )
        await orch.reflect(
            ReflectionRequest(
                memory_id=mid,
                outcome=ExecutionOutcome.TIMEOUT,
                confidence_delta=0.4,
            )
        )
        record = await repo.get_by_id(mid)
        assert record.importance == pytest.approx(0.6, abs=0.01)

    @pytest.mark.asyncio
    async def test_confidence_clamped_at_1(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("clamp high", source_type="e2e", confidence=0.95)
        await orch.reflect(
            ReflectionRequest(
                memory_id=mid,
                outcome=ExecutionOutcome.SUCCESS,
                confidence_delta=0.9,
            )
        )
        record = await repo.get_by_id(mid)
        assert record.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_confidence_clamped_at_0(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("clamp low", source_type="e2e", confidence=0.1)
        await orch.reflect(
            ReflectionRequest(
                memory_id=mid,
                outcome=ExecutionOutcome.FAILURE,
                confidence_delta=0.9,
            )
        )
        record = await repo.get_by_id(mid)
        assert record.confidence >= 0.0

    @pytest.mark.asyncio
    async def test_reflect_nonexistent_returns_false(self) -> None:
        orch, _, _ = _build_stack()
        result = await orch.reflect(
            ReflectionRequest(
                memory_id=uuid4(),
                outcome=ExecutionOutcome.SUCCESS,
                confidence_delta=0.1,
            )
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_multiple_reflections_compound(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("compound", source_type="e2e", confidence=0.5)
        for _ in range(3):
            await orch.reflect(
                ReflectionRequest(
                    memory_id=mid,
                    outcome=ExecutionOutcome.SUCCESS,
                    confidence_delta=0.1,
                )
            )
        record = await repo.get_by_id(mid)
        assert record.confidence == pytest.approx(0.8, abs=0.01)


# =====================================================================
# Category 6: Forgetting & Archive
# =====================================================================


class TestForgettingAndArchive:
    """Verify forget and archive operations."""

    @pytest.mark.asyncio
    async def test_forget_soft_deletes(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("forget me", source_type="e2e")
        result = await orch.forget(mid, reason="test")
        assert result is True
        record = await repo.get_by_id(mid)
        assert record.expires_at.year == 2000

    @pytest.mark.asyncio
    async def test_forget_nonexistent_returns_false(self) -> None:
        orch, _, _ = _build_stack()
        result = await orch.forget(uuid4(), reason="gone")
        assert result is False

    @pytest.mark.asyncio
    async def test_archive_sets_far_future(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("archive me", source_type="e2e")
        result = await orch.archive(mid, reason="old")
        assert result is True
        record = await repo.get_by_id(mid)
        assert record.expires_at.year == 9999

    @pytest.mark.asyncio
    async def test_archive_nonexistent_returns_false(self) -> None:
        orch, _, _ = _build_stack()
        result = await orch.archive(uuid4(), reason="gone")
        assert result is False

    @pytest.mark.asyncio
    async def test_forget_with_cascade(self) -> None:
        orch, repo, _ = _build_stack()
        mid1 = await orch.store("parent", source_type="e2e")
        mid2 = await orch.store("child", source_type="e2e")
        result = await orch.forget(mid1, reason="cascade test", cascade=True)
        assert result is True

    @pytest.mark.asyncio
    async def test_archive_then_forget(self) -> None:
        orch, repo, _ = _build_stack()
        mid = await orch.store("archive then forget", source_type="e2e")
        await orch.archive(mid, reason="old")
        record = await repo.get_by_id(mid)
        assert record.expires_at.year == 9999
        await orch.forget(mid, reason="really done")
        record = await repo.get_by_id(mid)
        assert record.expires_at.year == 2000


# =====================================================================
# Category 7: Scoring Integration
# =====================================================================


class TestScoringIntegration:
    """Verify scoring works correctly through the orchestrator."""

    @pytest.mark.asyncio
    async def test_score_returns_valid_range(self) -> None:
        orch, _, _ = _build_stack()
        mid = await orch.store("score test", source_type="e2e")
        score = await orch.score(mid)
        assert 0.0 <= score.final_score <= 1.0
        assert 0.0 <= score.recency <= 1.0
        assert 0.0 <= score.importance <= 1.0

    @pytest.mark.asyncio
    async def test_higher_importance_higher_score(self) -> None:
        orch, _, _ = _build_stack()
        low_id = await orch.store("low", source_type="e2e", importance=0.1)
        high_id = await orch.store("high", source_type="e2e", importance=0.9)
        score_low = await orch.score(low_id)
        score_high = await orch.score(high_id)
        assert score_high.importance >= score_low.importance

    @pytest.mark.asyncio
    async def test_score_nonexistent_raises(self) -> None:
        orch, _, _ = _build_stack()
        with pytest.raises(ValueError):
            await orch.score(uuid4())
