"""
PHASE: 41
STATUS: IMPLEMENTATION
SPECIFICATION:
    Goal #5 — Autonomous Multi-Agent Collaboration

Architecture:
    ParallelMissionPlanner converts sequential mission steps into
    wave-based parallel execution plans. Uses dependency analysis
    to determine which steps can run concurrently.
    Integrates with MissionManager — does NOT replace it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WaveStep(BaseModel):
    """A single step within a wave."""

    step_index: int
    description: str
    executor: str = "llm"
    estimated_cost: float = 0.05
    required_permissions: List[str] = Field(default_factory=list)
    depends_on: List[int] = Field(default_factory=list)


class ExecutionWave(BaseModel):
    """A group of steps that can execute in parallel."""

    wave_index: int
    steps: List[WaveStep] = Field(default_factory=list)
    depends_on_waves: List[int] = Field(default_factory=list)


class ParallelPlan(BaseModel):
    """Wave-based execution plan for parallel agent collaboration."""

    waves: List[ExecutionWave] = Field(default_factory=list)
    total_steps: int = 0
    estimated_total_cost: float = 0.0


_PHASE_ORDER = [
    {"phase": "research", "keywords": ["research", "gather", "find", "explore", "analyze", "study", "investigate", "search"]},
    {"phase": "design", "keywords": ["design", "plan", "architect", "structure", "specify", "define"]},
    {"phase": "implement", "keywords": ["implement", "code", "build", "create", "develop", "write", "backend", "frontend", "api"]},
    {"phase": "test", "keywords": ["test", "verify", "validate", "check", "qa", "debug"]},
    {"phase": "document", "keywords": ["document", "readme", "explain", "summarize", "report"]},
    {"phase": "review", "keywords": ["review", "audit", "inspect", "evaluate"]},
]


class ParallelMissionPlanner:
    """Converts sequential step lists into wave-based parallel plans.

    Strategy:
        1. Classify each step into a phase (research/design/implement/test/doc/review)
        2. Group steps by phase
        3. Steps in the same phase → same wave (parallel)
        4. Phases run in dependency order (research before implement, etc.)
        5. LLM enhancement for complex dependency analysis when available
    """

    def __init__(self, llm_runtime: Optional[Any] = None) -> None:
        self._llm_runtime = llm_runtime

    def plan_parallel(
        self, steps: List[Dict[str, Any]],
    ) -> ParallelPlan:
        """Convert sequential steps into a wave-based parallel plan."""
        if not steps:
            return ParallelPlan()

        classified = self._classify_steps(steps)
        waves = self._group_into_waves(classified)
        total_cost = sum(
            s.estimated_cost for w in waves for s in w.steps
        )

        return ParallelPlan(
            waves=waves,
            total_steps=len(steps),
            estimated_total_cost=total_cost,
        )

    async def plan_parallel_llm(
        self, steps: List[Dict[str, Any]], goal: str,
    ) -> ParallelPlan:
        """LLM-enhanced parallel planning for complex goals."""
        rule_plan = self.plan_parallel(steps)
        if self._llm_runtime is None or len(steps) <= 3:
            return rule_plan

        try:
            llm_plan = await self._llm_plan(steps, goal)
            if llm_plan is not None and len(llm_plan.waves) > 0:
                return llm_plan
        except Exception as e:
            logger.debug("LLM parallel planning failed: %s", e)

        return rule_plan

    def _classify_steps(
        self, steps: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Add phase classification to each step."""
        classified = []
        for i, step in enumerate(steps):
            desc = step.get("description", "").lower()
            phase = "implement"

            for phase_def in _PHASE_ORDER:
                if any(kw in desc for kw in phase_def["keywords"]):
                    phase = phase_def["phase"]
                    break

            classified.append({
                **step,
                "_phase": phase,
                "_original_index": step.get("step", i),
            })
        return classified

    def _group_into_waves(
        self, classified_steps: List[Dict[str, Any]],
    ) -> List[ExecutionWave]:
        """Group steps into waves based on phase dependencies."""
        phase_order = [p["phase"] for p in _PHASE_ORDER]

        phase_groups: Dict[str, List[Dict[str, Any]]] = {}
        for step in classified_steps:
            phase = step["_phase"]
            if phase not in phase_groups:
                phase_groups[phase] = []
            phase_groups[phase].append(step)

        waves: List[ExecutionWave] = []
        wave_idx = 0
        seen_phases: List[str] = []

        for phase in phase_order:
            if phase not in phase_groups:
                continue

            group = phase_groups[phase]
            depends_on_waves = list(range(wave_idx)) if wave_idx > 0 else []

            wave_steps = []
            for step in group:
                wave_steps.append(
                    WaveStep(
                        step_index=step["_original_index"],
                        description=step.get("description", ""),
                        executor=step.get("executor", "llm"),
                        estimated_cost=float(step.get("estimated_cost", 0.05)),
                        required_permissions=step.get("required_permissions", []),
                        depends_on=[],
                    ),
                )

            if wave_steps:
                if waves and self._can_merge_wave(seen_phases, phase):
                    waves[-1].steps.extend(wave_steps)
                else:
                    waves.append(
                        ExecutionWave(
                            wave_index=wave_idx,
                            steps=wave_steps,
                            depends_on_waves=depends_on_waves,
                        ),
                    )
                    wave_idx += 1

                seen_phases.append(phase)

        if not waves:
            waves.append(
                ExecutionWave(
                    wave_index=0,
                    steps=[
                        WaveStep(
                            step_index=i,
                            description=s.get("description", ""),
                            executor=s.get("executor", "llm"),
                        )
                        for i, s in enumerate(classified_steps)
                    ],
                ),
            )

        return waves

    @staticmethod
    def _can_merge_wave(seen: List[str], current: str) -> bool:
        """Check if current phase can merge into the previous wave."""
        mergeable = {
            ("research", "design"),
            ("design", "research"),
            ("test", "review"),
            ("review", "test"),
            ("document", "review"),
        }
        if not seen:
            return False
        return (seen[-1], current) in mergeable

    async def _llm_plan(
        self,
        steps: List[Dict[str, Any]],
        goal: str,
    ) -> Optional[ParallelPlan]:
        """Use LLM to create an optimized parallel plan."""
        if self._llm_runtime is None:
            return None

        import json

        from core.tools.llm_runtime import LlmRequest

        steps_text = "\n".join(
            f"  {i}: {s.get('description', '')}" for i, s in enumerate(steps)
        )

        request = LlmRequest(
            prompt=(
                "Group these mission steps into parallel execution waves.\n\n"
                f"Goal: {goal}\n"
                f"Steps:\n{steps_text}\n\n"
                "Rules:\n"
                "- Steps with no dependencies can run in the same wave (parallel)\n"
                "- Research before implementation, implementation before testing\n"
                "- Return a JSON array of waves, each with step indices\n\n"
                'Example: [{"wave": 0, "steps": [0, 1]}, {"wave": 1, "steps": [2, 3]}]\n'
                "Return ONLY valid JSON."
            ),
            system_prompt="You are a parallel execution planner. Output ONLY valid JSON.",
            category="planning",
            max_tokens=300,
            temperature=0.0,
        )

        response = await self._llm_runtime.generate(request)
        if not response.text or response.error:
            return None

        try:
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = json.loads(text)

            if not isinstance(parsed, list):
                return None

            waves = []
            for w_data in parsed:
                w_idx = w_data.get("wave", len(waves))
                step_indices = w_data.get("steps", [])
                wave_steps = []
                for si in step_indices:
                    if 0 <= si < len(steps):
                        s = steps[si]
                        wave_steps.append(
                            WaveStep(
                                step_index=si,
                                description=s.get("description", ""),
                                executor=s.get("executor", "llm"),
                                estimated_cost=float(s.get("estimated_cost", 0.05)),
                            ),
                        )
                if wave_steps:
                    waves.append(
                        ExecutionWave(
                            wave_index=w_idx,
                            steps=wave_steps,
                            depends_on_waves=list(range(w_idx)),
                        ),
                    )

            if waves:
                total_cost = sum(s.estimated_cost for w in waves for s in w.steps)
                return ParallelPlan(
                    waves=waves,
                    total_steps=len(steps),
                    estimated_total_cost=total_cost,
                )
        except Exception as e:
            logger.debug("LLM plan parsing failed: %s", e)

        return None

    def flatten_plan(self, plan: ParallelPlan) -> List[Dict[str, Any]]:
        """Convert a parallel plan back to a flat step list with wave metadata."""
        flat: List[Dict[str, Any]] = []
        for wave in plan.waves:
            for step in wave.steps:
                flat.append({
                    "step": step.step_index,
                    "description": step.description,
                    "executor": step.executor,
                    "estimated_cost": step.estimated_cost,
                    "required_permissions": step.required_permissions,
                    "wave_index": wave.wave_index,
                    "parallel": len(wave.steps) > 1,
                })
        return flat
