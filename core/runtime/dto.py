"""JARVIS OS - Agent Runtime DTOs and Resilience primitives.

Provides execution budget settings, checkpoint serialization schemas, and async cancellation tokens.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ExecutionBudget(BaseModel):
    """Pydantic model representing cost, resource, and duration constraints for an agent execution loop."""

    max_tokens: int = Field(
        default=2000,
        description="Maximum tokens allowed in session prompts/retrievals.",
    )
    max_cost: float = Field(
        default=0.5, description="Maximum financial cost limit in USD."
    )
    max_duration: float = Field(
        default=900.0,
        description="Maximum total run duration limit in seconds (default 15 minutes).",
    )
    max_memory_mb: Optional[int] = Field(
        default=512, description="Maximum RAM usage boundary in megabytes."
    )


class CheckpointDTO(BaseModel):
    """Pydantic schema representing task execution checkpoints for recovery/resumption."""

    task_id: UUID
    step_index: int
    state_data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CancellationToken:
    """Async-safe cancellation and pause/resume manager for coroutine loops."""

    def __init__(self) -> None:
        self._cancelled: bool = False
        self._paused: bool = False
        self._pause_event: asyncio.Event = asyncio.Event()
        self._pause_event.set()  # Default to not paused (ready to run)

    def cancel(self) -> None:
        """Trigger cancellation flag."""
        self._cancelled = True
        # Wake up any waiting coroutines so they can immediately raise cancellation exceptions
        self._pause_event.set()

    def pause(self) -> None:
        """Set pause flag, clearing the resume event."""
        self._paused = True
        self._pause_event.clear()

    def resume(self) -> None:
        """Clear pause flag and signal waiting coroutines to resume."""
        self._paused = False
        self._pause_event.set()

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancelled

    @property
    def is_paused(self) -> bool:
        """Check if pause has been requested."""
        return self._paused

    async def check_paused(self) -> None:
        """Await resume if execution has been paused."""
        if self._paused and not self._cancelled:
            await self._pause_event.wait()


class SwarmTask(BaseModel):
    """Pydantic model representing a task assigned to the swarm."""

    task_id: UUID
    goal: str
    priority: str = "NORMAL"  # "CRITICAL", "HIGH", "NORMAL", "LOW", "SYSTEM"
    capabilities: list[str] = Field(default_factory=list)
    timeout: float = 900.0
    retry: int = 0
    dependencies: list[UUID] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: str = "Pending"  # Pending, Running, Waiting, Completed, Failed, Cancelled


class SwarmTelemetry(BaseModel):
    """Resource metrics and active status parameters for a single agent."""

    agent_id: UUID
    cpu_usage: float
    memory_usage: float
    uptime_seconds: float
    current_task: Optional[str] = None
    heartbeat_ok: bool = True
    status: str


class SwarmSnapshot(BaseModel):
    """Global swarm state snapshot for monitoring dashboard and audits."""

    running_agents: int
    queued_tasks: int
    completed_tasks: int
    failed_tasks: int
    message_rate: float
    cpu_usage: float
    memory_usage: float
    cluster_status: str = "HEALTHY"  # HEALTHY | DEGRADED | CRITICAL
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
