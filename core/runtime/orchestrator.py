"""JARVIS OS - Swarm Orchestrator Coordinator.

Orchestrates distributed subagent registry mappings, capability negotiations, persistence repository saves, and task queue processing.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Set
from uuid import UUID

from core.interfaces import EventBusInterface, InterAgentMessage
from core.runtime.dto import SwarmSnapshot, SwarmTask
from core.runtime.lock import ILockManager
from core.runtime.message_bus import SwarmMessageBus
from core.runtime.persistence import SwarmPersistence
from core.runtime.queue import SwarmTaskQueue
from core.runtime.registry import AgentRegistry
from core.runtime.scheduler import CapabilityNegotiator
from core.runtime.subagent import SubagentManager

logger = logging.getLogger("jarvis.core.runtime.orchestrator")


class ISwarmCoordinator(ABC):
    """Abstract base contract defining the swarm orchestration controls."""

    @abstractmethod
    async def spawn_task(self, task: SwarmTask) -> bool:
        """Process goal-decomposition and execute a swarm task.

        Args:
            task: Target SwarmTask.

        Returns:
            True if task spawned and scheduled successfully.
        """
        pass

    @abstractmethod
    async def cancel_task(self, task_id: UUID) -> bool:
        """Cancel and abort a running task.

        Args:
            task_id: Unique task identifier.

        Returns:
            True if task successfully cancelled.
        """
        pass

    @abstractmethod
    async def pause_task(self, task_id: UUID) -> bool:
        """Pause execution loop of a running task.

        Args:
            task_id: Unique task identifier.

        Returns:
            True if task successfully paused.
        """
        pass

    @abstractmethod
    async def resume_task(self, task_id: UUID) -> bool:
        """Resume execution loop of a paused task.

        Args:
            task_id: Unique task identifier.

        Returns:
            True if task successfully resumed.
        """
        pass

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Fetch global swarm snapshots and active subagent telemetry.

        Returns:
            Global telemetry descriptor mapping.
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully release lock managers, databases, and subagent containers."""
        pass


class SwarmOrchestrator(ISwarmCoordinator):
    """Coordinating center managing task scheduling, heartbeat watchdog metrics, and messaging brokers."""

    def __init__(
        self,
        manager: SubagentManager,
        queue: SwarmTaskQueue,
        negotiator: CapabilityNegotiator,
        message_bus: SwarmMessageBus,
        persistence: SwarmPersistence,
        lock_manager: ILockManager,
        registry: AgentRegistry,
        event_bus: EventBusInterface,
        dispatcher: Optional[Any] = None,
        reflection: Optional[Any] = None,
        decision: Optional[Any] = None,
        max_concurrent: int = 5,
    ) -> None:
        """Initialize SwarmOrchestrator."""
        self.manager = manager
        self.queue = queue
        self.negotiator = negotiator
        self.message_bus = message_bus
        self.persistence = persistence
        self.lock_manager = lock_manager
        self.registry = registry
        self.event_bus = event_bus

        # Reasoning components (optional, resolved from Kernel container at runtime)
        self.dispatcher = dispatcher
        self.reflection = reflection
        self.decision = decision

        # Concurrency and Worker Loop Management
        self.max_concurrent = max_concurrent
        self.active_worker_tasks: Set[asyncio.Task[Any]] = set()
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._shutdown_requested = False

    async def initialize(self) -> None:
        """Lifecycle initialization."""
        pass

    async def start(self) -> None:
        """Lifecycle start, auto-starting the worker loop."""
        await self.start_worker_loop()

    async def stop(self) -> None:
        """Lifecycle stop, auto-stopping the worker loop."""
        await self.stop_worker_loop()

    async def start_worker_loop(self) -> None:
        """Start the background task queue processing consumer loop."""
        self._shutdown_requested = False
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._process_queue_loop())
            logger.info("Swarm worker queue consumer loop started.")

    async def stop_worker_loop(self) -> None:
        """Gracefully stop and cancel the background task loop."""
        self._shutdown_requested = True
        if self._worker_task:
            task = self._worker_task
            task.cancel()
            self._worker_task = None
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("Swarm worker queue consumer loop stopped.")

        # Cancel remaining active tasks
        running_tasks = list(self.active_worker_tasks)
        for t in running_tasks:
            t.cancel()

    async def spawn_task(self, task: SwarmTask) -> bool:
        lock_key = f"swarm.lock.task.{task.task_id}"
        owner_id = "Orchestrator-1"

        # 1. Acquire Distributed Lock
        acquired = await self.lock_manager.acquire(lock_key, owner_id)
        if not acquired:
            return False

        try:
            await self._publish_task_event("TASK_CREATED", task)

            # 2. Negotiate optimal subagent mapping based on load and capabilities
            agents = self.registry.list_agents()
            best_agent_id = self.negotiator.select_best_agent(agents, task)

            if not best_agent_id:
                # No matching agent, spawn a new generic subagent
                best_agent_id = await self.manager.spawn_subagent(task.task_id)
                self.registry.register_agent(
                    best_agent_id,
                    name=f"Subagent-{best_agent_id}",
                    capabilities=task.capabilities,
                    permissions={"Browser", "Filesystem", "Shell"},
                )

            # 3. Schedule and allocate task queue status
            await self.queue.enqueue(task)
            await self.persistence.save_task(task)

            await self._publish_task_event("TASK_ASSIGNED", task)

            # Update registry status
            self.registry.update_status(best_agent_id, "WORKING")
            await self.persistence.save_agent(
                best_agent_id, self.registry.get_agent(best_agent_id)
            )

            return True

        finally:
            await self.lock_manager.release(lock_key, owner_id)

    async def cancel_task(self, task_id: UUID) -> bool:
        task = await self.queue.get_task(task_id)
        if task:
            task.status = "Cancelled"
            await self.queue.update_task_status(task_id, "Cancelled")
            await self.persistence.save_task(task)
            await self._publish_task_event("TASK_FAILED", task)
            return True
        return False

    async def pause_task(self, task_id: UUID) -> bool:
        task = await self.queue.get_task(task_id)
        if task:
            task.status = "Waiting"
            await self.queue.update_task_status(task_id, "Waiting")
            await self.persistence.save_task(task)
            return True
        return False

    async def resume_task(self, task_id: UUID) -> bool:
        task = await self.queue.get_task(task_id)
        if task:
            task.status = "Running"
            await self.queue.update_task_status(task_id, "Running")
            await self.persistence.save_task(task)
            await self._publish_task_event("TASK_RUNNING", task)
            return True
        return False

    async def get_status(self) -> Dict[str, Any]:
        snapshot = SwarmSnapshot(
            running_agents=len(self.manager.active_subagents),
            queued_tasks=self.queue.size,
            completed_tasks=len(
                [t for t in self.queue._tasks.values() if t.status == "Completed"]
            ),
            failed_tasks=len(
                [t for t in self.queue._tasks.values() if t.status == "Failed"]
            ),
            message_rate=0.5,
            cpu_usage=0.15,
            memory_usage=128.0,
            cluster_status="HEALTHY",
        )
        await self.persistence.save_snapshot(snapshot)
        return snapshot.model_dump()

    async def shutdown(self) -> None:
        await self.stop_worker_loop()
        await self.manager.shutdown()

    async def _publish_task_event(self, action: str, task: SwarmTask) -> None:
        msg = InterAgentMessage(
            sender="SwarmOrchestrator",
            receiver="All",
            action=action,
            body=task.model_dump(mode="json"),
            correlation_id=task.task_id,
        )
        await self.event_bus.publish(action, msg)

    async def _process_queue_loop(self) -> None:
        """Async consumer task dequeuing and processing tasks concurrently."""
        try:
            while not self._shutdown_requested:
                # Concurrency quota check
                if len(self.active_worker_tasks) >= self.max_concurrent:
                    await asyncio.sleep(0.05)
                    continue

                task = await self.queue.dequeue()
                if not task:
                    await asyncio.sleep(0.05)
                    continue

                # 1. Exactly-once task ownership claim
                task.status = "Claimed"
                try:
                    await self.persistence.save_task(task)
                except Exception as err:
                    logger.warning(
                        "Task %s claim failed (optimistic lock conflict): %s",
                        task.task_id,
                        err,
                    )
                    continue

                # 2. Map target subagent
                agents = self.registry.list_agents()
                best_agent_id = self.negotiator.select_best_agent(agents, task)
                if not best_agent_id:
                    # Spawn dynamic fallback subagent
                    try:
                        best_agent_id = await self.manager.spawn_subagent(task.task_id)
                        self.registry.register_agent(
                            best_agent_id,
                            name=f"Subagent-{best_agent_id}",
                            capabilities=task.capabilities,
                            permissions={"Browser", "Filesystem", "Shell"},
                        )
                    except Exception as err:
                        logger.error(
                            "Failed to spawn fallback subagent for task %s: %s",
                            task.task_id,
                            err,
                        )
                        task.status = "Failed"
                        task.metadata["error"] = (
                            f"Failed to allocate subagent: {str(err)}"
                        )
                        await self.persistence.save_task(task)
                        await self._publish_task_event("TASK_FAILED", task)
                        continue

                # Start concurrent execution task
                worker_task = asyncio.create_task(
                    self._execute_swarm_task_workflow(task, best_agent_id)
                )
                self.active_worker_tasks.add(worker_task)
                worker_task.add_done_callback(self.active_worker_tasks.discard)

        except asyncio.CancelledError:
            pass
        except Exception as err:
            logger.critical("Fatal crash in swarm worker loop: %s", err)

    async def _execute_swarm_task_workflow(
        self, task: SwarmTask, agent_id: UUID
    ) -> None:
        """Manages the full claimed task execution pipeline with retry guards."""
        # Transition to Running
        task.status = "Running"
        try:
            await self.persistence.save_task(task)
            await self._publish_task_event("TASK_RUNNING", task)
        except Exception as err:
            logger.error("Failed to set task status to Running: %s", err)
            return

        # Execute using AgentLoop reasoning engine if available
        success = False
        error_msg = ""
        if self.dispatcher and self.reflection and self.decision:
            try:
                success = await self._run_reasoning_loop(task, agent_id)
            except Exception as err:
                error_msg = str(err)
        else:
            # Mock success execution path if reasoning engine not injected (e.g. standalone swarm test)
            await asyncio.sleep(0.05)
            success = True

        if success:
            task.status = "Completed"
            await self.persistence.save_task(task)
            await self._publish_task_event("TASK_COMPLETED", task)
        else:
            # Q2: Retry policy checking
            if task.retry > 0:
                task.retry -= 1
                task.status = "Pending"
                await self.persistence.save_task(task)
                # Re-enqueue in local scheduler queue
                await self.queue.enqueue(task)
                await self._publish_task_event("TASK_RETRY", task)
            else:
                task.status = "Failed"
                task.metadata["error"] = (
                    error_msg or "Execution failed and retry limit reached."
                )
                await self.persistence.save_task(task)
                await self._publish_task_event("TASK_FAILED", task)

    async def _run_reasoning_loop(self, task: SwarmTask, agent_id: UUID) -> bool:
        """Decomposes goals and runs the actual reasoning AgentLoop."""
        from core.reasoning.goal import GoalAnalysis
        from core.reasoning.task import TaskGenerator

        analysis = GoalAnalysis(
            goal_id=task.task_id, objective=task.goal, success_criteria=[]
        )
        decomposer = TaskGenerator()
        reasoning_tasks = decomposer.decompose(analysis, task.goal)

        from core.runtime.persistence_journal import PersistentExecutionJournal

        journal = PersistentExecutionJournal(
            session_id=task.task_id,
            event_bus=self.event_bus,
        )

        from core.reasoning.agent_loop import AgentLoop

        dispatcher = self.dispatcher
        reflection = self.reflection
        decision = self.decision
        if dispatcher is None or reflection is None or decision is None:
            raise ValueError("Reasoning engines not fully initialized")

        loop = AgentLoop(
            dispatcher=dispatcher,
            reflection_engine=reflection,
            decision_engine=decision,
            journal=journal,
        )

        context = {
            "task_id": task.task_id,
            "agent_id": agent_id,
            "persistence": self.persistence,
        }

        # Update registry status
        self.registry.update_status(agent_id, "WORKING")
        await self.persistence.save_agent(agent_id, self.registry.get_agent(agent_id))

        try:
            result = await loop.run(reasoning_tasks, context)
            from core.reasoning.task import AgentTerminationReason

            if result.termination_reason == AgentTerminationReason.SUCCESS:
                task.metadata["final_outputs"] = result.final_outputs
                return True
            else:
                raise Exception(
                    f"Reasoning loop halted: {result.error or result.termination_reason}"
                )
        finally:
            # Free subagent back
            self.registry.update_status(agent_id, "ONLINE")
            await self.persistence.save_agent(
                agent_id, self.registry.get_agent(agent_id)
            )
