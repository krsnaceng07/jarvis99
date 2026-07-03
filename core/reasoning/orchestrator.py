"""JARVIS OS - Execution Orchestrator.

Coordinates planning waves, individual tool steps, human approval hooks,
observability metrics logging, and retry-safe idempotency verification.
"""

import asyncio
import time
from typing import Any, Dict, Optional, Set
from uuid import UUID, uuid4

from core.config import Settings
from core.interfaces import EventBusInterface, InterAgentMessage
from core.reasoning.planner import ReasoningSession
from core.tools.base import SkillManifest
from core.tools.dto import (
    AggregatedWaveResult,
    ExecutionWave,
    RetryPolicy,
    ToolExecutionResult,
    WaveTask,
)
from core.tools.metrics_collector import ExecutionMetricsCollector
from core.tools.retry_manager import RetryManager
from core.tools.runtime import ToolRuntime
from core.tools.wave_executor import WaveExecutor


class ExecutionOrchestrator:
    """Orchestration facade coordinating execution, metrics collection, and task lifecycles."""

    def __init__(
        self,
        tool_runtime: ToolRuntime,
        settings: Settings,
        wave_executor: Optional[WaveExecutor] = None,
        metrics_collector: Optional[ExecutionMetricsCollector] = None,
        event_bus: Optional[EventBusInterface] = None,
    ) -> None:
        """Initialize ExecutionOrchestrator.

        Args:
            tool_runtime: Underlay ToolRuntime execution engine.
            settings: Loaded configuration profiles.
            wave_executor: Service coordinating parallel wave execution.
            metrics_collector: Observability metric logger.
            event_bus: Event bus connection to publish status events.
        """
        self.tool_runtime = tool_runtime
        self.settings = settings
        self.metrics_collector = metrics_collector or ExecutionMetricsCollector()
        self.event_bus = event_bus or getattr(tool_runtime, "event_bus", None)

        if wave_executor is None:
            from core.tools.dependency_resolver import DependencyResolver
            from core.tools.result_aggregator import WaveResultAggregator

            resolver = DependencyResolver()
            aggregator = WaveResultAggregator()
            retry_manager = RetryManager()
            self.wave_executor = WaveExecutor(
                resolver=resolver,
                aggregator=aggregator,
                retry_manager=retry_manager,
                metrics_collector=self.metrics_collector,
                concurrency_limit=5,
            )
            self.retry_manager = retry_manager
        else:
            self.wave_executor = wave_executor
            self.retry_manager = (
                getattr(wave_executor, "retry_manager", None) or RetryManager()
            )

        # Active tasks mapping to support cancellations: task_id -> asyncio.Task
        self.active_tasks: Dict[UUID, asyncio.Task[Any]] = {}
        # Mapping of task_id -> wave_id to cancel complete waves
        self.task_wave_map: Dict[UUID, UUID] = {}

        # Idempotency cache: idempotency_key -> cached ToolExecutionResult
        self.processed_idempotency_keys: Set[UUID] = set()
        self.idempotency_results: Dict[UUID, ToolExecutionResult] = {}

    def register_active_task(
        self, task_id: UUID, future: asyncio.Task[Any], wave_id: UUID
    ) -> None:
        """Track an active running task for cancellation lookup.

        Args:
            task_id: UUID identifier of the task.
            future: Asyncio Task future wrapping task execution.
            wave_id: Associated parent wave UUID.
        """
        self.active_tasks[task_id] = future
        self.task_wave_map[task_id] = wave_id

    def unregister_active_task(self, task_id: UUID) -> None:
        """Remove finished task from lookup registry.

        Args:
            task_id: Target task UUID.
        """
        self.active_tasks.pop(task_id, None)
        self.task_wave_map.pop(task_id, None)

    async def cancel_task(self, task_id: UUID) -> bool:
        """Explicitly request cancellation of a running task future.

        Args:
            task_id: Target task UUID.

        Returns:
            True if task was registered and cancellation requested, False otherwise.
        """
        future = self.active_tasks.get(task_id)
        if future and not future.done():
            future.cancel()
            cancel_res = ToolExecutionResult(
                task_id=task_id,
                status="CANCELLED",
                error="Task explicitly cancelled.",
            )
            await self.publish_task_event("tool.cancelled", cancel_res)
            return True
        return False

    async def cancel_wave(self, wave_id: UUID) -> int:
        """Cancel all registered active tasks associated with the target wave.

        Args:
            wave_id: Target wave UUID.

        Returns:
            Count of cancelled tasks.
        """
        cancelled_count = 0
        target_tasks = [
            tid for tid, wid in self.task_wave_map.items() if wid == wave_id
        ]
        for tid in target_tasks:
            cancelled = await self.cancel_task(tid)
            if cancelled:
                cancelled_count += 1
        return cancelled_count

    async def execute_wave(
        self, wave: ExecutionWave, session: ReasoningSession
    ) -> AggregatedWaveResult:
        """Coordinate execution of all tasks in the wave.

        Args:
            wave: Target ExecutionWave model.
            session: Active ReasoningSession tracker.

        Returns:
            AggregatedWaveResult detailing combined outputs.
        """
        return await self.wave_executor.execute_wave(wave, session, self)

    async def execute_task_step(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session: ReasoningSession,
        caller_id: str = "orchestrator",
        system_env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Legacy sequential execution adapter converting calls to WaveTasks under the hood.

        Args:
            tool_name: Skill package identifier.
            arguments: Payload arguments mapping.
            session: Active ReasoningSession.
            caller_id: Requester identity.
            system_env: Optional scoped secrets payload.

        Returns:
            Legacy format dictionary result.
        """
        # Formulate temporary single-task wave DTO
        task = WaveTask(
            task_id=uuid4(),
            idempotency_key=uuid4(),
            tool_name=tool_name,
            arguments=arguments,
            priority=1,
            timeout=float(arguments.get("timeout", 900.0)),
            approval_level="L0",
            retry_policy=None,
            dependencies=[],
            metadata={},
        )

        # Define the execution callback
        async def execute_callback() -> ToolExecutionResult:
            return await self.execute_task_step_internal(
                task=task,
                session=session,
                caller_id=caller_id,
                system_env=system_env,
            )

        # Legacy retry config: up to 2 retries, 0.01s sleep, retry all failures
        policy = RetryPolicy(
            max_retries=2,
            delay=0.01,
            backoff_multiplier=1.0,
            retryable_errors=[],
        )

        res = await self.retry_manager.execute_with_retry(
            task_fn=execute_callback,
            policy=policy,
            metrics_collector=self.metrics_collector,
            event_publisher_fn=self.publish_task_event,
        )

        # Map to legacy dictionary format expected by external modules
        ret = {
            "status": res.status,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "exit_code": res.exit_code,
        }
        if res.error:
            ret["error"] = res.error
        return ret

    async def execute_task_step_internal(
        self,
        task: WaveTask,
        session: ReasoningSession,
        caller_id: str = "orchestrator",
        system_env: Optional[Dict[str, str]] = None,
    ) -> ToolExecutionResult:
        """Run single task execution steps, checking idempotency, L3 approval gates, and timeouts.

        Args:
            task: WaveTask model definition.
            session: Active ReasoningSession context tracker.
            caller_id: Agent identification.
            system_env: Environment config secrets.

        Returns:
            ToolExecutionResult outcome.
        """
        # 1. Idempotency safety lookup
        if task.idempotency_key in self.processed_idempotency_keys:
            cached_res = self.idempotency_results[task.idempotency_key]
            # Publish cached execution events sequence
            dummy_start = ToolExecutionResult(task_id=task.task_id, status="SUCCESS")
            dummy_start.artifacts["tool_name"] = task.tool_name
            await self.publish_task_event("tool.spawn.started", dummy_start)
            await self.publish_task_event("tool.running", dummy_start)
            await self.publish_task_event("tool.completed", cached_res)
            return cached_res

        # 2. Check and run L3 human-in-the-loop approvals
        needs_approval = False
        registry = getattr(self.tool_runtime, "registry", None)
        gatekeeper = getattr(self.tool_runtime, "gatekeeper", None)

        manifest: Optional[SkillManifest] = None
        if registry:
            try:
                manifest = registry.get_skill(task.tool_name)
            except AttributeError:
                pass

        if manifest and gatekeeper:
            for perm in manifest.permissions:
                if gatekeeper.get_permission_level(perm) in {"L2", "L3"}:
                    needs_approval = True
                    break

        if needs_approval and manifest and gatekeeper:
            wait_res = ToolExecutionResult(
                task_id=task.task_id, status="WAITING_APPROVAL"
            )
            wait_res.artifacts["tool_name"] = task.tool_name
            await self.publish_task_event("tool.approval.waiting", wait_res)

            approval_start = time.perf_counter()
            try:
                # Trigger verification checks directly
                for perm in manifest.permissions:
                    await gatekeeper.verify_permissions(task.tool_name, perm, caller_id)
                wait_duration = time.perf_counter() - approval_start
                await self.metrics_collector.log_approval_wait(wait_duration)

                granted_res = ToolExecutionResult(
                    task_id=task.task_id, status="SUCCESS"
                )
                granted_res.artifacts["tool_name"] = task.tool_name
                await self.publish_task_event("tool.approval.granted", granted_res)
            except Exception as err:
                wait_duration = time.perf_counter() - approval_start
                await self.metrics_collector.log_approval_wait(wait_duration)
                fail_res = ToolExecutionResult(
                    task_id=task.task_id,
                    status="FAILURE",
                    error=f"Permission rejected/timeout: {str(err)}",
                )
                fail_res.artifacts["tool_name"] = task.tool_name
                await self.publish_task_event("tool.failed", fail_res)
                return fail_res

        # 3. Execution run
        start_res = ToolExecutionResult(task_id=task.task_id, status="SUCCESS")
        start_res.artifacts["tool_name"] = task.tool_name
        await self.publish_task_event("tool.spawn.started", start_res)
        await self.publish_task_event("tool.running", start_res)

        start_time = time.perf_counter()
        try:
            # Wrap execution run in wait_for to enforce dynamic timeouts
            timeout = task.timeout if task.timeout > 0.0 else 900.0
            if (
                manifest
                and manifest.timeout > 0.0
                and (task.timeout == 900.0 or task.timeout <= 0.0)
            ):
                timeout = manifest.timeout

            # Update timeout arguments payload
            args = dict(task.arguments)
            args["timeout"] = timeout

            runtime_res = await asyncio.wait_for(
                self.tool_runtime.execute_tool(
                    tool_name=task.tool_name,
                    arguments=args,
                    caller_id=caller_id,
                    system_env=system_env,
                ),
                timeout=timeout,
            )

            res = ToolExecutionResult(
                task_id=task.task_id,
                status="SUCCESS" if runtime_res.exit_code == 0 else "FAILURE",
                stdout=runtime_res.stdout,
                stderr=runtime_res.stderr,
                exit_code=runtime_res.exit_code,
                duration=runtime_res.duration,
                memory_usage=runtime_res.memory_usage,
                cpu_usage=runtime_res.cpu_usage,
                truncated=runtime_res.truncated,
                audit_id=runtime_res.audit_id,
                artifacts={"tool_name": task.tool_name},
                error=None
                if runtime_res.exit_code == 0
                else "Non-zero exit code status.",
            )

        except asyncio.TimeoutError:
            await self.metrics_collector.log_timeout()
            res = ToolExecutionResult(
                task_id=task.task_id,
                status="TIMEOUT",
                exit_code=124,
                duration=time.perf_counter() - start_time,
                artifacts={"tool_name": task.tool_name},
                error=f"Task execution exceeded timeout limit of {timeout}s.",
            )
            await self.publish_task_event("tool.timeout", res)

        except Exception as err:
            res = ToolExecutionResult(
                task_id=task.task_id,
                status="ERROR",
                exit_code=-1,
                duration=time.perf_counter() - start_time,
                artifacts={"tool_name": task.tool_name},
                error=str(err),
            )

        # 4. Final events and caching
        res.artifacts["tool_name"] = task.tool_name
        if res.status == "SUCCESS":
            await self.publish_task_event("tool.completed", res)
        elif res.status != "TIMEOUT":
            await self.publish_task_event("tool.failed", res)

        # Cache results for idempotency registry check only on success
        if res.status == "SUCCESS":
            self.processed_idempotency_keys.add(task.idempotency_key)
            self.idempotency_results[task.idempotency_key] = res

        # Record tool trace log in reasoning session for compatibility
        trace_entry = {
            "tool_name": task.tool_name,
            "arguments": task.arguments,
            "status": "success" if res.status == "SUCCESS" else "failure",
            "exit_code": res.exit_code,
            "duration_s": res.duration,
            "error": res.error,
        }
        session.tool_calls.append(trace_entry)

        # Sync reasoning session latencies for compatibility
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        session.latency_ms += duration_ms

        return res

    async def publish_task_event(self, topic: str, result: ToolExecutionResult) -> None:
        """Publish execution updates to the global event bus dispatcher.

        Args:
            topic: Trigger event action topic name.
            result: Current ToolExecutionResult.
        """
        if not self.event_bus:
            return

        msg = InterAgentMessage(
            id=uuid4(),
            correlation_id=result.task_id,
            sender="tool_orchestrator",
            receiver="system_broadcast",
            action=topic,
            body={
                "task_id": str(result.task_id),
                "status": result.status,
                "tool_name": result.artifacts.get("tool_name", ""),
                "exit_code": result.exit_code,
                "duration": result.duration,
                "error": result.error,
            },
        )
        await self.event_bus.publish(topic, msg)
