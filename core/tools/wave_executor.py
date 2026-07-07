"""JARVIS OS - Wave Executor.

Coordinates parallel execution of WaveTasks using an event-driven DAG scheduler.
Respects concurrency semaphores, handles retry wrappers, and aggregates wave outcomes.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from core.exceptions import JarvisSystemError
from core.reasoning.planner import ReasoningSession
from core.tools.dependency_resolver import DependencyResolver
from core.tools.dto import (
    AggregatedWaveResult,
    ExecutionWave,
    ToolExecutionResult,
    WaveTask,
)
from core.tools.metrics_collector import ExecutionMetricsCollector
from core.tools.result_aggregator import WaveResultAggregator
from core.tools.retry_manager import RetryManager


class WaveExecutor:
    """DAG scheduler running WaveTasks concurrently based on dependency events."""

    def __init__(
        self,
        resolver: DependencyResolver,
        aggregator: WaveResultAggregator,
        retry_manager: RetryManager,
        metrics_collector: ExecutionMetricsCollector,
        concurrency_limit: int = 5,
    ) -> None:
        """Initialize WaveExecutor.

        Args:
            resolver: DependencyResolver to validate cycles.
            aggregator: WaveResultAggregator to compile results.
            retry_manager: RetryManager to handle retries.
            metrics_collector: ExecutionMetricsCollector for observability.
            concurrency_limit: Maximum active parallel tasks allowed globally.
        """
        self.resolver = resolver
        self.aggregator = aggregator
        self.retry_manager = retry_manager
        self.metrics_collector = metrics_collector
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def execute_wave(
        self,
        wave: ExecutionWave,
        session: ReasoningSession,
        orchestrator: Any,
    ) -> AggregatedWaveResult:
        """Run all tasks in the wave concurrently using a dynamic dependency graph.

        Args:
            wave: The execution wave structure.
            session: Active ReasoningSession context tracker.
            orchestrator: The orchestrator instance coordinating execution details.

        Returns:
            AggregatedWaveResult DTO containing outcomes of all tasks.
        """
        wave.status = "RUNNING"
        wave.started_at = datetime.now(timezone.utc)

        # 1. Validate dependencies for cycle errors
        try:
            self.resolver.resolve_execution_layers(wave.tasks)
        except JarvisSystemError as err:
            wave.status = "FAILURE"
            wave.completed_at = datetime.now(timezone.utc)
            return AggregatedWaveResult(
                wave_id=wave.wave_id,
                status="FAILURE",
                combined_stdout="",
                combined_stderr=f"DAG Validation failed: {err.message}",
                total_duration=0.0,
                artifacts={},
            )

        # 2. Setup event synchronization for dependencies
        task_events: Dict[UUID, asyncio.Event] = {
            t.task_id: asyncio.Event() for t in wave.tasks
        }
        task_results: Dict[UUID, ToolExecutionResult] = {}

        # Track active asyncio tasks for cancellations
        active_futures: Dict[UUID, asyncio.Task[Any]] = {}

        async def run_task(task: WaveTask) -> None:
            # Await all parent dependencies
            if task.dependencies:
                await asyncio.gather(
                    *(task_events[dep_id].wait() for dep_id in task.dependencies)
                )

                # Check if any parent failed/cancelled. If so, fail early.
                for dep_id in task.dependencies:
                    parent_res = task_results.get(dep_id)
                    if not parent_res or parent_res.status != "SUCCESS":
                        res = ToolExecutionResult(
                            task_id=task.task_id,
                            status="FAILURE",
                            error=f"Dependency task '{dep_id}' was not completed successfully.",
                            stdout="",
                            stderr="",
                        )
                        task_results[task.task_id] = res
                        task_events[task.task_id].set()
                        return

            # Enforce concurrency boundary semaphore
            async with self.semaphore:
                # Track start times
                start_time = time.perf_counter()

                # Execute with retry manager wrapper
                async def execute_callback() -> ToolExecutionResult:
                    res_val: ToolExecutionResult = (
                        await orchestrator.execute_task_step_internal(
                            task=task,
                            session=session,
                        )
                    )
                    return res_val

                try:
                    # Retry wrapper
                    res = await self.retry_manager.execute_with_retry(
                        task_fn=execute_callback,
                        policy=task.retry_policy,
                        metrics_collector=self.metrics_collector,
                        event_publisher_fn=orchestrator.publish_task_event,
                    )
                except asyncio.CancelledError:
                    res = ToolExecutionResult(
                        task_id=task.task_id,
                        status="CANCELLED",
                        error="Task was explicitly cancelled.",
                        duration=time.perf_counter() - start_time,
                    )
                except Exception as err:
                    res = ToolExecutionResult(
                        task_id=task.task_id,
                        status="ERROR",
                        error=str(err),
                        duration=time.perf_counter() - start_time,
                    )

                task_results[task.task_id] = res
                # Log metrics
                await self.metrics_collector.log_run(res.duration, res.status)

                # Set complete event and notify children
                task_events[task.task_id].set()

        # 3. Schedule all tasks in wave
        loop = asyncio.get_running_loop()
        futures: List[asyncio.Task[Any]] = []

        for task in wave.tasks:
            fut = loop.create_task(run_task(task))
            active_futures[task.task_id] = fut
            futures.append(fut)

            # Register inside orchestrator for cancellation controls
            orchestrator.register_active_task(task.task_id, fut, wave.wave_id)

        # 4. Wait for all tasks to complete
        await asyncio.gather(*futures, return_exceptions=True)

        # Cleanup orchestrator active registrations
        for task in wave.tasks:
            orchestrator.unregister_active_task(task.task_id)

        wave.completed_at = datetime.now(timezone.utc)

        # 5. Aggregate results
        aggregated = self.aggregator.aggregate_results(wave.wave_id, task_results)
        wave.status = aggregated.status
        return aggregated
