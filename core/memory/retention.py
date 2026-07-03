"""
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

Architecture boundary:
    RetentionEngine is a PURE DECISION ENGINE.
    It never writes to the repository.
    All returned Action objects are decisions only.
    Actual database mutations must be executed by MemoryOrchestrator (M7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from core.config import MemoryRetentionConfig
from core.interfaces import EventBusInterface, InterAgentMessage
from core.memory.dto import MemoryRecord, MemoryTier
from core.memory.memory_repository import IMemoryRecordRepository
from core.memory.scoring import ScoringEngine, ScoringInput

# =====================================================================
# Promotion Reason Enum (Recommendation 3)
# =====================================================================


class PromotionReason(str, Enum):
    """Reason explaining why a promotion was recommended. Frozen contract."""

    ACCESS_COUNT = "access_count"
    HIGH_SCORE = "high_score"
    PINNED = "pinned"
    USER_ACTION = "user_action"
    REFLECTION = "reflection"
    POLICY = "policy"


# =====================================================================
# Action DTOs (all decisions — no side effects)
# =====================================================================


@dataclass(frozen=True)
class PromotionAction:
    """Decision: recommend promoting a memory from one tier to another."""

    memory_id: UUID
    source_tier: MemoryTier
    target_tier: MemoryTier
    reason: str
    promotion_reason: PromotionReason = PromotionReason.POLICY


@dataclass(frozen=True)
class ForgettingAction:
    """Decision: recommend forgetting (eviction or hard delete) for a memory."""

    memory_id: UUID
    action_type: Literal["archive", "forget"]
    reason: str


@dataclass(frozen=True)
class ArchiveAction:
    """Decision: recommend archiving a specific memory chunk."""

    memory_id: UUID
    reason: str


@dataclass(frozen=True)
class CascadeDeleteAction:
    """Decision: recommend cascading deletion of all memories for a source entity."""

    source_id: UUID
    reason: str
    target_memory_ids: List[UUID]


# =====================================================================
# Retention Batch (Recommendation 2)
# =====================================================================


@dataclass
class RetentionBatch:
    """Aggregated output of a retention evaluation run.

    All items are DECISIONS only. No side effects.
    Execution must be handled by MemoryOrchestrator (M7).
    """

    evaluated_at: datetime
    promotions: List[PromotionAction] = field(default_factory=list)
    forgettings: List[ForgettingAction] = field(default_factory=list)
    archives: List[ArchiveAction] = field(default_factory=list)
    cascades: List[CascadeDeleteAction] = field(default_factory=list)

    @property
    def promotion_count(self) -> int:
        return len(self.promotions)

    @property
    def forget_count(self) -> int:
        return len([a for a in self.forgettings if a.action_type == "forget"])

    @property
    def archive_count(self) -> int:
        return len(self.forgettings) - self.forget_count + len(self.archives)

    @property
    def cascade_count(self) -> int:
        return len(self.cascades)

    @property
    def total_actions(self) -> int:
        return (
            self.promotion_count
            + len(self.forgettings)
            + len(self.archives)
            + self.cascade_count
        )


# =====================================================================
# Retention Engine (pure decision layer)
# =====================================================================


class RetentionEngine:
    """Evaluates memory lifecycle decisions. Pure decision engine.

    Architecture invariant (FROZEN):
        - NEVER writes to repository.
        - NEVER executes promotions, deletions, or archives directly.
        - ALWAYS returns structured action decisions.
        - MemoryOrchestrator (M7) is responsible for all execution.
    """

    def __init__(
        self,
        memory_repo: IMemoryRecordRepository,
        scoring_engine: ScoringEngine,
        config: MemoryRetentionConfig,
        event_bus: Optional[EventBusInterface] = None,
    ) -> None:
        self._repository = memory_repo
        self._scoring_engine = scoring_engine
        self._config = config
        self._event_bus = event_bus

    async def _publish_event(self, topic: str, body: Dict[str, Any]) -> None:
        """Publish a telemetry event to the EventBus."""
        if self._event_bus is None:
            return
        try:
            msg = InterAgentMessage(
                sender="memory.retention_engine",
                receiver="system",
                action=topic,
                body=body,
            )
            await self._event_bus.publish(topic, msg)
        except Exception:
            # Telemetry must never disrupt retention pipeline
            pass

    def _infer_tier(self, record: MemoryRecord) -> MemoryTier:
        """Infer memory tier from record properties."""
        if record.metadata and record.metadata.extra:
            tier_str = record.metadata.extra.get("tier")
            if tier_str:
                try:
                    return MemoryTier(tier_str)
                except ValueError:
                    pass
        if record.expires_at is not None:
            if record.expires_at.year >= 9999:
                return MemoryTier.ARCHIVED
        return MemoryTier.LONG_TERM

    def _get_access_count(self, record: MemoryRecord) -> int:
        """Extract access_count from metadata.extra."""
        if record.metadata and record.metadata.extra:
            return int(record.metadata.extra.get("access_count", 0))
        return 0

    def _get_is_pinned(self, record: MemoryRecord) -> bool:
        """Extract is_pinned boolean flag from metadata.extra."""
        if record.metadata and record.metadata.extra:
            extra = record.metadata.extra
            return bool(extra.get("is_pinned", extra.get("pinned", False)))
        return False

    def _is_throttled(self, record: MemoryRecord, now: datetime) -> bool:
        """Check if a record was promoted recently (within throttle window)."""
        last_promoted_str = record.metadata.extra.get("last_promoted")
        if not last_promoted_str:
            return False
        try:
            last_promoted = datetime.fromisoformat(last_promoted_str)
            return (
                now - last_promoted
            ).total_seconds() < self._config.promotion_throttle_seconds
        except ValueError:
            return False

    async def evaluate_promotions(
        self,
        session_id: UUID,
        now: datetime,
    ) -> List[PromotionAction]:
        """Evaluate pending promotions for a session.

        Pure decision function: no writes, no side effects.
        Returns promotion action decisions for MemoryOrchestrator to execute.
        """
        records = await self._repository.list_records(session_id=session_id)
        actions: List[PromotionAction] = []

        # Score all CONVERSATION tier records for L2->L3 evaluation
        l2_records = [
            r for r in records if self._infer_tier(r) == MemoryTier.CONVERSATION
        ]

        scores_map: Dict[UUID, float] = {}
        if l2_records:
            scoring_inputs = [
                ScoringInput(
                    memory_id=r.memory_id,
                    confidence=r.confidence,
                    importance=r.importance,
                    trust_level=r.trust_level,
                    access_count=self._get_access_count(r),
                    last_accessed=r.updated_at,
                    created_at=r.created_at,
                    is_pinned=self._get_is_pinned(r),
                    semantic_similarity=0.0,
                    tier=MemoryTier.CONVERSATION,
                )
                for r in l2_records
            ]
            scores = self._scoring_engine.rank(scoring_inputs, now)
            scores_map = {s.memory_id: s.final_score for s in scores}

        for record in records:
            tier = self._infer_tier(record)
            if self._is_throttled(record, now):
                continue

            if tier == MemoryTier.WORKING:
                # L1 -> L2: access_count >= 3 within TTL window
                age_minutes = (now - record.updated_at).total_seconds() / 60.0
                access_count = self._get_access_count(record)
                if (
                    age_minutes <= self._config.l1_ttl_minutes
                    and access_count >= 3
                ):
                    actions.append(
                        PromotionAction(
                            memory_id=record.memory_id,
                            source_tier=MemoryTier.WORKING,
                            target_tier=MemoryTier.CONVERSATION,
                            reason=f"L1 hot promotion (access_count={access_count} >= 3)",
                            promotion_reason=PromotionReason.ACCESS_COUNT,
                        )
                    )

            elif tier == MemoryTier.CONVERSATION:
                # L2 -> L3: score >= threshold AND access_count >= 2
                score = scores_map.get(record.memory_id, 0.0)
                access_count = self._get_access_count(record)
                if (
                    score >= self._config.l2_promotion_threshold
                    and access_count >= 2
                ):
                    promotion_reason = (
                        PromotionReason.PINNED
                        if self._get_is_pinned(record)
                        else PromotionReason.HIGH_SCORE
                    )
                    actions.append(
                        PromotionAction(
                            memory_id=record.memory_id,
                            source_tier=MemoryTier.CONVERSATION,
                            target_tier=MemoryTier.LONG_TERM,
                            reason=f"L2 persistent promotion (score={score:.2f} >= {self._config.l2_promotion_threshold})",
                            promotion_reason=promotion_reason,
                        )
                    )

        return actions

    async def evaluate_forgetting(
        self,
        now: datetime,
    ) -> List[ForgettingAction]:
        """Evaluate pending evictions/forgettings across all tiers.

        Pure decision function: no writes, no side effects.
        Returns forgetting action decisions for MemoryOrchestrator to execute.
        """
        records = await self._repository.list_records(
            include_deleted=False, include_archived=True
        )
        actions: List[ForgettingAction] = []

        # Score CONVERSATION and LONG_TERM records for decay evaluation
        l2_l3_records = [
            r
            for r in records
            if self._infer_tier(r) in (MemoryTier.CONVERSATION, MemoryTier.LONG_TERM)
        ]

        scores_map: Dict[UUID, float] = {}
        if l2_l3_records:
            scoring_inputs = [
                ScoringInput(
                    memory_id=r.memory_id,
                    confidence=r.confidence,
                    importance=r.importance,
                    trust_level=r.trust_level,
                    access_count=self._get_access_count(r),
                    last_accessed=r.updated_at,
                    created_at=r.created_at,
                    is_pinned=self._get_is_pinned(r),
                    semantic_similarity=0.0,
                    tier=self._infer_tier(r),
                )
                for r in l2_l3_records
            ]
            scores = self._scoring_engine.rank(scoring_inputs, now)
            scores_map = {s.memory_id: s.final_score for s in scores}

        for record in records:
            tier = self._infer_tier(record)

            if tier == MemoryTier.WORKING:
                age_minutes = (now - record.updated_at).total_seconds() / 60.0
                if age_minutes > self._config.l1_ttl_minutes:
                    actions.append(
                        ForgettingAction(
                            memory_id=record.memory_id,
                            action_type="forget",
                            reason=f"L1 TTL expiry (age={age_minutes:.1f}m > {self._config.l1_ttl_minutes}m)",
                        )
                    )

            elif tier == MemoryTier.CONVERSATION:
                age_hours = (now - record.updated_at).total_seconds() / 3600.0
                if age_hours > self._config.l2_ttl_hours:
                    score = scores_map.get(record.memory_id, 0.0)
                    is_promotable = (
                        score >= self._config.l2_promotion_threshold
                        and self._get_access_count(record) >= 2
                    )
                    if not is_promotable:
                        actions.append(
                            ForgettingAction(
                                memory_id=record.memory_id,
                                action_type="forget",
                                reason=f"L2 TTL expiry without promotion eligibility (age={age_hours:.1f}h, score={score:.2f})",
                            )
                        )

            elif tier == MemoryTier.LONG_TERM:
                score = scores_map.get(record.memory_id, 0.0)
                if score < self._config.l3_decay_threshold:
                    actions.append(
                        ForgettingAction(
                            memory_id=record.memory_id,
                            action_type="archive",
                            reason=f"L3 score decay (score={score:.2f} < {self._config.l3_decay_threshold})",
                        )
                    )

            elif tier == MemoryTier.ARCHIVED:
                age_days = (now - record.updated_at).total_seconds() / 86400.0
                if age_days > self._config.archive_retention_days:
                    actions.append(
                        ForgettingAction(
                            memory_id=record.memory_id,
                            action_type="forget",
                            reason=f"Archive retention period exceeded (age={age_days:.1f}d > {self._config.archive_retention_days}d)",
                        )
                    )

        return actions

    def recommend_archive(self, chunk_id: UUID, reason: str) -> ArchiveAction:
        """Produce an archive decision for a specific chunk.

        Pure decision function: returns an ArchiveAction, does NOT write.
        Execution must be performed by MemoryOrchestrator (M7).
        """
        return ArchiveAction(memory_id=chunk_id, reason=reason)

    async def recommend_cascade_delete(
        self,
        source_id: UUID,
        reason: str,
    ) -> CascadeDeleteAction:
        """Produce a cascade delete decision for a source entity.

        Pure decision function: reads records to compute affected IDs, does NOT write.
        Execution must be performed by MemoryOrchestrator (M7).
        """
        records = await self._repository.list_records(
            include_deleted=False, include_archived=True
        )
        target_ids = [
            r.memory_id
            for r in records
            if (
                r.provenance.workflow_id == source_id
                or r.provenance.agent_id == source_id
            )
        ]
        return CascadeDeleteAction(
            source_id=source_id,
            reason=reason,
            target_memory_ids=target_ids,
        )

    async def evaluate_all(
        self,
        session_id: Optional[UUID],
        now: datetime,
    ) -> RetentionBatch:
        """Run a full retention evaluation cycle and return a RetentionBatch.

        Emits telemetry events on start, completion, and failure.
        Pure decision: all returned actions require Orchestrator execution.
        """
        start = datetime.now(timezone.utc)
        await self._publish_event(
            "memory.retention.started",
            {
                "session_id": str(session_id) if session_id else None,
            },
        )

        try:
            promotions: List[PromotionAction] = []
            if session_id is not None:
                promotions = await self.evaluate_promotions(session_id, now)

            forgettings = await self.evaluate_forgetting(now)

            batch = RetentionBatch(
                evaluated_at=now,
                promotions=promotions,
                forgettings=forgettings,
            )

            elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            await self._publish_event(
                "memory.retention.completed",
                {
                    "promotion_count": batch.promotion_count,
                    "forget_count": batch.forget_count,
                    "archive_count": batch.archive_count,
                    "cascade_count": batch.cascade_count,
                    "duration_ms": round(elapsed_ms, 2),
                },
            )

            return batch

        except Exception as e:
            await self._publish_event(
                "memory.retention.failed",
                {"error": str(e)},
            )
            raise
