"""JARVIS OS - Phase 19 M8 Memory API Tests.

Tests for all 10 memory API DTOs (request/response validation) and
route handler logic via direct async calls (no HTTP server needed).

PHASE: 19
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from api.routes.memory import (
    MemoryActionResponse,
    MemoryArchiveRequest,
    MemoryForgetRequest,
    MemoryGetResponse,
    MemoryPromoteRequest,
    MemoryRecallRequest,
    MemoryRecallResponse,
    MemoryReflectRequest,
    MemoryScoreResponse,
    MemorySearchResponse,
    MemoryStatsResponse,
    MemoryStoreRequest,
    MemoryStoreResponse,
)
from core.memory.dto import MemoryTier


# =====================================================================
# MemoryStoreRequest Validation
# =====================================================================


class TestMemoryStoreRequest:
    def test_valid_request(self) -> None:
        req = MemoryStoreRequest(content="hello", source_type="test")
        assert req.content == "hello"
        assert req.source_type == "test"
        assert req.importance == 0.5
        assert req.confidence == 1.0
        assert req.metadata is None

    def test_with_metadata(self) -> None:
        req = MemoryStoreRequest(
            content="hello",
            source_type="web",
            metadata={"url": "https://example.com"},
            importance=0.9,
            confidence=0.8,
        )
        assert req.metadata == {"url": "https://example.com"}
        assert req.importance == 0.9

    def test_empty_content_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryStoreRequest(content="", source_type="test")

    def test_empty_source_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryStoreRequest(content="hello", source_type="")

    def test_importance_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            MemoryStoreRequest(content="x", source_type="t", importance=1.5)

    def test_confidence_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            MemoryStoreRequest(content="x", source_type="t", confidence=-0.1)


# =====================================================================
# MemoryRecallRequest Validation
# =====================================================================


class TestMemoryRecallRequest:
    def test_valid_request(self) -> None:
        req = MemoryRecallRequest(query="test query")
        assert req.query == "test query"
        assert req.max_chunks == 50
        assert req.min_score == 0.0

    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryRecallRequest(query="")

    def test_max_chunks_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MemoryRecallRequest(query="q", max_chunks=0)
        with pytest.raises(ValidationError):
            MemoryRecallRequest(query="q", max_chunks=501)

    def test_min_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MemoryRecallRequest(query="q", min_score=-0.1)
        with pytest.raises(ValidationError):
            MemoryRecallRequest(query="q", min_score=1.1)


# =====================================================================
# MemoryReflectRequest Validation
# =====================================================================


class TestMemoryReflectRequest:
    def test_valid_request(self) -> None:
        req = MemoryReflectRequest(outcome="success", confidence_delta=0.2)
        assert req.outcome == "success"
        assert req.confidence_delta == 0.2
        assert req.notes is None

    def test_with_notes(self) -> None:
        req = MemoryReflectRequest(
            outcome="failure", confidence_delta=-0.3, notes="wrong"
        )
        assert req.notes == "wrong"

    def test_delta_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            MemoryReflectRequest(outcome="success", confidence_delta=1.5)
        with pytest.raises(ValidationError):
            MemoryReflectRequest(outcome="success", confidence_delta=-1.5)


# =====================================================================
# MemoryForgetRequest Validation
# =====================================================================


class TestMemoryForgetRequest:
    def test_valid_request(self) -> None:
        req = MemoryForgetRequest(reason="outdated")
        assert req.reason == "outdated"
        assert req.cascade is False

    def test_with_cascade(self) -> None:
        req = MemoryForgetRequest(reason="cleanup", cascade=True)
        assert req.cascade is True

    def test_empty_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryForgetRequest(reason="")


# =====================================================================
# MemoryArchiveRequest Validation
# =====================================================================


class TestMemoryArchiveRequest:
    def test_valid_request(self) -> None:
        req = MemoryArchiveRequest(reason="old data")
        assert req.reason == "old data"

    def test_empty_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MemoryArchiveRequest(reason="")


# =====================================================================
# MemoryPromoteRequest Validation
# =====================================================================


class TestMemoryPromoteRequest:
    def test_valid_request(self) -> None:
        req = MemoryPromoteRequest(target_tier="conversation")
        assert req.target_tier == "conversation"

    def test_all_tier_values_accepted(self) -> None:
        for tier in MemoryTier:
            req = MemoryPromoteRequest(target_tier=tier.value)
            assert req.target_tier == tier.value


# =====================================================================
# Response DTOs
# =====================================================================


class TestResponseDTOs:
    def test_store_response(self) -> None:
        mid = uuid4()
        resp = MemoryStoreResponse(chunk_id=mid)
        assert resp.chunk_id == mid
        assert resp.api_version == "v1"

    def test_recall_response(self) -> None:
        resp = MemoryRecallResponse(
            chunks=[{"memory_id": "abc", "content": "hello"}],
            total_chunks=1,
        )
        assert resp.total_chunks == 1
        assert len(resp.chunks) == 1

    def test_get_response(self) -> None:
        mid = uuid4()
        resp = MemoryGetResponse(
            memory_id=mid,
            content="test",
            memory_type="fact",
            confidence=0.9,
            importance=0.5,
            tier="working",
            created_at="2026-07-01T00:00:00",
            updated_at="2026-07-01T00:00:00",
        )
        assert resp.memory_id == mid
        assert resp.tier == "working"

    def test_score_response(self) -> None:
        mid = uuid4()
        resp = MemoryScoreResponse(
            memory_id=mid,
            final_score=0.85,
            recency_score=0.9,
            importance_score=0.8,
            confidence_score=0.95,
            access_score=0.7,
        )
        assert resp.final_score == 0.85

    def test_action_response(self) -> None:
        mid = uuid4()
        resp = MemoryActionResponse(success=True, memory_id=mid, action="forget")
        assert resp.success is True
        assert resp.action == "forget"

    def test_stats_response(self) -> None:
        resp = MemoryStatsResponse(total_chunks=42)
        assert resp.total_chunks == 42
        assert resp.api_version == "v1"

    def test_search_response(self) -> None:
        resp = MemorySearchResponse(chunks=[], total_chunks=0)
        assert resp.total_chunks == 0


# =====================================================================
# Route Handler Tests (direct async calls with mock orchestrator)
# =====================================================================


class MockRequest:
    """Minimal mock for FastAPI Request."""

    class _State:
        request_id = None

    state = _State()


class MockOrchestrator:
    """Mock MemoryOrchestrator for testing route handlers."""

    def __init__(self) -> None:
        self.stored: list[dict[str, Any]] = []
        self.memory_repo = MockRepo()

    async def store(
        self,
        content: str,
        source_type: str,
        metadata: Optional[dict[str, Any]] = None,
        importance: float = 0.5,
        confidence: float = 1.0,
        session_id: Optional[UUID] = None,
    ) -> UUID:
        mid = uuid4()
        self.stored.append({"id": mid, "content": content})
        return mid

    async def recall(self, request: Any) -> Any:
        class R:
            chunks: list[Any] = []
        return R()

    async def reflect(self, request: Any) -> bool:
        return True

    async def forget(
        self, chunk_id: UUID, reason: str, cascade: bool = False
    ) -> bool:
        return True

    async def archive(self, chunk_id: UUID, reason: str) -> bool:
        return True

    async def promote(self, chunk_id: UUID, target_tier: Any) -> bool:
        return True

    async def score(self, chunk_id: UUID) -> Any:
        class S:
            final_score = 0.85
            recency_score = 0.9
            importance_score = 0.8
            confidence_score = 0.95
            access_score = 0.7
        return S()

    @staticmethod
    def _infer_tier(record: Any) -> Any:
        class T:
            value = "working"
        return T()


class MockRepo:
    """Mock memory repository."""

    async def get_by_id(self, memory_id: UUID) -> Any:
        return None

    async def list_records(self, **kwargs: Any) -> list[Any]:
        return []


class TestRouteHandlers:
    """Test route handlers via direct async invocation."""

    @pytest.mark.asyncio
    async def test_store_memory_handler(self) -> None:
        from api.routes.memory import store_memory

        body = MemoryStoreRequest(content="test content", source_type="test")
        orch = MockOrchestrator()
        result = await store_memory(body=body, request=MockRequest(), orchestrator=orch)
        assert result.status_code == 201
        assert len(orch.stored) == 1

    @pytest.mark.asyncio
    async def test_recall_memory_handler(self) -> None:
        from api.routes.memory import recall_memory

        body = MemoryRecallRequest(query="test")
        orch = MockOrchestrator()
        result = await recall_memory(
            body=body, request=MockRequest(), orchestrator=orch
        )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_get_memory_not_found(self) -> None:
        from api.routes.memory import get_memory

        orch = MockOrchestrator()
        result = await get_memory(
            memory_id=uuid4(), request=MockRequest(), orchestrator=orch
        )
        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_score_memory_not_found(self) -> None:
        from api.routes.memory import get_memory_score

        class RaisingOrch(MockOrchestrator):
            async def score(self, chunk_id: UUID) -> Any:
                raise ValueError("Memory not found")

        orch = RaisingOrch()
        result = await get_memory_score(
            memory_id=uuid4(), request=MockRequest(), orchestrator=orch
        )
        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_reflect_memory_handler(self) -> None:
        from api.routes.memory import reflect_memory

        body = MemoryReflectRequest(outcome="success", confidence_delta=0.1)
        orch = MockOrchestrator()
        result = await reflect_memory(
            memory_id=uuid4(), body=body, request=MockRequest(), orchestrator=orch
        )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_reflect_invalid_outcome(self) -> None:
        from api.routes.memory import reflect_memory

        body = MemoryReflectRequest(outcome="invalid_outcome", confidence_delta=0.1)
        orch = MockOrchestrator()
        result = await reflect_memory(
            memory_id=uuid4(), body=body, request=MockRequest(), orchestrator=orch
        )
        assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_forget_memory_handler(self) -> None:
        from api.routes.memory import forget_memory

        body = MemoryForgetRequest(reason="cleanup")
        orch = MockOrchestrator()
        result = await forget_memory(
            memory_id=uuid4(), body=body, request=MockRequest(), orchestrator=orch
        )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_archive_memory_handler(self) -> None:
        from api.routes.memory import archive_memory

        body = MemoryArchiveRequest(reason="old")
        orch = MockOrchestrator()
        result = await archive_memory(
            memory_id=uuid4(), body=body, request=MockRequest(), orchestrator=orch
        )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_promote_memory_handler(self) -> None:
        from api.routes.memory import promote_memory

        body = MemoryPromoteRequest(target_tier="conversation")
        orch = MockOrchestrator()
        result = await promote_memory(
            memory_id=uuid4(), body=body, request=MockRequest(), orchestrator=orch
        )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_promote_invalid_tier(self) -> None:
        from api.routes.memory import promote_memory

        body = MemoryPromoteRequest(target_tier="invalid_tier")
        orch = MockOrchestrator()
        result = await promote_memory(
            memory_id=uuid4(), body=body, request=MockRequest(), orchestrator=orch
        )
        assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_stats_handler(self) -> None:
        from api.routes.memory import get_memory_stats

        orch = MockOrchestrator()
        result = await get_memory_stats(request=MockRequest(), orchestrator=orch)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_search_missing_query(self) -> None:
        from api.routes.memory import search_memories

        orch = MockOrchestrator()
        result = await search_memories(
            request=MockRequest(), q="", orchestrator=orch
        )
        assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_search_with_query(self) -> None:
        from api.routes.memory import search_memories

        orch = MockOrchestrator()
        result = await search_memories(
            request=MockRequest(), q="test", orchestrator=orch
        )
        assert result.status_code == 200
