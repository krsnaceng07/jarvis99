"""
PHASE: 20
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 20 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.memory.dto import MemoryRecord
from core.memory.retrieval_engine import estimate_tokens


class MemoryContextBuilder:
    """Builds unified, token-budget-enforced context packages for Brain/LLM consumption.

    Orchestrates different categories of active context (Goals, Conversation, Preferences, Graph Knowledge)
    and formats them with clear semantic markers.
    """

    def __init__(self, default_max_tokens: int = 2000) -> None:
        self.default_max_tokens = default_max_tokens

    def build_context_package(
        self,
        current_goal: Optional[str] = None,
        conversation_history: Optional[List[MemoryRecord]] = None,
        personal_memories: Optional[List[MemoryRecord]] = None,
        knowledge_nodes: Optional[List[MemoryRecord]] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Compile and format different memory sources into a structured context package."""
        max_tokens = max_tokens or self.default_max_tokens
        history = conversation_history or []
        personal = personal_memories or []
        knowledge = knowledge_nodes or []

        # Token usage trackers
        goal_tokens = estimate_tokens(current_goal) if current_goal else 0
        budget_remaining = max_tokens - goal_tokens

        # Enforce budget and format segments
        formatted_history: List[str] = []
        history_tokens = 0
        for rec in reversed(history):  # prioritize most recent
            rec_tokens = estimate_tokens(rec.content)
            if history_tokens + rec_tokens > int(
                max_tokens * 0.4
            ):  # cap history at 40%
                continue
            formatted_history.insert(0, f"- {rec.content}")
            history_tokens += rec_tokens

        budget_remaining -= history_tokens

        formatted_personal: List[str] = []
        personal_tokens = 0
        for rec in personal:
            rec_tokens = estimate_tokens(rec.content)
            if personal_tokens + rec_tokens > int(
                max_tokens * 0.3
            ):  # cap personal at 30%
                continue
            formatted_personal.append(f"- {rec.content}")
            personal_tokens += rec_tokens

        budget_remaining -= personal_tokens

        formatted_knowledge: List[str] = []
        knowledge_tokens = 0
        for rec in knowledge:
            rec_tokens = estimate_tokens(rec.content)
            if knowledge_tokens + rec_tokens > budget_remaining:
                continue
            formatted_knowledge.append(f"- {rec.content}")
            knowledge_tokens += rec_tokens

        budget_remaining -= knowledge_tokens

        # Build Context String
        parts = []
        if current_goal:
            parts.append(f"### CURRENT GOAL\n{current_goal}")
        if formatted_history:
            parts.append("### CONVERSATION HISTORY\n" + "\n".join(formatted_history))
        if formatted_personal:
            parts.append(
                "### USER PREFERENCES & FACTS\n" + "\n".join(formatted_personal)
            )
        if formatted_knowledge:
            parts.append("### RELATIONAL KNOWLEDGE\n" + "\n".join(formatted_knowledge))

        context_string = "\n\n".join(parts)
        total_used_tokens = (
            goal_tokens + history_tokens + personal_tokens + knowledge_tokens
        )

        return {
            "context_string": context_string,
            "tokens_used": total_used_tokens,
            "budget_limit": max_tokens,
            "breakdown": {
                "goal": goal_tokens,
                "conversation": history_tokens,
                "personal": personal_tokens,
                "knowledge": knowledge_tokens,
            },
        }
