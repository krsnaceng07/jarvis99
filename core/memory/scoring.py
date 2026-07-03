"""JARVIS OS - Phase 19 Memory Scoring Engine.

Pure-function score calculation. No IO, no repository, no side effects.
Implements the frozen scoring formula from §3.1 of the spec.

PHASE: 19
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/81_PHASE_19_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from core.memory.dto import (
    MemoryRecord,
    MemoryScore,
    MemoryTier,
    MemoryTrustLevel,
)

# =====================================================================
# Scoring Config (§3.2 frozen weights)
# =====================================================================


@dataclass(frozen=True)
class ScoringWeights:
    """Frozen scoring weights from §3.2. Immutable."""

    w_recency: float = 0.25
    w_semantic: float = 0.20
    w_confidence: float = 0.20
    w_importance: float = 0.15
    w_frequency: float = 0.10
    w_trust: float = 0.05
    w_pin: float = 1.00
    lambda_decay: float = 0.05
    max_access_count: int = 1000


# =====================================================================
# Scoring Profile (future-proof, DEFAULT only for now)
# =====================================================================


class ScoringProfile:
    """Scoring profile for context-specific scoring.

    Currently only DEFAULT is supported.
    Future profiles: SEARCH, CHAT, PLANNING, REFLECTION.
    """

    DEFAULT = "default"


# =====================================================================
# Trust Level to Float Mapping (§3.3)
# =====================================================================


_TRUST_VALUES: Dict[MemoryTrustLevel, float] = {
    MemoryTrustLevel.SYSTEM: 1.0,
    MemoryTrustLevel.USER_EXPLICIT: 0.9,
    MemoryTrustLevel.USER_IMPLICIT: 0.7,
    MemoryTrustLevel.LEARNED: 0.5,
    MemoryTrustLevel.INFERRED: 0.3,
}


# =====================================================================
# Scoring Input (immutable)
# =====================================================================


@dataclass(frozen=True)
class ScoringInput:
    """Input for scoring a single memory. Immutable."""

    memory_id: UUID
    confidence: float
    importance: float
    trust_level: MemoryTrustLevel
    access_count: int
    last_accessed: datetime
    created_at: datetime
    is_pinned: bool = False
    semantic_similarity: float = 0.0
    tier: MemoryTier = MemoryTier.LONG_TERM


# =====================================================================
# Scoring Engine (pure functions)
# =====================================================================


class ScoringEngine:
    """Pure-function scoring engine. No IO, no side effects.

    Implements the frozen formula:
    FinalScore = w_recency * Recency + w_semantic * SemanticSimilarity +
                 w_confidence * Confidence + w_importance * Importance +
                 w_frequency * Frequency + w_trust * Trust + w_pin * UserPin
    """

    def __init__(self, weights: Optional[ScoringWeights] = None) -> None:
        self._weights = weights or ScoringWeights()

    @property
    def weights(self) -> ScoringWeights:
        return self._weights

    def _round(self, value: float) -> float:
        """Round to 6 decimal places for floating-point stability."""
        return round(value, 6)

    def _compute_recency(self, last_accessed: datetime, now: datetime) -> float:
        """Compute recency score: e^(-lambda * delta_hours)."""
        delta = now - last_accessed
        delta_hours = delta.total_seconds() / 3600.0
        return self._round(math.exp(-self._weights.lambda_decay * delta_hours))

    def _compute_frequency(self, access_count: int) -> float:
        """Compute frequency score: ln(1 + access_count) / ln(1 + max_access_count)."""
        if self._weights.max_access_count <= 0:
            return 0.0
        numerator = math.log(1 + access_count)
        denominator = math.log(1 + self._weights.max_access_count)
        if denominator == 0:
            return 0.0
        return self._round(min(1.0, numerator / denominator))

    def _compute_trust(self, trust_level: MemoryTrustLevel) -> float:
        """Compute trust score from trust level."""
        return _TRUST_VALUES.get(trust_level, 0.3)

    def _compute_user_pin(self, is_pinned: bool) -> float:
        """Compute user pin boost: 1.0 if pinned, 0.0 otherwise."""
        return 1.0 if is_pinned else 0.0

    def score(
        self,
        input_data: ScoringInput,
        now: Optional[datetime] = None,
    ) -> MemoryScore:
        """Calculate composite score for a single memory.

        Pure function: same input → same output, always.
        """
        now = now or datetime.now(timezone.utc)

        recency = self._compute_recency(input_data.last_accessed, now)
        semantic = self._round(input_data.semantic_similarity)
        confidence = self._round(input_data.confidence)
        importance = self._round(input_data.importance)
        frequency = self._compute_frequency(input_data.access_count)
        trust = self._compute_trust(input_data.trust_level)
        user_pin = self._compute_user_pin(input_data.is_pinned)

        final_score = self._round(
            self._weights.w_recency * recency
            + self._weights.w_semantic * semantic
            + self._weights.w_confidence * confidence
            + self._weights.w_importance * importance
            + self._weights.w_frequency * frequency
            + self._weights.w_trust * trust
            + self._weights.w_pin * user_pin
        )

        return MemoryScore(
            memory_id=input_data.memory_id,
            recency=recency,
            semantic_similarity=semantic,
            confidence=confidence,
            importance=importance,
            frequency=frequency,
            trust=trust,
            user_pin=user_pin,
            final_score=final_score,
            tier=input_data.tier,
            calculated_at=now,
        )

    def _tie_break_key(self, score: MemoryScore) -> tuple[float, float, float, str]:
        """Compute tie-break key for stable ordering.

        Order: Higher Trust → Higher Importance → More Recent → Older UUID.
        """
        return (
            -score.trust,
            -score.importance,
            -score.recency,
            str(score.memory_id),
        )

    def rank(
        self,
        inputs: List[ScoringInput],
        now: Optional[datetime] = None,
    ) -> List[MemoryScore]:
        """Score and rank multiple memories. Returns sorted list (highest first).

        Pure function: same inputs → same output, always.
        Stable sort with tie-break rules.
        """
        now = now or datetime.now(timezone.utc)
        scores = [self.score(inp, now) for inp in inputs]
        scores.sort(key=lambda s: (-s.final_score, self._tie_break_key(s)))
        return scores

    def rank_records(
        self,
        records: List[MemoryRecord],
        access_counts: Optional[Dict[UUID, int]] = None,
        semantic_similarities: Optional[Dict[UUID, float]] = None,
        pinned_ids: Optional[set[UUID]] = None,
        now: Optional[datetime] = None,
    ) -> List[MemoryScore]:
        """Score and rank MemoryRecord objects. Convenience method.

        Pure function: same inputs → same output, always.
        """
        access_counts = access_counts or {}
        semantic_similarities = semantic_similarities or {}
        pinned_ids = pinned_ids or set()

        inputs = []
        for record in records:
            inputs.append(
                ScoringInput(
                    memory_id=record.memory_id,
                    confidence=record.confidence,
                    importance=record.importance,
                    trust_level=record.trust_level,
                    access_count=access_counts.get(record.memory_id, 0),
                    last_accessed=record.updated_at,
                    created_at=record.created_at,
                    is_pinned=record.memory_id in pinned_ids,
                    semantic_similarity=semantic_similarities.get(
                        record.memory_id, 0.0
                    ),
                    tier=MemoryTier.LONG_TERM,
                )
            )

        return self.rank(inputs, now)
