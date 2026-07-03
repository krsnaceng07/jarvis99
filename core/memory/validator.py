"""JARVIS OS - Phase 19 Memory Validator.

Pure validation layer for memory DTOs. No side effects.
No repository, no DB, no vector, no graph, no scoring, no EventBus.

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

from dataclasses import dataclass, field
from typing import List
from uuid import UUID

from core.memory.dto import (
    ArchiveRequest,
    ForgetRequest,
    KGEdgeType,
    KGNodeType,
    MemoryIdentity,
    MemoryMetadata,
    MemoryProvenance,
    MemoryRecord,
    MemoryScore,
    MemoryTier,
    MemoryTrustLevel,
    MemoryType,
    MemoryVisibility,
    PromotionRequest,
    ReflectionRequest,
    RetrievalRequest,
    StoreRequest,
)
from core.memory.interfaces import MemoryNodeDTO, MemoryRelationDTO

# =====================================================================
# Validation Result
# =====================================================================


@dataclass(frozen=True)
class ValidationResult:
    """Result of a validation operation."""

    valid: bool
    errors: List[str] = field(default_factory=list)

    @classmethod
    def ok(cls) -> ValidationResult:
        return ValidationResult(valid=True)

    @classmethod
    def fail(cls, *errors: str) -> ValidationResult:
        return ValidationResult(valid=False, errors=list(errors))


# =====================================================================
# Identity Validator (§16.1)
# =====================================================================


def validate_identity(identity: MemoryIdentity) -> ValidationResult:
    """Validate MemoryIdentity contract fields.

    Checks:
    - memory_id is not nil
    - owner_id is not nil
    - created_by is non-empty
    - memory_type is valid enum
    - visibility is valid enum
    - trust_level is valid enum
    - confidence in [0.0, 1.0]
    - version >= 1
    """
    errors: List[str] = []

    if identity.memory_id == UUID(int=0):
        errors.append("memory_id must not be nil UUID")

    if identity.owner_id == UUID(int=0):
        errors.append("owner_id must not be nil UUID")

    if not identity.created_by or not identity.created_by.strip():
        errors.append("created_by must be non-empty")

    if not isinstance(identity.memory_type, MemoryType):
        errors.append(
            f"memory_type must be a valid MemoryType, got {identity.memory_type!r}"
        )

    if not isinstance(identity.visibility, MemoryVisibility):
        errors.append(
            f"visibility must be a valid MemoryVisibility, got {identity.visibility!r}"
        )

    if not isinstance(identity.trust_level, MemoryTrustLevel):
        errors.append(
            f"trust_level must be a valid MemoryTrustLevel, got {identity.trust_level!r}"
        )

    if not (0.0 <= identity.confidence <= 1.0):
        errors.append(f"confidence must be in [0.0, 1.0], got {identity.confidence}")

    if identity.version < 1:
        errors.append(f"version must be >= 1, got {identity.version}")

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Provenance Validator (§16.2)
# =====================================================================


def validate_provenance(provenance: MemoryProvenance) -> ValidationResult:
    """Validate MemoryProvenance contract fields.

    Checks:
    - origin is non-empty
    - created_by is non-empty
    - derived_from contains valid UUIDs if present
    """
    errors: List[str] = []

    if not provenance.origin or not provenance.origin.strip():
        errors.append("origin must be non-empty")

    if not provenance.created_by or not provenance.created_by.strip():
        errors.append("created_by must be non-empty")

    if provenance.derived_from is not None:
        for i, parent_id in enumerate(provenance.derived_from):
            if parent_id == UUID(int=0):
                errors.append(f"derived_from[{i}] must not be nil UUID")

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Metadata Validator
# =====================================================================


def validate_metadata(metadata: MemoryMetadata) -> ValidationResult:
    """Validate MemoryMetadata fields.

    Checks:
    - importance in [0.0, 1.0]
    - token_count >= 0
    """
    errors: List[str] = []

    if not (0.0 <= metadata.importance <= 1.0):
        errors.append(f"importance must be in [0.0, 1.0], got {metadata.importance}")

    if metadata.token_count < 0:
        errors.append(f"token_count must be >= 0, got {metadata.token_count}")

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Memory Record Validator (§16.9)
# =====================================================================


def validate_record(record: MemoryRecord) -> ValidationResult:
    """Validate a complete MemoryRecord.

    Checks:
    - schema_version is "1.0"
    - Identity fields valid
    - Provenance valid
    - Metadata valid
    - content is non-empty
    - content_hash is non-empty
    - confidence in [0.0, 1.0]
    - importance in [0.0, 1.0]
    - version >= 1
    """
    errors: List[str] = []

    if record.schema_version != "1.0":
        errors.append(f"schema_version must be '1.0', got {record.schema_version!r}")

    if record.memory_id == UUID(int=0):
        errors.append("memory_id must not be nil UUID")

    if record.owner_id == UUID(int=0):
        errors.append("owner_id must not be nil UUID")

    if not isinstance(record.memory_type, MemoryType):
        errors.append(
            f"memory_type must be a valid MemoryType, got {record.memory_type!r}"
        )

    if not isinstance(record.visibility, MemoryVisibility):
        errors.append(
            f"visibility must be a valid MemoryVisibility, got {record.visibility!r}"
        )

    if not isinstance(record.trust_level, MemoryTrustLevel):
        errors.append(
            f"trust_level must be a valid MemoryTrustLevel, got {record.trust_level!r}"
        )

    if not (0.0 <= record.confidence <= 1.0):
        errors.append(f"confidence must be in [0.0, 1.0], got {record.confidence}")

    if not (0.0 <= record.importance <= 1.0):
        errors.append(f"importance must be in [0.0, 1.0], got {record.importance}")

    if record.version < 1:
        errors.append(f"version must be >= 1, got {record.version}")

    if not record.content or not record.content.strip():
        errors.append("content must be non-empty")

    if not record.content_hash or not record.content_hash.strip():
        errors.append("content_hash must be non-empty")

    provenance_result = validate_provenance(record.provenance)
    if not provenance_result.valid:
        errors.extend(provenance_result.errors)

    metadata_result = validate_metadata(record.metadata)
    if not metadata_result.valid:
        errors.extend(metadata_result.errors)

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Score Validator (§3.1)
# =====================================================================


def validate_score(score: MemoryScore) -> ValidationResult:
    """Validate a MemoryScore.

    Checks:
    - schema_version is "1.0"
    - All components in [0.0, 1.0]
    - final_score >= 0.0
    - tier is valid
    """
    errors: List[str] = []

    if score.schema_version != "1.0":
        errors.append(f"schema_version must be '1.0', got {score.schema_version!r}")

    if score.memory_id == UUID(int=0):
        errors.append("memory_id must not be nil UUID")

    components = {
        "recency": score.recency,
        "semantic_similarity": score.semantic_similarity,
        "confidence": score.confidence,
        "importance": score.importance,
        "frequency": score.frequency,
        "trust": score.trust,
        "user_pin": score.user_pin,
    }
    for name, value in components.items():
        if not (0.0 <= value <= 1.0):
            errors.append(f"{name} must be in [0.0, 1.0], got {value}")

    if score.final_score < 0.0:
        errors.append(f"final_score must be >= 0.0, got {score.final_score}")

    if not isinstance(score.tier, MemoryTier):
        errors.append(f"tier must be a valid MemoryTier, got {score.tier!r}")

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Store Request Validator
# =====================================================================


def validate_store_request(request: StoreRequest) -> ValidationResult:
    """Validate a StoreRequest.

    Checks:
    - schema_version is "1.0"
    - content is non-empty
    - source_type is non-empty
    - owner_id is not nil
    - memory_type is valid
    - visibility is valid
    - trust_level is valid
    - importance in [0.0, 1.0]
    - confidence in [0.0, 1.0]
    """
    errors: List[str] = []

    if request.schema_version != "1.0":
        errors.append(f"schema_version must be '1.0', got {request.schema_version!r}")

    if not request.content or not request.content.strip():
        errors.append("content must be non-empty")

    if not request.source_type or not request.source_type.strip():
        errors.append("source_type must be non-empty")

    if request.owner_id == UUID(int=0):
        errors.append("owner_id must not be nil UUID")

    if not isinstance(request.memory_type, MemoryType):
        errors.append(
            f"memory_type must be a valid MemoryType, got {request.memory_type!r}"
        )

    if not isinstance(request.visibility, MemoryVisibility):
        errors.append(
            f"visibility must be a valid MemoryVisibility, got {request.visibility!r}"
        )

    if not isinstance(request.trust_level, MemoryTrustLevel):
        errors.append(
            f"trust_level must be a valid MemoryTrustLevel, got {request.trust_level!r}"
        )

    if not (0.0 <= request.importance <= 1.0):
        errors.append(f"importance must be in [0.0, 1.0], got {request.importance}")

    if not (0.0 <= request.confidence <= 1.0):
        errors.append(f"confidence must be in [0.0, 1.0], got {request.confidence}")

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Retrieval Request Validator
# =====================================================================


def validate_retrieval_request(request: RetrievalRequest) -> ValidationResult:
    """Validate a RetrievalRequest.

    Checks:
    - schema_version is "1.0"
    - query is non-empty
    - max_chunks >= 1
    - max_tokens >= 1
    - min_score in [0.0, 1.0]
    - graph_depth >= 0
    - tier_filter contains valid tiers if present
    """
    errors: List[str] = []

    if request.schema_version != "1.0":
        errors.append(f"schema_version must be '1.0', got {request.schema_version!r}")

    if not request.query or not request.query.strip():
        errors.append("query must be non-empty")

    if request.max_chunks < 1:
        errors.append(f"max_chunks must be >= 1, got {request.max_chunks}")

    if request.max_tokens < 1:
        errors.append(f"max_tokens must be >= 1, got {request.max_tokens}")

    if not (0.0 <= request.min_score <= 1.0):
        errors.append(f"min_score must be in [0.0, 1.0], got {request.min_score}")

    if request.graph_depth < 0:
        errors.append(f"graph_depth must be >= 0, got {request.graph_depth}")

    if request.tier_filter is not None:
        for i, tier in enumerate(request.tier_filter):
            if not isinstance(tier, MemoryTier):
                errors.append(
                    f"tier_filter[{i}] must be a valid MemoryTier, got {tier!r}"
                )

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Reflection Request Validator
# =====================================================================


def validate_reflection_request(request: ReflectionRequest) -> ValidationResult:
    """Validate a ReflectionRequest.

    Checks:
    - schema_version is "1.0"
    - memory_id is not nil
    - outcome is valid
    - confidence_delta in [-1.0, 1.0]
    """
    errors: List[str] = []

    if request.schema_version != "1.0":
        errors.append(f"schema_version must be '1.0', got {request.schema_version!r}")

    if request.memory_id == UUID(int=0):
        errors.append("memory_id must not be nil UUID")

    if not isinstance(
        request.outcome,
        __import__("core.memory.dto", fromlist=["ExecutionOutcome"]).ExecutionOutcome,
    ):
        errors.append(
            f"outcome must be a valid ExecutionOutcome, got {request.outcome!r}"
        )

    if not (-1.0 <= request.confidence_delta <= 1.0):
        errors.append(
            f"confidence_delta must be in [-1.0, 1.0], got {request.confidence_delta}"
        )

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Promotion Request Validator
# =====================================================================


def validate_promotion_request(request: PromotionRequest) -> ValidationResult:
    """Validate a PromotionRequest.

    Checks:
    - schema_version is "1.0"
    - memory_id is not nil
    - target_tier is valid
    - target_tier is promotable (not IDENTITY or ARCHIVED)
    """
    errors: List[str] = []

    if request.schema_version != "1.0":
        errors.append(f"schema_version must be '1.0', got {request.schema_version!r}")

    if request.memory_id == UUID(int=0):
        errors.append("memory_id must not be nil UUID")

    if not isinstance(request.target_tier, MemoryTier):
        errors.append(
            f"target_tier must be a valid MemoryTier, got {request.target_tier!r}"
        )

    if request.target_tier in (MemoryTier.IDENTITY, MemoryTier.ARCHIVED):
        errors.append(
            f"target_tier must be promotable, got {request.target_tier!r} "
            "(IDENTITY and ARCHIVED are not promotable targets)"
        )

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Archive Request Validator
# =====================================================================


def validate_archive_request(request: ArchiveRequest) -> ValidationResult:
    """Validate an ArchiveRequest.

    Checks:
    - schema_version is "1.0"
    - memory_id is not nil
    - reason is non-empty
    """
    errors: List[str] = []

    if request.schema_version != "1.0":
        errors.append(f"schema_version must be '1.0', got {request.schema_version!r}")

    if request.memory_id == UUID(int=0):
        errors.append("memory_id must not be nil UUID")

    if not request.reason or not request.reason.strip():
        errors.append("reason must be non-empty")

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Forget Request Validator
# =====================================================================


def validate_forget_request(request: ForgetRequest) -> ValidationResult:
    """Validate a ForgetRequest.

    Checks:
    - schema_version is "1.0"
    - memory_id is not nil
    - reason is non-empty
    """
    errors: List[str] = []

    if request.schema_version != "1.0":
        errors.append(f"schema_version must be '1.0', got {request.schema_version!r}")

    if request.memory_id == UUID(int=0):
        errors.append("memory_id must not be nil UUID")

    if not request.reason or not request.reason.strip():
        errors.append("reason must be non-empty")

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Tier Transition Validator
# =====================================================================


# Valid promotion transitions (§4)
_PROMOTION_TRANSITIONS: dict[MemoryTier, List[MemoryTier]] = {
    MemoryTier.WORKING: [MemoryTier.CONVERSATION],
    MemoryTier.CONVERSATION: [MemoryTier.LONG_TERM],
    MemoryTier.LONG_TERM: [MemoryTier.ARCHIVED],
}


def validate_tier_transition(
    current_tier: MemoryTier, target_tier: MemoryTier
) -> ValidationResult:
    """Validate a tier transition is allowed.

    Checks:
    - current_tier is valid
    - target_tier is valid
    - transition is in the allowed set
    """
    errors: List[str] = []

    if not isinstance(current_tier, MemoryTier):
        errors.append(f"current_tier must be a valid MemoryTier, got {current_tier!r}")

    if not isinstance(target_tier, MemoryTier):
        errors.append(f"target_tier must be a valid MemoryTier, got {target_tier!r}")

    if current_tier == target_tier:
        return ValidationResult.ok()

    allowed_targets = _PROMOTION_TRANSITIONS.get(current_tier, [])
    if target_tier not in allowed_targets:
        errors.append(
            f"Transition from {current_tier.value!r} to {target_tier.value!r} is not allowed. "
            f"Allowed targets: {[t.value for t in allowed_targets]}"
        )

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


# =====================================================================
# Knowledge Graph Node and Relation Validators
# =====================================================================


def validate_graph_node(node: MemoryNodeDTO) -> ValidationResult:
    """Validate Knowledge Graph Node against standard enum types.

    Checks:
    - node.id is not nil
    - node.name is non-empty
    - node.type matches KGNodeType enum value
    """
    errors: List[str] = []

    if node.id == UUID(int=0):
        errors.append("node_id must not be nil UUID")

    if not node.name or not node.name.strip():
        errors.append("node name must be non-empty")

    valid_types = {t.value for t in KGNodeType}
    if node.type not in valid_types:
        errors.append(
            f"node type must be a valid KGNodeType, got {node.type!r}. "
            f"Allowed types: {sorted(list(valid_types))}"
        )

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)


def validate_graph_relation(relation: MemoryRelationDTO) -> ValidationResult:
    """Validate Knowledge Graph Edge/Relation against standard enum types.

    Checks:
    - relation.id is not nil
    - relation.source_node_id is not nil
    - relation.target_node_id is not nil
    - relation.relation_type matches KGEdgeType enum value
    """
    errors: List[str] = []

    if relation.id == UUID(int=0):
        errors.append("relation_id must not be nil UUID")

    if relation.source_node_id == UUID(int=0):
        errors.append("source_node_id must not be nil UUID")

    if relation.target_node_id == UUID(int=0):
        errors.append("target_node_id must not be nil UUID")

    valid_relations = {e.value for e in KGEdgeType}
    if relation.relation_type not in valid_relations:
        errors.append(
            f"relation_type must be a valid KGEdgeType, got {relation.relation_type!r}. "
            f"Allowed relation types: {sorted(list(valid_relations))}"
        )

    return ValidationResult.ok() if not errors else ValidationResult.fail(*errors)
