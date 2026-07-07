"""JARVIS OS - Phase 19 Memory Retrieval Engine.

Implements the frozen retrieval pipeline from §6.1 of the spec.
Coordinates Repository reads, Permission filtering, Scoring, and Ranking.
No writes, no promotion, no retention, no reflection, no KG mutation.

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

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol
from uuid import UUID

from core.interfaces import EventBusInterface, InterAgentMessage
from core.memory.dto import (
    MemoryRecord,
    MemoryTier,
    MemoryType,
    MemoryVisibility,
    RecallMetadata,
    RetrievalRequest,
    RetrievalResponse,
)
from core.memory.memory_repository import IMemoryRecordRepository
from core.memory.scoring import ScoringEngine, ScoringInput

# =====================================================================
# Retrieval Reason Enum (Recommendation 2)
# =====================================================================


class RetrievalReason(str, Enum):
    """Reason explaining why a memory was retrieved. Frozen contract mapping."""

    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    PINNED = "pinned"
    IDENTITY = "identity"
    GRAPH = "graph"
    SESSION = "session"


# =====================================================================
# CandidateProvider Protocol (Recommendation 1)
# =====================================================================


class CandidateProvider(Protocol):
    """Protocol for candidate generation sources. Standardized immutable contract.

    Future implementations:
    - MetadataCandidateProvider (keyword search)
    - VectorCandidateProvider (cosine similarity)
    - HybridCandidateProvider (RRF fusion)
    - KGCandidateProvider (graph traversal)
    """

    @property
    def name(self) -> str:
        """Name of the candidate provider."""
        ...

    def supports(self, tier: MemoryTier) -> bool:
        """Check if this provider supports the given memory tier."""
        ...

    async def search(
        self,
        query: str,
        owner_id: Optional[UUID] = None,
        limit: int = 200,
    ) -> List[MemoryRecord]:
        """Search and generate candidates matching the query."""
        ...


# =====================================================================
# Token Estimation Utility (Recommendation 4)
# =====================================================================


def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string.

    Can be swapped/extended with a proper tokenizer wrapper in the future.
    """
    if not text:
        return 0
    # Baseline estimation: ~4 characters per token
    return max(1, len(text) // 4)


# =====================================================================
# Permission Filter
# =====================================================================


def filter_by_permission(
    records: List[MemoryRecord],
    owner_id: Optional[UUID] = None,
) -> List[MemoryRecord]:
    """Filter records by visibility and ownership.

    Permission-first rule: applied BEFORE candidate generation scoring.
    """
    result: List[MemoryRecord] = []
    for record in records:
        if owner_id is not None and record.owner_id == owner_id:
            result.append(record)
            continue

        if record.visibility in (
            MemoryVisibility.PUBLIC,
            MemoryVisibility.SYSTEM,
            MemoryVisibility.AGENT,
        ):
            result.append(record)
            continue

    return result


# =====================================================================
# Metadata Filter
# =====================================================================


def filter_by_metadata(
    records: List[MemoryRecord],
    memory_type: Optional[MemoryType] = None,
    visibility: Optional[MemoryVisibility] = None,
    min_confidence: float = 0.0,
    include_archived: bool = False,
) -> List[MemoryRecord]:
    """Filter records by metadata criteria."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result: List[MemoryRecord] = []

    for record in records:
        if not include_archived and record.expires_at is not None:
            if record.expires_at > now:
                continue

        if memory_type is not None and record.memory_type != memory_type:
            continue

        if visibility is not None and record.visibility != visibility:
            continue

        if record.confidence < min_confidence:
            continue

        result.append(record)

    return result


# =====================================================================
# Retrieval Metrics
# =====================================================================


@dataclass
class RetrievalMetrics:
    """Internal metrics for retrieval observability."""

    candidate_count: int = 0
    permission_filtered_count: int = 0
    metadata_filtered_count: int = 0
    scored_count: int = 0
    returned_count: int = 0
    retrieval_duration_ms: float = 0.0


# =====================================================================
# Retrieval Engine
# =====================================================================


class RetrievalEngine:
    """Implements the frozen retrieval pipeline from Section 6.1.

    Pipeline order (frozen):
    1. Request Validator
    2. Permission Filter
    3. Visibility Filter
    4. Tier Filter
    5. Candidate Generation
    6. Scoring (ScoringEngine.rank())
    7. Deduplication
    8. Top-K Selection
    9. Response
    """

    def __init__(
        self,
        repository: IMemoryRecordRepository,
        scoring_engine: ScoringEngine,
        candidate_provider: Optional[CandidateProvider] = None,
        event_bus: Optional[EventBusInterface] = None,
    ) -> None:
        self._repository = repository
        self._scoring_engine = scoring_engine
        self._candidate_provider = candidate_provider
        self._event_bus = event_bus

    async def _publish_event(self, topic: str, body: Dict[str, Any]) -> None:
        """Publish a telemetry event to the EventBus."""
        if self._event_bus is None:
            return
        try:
            msg = InterAgentMessage(
                sender="memory.retrieval_engine",
                receiver="system",
                action=topic,
                body=body,
            )
            await self._event_bus.publish(topic, msg)
        except Exception:
            # Telemetry publishing should never disrupt memory retrieval pipelines
            pass

    async def retrieve(
        self,
        request: RetrievalRequest,
        now: Optional[datetime] = None,
    ) -> RetrievalResponse:
        """Execute the frozen retrieval pipeline.

        Returns ranked memories with scores and metrics.
        """
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        metrics = RetrievalMetrics()
        start_time = datetime.now(timezone.utc)

        await self._publish_event(
            "memory.retrieve.started",
            {
                "query": request.query,
                "owner_id": str(request.owner_id) if request.owner_id else None,
            },
        )

        try:
            # 1. Request Validator
            max_chunks = request.max_chunks
            if max_chunks <= 0:
                max_chunks = 20
            elif max_chunks > 100:
                max_chunks = 100

            max_tokens = request.max_tokens
            if max_tokens <= 0:
                max_tokens = 2000

            # 2 & 3. Permission Filter & Visibility Filter Setup
            allowed_visibilities = [
                MemoryVisibility.PUBLIC,
                MemoryVisibility.SYSTEM,
                MemoryVisibility.AGENT,
            ]

            # 4. Tier Filter Setup
            allowed_tiers = request.tier_filter or [
                MemoryTier.IDENTITY,
                MemoryTier.WORKING,
                MemoryTier.CONVERSATION,
                MemoryTier.LONG_TERM,
            ]

            # 5. Candidate Generation
            if self._candidate_provider is not None:
                raw_candidates = await self._candidate_provider.search(
                    query=request.query,
                    owner_id=request.owner_id,
                    limit=max_chunks * 4,
                )
            else:
                raw_candidates = await self._repository.search_metadata(
                    query=request.query,
                    limit=max_chunks * 4,
                )
            metrics.candidate_count = len(raw_candidates)

            # Apply Permission Filter & Visibility Filter
            permitted = filter_by_permission(raw_candidates, request.owner_id)
            metrics.permission_filtered_count = len(raw_candidates) - len(permitted)

            # Apply Tier Filter & Metadata Filter (including expiration checks)
            metadata_filtered = [
                r for r in permitted if self._infer_tier(r) in allowed_tiers
            ]
            if not request.include_archived:
                metadata_filtered = [
                    r
                    for r in metadata_filtered
                    if r.expires_at is None or r.expires_at > now
                ]

            metrics.metadata_filtered_count = len(permitted) - len(metadata_filtered)

            # 6. Scoring (ScoringEngine.rank())
            scoring_inputs = []
            for record in metadata_filtered:
                sim = 0.0
                if (
                    self._candidate_provider is not None
                    and hasattr(self._candidate_provider, "get_similarity")
                ):
                    sim = self._candidate_provider.get_similarity(record.memory_id)
                scoring_inputs.append(
                    ScoringInput(
                        memory_id=record.memory_id,
                        confidence=record.confidence,
                        importance=record.importance,
                        trust_level=record.trust_level,
                        access_count=0,
                        last_accessed=record.updated_at,
                        created_at=record.created_at,
                        semantic_similarity=sim,
                        tier=self._infer_tier(record),
                    )
                )

            scores = self._scoring_engine.rank(scoring_inputs, now)
            metrics.scored_count = len(scores)

            # Build quick map of memory_id to record for assembling response
            record_map = {r.memory_id: r for r in metadata_filtered}

            # 7. Deduplication
            seen_hashes = set()
            seen_ids = set()
            deduped_scores = []
            for score in scores:
                record = record_map[score.memory_id]
                c_hash = record.content_hash
                m_id = record.memory_id
                if c_hash in seen_hashes or m_id in seen_ids:
                    continue
                seen_hashes.add(c_hash)
                seen_ids.add(m_id)
                deduped_scores.append(score)

            # 8. Top-K Selection (enforcing max_chunks and token budget limits)
            final_chunks = []
            final_scores = []
            total_tokens = 0

            for score in deduped_scores:
                if len(final_chunks) >= max_chunks:
                    break
                record = record_map[score.memory_id]
                token_count = (
                    record.metadata.token_count
                    if record.metadata and record.metadata.token_count > 0
                    else estimate_tokens(record.content)
                )
                if total_tokens + token_count > max_tokens:
                    continue

                # Determine retrieval reason (default to keyword)
                reason = RetrievalReason.KEYWORD.value
                if score.user_pin > 0:
                    reason = RetrievalReason.PINNED.value
                elif score.semantic_similarity > 0:
                    reason = RetrievalReason.SEMANTIC.value

                # Clone the record to keep the original storage model immutable in repository cache
                record_copy = record.model_copy(deep=True)
                record_copy.metadata.extra["retrieval_reason"] = reason

                final_chunks.append(record_copy)
                final_scores.append(score)
                total_tokens += token_count

            metrics.returned_count = len(final_chunks)

            # Calculate and record granular filter statistics
            deduplicated_count = len(scores) - len(deduped_scores)
            filtered_visibility = len(permitted) - len(
                [
                    r
                    for r in permitted
                    if r.visibility in allowed_visibilities
                    or r.owner_id == request.owner_id
                ]
            )

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            metrics.retrieval_duration_ms = round(elapsed, 2)

            response = RetrievalResponse(
                chunks=final_chunks,
                scores=final_scores,
                graph_node_ids=[],
                total_tokens=total_tokens,
                metadata=RecallMetadata(
                    query_time_ms=metrics.retrieval_duration_ms,
                    chunks_searched=metrics.candidate_count,
                    tiers_hit=list(set(self._infer_tier(r) for r in final_chunks)),
                    budget_used=metrics.returned_count,
                    budget_remaining=max_chunks - metrics.returned_count,
                ),
            )

            await self._publish_event(
                "memory.retrieve.completed",
                {
                    "query": request.query,
                    "candidate_count": metrics.candidate_count,
                    "filtered_permission": metrics.permission_filtered_count,
                    "filtered_visibility": filtered_visibility,
                    "filtered_tier": metrics.metadata_filtered_count,
                    "returned_count": metrics.returned_count,
                    "deduplicated_count": deduplicated_count,
                    "latency_ms": metrics.retrieval_duration_ms,
                },
            )

            return response

        except Exception as e:
            await self._publish_event(
                "memory.retrieve.failed",
                {"query": request.query, "error": str(e)},
            )
            raise

    def _infer_tier(self, record: MemoryRecord) -> MemoryTier:
        """Infer memory tier from record properties."""
        if record.expires_at is not None:
            if record.expires_at.year >= 9999:
                return MemoryTier.ARCHIVED
        return MemoryTier.LONG_TERM
