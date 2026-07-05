"""
PHASE: 24
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/84_PHASE_24_AUTONOMOUS_AGENT_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/85_PHASE_24_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.reasoning.task import ExecutorType


class ToolSelectionResult(BaseModel):
    """Output of the Decision Engine's tool-selection analysis."""

    executor_type: ExecutorType = Field(
        ..., description="Recommended executor type for the task."
    )
    confidence: float = Field(
        ..., description="Confidence score [0.0–1.0] in this selection."
    )
    reasoning: str = Field(
        ..., description="Short explanation of why this executor was chosen."
    )
    alternative: Optional[ExecutorType] = Field(
        default=None,
        description="Fallback executor if primary fails.",
    )


# ── Decision rules ───────────────────────────────────────────────────────────
#
#  Each rule is: (pattern_list, executor, confidence, reasoning, alternative)
#  Rules are evaluated in order; first match wins.

_RULES: List[
    tuple[List[str], ExecutorType, float, str, Optional[ExecutorType]]
] = [
    # Browser / web scraping
    (
        ["browser", "screenshot", "navigate", "click", "dom", "web page", "url", "http"],
        ExecutorType.BROWSER,
        0.90,
        "Task requires browser interaction or web page navigation.",
        ExecutorType.API,
    ),
    # Python code execution
    (
        [
            "python", "code", "script", "calculate", "compute",
            "analyse", "analyze", "parse", "csv", "dataframe",
            "pandas", "numpy", "plot", "graph", "generate",
        ],
        ExecutorType.PYTHON,
        0.88,
        "Task requires Python code execution or data processing.",
        ExecutorType.SHELL,
    ),
    # Shell / system commands
    (
        [
            "shell", "command", "terminal", "bash", "powershell",
            "install", "pip", "apt", "brew", "mkdir", "rm", "ls",
            "chmod", "chown", "move", "copy", "rename",
        ],
        ExecutorType.SHELL,
        0.85,
        "Task requires OS-level shell command execution.",
        ExecutorType.PYTHON,
    ),
    # File operations
    (
        [
            "file", "read file", "write file", "save", "load",
            "pdf", "txt", "json", "yaml", "csv file", "directory",
            "folder", "search files",
        ],
        ExecutorType.FILE,
        0.87,
        "Task requires filesystem read/write operations.",
        ExecutorType.PYTHON,
    ),
    # API / HTTP calls
    (
        [
            "api", "rest", "endpoint", "fetch", "request", "post",
            "get", "webhook", "json api", "http", "https", "curl",
            "email", "smtp", "send email",
        ],
        ExecutorType.API,
        0.85,
        "Task requires an HTTP API call or remote service interaction.",
        ExecutorType.PYTHON,
    ),
    # Memory queries
    (
        [
            "memory", "recall", "remember", "retrieve", "search memory",
            "what did i", "past context", "previous",
        ],
        ExecutorType.MEMORY,
        0.88,
        "Task requires memory retrieval from the knowledge store.",
        None,
    ),
    # Human approval / input
    (
        [
            "confirm", "approve", "human", "ask user", "wait for",
            "manual", "input required", "permission",
        ],
        ExecutorType.HUMAN,
        0.92,
        "Task requires explicit human approval or input.",
        None,
    ),
    # LLM reasoning
    (
        [
            "summarise", "summarize", "explain", "describe", "write",
            "draft", "translate", "llm", "reason", "think",
        ],
        ExecutorType.LLM,
        0.80,
        "Task requires LLM text reasoning or content generation.",
        None,
    ),
]

_DEFAULT_RULE = (
    ExecutorType.LLM,
    0.40,
    "No specific tool pattern matched; defaulting to LLM reasoning.",
    None,
)


class DecisionEngine:
    """Analyses task descriptions to select the most appropriate executor.

    Architecture:
        Observe task description
            ↓
        Pattern-match against known tool signatures
            ↓
        Return ToolSelectionResult (executor + confidence + reasoning)

    Constraint: DecisionEngine only reads; it NEVER invokes any executor.
    """

    def select_tool(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolSelectionResult:
        """Select the best executor for the given task description.

        Args:
            task_description: Natural-language description of what must be done.
            context: Optional contextual hints (e.g. previous executor, error type).

        Returns:
            ToolSelectionResult with recommended executor and confidence.
        """
        lower = task_description.lower()
        context = context or {}

        # Honour explicit override from context (e.g. Reflection Engine advice)
        forced = context.get("forced_executor")
        if forced:
            try:
                forced_type = ExecutorType(forced)
                return ToolSelectionResult(
                    executor_type=forced_type,
                    confidence=0.95,
                    reasoning=f"Executor forced by context override: {forced}.",
                )
            except ValueError:
                pass

        # Pattern-match rules in priority order
        for patterns, executor, confidence, reasoning, alternative in _RULES:
            if any(re.search(r"\b" + re.escape(p) + r"\b", lower) for p in patterns):
                return ToolSelectionResult(
                    executor_type=executor,
                    confidence=confidence,
                    reasoning=reasoning,
                    alternative=alternative,
                )

        # Default fallback
        executor, confidence, reasoning, alternative = _DEFAULT_RULE
        return ToolSelectionResult(
            executor_type=executor,
            confidence=confidence,
            reasoning=reasoning,
            alternative=alternative,
        )
