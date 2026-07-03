"""JARVIS OS - Tests for Phase 19 M5.0 Retention DTOs.

Tests for the new Retention DTOs added in M5.0:
- PromotionAction
- ForgettingAction
- RetentionEvaluationResult

Frozen contract: Phase 19 spec §8.2 Retention Engine contracts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.memory.dto import (
    ForgettingAction,
    MemoryTier,
    PromotionAction,
    RetentionEvaluationResult,
)


class TestPromotionAction:
    """Tests for PromotionAction DTO."""

    def test_create_minimal(self) -> None:
        """A PromotionAction with only required fields must validate."""
        mem_id = uuid4()
        action = PromotionAction(
            memory_id=mem_id,
            from_tier=MemoryTier.WORKING,
            to_tier=MemoryTier.CONVERSATION,
            reason="L1 -> L2: access_count >= 3",
        )
        assert action.memory_id == mem_id
        assert action.from_tier == MemoryTier.WORKING
        assert action.to_tier == MemoryTier.CONVERSATION
        assert action.reason == "L1 -> L2: access_count >= 3"
        assert action.score is None
        assert action.access_count is None
        assert action.schema_version == "1.0"

    def test_create_with_score(self) -> None:
        """Score and access_count are optional but accepted."""
        mem_id = uuid4()
        action = PromotionAction(
            memory_id=mem_id,
            from_tier=MemoryTier.CONVERSATION,
            to_tier=MemoryTier.LONG_TERM,
            reason="L2 -> L3: score >= 0.7",
            score=0.85,
            access_count=42,
        )
        assert action.score == 0.85
        assert action.access_count == 42

    def test_score_must_be_in_range(self) -> None:
        """Score must be in [0.0, 1.0] per DTO contract."""
        with pytest.raises(ValidationError):
            PromotionAction(
                memory_id=uuid4(),
                from_tier=MemoryTier.WORKING,
                to_tier=MemoryTier.CONVERSATION,
                reason="test",
                score=1.5,  # out of range
            )

    def test_negative_access_count_rejected(self) -> None:
        """access_count must be >= 0."""
        with pytest.raises(ValidationError):
            PromotionAction(
                memory_id=uuid4(),
                from_tier=MemoryTier.WORKING,
                to_tier=MemoryTier.CONVERSATION,
                reason="test",
                access_count=-1,
            )

    def test_empty_reason_rejected(self) -> None:
        """Reason must be non-empty (min_length=1)."""
        with pytest.raises(ValidationError):
            PromotionAction(
                memory_id=uuid4(),
                from_tier=MemoryTier.WORKING,
                to_tier=MemoryTier.CONVERSATION,
                reason="",
            )

    def test_reason_max_length_enforced(self) -> None:
        """Reason max_length=200 enforced."""
        with pytest.raises(ValidationError):
            PromotionAction(
                memory_id=uuid4(),
                from_tier=MemoryTier.WORKING,
                to_tier=MemoryTier.CONVERSATION,
                reason="x" * 201,
            )

    def test_idempotency_via_uuid(self) -> None:
        """Same (memory_id, to_tier) re-emitted is a no-op (engine handles dedup)."""
        mem_id = uuid4()
        a1 = PromotionAction(
            memory_id=mem_id,
            from_tier=MemoryTier.WORKING,
            to_tier=MemoryTier.CONVERSATION,
            reason="first",
        )
        a2 = PromotionAction(
            memory_id=mem_id,
            from_tier=MemoryTier.WORKING,
            to_tier=MemoryTier.CONVERSATION,
            reason="second",
        )
        # DTO does not enforce dedup; that is the engine's job (per spec §8.2).
        # This test asserts the DTO is constructible for both calls.
        assert a1.memory_id == a2.memory_id
        assert a1.to_tier == a2.to_tier

    def test_created_at_default_is_utc(self) -> None:
        """created_at defaults to current UTC time."""
        before = datetime.now(timezone.utc)
        action = PromotionAction(
            memory_id=uuid4(),
            from_tier=MemoryTier.WORKING,
            to_tier=MemoryTier.CONVERSATION,
            reason="test",
        )
        after = datetime.now(timezone.utc)
        assert before <= action.created_at <= after

    def test_schema_version_locked(self) -> None:
        """Schema version is locked at 1.0 (immutability rule)."""
        with pytest.raises(ValidationError):
            PromotionAction(
                memory_id=uuid4(),
                from_tier=MemoryTier.WORKING,
                to_tier=MemoryTier.CONVERSATION,
                reason="test",
                schema_version="2.0",  # type: ignore[arg-type]
            )

    def test_serializable_round_trip(self) -> None:
        """DTO must round-trip through JSON without data loss."""
        mem_id = uuid4()
        action = PromotionAction(
            memory_id=mem_id,
            from_tier=MemoryTier.WORKING,
            to_tier=MemoryTier.CONVERSATION,
            reason="L1 -> L2: access_count >= 3",
            score=0.6,
            access_count=5,
        )
        json_str = action.model_dump_json()
        restored = PromotionAction.model_validate_json(json_str)
        assert restored == action


class TestForgettingAction:
    """Tests for ForgettingAction DTO."""

    @pytest.mark.parametrize(
        "reason",
        ["ttl", "decay", "manual", "cascade", "gdpr"],
    )
    def test_all_valid_reasons(self, reason: str) -> None:
        """All 5 spec-defined reasons must be accepted."""
        action = ForgettingAction(
            memory_id=uuid4(),
            from_tier=MemoryTier.CONVERSATION,
            reason=reason,  # type: ignore[arg-type]
        )
        assert action.reason == reason

    def test_invalid_reason_rejected(self) -> None:
        """Unknown reason values must be rejected (closed enum)."""
        with pytest.raises(ValidationError):
            ForgettingAction(
                memory_id=uuid4(),
                from_tier=MemoryTier.CONVERSATION,
                reason="not_a_valid_reason",  # type: ignore[arg-type]
            )

    def test_score_optional(self) -> None:
        """Score is optional (decay reason may not have a score)."""
        action = ForgettingAction(
            memory_id=uuid4(),
            from_tier=MemoryTier.LONG_TERM,
            reason="ttl",
        )
        assert action.score is None
        assert action.age_seconds is None

    def test_age_seconds_must_be_non_negative(self) -> None:
        """age_seconds must be >= 0."""
        with pytest.raises(ValidationError):
            ForgettingAction(
                memory_id=uuid4(),
                from_tier=MemoryTier.LONG_TERM,
                reason="ttl",
                age_seconds=-1,
            )

    def test_cascade_reason_for_graph_operations(self) -> None:
        """Cascade is the reason used by M6 KG operations (future use)."""
        action = ForgettingAction(
            memory_id=uuid4(),
            from_tier=MemoryTier.LONG_TERM,
            reason="cascade",
        )
        assert action.reason == "cascade"

    def test_gdpr_reason_for_erasure(self) -> None:
        """GDPR reason used for data subject erasure requests."""
        action = ForgettingAction(
            memory_id=uuid4(),
            from_tier=MemoryTier.LONG_TERM,
            reason="gdpr",
        )
        assert action.reason == "gdpr"

    def test_schema_version_locked(self) -> None:
        """Schema version locked at 1.0."""
        with pytest.raises(ValidationError):
            ForgettingAction(
                memory_id=uuid4(),
                from_tier=MemoryTier.LONG_TERM,
                reason="manual",
                schema_version="2.0",  # type: ignore[arg-type]
            )


class TestRetentionEvaluationResult:
    """Tests for RetentionEvaluationResult DTO."""

    def test_empty_result(self) -> None:
        """An empty result (no actions) must validate."""
        result = RetentionEvaluationResult()
        assert result.promotions == []
        assert result.forgetting == []
        assert result.total_promotions == 0
        assert result.total_forgetting == 0
        assert result.cycle_duration_ms == 0.0

    def test_record_updates_totals(self) -> None:
        """record() updates totals from action list lengths."""
        result = RetentionEvaluationResult(
            promotions=[
                PromotionAction(
                    memory_id=uuid4(),
                    from_tier=MemoryTier.WORKING,
                    to_tier=MemoryTier.CONVERSATION,
                    reason="test",
                ),
                PromotionAction(
                    memory_id=uuid4(),
                    from_tier=MemoryTier.CONVERSATION,
                    to_tier=MemoryTier.LONG_TERM,
                    reason="test",
                ),
            ],
            forgetting=[
                ForgettingAction(
                    memory_id=uuid4(),
                    from_tier=MemoryTier.CONVERSATION,
                    reason="ttl",
                ),
            ],
        )
        # record() not yet called, totals are stale
        assert result.total_promotions == 0
        assert result.total_forgetting == 0

        result.record()

        assert result.total_promotions == 2
        assert result.total_forgetting == 1

    def test_record_is_idempotent(self) -> None:
        """Calling record() multiple times is safe."""
        result = RetentionEvaluationResult(
            promotions=[
                PromotionAction(
                    memory_id=uuid4(),
                    from_tier=MemoryTier.WORKING,
                    to_tier=MemoryTier.CONVERSATION,
                    reason="test",
                )
            ],
        )
        result.record()
        first_total = result.total_promotions
        result.record()
        result.record()
        assert result.total_promotions == first_total == 1

    def test_cycle_duration_ms_must_be_non_negative(self) -> None:
        """cycle_duration_ms must be >= 0 (sanity check)."""
        with pytest.raises(ValidationError):
            RetentionEvaluationResult(cycle_duration_ms=-1.0)

    def test_serializable_round_trip(self) -> None:
        """Result must round-trip through JSON."""
        result = RetentionEvaluationResult(
            promotions=[
                PromotionAction(
                    memory_id=uuid4(),
                    from_tier=MemoryTier.WORKING,
                    to_tier=MemoryTier.CONVERSATION,
                    reason="test",
                )
            ],
            forgetting=[
                ForgettingAction(
                    memory_id=uuid4(),
                    from_tier=MemoryTier.LONG_TERM,
                    reason="manual",
                )
            ],
            cycle_duration_ms=12.5,
        )
        result.record()
        json_str = result.model_dump_json()
        restored = RetentionEvaluationResult.model_validate_json(json_str)
        assert restored.promotions == result.promotions
        assert restored.forgetting == result.forgetting
        assert restored.total_promotions == result.total_promotions
        assert restored.total_forgetting == result.total_forgetting
        assert restored.cycle_duration_ms == result.cycle_duration_ms

    def test_evaluated_at_default_is_utc(self) -> None:
        """evaluated_at defaults to current UTC time."""
        before = datetime.now(timezone.utc)
        result = RetentionEvaluationResult()
        after = datetime.now(timezone.utc)
        assert before <= result.evaluated_at <= after

    def test_promotion_only_result(self) -> None:
        """Result with only promotions (no forgetting) must work."""
        result = RetentionEvaluationResult(
            promotions=[
                PromotionAction(
                    memory_id=uuid4(),
                    from_tier=MemoryTier.WORKING,
                    to_tier=MemoryTier.CONVERSATION,
                    reason="test",
                )
            ]
        )
        result.record()
        assert result.total_promotions == 1
        assert result.total_forgetting == 0

    def test_forgetting_only_result(self) -> None:
        """Result with only forgetting (no promotions) must work."""
        result = RetentionEvaluationResult(
            forgetting=[
                ForgettingAction(
                    memory_id=uuid4(),
                    from_tier=MemoryTier.LONG_TERM,
                    reason="gdpr",
                )
            ]
        )
        result.record()
        assert result.total_promotions == 0
        assert result.total_forgetting == 1
