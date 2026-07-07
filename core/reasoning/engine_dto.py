"""JARVIS OS - Reasoning Engine DTOs.

Defines status state machines, reflection decision types, plan structures, and performance metrics DTOs.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.tools.dto import ExecutionWave


class SessionState(str, Enum):
    """Execution lifecycle state indicators."""

    PLANNING = "Planning"
    EXECUTING = "Executing"
    REFLECTING = "Reflecting"
    REPAIRING = "Repairing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class ReflectionDecision(str, Enum):
    """Outcomes of the self-correction engine assessment loops."""

    SUCCESS = "SUCCESS"
    RETRY = "RETRY"
    REPLAN = "REPLAN"
    ABORT = "ABORT"


class FailureType(str, Enum):
    """Categorized root causes of task and system execution halts."""

    PlannerFailure = "PlannerFailure"
    ToolFailure = "ToolFailure"
    ModelFailure = "ModelFailure"
    ReflectionFailure = "ReflectionFailure"
    BudgetFailure = "BudgetFailure"
    ApprovalFailure = "ApprovalFailure"
    TimeoutFailure = "TimeoutFailure"


class RiskLevel(str, Enum):
    """Task-level risk categories."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ExecutionPlan(BaseModel):
    """DTO representing the structured execution plan containing sequential waves."""

    goal: str
    trace_id: UUID
    plan_version: int = 1
    waves: List[ExecutionWave]
    estimated_cost: Decimal = Field(default_factory=lambda: Decimal("0.0"))
    estimated_tokens: int = 0
    risk_level: RiskLevel = RiskLevel.LOW


class EngineMetrics(BaseModel):
    """Observability performance logs collected for execution analytics."""

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_duration: float = 0.0
    planning_time: float = 0.0
    execution_time: float = 0.0
    reflection_time: float = 0.0
    repair_time: float = 0.0
    total_tokens: int = 0
    total_cost: Decimal = Field(default_factory=lambda: Decimal("0.0"))
    wave_count: int = 0
    reflection_count: int = 0
    repair_count: int = 0
    success_rate: float = 0.0
