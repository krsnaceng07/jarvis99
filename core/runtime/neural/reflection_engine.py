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

import logging
from typing import Any, Dict

from core.runtime.neural.model_router import ModelRouter

logger = logging.getLogger(__name__)


class ReflectionEngine:
    """Analyzes execution logs, outcomes, and costs to calculate confidence score adjustments."""

    def __init__(self, model_router: ModelRouter) -> None:
        self.model_router = model_router

    async def reflect(self, execution_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Critique an execution result and determine correctness."""
        logger.info("ReflectionEngine analyzing execution metadata.")

        goal = execution_metadata.get("goal", "unknown")
        status = execution_metadata.get("status", "unknown")
        confidence = execution_metadata.get("confidence", 1.0)
        cost = execution_metadata.get("cost", 0.0)

        prompt = (
            f"Reflect on this AI agent execution:\n"
            f"Goal: {goal}\n"
            f"Status: {status}\n"
            f"Confidence: {confidence}\n"
            f"Cost: ${cost}\n\n"
            f"Provide a brief analysis (2-3 sentences):\n"
            f"1. What worked or failed?\n"
            f"2. What should change next time for similar goals?\n"
            f"3. Key lesson learned."
        )
        response = await self.model_router.route_query(
            prompt,
            system_instruction=(
                "You are a reflective AI analyst. "
                "Give concise, actionable insights. No fluff."
            ),
        )

        is_correct = status == "SUCCESS"

        return {
            "is_correct": is_correct,
            "reflection_critique": response,
            "confidence_adjustment": 0.05 if is_correct else -0.10,
        }
