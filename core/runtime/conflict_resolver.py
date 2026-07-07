"""
PHASE: 41
STATUS: IMPLEMENTATION
SPECIFICATION:
    Goal #5 — Autonomous Multi-Agent Collaboration

Architecture:
    ConflictResolver detects and resolves contradictory outputs from
    parallel agents. Uses LLM arbitration for complex conflicts,
    rule-based heuristics for common patterns.
    Example: Agent A says "Use PostgreSQL", Agent B says "Use MongoDB"
    → detect conflict → LLM arbitration → single decision.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Conflict(BaseModel):
    """A detected contradiction between two agent outputs."""

    agent_a: str
    agent_b: str
    description: str
    output_a: str = ""
    output_b: str = ""
    severity: str = "medium"  # low, medium, high


class Resolution(BaseModel):
    """The resolved outcome of a conflict."""

    conflict: Conflict
    chosen_output: str
    reasoning: str
    strategy: str = "llm_arbitration"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


_CONFLICT_INDICATORS: List[str] = [
    "instead of", "rather than", "not", "shouldn't",
    "don't use", "avoid", "wrong", "incorrect",
    "better to", "prefer", "recommend against",
]

_TECHNOLOGY_PAIRS: List[Tuple[str, str]] = [
    ("postgresql", "mongodb"),
    ("mysql", "postgresql"),
    ("react", "vue"),
    ("angular", "react"),
    ("rest", "graphql"),
    ("docker", "kubernetes"),
    ("python", "javascript"),
    ("sync", "async"),
    ("sql", "nosql"),
    ("monolith", "microservice"),
]


class ConflictResolver:
    """Detects and resolves conflicting outputs from parallel agents.

    Detection strategies:
        1. Technology pair detection (PostgreSQL vs MongoDB)
        2. Negation pattern detection ("don't use X" vs "use X")
        3. LLM-based semantic conflict detection

    Resolution strategies:
        1. Priority-based (higher-role agent wins)
        2. Confidence-based (higher-confidence output wins)
        3. LLM arbitration (intelligent decision)
    """

    ROLE_PRIORITY: Dict[str, int] = {
        "planning": 5,
        "review": 4,
        "coding": 3,
        "testing": 3,
        "research": 2,
        "documentation": 1,
        "general": 0,
    }

    def __init__(self, llm_runtime: Optional[Any] = None) -> None:
        self._llm_runtime = llm_runtime

    def detect_conflicts(
        self,
        outputs: List[Dict[str, Any]],
    ) -> List[Conflict]:
        """Detect conflicts between agent outputs using heuristics."""
        conflicts: List[Conflict] = []

        for i in range(len(outputs)):
            for j in range(i + 1, len(outputs)):
                a = outputs[i]
                b = outputs[j]
                text_a = str(a.get("stdout", "")).lower()
                text_b = str(b.get("stdout", "")).lower()

                tech_conflict = self._detect_technology_conflict(text_a, text_b)
                if tech_conflict:
                    conflicts.append(
                        Conflict(
                            agent_a=str(a.get("agent_id", f"agent-{i}")),
                            agent_b=str(b.get("agent_id", f"agent-{j}")),
                            description=f"Technology conflict: {tech_conflict}",
                            output_a=text_a[:200],
                            output_b=text_b[:200],
                            severity="high",
                        ),
                    )
                    continue

                negation = self._detect_negation_conflict(text_a, text_b)
                if negation:
                    conflicts.append(
                        Conflict(
                            agent_a=str(a.get("agent_id", f"agent-{i}")),
                            agent_b=str(b.get("agent_id", f"agent-{j}")),
                            description=f"Contradictory recommendation: {negation}",
                            output_a=text_a[:200],
                            output_b=text_b[:200],
                            severity="medium",
                        ),
                    )

        return conflicts

    async def detect_conflicts_llm(
        self,
        outputs: List[Dict[str, Any]],
    ) -> List[Conflict]:
        """LLM-enhanced conflict detection for semantic contradictions."""
        rule_conflicts = self.detect_conflicts(outputs)

        if self._llm_runtime is None or len(outputs) < 2:
            return rule_conflicts

        try:
            from core.tools.llm_runtime import LlmRequest
            import json

            summaries = []
            for i, o in enumerate(outputs):
                text = str(o.get("stdout", ""))[:300]
                role = o.get("role", "general")
                summaries.append(f"Agent {i} ({role}): {text}")

            request = LlmRequest(
                prompt=(
                    "Analyze these parallel agent outputs for contradictions.\n\n"
                    + "\n\n".join(summaries)
                    + "\n\nReturn a JSON array of conflicts. Each conflict:\n"
                    '{"agent_a": 0, "agent_b": 1, "description": "..."}\n'
                    "Return [] if no conflicts. Return ONLY valid JSON."
                ),
                system_prompt="You are a conflict detection engine. Output ONLY valid JSON.",
                category="reasoning",
                max_tokens=300,
                temperature=0.0,
            )
            response = await self._llm_runtime.generate(request)
            if response.text and not response.error:
                text = response.text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    for c in parsed:
                        conflict = Conflict(
                            agent_a=str(c.get("agent_a", "")),
                            agent_b=str(c.get("agent_b", "")),
                            description=c.get("description", "LLM-detected conflict"),
                            severity="medium",
                        )
                        if not any(
                            rc.agent_a == conflict.agent_a and rc.agent_b == conflict.agent_b
                            for rc in rule_conflicts
                        ):
                            rule_conflicts.append(conflict)
        except Exception as e:
            logger.debug("LLM conflict detection failed: %s", e)

        return rule_conflicts

    def resolve_by_priority(
        self,
        conflict: Conflict,
        outputs: List[Dict[str, Any]],
    ) -> Resolution:
        """Resolve conflict by agent role priority."""
        role_a = "general"
        role_b = "general"
        out_a = ""
        out_b = ""

        for o in outputs:
            aid = str(o.get("agent_id", ""))
            if aid == conflict.agent_a:
                role_a = o.get("role", "general")
                out_a = str(o.get("stdout", ""))[:300]
            elif aid == conflict.agent_b:
                role_b = o.get("role", "general")
                out_b = str(o.get("stdout", ""))[:300]

        pri_a = self.ROLE_PRIORITY.get(role_a, 0)
        pri_b = self.ROLE_PRIORITY.get(role_b, 0)

        if pri_a >= pri_b:
            return Resolution(
                conflict=conflict,
                chosen_output=out_a,
                reasoning=f"Agent {conflict.agent_a} ({role_a}, priority {pri_a}) "
                          f"overrides {conflict.agent_b} ({role_b}, priority {pri_b}).",
                strategy="priority",
                confidence=0.6 + 0.1 * abs(pri_a - pri_b),
            )
        else:
            return Resolution(
                conflict=conflict,
                chosen_output=out_b,
                reasoning=f"Agent {conflict.agent_b} ({role_b}, priority {pri_b}) "
                          f"overrides {conflict.agent_a} ({role_a}, priority {pri_a}).",
                strategy="priority",
                confidence=0.6 + 0.1 * abs(pri_a - pri_b),
            )

    async def resolve_llm(
        self,
        conflict: Conflict,
        goal: str = "",
    ) -> Resolution:
        """Use LLM arbitration to resolve a conflict intelligently."""
        if self._llm_runtime is None:
            return Resolution(
                conflict=conflict,
                chosen_output=conflict.output_a,
                reasoning="No LLM available; defaulting to first agent.",
                strategy="default",
                confidence=0.3,
            )

        try:
            from core.tools.llm_runtime import LlmRequest

            request = LlmRequest(
                prompt=(
                    "Two agents produced conflicting outputs. Decide which is correct.\n\n"
                    f"Mission goal: {goal}\n"
                    f"Conflict: {conflict.description}\n\n"
                    f"Agent A output: {conflict.output_a[:400]}\n"
                    f"Agent B output: {conflict.output_b[:400]}\n\n"
                    "Which output is better for the mission goal? "
                    "Return a JSON object:\n"
                    '{"winner": "A" or "B", "reasoning": "...", "confidence": 0.0-1.0}\n'
                    "Return ONLY valid JSON."
                ),
                system_prompt="You are a conflict arbitrator. Output ONLY valid JSON.",
                category="reasoning",
                max_tokens=200,
                temperature=0.0,
            )
            response = await self._llm_runtime.generate(request)
            if response.text and not response.error:
                import json

                text = response.text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                parsed = json.loads(text)
                winner = parsed.get("winner", "A").upper()
                chosen = conflict.output_a if winner == "A" else conflict.output_b
                return Resolution(
                    conflict=conflict,
                    chosen_output=chosen,
                    reasoning=parsed.get("reasoning", "LLM arbitration"),
                    strategy="llm_arbitration",
                    confidence=float(parsed.get("confidence", 0.7)),
                )
        except Exception as e:
            logger.debug("LLM conflict resolution failed: %s", e)

        return Resolution(
            conflict=conflict,
            chosen_output=conflict.output_a,
            reasoning="LLM arbitration failed; defaulting to first agent.",
            strategy="default",
            confidence=0.3,
        )

    async def resolve_all(
        self,
        conflicts: List[Conflict],
        outputs: List[Dict[str, Any]],
        goal: str = "",
    ) -> List[Resolution]:
        """Resolve all detected conflicts."""
        resolutions: List[Resolution] = []
        for conflict in conflicts:
            if self._llm_runtime is not None:
                resolution = await self.resolve_llm(conflict, goal)
            else:
                resolution = self.resolve_by_priority(conflict, outputs)
            resolutions.append(resolution)
        return resolutions

    @staticmethod
    def _detect_technology_conflict(
        text_a: str, text_b: str,
    ) -> Optional[str]:
        """Check for mutually exclusive technology recommendations."""
        for tech1, tech2 in _TECHNOLOGY_PAIRS:
            if tech1 in text_a and tech2 in text_b:
                return f"{tech1} vs {tech2}"
            if tech2 in text_a and tech1 in text_b:
                return f"{tech2} vs {tech1}"
        return None

    @staticmethod
    def _detect_negation_conflict(
        text_a: str, text_b: str,
    ) -> Optional[str]:
        """Check for negation patterns suggesting contradiction."""
        for indicator in _CONFLICT_INDICATORS:
            if indicator in text_a and indicator not in text_b:
                return f"Agent A uses negation '{indicator}' absent in Agent B"
            if indicator in text_b and indicator not in text_a:
                return f"Agent B uses negation '{indicator}' absent in Agent A"
        return None
