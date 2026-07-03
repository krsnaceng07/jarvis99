"""JARVIS OS - Phase 19 M3 Scoring Engine Tests.

Tests for the Memory Scoring Engine. Verifies:
- Deterministic scoring (same input → same output)
- Frozen formula compliance
- Tie-break rules
- Ranking stability
- No IO, no side effects

PHASE: 19
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from core.memory.dto import (
    MemoryProvenance,
    MemoryRecord,
    MemoryTrustLevel,
    MemoryType,
    MemoryVisibility,
)
from core.memory.scoring import (
    ScoringEngine,
    ScoringInput,
    ScoringWeights,
)

# =====================================================================
# Helpers
# =====================================================================

FIXED_NOW = datetime(2026, 6, 30, 12, 0, 0)


def _make_input(
    confidence: float = 0.9,
    importance: float = 0.5,
    trust_level: MemoryTrustLevel = MemoryTrustLevel.USER_IMPLICIT,
    access_count: int = 0,
    hours_ago: float = 0.0,
    is_pinned: bool = False,
    semantic_similarity: float = 0.0,
) -> ScoringInput:
    last_accessed = FIXED_NOW - timedelta(hours=hours_ago)
    created = FIXED_NOW - timedelta(hours=hours_ago + 1)
    return ScoringInput(
        memory_id=uuid4(),
        confidence=confidence,
        importance=importance,
        trust_level=trust_level,
        access_count=access_count,
        last_accessed=last_accessed,
        created_at=created,
        is_pinned=is_pinned,
        semantic_similarity=semantic_similarity,
    )


def _make_record(
    confidence: float = 0.9,
    importance: float = 0.5,
    trust_level: MemoryTrustLevel = MemoryTrustLevel.USER_IMPLICIT,
    hours_ago: float = 0.0,
) -> MemoryRecord:
    updated = FIXED_NOW - timedelta(hours=hours_ago)
    created = FIXED_NOW - timedelta(hours=hours_ago + 1)
    return MemoryRecord(
        memory_type=MemoryType.FACT,
        owner_id=uuid4(),
        visibility=MemoryVisibility.PRIVATE,
        trust_level=trust_level,
        confidence=confidence,
        importance=importance,
        created_at=created,
        updated_at=updated,
        provenance=MemoryProvenance(origin="test", created_by="test"),
        content="test",
        content_hash="hash",
    )


# =====================================================================
# Weights Tests
# =====================================================================


class TestScoringWeights:
    """Verify default weights match §3.2."""

    def test_default_weights(self) -> None:
        w = ScoringWeights()
        assert w.w_recency == 0.25
        assert w.w_semantic == 0.20
        assert w.w_confidence == 0.20
        assert w.w_importance == 0.15
        assert w.w_frequency == 0.10
        assert w.w_trust == 0.05
        assert w.w_pin == 1.00
        assert w.lambda_decay == 0.05

    def test_weights_immutable(self) -> None:
        w = ScoringWeights()
        with pytest.raises(AttributeError):
            w.w_recency = 0.5  # type: ignore[misc]


# =====================================================================
# Determinism Tests
# =====================================================================


class TestDeterminism:
    """Verify scoring is deterministic."""

    def test_same_input_same_output(self) -> None:
        engine = ScoringEngine()
        inp = _make_input()

        score1 = engine.score(inp, now=FIXED_NOW)
        score2 = engine.score(inp, now=FIXED_NOW)

        assert score1.final_score == score2.final_score
        assert score1.recency == score2.recency
        assert score1.frequency == score2.frequency

    def test_different_time_different_score(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(hours_ago=1.0)

        score1 = engine.score(inp, now=FIXED_NOW)
        score2 = engine.score(inp, now=FIXED_NOW + timedelta(hours=1))

        assert score1.final_score != score2.final_score

    def test_rank_deterministic(self) -> None:
        engine = ScoringEngine()
        inputs = [_make_input(access_count=i) for i in range(5)]

        rank1 = engine.rank(inputs, now=FIXED_NOW)
        rank2 = engine.rank(inputs, now=FIXED_NOW)

        assert [s.memory_id for s in rank1] == [s.memory_id for s in rank2]


# =====================================================================
# Recency Tests
# =====================================================================


class TestRecency:
    """Verify recency score computation."""

    def test_just_accessed(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(hours_ago=0.0)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.recency == 1.0

    def test_14_hours_ago(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(hours_ago=14.0)
        score = engine.score(inp, now=FIXED_NOW)
        assert 0.45 < score.recency < 0.55

    def test_48_hours_ago(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(hours_ago=48.0)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.recency < 0.1


# =====================================================================
# Frequency Tests
# =====================================================================


class TestFrequency:
    """Verify frequency score computation."""

    def test_zero_accesses(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(access_count=0)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.frequency == 0.0

    def test_one_access(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(access_count=1)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.frequency > 0.0

    def test_many_accesses(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(access_count=100)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.frequency > 0.5


# =====================================================================
# Trust Tests
# =====================================================================


class TestTrust:
    """Verify trust score mapping."""

    def test_system_trust(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(trust_level=MemoryTrustLevel.SYSTEM)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.trust == 1.0

    def test_user_explicit_trust(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(trust_level=MemoryTrustLevel.USER_EXPLICIT)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.trust == 0.9

    def test_user_implicit_trust(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(trust_level=MemoryTrustLevel.USER_IMPLICIT)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.trust == 0.7

    def test_learned_trust(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(trust_level=MemoryTrustLevel.LEARNED)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.trust == 0.5

    def test_inferred_trust(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(trust_level=MemoryTrustLevel.INFERRED)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.trust == 0.3


# =====================================================================
# UserPin Tests
# =====================================================================


class TestUserPin:
    """Verify user pin boost."""

    def test_pinned(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(is_pinned=True)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.user_pin == 1.0

    def test_not_pinned(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(is_pinned=False)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.user_pin == 0.0


# =====================================================================
# Final Score Tests
# =====================================================================


class TestFinalScore:
    """Verify final score computation."""

    def test_all_zeros(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(
            confidence=0.0,
            importance=0.0,
            trust_level=MemoryTrustLevel.INFERRED,
            access_count=0,
            hours_ago=999,
            is_pinned=False,
            semantic_similarity=0.0,
        )
        score = engine.score(inp, now=FIXED_NOW)
        assert score.final_score >= 0.0
        assert score.final_score <= 1.0

    def test_all_ones(self) -> None:
        engine = ScoringEngine()
        inp = _make_input(
            confidence=1.0,
            importance=1.0,
            trust_level=MemoryTrustLevel.SYSTEM,
            access_count=1000,
            hours_ago=0.0,
            is_pinned=True,
            semantic_similarity=1.0,
        )
        score = engine.score(inp, now=FIXED_NOW)
        assert score.final_score > 1.0

    def test_score_rounded_to_6_decimals(self) -> None:
        engine = ScoringEngine()
        inp = _make_input()
        score = engine.score(inp, now=FIXED_NOW)
        assert score.final_score == round(score.final_score, 6)


# =====================================================================
# Ranking Tests
# =====================================================================


class TestRanking:
    """Verify ranking behavior."""

    def test_rank_descending(self) -> None:
        engine = ScoringEngine()
        inputs = [
            _make_input(confidence=0.3),
            _make_input(confidence=0.9),
            _make_input(confidence=0.6),
        ]
        scores = engine.rank(inputs, now=FIXED_NOW)
        for i in range(len(scores) - 1):
            assert scores[i].final_score >= scores[i + 1].final_score

    def test_rank_by_recency(self) -> None:
        engine = ScoringEngine()
        inputs = [
            _make_input(hours_ago=48),
            _make_input(hours_ago=1),
            _make_input(hours_ago=24),
        ]
        scores = engine.rank(inputs, now=FIXED_NOW)
        assert scores[0].recency > scores[1].recency > scores[2].recency

    def test_rank_by_trust(self) -> None:
        engine = ScoringEngine()
        inputs = [
            _make_input(trust_level=MemoryTrustLevel.INFERRED),
            _make_input(trust_level=MemoryTrustLevel.SYSTEM),
            _make_input(trust_level=MemoryTrustLevel.LEARNED),
        ]
        scores = engine.rank(inputs, now=FIXED_NOW)
        assert scores[0].trust > scores[1].trust > scores[2].trust

    def test_rank_empty(self) -> None:
        engine = ScoringEngine()
        scores = engine.rank([], now=FIXED_NOW)
        assert scores == []


# =====================================================================
# Tie-Break Tests
# =====================================================================


class TestTieBreak:
    """Verify tie-break rules: Trust → Importance → Recency → UUID."""

    def test_tie_break_trust(self) -> None:
        engine = ScoringEngine()
        inp1 = _make_input(trust_level=MemoryTrustLevel.SYSTEM)
        inp2 = _make_input(trust_level=MemoryTrustLevel.INFERRED)

        scores = engine.rank([inp1, inp2], now=FIXED_NOW)
        assert scores[0].trust > scores[1].trust

    def test_tie_break_importance(self) -> None:
        engine = ScoringEngine()
        inp1 = _make_input(importance=0.9)
        inp2 = _make_input(importance=0.1)

        scores = engine.rank([inp1, inp2], now=FIXED_NOW)
        assert scores[0].importance > scores[1].importance

    def test_tie_break_recency(self) -> None:
        engine = ScoringEngine()
        inp1 = _make_input(hours_ago=1)
        inp2 = _make_input(hours_ago=48)

        scores = engine.rank([inp1, inp2], now=FIXED_NOW)
        assert scores[0].recency > scores[1].recency

    def test_stable_sort(self) -> None:
        engine = ScoringEngine()
        inputs = [_make_input(confidence=0.5) for _ in range(10)]

        rank1 = engine.rank(inputs, now=FIXED_NOW)
        rank2 = engine.rank(inputs, now=FIXED_NOW)

        assert [s.memory_id for s in rank1] == [s.memory_id for s in rank2]


# =====================================================================
# rank_records Tests
# =====================================================================


class TestRankRecords:
    """Verify rank_records convenience method."""

    def test_rank_records(self) -> None:
        engine = ScoringEngine()
        records = [_make_record(confidence=c) for c in [0.3, 0.9, 0.6]]

        scores = engine.rank_records(records, now=FIXED_NOW)
        assert len(scores) == 3
        for i in range(len(scores) - 1):
            assert scores[i].final_score >= scores[i + 1].final_score

    def test_rank_records_with_access_counts(self) -> None:
        engine = ScoringEngine()
        r1 = _make_record()
        r2 = _make_record()
        access_counts = {r1.memory_id: 100, r2.memory_id: 0}

        scores = engine.rank_records(
            [r1, r2], access_counts=access_counts, now=FIXED_NOW
        )
        assert scores[0].frequency > scores[1].frequency

    def test_rank_records_with_pinned(self) -> None:
        engine = ScoringEngine()
        r1 = _make_record()
        r2 = _make_record()
        pinned = {r1.memory_id}

        scores = engine.rank_records([r1, r2], pinned_ids=pinned, now=FIXED_NOW)
        assert scores[0].user_pin == 1.0
        assert scores[1].user_pin == 0.0


# =====================================================================
# Custom Weights Tests
# =====================================================================


class TestCustomWeights:
    """Verify custom weights affect scoring."""

    def test_different_weights_different_scores(self) -> None:
        engine1 = ScoringEngine(ScoringWeights(w_recency=0.25))
        engine2 = ScoringEngine(ScoringWeights(w_recency=0.75))

        inp = _make_input(hours_ago=1.0)
        score1 = engine1.score(inp, now=FIXED_NOW)
        score2 = engine2.score(inp, now=FIXED_NOW)

        assert score1.final_score != score2.final_score

    def test_recency_heavy_weights(self) -> None:
        engine = ScoringEngine(ScoringWeights(w_recency=1.0, w_pin=0.0))
        inp = _make_input(hours_ago=0.0)
        score = engine.score(inp, now=FIXED_NOW)
        assert score.final_score >= score.recency
