"""
PHASE: 41
STATUS: IMPLEMENTATION
SPECIFICATION:
    Goal #5 — Autonomous Multi-Agent Collaboration

Architecture:
    AgentSupervisor monitors agent health, detects failures,
    reassigns tasks from failed/stalled agents, and coordinates
    wave completion. Uses existing AgentRegistry for status tracking
    and SubagentManager for lifecycle operations.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SupervisorEvent(BaseModel):
    """Record of a supervisor intervention."""

    event_type: str  # timeout, heartbeat_fail, reassign, restart, wave_complete
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    description: str = ""
    timestamp: float = Field(default_factory=time.time)


class WaveStatus(BaseModel):
    """Status of a parallel execution wave."""

    wave_index: int
    total_tasks: int = 0
    completed: int = 0
    failed: int = 0
    in_progress: int = 0
    is_complete: bool = False


class AgentSupervisor:
    """Monitors and coordinates parallel agent execution.

    Responsibilities:
        1. Health monitoring — detect stalled/failed agents
        2. Task reassignment — move work from failed agents
        3. Wave coordination — track wave completion
        4. Automatic restart — respawn failed agents
        5. Escalation — abort wave if too many failures

    Uses existing components:
        AgentRegistry → agent status tracking
        SubagentManager → agent lifecycle (spawn/terminate)
        SwarmMessageBus → event notifications
    """

    MAX_FAILURES_PER_WAVE = 2
    AGENT_TIMEOUT_SECONDS = 300.0
    HEALTH_CHECK_INTERVAL = 10.0

    def __init__(
        self,
        registry: Optional[Any] = None,
        subagent_manager: Optional[Any] = None,
        message_bus: Optional[Any] = None,
        queue: Optional[Any] = None,
    ) -> None:
        self._registry = registry
        self._manager = subagent_manager
        self._message_bus = message_bus
        self._queue = queue
        self._events: List[SupervisorEvent] = []
        self._wave_tracking: Dict[int, WaveStatus] = {}
        self._agent_task_map: Dict[UUID, Dict[str, Any]] = {}
        self._agent_start_times: Dict[UUID, float] = {}
        self._monitor_task: Optional[asyncio.Task[None]] = None
        self._active = False

    async def start_monitoring(self) -> None:
        """Start the background health monitor loop."""
        self._active = True
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            logger.info("AgentSupervisor monitoring started.")

    async def stop_monitoring(self) -> None:
        """Stop the background health monitor."""
        self._active = False
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
            logger.info("AgentSupervisor monitoring stopped.")

    def register_agent_task(
        self,
        agent_id: UUID,
        task_info: Dict[str, Any],
        wave_index: int = 0,
    ) -> None:
        """Register that an agent is working on a task in a wave."""
        self._agent_task_map[agent_id] = {
            **task_info,
            "wave_index": wave_index,
        }
        self._agent_start_times[agent_id] = time.time()

        if wave_index not in self._wave_tracking:
            self._wave_tracking[wave_index] = WaveStatus(wave_index=wave_index)
        self._wave_tracking[wave_index].total_tasks += 1
        self._wave_tracking[wave_index].in_progress += 1

    def report_task_complete(
        self,
        agent_id: UUID,
        success: bool = True,
    ) -> None:
        """Report that an agent has completed its task."""
        task_info = self._agent_task_map.pop(agent_id, None)
        self._agent_start_times.pop(agent_id, None)

        if task_info is None:
            return

        wave_idx = task_info.get("wave_index", 0)
        wave = self._wave_tracking.get(wave_idx)
        if wave is None:
            return

        wave.in_progress = max(0, wave.in_progress - 1)
        if success:
            wave.completed += 1
        else:
            wave.failed += 1

        wave.is_complete = (wave.completed + wave.failed) >= wave.total_tasks

        if wave.is_complete:
            self._events.append(
                SupervisorEvent(
                    event_type="wave_complete",
                    description=(
                        f"Wave {wave_idx} complete: "
                        f"{wave.completed} succeeded, {wave.failed} failed"
                    ),
                ),
            )

    def get_wave_status(self, wave_index: int) -> Optional[WaveStatus]:
        """Get the current status of a wave."""
        return self._wave_tracking.get(wave_index)

    def is_wave_complete(self, wave_index: int) -> bool:
        """Check if all tasks in a wave have finished."""
        wave = self._wave_tracking.get(wave_index)
        if wave is None:
            return True
        return wave.is_complete

    def should_abort_wave(self, wave_index: int) -> bool:
        """Check if too many failures have occurred in a wave."""
        wave = self._wave_tracking.get(wave_index)
        if wave is None:
            return False
        return wave.failed >= self.MAX_FAILURES_PER_WAVE

    def get_stalled_agents(self) -> List[UUID]:
        """Find agents that have exceeded the timeout threshold."""
        now = time.time()
        stalled: List[UUID] = []
        for agent_id, start_time in self._agent_start_times.items():
            if (now - start_time) > self.AGENT_TIMEOUT_SECONDS:
                stalled.append(agent_id)
        return stalled

    async def handle_stalled_agents(self) -> List[SupervisorEvent]:
        """Detect and handle stalled agents."""
        stalled = self.get_stalled_agents()
        events: List[SupervisorEvent] = []

        for agent_id in stalled:
            task_info = self._agent_task_map.get(agent_id, {})

            event = SupervisorEvent(
                event_type="timeout",
                agent_id=str(agent_id),
                task_id=str(task_info.get("task_id", "")),
                description=f"Agent {agent_id} timed out after "
                            f"{self.AGENT_TIMEOUT_SECONDS}s",
            )
            events.append(event)
            self._events.append(event)

            self.report_task_complete(agent_id, success=False)

            if self._manager is not None:
                try:
                    await self._manager.terminate_subagent(
                        agent_id, "Supervisor timeout",
                    )
                except Exception as e:
                    logger.debug("Failed to terminate stalled agent %s: %s", agent_id, e)

            await self._attempt_reassign(task_info)

        return events

    async def handle_agent_failure(
        self,
        agent_id: UUID,
        error: str = "",
    ) -> Optional[SupervisorEvent]:
        """Handle a reported agent failure with potential reassignment."""
        task_info = self._agent_task_map.get(agent_id, {})

        event = SupervisorEvent(
            event_type="agent_failure",
            agent_id=str(agent_id),
            task_id=str(task_info.get("task_id", "")),
            description=f"Agent {agent_id} failed: {error[:200]}",
        )
        self._events.append(event)

        self.report_task_complete(agent_id, success=False)

        wave_idx = task_info.get("wave_index", 0)
        if not self.should_abort_wave(wave_idx):
            await self._attempt_reassign(task_info)

        return event

    async def _attempt_reassign(
        self,
        task_info: Dict[str, Any],
    ) -> bool:
        """Try to reassign a failed task to another available agent."""
        if not task_info or self._queue is None:
            return False

        try:
            from core.runtime.dto import SwarmTask

            reassign_task = SwarmTask(
                task_id=uuid4(),
                goal=task_info.get("goal", task_info.get("description", "")),
                priority="HIGH",
                capabilities=task_info.get("capabilities", []),
                metadata={
                    "reassigned": True,
                    "original_task_id": str(task_info.get("task_id", "")),
                    "wave_index": task_info.get("wave_index", 0),
                },
            )
            await self._queue.enqueue(reassign_task)

            event = SupervisorEvent(
                event_type="reassign",
                task_id=str(task_info.get("task_id", "")),
                description=f"Task reassigned with HIGH priority",
            )
            self._events.append(event)
            return True

        except Exception as e:
            logger.debug("Task reassignment failed: %s", e)
            return False

    async def _monitor_loop(self) -> None:
        """Background loop checking agent health periodically."""
        try:
            while self._active:
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)
                await self.handle_stalled_agents()
                self._check_registry_health()
        except asyncio.CancelledError:
            pass

    def _check_registry_health(self) -> None:
        """Cross-check agent registry for unhealthy agents."""
        if self._registry is None:
            return

        try:
            agents = self._registry.list_agents()
            for agent in agents:
                agent_id = agent.get("id")
                status = agent.get("status", "")
                failures = agent.get("recent_failures", 0)

                if failures >= 3 and agent_id in self._agent_task_map:
                    self._events.append(
                        SupervisorEvent(
                            event_type="high_failure_rate",
                            agent_id=str(agent_id),
                            description=f"Agent has {failures} recent failures",
                        ),
                    )
        except Exception as e:
            logger.debug("Registry health check failed: %s", e)

    def get_events(self) -> List[SupervisorEvent]:
        """Return all supervisor events for inspection."""
        return list(self._events)

    def get_all_wave_statuses(self) -> List[WaveStatus]:
        """Return status of all tracked waves."""
        return [
            self._wave_tracking[k]
            for k in sorted(self._wave_tracking.keys())
        ]
