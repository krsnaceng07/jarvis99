"""JARVIS OS - Phase 19 Memory Orchestrator (M7).

Sole entry point for all memory operations. Coordinates the repository,
scoring, retention, retrieval, and intelligence subsystems and publishes
the frozen memory event topics (spec §2.4).

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

Architecture boundary (spec §8.3 invariants):
    - Sole entry point — routes and CLI never call repos directly.
    - All operations emit appropriate events.
    - All operations are idempotent where possible.
    - Score is calculated on every store and recall.
    - Decision engines (RetentionEngine) propose; this orchestrator disposes.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from core.interfaces import EventBusInterface, InterAgentMessage
from core.memory.dto import (
    ExecutionOutcome,
    MemoryMetadata,
    MemoryProvenance,
    MemoryRecord,
    MemoryScore,
    MemoryTier,
    MemoryTrustLevel,
    MemoryType,
    MemoryVisibility,
    ReflectionRequest,
    RetrievalRequest,
    RetrievalResponse,
)
from core.memory.intelligence import MemoryIntelligenceService
from core.memory.memory_repository import IMemoryRecordRepository
from core.memory.retention import RetentionBatch, RetentionEngine
from core.memory.retrieval_engine import RetrievalEngine
from core.memory.scoring import ScoringEngine, ScoringInput
from core.memory.service import MemoryService
from core.memory.validator import validate_tier_transition

# Deterministic owner for records stored without an explicit owner.
SYSTEM_OWNER_ID = UUID("00000000-0000-0000-0000-000000000000")


class MemoryOrchestrator:
    """Entry point for all memory operations (spec §8.3, plan M7).

    Coordinates scoring, retention, retrieval, and persistence. Routes and
    CLI adapters must call this class and never touch repositories directly.
    """

    def __init__(
        self,
        memory_service: Optional[MemoryService],
        scoring_engine: ScoringEngine,
        retention_engine: RetentionEngine,
        retrieval_engine: RetrievalEngine,
        intelligence_service: Optional[MemoryIntelligenceService],
        memory_repo: IMemoryRecordRepository,
        event_bus: Optional[EventBusInterface] = None,
        vector_index: Optional[Any] = None,
    ) -> None:
        self.memory_service = memory_service
        self.scoring_engine = scoring_engine
        self.retention_engine = retention_engine
        self.retrieval_engine = retrieval_engine
        self.intelligence_service = intelligence_service
        self.memory_repo = memory_repo
        self.event_bus = event_bus
        self.vector_index = vector_index

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _hash(text: str) -> str:
        """SHA-256 content hash for exact deduplication."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def _publish_event(self, topic: str, body: Dict[str, Any]) -> None:
        """Publish a telemetry event to the EventBus (never disrupts flow)."""
        if self.event_bus is None:
            return
        try:
            msg = InterAgentMessage(
                sender="memory.orchestrator",
                receiver="system",
                action=topic,
                body=body,
            )
            await self.event_bus.publish(topic, msg)
        except Exception:
            # Telemetry must never disrupt memory operations
            pass

    @staticmethod
    def _infer_tier(record: MemoryRecord) -> MemoryTier:
        """Infer memory tier from record metadata (mirrors RetentionEngine)."""
        if record.metadata and record.metadata.extra:
            tier_str = record.metadata.extra.get("tier")
            if tier_str:
                try:
                    return MemoryTier(tier_str)
                except ValueError:
                    pass
        if record.expires_at is not None and record.expires_at.year >= 9999:
            return MemoryTier.ARCHIVED
        return MemoryTier.LONG_TERM

    def _score_record(
        self,
        record: MemoryRecord,
        now: Optional[datetime] = None,
    ) -> MemoryScore:
        """Compute the composite score for a record (spec §3.1)."""
        extra = record.metadata.extra if record.metadata else {}
        scoring_input = ScoringInput(
            memory_id=record.memory_id,
            confidence=record.confidence,
            importance=record.importance,
            trust_level=record.trust_level,
            access_count=int(extra.get("access_count", 0)),
            last_accessed=record.updated_at,
            created_at=record.created_at,
            is_pinned=bool(extra.get("is_pinned", extra.get("pinned", False))),
            semantic_similarity=0.0,
            tier=self._infer_tier(record),
        )
        return self.scoring_engine.score(scoring_input, now=now)

    # ------------------------------------------------------------------
    # Store (plan M7: store(...) -> UUID)
    # ------------------------------------------------------------------

    async def store(
        self,
        content: str,
        source_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
        confidence: float = 1.0,
        session_id: Optional[UUID] = None,
    ) -> UUID:
        """Store a new memory with scoring and tier assignment.

        Idempotent: storing identical content returns the existing record's
        id and bumps its access count instead of duplicating it.
        """
        meta: Dict[str, Any] = dict(metadata or {})
        content_hash = self._hash(content)

        existing = await self.memory_repo.get_by_hash(content_hash)
        if existing is not None:
            dedup_extra = dict(existing.metadata.extra) if existing.metadata else {}
            dedup_extra["access_count"] = int(dedup_extra.get("access_count", 0)) + 1
            dedup_meta = existing.metadata.model_dump() if existing.metadata else {}
            dedup_meta["extra"] = dedup_extra
            await self.memory_repo.update(
                existing.memory_id,
                existing.version,
                {"metadata": dedup_meta},
            )
            return existing.memory_id

        owner_raw = meta.pop("owner_id", None)
        owner_id = UUID(str(owner_raw)) if owner_raw is not None else SYSTEM_OWNER_ID

        memory_type_raw = meta.pop("memory_type", MemoryType.FACT.value)
        visibility_raw = meta.pop("visibility", MemoryVisibility.PRIVATE.value)
        trust_raw = meta.pop("trust_level", MemoryTrustLevel.USER_IMPLICIT.value)

        extra: Dict[str, Any] = dict(meta)
        extra.setdefault("tier", MemoryTier.WORKING.value)
        extra.setdefault("access_count", 0)
        if session_id is not None:
            extra.setdefault("session_id", str(session_id))

        record = MemoryRecord(
            memory_type=MemoryType(memory_type_raw),
            owner_id=owner_id,
            visibility=MemoryVisibility(visibility_raw),
            trust_level=MemoryTrustLevel(trust_raw),
            confidence=confidence,
            importance=importance,
            provenance=MemoryProvenance(
                origin=source_type,
                created_by="memory.orchestrator",
            ),
            content=content,
            content_hash=content_hash,
            metadata=MemoryMetadata(importance=importance, extra=extra),
        )
        saved = await self.memory_repo.save(record)

        score = self._score_record(saved)

        if self.vector_index is not None:
            try:
                await self.vector_index.index_memory(
                    saved.memory_id, content,
                    metadata={"source_type": source_type, "importance": importance},
                )
            except Exception as ve:
                logger.debug("Vector indexing skipped for %s: %s", saved.memory_id, ve)

        await self._publish_event(
            "memory.created",
            {
                "memory_id": str(saved.memory_id),
                "owner_id": str(saved.owner_id),
                "tier": self._infer_tier(saved).value,
                "memory_type": saved.memory_type.value,
                "score": score.final_score,
            },
        )
        return saved.memory_id

    # ------------------------------------------------------------------
    # Recall (plan M7: recall(request, session_id) -> RetrievalResponse)
    # ------------------------------------------------------------------

    async def recall(
        self,
        request: RetrievalRequest,
        session_id: Optional[UUID] = None,
    ) -> RetrievalResponse:
        """Retrieve memories with scoring and ranking (spec §6.1 pipeline)."""
        if session_id is not None and request.session_id is None:
            request = request.model_copy(update={"session_id": session_id})

        response = await self.retrieval_engine.retrieve(request)

        for chunk in response.chunks:
            extra = chunk.metadata.extra if chunk.metadata else {}
            await self._publish_event(
                "memory.retrieved",
                {
                    "memory_id": str(chunk.memory_id),
                    "tier": self._infer_tier(chunk).value,
                    "access_count": int(extra.get("access_count", 0)),
                    "query": request.query,
                },
            )
        return response

    # ------------------------------------------------------------------
    # Reflect (plan M7: reflect(request) -> bool)
    # ------------------------------------------------------------------

    async def reflect(self, request: ReflectionRequest) -> bool:
        """Apply reflection to update memory confidence (spec §7.2 rules)."""
        record = await self.memory_repo.get_by_id(request.memory_id)
        if record is None:
            return False

        delta = abs(request.confidence_delta)
        fields: Dict[str, object] = {}

        if request.outcome == ExecutionOutcome.SUCCESS:
            fields["confidence"] = min(1.0, record.confidence + delta)
        elif request.outcome == ExecutionOutcome.FAILURE:
            fields["confidence"] = max(0.0, record.confidence - delta)
        elif request.outcome == ExecutionOutcome.PARTIAL:
            adjusted = record.confidence + (request.confidence_delta * 0.5)
            fields["confidence"] = min(1.0, max(0.0, adjusted))
        else:  # TIMEOUT: decrease importance, memory remains relevant
            fields["importance"] = max(0.0, record.importance - (delta * 0.5))

        updated = await self.memory_repo.update(
            record.memory_id, record.version, fields
        )
        if updated is None:
            return False

        await self._publish_event(
            "memory.reflected",
            {
                "memory_id": str(record.memory_id),
                "outcome": request.outcome.value,
                "confidence_delta": request.confidence_delta,
            },
        )
        return True

    # ------------------------------------------------------------------
    # Forget (plan M7: forget(chunk_id, reason, cascade) -> bool)
    # ------------------------------------------------------------------

    async def forget(
        self,
        chunk_id: UUID,
        reason: str,
        cascade: bool = False,
    ) -> bool:
        """Forget a memory (soft delete + memory.deleted event)."""
        record = await self.memory_repo.get_by_id(chunk_id)
        if record is None:
            return False

        tier = self._infer_tier(record)

        if cascade:
            action = await self.retention_engine.recommend_cascade_delete(
                chunk_id, reason
            )
            for target_id in action.target_memory_ids:
                if target_id == chunk_id:
                    continue
                if await self.memory_repo.delete(target_id):
                    await self._publish_event(
                        "memory.deleted",
                        {
                            "memory_id": str(target_id),
                            "tier": tier.value,
                            "forget_reason": "cascade",
                        },
                    )

        deleted = await self.memory_repo.delete(chunk_id)
        if not deleted:
            return False

        if self.vector_index is not None:
            try:
                await self.vector_index.remove_memory(chunk_id)
            except Exception:
                pass

        await self._publish_event(
            "memory.deleted",
            {
                "memory_id": str(chunk_id),
                "tier": tier.value,
                "forget_reason": reason,
            },
        )
        return True

    # ------------------------------------------------------------------
    # Archive (plan M7: archive(chunk_id, reason) -> bool)
    # ------------------------------------------------------------------

    async def archive(self, chunk_id: UUID, reason: str) -> bool:
        """Archive a memory (logical flag + memory.archived event)."""
        record = await self.memory_repo.get_by_id(chunk_id)
        if record is None:
            return False

        tier = self._infer_tier(record)
        archived = await self.memory_repo.archive(chunk_id)
        if not archived:
            return False

        await self._publish_event(
            "memory.archived",
            {
                "memory_id": str(chunk_id),
                "tier": tier.value,
                "archive_reason": reason,
            },
        )
        return True

    # ------------------------------------------------------------------
    # Promote (plan M7: promote(chunk_id, target_tier) -> bool)
    # ------------------------------------------------------------------

    async def promote(self, chunk_id: UUID, target_tier: MemoryTier) -> bool:
        """Manually promote a memory to a higher tier (spec §4 policy)."""
        record = await self.memory_repo.get_by_id(chunk_id)
        if record is None:
            return False

        current_tier = self._infer_tier(record)
        if current_tier == target_tier:
            return True  # Idempotent no-op

        result = validate_tier_transition(current_tier, target_tier)
        if not result.valid:
            return False

        new_meta = record.metadata.model_dump() if record.metadata else {}
        extra = dict(new_meta.get("extra", {}))
        extra["tier"] = target_tier.value
        new_meta["extra"] = extra

        updated = await self.memory_repo.update(
            record.memory_id, record.version, {"metadata": new_meta}
        )
        if updated is None:
            return False

        score = self._score_record(updated)
        await self._publish_event(
            "memory.promoted",
            {
                "memory_id": str(chunk_id),
                "old_tier": current_tier.value,
                "new_tier": target_tier.value,
                "score": score.final_score,
            },
        )
        return True

    # ------------------------------------------------------------------
    # Score (plan M7: score(chunk_id) -> MemoryScore)
    # ------------------------------------------------------------------

    async def score(self, chunk_id: UUID) -> MemoryScore:
        """Calculate and return the score for a memory (spec §3.1)."""
        record = await self.memory_repo.get_by_id(chunk_id)
        if record is None:
            raise ValueError(f"Memory {chunk_id} not found")
        return self._score_record(record)

    # ------------------------------------------------------------------
    # Retention execution (retention.py boundary: engine proposes,
    # orchestrator disposes)
    # ------------------------------------------------------------------

    async def run_retention_cycle(
        self,
        session_id: Optional[UUID] = None,
        now: Optional[datetime] = None,
    ) -> RetentionBatch:
        """Evaluate and execute one retention cycle.

        RetentionEngine returns pure decisions; this method executes them:
        promotions become tier changes, forgetting actions become soft
        deletes or archives. Returns the evaluated batch.
        """
        now = now or datetime.now(timezone.utc)
        batch = await self.retention_engine.evaluate_all(session_id, now)

        for promotion in batch.promotions:
            await self.promote(promotion.memory_id, promotion.target_tier)

        for forgetting in batch.forgettings:
            if forgetting.action_type == "archive":
                await self.archive(forgetting.memory_id, forgetting.reason)
            else:
                await self.forget(forgetting.memory_id, forgetting.reason)

        for archive_action in batch.archives:
            await self.archive(archive_action.memory_id, archive_action.reason)

        for cascade in batch.cascades:
            for target_id in cascade.target_memory_ids:
                await self.forget(target_id, cascade.reason)

        return batch
