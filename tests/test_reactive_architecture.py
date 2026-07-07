"""JARVIS OS - Event Bus & Reactive Architecture Integration Tests.

Verifies end-to-end event dispatching, trace propagation, handler decoupling, and subsystem wiring.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from core.events import MemoryEventBus
from core.events.handlers.consensus_handler import ConsensusEventHandler
from core.events.handlers.memory_handler import MemoryEventHandler
from core.events.handlers.scale_handler import ScaleEventHandler
from core.events.reactive_router import ReactiveRouter
from core.interfaces import InterAgentMessage
from core.memory.episodic_memory import EpisodicMemory
from core.memory.knowledge_graph import KnowledgeGraph
from core.memory.long_term_memory import LongTermMemory
from core.memory.memory_coordinator import MemoryCoordinator
from core.memory.procedural_memory import ProceduralMemory
from core.memory.semantic_memory import SemanticMemory
from core.memory.working_memory import WorkingMemory
from core.runtime.consensus import ConsensusManager
from core.tools.runtime import ToolRuntime
from core.workflow.dag_scheduler import DAGScheduler
from core.workflow.workflow_executor import WorkflowExecutor
from core.workflow.workflow_graph import WorkflowGraph, WorkflowNode


@pytest.fixture
def memory_coordinator() -> MemoryCoordinator:
    """Fixture providing a configured memory coordinator instance."""
    return MemoryCoordinator(
        working_memory=WorkingMemory(),
        long_term_memory=MagicMock(spec=LongTermMemory),
        knowledge_graph=KnowledgeGraph(),
        episodic_memory=EpisodicMemory(),
        semantic_memory=SemanticMemory(),
        procedural_memory=ProceduralMemory(),
    )


@pytest.mark.asyncio
async def test_reactive_router_basic_pub_sub() -> None:
    """Verify that ReactiveRouter routes messages correctly via MemoryEventBus."""
    bus = MemoryEventBus()
    await bus.initialize()
    await bus.start()

    router = ReactiveRouter(event_bus=bus)
    received_events = []

    async def test_callback(msg: InterAgentMessage) -> None:
        received_events.append(msg)

    sub_id = await router.subscribe("test.topic", test_callback)
    assert sub_id is not None

    correlation_id = uuid4()
    publish_ok = await router.publish(
        topic="test.topic",
        sender="test_sender",
        body={"value": "hello"},
        correlation_id=correlation_id,
    )
    assert publish_ok

    # Yield control to run background dispatch tasks
    await asyncio.sleep(0.05)

    assert len(received_events) == 1
    assert received_events[0].action == "test.topic"
    assert received_events[0].sender == "test_sender"
    assert received_events[0].body == {"value": "hello"}
    assert received_events[0].correlation_id == correlation_id

    # Unsubscribe check
    unsub_ok = await router.unsubscribe("test.topic", sub_id)
    assert unsub_ok

    await router.publish("test.topic", "test_sender", {"value": "hello2"})
    await asyncio.sleep(0.05)
    assert len(received_events) == 1  # unchanged

    await bus.stop()
    await bus.shutdown()


@pytest.mark.asyncio
async def test_memory_handler_workflow_completed(memory_coordinator: MemoryCoordinator) -> None:
    """Verify that MemoryEventHandler records episodic memory when a workflow completes."""
    handler = MemoryEventHandler(memory_coordinator=memory_coordinator)
    trace_id = uuid4()
    msg = InterAgentMessage(
        sender="workflow_executor",
        receiver="all",
        action="workflow.completed",
        body={
            "graph_id": "test_graph_id",
            "success": True,
            "completed_nodes": ["node_1", "node_2"],
            "outputs": {"node_2": "output_val"},
            "error": None,
        },
        correlation_id=trace_id,
    )

    await handler.handle_workflow_completed(msg)

    episodes = await memory_coordinator.episodic_memory.get_recent_episodes()
    assert len(episodes) == 1
    assert episodes[0]["graph_id"] == "test_graph_id"
    assert episodes[0]["success"] is True
    assert episodes[0]["correlation_id"] == str(trace_id)


@pytest.mark.asyncio
async def test_memory_handler_mission_completed(memory_coordinator: MemoryCoordinator) -> None:
    """Verify that MemoryEventHandler records semantic memory when a mission completes."""
    handler = MemoryEventHandler(memory_coordinator=memory_coordinator)
    trace_id = uuid4()
    msg = InterAgentMessage(
        sender="mission_manager",
        receiver="all",
        action="mission.completed",
        body={
            "mission_id": "mission-uuid-string",
            "status": "COMPLETED",
        },
        correlation_id=trace_id,
    )

    await handler.handle_mission_completed(msg)

    facts = await memory_coordinator.semantic_memory.query_facts("mission")
    assert len(facts) == 1
    assert facts[0]["concept"] == "mission_mission-uuid-string"
    assert facts[0]["status"] == "COMPLETED"
    assert facts[0]["correlation_id"] == str(trace_id)


@pytest.mark.asyncio
async def test_scale_and_consensus_handlers_run_safely() -> None:
    """Verify Scale and Consensus handlers execute without errors."""
    mock_scale = MagicMock()
    mock_consensus = MagicMock()

    scale_handler = ScaleEventHandler(scale_manager=mock_scale)
    consensus_handler = ConsensusEventHandler(consensus_manager=mock_consensus)

    trace = uuid4()
    msg = InterAgentMessage(
        sender="test",
        receiver="all",
        action="test",
        body={"graph_id": "test", "mission_id": str(trace), "goal": "test", "approved": True},
        correlation_id=trace,
    )

    # Calling handlers should execute safely
    await scale_handler.handle_workflow_started(msg)
    await scale_handler.handle_workflow_completed(msg)
    await consensus_handler.handle_mission_created(msg)
    await consensus_handler.handle_consensus_reached(msg)


@pytest.mark.asyncio
async def test_workflow_executor_publishes_events() -> None:
    """Verify that WorkflowExecutor publishes start and completion events with traces."""
    bus = MemoryEventBus()
    await bus.initialize()
    await bus.start()

    events_received = []

    async def event_callback(msg: InterAgentMessage) -> None:
        events_received.append(msg)

    await bus.subscribe("workflow.started", event_callback)
    await bus.subscribe("workflow.completed", event_callback)

    # Set up scheduler and simple workflow graph
    scheduler = DAGScheduler()
    executor = WorkflowExecutor(scheduler=scheduler, event_bus=bus)

    # Empty node handler mock
    async def dummy_handler(node: WorkflowNode) -> dict[str, Any]:
        return {"output": "val"}
    executor.register_handler("dummy", dummy_handler)

    graph = WorkflowGraph(graph_id=str(uuid4()), name="test_graph")
    node = WorkflowNode(node_id="node_a", name="Node A", task_type="dummy", parameters={})
    graph.add_node(node)

    res = await executor.execute(graph)
    assert res.success

    # Yield control to let event loop route message tasks
    await asyncio.sleep(0.05)

    assert len(events_received) == 2
    assert events_received[0].action == "workflow.started"
    assert events_received[1].action == "workflow.completed"

    # Check that correlation trace IDs match graph ID context
    assert events_received[0].correlation_id == UUID(graph.graph_id)
    assert events_received[1].correlation_id == UUID(graph.graph_id)
    assert events_received[1].body["success"] is True

    await bus.stop()
    await bus.shutdown()


@pytest.mark.asyncio
async def test_consensus_manager_publishes_consensus_reached() -> None:
    """Verify ConsensusManager publishes consensus.reached on resolution."""
    bus = MemoryEventBus()
    await bus.initialize()
    await bus.start()

    events_received = []

    async def event_callback(msg: InterAgentMessage) -> None:
        events_received.append(msg)

    await bus.subscribe("consensus.reached", event_callback)

    # Mock dependencies
    mock_fed = MagicMock()
    mock_fed.list_peers = AsyncMock(return_value=[])
    mock_fed.node_id = "node_a"
    mock_vault = MagicMock()
    mock_vault.get_secret = MagicMock(return_value="secret")

    consensus = ConsensusManager(
        settings=MagicMock(),
        db_manager=MagicMock(),
        federation_manager=mock_fed,
        vault_manager=mock_vault,
        event_bus=bus,
    )

    # Proposer is node_a. Since peer list is empty, local node is the only peer (N=1, majority_required = 1)
    # The proposal should immediately resolve to APPROVED on creation!
    mission_id = uuid4()
    payload = {"mission_id": str(mission_id)}
    proposal = await consensus.create_proposal("verify_run", payload, "node_a")

    assert proposal["status"] == "APPROVED"

    await asyncio.sleep(0.05)

    assert len(events_received) == 1
    assert events_received[0].action == "consensus.reached"
    assert events_received[0].body["approved"] is True
    assert events_received[0].body["mission_id"] == str(mission_id)
    assert events_received[0].correlation_id == mission_id

    await bus.stop()
    await bus.shutdown()


@pytest.mark.asyncio
async def test_tool_runtime_publishes_tool_executed() -> None:
    """Verify ToolRuntime publishes tool.executed events."""
    bus = MemoryEventBus()
    await bus.initialize()
    await bus.start()

    events_received = []

    async def event_callback(msg: InterAgentMessage) -> None:
        events_received.append(msg)

    await bus.subscribe("tool.executed", event_callback)

    # Mock tool dependencies
    mock_reg = MagicMock()
    mock_skill = MagicMock()
    mock_skill.permissions = ["file_read"]
    mock_skill.dependencies = []
    mock_skill.network_access = False
    mock_reg.get_skill = MagicMock(return_value=mock_skill)

    mock_sandbox = MagicMock()
    mock_sandbox.run = AsyncMock(return_value={"stdout": "hello", "exit_code": 0})

    mock_gatekeeper = MagicMock()
    mock_gatekeeper.verify_permissions = AsyncMock()
    mock_gatekeeper.inject_scoped_secrets = MagicMock(return_value={})

    runtime = ToolRuntime(
        registry=mock_reg,
        sandbox=mock_sandbox,
        gatekeeper=mock_gatekeeper,
        event_bus=bus,
    )

    res = await runtime.execute_tool("cat_file", {"command": ["cat"]}, "node_a")
    assert res.exit_code == 0

    await asyncio.sleep(0.05)

    assert len(events_received) == 1
    assert events_received[0].action == "tool.executed"
    assert events_received[0].body["node_id"] == "node_a"
    assert events_received[0].body["status"] == "SUCCESS"
    assert events_received[0].body["exit_code"] == 0

    await bus.stop()
    await bus.shutdown()
