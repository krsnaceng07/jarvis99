"""JARVIS OS - Swarm Session Recovery Manager.

Scans for stale running tasks, restores pending items to queues, and recovers subagent registry statuses on startup.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces import EventBusInterface, InterAgentMessage, LifecycleInterface
from core.memory.database import db_manager
from core.runtime.dto import SwarmTask
from core.runtime.orchestrator import SwarmOrchestrator
from core.runtime.persistence_models import SwarmAgentModel, SwarmTaskModel

logger = logging.getLogger("jarvis.core.runtime.recovery_manager")


class SwarmResumeManager(LifecycleInterface):
    """Monitors and recovers stale active swarm execution runs during boot phase."""

    def __init__(
        self,
        orchestrator: SwarmOrchestrator,
        event_bus: EventBusInterface,
        recovery_timeout_seconds: float = 300.0,
    ) -> None:
        """Initialize SwarmResumeManager.

        Args:
            orchestrator: Active SwarmOrchestrator.
            event_bus: System event bus.
            recovery_timeout_seconds: Timeout threshold for running tasks.
        """
        self.orchestrator = orchestrator
        self.event_bus = event_bus
        self.recovery_timeout = recovery_timeout_seconds

    async def initialize(self) -> None:
        """Startup setup."""
        pass

    async def start(self) -> None:
        """Scan and recover stale sessions on startup."""
        try:
            await self.recover_all()
        except Exception as err:
            logger.error(
                "SwarmResumeManager failed to recover sessions on boot (database may be offline or uninitialized): %s",
                err,
            )

    async def stop(self) -> None:
        """Stop recovery hooks."""
        pass

    async def shutdown(self) -> None:
        """Teardown recovery hooks."""
        pass

    async def recover_all(self) -> None:
        """Execute the full recovery protocol for tasks, agents, and queue re-seeding."""
        logger.info("SwarmResumeManager starting execution session recovery...")
        now = datetime.now(timezone.utc)

        async with db_manager.session() as session:
            if not session.in_transaction():
                async with session.begin():
                    await self._recover_session_data(session, now)
            else:
                await self._recover_session_data(session, now)

        logger.info("SwarmResumeManager execution recovery completed successfully.")

    async def _recover_session_data(self, session: AsyncSession, now: datetime) -> None:
        """Runs the recovery business logic within an active session transaction."""
        # 1. Recover stale active tasks
        task_query = select(SwarmTaskModel).where(
            SwarmTaskModel.status.in_(["Running", "Claimed", "Pending"])
        )
        res = await session.execute(task_query)
        stale_tasks = res.scalars().all()

        pending_to_enqueue = []

        for task_model in stale_tasks:
            task = SwarmTask(
                task_id=task_model.task_id,
                goal=task_model.goal,
                priority=task_model.priority,
                capabilities=task_model.capabilities or [],
                timeout=task_model.timeout,
                retry=task_model.retry,
                dependencies=[UUID(d) for d in task_model.dependencies]
                if task_model.dependencies
                else [],
                metadata=task_model.metadata_ or {},
                status=task_model.status,
            )
            # Keep track of version for optimistic locking
            task.metadata["_version"] = task_model.version

            if task_model.status in ["Running", "Claimed"]:
                # Recovery timeout constraint: check if running long enough
                elapsed = (now - task_model.updated_at).total_seconds()
                if elapsed > self.recovery_timeout:
                    logger.info(
                        "Stale task %s detected (running for %.1fs > %.1fs)",
                        task.task_id,
                        elapsed,
                        self.recovery_timeout,
                    )
                    if task.retry > 0:
                        task.retry -= 1
                        task.status = "Pending"
                        task_model.status = "Pending"
                        task_model.retry = task.retry
                        task_model.version += 1
                        pending_to_enqueue.append(task)
                        await self._publish_event("TASK_RECOVERED", task)
                    else:
                        task.status = "Failed"
                        task_model.status = "Failed"
                        task_model.metadata_ = {
                            **(task_model.metadata_ or {}),
                            "error": "System interrupted and execution timed out.",
                        }
                        task_model.version += 1
                        await self._publish_event("TASK_FAILED", task)
                else:
                    # Not stale yet, let it be (re-enqueue or leave)
                    logger.debug(
                        "Task %s is active and running under timeout.", task.task_id
                    )
            elif task_model.status == "Pending":
                pending_to_enqueue.append(task)

        # 2. Reset stale subagents
        agent_query = select(SwarmAgentModel).where(
            SwarmAgentModel.status.in_(["WORKING", "WAITING", "ONLINE"])
        )
        agent_res = await session.execute(agent_query)
        stale_agents = agent_res.scalars().all()

        for agent_model in stale_agents:
            # Validate container/process driver status if possible
            is_active = False
            driver = self.orchestrator.manager.driver
            if driver:
                try:
                    metrics = await driver.get_container_metrics(agent_model.agent_id)
                    # If uptime is positive, container is still active
                    if metrics.get("uptime", 0.0) > 0.0:
                        is_active = True
                except Exception:
                    pass

            if not is_active:
                logger.info(
                    "Resetting stale subagent registry %s to ONLINE",
                    agent_model.agent_id,
                )
                agent_model.status = "ONLINE"
                agent_model.cpu_load = 0.0
                agent_model.memory = 0.0
                agent_model.version += 1
                self.orchestrator.registry.update_status(agent_model.agent_id, "ONLINE")

        # 3. Populate task queue with sorted pending tasks
        # Sort tasks: higher priority score runs first
        priority_map = {
            "CRITICAL": 5,
            "HIGH": 4,
            "NORMAL": 3,
            "LOW": 2,
            "SYSTEM": 1,
        }
        pending_to_enqueue.sort(
            key=lambda t: priority_map.get(t.priority, 3),
            reverse=True,
        )

        for task in pending_to_enqueue:
            await self.orchestrator.queue.enqueue(task)

    async def _publish_event(self, action: str, task: SwarmTask) -> None:
        msg = InterAgentMessage(
            sender="SwarmResumeManager",
            receiver="All",
            action=action,
            body=task.model_dump(mode="json"),
            correlation_id=task.task_id,
        )
        await self.event_bus.publish(action, msg)
