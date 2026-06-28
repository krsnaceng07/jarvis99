"""JARVIS OS - Workflow Automation DTOs.

Defines enums, plans, versions, metrics, and immutable compiled workflow structures.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List
from uuid import UUID

from pydantic import BaseModel, Field


class WorkflowState(str, Enum):
    """Global execution status states for workflows."""

    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class WorkflowStepState(str, Enum):
    """Lifecycle status states for individual workflow steps."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RecoveryPolicy(str, Enum):
    """Failure recovery actions to take when a workflow step crashes."""

    STOP = "STOP"
    CONTINUE = "CONTINUE"
    RETRY_STEP = "RETRY_STEP"
    RETRY_WORKFLOW = "RETRY_WORKFLOW"
    ROLLBACK = "ROLLBACK"
    COMPENSATE = "COMPENSATE"


class WorkflowVersion(BaseModel):
    """DTO representing historical workflow plan metadata and version tags."""

    workflow_id: UUID
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    checksum: str


class WorkflowStep(BaseModel):
    """Configuration structure defining a single step within a workflow macro."""

    name: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    timeout: float = 300.0
    recovery_policy: RecoveryPolicy = RecoveryPolicy.STOP


class WorkflowPlan(BaseModel):
    """Raw workflow configuration model detailing sequence steps and variables."""

    name: str
    workflow_id: UUID
    version: int = 1
    steps: List[WorkflowStep]


class CompiledWorkflow(BaseModel):
    """Immutable compiled execution graph DTO produced by compilation."""

    model_config = {"frozen": True}  # Immutable pydantic constraint

    workflow_id: UUID
    version: int
    waves: List[List[WorkflowStep]]
    estimated_cost: Decimal = Field(default_factory=lambda: Decimal("0.0"))


class WorkflowMetrics(BaseModel):
    """Detailed logs tracking automated workflow runs."""

    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    retry_count: int = 0
    approval_wait_time: float = 0.0
    token_cost: Decimal = Field(default_factory=lambda: Decimal("0.0"))
    execution_duration: float = 0.0
    success_rate: float = 0.0
