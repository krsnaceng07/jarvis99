"""JARVIS OS - Learning Engine Router.

Exposes REST APIs for document scraping, context querying, and ingestion metrics.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from core.learning.service import LearningService
from core.memory.interfaces import RetrievalQuery

# Global service holder for FastAPI router dependency injection
_global_learning_service: Optional[LearningService] = None


def set_learning_service(service: Optional[LearningService]) -> None:
    """Set the active global learning service coordinator.

    Args:
        service: Active LearningService instance or None.
    """
    global _global_learning_service
    _global_learning_service = service


learning_router = APIRouter(prefix="/api/v1/learning", tags=["learning"])


class IngestRequest(BaseModel):
    """Pydantic model representing ingestion URL parameters."""

    url: str = Field(..., description="Trusted documentation page URL.")


class IngestResponse(BaseModel):
    """Ingestion process success result."""

    status: str
    chunk_id: UUID
    message: str


class StatusResponse(BaseModel):
    """Ingestion statistics status payload."""

    total_chunks: int
    total_stale: int
    cluster_status: str


@learning_router.post("/ingest", response_model=IngestResponse)
async def ingest_url(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    background: bool = False,
) -> Dict[str, Any]:
    """Scrape and ingest target URL contents into system memory."""
    if not _global_learning_service:
        raise HTTPException(
            status_code=503, detail="Learning Engine service unavailable."
        )

    try:
        from uuid import uuid4

        chunk_id = uuid4()
        if background:
            # Add non-blocking background task
            background_tasks.add_task(
                _global_learning_service.ingest_url, request.url, chunk_id
            )
            return {
                "status": "PROCESSING",
                "chunk_id": chunk_id,
                "message": f"URL {request.url} ingestion scheduled in background.",
            }
        else:
            actual_id = await _global_learning_service.ingest_url(request.url, chunk_id)
            return {
                "status": "SUCCESS",
                "chunk_id": actual_id,
                "message": f"URL {request.url} ingested successfully.",
            }
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err))


@learning_router.get("/query")
async def query_knowledge(q: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Query ingested technical chunks semantically."""
    if not _global_learning_service:
        raise HTTPException(
            status_code=503, detail="Learning Engine service unavailable."
        )

    try:
        query_dto = RetrievalQuery(query_text=q, limit=limit)
        results = await _global_learning_service.memory_service.retrieve(query_dto)
        return [r.model_dump() for r in results]
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))


@learning_router.get("/status", response_model=StatusResponse)
async def get_learning_status() -> Dict[str, Any]:
    """Retrieve stats on total chunks indexed and stale expiration states."""
    if not _global_learning_service:
        raise HTTPException(
            status_code=503, detail="Learning Engine service unavailable."
        )

    try:
        from sqlalchemy import select

        from core.memory.models import MemoryChunk

        stmt = select(MemoryChunk).where(MemoryChunk.is_deleted.is_(False))
        session = getattr(
            _global_learning_service.memory_service.memory_repo, "session", None
        )
        if not session:
            chunks = []
        else:
            res = await session.execute(stmt)
            chunks = res.scalars().all()

        stale = await _global_learning_service.check_stale_nodes()
        return {
            "total_chunks": len(chunks),
            "total_stale": len(stale),
            "cluster_status": "HEALTHY",
        }
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))
