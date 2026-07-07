"""JARVIS OS - Phase 19 M9 Memory CLI Tests.

Tests for all 10 memory CLI command handlers. Tests call async handlers
directly with mock argparse.Namespace and mock MemoryOrchestrator.

PHASE: 19
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

import argparse
from typing import Any, Optional
from uuid import UUID, uuid4

import pytest

from memory.cli import (
    cmd_archive,
    cmd_forget,
    cmd_get,
    cmd_promote,
    cmd_recall,
    cmd_reflect,
    cmd_score,
    cmd_search,
    cmd_stats,
    cmd_store,
    _print_human,
)


# =====================================================================
# Mock Orchestrator
# =====================================================================


class MockRepo:
    """Mock memory repository for CLI tests."""

    def __init__(self) -> None:
        self._records: dict[UUID, Any] = {}

    async def get_by_id(self, memory_id: UUID) -> Any:
        return self._records.get(memory_id)

    async def list_records(self, **kwargs: Any) -> list[Any]:
        return list(self._records.values())


class MockRecord:
    """Mock MemoryRecord for CLI tests."""

    def __init__(self, memory_id: Optional[UUID] = None) -> None:
        self.memory_id = memory_id or uuid4()
        self.content = "test content"
        self.content_hash = "hash_abc"
        self.confidence = 0.9
        self.importance = 0.5
        self.created_at = "2026-07-01T00:00:00"
        self.updated_at = "2026-07-01T00:00:00"

        class MT:
            value = "fact"
        self.memory_type = MT()


class MockScore:
    """Mock MemoryScore."""

    final_score = 0.85
    recency_score = 0.9
    importance_score = 0.8
    confidence_score = 0.95
    access_score = 0.7


class MockChunk:
    """Mock retrieval chunk."""

    def __init__(self) -> None:
        self.memory_id = uuid4()
        self.content = "retrieved content"
        self.content_hash = "hash_xyz"
        self.created_at = "2026-07-01T00:00:00"


class MockResponse:
    """Mock RetrievalResponse."""

    def __init__(self, chunks: Optional[list[Any]] = None) -> None:
        self.chunks = chunks or []


class MockOrchestrator:
    """Mock MemoryOrchestrator for CLI tests."""

    def __init__(self) -> None:
        self.memory_repo = MockRepo()
        self._stored: list[dict[str, Any]] = []

    async def store(self, **kwargs: Any) -> UUID:
        mid = uuid4()
        self._stored.append({"id": mid, **kwargs})
        return mid

    async def recall(self, request: Any) -> MockResponse:
        return MockResponse([MockChunk()])

    async def reflect(self, request: Any) -> bool:
        return True

    async def forget(self, chunk_id: UUID, reason: str, cascade: bool = False) -> bool:
        return True

    async def archive(self, chunk_id: UUID, reason: str) -> bool:
        return True

    async def promote(self, chunk_id: UUID, target_tier: Any) -> bool:
        return True

    async def score(self, chunk_id: UUID) -> MockScore:
        return MockScore()

    @staticmethod
    def _infer_tier(record: Any) -> Any:
        class T:
            value = "working"
        return T()


def _ns(**kwargs: Any) -> argparse.Namespace:
    """Build an argparse.Namespace from keyword args."""
    return argparse.Namespace(**kwargs)


# =====================================================================
# Store Tests
# =====================================================================


class TestCmdStore:
    @pytest.mark.asyncio
    async def test_store_success(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_store(
            orch,
            _ns(
                content="hello world",
                source_type="test",
                importance=0.5,
                confidence=1.0,
                metadata=None,
            ),
        )
        assert result["success"] is True
        assert "chunk_id" in result

    @pytest.mark.asyncio
    async def test_store_with_json_metadata(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_store(
            orch,
            _ns(
                content="test",
                source_type="web",
                importance=0.8,
                confidence=0.9,
                metadata='{"url": "https://example.com"}',
            ),
        )
        assert result["success"] is True


# =====================================================================
# Recall Tests
# =====================================================================


class TestCmdRecall:
    @pytest.mark.asyncio
    async def test_recall_success(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_recall(
            orch, _ns(query="test", max_chunks=10, min_score=0.0)
        )
        assert result["success"] is True
        assert result["total"] == 1
        assert len(result["chunks"]) == 1


# =====================================================================
# Get Tests
# =====================================================================


class TestCmdGet:
    @pytest.mark.asyncio
    async def test_get_not_found(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_get(orch, _ns(chunk_id=str(uuid4())))
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_found(self) -> None:
        orch = MockOrchestrator()
        record = MockRecord()
        orch.memory_repo._records[record.memory_id] = record
        result = await cmd_get(orch, _ns(chunk_id=str(record.memory_id)))
        assert result["success"] is True
        assert result["content"] == "test content"

    @pytest.mark.asyncio
    async def test_get_invalid_uuid(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_get(orch, _ns(chunk_id="not-a-uuid"))
        assert result["success"] is False
        assert "invalid" in result["error"].lower()


# =====================================================================
# Score Tests
# =====================================================================


class TestCmdScore:
    @pytest.mark.asyncio
    async def test_score_success(self) -> None:
        orch = MockOrchestrator()
        mid = uuid4()
        result = await cmd_score(orch, _ns(chunk_id=str(mid)))
        assert result["success"] is True
        assert result["final_score"] == 0.85

    @pytest.mark.asyncio
    async def test_score_invalid_uuid(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_score(orch, _ns(chunk_id="bad"))
        assert result["success"] is False


# =====================================================================
# Reflect Tests
# =====================================================================


class TestCmdReflect:
    @pytest.mark.asyncio
    async def test_reflect_success(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_reflect(
            orch, _ns(chunk_id=str(uuid4()), outcome="success", delta=0.1)
        )
        assert result["success"] is True
        assert result["action"] == "reflect"

    @pytest.mark.asyncio
    async def test_reflect_invalid_outcome(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_reflect(
            orch, _ns(chunk_id=str(uuid4()), outcome="invalid", delta=0.1)
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_reflect_invalid_uuid(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_reflect(
            orch, _ns(chunk_id="bad", outcome="success", delta=0.1)
        )
        assert result["success"] is False


# =====================================================================
# Forget Tests
# =====================================================================


class TestCmdForget:
    @pytest.mark.asyncio
    async def test_forget_success(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_forget(
            orch, _ns(chunk_id=str(uuid4()), reason="cleanup", cascade=False)
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_forget_with_cascade(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_forget(
            orch, _ns(chunk_id=str(uuid4()), reason="deep clean", cascade=True)
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_forget_invalid_uuid(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_forget(
            orch, _ns(chunk_id="bad", reason="test", cascade=False)
        )
        assert result["success"] is False


# =====================================================================
# Archive Tests
# =====================================================================


class TestCmdArchive:
    @pytest.mark.asyncio
    async def test_archive_success(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_archive(
            orch, _ns(chunk_id=str(uuid4()), reason="old data")
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_archive_invalid_uuid(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_archive(orch, _ns(chunk_id="bad", reason="test"))
        assert result["success"] is False


# =====================================================================
# Promote Tests
# =====================================================================


class TestCmdPromote:
    @pytest.mark.asyncio
    async def test_promote_success(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_promote(
            orch, _ns(chunk_id=str(uuid4()), tier="conversation")
        )
        assert result["success"] is True
        assert result["target_tier"] == "conversation"

    @pytest.mark.asyncio
    async def test_promote_invalid_tier(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_promote(
            orch, _ns(chunk_id=str(uuid4()), tier="invalid_tier")
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_promote_invalid_uuid(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_promote(orch, _ns(chunk_id="bad", tier="conversation"))
        assert result["success"] is False


# =====================================================================
# Stats Tests
# =====================================================================


class TestCmdStats:
    @pytest.mark.asyncio
    async def test_stats_empty(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_stats(orch, _ns())
        assert result["success"] is True
        assert result["total_chunks"] == 0

    @pytest.mark.asyncio
    async def test_stats_with_records(self) -> None:
        orch = MockOrchestrator()
        mid = uuid4()
        orch.memory_repo._records[mid] = MockRecord(mid)
        result = await cmd_stats(orch, _ns())
        assert result["total_chunks"] == 1


# =====================================================================
# Search Tests
# =====================================================================


class TestCmdSearch:
    @pytest.mark.asyncio
    async def test_search_success(self) -> None:
        orch = MockOrchestrator()
        result = await cmd_search(
            orch, _ns(query="test", max_chunks=10, min_score=0.0)
        )
        assert result["success"] is True
        assert result["total"] == 1


# =====================================================================
# Human Output Tests
# =====================================================================


class TestPrintHuman:
    def test_print_store(self, capsys: Any) -> None:
        _print_human({"success": True, "chunk_id": "abc-123"}, "store")
        captured = capsys.readouterr()
        assert "abc-123" in captured.out

    def test_print_recall_empty(self, capsys: Any) -> None:
        _print_human({"success": True, "total": 0, "chunks": []}, "recall")
        captured = capsys.readouterr()
        assert "No memories" in captured.out

    def test_print_stats(self, capsys: Any) -> None:
        _print_human({"success": True, "total_chunks": 42}, "stats")
        captured = capsys.readouterr()
        assert "42" in captured.out

    def test_print_error(self, capsys: Any) -> None:
        _print_human({"success": False, "error": "boom"}, "store")
        captured = capsys.readouterr()
        assert "boom" in captured.err

    def test_print_score(self, capsys: Any) -> None:
        _print_human(
            {
                "success": True,
                "memory_id": "test-id",
                "final_score": 0.85,
                "recency_score": 0.9,
                "importance_score": 0.8,
                "confidence_score": 0.95,
                "access_score": 0.7,
            },
            "score",
        )
        captured = capsys.readouterr()
        assert "0.85" in captured.out
