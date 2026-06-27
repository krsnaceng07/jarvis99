"""JARVIS OS - Knowledge Graph Layer Tests.

Verifies node/edge insertions, relation links, and cycle-resilient BFS traversal.
"""

from uuid import uuid4

import pytest

from core.config import Settings
from core.memory.database import db_manager
from core.memory.graph import PostgresKnowledgeGraphRepository
from core.memory.interfaces import MemoryNodeDTO, MemoryRelationDTO
from core.memory.models import Base


@pytest.mark.asyncio
async def test_knowledge_graph_traversal_and_cycles() -> None:
    """Verify BFS traversal depth boundaries and infinite loop cycle avoidance."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    # Create tables
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    async with db_manager.session() as session:
        repo = PostgresKnowledgeGraphRepository(session)

        # 1. Create a cyclic triangular node path: A -> B -> C -> A
        node_a = MemoryNodeDTO(id=uuid4(), name="Node A", type="concept")
        node_b = MemoryNodeDTO(id=uuid4(), name="Node B", type="concept")
        node_c = MemoryNodeDTO(id=uuid4(), name="Node C", type="concept")
        node_d = MemoryNodeDTO(id=uuid4(), name="Node D", type="concept")  # Isolated

        await repo.create_node(node_a)
        await repo.create_node(node_b)
        await repo.create_node(node_c)
        await repo.create_node(node_d)

        # Link A -> B
        await repo.create_relation(
            MemoryRelationDTO(
                source_node_id=node_a.id,
                target_node_id=node_b.id,
                relation_type="links",
            )
        )
        # Link B -> C
        await repo.create_relation(
            MemoryRelationDTO(
                source_node_id=node_b.id,
                target_node_id=node_c.id,
                relation_type="links",
            )
        )
        # Link C -> A (Creates cycle!)
        await repo.create_relation(
            MemoryRelationDTO(
                source_node_id=node_c.id,
                target_node_id=node_a.id,
                relation_type="links",
            )
        )
        # Link C -> D (Leaf node)
        await repo.create_relation(
            MemoryRelationDTO(
                source_node_id=node_c.id,
                target_node_id=node_d.id,
                relation_type="links",
            )
        )

        await session.commit()

    # Verify traversal and cycle resilience
    async with db_manager.session() as session:
        repo = PostgresKnowledgeGraphRepository(session)

        # Traversal Depth = 1: Should get A and its direct neighbor B
        results_depth_1 = await repo.traverse(node_a.id, max_depth=1)
        assert len(results_depth_1) == 2
        names_d1 = {n.name for n in results_depth_1}
        assert "Node A" in names_d1
        assert "Node B" in names_d1

        # Traversal Depth = 2: Should get A, B, and C
        results_depth_2 = await repo.traverse(node_a.id, max_depth=2)
        assert len(results_depth_2) == 3
        names_d2 = {n.name for n in results_depth_2}
        assert "Node A" in names_d2
        assert "Node B" in names_d2
        assert "Node C" in names_d2

        # Traversal Depth = 3: Should get A, B, C, and D
        # And cycle C -> A must be ignored without infinite loop crashes
        results_depth_3 = await repo.traverse(node_a.id, max_depth=3)
        assert len(results_depth_3) == 4
        names_d3 = {n.name for n in results_depth_3}
        assert "Node D" in names_d3

    await db_manager.close()
