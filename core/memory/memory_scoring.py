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

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from core.memory.dto import MemoryRecord, MemoryScore, MemoryTier
from core.memory.scoring import ScoringEngine, ScoringInput, ScoringWeights


def to_naive_utc(dt: datetime) -> datetime:
    """Ensure datetime is offset-naive UTC to align with database records."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class MemoryScoring:
    """Intelligent scoring coordinator for memory retrieval and prioritization.

    Calculates composite ranking scores based on:
      FinalScore = w_recency * Recency + w_semantic * SemanticSimilarity +
                   w_confidence * Confidence + w_importance * Importance +
                   w_frequency * Frequency + w_trust * Trust + w_pin * UserPin
    """

    def __init__(
        self,
        weights: Optional[ScoringWeights] = None,
    ) -> None:
        self.engine = ScoringEngine(weights)

    def calculate_score(
        self,
        record: MemoryRecord,
        access_count: int = 0,
        semantic_similarity: float = 0.0,
        is_pinned: bool = False,
        now: Optional[datetime] = None,
    ) -> MemoryScore:
        """Calculate the composite score for a single memory record."""
        now_naive = (
            to_naive_utc(now)
            if now
            else datetime.now(timezone.utc).replace(tzinfo=None)
        )
        inp = ScoringInput(
            memory_id=record.memory_id,
            confidence=record.confidence,
            importance=record.importance,
            trust_level=record.trust_level,
            access_count=access_count,
            last_accessed=to_naive_utc(record.updated_at),
            created_at=to_naive_utc(record.created_at),
            is_pinned=is_pinned,
            semantic_similarity=semantic_similarity,
            tier=record.metadata.extra.get("tier", MemoryTier.LONG_TERM)
            if record.metadata
            else MemoryTier.LONG_TERM,
        )
        return self.engine.score(inp, now_naive)

    def rank_records(
        self,
        records: List[MemoryRecord],
        access_counts: Optional[Dict[UUID, int]] = None,
        semantic_similarities: Optional[Dict[UUID, float]] = None,
        pinned_ids: Optional[set[UUID]] = None,
        now: Optional[datetime] = None,
    ) -> List[MemoryScore]:
        """Rank a batch of MemoryRecords and return their calculated scores sorted descending."""
        now_naive = (
            to_naive_utc(now)
            if now
            else datetime.now(timezone.utc).replace(tzinfo=None)
        )
        # Normalize records' datetimes in-place or before ranking to avoid downstream naive/aware mismatches
        for record in records:
            record.created_at = to_naive_utc(record.created_at)
            record.updated_at = to_naive_utc(record.updated_at)
            if record.expires_at is not None:
                record.expires_at = to_naive_utc(record.expires_at)

        return self.engine.rank_records(
            records=records,
            access_counts=access_counts,
            semantic_similarities=semantic_similarities,
            pinned_ids=pinned_ids,
            now=now_naive,
        )
