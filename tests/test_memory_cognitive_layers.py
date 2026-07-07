"""JARVIS OS - Phase 38 Cognitive Layer Tests.

Tests for all five cognitive memory layers (Working, Episodic, Semantic,
Procedural, KnowledgeGraph), plus LongTermMemory, MemoryCoordinator,
ContextAssembly, and MemoryConsolidation.

PHASE: 38
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

from typing import Any

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


# =====================================================================
# Helpers
# =====================================================================


def _make_coordinator() -> tuple[
    MemoryCoordinator,
    WorkingMemory,
    LongTermMemory,
    KnowledgeGraph,
    EpisodicMemory,
    SemanticMemory,
    ProceduralMemory,
]:
    wm = WorkingMemory()
    ltm = LongTermMemory(db_manager=None)
    kg = KnowledgeGraph()
    em = EpisodicMemory()
    sm = SemanticMemory()
    pm = ProceduralMemory()
    coord = MemoryCoordinator(
        working_memory=wm,
        long_term_memory=ltm,
        knowledge_graph=kg,
        episodic_memory=em,
        semantic_memory=sm,
        procedural_memory=pm,
    )
    return coord, wm, ltm, kg, em, sm, pm


# =====================================================================
# WorkingMemory Tests
# =====================================================================


class TestWorkingMemory:
    def test_set_and_get(self) -> None:
        wm = WorkingMemory()
        wm.set("key1", "value1")
        assert wm.get("key1") == "value1"

    def test_get_default(self) -> None:
        wm = WorkingMemory()
        assert wm.get("missing") is None
        assert wm.get("missing", 42) == 42

    def test_clear(self) -> None:
        wm = WorkingMemory()
        wm.set("a", 1)
        wm.set("b", 2)
        wm.clear()
        assert wm.get("a") is None
        assert wm.export() == {}

    def test_export(self) -> None:
        wm = WorkingMemory()
        wm.set("x", 10)
        wm.set("y", 20)
        snapshot = wm.export()
        assert snapshot == {"x": 10, "y": 20}
        # export returns a copy
        snapshot["z"] = 30
        assert wm.get("z") is None

    def test_overwrite(self) -> None:
        wm = WorkingMemory()
        wm.set("k", "old")
        wm.set("k", "new")
        assert wm.get("k") == "new"


# =====================================================================
# EpisodicMemory Tests
# =====================================================================


class TestEpisodicMemory:
    @pytest.mark.asyncio
    async def test_record_and_get_episodes(self) -> None:
        em = EpisodicMemory()
        await em.record_episode({"goal": "test1", "outcome": "success"})
        await em.record_episode({"goal": "test2", "outcome": "failure"})
        episodes = await em.get_recent_episodes(limit=10)
        assert len(episodes) == 2

    @pytest.mark.asyncio
    async def test_limit_returns_most_recent(self) -> None:
        em = EpisodicMemory()
        for i in range(10):
            await em.record_episode({"goal": f"goal_{i}"})
        episodes = await em.get_recent_episodes(limit=3)
        assert len(episodes) == 3
        assert episodes[-1]["goal"] == "goal_9"

    @pytest.mark.asyncio
    async def test_empty_episodes(self) -> None:
        em = EpisodicMemory()
        episodes = await em.get_recent_episodes()
        assert episodes == []


# =====================================================================
# SemanticMemory Tests
# =====================================================================


class TestSemanticMemory:
    @pytest.mark.asyncio
    async def test_add_and_query(self) -> None:
        sm = SemanticMemory()
        await sm.add_fact({"concept": "Python", "details": "A programming language"})
        results = await sm.query_facts("python")
        assert len(results) == 1
        assert results[0]["concept"] == "Python"

    @pytest.mark.asyncio
    async def test_query_no_match(self) -> None:
        sm = SemanticMemory()
        await sm.add_fact({"concept": "Java", "details": "Another language"})
        results = await sm.query_facts("rust")
        assert results == []

    @pytest.mark.asyncio
    async def test_query_matches_details(self) -> None:
        sm = SemanticMemory()
        await sm.add_fact({"concept": "ML", "details": "machine learning algorithms"})
        results = await sm.query_facts("algorithm")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_limit(self) -> None:
        sm = SemanticMemory()
        for i in range(10):
            await sm.add_fact({"concept": f"topic_{i}", "details": "common topic"})
        results = await sm.query_facts("topic", limit=3)
        assert len(results) == 3


# =====================================================================
# ProceduralMemory Tests
# =====================================================================


class TestProceduralMemory:
    @pytest.mark.asyncio
    async def test_register_and_get(self) -> None:
        pm = ProceduralMemory()
        await pm.register_procedure("deploy", ["build", "test", "push"])
        proc = await pm.get_procedure("deploy")
        assert proc is not None
        assert proc["name"] == "deploy"
        assert proc["steps"] == ["build", "test", "push"]

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self) -> None:
        pm = ProceduralMemory()
        proc = await pm.get_procedure("nonexistent")
        assert proc is None

    @pytest.mark.asyncio
    async def test_multiple_procedures(self) -> None:
        pm = ProceduralMemory()
        await pm.register_procedure("a", ["step1"])
        await pm.register_procedure("b", ["step2"])
        assert (await pm.get_procedure("a")) is not None
        assert (await pm.get_procedure("b")) is not None


# =====================================================================
# KnowledgeGraph Tests
# =====================================================================


class TestKnowledgeGraph:
    @pytest.mark.asyncio
    async def test_add_entity(self) -> None:
        kg = KnowledgeGraph()
        await kg.add_entity("user_1", "person", {"name": "Alice"})
        assert "user_1" in kg.nodes
        assert kg.nodes["user_1"]["type"] == "person"

    @pytest.mark.asyncio
    async def test_add_relation(self) -> None:
        kg = KnowledgeGraph()
        await kg.add_entity("a", "node", {})
        await kg.add_entity("b", "node", {})
        await kg.add_relation("a", "b", "LINKS_TO")
        assert ("a", "b", "LINKS_TO") in kg.relations

    @pytest.mark.asyncio
    async def test_get_neighbors(self) -> None:
        kg = KnowledgeGraph()
        await kg.add_entity("a", "node", {})
        await kg.add_entity("b", "node", {})
        await kg.add_entity("c", "node", {})
        await kg.add_relation("a", "b", "KNOWS")
        await kg.add_relation("c", "a", "FOLLOWS")
        neighbors = await kg.get_neighbors("a")
        assert len(neighbors) == 2
        neighbor_names = {n[0] for n in neighbors}
        assert "b" in neighbor_names
        assert "c" in neighbor_names

    @pytest.mark.asyncio
    async def test_get_neighbors_no_relations(self) -> None:
        kg = KnowledgeGraph()
        await kg.add_entity("lonely", "node", {})
        neighbors = await kg.get_neighbors("lonely")
        assert neighbors == []

    @pytest.mark.asyncio
    async def test_entity_overwrite(self) -> None:
        kg = KnowledgeGraph()
        await kg.add_entity("x", "old_type", {"v": 1})
        await kg.add_entity("x", "new_type", {"v": 2})
        assert kg.nodes["x"]["type"] == "new_type"
        assert kg.nodes["x"]["properties"]["v"] == 2


# =====================================================================
# LongTermMemory Tests
# =====================================================================


class TestLongTermMemory:
    @pytest.mark.asyncio
    async def test_save_and_search(self) -> None:
        ltm = LongTermMemory(db_manager=None)
        await ltm.save_experience({"goal": "deploy app", "outcome": "success"})
        results = await ltm.search_semantic("deploy")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_no_match(self) -> None:
        ltm = LongTermMemory(db_manager=None)
        await ltm.save_experience({"goal": "run tests"})
        results = await ltm.search_semantic("deploy")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_limit(self) -> None:
        ltm = LongTermMemory(db_manager=None)
        for i in range(10):
            await ltm.save_experience({"goal": f"task_{i}"})
        results = await ltm.search_semantic("task", limit=3)
        assert len(results) == 3


# =====================================================================
# MemoryCoordinator Tests
# =====================================================================


class TestMemoryCoordinator:
    @pytest.mark.asyncio
    async def test_retrieve_context_empty(self) -> None:
        coord, *_ = _make_coordinator()
        ctx = await coord.retrieve_context("anything")
        assert "working_memory" in ctx
        assert "ranked_memories" in ctx
        assert "episodic_episodes" in ctx
        assert "graph_entities_count" in ctx

    @pytest.mark.asyncio
    async def test_retrieve_context_with_data(self) -> None:
        coord, wm, ltm, kg, em, sm, pm = _make_coordinator()
        wm.set("current_task", "testing")
        await sm.add_fact({"concept": "testing", "details": "unit tests"})
        await ltm.save_experience({"goal": "testing suite", "outcome": "pass"})
        await em.record_episode({"goal": "run tests", "outcome": "success"})
        await kg.add_entity("test_suite", "component", {})

        ctx = await coord.retrieve_context("testing")
        assert ctx["working_memory"]["current_task"] == "testing"
        assert len(ctx["ranked_memories"]) >= 1
        assert len(ctx["episodic_episodes"]) == 1
        assert ctx["graph_entities_count"] >= 1

    @pytest.mark.asyncio
    async def test_ranked_memories_have_confidence(self) -> None:
        coord, _, _, _, _, sm, _ = _make_coordinator()
        await sm.add_fact({"concept": "ML", "details": "machine learning"})
        ctx = await coord.retrieve_context("ML")
        for mem in ctx["ranked_memories"]:
            assert "confidence" in mem
            assert "relevance" in mem


# =====================================================================
# ContextAssembly Tests
# =====================================================================


class TestContextAssembly:
    @pytest.mark.asyncio
    async def test_assemble_context_structure(self) -> None:
        coord, *_ = _make_coordinator()
        ca = ContextAssembly(memory_coordinator=coord)
        ctx = await ca.assemble_context("test query")
        assert ctx["query"] == "test query"
        assert "working_memory" in ctx
        assert "ranked_memories" in ctx
        assert "episodic_memory" in ctx
        assert "knowledge_graph_entities_count" in ctx

    @pytest.mark.asyncio
    async def test_assemble_context_with_data(self) -> None:
        coord, wm, _, _, em, sm, _ = _make_coordinator()
        ca = ContextAssembly(memory_coordinator=coord)
        wm.set("focus", "coding")
        await sm.add_fact({"concept": "coding", "details": "write code"})
        await em.record_episode({"goal": "code review"})

        ctx = await ca.assemble_context("coding")
        assert ctx["working_memory"]["focus"] == "coding"
        assert len(ctx["ranked_memories"]) >= 1
        assert len(ctx["episodic_memory"]) == 1


# =====================================================================
# MemoryConsolidation Tests
# =====================================================================


class TestConsolidation:
    @pytest.mark.asyncio
    async def test_empty_consolidation(self) -> None:
        em = EpisodicMemory()
        ltm = LongTermMemory(db_manager=None)
        sm = SemanticMemory()
        kg = KnowledgeGraph()
        mc = MemoryConsolidation(
            episodic_memory=em,
            long_term_memory=ltm,
            semantic_memory=sm,
            knowledge_graph=kg,
        )
        stats = await mc.consolidate()
        assert stats["episodes_processed"] == 0

    @pytest.mark.asyncio
    async def test_consolidation_persists_to_long_term(self) -> None:
        em = EpisodicMemory()
        ltm = LongTermMemory(db_manager=None)
        sm = SemanticMemory()
        kg = KnowledgeGraph()
        mc = MemoryConsolidation(
            episodic_memory=em,
            long_term_memory=ltm,
            semantic_memory=sm,
            knowledge_graph=kg,
        )
        await em.record_episode(
            {"mission_id": "m1", "goal": "deploy", "outcome": "success"}
        )
        stats = await mc.consolidate()
        assert stats["episodes_processed"] == 1
        results = await ltm.search_semantic("deploy")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_consolidation_creates_semantic_fact(self) -> None:
        em = EpisodicMemory()
        ltm = LongTermMemory(db_manager=None)
        sm = SemanticMemory()
        kg = KnowledgeGraph()
        mc = MemoryConsolidation(
            episodic_memory=em,
            long_term_memory=ltm,
            semantic_memory=sm,
            knowledge_graph=kg,
        )
        await em.record_episode({"goal": "optimize", "outcome": "partial"})
        stats = await mc.consolidate()
        assert stats["facts_created"] == 1
        facts = await sm.query_facts("optimize")
        assert len(facts) == 1

    @pytest.mark.asyncio
    async def test_consolidation_creates_graph_triples(self) -> None:
        em = EpisodicMemory()
        ltm = LongTermMemory(db_manager=None)
        sm = SemanticMemory()
        kg = KnowledgeGraph()
        mc = MemoryConsolidation(
            episodic_memory=em,
            long_term_memory=ltm,
            semantic_memory=sm,
            knowledge_graph=kg,
        )
        await em.record_episode(
            {"mission_id": "m1", "goal": "build API", "outcome": "success"}
        )
        stats = await mc.consolidate()
        assert stats["entities_created"] == 2  # mission + goal
        assert stats["relations_created"] == 1
        assert "m1" in kg.nodes
        assert "build API" in kg.nodes

    @pytest.mark.asyncio
    async def test_consolidation_idempotent(self) -> None:
        em = EpisodicMemory()
        ltm = LongTermMemory(db_manager=None)
        sm = SemanticMemory()
        kg = KnowledgeGraph()
        mc = MemoryConsolidation(
            episodic_memory=em,
            long_term_memory=ltm,
            semantic_memory=sm,
            knowledge_graph=kg,
        )
        await em.record_episode(
            {"mission_id": "m1", "goal": "deploy", "outcome": "ok"}
        )
        stats1 = await mc.consolidate()
        stats2 = await mc.consolidate()
        assert stats1["episodes_processed"] == 1
        assert stats2["episodes_processed"] == 0

    @pytest.mark.asyncio
    async def test_consolidation_partial_episodes(self) -> None:
        em = EpisodicMemory()
        ltm = LongTermMemory(db_manager=None)
        sm = SemanticMemory()
        kg = KnowledgeGraph()
        mc = MemoryConsolidation(
            episodic_memory=em,
            long_term_memory=ltm,
            semantic_memory=sm,
            knowledge_graph=kg,
        )
        # Episode with no goal or mission_id
        await em.record_episode({"outcome": "unknown"})
        stats = await mc.consolidate()
        assert stats["episodes_processed"] == 1
        assert stats["facts_created"] == 0
        assert stats["entities_created"] == 0
