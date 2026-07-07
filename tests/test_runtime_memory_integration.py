"""JARVIS OS - Phase 20 Runtime Memory Integration Tests.

Tests verifying the full runtime pipeline:
- BrainKernel.observe() stores memories via MemoryOrchestrator
- BrainKernel.reason() recalls memories into context
- BrainKernel.reflect_and_learn() stores execution experiences
- BrainKernel.step() runs the full cognitive cycle with memory
- ContextAssembly enriches context with Phase 19 scored retrieval
- MemoryEventHandler subscribes to and handles memory events

PHASE: 20
STATUS: IMPLEMENTATION
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import pytest

from core.memory.event_handler import MemoryEventHandler


# =====================================================================
# Lightweight mocks (no external dependencies)
# =====================================================================


class MockEventBus:
    """In-memory event bus for testing."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Any]] = {}
        self.published: List[Dict[str, Any]] = []

    async def subscribe(self, topic: str, handler: Any) -> str:
        self._subscribers.setdefault(topic, []).append(handler)
        return f"sub_{topic}"

    async def publish(self, topic: str, data: Any) -> None:
        self.published.append({"topic": topic, "data": data})
        for handler in self._subscribers.get(topic, []):
            await handler(data)

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass


class MockInterAgentMessage:
    """Minimal InterAgentMessage mock."""

    def __init__(self, body: Dict[str, Any]) -> None:
        self.body = body
        self.sender = "test"
        self.receiver = "test"
        self.action = "test"


class MockRecord:
    """Minimal MemoryRecord mock."""

    def __init__(self, memory_id: Optional[UUID] = None, content: str = "test") -> None:
        self.memory_id = memory_id or uuid4()
        self.content = content
        self.content_hash = "hash_" + content[:8]
        self.confidence = 0.9
        self.importance = 0.5
        self.created_at = "2026-07-07T00:00:00"
        self.updated_at = "2026-07-07T00:00:00"

        class MT:
            value = "fact"

        self.memory_type = MT()


class MockRetrievalResponse:
    """Mock RetrievalResponse."""

    def __init__(self, chunks: Optional[list[Any]] = None) -> None:
        self.chunks = chunks or []


class MockChunk:
    """Mock retrieval chunk."""

    def __init__(self, content: str = "recalled memory") -> None:
        self.memory_id = uuid4()
        self.content = content
        self.content_hash = "hash_recalled"
        self.created_at = "2026-07-07T00:00:00"


class MockMemoryOrchestrator:
    """Mock MemoryOrchestrator tracking all calls."""

    def __init__(self) -> None:
        self.stored: List[Dict[str, Any]] = []
        self.recalled: List[Any] = []
        self._chunks_to_return: List[Any] = [MockChunk()]

    async def store(self, **kwargs: Any) -> UUID:
        mid = uuid4()
        self.stored.append({"id": mid, **kwargs})
        return mid

    async def recall(self, request: Any) -> MockRetrievalResponse:
        self.recalled.append(request)
        return MockRetrievalResponse(self._chunks_to_return)


class MockWorkingMemory:
    """Mock WorkingMemory tracking add/remove calls."""

    def __init__(self) -> None:
        self.items: Dict[str, Any] = {}
        self.added: List[str] = []
        self.removed: List[str] = []

    def add(self, key: str, value: Any) -> None:
        self.items[key] = value
        self.added.append(key)

    def remove(self, key: str) -> None:
        self.items.pop(key, None)
        self.removed.append(key)

    def export(self) -> Dict[str, Any]:
        return dict(self.items)


class MockBrainContext:
    """Mock BrainContext."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def export(self) -> Dict[str, Any]:
        return dict(self._data)


class MockCognitiveState:
    """Mock CognitiveState."""

    def __init__(self) -> None:
        self.current_goal: Optional[str] = None
        self.attention_queue: List[str] = []
        self.energy: float = 1.0
        self.confidence: float = 1.0
        self.estimated_cost: float = 0.0

    def model_dump(self) -> Dict[str, Any]:
        return {
            "current_goal": self.current_goal,
            "attention_queue": self.attention_queue,
            "energy": self.energy,
            "confidence": self.confidence,
        }


# =====================================================================
# BrainKernel + Memory Integration Tests
# =====================================================================


class TestBrainKernelMemoryObserve:
    """Test that BrainKernel.observe() stores observations as memories."""

    @pytest.mark.asyncio
    async def test_observe_stores_memory(self) -> None:
        from core.runtime.brain_kernel import BrainKernel

        event_bus = MockEventBus()
        orch = MockMemoryOrchestrator()
        state = MockCognitiveState()
        context = MockBrainContext()

        bk = BrainKernel(
            settings={},
            state=state,
            context=context,
            event_bus=event_bus,
            memory_orchestrator=orch,
        )

        await bk.observe({"message": "User said hello"})

        assert len(orch.stored) == 1
        assert orch.stored[0]["content"] == "User said hello"
        assert orch.stored[0]["source_type"] == "observation"

    @pytest.mark.asyncio
    async def test_observe_without_orchestrator(self) -> None:
        from core.runtime.brain_kernel import BrainKernel

        event_bus = MockEventBus()
        state = MockCognitiveState()
        context = MockBrainContext()

        bk = BrainKernel(
            settings={},
            state=state,
            context=context,
            event_bus=event_bus,
        )

        await bk.observe({"message": "test"})
        assert "test" in state.attention_queue

    @pytest.mark.asyncio
    async def test_observe_custom_importance(self) -> None:
        from core.runtime.brain_kernel import BrainKernel

        orch = MockMemoryOrchestrator()
        bk = BrainKernel(
            settings={},
            state=MockCognitiveState(),
            context=MockBrainContext(),
            event_bus=MockEventBus(),
            memory_orchestrator=orch,
        )

        await bk.observe({"message": "critical event", "importance": 0.9})
        assert orch.stored[0]["importance"] == 0.9


class TestBrainKernelMemoryReason:
    """Test that BrainKernel.reason() recalls memories into context."""

    @pytest.mark.asyncio
    async def test_reason_recalls_memories(self) -> None:
        from core.runtime.brain_kernel import BrainKernel

        orch = MockMemoryOrchestrator()
        context = MockBrainContext()
        state = MockCognitiveState()
        state.current_goal = "solve the puzzle"

        bk = BrainKernel(
            settings={},
            state=state,
            context=context,
            event_bus=MockEventBus(),
            memory_orchestrator=orch,
        )

        result = await bk.reason()

        assert len(orch.recalled) == 1
        memory_ctx = context.get("memory_context")
        assert memory_ctx is not None
        assert len(memory_ctx) == 1
        assert memory_ctx[0]["content"] == "recalled memory"

    @pytest.mark.asyncio
    async def test_reason_skips_idle_goal(self) -> None:
        from core.runtime.brain_kernel import BrainKernel

        orch = MockMemoryOrchestrator()
        state = MockCognitiveState()

        bk = BrainKernel(
            settings={},
            state=state,
            context=MockBrainContext(),
            event_bus=MockEventBus(),
            memory_orchestrator=orch,
        )

        await bk.reason()
        assert len(orch.recalled) == 0

    @pytest.mark.asyncio
    async def test_reason_without_orchestrator(self) -> None:
        from core.runtime.brain_kernel import BrainKernel

        state = MockCognitiveState()
        state.current_goal = "test"

        bk = BrainKernel(
            settings={},
            state=state,
            context=MockBrainContext(),
            event_bus=MockEventBus(),
        )

        result = await bk.reason()
        assert result["confidence"] == 1.0


class TestBrainKernelMemoryReflect:
    """Test that BrainKernel.reflect_and_learn() stores experiences."""

    @pytest.mark.asyncio
    async def test_reflect_stores_experience(self) -> None:
        from core.runtime.brain_kernel import BrainKernel

        orch = MockMemoryOrchestrator()
        bk = BrainKernel(
            settings={},
            state=MockCognitiveState(),
            context=MockBrainContext(),
            event_bus=MockEventBus(),
            memory_orchestrator=orch,
        )

        await bk.reflect_and_learn("test goal", {"status": "SUCCESS"})

        assert len(orch.stored) == 1
        assert "test goal" in orch.stored[0]["content"]
        assert orch.stored[0]["source_type"] == "execution_experience"
        assert orch.stored[0]["importance"] == 0.6

    @pytest.mark.asyncio
    async def test_reflect_failure_higher_importance(self) -> None:
        from core.runtime.brain_kernel import BrainKernel

        orch = MockMemoryOrchestrator()
        bk = BrainKernel(
            settings={},
            state=MockCognitiveState(),
            context=MockBrainContext(),
            event_bus=MockEventBus(),
            memory_orchestrator=orch,
        )

        await bk.reflect_and_learn("failed goal", {"status": "BLOCKED"})

        assert orch.stored[0]["importance"] == 0.8

    @pytest.mark.asyncio
    async def test_reflect_without_orchestrator(self) -> None:
        from core.runtime.brain_kernel import BrainKernel

        bk = BrainKernel(
            settings={},
            state=MockCognitiveState(),
            context=MockBrainContext(),
            event_bus=MockEventBus(),
        )

        await bk.reflect_and_learn("goal", {"status": "SUCCESS"})


class TestBrainKernelFullCycle:
    """Test that BrainKernel.step() runs the full cycle with memory."""

    @pytest.mark.asyncio
    async def test_step_full_cycle_with_memory(self) -> None:
        from core.runtime.brain_kernel import BrainKernel

        orch = MockMemoryOrchestrator()
        state = MockCognitiveState()
        state.attention_queue = ["process data"]
        event_bus = MockEventBus()

        bk = BrainKernel(
            settings={},
            state=state,
            context=MockBrainContext(),
            event_bus=event_bus,
            memory_orchestrator=orch,
        )

        await bk.step()

        assert len(orch.recalled) >= 1
        assert len(orch.stored) >= 1
        experience_stored = any(
            s.get("source_type") == "execution_experience" for s in orch.stored
        )
        assert experience_stored


# =====================================================================
# ContextAssembly + MemoryOrchestrator Integration Tests
# =====================================================================


class TestContextAssemblyMemoryBridge:
    """Test that ContextAssembly enriches context with Phase 19 scored retrieval."""

    @pytest.mark.asyncio
    async def test_assemble_with_orchestrator(self) -> None:
        from core.memory.context_assembly import ContextAssembly
        from core.memory.memory_coordinator import MemoryCoordinator

        coordinator = MemoryCoordinator(
            working_memory=MockWorkingMemory(),
            long_term_memory=None,
            knowledge_graph=None,
            episodic_memory=None,
            semantic_memory=None,
            procedural_memory=None,
        )
        orch = MockMemoryOrchestrator()

        assembler = ContextAssembly(
            memory_coordinator=coordinator,
            memory_orchestrator=orch,
        )

        result = await assembler.assemble_context("test query")

        assert "scored_memories" in result
        assert result["scored_memory_count"] == 1
        assert len(orch.recalled) == 1

    @pytest.mark.asyncio
    async def test_assemble_without_orchestrator(self) -> None:
        from core.memory.context_assembly import ContextAssembly
        from core.memory.memory_coordinator import MemoryCoordinator

        coordinator = MemoryCoordinator(
            working_memory=MockWorkingMemory(),
            long_term_memory=None,
            knowledge_graph=None,
            episodic_memory=None,
            semantic_memory=None,
            procedural_memory=None,
        )

        assembler = ContextAssembly(memory_coordinator=coordinator)
        result = await assembler.assemble_context("test")

        assert "scored_memories" not in result


# =====================================================================
# MemoryEventHandler Tests
# =====================================================================


class TestMemoryEventHandler:
    """Test that MemoryEventHandler subscribes to and handles events."""

    @pytest.mark.asyncio
    async def test_subscribes_to_all_topics(self) -> None:
        event_bus = MockEventBus()
        handler = MemoryEventHandler(event_bus=event_bus)
        await handler.initialize()

        expected_topics = {
            "memory.created",
            "memory.updated",
            "memory.promoted",
            "memory.archived",
            "memory.deleted",
            "memory.retrieved",
            "memory.reflected",
            "memory.indexed",
        }
        subscribed = set(event_bus._subscribers.keys())
        assert expected_topics == subscribed

    @pytest.mark.asyncio
    async def test_created_event_updates_working_memory(self) -> None:
        event_bus = MockEventBus()
        wm = MockWorkingMemory()
        handler = MemoryEventHandler(event_bus=event_bus, working_memory=wm)
        await handler.initialize()

        msg = MockInterAgentMessage({"chunk_id": "abc-123"})
        await event_bus.publish("memory.created", msg)

        assert len(wm.added) == 1
        assert "memory:abc-123" in wm.added[0]

    @pytest.mark.asyncio
    async def test_deleted_event_removes_from_working_memory(self) -> None:
        event_bus = MockEventBus()
        wm = MockWorkingMemory()
        wm.items["memory:xyz"] = {"event": "created"}
        handler = MemoryEventHandler(event_bus=event_bus, working_memory=wm)
        await handler.initialize()

        msg = MockInterAgentMessage({"chunk_id": "xyz"})
        await event_bus.publish("memory.deleted", msg)

        assert "memory:xyz" in wm.removed

    @pytest.mark.asyncio
    async def test_promoted_event_logged(self) -> None:
        event_bus = MockEventBus()
        handler = MemoryEventHandler(event_bus=event_bus)
        await handler.initialize()

        msg = MockInterAgentMessage({"chunk_id": "abc", "target_tier": "long_term"})
        await event_bus.publish("memory.promoted", msg)
        assert len(event_bus.published) == 1

    @pytest.mark.asyncio
    async def test_handler_without_working_memory(self) -> None:
        event_bus = MockEventBus()
        handler = MemoryEventHandler(event_bus=event_bus)
        await handler.initialize()

        msg = MockInterAgentMessage({"chunk_id": "test"})
        await event_bus.publish("memory.created", msg)

    @pytest.mark.asyncio
    async def test_all_event_types_fire(self) -> None:
        event_bus = MockEventBus()
        handler = MemoryEventHandler(event_bus=event_bus)
        await handler.initialize()

        topics = [
            "memory.created",
            "memory.updated",
            "memory.promoted",
            "memory.archived",
            "memory.deleted",
            "memory.retrieved",
            "memory.reflected",
            "memory.indexed",
        ]
        for topic in topics:
            msg = MockInterAgentMessage({"chunk_id": "test"})
            await event_bus.publish(topic, msg)

        assert len(event_bus.published) == 8
