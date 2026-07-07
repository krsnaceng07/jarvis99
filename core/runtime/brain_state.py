"""
PHASE: 37
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/PHASE_37_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CognitiveState(BaseModel):
    """Represents operational cognitive metrics of the brain kernel."""

    current_goal: Optional[str] = None
    current_mission_id: Optional[UUID] = None
    current_task_id: Optional[str] = None
    attention_queue: List[str] = Field(default_factory=list)
    energy: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    risk_level: float = Field(default=0.0, ge=0.0, le=1.0)
    available_budget: float = Field(default=0.0, ge=0.0)
    estimated_cost: float = Field(default=0.0, ge=0.0)
    context_metadata: Dict[str, Any] = Field(default_factory=dict)
