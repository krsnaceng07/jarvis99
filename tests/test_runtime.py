"""JARVIS OS - Agent Runtime & Orchestrator Foundation Unit & Integration Tests.

Verifies state transition managers, scheduler strategies, subagent limits, context budgets,
execution runtime loop, cancellation tokens, checkpoints, and event notifier brokers.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from core.events.memory_bus import MemoryEventBus
from core.exceptions import JarvisAgentError, JarvisSystemError
from core.interfaces import InterAgentMessage
from core.runtime.context import AgentContextManager
from core.runtime.dto import CancellationToken, CheckpointDTO, ExecutionBudget
from core.runtime.engine import AgentRuntime
from core.runtime.events import (
    AgentRuntimeNotifier,
    InMemoryStateStore,
    RedisStateStore,
)
from core.runtime.scheduler import (
    CostAwareSchedulerStrategy,
    DeadlineSchedulerStrategy,
    FIFOSchedulerStrategy,
    PrioritySchedulerStrategy,
    RoundRobinSchedulerStrategy,
    ScheduledTask,
    TaskScheduler,
)
from core.runtime.state import (
    AgentExecutionState,
    AgentStateTransitionManager,
    SubagentState,
)
from core.runtime.subagent import SubagentManager

# =====================================================================
# 1. State Machine Transitions Tests
# =====================================================================


def test_subagent_transitions() -> None:
    """Verify valid and invalid transitions for SubagentState lifecycle."""
    # Valid transition
    AgentStateTransitionManager.validate_subagent_transition(
        SubagentState.CREATE, SubagentState.INITIALIZE
    )
    AgentStateTransitionManager.validate_subagent_transition(
        SubagentState.CREATE, SubagentState.DESTROYED
    )
    AgentStateTransitionManager.validate_subagent_transition(
        SubagentState.DESTROYED, SubagentState.DESTROYED
    )

    # Invalid transition
    with pytest.raises(JarvisAgentError) as excinfo:
        AgentStateTransitionManager.validate_subagent_transition(
            SubagentState.CREATE, SubagentState.WORKING
        )
    assert excinfo.value.code == "AGENT_001"
    assert "Invalid subagent transition path" in excinfo.value.message


def test_execution_transitions() -> None:
    """Verify valid and invalid transitions for AgentExecutionState loop."""
    # Valid transition
    AgentStateTransitionManager.validate_execution_transition(
        AgentExecutionState.IDLE, AgentExecutionState.LOAD
    )
    AgentStateTransitionManager.validate_execution_transition(
        AgentExecutionState.LOAD, AgentExecutionState.PERSIST
    )

    # Invalid transition
    with pytest.raises(JarvisAgentError) as excinfo:
        AgentStateTransitionManager.validate_execution_transition(
            AgentExecutionState.IDLE, AgentExecutionState.VERIFY
        )
    assert excinfo.value.code == "AGENT_001"
    assert "Invalid execution loop transition path" in excinfo.value.message


# =====================================================================
# 2. Scheduler Strategies Tests
# =====================================================================


@pytest.mark.asyncio
async def test_fifo_scheduler_strategy() -> None:
    """Verify FIFO strategy schedules tasks strictly by created_at ascending."""
    strategy = FIFOSchedulerStrategy()
    t1 = ScheduledTask(
        id=uuid4(),
        priority=10,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    t2 = ScheduledTask(id=uuid4(), priority=5, created_at=datetime.now(timezone.utc))

    sorted_tasks = await strategy.schedule([t2, t1])
    assert sorted_tasks[0].id == t1.id
    assert sorted_tasks[1].id == t2.id


@pytest.mark.asyncio
async def test_priority_scheduler_strategy() -> None:
    """Verify Priority strategy schedules tasks by priority value descending."""
    strategy = PrioritySchedulerStrategy()
    t1 = ScheduledTask(
        id=uuid4(),
        priority=5,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    t2 = ScheduledTask(id=uuid4(), priority=10, created_at=datetime.now(timezone.utc))

    sorted_tasks = await strategy.schedule([t1, t2])
    assert sorted_tasks[0].id == t2.id
    assert sorted_tasks[1].id == t1.id


@pytest.mark.asyncio
async def test_deadline_scheduler_strategy() -> None:
    """Verify Deadline strategy schedules tasks with earlier deadlines first."""
    strategy = DeadlineSchedulerStrategy()
    t1 = ScheduledTask(
        id=uuid4(), deadline=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    t2 = ScheduledTask(
        id=uuid4(), deadline=datetime.now(timezone.utc) + timedelta(minutes=2)
    )
    t3 = ScheduledTask(id=uuid4(), deadline=None)

    sorted_tasks = await strategy.schedule([t1, t3, t2])
    assert sorted_tasks[0].id == t2.id
    assert sorted_tasks[1].id == t1.id
    assert sorted_tasks[2].id == t3.id


@pytest.mark.asyncio
async def test_cost_aware_scheduler_strategy() -> None:
    """Verify CostAware strategy schedules tasks with lower costs first."""
    strategy = CostAwareSchedulerStrategy()
    t1 = ScheduledTask(id=uuid4(), cost=1.5)
    t2 = ScheduledTask(id=uuid4(), cost=0.2)

    sorted_tasks = await strategy.schedule([t1, t2])
    assert sorted_tasks[0].id == t2.id
    assert sorted_tasks[1].id == t1.id


@pytest.mark.asyncio
async def test_task_scheduler_enqueues_and_dequeues() -> None:
    """Verify TaskScheduler manages queues and dynamic strategy switching."""
    scheduler = TaskScheduler(strategy=FIFOSchedulerStrategy())
    t1 = ScheduledTask(
        id=uuid4(),
        priority=5,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    t2 = ScheduledTask(id=uuid4(), priority=10, created_at=datetime.now(timezone.utc))

    await scheduler.add_task(t2)
    await scheduler.add_task(t1)

    # In FIFO: t1 must come first because of earlier created_at
    all_tasks = await scheduler.get_all_tasks()
    assert len(all_tasks) == 2
    assert all_tasks[0].id == t1.id

    # Switch dynamically to Priority strategy
    await scheduler.set_strategy(PrioritySchedulerStrategy())
    next_task = await scheduler.get_next_task()
    assert next_task is not None
    assert next_task.id == t2.id  # Higher priority (10 > 5)

    remaining = await scheduler.get_next_task()
    assert remaining is not None
    assert remaining.id == t1.id

    assert await scheduler.get_next_task() is None


# =====================================================================
# 3. Subagent Manager Tests
# =====================================================================


@pytest.mark.asyncio
async def test_round_robin_strategy() -> None:
    """Verify RoundRobin strategy returns tasks in initial sequence."""
    strategy = RoundRobinSchedulerStrategy()
    t1 = ScheduledTask(id=uuid4())
    t2 = ScheduledTask(id=uuid4())
    sorted_tasks = await strategy.schedule([t1, t2])
    assert sorted_tasks == [t1, t2]


@pytest.mark.asyncio
async def test_subagent_manager_limits_and_watchdog() -> None:
    """Verify SubagentManager limits active concurrency and enforces timeouts."""
    manager = SubagentManager(
        max_concurrent=2, max_lifespan=5.0, heartbeat_timeout=2.0, check_interval=0.001
    )
    await manager.initialize()
    await asyncio.sleep(0.01)  # Yield to let watchdog loop run

    t_id = uuid4()
    s1 = await manager.spawn_subagent(t_id)
    s2 = await manager.spawn_subagent(t_id)
    assert len(manager.active_subagents) == 2

    # Verify spawning 3rd raises limit error
    with pytest.raises(JarvisAgentError) as excinfo:
        await manager.spawn_subagent(t_id)
    assert excinfo.value.code == "AGENT_002"
    assert "Spawning limit exceeded" in excinfo.value.message

    # Try updating non-existent subagent state
    with pytest.raises(JarvisAgentError) as excinfo:
        await manager.update_state(uuid4(), SubagentState.WORKING)
    assert excinfo.value.code == "AGENT_999"

    # Transition s1 to WORKING
    await manager.update_state(s1, SubagentState.WORKING)
    assert manager.active_subagents[s1].state == SubagentState.WORKING

    # Trigger heartbeat registration
    await manager.register_heartbeat(s1)
    await manager.register_heartbeat(uuid4())  # non-existent is a noop

    # Simulate heartbeat timeout by backdating last_heartbeat
    manager.active_subagents[s1].last_heartbeat = time.time() - 3.0
    await manager._check_timeouts()
    # s1 should be terminated/destroyed due to lost heartbeat
    assert s1 not in manager.active_subagents

    # Verify lifespan timeout
    manager.active_subagents[s2].created_at = time.time() - 10.0
    await manager._check_timeouts()
    assert s2 not in manager.active_subagents

    # Spawn another subagent to verify cleanup in shutdown
    s3 = await manager.spawn_subagent(t_id)
    await manager.update_state(
        s3, SubagentState.DESTROYED
    )  # Verify update state to DESTROYED pop
    assert s3 not in manager.active_subagents

    await manager.spawn_subagent(t_id)
    assert len(manager.active_subagents) == 1
    # Shutdown with active subagent to cover cleanup loop
    await manager.shutdown()
    assert len(manager.active_subagents) == 0


# =====================================================================
# 4. Context & Budget Manager Tests
# =====================================================================


def test_context_manager_variables_and_budgets() -> None:
    """Verify variable storage and budget limits enforcement in AgentContextManager."""
    budget = ExecutionBudget(
        max_tokens=100, max_cost=0.10, max_duration=2.0, max_memory_mb=128
    )
    context = AgentContextManager(budget=budget)

    context.set_variable("foo", "bar")
    assert context.get_variable("foo") == "bar"
    assert context.get_variable("missing", "default") == "default"

    # Token violation check
    context.update_token_usage(50)
    with pytest.raises(JarvisAgentError) as excinfo:
        context.update_token_usage(51)
    assert excinfo.value.code == "AGENT_003"
    assert "Token budget exceeded" in excinfo.value.message

    # Cost violation check
    context.update_cost(0.05)
    with pytest.raises(JarvisAgentError) as excinfo:
        context.update_cost(0.06)
    assert excinfo.value.code == "AGENT_003"
    assert "Financial budget exceeded" in excinfo.value.message

    # Memory violation check
    context.update_memory_usage(100)
    with pytest.raises(JarvisAgentError) as excinfo:
        context.update_memory_usage(150)
    assert excinfo.value.code == "AGENT_003"
    assert "Memory budget exceeded" in excinfo.value.message

    # Duration violation check
    context.start_time = time.time() - 5.0
    with pytest.raises(JarvisAgentError) as excinfo:
        context.check_duration()
    assert excinfo.value.code == "AGENT_003"
    assert "Duration limit exceeded" in excinfo.value.message


# =====================================================================
# 5. Execution Runtime Engine Tests
# =====================================================================


class StepCancelledToken(CancellationToken):
    """Token subclass that returns cancelled=True starting from the second check (at DISPATCH)."""

    def __init__(self) -> None:
        super().__init__()
        self.checks = 0

    @property
    def is_cancelled(self) -> bool:
        self.checks += 1
        if self.checks >= 2:
            return True
        return False


class WaitCancelledToken(CancellationToken):
    """Token subclass that returns cancelled=True starting from the third check (at WAIT)."""

    def __init__(self) -> None:
        super().__init__()
        self.checks = 0

    @property
    def is_cancelled(self) -> bool:
        self.checks += 1
        if self.checks >= 3:
            return True
        return False


@pytest.mark.asyncio
async def test_runtime_engine_success_loop() -> None:
    """Verify AgentRuntime successfully coordinates task execution loop."""
    runtime = AgentRuntime()
    task = ScheduledTask(id=uuid4())

    async def step_executor(
        t: ScheduledTask, idx: int, ctx: AgentContextManager
    ) -> Dict[str, Any]:
        ctx.set_variable("step_val", idx)
        return {"step": idx, "status": "done"}

    summary = await runtime.run_task(task, step_executor, steps=3)
    assert summary["status"] == "SUCCESS"
    assert len(summary["results"]) == 3
    assert runtime.checkpoint is not None
    assert runtime.checkpoint.step_index == 3
    assert runtime.context.get_variable("step_val") == 2


@pytest.mark.asyncio
async def test_runtime_engine_cancellation_during_dispatch() -> None:
    """Verify runtime aborts loop when cancellation is detected during DISPATCH phase."""
    token = StepCancelledToken()
    runtime = AgentRuntime(token=token)
    task = ScheduledTask(id=uuid4())

    async def executor(
        t: ScheduledTask, idx: int, ctx: AgentContextManager
    ) -> Dict[str, Any]:
        return {"step": idx}

    with pytest.raises(JarvisAgentError) as excinfo:
        await runtime.run_task(task, executor, steps=1)
    assert excinfo.value.code == "AGENT_004"
    assert "cancelled" in excinfo.value.message


@pytest.mark.asyncio
async def test_runtime_engine_cancellation_during_wait_state() -> None:
    """Verify runtime aborts loop when cancellation is detected during WAIT phase."""
    token = WaitCancelledToken()
    runtime = AgentRuntime(token=token)
    task = ScheduledTask(id=uuid4())

    async def executor(
        t: ScheduledTask, idx: int, ctx: AgentContextManager
    ) -> Dict[str, Any]:
        return {"step": idx}

    with pytest.raises(JarvisAgentError) as excinfo:
        await runtime.run_task(task, executor, steps=1)
    assert excinfo.value.code == "AGENT_004"
    assert "cancelled" in excinfo.value.message


@pytest.mark.asyncio
async def test_runtime_engine_cancellation_during_wait() -> None:
    """Verify runtime aborts loop and cleans up during WAIT pause states on cancellation."""
    runtime = AgentRuntime()
    task = ScheduledTask(id=uuid4())

    async def long_step_executor(
        t: ScheduledTask, idx: int, ctx: AgentContextManager
    ) -> Dict[str, Any]:
        runtime.token.cancel()
        return {"step": idx}

    with pytest.raises(JarvisAgentError) as excinfo:
        await runtime.run_task(task, long_step_executor, steps=2)
    assert excinfo.value.code == "AGENT_004"
    assert "cancelled" in excinfo.value.message
    assert runtime.state == AgentExecutionState.IDLE


@pytest.mark.asyncio
async def test_runtime_engine_pause_and_resume() -> None:
    """Verify runtime pauses execution until resumed when CancellationToken is paused."""
    runtime = AgentRuntime()
    task = ScheduledTask(id=uuid4())
    runtime.token.pause()

    async def executor(
        t: ScheduledTask, idx: int, ctx: AgentContextManager
    ) -> Dict[str, Any]:
        return {"done": True}

    # Run in background to let it block on pause
    task_run = asyncio.create_task(runtime.run_task(task, executor, steps=1))
    await asyncio.sleep(0.05)
    assert runtime.token.is_paused

    # Resume the loop
    runtime.token.resume()
    summary = await task_run
    assert summary["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_runtime_engine_checkpoint_resumption() -> None:
    """Verify runtime checkpoint creation and task resumption from intermediate index."""
    runtime = AgentRuntime()
    task = ScheduledTask(id=uuid4())

    # Pre-populate a checkpoint from step 2
    checkpoint = CheckpointDTO(
        task_id=task.id,
        step_index=2,
        state_data={
            "results": [{"step": 0}, {"step": 1}],
            "variables": {"init_var": "val"},
        },
    )
    runtime.checkpoint = checkpoint

    async def executor(
        t: ScheduledTask, idx: int, ctx: AgentContextManager
    ) -> Dict[str, Any]:
        return {"step": idx, "saved_val": ctx.get_variable("init_var")}

    summary = await runtime.run_task(task, executor, steps=3)
    assert summary["status"] == "SUCCESS"
    assert len(summary["results"]) == 3
    assert summary["results"][0] == {"step": 0}
    assert summary["results"][1] == {"step": 1}
    assert summary["results"][2] == {"step": 2, "saved_val": "val"}


# =====================================================================
# 6. State Persistence & Event Integration Tests
# =====================================================================


@pytest.mark.asyncio
async def test_in_memory_state_store() -> None:
    """Verify state serialization inside InMemoryStateStore."""
    store = InMemoryStateStore()
    agent_id = "agent-123"
    state = {"status": "ACTIVE", "step": 5}

    await store.set_state(agent_id, state)
    fetched = await store.get_state(agent_id)
    assert fetched == state

    await store.delete_state(agent_id)
    assert await store.get_state(agent_id) is None


@pytest.mark.asyncio
async def test_redis_state_store() -> None:
    """Verify state serialization inside RedisStateStore using AsyncMock."""
    mock_redis = AsyncMock()
    store = RedisStateStore(client=mock_redis)
    agent_id = "agent-456"
    state = {"status": "ACTIVE", "step": 10}

    # Set mock behavior
    mock_redis.get.return_value = '{"status": "ACTIVE", "step": 10}'

    await store.set_state(agent_id, state)
    mock_redis.set.assert_called_once_with(
        f"jarvis:state:agent:{agent_id}", '{"status": "ACTIVE", "step": 10}'
    )

    fetched = await store.get_state(agent_id)
    assert fetched == state
    mock_redis.get.assert_called_once_with(f"jarvis:state:agent:{agent_id}")

    await store.delete_state(agent_id)
    mock_redis.delete.assert_called_once_with(f"jarvis:state:agent:{agent_id}")

    # Set mock behavior to return None to test falsy parsing branch
    mock_redis.get.return_value = None
    assert await store.get_state("non-existent") is None


@pytest.mark.asyncio
async def test_redis_state_store_exceptions() -> None:
    """Verify RedisStateStore raises JarvisSystemError if Redis operations fail."""
    mock_redis = AsyncMock()
    store = RedisStateStore(client=mock_redis)
    agent_id = "agent-999"

    # 1. get exception
    mock_redis.get.side_effect = Exception("Connection lost")
    with pytest.raises(JarvisSystemError) as excinfo:
        await store.get_state(agent_id)
    assert excinfo.value.code == "SYSTEM_001"

    # 2. set exception
    mock_redis.set.side_effect = Exception("Write forbidden")
    with pytest.raises(JarvisSystemError) as excinfo:
        await store.set_state(agent_id, {"status": "OK"})
    assert excinfo.value.code == "SYSTEM_001"

    # 3. delete exception
    mock_redis.delete.side_effect = Exception("Cluster down")
    with pytest.raises(JarvisSystemError) as excinfo:
        await store.delete_state(agent_id)
    assert excinfo.value.code == "SYSTEM_001"


@pytest.mark.asyncio
async def test_agent_runtime_notifier_publishes_event() -> None:
    """Verify AgentRuntimeNotifier publishes state transition messages on the event bus."""
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    notifier = AgentRuntimeNotifier(event_bus=event_bus)

    # Subscribe to state changed topic
    received_messages = []

    async def callback(msg: InterAgentMessage) -> None:
        received_messages.append(msg)

    await event_bus.subscribe("agent.state.changed", callback)

    agent_id = uuid4()
    published = await notifier.notify_state_changed(
        agent_id=agent_id,
        previous_state="IDLE",
        current_state="LOAD",
    )
    assert published is True

    # Yield to background callback processing
    await asyncio.sleep(0.1)

    assert len(received_messages) == 1
    msg = received_messages[0]
    assert msg.action == "agent_state_changed"
    assert msg.body["agent_id"] == str(agent_id)
    assert msg.body["previous_state"] == "IDLE"
    assert msg.body["current_state"] == "LOAD"

    await event_bus.stop()
    await event_bus.shutdown()
