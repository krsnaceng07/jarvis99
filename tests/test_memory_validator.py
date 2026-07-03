"""JARVIS OS - Phase 19 M1 Validator Tests.

Tests for the Memory Validator. Verifies:
- All validators accept valid inputs
- All validators reject invalid inputs
- No side effects (pure validation)
- Error messages are descriptive

PHASE: 19
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

from uuid import UUID, uuid4

from core.memory.dto import (
    ArchiveRequest,
    ExecutionOutcome,
    ForgetRequest,
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
from core.memory.validator import (
    ValidationResult,
    validate_archive_request,
    validate_forget_request,
    validate_identity,
    validate_metadata,
    validate_promotion_request,
    validate_provenance,
    validate_record,
    validate_reflection_request,
    validate_retrieval_request,
    validate_score,
    validate_store_request,
    validate_tier_transition,
)

NIL_UUID = UUID(int=0)


# =====================================================================
# Helpers
# =====================================================================


def _valid_identity() -> MemoryIdentity:
    return MemoryIdentity(
        owner_id=uuid4(),
        created_by="test_agent",
        memory_type=MemoryType.FACT,
        visibility=MemoryVisibility.PRIVATE,
        trust_level=MemoryTrustLevel.USER_IMPLICIT,
        confidence=0.9,
    )


def _valid_provenance() -> MemoryProvenance:
    return MemoryProvenance(
        origin="user_input",
        created_by="test_agent",
    )


def _valid_metadata() -> MemoryMetadata:
    return MemoryMetadata(importance=0.5, token_count=100)


def _valid_record() -> MemoryRecord:
    return MemoryRecord(
        memory_type=MemoryType.FACT,
        owner_id=uuid4(),
        visibility=MemoryVisibility.PRIVATE,
        trust_level=MemoryTrustLevel.USER_IMPLICIT,
        confidence=0.9,
        provenance=_valid_provenance(),
        content="test content",
        content_hash="abc123",
    )


def _valid_score() -> MemoryScore:
    return MemoryScore(
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


def _valid_store_request() -> StoreRequest:
    return StoreRequest(
        content="test content",
        source_type="user_input",
        owner_id=uuid4(),
    )


def _valid_retrieval_request() -> RetrievalRequest:
    return RetrievalRequest(query="test query")


def _valid_reflection_request() -> ReflectionRequest:
    return ReflectionRequest(
        memory_id=uuid4(),
        outcome=ExecutionOutcome.SUCCESS,
        confidence_delta=0.1,
    )


def _valid_promotion_request() -> PromotionRequest:
    return PromotionRequest(
        memory_id=uuid4(),
        target_tier=MemoryTier.CONVERSATION,
    )


def _valid_archive_request() -> ArchiveRequest:
    return ArchiveRequest(
        memory_id=uuid4(),
        reason="TTL expired",
    )


def _valid_forget_request() -> ForgetRequest:
    return ForgetRequest(
        memory_id=uuid4(),
        reason="User request",
    )


# =====================================================================
# ValidationResult Tests
# =====================================================================


class TestValidationResult:
    """Verify ValidationResult dataclass."""

    def test_ok(self) -> None:
        result = ValidationResult.ok()
        assert result.valid is True
        assert result.errors == []

    def test_fail(self) -> None:
        result = ValidationResult.fail("error 1", "error 2")
        assert result.valid is False
        assert result.errors == ["error 1", "error 2"]


# =====================================================================
# Identity Validator Tests
# =====================================================================


class TestValidateIdentity:
    """Verify validate_identity accepts valid and rejects invalid."""

    def test_valid_identity(self) -> None:
        result = validate_identity(_valid_identity())
        assert result.valid is True

    def test_nil_memory_id(self) -> None:
        identity = _valid_identity()
        identity.memory_id = NIL_UUID
        result = validate_identity(identity)
        assert result.valid is False
        assert any("memory_id" in e for e in result.errors)

    def test_nil_owner_id(self) -> None:
        identity = _valid_identity()
        identity.owner_id = NIL_UUID
        result = validate_identity(identity)
        assert result.valid is False
        assert any("owner_id" in e for e in result.errors)

    def test_empty_created_by(self) -> None:
        identity = _valid_identity()
        identity.created_by = ""
        result = validate_identity(identity)
        assert result.valid is False
        assert any("created_by" in e for e in result.errors)

    def test_whitespace_created_by(self) -> None:
        identity = _valid_identity()
        identity.created_by = "   "
        result = validate_identity(identity)
        assert result.valid is False

    def test_invalid_memory_type(self) -> None:
        identity = _valid_identity()
        identity.memory_type = "invalid"  # type: ignore[assignment]
        result = validate_identity(identity)
        assert result.valid is False
        assert any("memory_type" in e for e in result.errors)

    def test_invalid_visibility(self) -> None:
        identity = _valid_identity()
        identity.visibility = "invalid"  # type: ignore[assignment]
        result = validate_identity(identity)
        assert result.valid is False
        assert any("visibility" in e for e in result.errors)

    def test_invalid_trust_level(self) -> None:
        identity = _valid_identity()
        identity.trust_level = "invalid"  # type: ignore[assignment]
        result = validate_identity(identity)
        assert result.valid is False
        assert any("trust_level" in e for e in result.errors)

    def test_version_zero(self) -> None:
        identity = _valid_identity()
        identity.version = 0
        result = validate_identity(identity)
        assert result.valid is False
        assert any("version" in e for e in result.errors)

    def test_multiple_errors(self) -> None:
        identity = _valid_identity()
        identity.created_by = ""
        identity.memory_id = NIL_UUID
        result = validate_identity(identity)
        assert result.valid is False
        assert len(result.errors) >= 2


# =====================================================================
# Provenance Validator Tests
# =====================================================================


class TestValidateProvenance:
    """Verify validate_provenance accepts valid and rejects invalid."""

    def test_valid_provenance(self) -> None:
        result = validate_provenance(_valid_provenance())
        assert result.valid is True

    def test_empty_origin(self) -> None:
        provenance = _valid_provenance()
        provenance.origin = ""
        result = validate_provenance(provenance)
        assert result.valid is False
        assert any("origin" in e for e in result.errors)

    def test_empty_created_by(self) -> None:
        provenance = _valid_provenance()
        provenance.created_by = ""
        result = validate_provenance(provenance)
        assert result.valid is False
        assert any("created_by" in e for e in result.errors)

    def test_nil_derived_from(self) -> None:
        provenance = MemoryProvenance(
            origin="test",
            created_by="agent",
            derived_from=[NIL_UUID],
        )
        result = validate_provenance(provenance)
        assert result.valid is False
        assert any("derived_from" in e for e in result.errors)


# =====================================================================
# Metadata Validator Tests
# =====================================================================


class TestValidateMetadata:
    """Verify validate_metadata accepts valid and rejects invalid."""

    def test_valid_metadata(self) -> None:
        result = validate_metadata(_valid_metadata())
        assert result.valid is True

    def test_boundary_importance_0(self) -> None:
        metadata = MemoryMetadata(importance=0.0)
        result = validate_metadata(metadata)
        assert result.valid is True

    def test_boundary_importance_1(self) -> None:
        metadata = MemoryMetadata(importance=1.0)
        result = validate_metadata(metadata)
        assert result.valid is True

    def test_boundary_token_count_0(self) -> None:
        metadata = MemoryMetadata(token_count=0)
        result = validate_metadata(metadata)
        assert result.valid is True


# =====================================================================
# Record Validator Tests
# =====================================================================


class TestValidateRecord:
    """Verify validate_record accepts valid and rejects invalid."""

    def test_valid_record(self) -> None:
        result = validate_record(_valid_record())
        assert result.valid is True

    def test_wrong_schema_version(self) -> None:
        record = _valid_record()
        record.schema_version = "2.0"  # type: ignore[assignment]
        result = validate_record(record)
        assert result.valid is False
        assert any("schema_version" in e for e in result.errors)

    def test_empty_content(self) -> None:
        record = _valid_record()
        record.content = ""
        result = validate_record(record)
        assert result.valid is False
        assert any("content" in e for e in result.errors)

    def test_empty_content_hash(self) -> None:
        record = _valid_record()
        record.content_hash = ""
        result = validate_record(record)
        assert result.valid is False
        assert any("content_hash" in e for e in result.errors)

    def test_invalid_provenance(self) -> None:
        record = _valid_record()
        record.provenance = MemoryProvenance(origin="", created_by="")
        result = validate_record(record)
        assert result.valid is False
        assert len(result.errors) >= 2

    def test_nil_memory_id(self) -> None:
        record = _valid_record()
        record.memory_id = NIL_UUID
        result = validate_record(record)
        assert result.valid is False
        assert any("memory_id" in e for e in result.errors)

    def test_nil_owner_id(self) -> None:
        record = _valid_record()
        record.owner_id = NIL_UUID
        result = validate_record(record)
        assert result.valid is False
        assert any("owner_id" in e for e in result.errors)


# =====================================================================
# Score Validator Tests
# =====================================================================


class TestValidateScore:
    """Verify validate_score accepts valid and rejects invalid."""

    def test_valid_score(self) -> None:
        result = validate_score(_valid_score())
        assert result.valid is True

    def test_final_score_can_exceed_one(self) -> None:
        score = _valid_score()
        score.final_score = 7.0
        result = validate_score(score)
        assert result.valid is True

    def test_nil_memory_id(self) -> None:
        score = _valid_score()
        score.memory_id = NIL_UUID
        result = validate_score(score)
        assert result.valid is False
        assert any("memory_id" in e for e in result.errors)

    def test_invalid_tier(self) -> None:
        score = _valid_score()
        score.tier = "invalid"  # type: ignore[assignment]
        result = validate_score(score)
        assert result.valid is False
        assert any("tier" in e for e in result.errors)

    def test_wrong_schema_version(self) -> None:
        score = _valid_score()
        score.schema_version = "2.0"  # type: ignore[assignment]
        result = validate_score(score)
        assert result.valid is False
        assert any("schema_version" in e for e in result.errors)


# =====================================================================
# Store Request Validator Tests
# =====================================================================


class TestValidateStoreRequest:
    """Verify validate_store_request accepts valid and rejects invalid."""

    def test_valid_store_request(self) -> None:
        result = validate_store_request(_valid_store_request())
        assert result.valid is True

    def test_empty_content(self) -> None:
        request = _valid_store_request()
        request.content = ""
        result = validate_store_request(request)
        assert result.valid is False
        assert any("content" in e for e in result.errors)

    def test_empty_source_type(self) -> None:
        request = _valid_store_request()
        request.source_type = ""
        result = validate_store_request(request)
        assert result.valid is False
        assert any("source_type" in e for e in result.errors)

    def test_nil_owner_id(self) -> None:
        request = _valid_store_request()
        request.owner_id = NIL_UUID
        result = validate_store_request(request)
        assert result.valid is False
        assert any("owner_id" in e for e in result.errors)

    def test_wrong_schema_version(self) -> None:
        request = _valid_store_request()
        request.schema_version = "2.0"  # type: ignore[assignment]
        result = validate_store_request(request)
        assert result.valid is False
        assert any("schema_version" in e for e in result.errors)


# =====================================================================
# Retrieval Request Validator Tests
# =====================================================================


class TestValidateRetrievalRequest:
    """Verify validate_retrieval_request accepts valid and rejects invalid."""

    def test_valid_retrieval_request(self) -> None:
        result = validate_retrieval_request(_valid_retrieval_request())
        assert result.valid is True

    def test_empty_query(self) -> None:
        request = RetrievalRequest(query="")
        result = validate_retrieval_request(request)
        assert result.valid is False
        assert any("query" in e for e in result.errors)

    def test_whitespace_query(self) -> None:
        request = RetrievalRequest(query="   ")
        result = validate_retrieval_request(request)
        assert result.valid is False

    def test_valid_tier_filter(self) -> None:
        request = RetrievalRequest(
            query="test",
            tier_filter=[MemoryTier.WORKING, MemoryTier.CONVERSATION],
        )
        result = validate_retrieval_request(request)
        assert result.valid is True

    def test_wrong_schema_version(self) -> None:
        request = _valid_retrieval_request()
        request.schema_version = "2.0"  # type: ignore[assignment]
        result = validate_retrieval_request(request)
        assert result.valid is False
        assert any("schema_version" in e for e in result.errors)


# =====================================================================
# Reflection Request Validator Tests
# =====================================================================


class TestValidateReflectionRequest:
    """Verify validate_reflection_request accepts valid and rejects invalid."""

    def test_valid_reflection_request(self) -> None:
        result = validate_reflection_request(_valid_reflection_request())
        assert result.valid is True

    def test_nil_memory_id(self) -> None:
        request = _valid_reflection_request()
        request.memory_id = NIL_UUID
        result = validate_reflection_request(request)
        assert result.valid is False
        assert any("memory_id" in e for e in result.errors)

    def test_boundary_delta_1(self) -> None:
        request = ReflectionRequest(
            memory_id=uuid4(),
            outcome=ExecutionOutcome.SUCCESS,
            confidence_delta=1.0,
        )
        result = validate_reflection_request(request)
        assert result.valid is True

    def test_boundary_delta_neg1(self) -> None:
        request = ReflectionRequest(
            memory_id=uuid4(),
            outcome=ExecutionOutcome.FAILURE,
            confidence_delta=-1.0,
        )
        result = validate_reflection_request(request)
        assert result.valid is True

    def test_wrong_schema_version(self) -> None:
        request = _valid_reflection_request()
        request.schema_version = "2.0"  # type: ignore[assignment]
        result = validate_reflection_request(request)
        assert result.valid is False
        assert any("schema_version" in e for e in result.errors)


# =====================================================================
# Promotion Request Validator Tests
# =====================================================================


class TestValidatePromotionRequest:
    """Verify validate_promotion_request accepts valid and rejects invalid."""

    def test_valid_promotion_request(self) -> None:
        result = validate_promotion_request(_valid_promotion_request())
        assert result.valid is True

    def test_nil_memory_id(self) -> None:
        request = _valid_promotion_request()
        request.memory_id = NIL_UUID
        result = validate_promotion_request(request)
        assert result.valid is False
        assert any("memory_id" in e for e in result.errors)

    def test_identity_not_promotable(self) -> None:
        request = PromotionRequest(
            memory_id=uuid4(),
            target_tier=MemoryTier.IDENTITY,
        )
        result = validate_promotion_request(request)
        assert result.valid is False
        assert any("IDENTITY" in e for e in result.errors)

    def test_archived_not_promotable(self) -> None:
        request = PromotionRequest(
            memory_id=uuid4(),
            target_tier=MemoryTier.ARCHIVED,
        )
        result = validate_promotion_request(request)
        assert result.valid is False
        assert any("ARCHIVED" in e for e in result.errors)

    def test_working_promotable(self) -> None:
        request = PromotionRequest(
            memory_id=uuid4(),
            target_tier=MemoryTier.WORKING,
        )
        result = validate_promotion_request(request)
        assert result.valid is True

    def test_long_term_promotable(self) -> None:
        request = PromotionRequest(
            memory_id=uuid4(),
            target_tier=MemoryTier.LONG_TERM,
        )
        result = validate_promotion_request(request)
        assert result.valid is True


# =====================================================================
# Archive Request Validator Tests
# =====================================================================


class TestValidateArchiveRequest:
    """Verify validate_archive_request accepts valid and rejects invalid."""

    def test_valid_archive_request(self) -> None:
        result = validate_archive_request(_valid_archive_request())
        assert result.valid is True

    def test_nil_memory_id(self) -> None:
        request = _valid_archive_request()
        request.memory_id = NIL_UUID
        result = validate_archive_request(request)
        assert result.valid is False
        assert any("memory_id" in e for e in result.errors)

    def test_empty_reason(self) -> None:
        request = _valid_archive_request()
        request.reason = ""
        result = validate_archive_request(request)
        assert result.valid is False
        assert any("reason" in e for e in result.errors)

    def test_wrong_schema_version(self) -> None:
        request = _valid_archive_request()
        request.schema_version = "2.0"  # type: ignore[assignment]
        result = validate_archive_request(request)
        assert result.valid is False
        assert any("schema_version" in e for e in result.errors)


# =====================================================================
# Forget Request Validator Tests
# =====================================================================


class TestValidateForgetRequest:
    """Verify validate_forget_request accepts valid and rejects invalid."""

    def test_valid_forget_request(self) -> None:
        result = validate_forget_request(_valid_forget_request())
        assert result.valid is True

    def test_nil_memory_id(self) -> None:
        request = _valid_forget_request()
        request.memory_id = NIL_UUID
        result = validate_forget_request(request)
        assert result.valid is False
        assert any("memory_id" in e for e in result.errors)

    def test_empty_reason(self) -> None:
        request = _valid_forget_request()
        request.reason = ""
        result = validate_forget_request(request)
        assert result.valid is False
        assert any("reason" in e for e in result.errors)

    def test_wrong_schema_version(self) -> None:
        request = _valid_forget_request()
        request.schema_version = "2.0"  # type: ignore[assignment]
        result = validate_forget_request(request)
        assert result.valid is False
        assert any("schema_version" in e for e in result.errors)


# =====================================================================
# Tier Transition Validator Tests
# =====================================================================


class TestValidateTierTransition:
    """Verify validate_tier_transition accepts valid and rejects invalid."""

    def test_working_to_conversation(self) -> None:
        result = validate_tier_transition(MemoryTier.WORKING, MemoryTier.CONVERSATION)
        assert result.valid is True

    def test_conversation_to_long_term(self) -> None:
        result = validate_tier_transition(MemoryTier.CONVERSATION, MemoryTier.LONG_TERM)
        assert result.valid is True

    def test_long_term_to_archived(self) -> None:
        result = validate_tier_transition(MemoryTier.LONG_TERM, MemoryTier.ARCHIVED)
        assert result.valid is True

    def test_same_tier(self) -> None:
        result = validate_tier_transition(MemoryTier.WORKING, MemoryTier.WORKING)
        assert result.valid is True

    def test_working_to_long_term_invalid(self) -> None:
        result = validate_tier_transition(MemoryTier.WORKING, MemoryTier.LONG_TERM)
        assert result.valid is False
        assert any("not allowed" in e.lower() for e in result.errors)

    def test_archived_to_working_invalid(self) -> None:
        result = validate_tier_transition(MemoryTier.ARCHIVED, MemoryTier.WORKING)
        assert result.valid is False

    def test_identity_to_any_invalid(self) -> None:
        result = validate_tier_transition(MemoryTier.IDENTITY, MemoryTier.WORKING)
        assert result.valid is False

    def test_conversation_to_working_invalid(self) -> None:
        result = validate_tier_transition(MemoryTier.CONVERSATION, MemoryTier.WORKING)
        assert result.valid is False

    def test_long_term_to_conversation_invalid(self) -> None:
        result = validate_tier_transition(MemoryTier.LONG_TERM, MemoryTier.CONVERSATION)
        assert result.valid is False
