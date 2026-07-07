"""JARVIS OS - Phase 19 M8 Memory API Routes.

Thin REST adapter exposing all 10 frozen memory endpoints (spec §9.1).
Every handler delegates to MemoryOrchestrator — no business logic here.

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

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import get_memory_orchestrator
from api.dto import ErrorDetail, ErrorEnvelope, MetaBlock, SuccessEnvelope
from core.memory.dto import (
    ExecutionOutcome,
    MemoryTier,
    ReflectionRequest,
    RetrievalRequest,
)

router = APIRouter(prefix="/memory", tags=["memory"])


# =====================================================================
# Request / Response DTOs (spec §9.2)
# =====================================================================


class MemoryStoreRequest(BaseModel):
    """POST /api/v1/memory/store request body."""

    content: str = Field(min_length=1, max_length=100_000)
    source_type: str = Field(min_length=1, max_length=100)
    metadata: Optional[Dict[str, Any]] = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class MemoryStoreResponse(BaseModel):
    """POST /api/v1/memory/store response data."""

    chunk_id: UUID
    api_version: str = "v1"


class MemoryRecallRequest(BaseModel):
    """POST /api/v1/memory/recall request body."""

    query: str = Field(min_length=1, max_length=10_000)
    max_chunks: int = Field(default=50, ge=1, le=500)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class MemoryRecallResponse(BaseModel):
    """POST /api/v1/memory/recall response data."""

    chunks: List[Dict[str, Any]]
    total_chunks: int
    api_version: str = "v1"


class MemoryGetResponse(BaseModel):
    """GET /api/v1/memory/{id} response data."""

    memory_id: UUID
    content: str
    memory_type: str
    confidence: float
    importance: float
    tier: str
    created_at: str
    updated_at: str
    api_version: str = "v1"


class MemoryScoreResponse(BaseModel):
    """GET /api/v1/memory/{id}/score response data."""

    memory_id: UUID
    final_score: float
    recency_score: float
    importance_score: float
    confidence_score: float
    access_score: float
    api_version: str = "v1"


class MemoryReflectRequest(BaseModel):
    """POST /api/v1/memory/{id}/reflect request body."""

    outcome: str = Field(description="One of: success, failure, partial, timeout")
    confidence_delta: float = Field(ge=-1.0, le=1.0)
    notes: Optional[str] = None


class MemoryForgetRequest(BaseModel):
    """POST /api/v1/memory/{id}/forget request body."""

    reason: str = Field(min_length=1, max_length=500)
    cascade: bool = False


class MemoryArchiveRequest(BaseModel):
    """POST /api/v1/memory/{id}/archive request body."""

    reason: str = Field(min_length=1, max_length=500)


class MemoryPromoteRequest(BaseModel):
    """POST /api/v1/memory/{id}/promote request body."""

    target_tier: str = Field(description="Target tier: conversation, long_term, archived")


class MemoryActionResponse(BaseModel):
    """Generic success/failure action response."""

    success: bool
    memory_id: UUID
    action: str
    api_version: str = "v1"


class MemoryStatsResponse(BaseModel):
    """GET /api/v1/memory/stats response data."""

    total_chunks: int
    api_version: str = "v1"


class MemorySearchResponse(BaseModel):
    """GET /api/v1/memory/search response data."""

    chunks: List[Dict[str, Any]]
    total_chunks: int
    api_version: str = "v1"


# =====================================================================
# Helpers
# =====================================================================


def _meta(request: Request) -> MetaBlock:
    """Build MetaBlock from request state."""
    request_id = getattr(request.state, "request_id", None)
    return MetaBlock(request_id=request_id) if request_id else MetaBlock()


def _error_response(
    status_code: int, code: str, message: str, request: Request
) -> JSONResponse:
    """Build a standard error envelope response."""
    envelope = ErrorEnvelope(
        error=ErrorDetail(code=code, message=message),
        meta=_meta(request),
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
    )


# =====================================================================
# Endpoints (frozen mapping — spec §9.1)
# NOTE: Static GET paths (/stats, /search) MUST be registered before
#       dynamic paths (/{memory_id}) to prevent FastAPI path shadowing.
# =====================================================================


@router.post("/store")
async def store_memory(
    body: MemoryStoreRequest,
    request: Request,
    orchestrator: Any = Depends(get_memory_orchestrator),
) -> JSONResponse:
    """POST /api/v1/memory/store — Store a new memory."""
    try:
        chunk_id = await orchestrator.store(
            content=body.content,
            source_type=body.source_type,
            metadata=body.metadata,
            importance=body.importance,
            confidence=body.confidence,
        )
        data = MemoryStoreResponse(chunk_id=chunk_id)
        envelope = SuccessEnvelope[MemoryStoreResponse](data=data, meta=_meta(request))
        return JSONResponse(
            status_code=201,
            content=envelope.model_dump(mode="json"),
        )
    except Exception as e:
        return _error_response(500, "MEMORY_001", str(e), request)


@router.post("/recall")
async def recall_memory(
    body: MemoryRecallRequest,
    request: Request,
    orchestrator: Any = Depends(get_memory_orchestrator),
) -> JSONResponse:
    """POST /api/v1/memory/recall — Retrieve memories with scoring."""
    try:
        retrieval_request = RetrievalRequest(
            query=body.query,
            max_chunks=body.max_chunks,
            min_score=body.min_score,
        )
        response = await orchestrator.recall(retrieval_request)
        chunks = [
            {
                "memory_id": str(c.memory_id),
                "content": c.content,
                "content_hash": c.content_hash,
                "created_at": str(c.created_at) if c.created_at else None,
            }
            for c in response.chunks
        ]
        data = MemoryRecallResponse(chunks=chunks, total_chunks=len(chunks))
        envelope = SuccessEnvelope[MemoryRecallResponse](
            data=data, meta=_meta(request)
        )
        return JSONResponse(content=envelope.model_dump(mode="json"))
    except Exception as e:
        return _error_response(500, "MEMORY_002", str(e), request)


# --- Static GET paths (must precede /{memory_id} to avoid shadowing) ---


@router.get("/stats")
async def get_memory_stats(
    request: Request,
    orchestrator: Any = Depends(get_memory_orchestrator),
) -> JSONResponse:
    """GET /api/v1/memory/stats — Get memory statistics."""
    try:
        records = await orchestrator.memory_repo.list_records()
        data = MemoryStatsResponse(total_chunks=len(records))
        envelope = SuccessEnvelope[MemoryStatsResponse](
            data=data, meta=_meta(request)
        )
        return JSONResponse(content=envelope.model_dump(mode="json"))
    except Exception as e:
        return _error_response(500, "MEMORY_013", str(e), request)


@router.get("/search")
async def search_memories(
    request: Request,
    q: str = "",
    max_chunks: int = 50,
    min_score: float = 0.0,
    orchestrator: Any = Depends(get_memory_orchestrator),
) -> JSONResponse:
    """GET /api/v1/memory/search — Search memories by query."""
    if not q:
        return _error_response(
            400, "MEMORY_014", "Query parameter 'q' is required", request
        )

    try:
        retrieval_request = RetrievalRequest(
            query=q,
            max_chunks=max_chunks,
            min_score=min_score,
        )
        response = await orchestrator.recall(retrieval_request)
        chunks = [
            {
                "memory_id": str(c.memory_id),
                "content": c.content,
                "content_hash": c.content_hash,
                "created_at": str(c.created_at) if c.created_at else None,
            }
            for c in response.chunks
        ]
        data = MemorySearchResponse(chunks=chunks, total_chunks=len(chunks))
        envelope = SuccessEnvelope[MemorySearchResponse](
            data=data, meta=_meta(request)
        )
        return JSONResponse(content=envelope.model_dump(mode="json"))
    except Exception as e:
        return _error_response(500, "MEMORY_015", str(e), request)


# --- Dynamic paths (/{memory_id} and sub-paths) ---


@router.get("/{memory_id}")
async def get_memory(
    memory_id: UUID,
    request: Request,
    orchestrator: Any = Depends(get_memory_orchestrator),
) -> JSONResponse:
    """GET /api/v1/memory/{id} — Get a specific memory."""
    try:
        record = await orchestrator.memory_repo.get_by_id(memory_id)
        if record is None:
            return _error_response(404, "MEMORY_003", "Memory not found", request)

        tier = orchestrator._infer_tier(record)
        data = MemoryGetResponse(
            memory_id=record.memory_id,
            content=record.content,
            memory_type=record.memory_type.value
            if hasattr(record.memory_type, "value")
            else str(record.memory_type),
            confidence=record.confidence,
            importance=record.importance,
            tier=tier.value,
            created_at=str(record.created_at),
            updated_at=str(record.updated_at),
        )
        envelope = SuccessEnvelope[MemoryGetResponse](data=data, meta=_meta(request))
        return JSONResponse(content=envelope.model_dump(mode="json"))
    except Exception as e:
        return _error_response(500, "MEMORY_004", str(e), request)


@router.get("/{memory_id}/score")
async def get_memory_score(
    memory_id: UUID,
    request: Request,
    orchestrator: Any = Depends(get_memory_orchestrator),
) -> JSONResponse:
    """GET /api/v1/memory/{id}/score — Get the score for a memory."""
    try:
        score = await orchestrator.score(memory_id)
        data = MemoryScoreResponse(
            memory_id=memory_id,
            final_score=score.final_score,
            recency_score=score.recency_score,
            importance_score=score.importance_score,
            confidence_score=score.confidence_score,
            access_score=score.access_score,
        )
        envelope = SuccessEnvelope[MemoryScoreResponse](data=data, meta=_meta(request))
        return JSONResponse(content=envelope.model_dump(mode="json"))
    except ValueError:
        return _error_response(404, "MEMORY_005", "Memory not found", request)
    except Exception as e:
        return _error_response(500, "MEMORY_006", str(e), request)


@router.post("/{memory_id}/reflect")
async def reflect_memory(
    memory_id: UUID,
    body: MemoryReflectRequest,
    request: Request,
    orchestrator: Any = Depends(get_memory_orchestrator),
) -> JSONResponse:
    """POST /api/v1/memory/{id}/reflect — Apply reflection."""
    try:
        outcome = ExecutionOutcome(body.outcome)
    except ValueError:
        return _error_response(
            400,
            "MEMORY_007",
            f"Invalid outcome: {body.outcome}. Must be one of: success, failure, partial, timeout",
            request,
        )

    try:
        reflection_request = ReflectionRequest(
            memory_id=memory_id,
            outcome=outcome,
            confidence_delta=body.confidence_delta,
            notes=body.notes,
        )
        result = await orchestrator.reflect(reflection_request)
        data = MemoryActionResponse(
            success=result, memory_id=memory_id, action="reflect"
        )
        envelope = SuccessEnvelope[MemoryActionResponse](
            data=data, meta=_meta(request)
        )
        return JSONResponse(content=envelope.model_dump(mode="json"))
    except Exception as e:
        return _error_response(500, "MEMORY_008", str(e), request)


@router.post("/{memory_id}/forget")
async def forget_memory(
    memory_id: UUID,
    body: MemoryForgetRequest,
    request: Request,
    orchestrator: Any = Depends(get_memory_orchestrator),
) -> JSONResponse:
    """POST /api/v1/memory/{id}/forget — Forget a memory."""
    try:
        result = await orchestrator.forget(
            chunk_id=memory_id, reason=body.reason, cascade=body.cascade
        )
        data = MemoryActionResponse(
            success=result, memory_id=memory_id, action="forget"
        )
        envelope = SuccessEnvelope[MemoryActionResponse](
            data=data, meta=_meta(request)
        )
        return JSONResponse(content=envelope.model_dump(mode="json"))
    except Exception as e:
        return _error_response(500, "MEMORY_009", str(e), request)


@router.post("/{memory_id}/archive")
async def archive_memory(
    memory_id: UUID,
    body: MemoryArchiveRequest,
    request: Request,
    orchestrator: Any = Depends(get_memory_orchestrator),
) -> JSONResponse:
    """POST /api/v1/memory/{id}/archive — Archive a memory."""
    try:
        result = await orchestrator.archive(chunk_id=memory_id, reason=body.reason)
        data = MemoryActionResponse(
            success=result, memory_id=memory_id, action="archive"
        )
        envelope = SuccessEnvelope[MemoryActionResponse](
            data=data, meta=_meta(request)
        )
        return JSONResponse(content=envelope.model_dump(mode="json"))
    except Exception as e:
        return _error_response(500, "MEMORY_010", str(e), request)


@router.post("/{memory_id}/promote")
async def promote_memory(
    memory_id: UUID,
    body: MemoryPromoteRequest,
    request: Request,
    orchestrator: Any = Depends(get_memory_orchestrator),
) -> JSONResponse:
    """POST /api/v1/memory/{id}/promote — Promote to higher tier."""
    try:
        target_tier = MemoryTier(body.target_tier)
    except ValueError:
        valid_tiers = [t.value for t in MemoryTier]
        return _error_response(
            400,
            "MEMORY_011",
            f"Invalid tier: {body.target_tier}. Must be one of: {valid_tiers}",
            request,
        )

    try:
        result = await orchestrator.promote(chunk_id=memory_id, target_tier=target_tier)
        data = MemoryActionResponse(
            success=result, memory_id=memory_id, action="promote"
        )
        envelope = SuccessEnvelope[MemoryActionResponse](
            data=data, meta=_meta(request)
        )
        return JSONResponse(content=envelope.model_dump(mode="json"))
    except Exception as e:
        return _error_response(500, "MEMORY_012", str(e), request)
