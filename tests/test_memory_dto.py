"""JARVIS OS - Phase 19 M0 DTO Tests.

Tests for the Memory DTO Layer. Verifies:
- All DTOs can be instantiated with defaults
- Validation constraints work (ge, le, required fields)
- Frozen enums have correct values
- Immutability where enforced
- No IO, no business logic

PHASE: 19
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from core.memory.dto import (
    ArchiveRequest,
    ArchiveResponse,
    ExecutionOutcome,
    ForgetRequest,
    ForgetResponse,
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
    PromotionResponse,
    RecallMetadata,
    ReflectionRequest,
    ReflectionResponse,
    RetrievalRequest,
    RetrievalResponse,
    StoreRequest,
    StoreResponse,
)

# =====================================================================
# Frozen Enum Tests
# =====================================================================


class TestFrozenEnums:
    """Verify frozen enums have correct values."""

    def test_memory_type_values(self) -> None:
        assert MemoryType.FACT.value == "fact"
        assert MemoryType.PREFERENCE.value == "preference"
        assert MemoryType.TASK.value == "task"
        assert MemoryType.GOAL.value == "goal"
        assert MemoryType.EVENT.value == "event"
        assert MemoryType.CONVERSATION.value == "conversation"
        assert MemoryType.RELATIONSHIP.value == "relationship"
        assert MemoryType.SYSTEM.value == "system"
        assert MemoryType.EPHEMERAL.value == "ephemeral"
        assert len(MemoryType) == 9

    def test_memory_visibility_values(self) -> None:
        assert MemoryVisibility.PRIVATE.value == "private"
        assert MemoryVisibility.USER.value == "user"
        assert MemoryVisibility.SYSTEM.value == "system"
        assert MemoryVisibility.AGENT.value == "agent"
        assert MemoryVisibility.PUBLIC.value == "public"
        assert len(MemoryVisibility) == 5

    def test_memory_trust_level_values(self) -> None:
        assert MemoryTrustLevel.SYSTEM.value == "system"
        assert MemoryTrustLevel.USER_EXPLICIT.value == "user_explicit"
        assert MemoryTrustLevel.USER_IMPLICIT.value == "user_implicit"
        assert MemoryTrustLevel.LEARNED.value == "learned"
        assert MemoryTrustLevel.INFERRED.value == "inferred"
        assert len(MemoryTrustLevel) == 5

    def test_memory_tier_values(self) -> None:
        assert MemoryTier.IDENTITY.value == "identity"
        assert MemoryTier.WORKING.value == "working"
        assert MemoryTier.CONVERSATION.value == "conversation"
        assert MemoryTier.LONG_TERM.value == "long_term"
        assert MemoryTier.ARCHIVED.value == "archived"
        assert len(MemoryTier) == 5

    def test_execution_outcome_values(self) -> None:
        assert ExecutionOutcome.SUCCESS.value == "success"
        assert ExecutionOutcome.FAILURE.value == "failure"
        assert ExecutionOutcome.PARTIAL.value == "partial"
        assert ExecutionOutcome.TIMEOUT.value == "timeout"
        assert len(ExecutionOutcome) == 4

    def test_kg_node_type_values(self) -> None:
        assert KGNodeType.PERSON.value == "Person"
        assert KGNodeType.ORGANIZATION.value == "Organization"
        assert KGNodeType.LOCATION.value == "Location"
        assert KGNodeType.CONCEPT.value == "Concept"
        assert KGNodeType.EVENT.value == "Event"
        assert KGNodeType.TASK.value == "Task"
        assert KGNodeType.GOAL.value == "Goal"
        assert KGNodeType.SKILL.value == "Skill"
        assert len(KGNodeType) == 8

    def test_kg_edge_type_values(self) -> None:
        assert KGEdgeType.KNOWS.value == "knows"
        assert KGEdgeType.WORKS_ON.value == "works_on"
        assert KGEdgeType.DEPENDS_ON.value == "depends_on"
        assert KGEdgeType.OWNS.value == "owns"
        assert KGEdgeType.RELATED_TO.value == "related_to"
        assert KGEdgeType.CAUSED_BY.value == "caused_by"
        assert KGEdgeType.USES.value == "uses"
        assert len(KGEdgeType) == 7


# =====================================================================
# Identity Contract Tests (§16.1)
# =====================================================================


class TestMemoryIdentity:
    """Verify MemoryIdentity contract fields."""

    def test_instantiation_with_defaults(self) -> None:
        identity = MemoryIdentity(
            owner_id=uuid4(),
            created_by="test_agent",
            memory_type=MemoryType.FACT,
            visibility=MemoryVisibility.PRIVATE,
            trust_level=MemoryTrustLevel.USER_IMPLICIT,
            confidence=0.9,
        )
        assert identity.memory_id is not None
        assert identity.created_at is not None
        assert identity.version == 1
        assert identity.session_id is None
        assert identity.conversation_id is None

    def test_confidence_bounds(self) -> None:
        identity = MemoryIdentity(
            owner_id=uuid4(),
            created_by="test",
            memory_type=MemoryType.FACT,
            visibility=MemoryVisibility.PRIVATE,
            trust_level=MemoryTrustLevel.SYSTEM,
            confidence=1.0,
        )
        assert identity.confidence == 1.0

        with pytest.raises(Exception):
            MemoryIdentity(
                owner_id=uuid4(),
                created_by="test",
                memory_type=MemoryType.FACT,
                visibility=MemoryVisibility.PRIVATE,
                trust_level=MemoryTrustLevel.SYSTEM,
                confidence=1.5,
            )

    def test_version_must_be_positive(self) -> None:
        with pytest.raises(Exception):
            MemoryIdentity(
                owner_id=uuid4(),
                created_by="test",
                memory_type=MemoryType.FACT,
                visibility=MemoryVisibility.PRIVATE,
                trust_level=MemoryTrustLevel.SYSTEM,
                confidence=0.5,
                version=0,
            )


# =====================================================================
# Provenance Contract Tests (§16.2)
# =====================================================================


class TestMemoryProvenance:
    """Verify MemoryProvenance contract fields."""

    def test_instantiation(self) -> None:
        provenance = MemoryProvenance(
            origin="user_input",
            created_by="test_agent",
        )
        assert provenance.origin == "user_input"
        assert provenance.created_by == "test_agent"
        assert provenance.derived_from is None
        assert provenance.reflection_id is None

    def test_with_derived_from(self) -> None:
        parent_id = uuid4()
        provenance = MemoryProvenance(
            origin="reflection",
            created_by="test_agent",
            derived_from=[parent_id],
        )
        assert provenance.derived_from == [parent_id]


# =====================================================================
# MemoryRecord Tests (§16.9)
# =====================================================================


class TestMemoryRecord:
    """Verify canonical MemoryRecord contract."""

    def test_instantiation_with_required_fields(self) -> None:
        provenance = MemoryProvenance(
            origin="test",
            created_by="test_agent",
        )
        record = MemoryRecord(
            memory_type=MemoryType.FACT,
            owner_id=uuid4(),
            visibility=MemoryVisibility.PRIVATE,
            trust_level=MemoryTrustLevel.USER_IMPLICIT,
            confidence=0.9,
            provenance=provenance,
            content="test content",
            content_hash="abc123",
        )
        assert record.memory_id is not None
        assert record.content == "test content"
        assert record.version == 1
        assert record.embedding_id is None
        assert record.graph_node_id is None

    def test_default_metadata(self) -> None:
        provenance = MemoryProvenance(
            origin="test",
            created_by="test_agent",
        )
        record = MemoryRecord(
            memory_type=MemoryType.FACT,
            owner_id=uuid4(),
            visibility=MemoryVisibility.PRIVATE,
            trust_level=MemoryTrustLevel.SYSTEM,
            confidence=1.0,
            provenance=provenance,
            content="test",
            content_hash="hash",
        )
        assert record.metadata.importance == 0.5
        assert record.metadata.token_count == 0

    def test_importance_bounds(self) -> None:
        provenance = MemoryProvenance(
            origin="test",
            created_by="test_agent",
        )
        with pytest.raises(Exception):
            MemoryRecord(
                memory_type=MemoryType.FACT,
                owner_id=uuid4(),
                visibility=MemoryVisibility.PRIVATE,
                trust_level=MemoryTrustLevel.SYSTEM,
                confidence=1.0,
                importance=1.5,
                provenance=provenance,
                content="test",
                content_hash="hash",
            )


# =====================================================================
# MemoryScore Tests (§3.1)
# =====================================================================


class TestMemoryScore:
    """Verify MemoryScore contract."""

    def test_instantiation(self) -> None:
        score = MemoryScore(
            memory_id=uuid4(),
            recency=0.8,
            semantic_similarity=0.7,
            confidence=0.9,
            importance=0.5,
            frequency=0.3,
            trust=0.6,
            user_pin=0.0,
            final_score=3.8,
            tier=MemoryTier.LONG_TERM,
        )
        assert score.memory_id is not None
        assert score.final_score == 3.8
        assert score.user_pin == 0.0

    def test_score_bounds(self) -> None:
        with pytest.raises(Exception):
            MemoryScore(
                memory_id=uuid4(),
                recency=1.5,
                semantic_similarity=0.5,
                confidence=0.5,
                importance=0.5,
                frequency=0.5,
                trust=0.5,
                final_score=3.5,
                tier=MemoryTier.LONG_TERM,
            )

    def test_final_score_can_exceed_one(self) -> None:
        score = MemoryScore(
            memory_id=uuid4(),
            recency=1.0,
            semantic_similarity=1.0,
            confidence=1.0,
            importance=1.0,
            frequency=1.0,
            trust=1.0,
            user_pin=1.0,
            final_score=7.0,
            tier=MemoryTier.LONG_TERM,
        )
        assert score.final_score == 7.0


# =====================================================================
# Retrieval DTOs Tests
# =====================================================================


class TestRetrievalDTOs:
    """Verify retrieval request/response DTOs."""

    def test_retrieval_request_defaults(self) -> None:
        request = RetrievalRequest(query="test query")
        assert request.query == "test query"
        assert request.max_chunks == 50
        assert request.max_tokens == 2000
        assert request.min_score == 0.0
        assert request.tier_filter is None
        assert request.graph_depth == 0
        assert request.include_archived is False

    def test_retrieval_response_defaults(self) -> None:
        response = RetrievalResponse()
        assert response.chunks == []
        assert response.scores == []
        assert response.total_tokens == 0

    def test_recall_metadata_defaults(self) -> None:
        metadata = RecallMetadata()
        assert metadata.query_time_ms == 0.0
        assert metadata.chunks_searched == 0
        assert metadata.tiers_hit == []


# =====================================================================
# Reflection DTOs Tests
# =====================================================================


class TestReflectionDTOs:
    """Verify reflection request/response DTOs."""

    def test_reflection_request(self) -> None:
        request = ReflectionRequest(
            memory_id=uuid4(),
            outcome=ExecutionOutcome.SUCCESS,
            confidence_delta=0.1,
        )
        assert request.confidence_delta == 0.1
        assert request.notes is None

    def test_reflection_response(self) -> None:
        response = ReflectionResponse(
            memory_id=uuid4(),
            old_confidence=0.7,
            new_confidence=0.8,
            applied=True,
        )
        assert response.applied is True

    def test_confidence_delta_bounds(self) -> None:
        with pytest.raises(Exception):
            ReflectionRequest(
                memory_id=uuid4(),
                outcome=ExecutionOutcome.SUCCESS,
                confidence_delta=1.5,
            )


# =====================================================================
# Promotion DTOs Tests
# =====================================================================


class TestPromotionDTOs:
    """Verify promotion request/response DTOs."""

    def test_promotion_request(self) -> None:
        request = PromotionRequest(
            memory_id=uuid4(),
            target_tier=MemoryTier.LONG_TERM,
        )
        assert request.target_tier == MemoryTier.LONG_TERM
        assert request.reason is None

    def test_promotion_response(self) -> None:
        response = PromotionResponse(
            memory_id=uuid4(),
            old_tier=MemoryTier.WORKING,
            new_tier=MemoryTier.CONVERSATION,
            promoted=True,
        )
        assert response.promoted is True


# =====================================================================
# Archive/Forget DTOs Tests
# =====================================================================


class TestArchiveForgetDTOs:
    """Verify archive and forget DTOs."""

    def test_archive_request(self) -> None:
        request = ArchiveRequest(
            memory_id=uuid4(),
            reason="TTL expired",
        )
        assert request.reason == "TTL expired"

    def test_archive_response(self) -> None:
        response = ArchiveResponse(
            memory_id=uuid4(),
            archived=True,
            archived_at=datetime.now(timezone.utc),
        )
        assert response.archived is True

    def test_forget_request(self) -> None:
        request = ForgetRequest(
            memory_id=uuid4(),
            reason="User request",
            cascade=True,
        )
        assert request.cascade is True

    def test_forget_response(self) -> None:
        response = ForgetResponse(
            memory_id=uuid4(),
            forgotten=True,
            cascade_count=3,
        )
        assert response.forgotten is True
        assert response.cascade_count == 3


# =====================================================================
# Store DTOs Tests
# =====================================================================


class TestStoreDTOs:
    """Verify store request/response DTOs."""

    def test_store_request_defaults(self) -> None:
        request = StoreRequest(
            content="test content",
            source_type="user_input",
            owner_id=uuid4(),
        )
        assert request.content == "test content"
        assert request.memory_type == MemoryType.FACT
        assert request.visibility == MemoryVisibility.PRIVATE
        assert request.trust_level == MemoryTrustLevel.USER_IMPLICIT
        assert request.importance == 0.5
        assert request.confidence == 1.0

    def test_store_response(self) -> None:
        response = StoreResponse(
            memory_id=uuid4(),
            tier=MemoryTier.WORKING,
        )
        assert response.tier == MemoryTier.WORKING
        assert response.score is None


# =====================================================================
# MemoryMetadata Tests
# =====================================================================


class TestMemoryMetadata:
    """Verify MemoryMetadata fields."""

    def test_defaults(self) -> None:
        metadata = MemoryMetadata()
        assert metadata.importance == 0.5
        assert metadata.token_count == 0
        assert metadata.embedding_id is None
        assert metadata.graph_node_id is None
        assert metadata.extra == {}

    def test_importance_bounds(self) -> None:
        with pytest.raises(Exception):
            MemoryMetadata(importance=1.5)

    def test_token_count_must_be_non_negative(self) -> None:
        with pytest.raises(Exception):
            MemoryMetadata(token_count=-1)


# =====================================================================
# Serialization Tests
# =====================================================================


class TestSerialization:
    """Verify DTOs can be serialized/deserialized."""

    def test_memory_record_roundtrip(self) -> None:
        provenance = MemoryProvenance(
            origin="test",
            created_by="test_agent",
        )
        record = MemoryRecord(
            memory_type=MemoryType.FACT,
            owner_id=uuid4(),
            visibility=MemoryVisibility.PRIVATE,
            trust_level=MemoryTrustLevel.USER_IMPLICIT,
            confidence=0.9,
            provenance=provenance,
            content="test content",
            content_hash="abc123",
        )
        data = record.model_dump()
        restored = MemoryRecord.model_validate(data)
        assert restored.memory_id == record.memory_id
        assert restored.content == record.content

    def test_retrieval_request_roundtrip(self) -> None:
        request = RetrievalRequest(
            query="test",
            max_chunks=10,
            tier_filter=[MemoryTier.WORKING, MemoryTier.CONVERSATION],
        )
        data = request.model_dump()
        restored = RetrievalRequest.model_validate(data)
        assert restored.query == "test"
        assert restored.tier_filter == [MemoryTier.WORKING, MemoryTier.CONVERSATION]

    def test_memory_score_roundtrip(self) -> None:
        score = MemoryScore(
            memory_id=uuid4(),
            recency=0.8,
            semantic_similarity=0.7,
            confidence=0.9,
            importance=0.5,
            frequency=0.3,
            trust=0.6,
            final_score=3.8,
            tier=MemoryTier.LONG_TERM,
        )
        data = score.model_dump()
        restored = MemoryScore.model_validate(data)
        assert restored.final_score == 3.8
        assert restored.tier == MemoryTier.LONG_TERM
