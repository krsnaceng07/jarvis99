"""
PHASE: 38
STATUS: IMPLEMENTATION — Tests
SPECIFICATION:
    docs/100_PHASE_38_UNIFIED_MEMORY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/PHASE_38_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from unittest.mock import MagicMock

import pytest

from core.memory.consolidation import MemoryConsolidation
from core.memory.context_assembly import ContextAssembly
from core.memory.episodic_memory import EpisodicMemory
from core.memory.knowledge_graph import KnowledgeGraph
from core.memory.long_term_memory import LongTermMemory
from core.memory.memory_coordinator import MemoryCoordinator
from core.memory.procedural_memory import ProceduralMemory
from core.memory.semantic_memory import SemanticMemory
from core.memory.working_memory import WorkingMemory

# ─────────────────────────────────────────────────────────────
# WorkingMemory
# ─────────────────────────────────────────────────────────────


def test_working_memory_set_and_get() -> None:
    wm = WorkingMemory()
    wm.set("mission", "deploy-v2")
    assert wm.get("mission") == "deploy-v2"


def test_working_memory_get_default() -> None:
    wm = WorkingMemory()
    assert wm.get("nonexistent", "fallback") == "fallback"


def test_working_memory_clear() -> None:
    wm = WorkingMemory()
    wm.set("key", "value")
    wm.clear()
    assert wm.export() == {}


def test_working_memory_export() -> None:
    wm = WorkingMemory()
    wm.set("goal", "test-goal")
    wm.set("budget", 100)
    snapshot = wm.export()
    assert snapshot == {"goal": "test-goal", "budget": 100}


def test_working_memory_export_is_copy() -> None:
    wm = WorkingMemory()
    wm.set("x", 1)
    snapshot = wm.export()
    snapshot["x"] = 99
    assert wm.get("x") == 1


# ─────────────────────────────────────────────────────────────
# LongTermMemory
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_long_term_memory_save_and_search() -> None:
    ltm = LongTermMemory(db_manager=MagicMock())
    await ltm.save_experience({"goal": "deploy-v2", "outcome": "success"})
    results = await ltm.search_semantic("deploy", limit=5)
    assert len(results) == 1
    assert results[0]["goal"] == "deploy-v2"


@pytest.mark.asyncio
async def test_long_term_memory_search_no_match() -> None:
    ltm = LongTermMemory(db_manager=MagicMock())
    await ltm.save_experience({"goal": "deploy-v2", "outcome": "success"})
    results = await ltm.search_semantic("nonexistent-query", limit=5)
    assert results == []


@pytest.mark.asyncio
async def test_long_term_memory_limit_respected() -> None:
    ltm = LongTermMemory(db_manager=MagicMock())
    for i in range(10):
        await ltm.save_experience({"goal": f"deploy-v{i}"})
    results = await ltm.search_semantic("deploy", limit=3)
    assert len(results) <= 3


# ─────────────────────────────────────────────────────────────
# KnowledgeGraph
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_knowledge_graph_add_entity() -> None:
    kg = KnowledgeGraph()
    await kg.add_entity("jarvis", "system", {"version": "38"})
    assert "jarvis" in kg.nodes
    assert kg.nodes["jarvis"]["type"] == "system"


@pytest.mark.asyncio
async def test_knowledge_graph_add_relation() -> None:
    kg = KnowledgeGraph()
    await kg.add_entity("jarvis", "system", {})
    await kg.add_entity("memory", "subsystem", {})
    await kg.add_relation("jarvis", "memory", "HAS_SUBSYSTEM")
    assert ("jarvis", "memory", "HAS_SUBSYSTEM") in kg.relations


@pytest.mark.asyncio
async def test_knowledge_graph_get_neighbors() -> None:
    kg = KnowledgeGraph()
    await kg.add_entity("jarvis", "system", {})
    await kg.add_entity("memory", "subsystem", {})
    await kg.add_entity("brain_kernel", "subsystem", {})
    await kg.add_relation("jarvis", "memory", "HAS_SUBSYSTEM")
    await kg.add_relation("jarvis", "brain_kernel", "HAS_SUBSYSTEM")
    neighbors = await kg.get_neighbors("jarvis")
    assert len(neighbors) == 2
    neighbor_names = [n[0] for n in neighbors]
    assert "memory" in neighbor_names
    assert "brain_kernel" in neighbor_names


@pytest.mark.asyncio
async def test_knowledge_graph_no_neighbors() -> None:
    kg = KnowledgeGraph()
    await kg.add_entity("isolated", "system", {})
    neighbors = await kg.get_neighbors("isolated")
    assert neighbors == []


# ─────────────────────────────────────────────────────────────
# EpisodicMemory
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_episodic_memory_record_and_retrieve() -> None:
    em = EpisodicMemory()
    await em.record_episode({"mission_id": "m1", "goal": "deploy", "outcome": "success"})
    episodes = await em.get_recent_episodes(limit=5)
    assert len(episodes) == 1
    assert episodes[0]["mission_id"] == "m1"


@pytest.mark.asyncio
async def test_episodic_memory_limit_respected() -> None:
    em = EpisodicMemory()
    for i in range(10):
        await em.record_episode({"mission_id": f"m{i}"})
    episodes = await em.get_recent_episodes(limit=3)
    assert len(episodes) == 3


@pytest.mark.asyncio
async def test_episodic_memory_recent_order() -> None:
    em = EpisodicMemory()
    await em.record_episode({"mission_id": "first"})
    await em.record_episode({"mission_id": "second"})
    await em.record_episode({"mission_id": "third"})
    episodes = await em.get_recent_episodes(limit=2)
    ids = [e["mission_id"] for e in episodes]
    assert "second" in ids
    assert "third" in ids


# ─────────────────────────────────────────────────────────────
# SemanticMemory
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_semantic_memory_add_and_query() -> None:
    sm = SemanticMemory()
    await sm.add_fact({"concept": "deployment", "details": "Process of releasing a version"})
    facts = await sm.query_facts("deployment", limit=5)
    assert len(facts) == 1
    assert facts[0]["concept"] == "deployment"


@pytest.mark.asyncio
async def test_semantic_memory_query_no_match() -> None:
    sm = SemanticMemory()
    await sm.add_fact({"concept": "deployment", "details": "Release process"})
    facts = await sm.query_facts("nonexistent", limit=5)
    assert facts == []


@pytest.mark.asyncio
async def test_semantic_memory_query_matches_details() -> None:
    sm = SemanticMemory()
    await sm.add_fact({"concept": "infra", "details": "kubernetes cluster management"})
    facts = await sm.query_facts("kubernetes", limit=5)
    assert len(facts) == 1


# ─────────────────────────────────────────────────────────────
# ProceduralMemory
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_procedural_memory_register_and_retrieve() -> None:
    pm = ProceduralMemory()
    await pm.register_procedure("deploy-pipeline", ["build", "test", "deploy"])
    proc = await pm.get_procedure("deploy-pipeline")
    assert proc is not None
    assert proc["name"] == "deploy-pipeline"
    assert proc["steps"] == ["build", "test", "deploy"]


@pytest.mark.asyncio
async def test_procedural_memory_not_found() -> None:
    pm = ProceduralMemory()
    proc = await pm.get_procedure("nonexistent")
    assert proc is None


@pytest.mark.asyncio
async def test_procedural_memory_multiple_procedures() -> None:
    pm = ProceduralMemory()
    await pm.register_procedure("deploy", ["build", "deploy"])
    await pm.register_procedure("debug", ["reproduce", "isolate", "fix"])
    deploy_proc = await pm.get_procedure("deploy")
    debug_proc = await pm.get_procedure("debug")
    assert deploy_proc is not None
    assert debug_proc is not None
    assert deploy_proc["steps"][0] == "build"
    assert debug_proc["steps"][0] == "reproduce"


# ─────────────────────────────────────────────────────────────
# MemoryCoordinator
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_coordinator_retrieve_context_empty() -> None:
    coordinator = MemoryCoordinator(
        working_memory=WorkingMemory(),
        long_term_memory=LongTermMemory(db_manager=MagicMock()),
        knowledge_graph=KnowledgeGraph(),
        episodic_memory=EpisodicMemory(),
        semantic_memory=SemanticMemory(),
        procedural_memory=ProceduralMemory(),
    )
    result = await coordinator.retrieve_context("test query")
    assert "working_memory" in result
    assert "ranked_memories" in result
    assert "episodic_episodes" in result
    assert "graph_entities_count" in result


@pytest.mark.asyncio
async def test_memory_coordinator_retrieves_working_memory() -> None:
    wm = WorkingMemory()
    wm.set("active_goal", "deploy-v3")
    coordinator = MemoryCoordinator(
        working_memory=wm,
        long_term_memory=LongTermMemory(db_manager=MagicMock()),
        knowledge_graph=KnowledgeGraph(),
        episodic_memory=EpisodicMemory(),
        semantic_memory=SemanticMemory(),
        procedural_memory=ProceduralMemory(),
    )
    result = await coordinator.retrieve_context("deploy")
    assert result["working_memory"].get("active_goal") == "deploy-v3"


@pytest.mark.asyncio
async def test_memory_coordinator_ranked_memories_have_confidence() -> None:
    ltm = LongTermMemory(db_manager=MagicMock())
    await ltm.save_experience({"goal": "deploy-v3"})
    coordinator = MemoryCoordinator(
        working_memory=WorkingMemory(),
        long_term_memory=ltm,
        knowledge_graph=KnowledgeGraph(),
        episodic_memory=EpisodicMemory(),
        semantic_memory=SemanticMemory(),
        procedural_memory=ProceduralMemory(),
    )
    result = await coordinator.retrieve_context("deploy")
    for memory in result["ranked_memories"]:
        assert "confidence" in memory
        assert "relevance" in memory
        assert "type" in memory


@pytest.mark.asyncio
async def test_memory_coordinator_graph_entities_count() -> None:
    kg = KnowledgeGraph()
    await kg.add_entity("jarvis", "system", {})
    await kg.add_entity("memory", "subsystem", {})
    coordinator = MemoryCoordinator(
        working_memory=WorkingMemory(),
        long_term_memory=LongTermMemory(db_manager=MagicMock()),
        knowledge_graph=kg,
        episodic_memory=EpisodicMemory(),
        semantic_memory=SemanticMemory(),
        procedural_memory=ProceduralMemory(),
    )
    result = await coordinator.retrieve_context("query")
    assert result["graph_entities_count"] == 2


# ─────────────────────────────────────────────────────────────
# ContextAssembly
# ─────────────────────────────────────────────────────────────


def _make_coordinator() -> MemoryCoordinator:
    return MemoryCoordinator(
        working_memory=WorkingMemory(),
        long_term_memory=LongTermMemory(db_manager=MagicMock()),
        knowledge_graph=KnowledgeGraph(),
        episodic_memory=EpisodicMemory(),
        semantic_memory=SemanticMemory(),
        procedural_memory=ProceduralMemory(),
    )


@pytest.mark.asyncio
async def test_context_assembly_structure() -> None:
    assembler = ContextAssembly(memory_coordinator=_make_coordinator())
    ctx = await assembler.assemble_context("deploy")
    assert "query" in ctx
    assert "working_memory" in ctx
    assert "ranked_memories" in ctx
    assert "episodic_memory" in ctx
    assert "knowledge_graph_entities_count" in ctx


@pytest.mark.asyncio
async def test_context_assembly_preserves_query() -> None:
    assembler = ContextAssembly(memory_coordinator=_make_coordinator())
    ctx = await assembler.assemble_context("specific-query")
    assert ctx["query"] == "specific-query"


@pytest.mark.asyncio
async def test_context_assembly_reflects_working_memory() -> None:
    wm = WorkingMemory()
    wm.set("mission_id", "m-test")
    coordinator = MemoryCoordinator(
        working_memory=wm,
        long_term_memory=LongTermMemory(db_manager=MagicMock()),
        knowledge_graph=KnowledgeGraph(),
        episodic_memory=EpisodicMemory(),
        semantic_memory=SemanticMemory(),
        procedural_memory=ProceduralMemory(),
    )
    assembler = ContextAssembly(memory_coordinator=coordinator)
    ctx = await assembler.assemble_context("deploy")
    assert ctx["working_memory"].get("mission_id") == "m-test"


# ─────────────────────────────────────────────────────────────
# MemoryConsolidation
# ─────────────────────────────────────────────────────────────


def _make_consolidation() -> MemoryConsolidation:
    return MemoryConsolidation(
        episodic_memory=EpisodicMemory(),
        long_term_memory=LongTermMemory(db_manager=MagicMock()),
        semantic_memory=SemanticMemory(),
        knowledge_graph=KnowledgeGraph(),
    )


@pytest.mark.asyncio
async def test_consolidation_empty_cycle() -> None:
    consolidation = _make_consolidation()
    stats = await consolidation.consolidate()
    assert stats == {
        "episodes_processed": 0,
        "facts_created": 0,
        "entities_created": 0,
        "relations_created": 0,
    }


@pytest.mark.asyncio
async def test_consolidation_persists_to_long_term_memory() -> None:
    consolidation = _make_consolidation()
    await consolidation.episodic_memory.record_episode(
        {"mission_id": "m1", "goal": "deploy-v2", "outcome": "success"}
    )
    stats = await consolidation.consolidate()
    assert stats["episodes_processed"] == 1
    records = await consolidation.long_term_memory.search_semantic("deploy", limit=5)
    assert len(records) == 1
    assert records[0]["mission_id"] == "m1"


@pytest.mark.asyncio
async def test_consolidation_creates_semantic_fact() -> None:
    consolidation = _make_consolidation()
    await consolidation.episodic_memory.record_episode(
        {"mission_id": "m1", "goal": "deploy-v2", "outcome": "success"}
    )
    stats = await consolidation.consolidate()
    assert stats["facts_created"] == 1
    facts = await consolidation.semantic_memory.query_facts("deploy-v2", limit=5)
    assert len(facts) == 1
    assert "success" in facts[0]["details"]


@pytest.mark.asyncio
async def test_consolidation_creates_graph_triples() -> None:
    consolidation = _make_consolidation()
    await consolidation.episodic_memory.record_episode(
        {"mission_id": "m1", "goal": "deploy-v2", "outcome": "success"}
    )
    stats = await consolidation.consolidate()
    assert stats["entities_created"] == 2
    assert stats["relations_created"] == 1
    assert "m1" in consolidation.knowledge_graph.nodes
    assert "deploy-v2" in consolidation.knowledge_graph.nodes
    assert ("m1", "deploy-v2", "PURSUED_GOAL") in consolidation.knowledge_graph.relations


@pytest.mark.asyncio
async def test_consolidation_is_idempotent() -> None:
    consolidation = _make_consolidation()
    await consolidation.episodic_memory.record_episode(
        {"mission_id": "m1", "goal": "deploy-v2", "outcome": "success"}
    )
    first = await consolidation.consolidate()
    second = await consolidation.consolidate()
    assert first["episodes_processed"] == 1
    assert second["episodes_processed"] == 0
    records = await consolidation.long_term_memory.search_semantic("deploy", limit=10)
    assert len(records) == 1
    facts = await consolidation.semantic_memory.query_facts("deploy-v2", limit=10)
    assert len(facts) == 1


@pytest.mark.asyncio
async def test_consolidation_handles_partial_episodes() -> None:
    consolidation = _make_consolidation()
    await consolidation.episodic_memory.record_episode({"note": "no goal or mission"})
    stats = await consolidation.consolidate()
    assert stats["episodes_processed"] == 1
    assert stats["facts_created"] == 0
    assert stats["entities_created"] == 0
    assert stats["relations_created"] == 0


@pytest.mark.asyncio
async def test_consolidation_multiple_episodes() -> None:
    consolidation = _make_consolidation()
    for i in range(3):
        await consolidation.episodic_memory.record_episode(
            {"mission_id": f"m{i}", "goal": f"goal-{i}", "outcome": "success"}
        )
    stats = await consolidation.consolidate()
    assert stats["episodes_processed"] == 3
    assert stats["facts_created"] == 3
    assert stats["relations_created"] == 3
