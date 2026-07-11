"""
PHASE: 37
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from core.runtime.neural.learning_engine import LearningEngine
from core.runtime.neural.model_router import ModelRouter
from core.runtime.neural.planning_engine import PlanningEngine
from core.runtime.neural.reasoning_engine import ReasoningEngine
from core.runtime.neural.reflection_engine import ReflectionEngine


class NeuralLayer:
    """Orchestrates neural operations, model routing, reasoning, planning, reflection, and learning engines."""

    def __init__(
        self,
        model_router: ModelRouter,
        reasoning_engine: ReasoningEngine,
        planning_engine: PlanningEngine,
        reflection_engine: ReflectionEngine,
        learning_engine: LearningEngine,
    ) -> None:
        self.model_router = model_router
        self.reasoning_engine = reasoning_engine
        self.planning_engine = planning_engine
        self.reflection_engine = reflection_engine
        self.learning_engine = learning_engine
