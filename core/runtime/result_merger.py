"""
PHASE: 41
STATUS: IMPLEMENTATION
SPECIFICATION:
    Goal #5 — Autonomous Multi-Agent Collaboration

Architecture:
    ResultMerger aggregates outputs from parallel agents executing
    in the same wave into a single coherent result.
    Uses LLM for intelligent merging when available, falls back
    to structured concatenation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentOutput(BaseModel):
    """Output from a single agent within a wave."""

    agent_id: str
    role: str = "general"
    task_description: str = ""
    stdout: str = ""
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    status: str = "SUCCESS"
    error: Optional[str] = None


class MergedResult(BaseModel):
    """Aggregated output from all agents in a wave."""

    wave_index: int = 0
    merged_output: str = ""
    individual_outputs: List[AgentOutput] = Field(default_factory=list)
    conflicts_detected: int = 0
    merge_strategy: str = "concatenation"
    success: bool = True
    error: Optional[str] = None


class ResultMerger:
    """Aggregates parallel agent outputs into coherent merged results.

    Strategies:
        1. Concatenation — simple append (default)
        2. Deduplication — remove overlapping content
        3. LLM synthesis — intelligent merging for complex outputs
    """

    def __init__(self, llm_runtime: Optional[Any] = None) -> None:
        self._llm_runtime = llm_runtime

    def merge_wave_results(
        self,
        outputs: List[AgentOutput],
        wave_index: int = 0,
    ) -> MergedResult:
        """Merge outputs from all agents in a single wave."""
        if not outputs:
            return MergedResult(wave_index=wave_index, merged_output="")

        successful = [o for o in outputs if o.status == "SUCCESS"]
        failed = [o for o in outputs if o.status != "SUCCESS"]

        if not successful:
            return MergedResult(
                wave_index=wave_index,
                individual_outputs=outputs,
                success=False,
                error=f"All {len(outputs)} agents failed.",
                merge_strategy="none",
            )

        merged_text = self._concatenate(successful)
        merged_artifacts = self._merge_artifacts(successful)

        return MergedResult(
            wave_index=wave_index,
            merged_output=merged_text,
            individual_outputs=outputs,
            conflicts_detected=0,
            merge_strategy="concatenation",
            success=len(failed) == 0,
            error=f"{len(failed)} agent(s) failed" if failed else None,
        )

    async def merge_wave_results_llm(
        self,
        outputs: List[AgentOutput],
        wave_index: int = 0,
        goal: str = "",
    ) -> MergedResult:
        """LLM-enhanced merging for complex multi-agent outputs."""
        basic = self.merge_wave_results(outputs, wave_index)

        if not basic.success or self._llm_runtime is None:
            return basic

        successful = [o for o in outputs if o.status == "SUCCESS"]
        if len(successful) <= 1:
            return basic

        try:
            synthesized = await self._llm_synthesize(successful, goal)
            if synthesized:
                return MergedResult(
                    wave_index=wave_index,
                    merged_output=synthesized,
                    individual_outputs=outputs,
                    conflicts_detected=0,
                    merge_strategy="llm_synthesis",
                    success=True,
                )
        except Exception as e:
            logger.debug("LLM merge failed, using concatenation: %s", e)

        return basic

    def merge_mission_results(
        self,
        wave_results: List[MergedResult],
    ) -> MergedResult:
        """Merge results across all waves into a final mission output."""
        if not wave_results:
            return MergedResult(merged_output="")

        all_outputs: List[AgentOutput] = []
        sections: List[str] = []
        total_conflicts = 0
        all_success = True

        for wr in wave_results:
            all_outputs.extend(wr.individual_outputs)
            total_conflicts += wr.conflicts_detected
            if wr.merged_output:
                sections.append(wr.merged_output)
            if not wr.success:
                all_success = False

        return MergedResult(
            wave_index=-1,
            merged_output="\n\n---\n\n".join(sections),
            individual_outputs=all_outputs,
            conflicts_detected=total_conflicts,
            merge_strategy="wave_sequential",
            success=all_success,
        )

    @staticmethod
    def _concatenate(outputs: List[AgentOutput]) -> str:
        """Simple structured concatenation of agent outputs."""
        sections: List[str] = []
        for output in outputs:
            header = f"[{output.role.upper()}]"
            if output.task_description:
                header += f" {output.task_description}"
            content = output.stdout.strip() if output.stdout else "(no output)"
            sections.append(f"{header}\n{content}")
        return "\n\n".join(sections)

    @staticmethod
    def _merge_artifacts(outputs: List[AgentOutput]) -> Dict[str, Any]:
        """Merge artifact dicts from multiple agents."""
        merged: Dict[str, Any] = {}
        for output in outputs:
            for key, value in output.artifacts.items():
                if key in merged and isinstance(merged[key], list) and isinstance(value, list):
                    merged[key].extend(value)
                else:
                    merged[key] = value
        return merged

    async def _llm_synthesize(
        self,
        outputs: List[AgentOutput],
        goal: str,
    ) -> Optional[str]:
        """Use LLM to synthesize multiple agent outputs into one coherent result."""
        if self._llm_runtime is None:
            return None

        from core.tools.llm_runtime import LlmRequest

        output_sections = []
        for o in outputs:
            section = f"[{o.role.upper()}]: {o.stdout[:500]}" if o.stdout else ""
            if section:
                output_sections.append(section)

        if not output_sections:
            return None

        request = LlmRequest(
            prompt=(
                "Synthesize these parallel agent outputs into one coherent result.\n\n"
                f"Mission goal: {goal}\n\n"
                "Agent outputs:\n"
                + "\n\n".join(output_sections)
                + "\n\nCreate a single unified summary preserving all key information. "
                "Resolve any redundancies. Be concise."
            ),
            system_prompt="You are a result synthesis engine. Be concise and accurate.",
            category="reasoning",
            max_tokens=500,
            temperature=0.0,
        )
        response = await self._llm_runtime.generate(request)
        if response.text and not response.error:
            return response.text.strip()

        return None
