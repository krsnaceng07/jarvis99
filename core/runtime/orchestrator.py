"""JARVIS OS - Swarm Orchestrator Coordinator.

Orchestrates distributed subagent registry mappings, capability negotiations, persistence repository saves, and task queue processing.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
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

    async def spawn_task(self, task: SwarmTask) -> bool:
        lock_key = f"swarm.lock.task.{task.task_id}"
        owner_id = "Orchestrator-1"

        # 1. Acquire Distributed Lock
        acquired = await self.lock_manager.acquire(lock_key, owner_id)
        if not acquired:
            return False

        try:
            await self._publish_event(
                "swarm.spawn.started", {"task_id": str(task.task_id)}
            )

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

            await self._publish_event(
                "swarm.task.assigned",
                {"task_id": str(task.task_id), "agent_id": str(best_agent_id)},
            )
            await self._publish_event(
                "swarm.spawn.completed", {"task_id": str(task.task_id)}
            )

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
            await self.queue.update_task_status(task_id, "Cancelled")
            await self._publish_event(
                "swarm.task.failed", {"task_id": str(task_id), "status": "Cancelled"}
            )
            return True
        return False

    async def pause_task(self, task_id: UUID) -> bool:
        task = await self.queue.get_task(task_id)
        if task:
            await self.queue.update_task_status(task_id, "Waiting")
            return True
        return False

    async def resume_task(self, task_id: UUID) -> bool:
        task = await self.queue.get_task(task_id)
        if task:
            await self.queue.update_task_status(task_id, "Running")
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
        await self.manager.shutdown()

    async def _publish_event(self, topic: str, body: Dict[str, Any]) -> None:
        msg = InterAgentMessage(
            sender="SwarmOrchestrator",
            receiver="All",
            action=topic,
            body=body,
        )
        await self.event_bus.publish(topic, msg)
