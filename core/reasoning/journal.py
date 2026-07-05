"""
PHASE: 25
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/85_PHASE_25_BROWSER_RUNTIME_SPECIFICATION.md

IMPLEMENTATION PLAN:
    Phase 25 Approved Plan

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Architect Constraints (Phase 25):
    1. Journal is APPEND-ONLY — no editing, no deleting previous records.
    2. Journal never stores raw LLM prompts — summaries only.
    3. Journal export ordering is deterministic: iteration ASC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


class IterationRecord(BaseModel):
    """Immutable snapshot of a single AgentLoop iteration.

    Each record captures the essential decision, action, and outcome
    of one cycle through the Observe-Think-Plan-Execute-Reflect loop.
    """

    iteration: int = Field(..., description="1-based iteration number.")
    goal_description: str = Field(
        default="", description="High-level summary of the current sub-goal."
    )
    chosen_executor: str = Field(
        default="", description="Executor type selected (e.g. PYTHON, BROWSER, SHELL)."
    )
    reasoning: str = Field(
        default="",
        description=(
            "Short reasoning summary explaining why this action was chosen. "
            "MUST NOT contain raw LLM prompts (Architect Constraint 3)."
        ),
    )
    output_summary: str = Field(
        default="",
        description="Condensed summary of the execution output (max ~200 chars).",
    )
    reflection_category: Optional[str] = Field(
        default=None,
        description="FailureCategory if the step failed, else None.",
    )
    next_action: str = Field(
        default="CONTINUE",
        description="What the loop decided to do next: CONTINUE, REPLAN, ABORT, or SUCCESS.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of when this record was created.",
    )


class ExecutionJournal:
    """Append-only, in-memory journal recording AgentLoop iterations.

    Architect Constraints:
        - APPEND-ONLY: ``record_iteration`` is the sole write path.
          No edit, delete, or update method exists or may be added.
        - DETERMINISTIC EXPORT: ``export()`` always returns records in
          ascending iteration order.
        - NO RAW PROMPTS: Only summary strings are stored.

    Usage::

        journal = ExecutionJournal()
        journal.record_iteration(
            iteration=1,
            goal_description="Navigate to login page",
            chosen_executor="BROWSER",
            reasoning="Login required before downloading report.",
            output_summary="Navigated to https://app.example.com/login",
            next_action="CONTINUE",
        )
        records = journal.export()
        text = journal.export_text()
    """

    def __init__(self) -> None:
        """Initialise an empty journal."""
        self._records: List[IterationRecord] = []

    def record_iteration(
        self,
        *,
        iteration: int,
        goal_description: str = "",
        chosen_executor: str = "",
        reasoning: str = "",
        output_summary: str = "",
        reflection_category: Optional[str] = None,
        next_action: str = "CONTINUE",
    ) -> None:
        """Append one iteration record to the journal.

        Args:
            iteration: 1-based iteration counter.
            goal_description: What the agent is trying to accomplish.
            chosen_executor: Which executor type was selected.
            reasoning: Short summary of why (NOT a raw LLM prompt).
            output_summary: Condensed output string.
            reflection_category: Failure classification if failed, else None.
            next_action: CONTINUE | REPLAN | ABORT | SUCCESS.
        """
        record = IterationRecord(
            iteration=iteration,
            goal_description=goal_description,
            chosen_executor=chosen_executor,
            reasoning=reasoning,
            output_summary=output_summary,
            reflection_category=reflection_category,
            next_action=next_action,
        )
        self._records.append(record)

    def export(self) -> List[IterationRecord]:
        """Return all records in deterministic ascending iteration order.

        Returns:
            Sorted (by iteration ASC) list of IterationRecord objects.
        """
        return sorted(self._records, key=lambda r: r.iteration)

    def export_text(self) -> str:
        """Produce a human-readable plain-text journal dump.

        Returns:
            Multi-line string suitable for logging or debugging display.
        """
        lines: list[str] = []
        for rec in self.export():
            lines.append(f"--- Iteration {rec.iteration} ---")
            lines.append(f"  Goal:       {rec.goal_description}")
            lines.append(f"  Executor:   {rec.chosen_executor}")
            lines.append(f"  Reasoning:  {rec.reasoning}")
            lines.append(f"  Output:     {rec.output_summary}")
            if rec.reflection_category:
                lines.append(f"  Reflection: {rec.reflection_category}")
            lines.append(f"  Next:       {rec.next_action}")
            lines.append(f"  Time:       {rec.timestamp.isoformat()}")
            lines.append("")
        return "\n".join(lines)

    def __len__(self) -> int:
        """Return the number of recorded iterations."""
        return len(self._records)
