"""JARVIS OS - Phase 19 Memory DTO Layer.

Canonical data transfer objects for the Real Memory Architecture.
These DTOs are the contract boundary for all memory operations.

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

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# =====================================================================
# Frozen Enums (§16.3, §16.4, §3.3 of spec)
# =====================================================================


class MemoryType(str, Enum):
    """Memory category. Frozen enum (§16.3)."""

    FACT = "fact"
    PREFERENCE = "preference"
    TASK = "task"
    GOAL = "goal"
    EVENT = "event"
    CONVERSATION = "conversation"
    RELATIONSHIP = "relationship"
    SYSTEM = "system"
    EPHEMERAL = "ephemeral"


class MemoryVisibility(str, Enum):
    """Access scope. Frozen enum (§16.4)."""

    PRIVATE = "private"
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"
    PUBLIC = "public"


class MemoryTrustLevel(str, Enum):
    """Source trust level. Frozen enum (§3.3)."""

    SYSTEM = "system"
    USER_EXPLICIT = "user_explicit"
    USER_IMPLICIT = "user_implicit"
    LEARNED = "learned"
    INFERRED = "inferred"


class MemoryTier(str, Enum):
    """Memory lifecycle tier. Frozen enum (§2.1)."""

    IDENTITY = "identity"
    WORKING = "working"
    CONVERSATION = "conversation"
    LONG_TERM = "long_term"
    ARCHIVED = "archived"


class ExecutionOutcome(str, Enum):
    """Post-execution result. Frozen enum (§7.2)."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


# =====================================================================
# Frozen Enums — Knowledge Graph (§16.5, §16.6)
# =====================================================================


class KGNodeType(str, Enum):
    """Knowledge graph node type. Frozen enum (§16.5)."""

    PERSON = "Person"
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    CONCEPT = "Concept"
    EVENT = "Event"
    TASK = "Task"
    GOAL = "Goal"
    SKILL = "Skill"


class KGEdgeType(str, Enum):
    """Knowledge graph edge type. Frozen enum (§16.6)."""

    KNOWS = "knows"
    WORKS_ON = "works_on"
    DEPENDS_ON = "depends_on"
    OWNS = "owns"
    RELATED_TO = "related_to"
    CAUSED_BY = "caused_by"
    USES = "uses"


# =====================================================================
# Identity Contract (§16.1)
# =====================================================================


class MemoryIdentity(BaseModel):
    """Immutable identity fields for a memory record. Frozen contract (§16.1)."""

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    session_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str
    memory_type: MemoryType
    visibility: MemoryVisibility
    trust_level: MemoryTrustLevel
    confidence: float = Field(ge=0.0, le=1.0)
    version: int = Field(ge=1, default=1)


# =====================================================================
# Provenance Contract (§16.2)
# =====================================================================


class MemoryProvenance(BaseModel):
    """Provenance metadata for a memory record. Frozen contract (§16.2)."""

    schema_version: Literal["1.0"] = "1.0"

    origin: str
    derived_from: Optional[List[UUID]] = None
    created_by: str
    updated_by: Optional[str] = None
    reason: Optional[str] = None
    reflection_id: Optional[UUID] = None
    workflow_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None


# =====================================================================
# Memory Metadata
# =====================================================================


class MemoryMetadata(BaseModel):
    """Extensible metadata for a memory record."""

    schema_version: Literal["1.0"] = "1.0"

    importance: float = Field(ge=0.0, le=1.0, default=0.5)
    token_count: int = Field(ge=0, default=0)
    embedding_id: Optional[UUID] = None
    graph_node_id: Optional[UUID] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


# =====================================================================
# Canonical Storage Contract (§16.9)
# =====================================================================


class MemoryRecord(BaseModel):
    """Canonical memory record. Frozen contract (§16.9).

    This is the single source of truth for memory storage across
    PostgreSQL, Vector DB, Graph DB, and future migrations.
    """

    schema_version: Literal["1.0"] = "1.0"

    # Identity (immutable after creation)
    memory_id: UUID = Field(default_factory=uuid4)
    memory_type: MemoryType

    # Ownership & Access
    owner_id: UUID
    visibility: MemoryVisibility

    # Trust & Confidence
    trust_level: MemoryTrustLevel
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0, default=0.5)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    # Versioning
    version: int = Field(ge=1, default=1)

    # Cross-references (representation links, not tiers)
    embedding_id: Optional[UUID] = None
    graph_node_id: Optional[UUID] = None

    # Provenance
    provenance: MemoryProvenance

    # Content & Metadata
    content: str
    content_hash: str  # SHA-256 for dedup
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)


# =====================================================================
# Score Contract (§3.1)
# =====================================================================


class MemoryScore(BaseModel):
    """Score breakdown for a memory record. Frozen formula (§3.1).

    FinalScore = Recency + SemanticSimilarity + Confidence + Importance
                 + Frequency + Trust + UserPin
    """

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    recency: float = Field(ge=0.0, le=1.0)
    semantic_similarity: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)
    frequency: float = Field(ge=0.0, le=1.0)
    trust: float = Field(ge=0.0, le=1.0)
    user_pin: float = Field(ge=0.0, le=1.0, default=0.0)
    final_score: float = Field(ge=0.0)
    tier: MemoryTier
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =====================================================================
# Retrieval DTOs (§6)
# =====================================================================


class RetrievalRequest(BaseModel):
    """Request to recall memories. Frozen contract (§6.1)."""

    schema_version: Literal["1.0"] = "1.0"

    query: str
    max_chunks: int = Field(ge=1, default=50)
    max_tokens: int = Field(ge=1, default=2000)
    min_score: float = Field(ge=0.0, le=1.0, default=0.0)
    tier_filter: Optional[List[MemoryTier]] = None
    graph_depth: int = Field(ge=0, default=0)
    graph_root_node_id: Optional[UUID] = None
    include_archived: bool = False
    session_id: Optional[UUID] = None
    owner_id: Optional[UUID] = None


class RecallMetadata(BaseModel):
    """Metadata about a retrieval operation."""

    schema_version: Literal["1.0"] = "1.0"

    query_time_ms: float = 0.0
    chunks_searched: int = 0
    tiers_hit: List[MemoryTier] = Field(default_factory=list)
    budget_used: int = 0
    budget_remaining: int = 0


class RetrievalResponse(BaseModel):
    """Response from memory recall. Frozen contract (§6.1)."""

    schema_version: Literal["1.0"] = "1.0"

    chunks: List[MemoryRecord] = Field(default_factory=list)
    scores: List[MemoryScore] = Field(default_factory=list)
    graph_node_ids: List[UUID] = Field(default_factory=list)
    total_tokens: int = 0
    metadata: RecallMetadata = Field(default_factory=RecallMetadata)


# =====================================================================
# Reflection DTOs (§7)
# =====================================================================


class ReflectionRequest(BaseModel):
    """Request to apply reflection to a memory. Frozen contract (§7.2)."""

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    outcome: ExecutionOutcome
    confidence_delta: float = Field(ge=-1.0, le=1.0)
    notes: Optional[str] = None


class ReflectionResponse(BaseModel):
    """Response from reflection operation."""

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    old_confidence: float = Field(ge=0.0, le=1.0)
    new_confidence: float = Field(ge=0.0, le=1.0)
    applied: bool = False
    reason: Optional[str] = None


# =====================================================================
# Promotion DTOs (§4)
# =====================================================================


class PromotionRequest(BaseModel):
    """Request to promote a memory to a higher tier. Frozen contract (§4)."""

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    target_tier: MemoryTier
    reason: Optional[str] = None


class PromotionResponse(BaseModel):
    """Response from promotion operation."""

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    old_tier: MemoryTier
    new_tier: MemoryTier
    promoted: bool = False
    reason: Optional[str] = None


# =====================================================================
# Archive DTOs (§5)
# =====================================================================


class ArchiveRequest(BaseModel):
    """Request to archive a memory. Frozen contract (§5)."""

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    reason: str


class ArchiveResponse(BaseModel):
    """Response from archive operation."""

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    archived: bool = False
    archived_at: Optional[datetime] = None


# =====================================================================
# Forget DTOs (§5)
# =====================================================================


class ForgetRequest(BaseModel):
    """Request to forget a memory. Frozen contract (§5)."""

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    reason: str
    cascade: bool = False


class ForgetResponse(BaseModel):
    """Response from forget operation."""

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    forgotten: bool = False
    cascade_count: int = 0


# =====================================================================
# Store DTO
# =====================================================================


class StoreRequest(BaseModel):
    """Request to store a new memory."""

    schema_version: Literal["1.0"] = "1.0"

    content: str
    source_type: str
    owner_id: UUID
    memory_type: MemoryType = MemoryType.FACT
    visibility: MemoryVisibility = MemoryVisibility.PRIVATE
    trust_level: MemoryTrustLevel = MemoryTrustLevel.USER_IMPLICIT
    importance: float = Field(ge=0.0, le=1.0, default=0.5)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    metadata: Optional[Dict[str, Any]] = None
    session_id: Optional[UUID] = None


class StoreResponse(BaseModel):
    """Response from store operation."""

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    tier: MemoryTier
    score: Optional[MemoryScore] = None


# =====================================================================
# Stats DTO
# =====================================================================


class MemoryStatsResponse(BaseModel):
    """Memory statistics per tier."""

    schema_version: Literal["1.0"] = "1.0"

    total_chunks: int = 0
    chunks_by_tier: Dict[MemoryTier, int] = Field(default_factory=dict)
    average_score: float = 0.0
    oldest_chunk_age_days: float = 0.0
    newest_chunk_age_days: float = 0.0


# =====================================================================
# Retention DTOs (M5.0)
# =====================================================================


class PromotionAction(BaseModel):
    """A single promotion action to be executed by the retention engine.

    Promotion moves a memory from a colder tier to a warmer tier
    (L1 -> L2 or L2 -> L3) when access/score thresholds are met.
    Idempotent: re-emitting the same (memory_id, to_tier) is a no-op.
    """

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    from_tier: MemoryTier
    to_tier: MemoryTier
    reason: str = Field(min_length=1, max_length=200)
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    access_count: Optional[int] = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ForgettingAction(BaseModel):
    """A single forgetting action to be executed by the retention engine.

    Forgetting removes a memory from active tiers. Reasons:
    - TTL: tier-specific time-to-live expired
    - decay: confidence/importance below threshold
    - manual: explicit user request
    - cascade: source memory deleted
    - gdpr: data subject erasure request
    """

    schema_version: Literal["1.0"] = "1.0"

    memory_id: UUID
    from_tier: MemoryTier
    reason: Literal["ttl", "decay", "manual", "cascade", "gdpr"]
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    age_seconds: Optional[int] = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RetentionEvaluationResult(BaseModel):
    """Result of a single retention evaluation cycle.

    Returned by RetentionEngine.evaluate(now). Contains the actions
    that should be applied. The orchestrator is responsible for
    executing them (single-responsibility rule: engine proposes,
    orchestrator disposes).
    """

    schema_version: Literal["1.0"] = "1.0"

    promotions: List[PromotionAction] = Field(default_factory=list)
    forgetting: List[ForgettingAction] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_promotions: int = 0
    total_forgetting: int = 0
    cycle_duration_ms: float = Field(default=0.0, ge=0.0)

    def record(self) -> None:
        """Update totals from action lists. Idempotent."""
        self.total_promotions = len(self.promotions)
        self.total_forgetting = len(self.forgetting)
