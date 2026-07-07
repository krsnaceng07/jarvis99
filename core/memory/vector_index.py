"""JARVIS OS - Memory Vector Index Service.

Bridges the MemoryOrchestrator (Phase 19 MemoryRecord pipeline) with
the vector store and embedding generator for semantic search.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from core.memory.interfaces import IEmbeddingGenerator, IVectorStoreRepository
from core.memory.memory_repository import IMemoryRecordRepository

logger = logging.getLogger(__name__)


class MemoryVectorIndex:
    """Manages vector embeddings for MemoryRecords.

    Called by MemoryOrchestrator on store() to index content,
    and by VectorCandidateProvider on recall() to search.
    """

    def __init__(
        self,
        vector_repo: IVectorStoreRepository,
        embedding_generator: IEmbeddingGenerator,
    ) -> None:
        self._vector_repo = vector_repo
        self._embedding = embedding_generator

    async def initialize(self) -> None:
        """Initialize the underlying vector store."""
        await self._vector_repo.initialize()

    async def index_memory(
        self, memory_id: UUID, content: str, metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Generate embedding for content and store in vector index."""
        try:
            embedding = await self._embedding.generate_embedding(content)
            meta = dict(metadata or {})
            meta["memory_id"] = str(memory_id)
            return await self._vector_repo.add_vector(memory_id, embedding, meta)
        except Exception as e:
            logger.warning("Failed to index memory %s: %s", memory_id, e)
            return False

    async def remove_memory(self, memory_id: UUID) -> bool:
        """Remove a memory from the vector index."""
        return await self._vector_repo.delete_vector(memory_id)

    async def search(
        self, query: str, limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search vector index for semantically similar memories.

        Returns list of dicts with 'id' (UUID) and 'score' (float 0-1).
        """
        try:
            embedding = await self._embedding.generate_embedding(query)
            return await self._vector_repo.search_vector(embedding, limit)
        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            return []


class VectorCandidateProvider:
    """CandidateProvider implementation using vector similarity search.

    Plugs into RetrievalEngine's candidate generation stage to provide
    semantically similar memories ranked by cosine similarity.
    """

    def __init__(
        self,
        vector_index: MemoryVectorIndex,
        record_repo: IMemoryRecordRepository,
    ) -> None:
        self._vector_index = vector_index
        self._record_repo = record_repo
        self._last_similarity_scores: Dict[UUID, float] = {}

    @property
    def name(self) -> str:
        return "vector"

    def supports(self, tier: Any) -> bool:
        return True

    async def search(
        self,
        query: str,
        owner_id: Optional[UUID] = None,
        limit: int = 200,
    ) -> list:
        """Search for candidate memories using vector similarity."""
        from core.memory.dto import MemoryRecord

        vector_results = await self._vector_index.search(query, limit=limit)
        self._last_similarity_scores.clear()

        records: list[MemoryRecord] = []
        for result in vector_results:
            memory_id = result["id"]
            score = result.get("score", 0.0)

            record = await self._record_repo.get_by_id(memory_id)
            if record is None:
                continue

            if owner_id is not None and record.owner_id != owner_id:
                if record.visibility.value not in ("public", "system", "agent"):
                    continue

            self._last_similarity_scores[memory_id] = max(0.0, score)
            records.append(record)

        return records

    def get_similarity(self, memory_id: UUID) -> float:
        """Get the similarity score for a memory from the last search."""
        return self._last_similarity_scores.get(memory_id, 0.0)
