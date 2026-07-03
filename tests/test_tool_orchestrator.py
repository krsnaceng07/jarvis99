"""JARVIS OS - Tool Orchestrator Integration & Unit Tests.

Verifies parallel wave execution, dynamic DAG dependency scheduling, idempotency checks,
L3 non-blocking approvals, timeouts, cancellations, metrics collection, and DI container setup.
"""

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.exceptions import JarvisSystemError
from core.interfaces import InterAgentMessage
from core.kernel import Kernel
from core.memory.database import db_manager
from core.memory.models import Base
from core.reasoning.orchestrator import ExecutionOrchestrator
from core.reasoning.planner import ReasoningSession
from core.tools.dependency_resolver import DependencyResolver
from core.tools.dto import ExecutionWave, RetryPolicy, ToolExecutionResult, WaveTask
from core.tools.metrics_collector import ExecutionMetricsCollector
from core.tools.registry import ToolRegistry
from core.tools.result_aggregator import WaveResultAggregator
from core.tools.retry_manager import RetryManager
from core.tools.runtime import ToolRuntime
from core.tools.sandbox import LocalSubprocessSandbox
from core.tools.security import PermissionGatekeeper
from core.tools.wave_executor import WaveExecutor


@pytest.mark.asyncio
async def test_dependency_resolver_dag_and_cycles() -> None:
    """Verify DependencyResolver correctly resolves layers and detects circular loops."""
    resolver = DependencyResolver()

    task_a = WaveTask(tool_name="tool-a", priority=1)
    task_b = WaveTask(tool_name="tool-b", priority=1, dependencies=[task_a.task_id])
    task_c = WaveTask(tool_name="tool-c", priority=1, dependencies=[task_b.task_id])

    # 1. Successful DAG layers resolution
    layers = resolver.resolve_execution_layers([task_a, task_b, task_c])
    assert len(layers) == 3
    assert layers[0] == [task_a]
    assert layers[1] == [task_b]
    assert layers[2] == [task_c]

    # 2. Circular dependency detection
    task_c.dependencies = [task_a.task_id]
    task_a.dependencies = [task_c.task_id]
    with pytest.raises(JarvisSystemError) as excinfo:
        resolver.resolve_execution_layers([task_a, task_b, task_c])
    assert excinfo.value.code == "ORCH_002"
    assert "Circular dependency" in excinfo.value.message

    # 3. Missing dependency check
    task_a.dependencies = []
    task_b.dependencies = [uuid4()]  # Random ID not present
    with pytest.raises(JarvisSystemError) as excinfo_missing:
        resolver.resolve_execution_layers([task_a, task_b])
    assert excinfo_missing.value.code == "ORCH_001"
    assert "missing task" in excinfo_missing.value.message.lower()


@pytest.mark.asyncio
async def test_result_aggregator_merges_data() -> None:
    """Verify WaveResultAggregator merges stdout, stderr, and metadata artifacts."""
    aggregator = WaveResultAggregator()
    wave_id = uuid4()
    task_1 = uuid4()
    task_2 = uuid4()

    res1 = ToolExecutionResult(
        task_id=task_1,
        status="SUCCESS",
        stdout="stdout-1",
        stderr="stderr-1",
        duration=1.5,
        exit_code=0,
        artifacts={"file": "a.txt"},
    )
    res2 = ToolExecutionResult(
        task_id=task_2,
        status="FAILURE",
        stdout="stdout-2",
        stderr="stderr-2",
        duration=2.0,
        exit_code=1,
        artifacts={"file2": "b.txt"},
    )

    results = {task_1: res1, task_2: res2}
    aggregated = aggregator.aggregate_results(wave_id, results)

    assert aggregated.wave_id == wave_id
    assert aggregated.status == "PARTIAL_FAILURE"
    assert task_1 in aggregated.tasks_completed
    assert task_2 in aggregated.tasks_failed
    assert "stdout-1" in aggregated.combined_stdout
    assert "stderr-2" in aggregated.combined_stderr
    assert aggregated.total_duration == 3.5
    assert aggregated.artifacts[f"{task_1}_file"] == "a.txt"


@pytest.mark.asyncio
async def test_metrics_collector_averages() -> None:
    """Verify ExecutionMetricsCollector logs run states and calculates correct ratios."""
    collector = ExecutionMetricsCollector()

    await collector.log_run(duration_s=2.0, status="SUCCESS")
    await collector.log_run(duration_s=4.0, status="FAILURE")
    await collector.log_run(duration_s=0.0, status="CANCELLED")
    await collector.log_retry()
    await collector.log_timeout()
    await collector.log_approval_wait(5.0)

    report = await collector.get_report()
    assert report["total_runs"] == 3.0
    assert report["success_runs"] == 1.0
    assert report["failed_runs"] == 1.0
    assert report["cancelled_runs"] == 1.0
    assert report["retry_runs"] == 1.0
    assert report["timeout_runs"] == 1.0
    assert report["approval_wait_time_s"] == 5.0
    assert report["avg_duration_s"] == 2.0
    assert report["success_rate"] == pytest.approx(0.33, abs=0.01)
    assert report["failure_rate"] == pytest.approx(0.33, abs=0.01)


@pytest.mark.asyncio
async def test_retry_manager_backoffs() -> None:
    """Verify RetryManager applies delay configurations and matching rules."""
    retry_manager = RetryManager()
    metrics = ExecutionMetricsCollector()

    attempts = 0

    async def failing_callback() -> ToolExecutionResult:
        nonlocal attempts
        attempts += 1
        return ToolExecutionResult(
            status="FAILURE",
            stdout="",
            stderr="database error",
            exit_code=1,
            error="database error",
        )

    policy = RetryPolicy(
        max_retries=2,
        delay=0.01,
        backoff_multiplier=2.0,
        retryable_errors=["database"],
    )

    res = await retry_manager.execute_with_retry(
        task_fn=failing_callback,
        policy=policy,
        metrics_collector=metrics,
    )

    assert attempts == 3  # 1 initial + 2 retries
    assert res.status == "FAILURE"
    assert (await metrics.get_report())["retry_runs"] == 2.0


@pytest.mark.asyncio
async def test_orchestration_wave_concurrency_and_events() -> None:
    """Verify ExecutionOrchestrator coordinates parallel tasks, checks idempotency, and handles DAG schedules."""
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    # Initialize memory DB
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create and register a mock skill
        skill_name = "test_skill"
        skill_path = os.path.join(temp_dir, skill_name)
        os.makedirs(skill_path)

        with open(os.path.join(skill_path, "main.py"), "w") as f:
            f.write("print('test')")

        sig = PermissionGatekeeper.calculate_directory_hash(skill_path)
        manifest_data = {
            "name": "test-skill",
            "version": "1.0.0",
            "entry_point": "main.py",
            "permissions": [],
            "signature": sig,
            "jarvis_api_version": "1.0",
            "skill_version": "1.0.0",
            "min_runtime_version": "1.0",
        }
        with open(os.path.join(skill_path, "manifest.json"), "w") as f:
            json.dump(manifest_data, f)

        registry = ToolRegistry(skills_dir=temp_dir)
        registry.load_skill_manifest(skill_name)

        # Setup orchestrator components
        sandbox = LocalSubprocessSandbox()
        gatekeeper = PermissionGatekeeper(event_bus=event_bus)
        runtime = ToolRuntime(
            registry=registry,
            sandbox=sandbox,
            gatekeeper=gatekeeper,
            event_bus=event_bus,
        )

        resolver = DependencyResolver()
        aggregator = WaveResultAggregator()
        retry_mgr = RetryManager()
        metrics = ExecutionMetricsCollector()

        wave_exec = WaveExecutor(
            resolver=resolver,
            aggregator=aggregator,
            retry_manager=retry_mgr,
            metrics_collector=metrics,
            concurrency_limit=5,
        )

        orchestrator = ExecutionOrchestrator(
            tool_runtime=runtime,
            wave_executor=wave_exec,
            metrics_collector=metrics,
            event_bus=event_bus,
            settings=settings,
        )

        session = ReasoningSession(session_id=uuid4(), goal_id=uuid4())

        # Test events collection
        received_topics = []

        async def callback(msg: InterAgentMessage) -> None:
            received_topics.append(msg.action)

        # Subscribe to some topics
        await event_bus.subscribe("tool.spawn.started", callback)
        await event_bus.subscribe("tool.running", callback)
        await event_bus.subscribe("tool.completed", callback)

        # 1. Run a parallel execution wave of 2 independent tasks
        task_a = WaveTask(
            task_id=uuid4(),
            idempotency_key=uuid4(),
            tool_name="test-skill",
            arguments={"command": ["python", "-c", "print('hello-a')"]},
        )
        task_b = WaveTask(
            task_id=uuid4(),
            idempotency_key=uuid4(),
            tool_name="test-skill",
            arguments={"command": ["python", "-c", "print('hello-b')"]},
            dependencies=[task_a.task_id],  # B depends on A
        )

        wave = ExecutionWave(wave_id=uuid4(), tasks=[task_a, task_b])
        result = await orchestrator.execute_wave(wave, session)

        assert result.status == "SUCCESS"
        assert len(result.tasks_completed) == 2
        assert "hello-a" in result.combined_stdout
        assert "hello-b" in result.combined_stdout

        await asyncio.sleep(0.1)  # Yield for event handler
        assert "tool.spawn.started" in received_topics
        assert "tool.running" in received_topics
        assert "tool.completed" in received_topics

        # 2. Verify Idempotency Cache
        # Running task_a again with the same idempotency_key returns cached result immediately
        res_dup = await orchestrator.execute_task_step_internal(task_a, session)
        assert res_dup.status == "SUCCESS"
        assert "hello-a" in res_dup.stdout

    # Cleanup
    await db_manager.close()
    await event_bus.stop()
    await event_bus.shutdown()


@pytest.mark.asyncio
async def test_non_blocking_l3_approval() -> None:
    """Verify that while one task is in WAITING_APPROVAL state, other independent parallel tasks execute."""
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a skill requiring L3 CLI permission
        skill_name = "test_l3"
        skill_path = os.path.join(temp_dir, skill_name)
        os.makedirs(skill_path)
        with open(os.path.join(skill_path, "main.py"), "w") as f:
            f.write("print('ok')")

        sig = PermissionGatekeeper.calculate_directory_hash(skill_path)
        manifest_data = {
            "name": "test-l3",
            "version": "1.0.0",
            "entry_point": "main.py",
            "permissions": ["cli"],  # Requires L3 clearance
            "signature": sig,
            "jarvis_api_version": "1.0",
            "skill_version": "1.0.0",
            "min_runtime_version": "1.0",
        }
        with open(os.path.join(skill_path, "manifest.json"), "w") as f:
            json.dump(manifest_data, f)

        # Create another normal skill
        skill_name_ok = "test_ok"
        skill_path_ok = os.path.join(temp_dir, skill_name_ok)
        os.makedirs(skill_path_ok)
        with open(os.path.join(skill_path_ok, "main.py"), "w") as f:
            f.write("print('normal')")

        sig_ok = PermissionGatekeeper.calculate_directory_hash(skill_path_ok)
        manifest_data_ok = {
            "name": "test-ok",
            "version": "1.0.0",
            "entry_point": "main.py",
            "permissions": ["file_read"],  # Normal L0
            "signature": sig_ok,
            "jarvis_api_version": "1.0",
            "skill_version": "1.0.0",
            "min_runtime_version": "1.0",
        }
        with open(os.path.join(skill_path_ok, "manifest.json"), "w") as f:
            json.dump(manifest_data_ok, f)

        registry = ToolRegistry(skills_dir=temp_dir)
        registry.load_skill_manifest(skill_name)
        registry.load_skill_manifest(skill_name_ok)

        sandbox = LocalSubprocessSandbox()
        gatekeeper = PermissionGatekeeper(event_bus=event_bus, approval_timeout=1.0)
        runtime = ToolRuntime(
            registry=registry,
            sandbox=sandbox,
            gatekeeper=gatekeeper,
            event_bus=event_bus,
        )

        resolver = DependencyResolver()
        aggregator = WaveResultAggregator()
        retry_mgr = RetryManager()
        metrics = ExecutionMetricsCollector()

        wave_exec = WaveExecutor(
            resolver=resolver,
            aggregator=aggregator,
            retry_manager=retry_mgr,
            metrics_collector=metrics,
            concurrency_limit=5,
        )

        orchestrator = ExecutionOrchestrator(
            tool_runtime=runtime,
            wave_executor=wave_exec,
            metrics_collector=metrics,
            event_bus=event_bus,
            settings=Settings.load_settings(),
        )

        session = ReasoningSession(session_id=uuid4(), goal_id=uuid4())

        # Task A: Requires L3 (blocked on approval)
        task_a = WaveTask(
            task_id=uuid4(),
            tool_name="test-l3",
            arguments={"command": ["python", "-c", "print('hello-l3')"]},
        )
        # Task B: Normal L0 (runs immediately)
        task_b = WaveTask(
            task_id=uuid4(),
            tool_name="test-ok",
            arguments={"command": ["python", "-c", "print('hello-normal')"]},
        )

        # Execute wave concurrently
        wave = ExecutionWave(wave_id=uuid4(), tasks=[task_a, task_b])

        # Since we do not simulate approval, Task A will fail with Timeout, but Task B should run and succeed
        res = await orchestrator.execute_wave(wave, session)

        assert res.status == "PARTIAL_FAILURE"
        assert task_b.task_id in res.tasks_completed
        assert task_a.task_id in res.tasks_failed
        assert "hello-normal" in res.combined_stdout

    await event_bus.stop()
    await event_bus.shutdown()


@pytest.mark.asyncio
async def test_cancellation_api() -> None:
    """Verify task and wave cancellation terminates running processes."""
    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    with tempfile.TemporaryDirectory() as temp_dir:
        skill_name = "test_cancel"
        skill_path = os.path.join(temp_dir, skill_name)
        os.makedirs(skill_path)
        with open(os.path.join(skill_path, "main.py"), "w") as f:
            f.write("print('ok')")

        sig = PermissionGatekeeper.calculate_directory_hash(skill_path)
        manifest_data = {
            "name": "test-cancel",
            "version": "1.0.0",
            "entry_point": "main.py",
            "permissions": [],
            "signature": sig,
            "jarvis_api_version": "1.0",
            "skill_version": "1.0.0",
            "min_runtime_version": "1.0",
        }
        with open(os.path.join(skill_path, "manifest.json"), "w") as f:
            json.dump(manifest_data, f)

        registry = ToolRegistry(skills_dir=temp_dir)
        registry.load_skill_manifest(skill_name)

        sandbox = LocalSubprocessSandbox()
        gatekeeper = PermissionGatekeeper(event_bus=event_bus)
        runtime = ToolRuntime(
            registry=registry,
            sandbox=sandbox,
            gatekeeper=gatekeeper,
            event_bus=event_bus,
        )

        resolver = DependencyResolver()
        aggregator = WaveResultAggregator()
        retry_mgr = RetryManager()
        metrics = ExecutionMetricsCollector()

        wave_exec = WaveExecutor(
            resolver=resolver,
            aggregator=aggregator,
            retry_manager=retry_mgr,
            metrics_collector=metrics,
            concurrency_limit=5,
        )

        orchestrator = ExecutionOrchestrator(
            tool_runtime=runtime,
            wave_executor=wave_exec,
            metrics_collector=metrics,
            event_bus=event_bus,
            settings=Settings.load_settings(),
        )

        session = ReasoningSession(session_id=uuid4(), goal_id=uuid4())

        # Long running sleep task to allow cancellation mid-flight
        task = WaveTask(
            task_id=uuid4(),
            tool_name="test-cancel",
            arguments={"command": ["python", "-c", "import time; time.sleep(10)"]},
        )

        wave = ExecutionWave(wave_id=uuid4(), tasks=[task])

        # Execute in background
        exec_fut = asyncio.create_task(orchestrator.execute_wave(wave, session))

        await asyncio.sleep(0.1)  # Let it start
        assert task.task_id in orchestrator.active_tasks

        # Cancel the wave
        cancelled_count = await orchestrator.cancel_wave(wave.wave_id)
        assert cancelled_count == 1

        res = await exec_fut
        assert res.status == "FAILURE"
        assert task.task_id in res.tasks_failed

    await event_bus.stop()
    await event_bus.shutdown()


@pytest.mark.asyncio
async def test_kernel_bootstrap_di() -> None:
    """Verify Kernel boots all orchestration services and binds them to the container."""
    kernel = Kernel()
    await kernel.initialize()

    # Mock vault and event bus internals
    setattr(kernel, "_load_vault", AsyncMock(return_value=True))
    setattr(kernel, "_initialize_event_bus", AsyncMock(return_value=True))

    boot_ok = await kernel.boot("config.yaml")
    assert boot_ok

    # Verify singletons can be resolved
    assert kernel.container.resolve(ToolRegistry) is not None
    assert kernel.container.resolve(PermissionGatekeeper) is not None
    assert kernel.container.resolve(ToolRuntime) is not None
    assert kernel.container.resolve(WaveExecutor) is not None
    assert kernel.container.resolve(ExecutionOrchestrator) is not None
    assert kernel.container.resolve(ExecutionMetricsCollector) is not None

    # Shutdown
    await kernel.lifecycle_manager.stop_all()
    await kernel.lifecycle_manager.shutdown_all()
