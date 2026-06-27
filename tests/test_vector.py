"""JARVIS OS - Vector Layer Tests.

Verifies similarity searching, mock generators, cache hits, and timeout policies.
"""

import asyncio
from typing import List
from uuid import uuid4

import pytest

from core.exceptions import JarvisMemoryError
from core.memory.embeddings import CachedEmbeddingGenerator, MockEmbeddingGenerator
from core.memory.interfaces import IEmbeddingGenerator
from core.memory.vector_store import InMemoryVectorRepository


class DelayedMockEmbeddingGenerator(IEmbeddingGenerator):
    """Embedding generator mock that introduces artificial latency for timeout testing."""

    def __init__(self, delay: float = 0.5) -> None:
        self.delay = delay

    async def generate_embedding(self, text: str) -> List[float]:
        await asyncio.sleep(self.delay)
        return [0.1, 0.2, 0.3]

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        await asyncio.sleep(self.delay)
        return [[0.1, 0.2, 0.3] for _ in texts]


@pytest.mark.asyncio
async def test_in_memory_vector_store_similarity() -> None:
    """Verify local numpy-based cosine similarity computations."""
    repo = InMemoryVectorRepository()
    await repo.initialize()

    v1_id = uuid4()
    v2_id = uuid4()

    # Pure orthogonal unit vectors
    assert await repo.add_vector(v1_id, [1.0, 0.0, 0.0], {"name": "v1"})
    assert await repo.add_vector(v2_id, [0.0, 1.0, 0.0], {"name": "v2"})

    # Query matching v1 exactly
    res = await repo.search_vector([1.0, 0.0, 0.0], limit=5)
    assert len(res) == 2
    assert res[0]["id"] == v1_id
    assert abs(res[0]["score"] - 1.0) < 1e-5  # Perfect match
    assert abs(res[1]["score"] - 0.0) < 1e-5  # Orthogonal vectors share zero similarity

    # Delete v1
    deleted = await repo.delete_vector(v1_id)
    assert deleted
    res2 = await repo.search_vector([1.0, 0.0, 0.0], limit=5)
    assert len(res2) == 1
    assert res2[0]["id"] == v2_id


@pytest.mark.asyncio
async def test_cached_embedding_generator() -> None:
    """Verify SHA256 caching and hit/miss rate tracking."""
    delegate = MockEmbeddingGenerator(dimensions=8)
    cached = CachedEmbeddingGenerator(delegate, timeout=5.0)

    text1 = "hello world"
    text2 = "test text"

    # Miss 1
    emb1 = await cached.generate_embedding(text1)
    # Hit 1
    emb1_cached = await cached.generate_embedding(text1)
    assert emb1 == emb1_cached

    # Miss 2
    await cached.generate_embedding(text2)

    metrics = cached.metrics
    assert metrics["hits"] == 1
    assert metrics["misses"] == 2
    assert abs(cached.hit_rate - (1.0 / 3.0)) < 1e-5


@pytest.mark.asyncio
async def test_embedding_generator_timeout() -> None:
    """Verify timeout exception triggers on slow delegates."""
    delegate = DelayedMockEmbeddingGenerator(delay=0.2)
    cached = CachedEmbeddingGenerator(delegate, timeout=0.05)

    with pytest.raises(JarvisMemoryError) as exc_info:
        await cached.generate_embedding("timeout test")
    assert "timed out" in exc_info.value.message
