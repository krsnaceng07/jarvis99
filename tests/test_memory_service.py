"""JARVIS OS - Memory Subsystem Integration Tests.

Verifies end-to-end CRUD, deduplication, retry queues, DLQs, and search benchmarks.
"""

import asyncio
import time
from typing import List
from uuid import UUID, uuid4

import pytest

from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.interfaces import InterAgentMessage
from core.memory.database import db_manager
from core.memory.embeddings import MockEmbeddingGenerator
from core.memory.graph import PostgresKnowledgeGraphRepository
from core.memory.indexer import MemoryIndexer
from core.memory.interfaces import (
    IEmbeddingGenerator,
    MemoryChunkDTO,
    MemoryNode,
)
from core.memory.models import Base
from core.memory.repository import PostgresMemoryRepository
from core.memory.service import MemoryService
from core.memory.vector_store import InMemoryVectorRepository


class FailingEmbeddingGenerator(IEmbeddingGenerator):
    """Embedding generator that fails a configured number of times before succeeding."""

    def __init__(self, fail_count: int) -> None:
        self.fail_count = fail_count
        self.call_count = 0

    async def generate_embedding(self, text: str) -> List[float]:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise RuntimeError("Temporary network failure")
        return [0.1, 0.2, 0.3]

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise RuntimeError("Temporary network failure")
        return [[0.1, 0.2, 0.3] for _ in texts]


@pytest.mark.asyncio
async def test_memory_service_deduplication_and_crud() -> None:
    """Verify storing duplicate memory text increments AccessCount instead of writing rows."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    # Initialize components
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    async with db_manager.session() as session:
        memory_repo = PostgresMemoryRepository(session)
        vector_repo = InMemoryVectorRepository()
        graph_repo = PostgresKnowledgeGraphRepository(session)
        emb_gen = MockEmbeddingGenerator(dimensions=3)

        service = MemoryService(
            settings, memory_repo, vector_repo, graph_repo, emb_gen, event_bus
        )

        node = MemoryNode(content="Exact deduplication test text", metadata={})

        # 1. First write: persists record
        chunk_id1 = await service.store(node)
        await session.commit()

        # Fetch chunk to verify it exists
        chunk1 = await memory_repo.get_chunk(chunk_id1)
        assert chunk1 is not None
        assert chunk1.metadata.get("access_count") == 1

        # 2. Second write with identical text: returns original ID, increments access_count
        chunk_id2 = await service.store(node)
        await session.commit()

        assert chunk_id1 == chunk_id2

        # Fetch updated chunk to verify access count increment
        chunk2 = await memory_repo.get_chunk(chunk_id1)
        assert chunk2 is not None
        assert chunk2.metadata.get("access_count") == 2

    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()


@pytest.mark.asyncio
async def test_event_driven_indexing_retry_and_dlq() -> None:
    """Verify indexer retry loop attempts re-processing and falls back to DLQ on exhaustion."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    # 1. Setup Failing Embedding Generator (fails 2 times, succeeds on 3rd)
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    vector_repo = InMemoryVectorRepository()
    dlq_messages: List[InterAgentMessage] = []

    async def dlq_callback(msg: InterAgentMessage) -> None:
        dlq_messages.append(msg)

    await event_bus.subscribe("memory.index.failed", dlq_callback)

    failing_generator = FailingEmbeddingGenerator(fail_count=2)

    async with db_manager.session() as session:
        memory_repo = PostgresMemoryRepository(session)
        graph_repo = PostgresKnowledgeGraphRepository(session)

        indexer = MemoryIndexer(
            memory_repo=memory_repo,
            vector_repo=vector_repo,
            graph_repo=graph_repo,
            embedding_generator=failing_generator,
            event_bus=event_bus,
        )
        await indexer.initialize()

        # Seed relational chunk
        chunk_id = uuid4()
        chunk_dto = MemoryChunkDTO(
            id=chunk_id,
            source_id=uuid4(),
            content="Retry test content",
            content_hash="hash123",
            token_count=3,
        )
        await memory_repo.create_chunk(chunk_dto)
        await session.commit()

        # Trigger chunk creation event
        event_msg = InterAgentMessage(
            sender="Test",
            receiver="Indexer",
            action="chunk_created",
            body={"chunk_id": str(chunk_id), "event_id": str(uuid4())},
        )
        await event_bus.publish("memory.chunk.created", event_msg)

        # Allow indexer to execute background retries
        for _ in range(100):
            if len(vector_repo.vectors) == 1:
                break
            await asyncio.sleep(0.01)

        # Verify indexing succeeded after retries (call_count should be 3)
        assert failing_generator.call_count == 3
        # Vector record should exist in repository
        assert len(vector_repo.vectors) == 1
        assert chunk_id in vector_repo.vectors
        assert len(dlq_messages) == 0

    await event_bus.stop()
    await event_bus.shutdown()

    # 2. Setup Consistently Failing Generator (fails 5 times, exceeds max_attempts=3)
    event_bus_exhaust = MemoryEventBus()
    await event_bus_exhaust.initialize()
    await event_bus_exhaust.start()

    dlq_messages_exhaust: List[InterAgentMessage] = []

    async def dlq_callback_exhaust(msg: InterAgentMessage) -> None:
        dlq_messages_exhaust.append(msg)

    await event_bus_exhaust.subscribe("memory.index.failed", dlq_callback_exhaust)

    failing_generator_exhaust = FailingEmbeddingGenerator(fail_count=5)
    vector_repo_exhaust = InMemoryVectorRepository()

    async with db_manager.session() as session:
        memory_repo = PostgresMemoryRepository(session)
        graph_repo = PostgresKnowledgeGraphRepository(session)

        indexer_exhaust = MemoryIndexer(
            memory_repo=memory_repo,
            vector_repo=vector_repo_exhaust,
            graph_repo=graph_repo,
            embedding_generator=failing_generator_exhaust,
            event_bus=event_bus_exhaust,
        )
        await indexer_exhaust.initialize()

        chunk_id_fail = uuid4()
        chunk_dto_fail = MemoryChunkDTO(
            id=chunk_id_fail,
            source_id=uuid4(),
            content="Exhaust retry test content",
            content_hash="hash456",
            token_count=3,
        )
        await memory_repo.create_chunk(chunk_dto_fail)
        await session.commit()

        event_msg_fail = InterAgentMessage(
            sender="Test",
            receiver="Indexer",
            action="chunk_created",
            body={"chunk_id": str(chunk_id_fail), "event_id": str(uuid4())},
        )
        await event_bus_exhaust.publish("memory.chunk.created", event_msg_fail)

        # Allow indexer to execute background retries
        for _ in range(100):
            if len(dlq_messages_exhaust) == 1:
                break
            await asyncio.sleep(0.01)

        # Verify failed attempts occurred (max_attempts = 3)
        assert failing_generator_exhaust.call_count == 3
        # Vector should NOT be stored
        assert len(vector_repo_exhaust.vectors) == 0
        # Dead Letter Queue should receive the failure notification
        assert len(dlq_messages_exhaust) == 1
        assert dlq_messages_exhaust[0].body["chunk_id"] == str(chunk_id_fail)
        assert dlq_messages_exhaust[0].body["attempts"] == 3
        assert "Temporary network failure" in dlq_messages_exhaust[0].body["error"]

    await event_bus_exhaust.stop()
    await event_bus_exhaust.shutdown()
    await db_manager.close()


@pytest.mark.asyncio
async def test_large_scale_vector_search_benchmark() -> None:
    """Benchmark local vector search latency over a large corpus of 100,000 vectors."""
    repo = InMemoryVectorRepository()
    await repo.initialize()

    # Generate 100,000 mock vectors (each of dimension 128)
    dimensions = 128
    record_count = 100000

    print(f"\nSeeding {record_count} vectors into in-memory repository...")
    int(time.time())

    # Bulk seed (mocking loop)
    for i in range(record_count):
        vid = UUID(int=i)
        # Create different vector coordinates
        vec = [(float(i) * 0.001 + float(j) * 0.01) % 1.0 for j in range(dimensions)]
        await repo.add_vector(vid, vec, {"index": i})

    assert len(repo.vectors) == record_count

    # Execute search query and measure performance
    query_vector = [0.5 for _ in range(dimensions)]

    t0 = time.perf_counter()
    results = await repo.search_vector(query_vector, limit=10)
    t1 = time.perf_counter()

    latency_ms = (t1 - t0) * 1000
    print(f"Search query latency over 100,000 records: {latency_ms:.2f} ms")

    # Assert search returned correct quantity and completed in reasonable time (< 2000ms)
    assert len(results) == 10
    assert latency_ms < 2000.0
