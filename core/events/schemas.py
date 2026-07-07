"""
PHASE: 40
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/102_PHASE_40_EVENT_BUS_REACTIVE_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/8e27d67d-09cc-4e93-9e3e-d5a4bb653dd9/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MissionCreatedPayload(BaseModel):
    """Payload for the 'mission.created' event."""

    mission_id: UUID = Field(..., description="Unique mission identifier.")
    goal: str = Field(..., description="The user goal context.")
    budget_limit: float = Field(..., description="Daily/monthly spending threshold in USD.")


class WorkflowStartedPayload(BaseModel):
    """Payload for the 'workflow.started' event."""

    graph_id: str = Field(..., description="The executed workflow instance identifier.")
    name: str = Field(..., description="Name of the workflow template.")


class WorkflowCompletedPayload(BaseModel):
    """Payload for the 'workflow.completed' and 'workflow.failed' events."""

    graph_id: str = Field(..., description="The workflow graph instance identifier.")
    success: bool = Field(..., description="True if all DAG nodes succeeded.")
    completed_nodes: List[str] = Field(
        default_factory=list, description="IDs of completed nodes."
    )
    outputs: Dict[str, Any] = Field(
        default_factory=dict, description="Outputs collected from nodes."
    )
    error: Optional[str] = Field(
        default=None, description="Diagnostic error message on failure."
    )


class ToolExecutedPayload(BaseModel):
    """Payload for the 'tool.executed' event."""

    node_id: str = Field(..., description="The workflow node ID that executed.")
    task_type: str = Field(..., description="Type of task (e.g. 'tool', 'python').")
    status: str = Field(..., description="The outcome status ('SUCCESS' or 'FAILURE').")
    exit_code: int = Field(..., description="Process exit code.")
    stdout: str = Field(..., description="Standard output buffer contents.")
    stderr: Optional[str] = Field(default=None, description="Standard error output.")
    error: Optional[str] = Field(default=None, description="Orchestration error.")


class ConsensusReachedPayload(BaseModel):
    """Payload for the 'consensus.reached' event."""

    mission_id: UUID = Field(..., description="The mission context ID requiring consensus.")
    approved: bool = Field(..., description="Whether peer voting approved the request.")
    votes: Dict[str, bool] = Field(..., description="Individual peer node votes.")
    reason: Optional[str] = Field(default=None, description="Resolution rationale.")


class LearningCompletedPayload(BaseModel):
    """Payload for the 'learning.completed' event."""

    task_id: str = Field(..., description="Target execution task that was analysed.")
    status: str = Field(..., description="Success or failure outcome of reflection.")
    confidence: float = Field(..., description="Updated model confidence estimation.")
    insights: str = Field(..., description="Lessons or procedural schema changes resolved.")
