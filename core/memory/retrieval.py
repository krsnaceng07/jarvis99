"""JARVIS OS - Search and Retrieval Subsystem.

Combines SQL exact-match and vector index semantic queries using Reciprocal Rank Fusion (RRF).
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from core.memory.interfaces import (
    IEmbeddingGenerator,
    IKnowledgeGraphRepository,
    IMemoryRepository,
    IVectorStoreRepository,
    MemoryChunkDTO,
    MemoryNodeDTO,
)


class RetrievalEngine:
    """Orchestrates search over vector indices, database tables, and the graph."""

    def __init__(
        self,
        memory_repo: IMemoryRepository,
        vector_repo: IVectorStoreRepository,
        graph_repo: IKnowledgeGraphRepository,
        embedding_generator: IEmbeddingGenerator,
    ) -> None:
        """Initialize RetrievalEngine with repositories.

        Args:
            memory_repo: Persistent relational database repository.
            vector_repo: High-dimensional vector index repository.
            graph_repo: Knowledge Graph relationship repository.
            embedding_generator: Text embedding generator client.
        """
        self.memory_repo = memory_repo
        self.vector_repo = vector_repo
        self.graph_repo = graph_repo
        self.embedding_generator = embedding_generator

    async def search_vector_similarity(
        self, query: str, limit: int = 10, min_score: float = 0.0
    ) -> List[MemoryChunkDTO]:
        """Perform semantic search using vector cosine similarity.

        Args:
            query: Semantic query text.
            limit: Maximum result count.
            min_score: Minimum similarity score threshold.
        """
        emb = await self.embedding_generator.generate_embedding(query)
        matches = await self.vector_repo.search_vector(emb, limit=limit)

        chunks = []
        for match in matches:
            score = float(match.get("score", 0.0))
            if score < min_score:
                continue

            chunk_id = match["id"]
            chunk = await self.memory_repo.get_chunk(chunk_id)
            if chunk:
                # Inject score inside metadata dynamically for upstream ranking
                chunk.metadata["search_score"] = score
                chunks.append(chunk)

        return chunks

    async def search_hybrid_rrf(
        self, query: str, limit: int = 5, k: int = 60
    ) -> List[MemoryChunkDTO]:
        """Execute hybrid search using Reciprocal Rank Fusion (RRF) on keyword & vector results.

        RRF Score(d) = sum_{m in models} 1 / (k + rank_m(d))

        Args:
            query: Target query text.
            limit: Maximum result count.
            k: RRF rank smoothing constant parameter.
        """
        # Fetch both result streams
        keyword_results = await self.memory_repo.keyword_search_chunks(
            query, limit=limit * 3
        )
        vector_results = await self.search_vector_similarity(query, limit=limit * 3)

        # Build rank mappings
        keyword_ranks = {chunk.id: idx for idx, chunk in enumerate(keyword_results)}
        vector_ranks = {chunk.id: idx for idx, chunk in enumerate(vector_results)}

        all_ids = set(keyword_ranks.keys()).union(vector_ranks.keys())
        rrf_scores: Dict[UUID, float] = {}

        for cid in all_ids:
            score = 0.0
            if cid in keyword_ranks:
                score += 1.0 / (k + keyword_ranks[cid])
            if cid in vector_ranks:
                score += 1.0 / (k + vector_ranks[cid])
            rrf_scores[cid] = score

        # Sort chunk IDs descending by RRF scores
        sorted_ids = sorted(all_ids, key=lambda x: rrf_scores[x], reverse=True)

        chunks = []
        for cid in sorted_ids[:limit]:
            # Try to fetch active chunk
            chunk = await self.memory_repo.get_chunk(cid)
            if chunk:
                chunk.metadata["rrf_score"] = rrf_scores[cid]
                chunks.append(chunk)

        return chunks

    async def retrieve_with_budget(
        self,
        query: str,
        max_chunks: int = 10,
        max_tokens: int = 2000,
        min_relevance: float = 0.0,
        graph_depth: int = 0,
        start_node_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Query memory stores, enforce token budgets, and load related graph nodes.

        Args:
            query: Semantic search query.
            max_chunks: Maximum allowed chunks returned.
            max_tokens: Combined token limit ceiling. Chunks are discarded if sum exceeds this.
            min_relevance: Relevance threshold filtering.
            graph_depth: Neighbors depth for graph traversal.
            start_node_id: Optional starting node for traversal.

        Returns:
            Dict containing:
              - 'chunks': list[MemoryChunkDTO] within budget limits.
              - 'nodes': list[MemoryNodeDTO] within budget limits.
              - 'total_tokens': total tokens returned.
        """
        # Execute hybrid search to get candidate text blocks
        candidates = await self.search_hybrid_rrf(query, limit=max_chunks * 2)

        # Filter by minimum relevance if search score exists in metadata
        filtered_candidates = []
        for c in candidates:
            # RRF score is a rank-based measure, check similarity score if available
            score = c.metadata.get("search_score", 1.0)
            if score >= min_relevance:
                filtered_candidates.append(c)

        # Apply token budget limits
        active_chunks: List[MemoryChunkDTO] = []
        total_tokens = 0

        for chunk in filtered_candidates:
            if len(active_chunks) >= max_chunks:
                break
            if total_tokens + chunk.token_count > max_tokens:
                continue  # Skip chunk if it pushes context over budget
            active_chunks.append(chunk)
            total_tokens += chunk.token_count

        # Traverse Knowledge Graph if requested
        active_nodes: List[MemoryNodeDTO] = []
        if graph_depth > 0 and start_node_id:
            active_nodes = await self.graph_repo.traverse(
                start_node_id, max_depth=graph_depth
            )

        return {
            "chunks": active_chunks,
            "nodes": active_nodes,
            "total_tokens": total_tokens,
        }
