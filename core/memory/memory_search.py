"""
PHASE: 20
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 20 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from core.memory.dto import MemoryRecord, MemoryTier, MemoryVisibility
from core.memory.interfaces import (
    IEmbeddingGenerator,
    IMemoryRepository,
    IVectorStoreRepository,
)
from core.memory.memory_scoring import MemoryScoring


class MemorySearch:
    """Orchestrates keyword, semantic, and hybrid search pipelines across memory tiers.

    Enforces permission checks, applies metadata filters, and ranks retrieval candidates
    using composite scoring tie-breakers.
    """

    def __init__(
        self,
        memory_repo: IMemoryRepository,
        vector_repo: IVectorStoreRepository,
        embedding_generator: IEmbeddingGenerator,
        scoring: MemoryScoring,
    ) -> None:
        self.memory_repo = memory_repo
        self.vector_repo = vector_repo
        self.embedding_generator = embedding_generator
        self.scoring = scoring

    async def search_keyword(
        self,
        query: str,
        limit: int = 50,
    ) -> List[MemoryRecord]:
        """Perform text keyword search in database."""
        legacy_chunks = await self.memory_repo.keyword_search_chunks(query, limit)
        from core.memory.memory_serializer import MemorySerializer

        return [MemorySerializer.from_dto(chunk) for chunk in legacy_chunks]

    async def search_semantic(
        self,
        query: str,
        limit: int = 50,
    ) -> List[tuple[MemoryRecord, float]]:
        """Perform semantic vector similarity search using embeddings."""
        embedding = await self.embedding_generator.generate_embedding(query)
        # Search vector store
        matches = await self.vector_repo.search_vector(embedding, limit)
        # matches is list of dict containing 'id' and 'score'
        from core.memory.memory_serializer import MemorySerializer

        results: List[tuple[MemoryRecord, float]] = []
        for match in matches:
            chunk_id = match["id"]
            score = float(match.get("score", 0.0))
            chunk = await self.memory_repo.get_chunk(chunk_id)
            if chunk:
                record = MemorySerializer.from_dto(chunk)
                results.append((record, score))
        return results

    async def search_hybrid(
        self,
        query: str,
        owner_id: Optional[UUID] = None,
        tier_filter: Optional[List[MemoryTier]] = None,
        min_score: float = 0.0,
        limit: int = 50,
        now: Optional[datetime] = None,
    ) -> List[MemoryRecord]:
        """Perform hybrid search (keyword + semantic) and rank by composite score.

        Enforces permission filters and token limits.
        """
        # 1. Fetch Candidates (Keyword + Semantic)
        keyword_candidates = await self.search_keyword(query, limit * 2)
        semantic_matches = await self.search_semantic(query, limit * 2)

        # 2. Collect all unique candidates
        candidate_map: Dict[UUID, MemoryRecord] = {}
        semantic_similarities: Dict[UUID, float] = {}

        for rec in keyword_candidates:
            candidate_map[rec.memory_id] = rec
            semantic_similarities[rec.memory_id] = 0.0

        for rec, similarity in semantic_matches:
            candidate_map[rec.memory_id] = rec
            semantic_similarities[rec.memory_id] = similarity

        candidates = list(candidate_map.values())

        # 3. Apply Permission Filters
        permitted = []
        for record in candidates:
            # Check ownership / visibility
            if owner_id is not None and record.owner_id == owner_id:
                permitted.append(record)
            elif record.visibility in (
                MemoryVisibility.PUBLIC,
                MemoryVisibility.SYSTEM,
                MemoryVisibility.AGENT,
            ):
                permitted.append(record)

        # 4. Apply Tier Filters
        if tier_filter is not None:
            permitted = [
                r
                for r in permitted
                if r.metadata and r.metadata.extra.get("tier") in tier_filter
            ]

        # 5. Score Candidates
        scores = self.scoring.rank_records(
            records=permitted,
            access_counts=None,  # default
            semantic_similarities=semantic_similarities,
            pinned_ids=None,
            now=now,
        )

        # 6. Select Top-K above threshold
        ranked_records = []
        for score in scores:
            if score.final_score < min_score:
                continue
            rec = candidate_map[score.memory_id]
            # Attach score metadata for inspectability
            rec.metadata.extra["retrieval_score"] = score.final_score
            ranked_records.append(rec)
            if len(ranked_records) >= limit:
                break

        return ranked_records
