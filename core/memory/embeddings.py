"""JARVIS OS - Embedding Generation.

Provides embedding abstractions, SHA256 caching, timeouts, and mock generators.
"""

import hashlib
import random
from typing import Dict, List

from core.exceptions import JarvisMemoryError
from core.memory.interfaces import IEmbeddingGenerator


class MockEmbeddingGenerator(IEmbeddingGenerator):
    """Deterministic mock embedding generator for local testing."""

    def __init__(self, dimensions: int = 384) -> None:
        """Initialize mock embedding generator.

        Args:
            dimensions: Target dimension shape for embeddings.
        """
        self.dimensions = dimensions

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate deterministic pseudo-random embedding based on text seed."""
        # Use hashing to seed Python's random for deterministic values
        h = hashlib.sha256(text.encode("utf-8")).digest()
        seed = int.from_bytes(h[:8], byteorder="big")
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate deterministic embeddings for multiple texts."""
        return [await self.generate_embedding(t) for t in texts]


class SemanticEmbeddingGenerator(IEmbeddingGenerator):
    """Embedding generator using word/n-gram hashing for semantic similarity.

    Similar texts share words and n-grams, so their hashed vectors
    have high cosine similarity — without requiring an external API.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate a semantic embedding via feature hashing."""
        import math
        import re

        vector = [0.0] * self.dimensions
        if not text:
            return vector

        normalized = text.lower().strip()
        words = re.findall(r"[a-z0-9]+", normalized)

        features: List[str] = []
        features.extend(words)
        for w in words:
            for i in range(len(w) - 2):
                features.append(w[i : i + 3])
        for i in range(len(words) - 1):
            features.append(f"{words[i]}_{words[i + 1]}")

        for feature in features:
            h = hashlib.md5(feature.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "big") % self.dimensions
            sign = 1.0 if h[4] & 1 else -1.0
            vector[idx] += sign

        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude > 0:
            vector = [v / magnitude for v in vector]
        return vector

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        return [await self.generate_embedding(t) for t in texts]


class CachedEmbeddingGenerator(IEmbeddingGenerator):
    """Decorator adding SHA256 caching and generation timeouts to an embedding generator."""

    def __init__(self, delegate: IEmbeddingGenerator, timeout: float = 10.0) -> None:
        """Initialize with a delegate generator and timeout boundary.

        Args:
            delegate: Underlying embedding generator.
            timeout: Generation timeout in seconds.
        """
        self.delegate = delegate
        self.timeout = timeout
        self._cache: Dict[str, List[float]] = {}
        self._hits = 0
        self._misses = 0

    def _hash(self, text: str) -> str:
        """Compute SHA256 content hash."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def generate_embedding(self, text: str) -> List[float]:
        """Get or generate embedding with timeout protection."""
        import asyncio

        h = self._hash(text)
        if h in self._cache:
            self._hits += 1
            return self._cache[h]

        self._misses += 1
        try:
            val = await asyncio.wait_for(
                self.delegate.generate_embedding(text), timeout=self.timeout
            )
            self._cache[h] = val
            return val
        except asyncio.TimeoutError as e:
            raise JarvisMemoryError(
                code="SYSTEM_999",
                message=f"Embedding generation timed out after {self.timeout}s",
            ) from e

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Batch query or generate embeddings with timeout protection."""
        import asyncio

        results: List[List[float]] = [[] for _ in texts]
        to_generate: List[str] = []
        indices: List[int] = []

        for idx, text in enumerate(texts):
            h = self._hash(text)
            if h in self._cache:
                self._hits += 1
                results[idx] = self._cache[h]
            else:
                self._misses += 1
                to_generate.append(text)
                indices.append(idx)

        if to_generate:
            try:
                vals = await asyncio.wait_for(
                    self.delegate.generate_embeddings(to_generate),
                    timeout=self.timeout,
                )
                for local_idx, val in enumerate(vals):
                    original_idx = indices[local_idx]
                    results[original_idx] = val
                    h_val = self._hash(to_generate[local_idx])
                    self._cache[h_val] = val
            except asyncio.TimeoutError as e:
                raise JarvisMemoryError(
                    code="SYSTEM_999",
                    message=f"Batch embedding generation timed out after {self.timeout}s",
                ) from e

        return results

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate ratio."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    @property
    def metrics(self) -> Dict[str, int]:
        """Return cache hit/miss count metrics."""
        return {"hits": self._hits, "misses": self._misses}
