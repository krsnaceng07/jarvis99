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

import logging
from typing import Any, Dict

from core.runtime.neural.model_router import ModelRouter

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """Manages reasoning cycles and system thinking prompts using ModelRouter."""

    def __init__(self, model_router: ModelRouter) -> None:
        """Initialize ReasoningEngine."""
        self.model_router = model_router

    async def analyze(self, goal: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a goal and produce step-by-step reasoning details."""
        logger.info("ReasoningEngine analyzing goal: %s", goal)

        memory_section = ""
        mem_ctx = context.get("memory_context")
        if mem_ctx and isinstance(mem_ctx, list):
            snippets = [
                str(m.get("content", ""))[:200]
                for m in mem_ctx[:5]
                if m.get("content")
            ]
            if snippets:
                joined = "\n".join(f"- {s}" for s in snippets)
                memory_section = (
                    f"\n\nRelevant memories:\n{joined}\n"
                    f"Consider these when analyzing feasibility and approach."
                )

        prompt = (
            f"Analyze this goal and determine the best approach:\n"
            f"Goal: {goal}\n"
            f"Available context: {list(context.keys())}"
            f"{memory_section}\n\n"
            f"Provide:\n"
            f"1. Is this goal feasible? (confidence 0.0-1.0)\n"
            f"2. Key risks or blockers\n"
            f"3. Recommended approach in 2-3 sentences"
        )
        response = await self.model_router.route_query(
            prompt,
            system_instruction=(
                "You are an analytical reasoning engine. "
                "Be concise and actionable."
            ),
        )

        confidence = 0.95
        lower = response.lower() if response else ""
        if "not feasible" in lower or "impossible" in lower:
            confidence = 0.3
        elif "risky" in lower or "uncertain" in lower or "difficult" in lower:
            confidence = 0.7

        return {
            "reasoning_steps": [response],
            "confidence": confidence,
        }
