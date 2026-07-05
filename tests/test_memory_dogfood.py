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

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.memory.database import db_manager
from core.memory.dto import MemoryTier
from core.memory.embeddings import MockEmbeddingGenerator
from core.memory.memory_context import MemoryContextBuilder
from core.memory.memory_engine import MemoryEngine
from core.memory.memory_scoring import MemoryScoring
from core.memory.memory_search import MemorySearch
from core.memory.models import Base
from core.memory.repository import PostgresMemoryRepository
from core.memory.vector_store import InMemoryVectorRepository


@pytest.mark.asyncio
async def test_memory_subsystem_dogfooding_flow() -> None:
    """End-to-end integration test validating the complete Memory Subsystem flow.

    Flow: Remember -> Store -> Search -> Retrieve -> Context Build -> Respond.
    """
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    # 1. Initialize Event Bus
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    # Create event listener list to capture published telemetry events
    captured_events = []

    async def event_listener(msg) -> None:
        captured_events.append(msg)

    await event_bus.subscribe("memory.created", event_listener)

    async with db_manager.session() as session:
        # Initialize Subsystem Core Repositories
        memory_repo = PostgresMemoryRepository(session)
        vector_repo = InMemoryVectorRepository()
        emb_generator = MockEmbeddingGenerator(dimensions=3)

        # 2. Initialize Memory Subsystem Components
        scoring = MemoryScoring()
        search = MemorySearch(
            memory_repo=memory_repo,
            vector_repo=vector_repo,
            embedding_generator=emb_generator,
            scoring=scoring,
        )
        context_builder = MemoryContextBuilder(default_max_tokens=2000)

        engine = MemoryEngine(
            memory_repo=memory_repo,
            scoring=scoring,
            search=search,
            context_builder=context_builder,
            event_bus=event_bus,
            l1_max_items=10,
        )

        # -------------------------------------------------------------
        # STEP A: Remember & Store (Write memory)
        # -------------------------------------------------------------
        fact_content = "JARVIS OS was established in 2026 by an advanced AI team."
        memory_id = await engine.store(
            content=fact_content,
            source_type="user_input",
            importance=0.9,
            confidence=1.0,
        )
        await session.commit()

        # Assert ID exists
        assert memory_id is not None

        # Verify background event arrived
        await asyncio.sleep(0.05)
        assert len(captured_events) == 1
        assert captured_events[0].body["memory_id"] == str(memory_id)

        # -------------------------------------------------------------
        # STEP B: Search (Hybrid query)
        # -------------------------------------------------------------
        # Mock vector store search to find our seeded memory
        # In a real run, the indexer consumes memory.created to generate vector matches.
        # Here we mock the vector search return for this integration test scope.
        chunk_dto = await memory_repo.get_chunk(memory_id)
        assert chunk_dto is not None
        vector_repo.search_vector = AsyncMock(
            return_value=[{"id": chunk_dto.id, "score": 0.95}]
        )

        search_results = await engine.search.search_hybrid(
            query="When was JARVIS OS established?",
            owner_id=memory_id,
            tier_filter=[MemoryTier.WORKING],
            min_score=0.3,
            limit=5,
        )

        assert len(search_results) == 1
        assert search_results[0].content == fact_content
        assert search_results[0].metadata.extra["retrieval_score"] > 0.0

        # -------------------------------------------------------------
        # STEP C: Retrieve (Direct UUID lookup from cache/L1)
        # -------------------------------------------------------------
        retrieved_record = await engine.retrieve(memory_id)
        assert retrieved_record is not None
        assert retrieved_record.content == fact_content

        # -------------------------------------------------------------
        # STEP D: Context Build
        # -------------------------------------------------------------
        goal_text = (
            "Ensure the new reasoning and planning subsystems have complete context."
        )
        context_package = engine.context_builder.build_context_package(
            current_goal=goal_text,
            conversation_history=[retrieved_record],
            personal_memories=[],
            knowledge_nodes=[],
        )

        context_str = context_package["context_string"]
        assert "### CURRENT GOAL" in context_str
        assert goal_text in context_str
        assert "### CONVERSATION HISTORY" in context_str
        assert fact_content in context_str
        assert context_package["tokens_used"] > 0

        # -------------------------------------------------------------
        # STEP E: Respond (LLM Prompt Assembly simulation)
        # -------------------------------------------------------------
        prompt = (
            f"You are the JARVIS Brain.\n"
            f"Given the active context below, answer the user query.\n\n"
            f"{context_str}\n\n"
            f"Query: Tell me about JARVIS OS establishment date."
        )

        assert "JARVIS OS was established in 2026" in prompt

    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()
