"""
PHASE: 21
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 21 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class GoalConstraints(BaseModel):
    """Operational limits and security bounds for planning and execution."""

    budget: float = 10.0
    deadline_hours: float = 24.0
    token_limit: int = 50000
    security_level: str = "standard"
    allowed_tools: List[str] = Field(default_factory=list)
    forbidden_tools: List[str] = Field(default_factory=list)
    parallel_limit: int = 3
    schema_version: Literal["1.0"] = "1.0"


class Goal(BaseModel):
    """Represents a high-level goal request from the user."""

    id: UUID = Field(default_factory=uuid4)
    goal_text: str
    owner_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: Literal["1.0"] = "1.0"


class GoalAnalysis(BaseModel):
    """Structured analysis parameters derived from a parsed Goal."""

    goal_id: UUID
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    complexity: str = "medium"  # low, medium, high
    preconditions: List[str] = Field(default_factory=list)
    postconditions: List[str] = Field(default_factory=list)
    constraints: GoalConstraints = Field(default_factory=GoalConstraints)
    tags: List[str] = Field(default_factory=list)
    schema_version: Literal["1.0"] = "1.0"


class GoalAnalyzer:
    """Rule-based goal analysis parser. Extracts constraints and metadata from text."""

    def analyze(self, goal: Goal) -> GoalAnalysis:
        text = goal.goal_text.lower()

        # Rule extraction heuristics
        budget = 10.0
        budget_match = re.search(r"(?:budget|cost)\s*=\s*\$?(\d+(?:\.\d+)?)", text)
        if budget_match:
            budget = float(budget_match.group(1))
        elif "$" in text:
            dollar_match = re.search(r"\$(\d+(?:\.\d+)?)", text)
            if dollar_match:
                budget = float(dollar_match.group(1))

        deadline_hours = 24.0
        deadline_match = re.search(r"(?:deadline|time|hours)\s*=\s*(\d+(?:\.\d+)?)", text)
        if deadline_match:
            deadline_hours = float(deadline_match.group(1))

        parallel_limit = 3
        parallel_match = re.search(r"parallel\s*=\s*(\d+)", text)
        if parallel_match:
            parallel_limit = int(parallel_match.group(1))

        # Extract allowed/forbidden tools
        forbidden_tools: List[str] = []
        forbidden_match = re.search(r"forbidden\s*=\s*([a-zA-Z0-9_,]+)", text)
        if forbidden_match:
            forbidden_tools = [t.strip() for t in forbidden_match.group(1).split(",") if t.strip()]

        allowed_tools: List[str] = []
        allowed_match = re.search(r"allowed\s*=\s*([a-zA-Z0-9_,]+)", text)
        if allowed_match:
            allowed_tools = [t.strip() for t in allowed_match.group(1).split(",") if t.strip()]

        # Complexity determination
        complexity = "medium"
        if len(text.split()) > 20 or "complex" in text or "deploy" in text:
            complexity = "high"
        elif len(text.split()) < 5:
            complexity = "low"

        # Tags extraction
        tags = []
        tags_match = re.findall(r"#(\w+)", goal.goal_text)
        if tags_match:
            tags = [t.lower() for t in tags_match]

        constraints = GoalConstraints(
            budget=budget,
            deadline_hours=deadline_hours,
            allowed_tools=allowed_tools,
            forbidden_tools=forbidden_tools,
            parallel_limit=parallel_limit,
        )

        # Pre/Post conditions
        preconditions = []
        if "precondition:" in text:
            pre_match = re.search(r"precondition:\s*([a-zA-Z0-9_,]+)", text)
            if pre_match:
                preconditions = [p.strip() for p in pre_match.group(1).split(",") if p.strip()]

        postconditions = []
        if "postcondition:" in text:
            post_match = re.search(r"postcondition:\s*([a-zA-Z0-9_,]+)", text)
            if post_match:
                postconditions = [p.strip() for p in post_match.group(1).split(",") if p.strip()]

        return GoalAnalysis(
            goal_id=goal.id,
            complexity=complexity,
            preconditions=preconditions,
            postconditions=postconditions,
            constraints=constraints,
            tags=tags,
        )
