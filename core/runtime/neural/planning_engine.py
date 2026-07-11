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

import json
import logging
from typing import Any, Dict, List

from core.runtime.neural.model_router import ModelRouter

logger = logging.getLogger(__name__)


class PlanningEngine:
    """Transforms raw goals into structured, executable checklists and plans."""

    def __init__(self, model_router: ModelRouter) -> None:
        """Initialize PlanningEngine."""
        self.model_router = model_router

    async def generate_plan(
        self, goal: str, context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Decompose a goal into an ordered sequence of discrete tasks.

        Returns a list of dicts with keys: step (int), description (str),
        estimated_cost (float), required_permissions (list[str]),
        executor (str: llm|python|shell|browser|api|file|memory).
        """
        logger.info("PlanningEngine decomposing goal: %s", goal)

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
                    f"\nRelevant past experiences:\n{joined}\n"
                    f"Use these to inform your plan — avoid past failures, "
                    f"leverage successful approaches.\n"
                )

        prompt = (
            "You are a task planner for an AI agent system. "
            "Decompose the following goal into 3-5 concrete, actionable execution steps.\n\n"
            "Each step must specify:\n"
            '- "step": integer starting at 0\n'
            '- "description": what to do (be specific and actionable)\n'
            '- "estimated_cost": estimated USD cost (float, e.g. 0.05)\n'
            '- "required_permissions": list of permission strings needed '
            '(e.g. ["file_read"], ["cli"], ["web_access"])\n'
            '- "executor": which tool to use: "llm", "python", "shell", '
            '"browser", "api", "file", or "memory"\n\n'
            "Return ONLY a valid JSON array. No explanation, no markdown.\n\n"
            f"Goal: {goal}{memory_section}"
        )
        response = await self.model_router.route_query(
            prompt,
            system_instruction=(
                "You are a precise task planning model. "
                "Output ONLY valid JSON. No markdown fences, no commentary."
            ),
        )

        steps = self._parse_plan(response, goal)
        if steps:
            return steps

        # Retry with explicit correction if first attempt failed
        retry_prompt = (
            "Your previous response was not valid JSON. "
            "Return ONLY a JSON array (no markdown, no explanation) for this goal:\n"
            f"{goal}\n\n"
            "Example format:\n"
            '[{"step": 0, "description": "Research the topic", '
            '"estimated_cost": 0.02, "required_permissions": ["web_access"], '
            '"executor": "llm"}]'
        )
        retry_response = await self.model_router.route_query(
            retry_prompt,
            system_instruction="Output ONLY valid JSON. Nothing else.",
        )
        steps = self._parse_plan(retry_response, goal)
        if steps:
            return steps

        logger.warning("PlanningEngine: LLM planning failed after retry, using default.")
        return self._default_plan(goal)

    def _parse_plan(self, response: str, goal: str) -> List[Dict[str, Any]]:
        """Attempt to parse LLM response into a valid plan."""
        try:
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            # Handle case where LLM wraps in an object
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "steps" in parsed:
                parsed = parsed["steps"]
            if isinstance(parsed, list) and len(parsed) > 0:
                return self._normalize_steps(parsed)
        except Exception:
            pass
        return []

    @staticmethod
    def _normalize_steps(raw_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure each step has all required fields with correct types."""
        normalized = []
        for i, step in enumerate(raw_steps):
            normalized.append({
                "step": step.get("step", step.get("step_index", i)),
                "description": step.get("description", step.get("task", f"Step {i}")),
                "estimated_cost": float(step.get("estimated_cost", 0.05)),
                "required_permissions": step.get("required_permissions", []),
                "executor": step.get("executor", "llm"),
            })
        return normalized

    @staticmethod
    def _default_plan(goal: str) -> List[Dict[str, Any]]:
        """Fallback plan when LLM planning fails entirely."""
        return [
            {
                "step": 0,
                "description": f"Research and analyze: {goal}",
                "estimated_cost": 0.05,
                "required_permissions": [],
                "executor": "llm",
            },
            {
                "step": 1,
                "description": f"Execute the core task: {goal}",
                "estimated_cost": 0.10,
                "required_permissions": [],
                "executor": "llm",
            },
            {
                "step": 2,
                "description": f"Verify and summarize results for: {goal}",
                "estimated_cost": 0.03,
                "required_permissions": [],
                "executor": "llm",
            },
        ]
