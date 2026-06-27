"""JARVIS OS - Subagent Manager.

Manages subagent lifecycle states, concurrency boundaries, heartbeats, and watchdog timeouts.
"""

import asyncio
import time
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from core.exceptions import JarvisAgentError
from core.runtime.dto import CancellationToken
from core.runtime.state import AgentStateTransitionManager, SubagentState


class SubagentInstance:
    """Represents an active sandboxed subagent process state tracker."""

    def __init__(self, id: UUID, task_id: UUID, token: CancellationToken) -> None:
        self.id = id
        self.task_id = task_id
        self.token = token
        self.state = SubagentState.CREATE
        self.created_at = time.time()
        self.last_heartbeat = time.time()


class SubagentManager:
    """Orchestrates dynamic subagent spawning, concurrency restrictions, and timeout checks."""

    def __init__(
        self,
        max_concurrent: int = 5,
        max_lifespan: float = 900.0,
        heartbeat_timeout: float = 180.0,
        heartbeat_interval: float = 30.0,
        check_interval: float = 1.0,
        driver: Optional[Any] = None,
    ) -> None:
        """Initialize SubagentManager.

        Args:
            max_concurrent: Maximum active subagent instances allowed.
            max_lifespan: Maximum lifespan allowed in seconds per subagent (default 15 minutes).
            heartbeat_timeout: Heartbeat timeout in seconds before termination.
            heartbeat_interval: Heartbeat report frequency interval in seconds.
            check_interval: Watchdog loop sleep interval in seconds.
            driver: Optional IContainerDriver reference.
        """
        self.max_concurrent = max_concurrent
        self.max_lifespan = max_lifespan
        self.heartbeat_timeout = heartbeat_timeout
        self.heartbeat_interval = heartbeat_interval
        self.check_interval = check_interval
        self.driver = driver
        self.active_subagents: Dict[UUID, SubagentInstance] = {}
        self._lock = asyncio.Lock()
        self._watchdog_task: Optional[asyncio.Task[None]] = None

    async def initialize(self) -> None:
        """Start the background watchdog checker coroutine."""
        if self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def shutdown(self) -> None:
        """Kill all active subagents and stop the watchdog task."""
        if self._watchdog_task:
            task = self._watchdog_task
            task.cancel()
            self._watchdog_task = None
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Clean up remaining subagents
        subagent_ids = list(self.active_subagents.keys())
        for sid in subagent_ids:
            await self.terminate_subagent(sid, "System shutdown request")

    async def spawn_subagent(self, task_id: UUID) -> UUID:
        """Spawn a new subagent container state tracker if limits allow.

        Args:
            task_id: Target ScheduledTask ID context.

        Returns:
            The unique UUID of the spawned subagent.

        Raises:
            JarvisAgentError: If maximum concurrent limit is exceeded.
        """
        async with self._lock:
            # 1. Concurrency limit check
            if len(self.active_subagents) >= self.max_concurrent:
                raise JarvisAgentError(
                    code="AGENT_002",
                    message=(
                        f"Spawning limit exceeded. Maximum concurrent active subagents "
                        f"is {self.max_concurrent}."
                    ),
                )

            subagent_id = uuid4()
            token = CancellationToken()
            instance = SubagentInstance(id=subagent_id, task_id=task_id, token=token)

            # 2. Lifecycle transitions
            AgentStateTransitionManager.validate_subagent_transition(
                instance.state, SubagentState.INITIALIZE
            )
            instance.state = SubagentState.INITIALIZE

            if self.driver:
                try:
                    await self.driver.spawn_container(subagent_id, task_id)
                except Exception as err:
                    raise JarvisAgentError(
                        code="AGENT_004",
                        message=f"Container driver failed to spawn environment: {str(err)}",
                    )

            AgentStateTransitionManager.validate_subagent_transition(
                instance.state, SubagentState.READY
            )
            instance.state = SubagentState.READY

            self.active_subagents[subagent_id] = instance
            return subagent_id

    async def update_state(
        self, subagent_id: UUID, target_state: SubagentState
    ) -> None:
        """Execute validated state transitions for a subagent.

        Args:
            subagent_id: Target subagent instance.
            target_state: New subagent lifecycle state.
        """
        async with self._lock:
            instance = self.active_subagents.get(subagent_id)
            if not instance:
                raise JarvisAgentError(
                    code="AGENT_999",
                    message=f"Subagent {subagent_id} not found.",
                )

            AgentStateTransitionManager.validate_subagent_transition(
                instance.state, target_state
            )
            instance.state = target_state

            if target_state == SubagentState.DESTROYED:
                instance.token.cancel()
                self.active_subagents.pop(subagent_id, None)

    async def register_heartbeat(self, subagent_id: UUID) -> None:
        """Update last heartbeat timestamp for the subagent.

        Args:
            subagent_id: Unique subagent identifier.
        """
        instance = self.active_subagents.get(subagent_id)
        if instance:
            instance.last_heartbeat = time.time()

    async def terminate_subagent(self, subagent_id: UUID, reason: str) -> None:
        """Force cancel and destroy a subagent.

        Args:
            subagent_id: Unique subagent identifier.
            reason: Termination reason log description.
        """
        async with self._lock:
            instance = self.active_subagents.get(subagent_id)
            if instance:
                instance.token.cancel()
                if self.driver:
                    try:
                        await self.driver.terminate_container(subagent_id)
                    except Exception:
                        pass
                instance.state = SubagentState.DESTROYED
                self.active_subagents.pop(subagent_id, None)

    async def _watchdog_loop(self) -> None:
        """Background coroutine checking timeouts periodically."""
        try:
            while True:
                await asyncio.sleep(self.check_interval)
                await self._check_timeouts()
        except asyncio.CancelledError:
            self._watchdog_task = None

    async def _check_timeouts(self) -> None:
        """Check all subagents against runtime lifespan and heartbeat thresholds."""
        now = time.time()
        to_terminate = []

        async with self._lock:
            for sid, instance in self.active_subagents.items():
                # Check lifespan timeout (e.g. 15 minutes limit)
                duration = now - instance.created_at
                if duration > self.max_lifespan:
                    to_terminate.append(
                        (
                            sid,
                            f"Lifespan timeout reached ({duration:.1f}s > {self.max_lifespan}s)",
                        )
                    )
                    continue

                # Check heartbeat timeout
                idle_time = now - instance.last_heartbeat
                if idle_time > self.heartbeat_timeout:
                    to_terminate.append(
                        (
                            sid,
                            f"Heartbeat lost ({idle_time:.1f}s > {self.heartbeat_timeout}s)",
                        )
                    )

        for sid, reason in to_terminate:
            await self.terminate_subagent(sid, reason)
