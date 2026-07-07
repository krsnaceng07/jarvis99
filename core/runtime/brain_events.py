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


class BrainEvents:
    """Standardized cognitive and system event names for event-driven orchestration."""

    GOAL_CREATED = "brain.goal.created"
    GOAL_COMPLETED = "brain.goal.completed"
    GOAL_FAILED = "brain.goal.failed"

    THICK_CYCLE_START = "brain.cycle.started"
    THICK_CYCLE_END = "brain.cycle.completed"

    ATTENTION_SHIFT = "brain.attention.shifted"
    RISK_THRESHOLD_EXCEEDED = "brain.risk.exceeded"
