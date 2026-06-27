"""JARVIS OS - Memory Subsystem Retrieval and Coverage Tests.

Tests retrieval engine, pgvector fallback repository, metadata updates, edge cases.
"""

import asyncio
from typing import List
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.exceptions import JarvisMemoryError
from core.interfaces import InterAgentMessage
from core.memory.database import db_manager
from core.memory.embeddings import CachedEmbeddingGenerator, MockEmbeddingGenerator
from core.memory.graph import PostgresKnowledgeGraphRepository
from core.memory.indexer import MemoryIndexer
from core.memory.interfaces import (
    MemoryChunkDTO,
    MemoryNode,
    MemoryNodeDTO,
    MemoryRelationDTO,
    MemorySourceDTO,
    RetrievalQuery,
)
from core.memory.models import Base
from core.memory.repository import PostgresMemoryRepository
from core.memory.service import MemoryService
from core.memory.vector_store import (
    InMemoryVectorRepository,
    PostgresVectorRepository,
)


@pytest.mark.asyncio
async def test_database_manager_postgres_init() -> None:
    """Verify database initialization paths for PostgreSQL and coverage for init configs."""
    settings = Settings.load_settings()
    # Force settings database host to not be sqlite/memory
    settings.database.host = "localhost"
    settings.database.username = "postgres"
    settings.database.password = "password"
    settings.database.name = "jarvis_test"
    settings.database.port = 5432

    # Initialize postgres connection url mapping (should build pg url and create postgres engine)
    db_manager.init(settings)
    assert db_manager._engine is not None
    await db_manager.close()

    # Re-init for other tests with sqlite
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
    async with db_manager._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_embeddings_extra_coverage() -> None:
    """Verify missing coverage lines in embeddings.py (batch, timeout, zero hit rate)."""
    delegate = MockEmbeddingGenerator(dimensions=4)

    # 1. Batch generate on MockEmbeddingGenerator
    res = await delegate.generate_embeddings(["first", "second"])
    assert len(res) == 2
    assert len(res[0]) == 4

    # 2. Zero hit rate check
    cached = CachedEmbeddingGenerator(delegate, timeout=5.0)
    assert cached.hit_rate == 0.0

    # 3. Batch generate on CachedEmbeddingGenerator (mix of hits and misses)
    await cached.generate_embedding("hello")  # Miss 1
    # Batch call
    batch_res = await cached.generate_embeddings(
        ["hello", "world"]
    )  # "hello" is hit, "world" is miss
    assert len(batch_res) == 2
    assert cached.metrics["hits"] == 1
    assert cached.metrics["misses"] == 2

    # 4. Batch timeout check
    class DelayedMock(MockEmbeddingGenerator):
        async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
            await asyncio.sleep(0.5)
            return [[0.1] * 4 for _ in texts]

    slow_delegate = DelayedMock(dimensions=4)
    cached_slow = CachedEmbeddingGenerator(slow_delegate, timeout=0.05)
    with pytest.raises(JarvisMemoryError) as exc_info:
        await cached_slow.generate_embeddings(["timeout1", "timeout2"])
    assert "timed out" in exc_info.value.message


@pytest.mark.asyncio
async def test_postgres_vector_repository_mocks() -> None:
    """Verify PostgresVectorRepository SQL executions via mock AsyncSession."""
    mock_session = AsyncMock()
    repo = PostgresVectorRepository(session=mock_session, dimensions=8)

    # 1. Initialize repository (creates pgvector extension, table, and HNSW index)
    await repo.initialize()
    assert mock_session.execute.call_count == 3
    assert mock_session.commit.call_count == 1

    # Initialize error path
    mock_session.execute.side_effect = RuntimeError("DB connection failure")
    with pytest.raises(JarvisMemoryError) as exc_info:
        await repo.initialize()
    assert "Failed initializing pgvector tables" in exc_info.value.message
    assert mock_session.rollback.call_count == 1

    # Reset mock
    mock_session.execute.side_effect = None
    mock_session.execute.reset_mock()

    # 2. Add Vector
    # Dimension mismatch error
    with pytest.raises(JarvisMemoryError) as exc_info:
        await repo.add_vector(uuid4(), [0.1, 0.2], {})
    assert "dimension mismatch" in exc_info.value.message

    # Successful insert
    mock_session.execute.return_value = MagicMock()
    success = await repo.add_vector(uuid4(), [0.1] * 8, {"key": "val"})
    assert success
    assert mock_session.execute.call_count == 1

    # Database error during insert
    mock_session.execute.side_effect = RuntimeError("Insert error")
    with pytest.raises(JarvisMemoryError) as exc_info:
        await repo.add_vector(uuid4(), [0.1] * 8, {"key": "val"})
    assert "Failed adding vector to Postgres" in exc_info.value.message

    # Reset mock
    mock_session.execute.side_effect = None
    mock_session.execute.reset_mock()

    # 3. Search Vector
    # Success without filter
    mock_rows = [
        (uuid4(), {"key": "val"}, 0.95),
        (uuid4(), '{"key": "val2"}', 0.85),
    ]
    mock_execute_res = MagicMock()
    mock_execute_res.all.return_value = mock_rows
    mock_session.execute.return_value = mock_execute_res

    results = await repo.search_vector([0.1] * 8, limit=5)
    assert len(results) == 2
    assert results[0]["score"] == 0.95
    assert results[1]["metadata"]["key"] == "val2"

    # Search with filter
    results_filtered = await repo.search_vector(
        [0.1] * 8, limit=5, filter_criteria={"key": "val"}
    )
    assert len(results_filtered) == 2

    # Search failure
    mock_session.execute.side_effect = RuntimeError("Search error")
    with pytest.raises(JarvisMemoryError) as exc:
        await repo.search_vector([0.1] * 8, limit=5)
    assert "Vector search failed" in exc.value.message

    # Reset mock
    mock_session.execute.side_effect = None
    mock_session.execute.reset_mock()

    # 4. Delete Vector
    mock_res_delete = MagicMock()
    mock_res_delete.rowcount = 1
    mock_session.execute.return_value = mock_res_delete
    deleted = await repo.delete_vector(uuid4())
    assert deleted

    # Delete failure
    mock_session.execute.side_effect = RuntimeError("Delete error")
    with pytest.raises(JarvisMemoryError) as exc:
        await repo.delete_vector(uuid4())
    assert "Failed deleting vector" in exc.value.message


@pytest.mark.asyncio
async def test_relational_repository_edge_cases() -> None:
    """Verify PostgresMemoryRepository edge cases under SQLite in-memory execution."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    async with db_manager.session() as session:
        repo = PostgresMemoryRepository(session)

        # 1. Source get/create checks
        source_id = uuid4()
        # Retrieve missing source
        assert await repo.get_source(source_id) is None

        # Create source
        src_dto = MemorySourceDTO(
            id=source_id,
            source_type="file",
            uri="file:///test.py",
            agent_id="TestAgent",
            confidence=0.9,
            version="1.0",
        )
        created_src = await repo.create_source(src_dto)
        assert created_src.id == source_id
        assert created_src.uri == "file:///test.py"

        # Retrieve existing source
        fetched_src = await repo.get_source(source_id)
        assert fetched_src is not None
        assert fetched_src.agent_id == "TestAgent"

        # 2. Chunk get/update/delete checks
        chunk_id = uuid4()
        # Retrieve missing chunk
        assert await repo.get_chunk(chunk_id) is None

        # Create chunk
        chunk_dto = MemoryChunkDTO(
            id=chunk_id,
            source_id=source_id,
            content="Testing edge cases content",
            content_hash="hash_edge_case",
            token_count=4,
            metadata={"orig": "meta"},
        )
        created_chunk = await repo.create_chunk(chunk_dto)
        assert created_chunk.id == chunk_id

        # Retrieve existing chunk by hash
        fetched_hash = await repo.get_chunk_by_hash("hash_edge_case")
        assert fetched_hash is not None
        assert fetched_hash.id == chunk_id

        # Update chunk (success - testing properties modification and metadata update)
        updated = await repo.update_chunk(
            chunk_id,
            current_version=1,
            updated_fields={"content": "New content text", "metadata": {"new": "val"}},
        )
        assert updated is not None
        assert updated.content == "New content text"
        assert updated.version == 2
        assert updated.metadata == {"new": "val"}

        # Update chunk - non-existing ID returns None
        assert (
            await repo.update_chunk(uuid4(), current_version=1, updated_fields={})
            is None
        )

        # Update chunk - version mismatch returns None
        assert (
            await repo.update_chunk(chunk_id, current_version=1, updated_fields={})
            is None
        )

        # Keyword search chunks matching
        keyword_results = await repo.keyword_search_chunks("New content", limit=5)
        assert len(keyword_results) == 1
        assert keyword_results[0].id == chunk_id

        # Soft delete chunk
        assert await repo.soft_delete_chunk(chunk_id) is True
        # Verify get_chunk returns None post soft-delete
        assert await repo.get_chunk(chunk_id) is None

        # Soft delete missing chunk returns False
        assert await repo.soft_delete_chunk(uuid4()) is False


@pytest.mark.asyncio
async def test_knowledge_graph_edge_cases() -> None:
    """Verify PostgresKnowledgeGraphRepository edge cases."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    async with db_manager.session() as session:
        repo = PostgresKnowledgeGraphRepository(session)

        node_id = uuid4()
        # 1. Fetch missing node
        assert await repo.get_node(node_id) is None

        # 2. Traverse with missing start node ID returns empty list
        assert await repo.traverse(node_id) == []

        # 3. Create node
        node_dto = MemoryNodeDTO(
            id=node_id,
            name="Source Node",
            type="concept",
            properties={"a": 1},
        )
        created_node = await repo.create_node(node_dto)
        assert created_node.id == node_id

        # 4. Fetch relations of isolated node returns empty list
        relations = await repo.get_relations(node_id)
        assert len(relations) == 0

        # 5. Update existing node
        updated_node = await repo.update_node(
            node_id,
            updated_fields={"name": "Updated Name", "properties": {"b": 2}},
        )
        assert updated_node is not None
        assert updated_node.name == "Updated Name"
        assert updated_node.properties == {"b": 2}

        # 6. Update missing node returns None
        assert await repo.update_node(uuid4(), {}) is None

        # 7. Create target node and edge to retrieve relations
        target_id = uuid4()
        target_dto = MemoryNodeDTO(id=target_id, name="Target Node", type="concept")
        await repo.create_node(target_dto)

        relation_dto = MemoryRelationDTO(
            id=uuid4(),
            source_node_id=node_id,
            target_node_id=target_id,
            relation_type="links_to",
            weight=0.8,
            confidence=0.9,
        )
        await repo.create_relation(relation_dto)

        # Retrieve relations
        rels = await repo.get_relations(node_id)
        assert len(rels) == 1
        assert rels[0].relation_type == "links_to"
        assert rels[0].source_node_id == node_id
        assert rels[0].target_node_id == target_id


@pytest.mark.asyncio
async def test_memory_indexer_edge_cases() -> None:
    """Verify MemoryIndexer edge cases, idempotency, missing chunk rows, and deletion handlers."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    # Use a local isolated event bus
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    async with db_manager.session() as session:
        memory_repo = PostgresMemoryRepository(session)
        vector_repo = InMemoryVectorRepository()
        graph_repo = PostgresKnowledgeGraphRepository(session)
        emb_gen = MockEmbeddingGenerator(dimensions=4)

        indexer = MemoryIndexer(
            memory_repo=memory_repo,
            vector_repo=vector_repo,
            graph_repo=graph_repo,
            embedding_generator=emb_gen,
            event_bus=event_bus,
        )
        await indexer.initialize()

        # 1. handle_chunk_created with missing event_id or chunk_id body
        msg_missing = InterAgentMessage(
            sender="Test", receiver="Indexer", action="chunk_created", body={}
        )
        # Should return early without exceptions
        await indexer.handle_chunk_created(msg_missing)

        # 2. handle_chunk_created when database chunk row is missing (e.g. deleted before indexing)
        event_id = uuid4()
        missing_chunk_id = uuid4()
        msg_missing_row = InterAgentMessage(
            sender="Test",
            receiver="Indexer",
            action="chunk_created",
            body={"event_id": str(event_id), "chunk_id": str(missing_chunk_id)},
        )
        # Should gracefully complete/return success=True inside handler without writing to vector_repo
        await indexer.handle_chunk_created(msg_missing_row)
        assert len(vector_repo.vectors) == 0

        # 3. Idempotency check: process identical event_id twice
        # First, add the chunk to memory db so it can be indexed
        chunk_id = uuid4()
        chunk_dto = MemoryChunkDTO(
            id=chunk_id,
            source_id=uuid4(),
            content="Idempotency test chunk",
            content_hash="hash_idemp",
            token_count=3,
        )
        await memory_repo.create_chunk(chunk_dto)
        await session.commit()

        event_id_idemp = uuid4()
        msg_idemp = InterAgentMessage(
            sender="Test",
            receiver="Indexer",
            action="chunk_created",
            body={"event_id": str(event_id_idemp), "chunk_id": str(chunk_id)},
        )
        # First process
        await indexer.handle_chunk_created(msg_idemp)
        assert len(vector_repo.vectors) == 1

        # Modify vector record in repo to test idempotency bypass
        vector_repo.vectors[chunk_id] = [9.9] * 4

        # Second process (should return early without rewriting vector)
        await indexer.handle_chunk_created(msg_idemp)
        assert vector_repo.vectors[chunk_id] == [9.9] * 4

        # 4. Deletion event handling
        msg_delete = InterAgentMessage(
            sender="Test",
            receiver="Indexer",
            action="chunk_deleted",
            body={"chunk_id": str(chunk_id)},
        )
        await indexer.handle_chunk_deleted(msg_delete)
        # Vector record should be removed
        assert chunk_id not in vector_repo.vectors

        # Deletion event with missing body parameters does not crash
        msg_delete_empty = InterAgentMessage(
            sender="Test", receiver="Indexer", action="chunk_deleted", body={}
        )
        await indexer.handle_chunk_deleted(msg_delete_empty)

    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()


@pytest.mark.asyncio
async def test_retrieval_engine_and_memory_service_orchestration() -> None:
    """Verify RetrievalEngine search streams, RRF ranking, budgets, and MemoryService updates/deletes."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    # Use isolated event bus
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    async with db_manager.session() as session:
        memory_repo = PostgresMemoryRepository(session)
        vector_repo = InMemoryVectorRepository()
        graph_repo = PostgresKnowledgeGraphRepository(session)
        emb_gen = MockEmbeddingGenerator(dimensions=4)

        service = MemoryService(
            settings, memory_repo, vector_repo, graph_repo, emb_gen, event_bus
        )

        # Seed multiple chunks for search queries
        node1 = MemoryNode(
            content="Apples are sweet red fruits", metadata={}, importance=0.8
        )
        node2 = MemoryNode(
            content="Oranges are citrus round fruits", metadata={}, importance=0.7
        )
        node3 = MemoryNode(
            content="Bananas are curved yellow fruits", metadata={}, importance=0.9
        )

        id1 = await service.store(node1)
        id2 = await service.store(node2)
        id3 = await service.store(node3)
        await session.commit()

        # Let the service generate vectors in the vector repo directly for the retrieval engine
        # (Usually this runs in indexer background, we populate vector repo manually for clean test)
        await vector_repo.add_vector(
            id1, await emb_gen.generate_embedding(node1.content), {"source_id": "src1"}
        )
        await vector_repo.add_vector(
            id2, await emb_gen.generate_embedding(node2.content), {"source_id": "src2"}
        )
        await vector_repo.add_vector(
            id3, await emb_gen.generate_embedding(node3.content), {"source_id": "src3"}
        )

        # 1. Test search_vector_similarity with min_score filtering
        # Lower min_score matches all
        matches_all = await service.retrieval_engine.search_vector_similarity(
            "fruits", limit=5, min_score=-2.0
        )
        assert len(matches_all) == 3

        # Higher min_score filters out matches
        matches_filtered = await service.retrieval_engine.search_vector_similarity(
            "Apples", limit=5, min_score=0.99
        )
        # Should filter out non-apple fruits
        assert len(matches_filtered) < 3

        # 2. Test search_hybrid_rrf
        rrf_results = await service.retrieval_engine.search_hybrid_rrf(
            "citrus fruits", limit=2
        )
        assert len(rrf_results) <= 2
        # Verify rrf_score was injected in metadata
        for r in rrf_results:
            assert "rrf_score" in r.metadata

        # 3. Test retrieve_with_budget (token limit, min relevance, and graph traversal)
        # Large token budget allows all
        budget_all = await service.retrieval_engine.retrieve_with_budget(
            "yellow fruits", max_tokens=1000
        )
        assert len(budget_all["chunks"]) > 0

        # Small token budget drops chunks that overflow
        budget_small = await service.retrieval_engine.retrieve_with_budget(
            "fruits", max_tokens=5
        )
        # Individual chunk might have more tokens than 5, so chunks list should be smaller/empty
        for c in budget_small["chunks"]:
            assert c.token_count <= 5

        # 4. Test MemoryService.retrieve DTO translation
        query = RetrievalQuery(query_text="citrus round", limit=2, depth=0)
        nodes = await service.retrieve(query)
        assert len(nodes) > 0
        assert isinstance(nodes[0], MemoryNode)

        # 5. Test MemoryService.update
        # Update missing ID returns False
        assert await service.update(uuid4(), {"content": "ghost"}) is False

        # Update existing content and verify hash recalculation and version increment
        updated_ok = await service.update(
            id1, {"content": "Apples are extremely tasty", "metadata": {"tasty": True}}
        )
        assert updated_ok
        await session.commit()

        updated_chunk = await memory_repo.get_chunk(id1)
        assert updated_chunk is not None
        assert updated_chunk.content == "Apples are extremely tasty"
        assert updated_chunk.content_hash == service._hash("Apples are extremely tasty")
        assert updated_chunk.metadata.get("tasty") is True
        # access_count and importance should be preserved
        assert updated_chunk.metadata.get("importance") == 0.8

        # 6. Test MemoryService.delete
        # Delete missing ID returns False
        assert await service.delete(uuid4()) is False

        # Delete existing ID publishes event and soft-deletes
        assert await service.delete(id1) is True
        await session.commit()
        # Verify chunk is soft deleted
        assert await memory_repo.get_chunk(id1) is None

        # 7. Test forget method returns 0
        assert await service.forget({}) == 0

    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()
