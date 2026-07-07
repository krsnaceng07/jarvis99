"""JARVIS OS - Tool Orchestration DTOs.

Defines Pydantic models for retry policies, wave tasks, execution waves, and results.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RetryPolicy(BaseModel):
    """Configuration for tool task retries and backoff rules."""

    max_retries: int = Field(
        default=2, description="Maximum execution attempts allowed."
    )
    delay: float = Field(default=1.0, description="Initial retry delay in seconds.")
    backoff_multiplier: float = Field(
        default=2.0, description="Multiplier applied to delay on subsequent attempts."
    )
    retryable_errors: List[str] = Field(
        default_factory=list,
        description="Substrings of exceptions/errors that trigger retry.",
    )


class WaveTask(BaseModel):
    """Unit of work representing a single tool invocation within a wave."""

    task_id: UUID = Field(default_factory=uuid4, description="Unique task identifier.")
    idempotency_key: UUID = Field(
        default_factory=uuid4, description="Key preventing duplicate execution."
    )
    tool_name: str = Field(..., description="Target whitelisted skill identifier.")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Parameter arguments payload."
    )
    priority: int = Field(default=1, description="Scheduling priority weights.")
    timeout: float = Field(default=900.0, description="Execution limit in seconds.")
    approval_level: str = Field(
        default="L0", description="L0-L3 security permission levels."
    )
    retry_policy: Optional[RetryPolicy] = Field(
        default=None, description="Custom task retry policy."
    )
    dependencies: List[UUID] = Field(
        default_factory=list, description="List of task UUIDs that must complete first."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context parameters."
    )


class ExecutionWave(BaseModel):
    """Collection of parallel tasks executed as a concurrent step block."""

    wave_id: UUID = Field(default_factory=uuid4, description="Unique wave identifier.")
    tasks: List[WaveTask] = Field(..., description="Sequential wave tasks list.")
    parallel_limit: int = Field(
        default=3, description="Maximum concurrent tasks in this wave."
    )
    status: str = Field(default="PENDING", description="Current execution state.")
    started_at: Optional[datetime] = Field(
        default=None, description="Wave initiation timestamp."
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="Wave completion timestamp."
    )


class ToolExecutionResult(BaseModel):
    """DTO detailing the output, metrics, and metadata of a tool run."""

    task_id: UUID = Field(
        default_factory=uuid4, description="UUID referencing the task."
    )
    status: str = Field(
        default="PENDING",
        description="Execution outcome: SUCCESS, FAILURE, ERROR, CANCELLED.",
    )
    stdout: str = Field(default="", description="Captured standard output buffer.")
    stderr: str = Field(default="", description="Captured standard error buffer.")
    exit_code: int = Field(default=0, description="Status exit code.")
    duration: float = Field(default=0.0, description="Execution duration in seconds.")
    memory_usage: int = Field(default=0, description="Peak memory consumption in MB.")
    cpu_usage: float = Field(
        default=0.0, description="Average CPU core usage fraction."
    )
    truncated: bool = Field(
        default=False, description="Flag indicating if output limits were breached."
    )
    audit_id: UUID = Field(
        default_factory=uuid4, description="UUID reference to the audit log."
    )
    artifacts: Dict[str, Any] = Field(
        default_factory=dict, description="Output files or state artifacts produced."
    )
    error: Optional[str] = Field(
        default=None, description="Detailed exception or failure reason."
    )


class AggregatedWaveResult(BaseModel):
    """Consolidated execution results for all tasks in a wave."""

    wave_id: UUID = Field(..., description="Target wave identifier.")
    status: str = Field(
        ..., description="Final wave status: SUCCESS, FAILURE, PARTIAL_FAILURE."
    )
    tasks_completed: List[UUID] = Field(
        default_factory=list, description="List of completed task IDs."
    )
    tasks_failed: List[UUID] = Field(
        default_factory=list, description="List of failed task IDs."
    )
    combined_stdout: str = Field(default="", description="Merged standard outputs.")
    combined_stderr: str = Field(default="", description="Merged standard errors.")
    total_duration: float = Field(
        default=0.0, description="Sum duration of all tasks in seconds."
    )
    artifacts: Dict[str, Any] = Field(
        default_factory=dict, description="Merged output artifacts."
    )
