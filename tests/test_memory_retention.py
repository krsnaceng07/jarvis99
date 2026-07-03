"""JARVIS OS - Phase 19 M5 Retention Engine Tests.

Tests for the Memory Retention Engine. Verifies:
- Promotion logic (WORKING -> CONVERSATION -> LONG_TERM)
- Expiry and eviction logic (L1 TTL, L2 TTL, Archive Expiry)
- Score decay / archiving criteria (L3 decay)
- Promotion throttling and idempotency
- Cascade delete returns CascadeDeleteAction (NO writes)
- Archive returns ArchiveAction (NO writes)
- RetentionBatch aggregation
- evaluate_all pipeline

Architecture invariant tested:
    RetentionEngine NEVER writes to repository.
    All outputs are DECISIONS only.

PHASE: 19
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID, uuid4

import pytest

from core.config import MemoryRetentionConfig
from core.memory.dto import (
    MemoryMetadata,
    MemoryProvenance,
    MemoryRecord,
    MemoryTier,
    MemoryTrustLevel,
    MemoryType,
    MemoryVisibility,
)
from core.memory.memory_repository import InMemoryRecordRepository
from core.memory.retention import (
    ArchiveAction,
    CascadeDeleteAction,
    ForgettingAction,
    PromotionAction,
    PromotionReason,
    RetentionBatch,
    RetentionEngine,
)
from core.memory.scoring import ScoringEngine

FIXED_NOW = datetime(2026, 6, 30, 12, 0, 0)


def _make_record(
    content: str = "lifecycle test",
    tier: MemoryTier = MemoryTier.WORKING,
    access_count: int = 1,
    hours_ago: float = 0.0,
    confidence: float = 1.0,
    importance: float = 0.5,
    last_promoted_str: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    owner_id: Optional[UUID] = None,
    workflow_id: Optional[UUID] = None,
    agent_id: Optional[UUID] = None,
    pinned: bool = False,
    trust_level: MemoryTrustLevel = MemoryTrustLevel.USER_EXPLICIT,
) -> MemoryRecord:
    updated = FIXED_NOW - timedelta(hours=hours_ago)
    created = FIXED_NOW - timedelta(hours=hours_ago + 1)
    extra: dict = {"tier": tier.value, "access_count": access_count}
    if last_promoted_str:
        extra["last_promoted"] = last_promoted_str
    if pinned:
        extra["pinned"] = True

    return MemoryRecord(
        memory_id=uuid4(),
        memory_type=MemoryType.FACT,
        owner_id=owner_id or uuid4(),
        visibility=MemoryVisibility.PUBLIC,
        trust_level=trust_level,
        confidence=confidence,
        importance=importance,
        created_at=created,
        updated_at=updated,
        expires_at=expires_at,
        provenance=MemoryProvenance(
            origin="test",
            created_by="test",
            workflow_id=workflow_id,
            agent_id=agent_id,
        ),
        metadata=MemoryMetadata(extra=extra),
        content=content,
        content_hash=f"hash_{uuid4().hex[:8]}",
    )


class TestRetentionPromotions:
    """Verify promotion decisions — no repository writes occur."""

    @pytest.mark.asyncio
    async def test_l1_to_l2_promotion(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        session_id = uuid4()
        record = _make_record(
            tier=MemoryTier.WORKING, access_count=3, workflow_id=session_id
        )
        await repo.save(record)

        actions = await engine.evaluate_promotions(session_id, FIXED_NOW)

        assert len(actions) == 1
        assert isinstance(actions[0], PromotionAction)
        assert actions[0].memory_id == record.memory_id
        assert actions[0].source_tier == MemoryTier.WORKING
        assert actions[0].target_tier == MemoryTier.CONVERSATION
        assert actions[0].promotion_reason == PromotionReason.ACCESS_COUNT

    @pytest.mark.asyncio
    async def test_l2_to_l3_promotion_high_score(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        session_id = uuid4()
        record = _make_record(
            tier=MemoryTier.CONVERSATION,
            access_count=2,
            confidence=1.0,
            importance=0.9,
            workflow_id=session_id,
            pinned=True,
            trust_level=MemoryTrustLevel.SYSTEM,
        )
        await repo.save(record)

        actions = await engine.evaluate_promotions(session_id, FIXED_NOW)

        assert len(actions) == 1
        assert actions[0].source_tier == MemoryTier.CONVERSATION
        assert actions[0].target_tier == MemoryTier.LONG_TERM
        assert actions[0].promotion_reason == PromotionReason.PINNED

    @pytest.mark.asyncio
    async def test_promotion_throttle(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        session_id = uuid4()
        # last_promoted was 10 seconds ago — within 60s throttle window
        last_promoted_str = (FIXED_NOW - timedelta(seconds=10)).isoformat()
        record = _make_record(
            tier=MemoryTier.WORKING,
            access_count=5,
            last_promoted_str=last_promoted_str,
            workflow_id=session_id,
        )
        await repo.save(record)

        actions = await engine.evaluate_promotions(session_id, FIXED_NOW)
        assert len(actions) == 0

    @pytest.mark.asyncio
    async def test_promotion_not_throttled_after_window(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        session_id = uuid4()
        # last_promoted was 90 seconds ago — outside 60s throttle window
        last_promoted_str = (FIXED_NOW - timedelta(seconds=90)).isoformat()
        record = _make_record(
            tier=MemoryTier.WORKING,
            access_count=5,
            last_promoted_str=last_promoted_str,
            workflow_id=session_id,
        )
        await repo.save(record)

        actions = await engine.evaluate_promotions(session_id, FIXED_NOW)
        assert len(actions) == 1

    @pytest.mark.asyncio
    async def test_no_promotion_insufficient_access_count(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        session_id = uuid4()
        # Only 2 accesses — below L1->L2 threshold of 3
        record = _make_record(
            tier=MemoryTier.WORKING, access_count=2, workflow_id=session_id
        )
        await repo.save(record)

        actions = await engine.evaluate_promotions(session_id, FIXED_NOW)
        assert len(actions) == 0


class TestRetentionForgetting:
    """Verify eviction/forgetting decisions — no repository writes occur."""

    @pytest.mark.asyncio
    async def test_l1_ttl_expiry(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        # 15 minutes old — past L1 10-minute TTL
        record = _make_record(tier=MemoryTier.WORKING, hours_ago=0.25)
        await repo.save(record)

        actions = await engine.evaluate_forgetting(FIXED_NOW)

        assert len(actions) == 1
        assert isinstance(actions[0], ForgettingAction)
        assert actions[0].memory_id == record.memory_id
        assert actions[0].action_type == "forget"
        assert "L1 TTL expiry" in actions[0].reason

    @pytest.mark.asyncio
    async def test_l2_ttl_expiry(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        # 26 hours old — past L2 24-hour TTL, low score → ineligible for promotion
        record = _make_record(
            tier=MemoryTier.CONVERSATION,
            hours_ago=26.0,
            confidence=0.1,
            importance=0.1,
        )
        await repo.save(record)

        actions = await engine.evaluate_forgetting(FIXED_NOW)

        assert len(actions) == 1
        assert actions[0].action_type == "forget"
        assert "L2 TTL expiry without promotion eligibility" in actions[0].reason

    @pytest.mark.asyncio
    async def test_l3_score_decay_archives(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        # L3 record with very low score — decays below 0.2 threshold
        record = _make_record(
            tier=MemoryTier.LONG_TERM,
            hours_ago=48.0,
            confidence=0.1,
            importance=0.1,
        )
        await repo.save(record)

        actions = await engine.evaluate_forgetting(FIXED_NOW)

        assert len(actions) == 1
        assert actions[0].action_type == "archive"
        assert "L3 score decay" in actions[0].reason

    @pytest.mark.asyncio
    async def test_archive_retention_expiry(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        # ARCHIVED record older than 30 days — eligible for hard deletion
        record = _make_record(
            tier=MemoryTier.ARCHIVED,
            hours_ago=35 * 24.0,
            expires_at=datetime(9999, 12, 31, 23, 59, 59),
        )
        await repo.save(record)

        actions = await engine.evaluate_forgetting(FIXED_NOW)

        assert len(actions) == 1
        assert actions[0].action_type == "forget"
        assert "Archive retention period exceeded" in actions[0].reason


class TestRetentionDecisionPurity:
    """Verify RetentionEngine produces DECISIONS only — zero repository writes."""

    def test_recommend_archive_returns_action_only(self) -> None:
        """recommend_archive() must return ArchiveAction without writing."""
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        chunk_id = uuid4()
        action = engine.recommend_archive(chunk_id, "manual audit")

        assert isinstance(action, ArchiveAction)
        assert action.memory_id == chunk_id
        assert action.reason == "manual audit"

    @pytest.mark.asyncio
    async def test_recommend_cascade_delete_returns_action_only(self) -> None:
        """recommend_cascade_delete() must list affected IDs without writing."""
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        source_id = uuid4()
        r1 = _make_record(workflow_id=source_id)
        r2 = _make_record(workflow_id=source_id)
        r3 = _make_record(workflow_id=uuid4())  # different source

        await repo.save(r1)
        await repo.save(r2)
        await repo.save(r3)

        action = await engine.recommend_cascade_delete(source_id, "workflow deleted")

        assert isinstance(action, CascadeDeleteAction)
        assert action.source_id == source_id
        assert set(action.target_memory_ids) == {r1.memory_id, r2.memory_id}
        # Verify r3 is NOT included
        assert r3.memory_id not in action.target_memory_ids

    @pytest.mark.asyncio
    async def test_no_writes_after_recommend_archive(self) -> None:
        """Repository state must be unchanged after recommend_archive."""
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        record = _make_record()
        await repo.save(record)

        # Request archive decision
        engine.recommend_archive(record.memory_id, "test audit")

        # Repository must be unmodified
        stored = await repo.get_by_id(record.memory_id)
        assert stored is not None
        assert stored.expires_at is None  # NOT mutated to 9999 sentinel

    @pytest.mark.asyncio
    async def test_no_writes_after_recommend_cascade_delete(self) -> None:
        """Repository state must be unchanged after recommend_cascade_delete."""
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        source_id = uuid4()
        r1 = _make_record(workflow_id=source_id)
        await repo.save(r1)

        await engine.recommend_cascade_delete(source_id, "test")

        # Repository must be unmodified
        stored = await repo.get_by_id(r1.memory_id)
        assert stored is not None
        assert stored.expires_at is None  # NOT soft-deleted


class TestRetentionBatch:
    """Verify RetentionBatch aggregation properties."""

    def test_batch_property_counts(self) -> None:
        chunk_id = uuid4()
        batch = RetentionBatch(
            evaluated_at=FIXED_NOW,
            promotions=[
                PromotionAction(
                    memory_id=chunk_id,
                    source_tier=MemoryTier.WORKING,
                    target_tier=MemoryTier.CONVERSATION,
                    reason="test",
                )
            ],
            forgettings=[
                ForgettingAction(
                    memory_id=chunk_id, action_type="forget", reason="test"
                ),
                ForgettingAction(
                    memory_id=chunk_id, action_type="archive", reason="test"
                ),
            ],
        )

        assert batch.promotion_count == 1
        assert batch.forget_count == 1
        assert batch.archive_count == 1
        assert batch.cascade_count == 0
        assert batch.total_actions == 3

    @pytest.mark.asyncio
    async def test_evaluate_all_pipeline(self) -> None:
        repo = InMemoryRecordRepository()
        engine = RetentionEngine(repo, ScoringEngine(), MemoryRetentionConfig())

        session_id = uuid4()
        # L1 promotion candidate
        promo = _make_record(
            tier=MemoryTier.WORKING, access_count=3, workflow_id=session_id
        )
        # L1 TTL expiry candidate
        expired = _make_record(tier=MemoryTier.WORKING, hours_ago=0.25)

        await repo.save(promo)
        await repo.save(expired)

        batch = await engine.evaluate_all(session_id=session_id, now=FIXED_NOW)

        assert isinstance(batch, RetentionBatch)
        assert batch.promotion_count >= 1
        assert batch.forget_count >= 1
        assert batch.total_actions >= 2
