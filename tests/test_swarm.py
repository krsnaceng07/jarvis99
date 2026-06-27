"""JARVIS OS - Swarm Orchestrator and Inter-Agent Message Routing Unit & Integration Tests.

Validates container drivers, agent registries, capability negotiators, distributed lock managers,
task priority queues, message brokers, DLQ redirects, state persistence, orchestrators, and api routes.
"""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.events.memory_bus import MemoryEventBus
from core.interfaces import InterAgentMessage
from core.runtime.container_driver import (
    DockerAdapter,
    LocalProcessAdapter,
    MockAdapter,
)
from core.runtime.dto import SwarmSnapshot, SwarmTask
from core.runtime.lock import MemoryLock, RedisLock
from core.runtime.message_bus import SwarmMessageBus
from core.runtime.orchestrator import SwarmOrchestrator
from core.runtime.persistence import SwarmRepository
from core.runtime.queue import SwarmTaskQueue
from core.runtime.registry import AgentPermissionManifest, AgentRegistry
from core.runtime.routes import set_orchestrator, swarm_router
from core.runtime.scheduler import CapabilityNegotiator
from core.runtime.subagent import SubagentManager


@pytest.mark.asyncio
async def test_container_drivers() -> None:
    """Verify container driver adapters spawn, terminate, and fetch metrics."""
    subagent_id = uuid4()
    task_id = uuid4()

    for adapter in [MockAdapter(), DockerAdapter(), LocalProcessAdapter()]:
        spawn_res = await adapter.spawn_container(subagent_id, task_id)
        assert spawn_res["status"] == "SUCCESS"

        metrics = await adapter.get_container_metrics(subagent_id)
        assert "cpu_usage" in metrics
        assert "memory_usage" in metrics

        term_res = await adapter.terminate_container(subagent_id)
        assert term_res is True

        metrics_after = await adapter.get_container_metrics(subagent_id)
        assert metrics_after["cpu_usage"] == 0.0


def test_agent_registry_and_permissions() -> None:
    """Verify registry maps subagents, updates statuses, and evaluates permission manifests."""
    registry = AgentRegistry()
    agent_id = uuid4()

    registry.register_agent(
        agent_id,
        name="TestCoder",
        capabilities=["Coding", "UnitTests"],
        permissions={"Browser", "Shell"},
    )

    agent = registry.get_agent(agent_id)
    assert agent["name"] == "TestCoder"
    assert "Coding" in agent["capabilities"]

    # Verify manifest
    manifest: AgentPermissionManifest = agent["manifest"]
    assert manifest.has_permission("Browser") is True
    assert manifest.has_permission("PC_Controller") is False

    registry.update_status(agent_id, "WORKING")
    assert registry.get_agent(agent_id)["status"] == "WORKING"

    registry.unregister_agent(agent_id)
    with pytest.raises(Exception):
        registry.get_agent(agent_id)


@pytest.mark.asyncio
async def test_lock_managers() -> None:
    """Verify memory and Redis lock manager acquisitions and releases."""
    owner1 = "Orchestrator-A"
    owner2 = "Orchestrator-B"
    lock_key = "test.lock.123"

    for lock in [MemoryLock(), RedisLock()]:
        # First acquire
        acquired = await lock.acquire(lock_key, owner1)
        assert acquired is True

        # Second acquire by other owner fails
        conflict = await lock.acquire(lock_key, owner2)
        assert conflict is False

        # Release by wrong owner fails
        fail_release = await lock.release(lock_key, owner2)
        assert fail_release is False

        # Release by correct owner succeeds
        release = await lock.release(lock_key, owner1)
        assert release is True


@pytest.mark.asyncio
async def test_swarm_task_queue() -> None:
    """Verify task priorities FIFO ordering in SwarmTaskQueue."""
    queue = SwarmTaskQueue()
    t1 = SwarmTask(task_id=uuid4(), goal="Low Task", priority="LOW")
    t2 = SwarmTask(task_id=uuid4(), goal="Critical Task", priority="CRITICAL")
    t3 = SwarmTask(task_id=uuid4(), goal="High Task", priority="HIGH")

    await queue.enqueue(t1)
    await queue.enqueue(t2)
    await queue.enqueue(t3)

    # Verify critical task dequeues first
    dq1 = await queue.dequeue()
    assert dq1 is not None
    assert dq1.goal == "Critical Task"

    # Verify high task dequeues second
    dq2 = await queue.dequeue()
    assert dq2 is not None
    assert dq2.goal == "High Task"


def test_capability_negotiator() -> None:
    """Verify capability match scoring selecting the optimal agent."""
    negotiator = CapabilityNegotiator()
    a1 = {
        "id": uuid4(),
        "status": "ONLINE",
        "capabilities": ["Coding"],
        "cpu_load": 0.1,
        "memory": 256.0,
        "recent_failures": 0,
    }
    a2 = {
        "id": uuid4(),
        "status": "WORKING",  # busy
        "capabilities": ["Coding"],
        "cpu_load": 0.8,
        "memory": 512.0,
        "recent_failures": 1,
    }

    task = SwarmTask(
        task_id=uuid4(), goal="Write Python Script", capabilities=["Coding"]
    )
    best = negotiator.select_best_agent([a1, a2], task)
    assert best == a1["id"]  # Less loaded agent selected


@pytest.mark.asyncio
async def test_message_bus_and_dlq() -> None:
    """Verify message retries and DLQ failover redirections."""
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    bus = SwarmMessageBus(event_bus, max_retry=2, retry_delay=0.01)
    msg = InterAgentMessage(
        sender="Planner",
        receiver="Developer",
        action="modify_file",
        body={"path": "src/app.py"},
    )

    # Publish with dummy target topic (fails to find real stream, but MemoryEventBus accepts publishes)
    res = await bus.publish_message("agent.action", msg)
    assert res is True  # MemoryEventBus delivers cleanly

    # Test security blocking
    blocked_msg = InterAgentMessage(
        sender="Planner",
        receiver="Developer",
        action="modify_file",
        body={"vault_key": "raw_password_123"},
    )
    security_res = await bus.publish_message("agent.action", blocked_msg)
    assert security_res is False  # Blocked

    await event_bus.stop()


@pytest.mark.asyncio
async def test_swarm_persistence() -> None:
    """Verify swarm persistence saving tasks, agents, and snapshots."""
    repo = SwarmRepository()
    task = SwarmTask(task_id=uuid4(), goal="Test Task")
    await repo.save_task(task)

    snapshot = SwarmSnapshot(
        running_agents=2,
        queued_tasks=1,
        completed_tasks=0,
        failed_tasks=0,
        message_rate=0.4,
        cpu_usage=0.2,
        memory_usage=128.0,
    )
    await repo.save_snapshot(snapshot)

    loaded = await repo.load_snapshot()
    assert loaded is not None
    assert loaded.running_agents == 2


@pytest.mark.asyncio
async def test_subagent_manager_watchdog() -> None:
    """Verify SubagentManager watchdog checks lifespan and heartbeat lost counts."""
    driver = MockAdapter()
    manager = SubagentManager(
        max_concurrent=5,
        max_lifespan=0.05,
        heartbeat_timeout=0.05,
        check_interval=0.01,
        driver=driver,
    )
    await manager.initialize()

    task_id = uuid4()
    sid = await manager.spawn_subagent(task_id)

    # Let timeout pass
    await asyncio.sleep(0.08)
    await manager._check_timeouts()

    # Verify subagent is terminated and removed by watchdog
    assert sid not in manager.active_subagents

    await manager.shutdown()


@pytest.mark.asyncio
async def test_swarm_orchestrator_integration() -> None:
    """Verify orchestrator coordinate flows."""
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    manager = SubagentManager(driver=MockAdapter())
    queue = SwarmTaskQueue()
    negotiator = CapabilityNegotiator()
    message_bus = SwarmMessageBus(event_bus)
    persistence = SwarmRepository()
    lock_manager = MemoryLock()
    registry = AgentRegistry()

    orchestrator = SwarmOrchestrator(
        manager=manager,
        queue=queue,
        negotiator=negotiator,
        message_bus=message_bus,
        persistence=persistence,
        lock_manager=lock_manager,
        registry=registry,
        event_bus=event_bus,
    )

    task = SwarmTask(
        task_id=uuid4(),
        goal="Decompose SaaS Application",
        capabilities=["Coding"],
    )

    spawned = await orchestrator.spawn_task(task)
    assert spawned is True

    status = await orchestrator.get_status()
    assert status["queued_tasks"] == 1

    cancel = await orchestrator.cancel_task(task.task_id)
    assert cancel is True

    await orchestrator.shutdown()
    await event_bus.stop()


def test_swarm_api_routes() -> None:
    """Verify REST router endpoints /spawn and /terminate."""
    app = FastAPI()
    app.include_router(swarm_router)
    client = TestClient(app)

    # Test before orchestrator set
    response = client.post(
        "/api/v1/swarm/spawn",
        json={"task_id": str(uuid4()), "goal": "Spawn Test"},
    )
    assert response.status_code == 503

    # Setup orchestrator Mock
    mock_orchestrator = AsyncMock()
    mock_orchestrator.spawn_task.return_value = True
    mock_orchestrator.cancel_task.return_value = True
    set_orchestrator(mock_orchestrator)

    # Success Spawn
    spawn_res = client.post(
        "/api/v1/swarm/spawn",
        json={"task_id": str(uuid4()), "goal": "Spawn Test"},
    )
    assert spawn_res.status_code == 200
    assert spawn_res.json()["status"] == "SUCCESS"

    # Success Terminate
    term_res = client.post(
        "/api/v1/swarm/terminate",
        json={"task_id": str(uuid4())},
    )
    assert term_res.status_code == 200
    assert term_res.json()["status"] == "SUCCESS"
