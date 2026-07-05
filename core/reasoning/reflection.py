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

Architect Constraint (Phase 24, Condition 2):
    ReflectionEngine MUST NOT execute tools, call APIs, write files, or run code.
    Its responsibility is ONLY: analyze → classify → advise.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.tools.dto import ToolExecutionResult

# Legacy settings import (optional — used only by reflect_and_correct for backward compat)
try:
    from core.config import Settings as _Settings
except ImportError:
    _Settings = None  # type: ignore[assignment,misc]


class FailureCategory(str, Enum):
    """Enumeration of root-cause failure categories for task diagnostics."""

    TOOL_FAILURE = "TOOL_FAILURE"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    NETWORK_ERROR = "NETWORK_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TIMEOUT = "TIMEOUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    LOGIC_ERROR = "LOGIC_ERROR"
    UNKNOWN = "UNKNOWN"


class RepairStrategy(BaseModel):
    """Structured repair advice returned by the Reflection Engine."""

    strategy: str = Field(..., description="Human-readable repair instruction.")
    suggested_executor: Optional[str] = Field(
        default=None,
        description="Suggested executor type to retry with (e.g. 'shell', 'python').",
    )
    suggested_payload_patch: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value patches to apply to the next task's payload.",
    )
    confidence: float = Field(
        default=0.5,
        description="Confidence score [0.0–1.0] that this strategy will succeed.",
    )


class ReflectionOutput(BaseModel):
    """Full analysis result from the Reflection Engine."""

    success: bool = Field(..., description="Whether the evaluated execution succeeded.")
    failure_category: Optional[FailureCategory] = Field(
        default=None, description="Root-cause failure classification."
    )
    failure_summary: str = Field(
        default="", description="Short human-readable failure description."
    )
    repair_strategy: Optional[RepairStrategy] = Field(
        default=None, description="Structured repair advice (None on success)."
    )
    should_replan: bool = Field(
        default=False,
        description="True when the Agent Loop should trigger dynamic replanning.",
    )
    should_abort: bool = Field(
        default=False,
        description="True when the failure is unrecoverable and the loop must stop.",
    )


# ── Failure pattern matching ────────────────────────────────────────────────

_PATTERN_MAP: List[tuple[str, FailureCategory, str, str]] = [
    # (stderr_substring, category, strategy_text, suggested_executor)
    (
        "ModuleNotFoundError",
        FailureCategory.MISSING_DEPENDENCY,
        "Install the missing Python package via 'pip install <package>' using ShellExecutor, then retry.",
        "shell",
    ),
    (
        "ImportError",
        FailureCategory.MISSING_DEPENDENCY,
        "Resolve the import error by installing or fixing the missing module.",
        "shell",
    ),
    (
        "SyntaxError",
        FailureCategory.SYNTAX_ERROR,
        "The generated Python code has a syntax error. Re-generate corrected code.",
        "python",
    ),
    (
        "timed out",
        FailureCategory.TIMEOUT,
        "Execution exceeded timeout. Increase timeout or split the task into smaller steps.",
        None,
    ),
    (
        "Connection refused",
        FailureCategory.NETWORK_ERROR,
        "Target service is unreachable. Check network connectivity or retry after delay.",
        "api",
    ),
    (
        "PermissionError",
        FailureCategory.PERMISSION_DENIED,
        "Insufficient filesystem permissions. Check path ownership or run as elevated user.",
        "shell",
    ),
    (
        "Permission denied",
        FailureCategory.PERMISSION_DENIED,
        "Insufficient filesystem permissions. Check path ownership or run as elevated user.",
        "shell",
    ),
    (
        "BUDGET",
        FailureCategory.BUDGET_EXCEEDED,
        "API cost budget exhausted. Switch to a local provider (Qwen/Llama) or reduce token usage.",
        None,
    ),
]

_UNRECOVERABLE: frozenset[FailureCategory] = frozenset(
    {FailureCategory.BUDGET_EXCEEDED, FailureCategory.PERMISSION_DENIED}
)


class ReflectionEngine:
    """Analyzes tool execution outcomes and produces structured repair advice.

    Architect Constraint:
        This class MUST NOT call any executor, tool, API, or filesystem operation.
        It only reads result data and returns advice structs.

    Backward compatibility:
        Accepts an optional `settings` argument in __init__ for callers that
        pre-date Phase 24 (Phase 21 ReasoningSession tests). Settings is not
        used by Phase 24 paths but must not break legacy callers.
    """

    # ── Reflection count ceiling (legacy reflect_and_correct) ────────────────
    MAX_REFLECTIONS: int = 3
    BASE_CONFIDENCE: float = 0.60
    CONFIDENCE_INCREMENT: float = 0.15

    def __init__(self, settings: Any = None) -> None:  # noqa: ANN401
        """Initialise ReflectionEngine.

        Args:
            settings: Optional Settings object (kept for backward compat only;
                      not used by Phase 24 analyze() path).
        """
        # settings deliberately unused — Phase 24 is stateless
        _ = settings

    async def reflect_and_correct(
        self,
        task_name: str,
        execution_result: Dict[str, Any],
        session: Any,
        target_confidence: float = 0.90,
    ) -> Dict[str, Any]:
        """Legacy reflection loop interface (Phase 21 / ReasoningSession compat).

        Analyses a high-level execution dict result and returns a structured
        reflection outcome with iteration counting and early stopping.

        Args:
            task_name: Human-readable task label for tracing.
            execution_result: Dict with at least {"status": "SUCCESS"|"FAILURE"}.
            session: ReasoningSession object with reflection_count and budget attrs.
            target_confidence: Confidence threshold that triggers early-stop success.

        Returns:
            Dict: {"status": str, "reason": str, "reflection_count": int}
        """
        # Budget early-stop
        if hasattr(session, "total_cost") and hasattr(session, "budget"):
            if session.total_cost >= session.budget:
                return {"status": "STOPPED", "reason": "BUDGET_EXCEEDED", "reflection_count": getattr(session, "reflection_count", 0)}

        # Increment session reflection count
        if not hasattr(session, "reflection_count"):
            session.reflection_count = 0
        session.reflection_count += 1
        count = session.reflection_count

        # Success fast-path
        if execution_result.get("status") == "SUCCESS":
            return {"status": "RESOLVED", "reason": "SUCCESS", "reflection_count": count}

        # Maximum reflections ceiling
        if count >= self.MAX_REFLECTIONS:
            return {"status": "FAILED", "reason": "MODEL_FAILURE", "reflection_count": count}

        # Confidence-based early stop on repeated failure
        current_confidence = round(
            self.BASE_CONFIDENCE + (count * self.CONFIDENCE_INCREMENT), 10
        )
        if current_confidence >= target_confidence:
            return {"status": "RESOLVED", "reason": "SUCCESS", "reflection_count": count}

        return {"status": "RETRY", "reason": "LOW_CONFIDENCE", "reflection_count": count}

    def analyze(self, result: ToolExecutionResult) -> ReflectionOutput:
        """Analyse a completed tool execution result and produce structured advice.

        Args:
            result: The ToolExecutionResult from any executor.

        Returns:
            ReflectionOutput with classification and optional repair strategy.
        """
        if result.status == "SUCCESS" and result.exit_code == 0:
            return ReflectionOutput(success=True)

        # Combine stderr + error for pattern matching
        combined_text = " ".join(
            filter(None, [result.stderr or "", result.error or ""])
        )

        category, strategy_text, suggested_executor = self._classify(combined_text)

        # Build repair strategy
        repair = RepairStrategy(
            strategy=strategy_text,
            suggested_executor=suggested_executor,
            confidence=0.75 if category != FailureCategory.UNKNOWN else 0.30,
        )

        should_abort = category in _UNRECOVERABLE

        return ReflectionOutput(
            success=False,
            failure_category=category,
            failure_summary=f"[{category.value}] {combined_text[:200]}",
            repair_strategy=repair,
            should_replan=not should_abort,
            should_abort=should_abort,
        )

    def _classify(
        self, text: str
    ) -> tuple[FailureCategory, str, Optional[str]]:
        """Match failure text against known patterns and return classification.

        Args:
            text: Combined stderr + error string.

        Returns:
            Tuple of (FailureCategory, strategy_text, suggested_executor).
        """
        for pattern, category, strategy, executor in _PATTERN_MAP:
            if pattern.lower() in text.lower():
                return category, strategy, executor

        return (
            FailureCategory.UNKNOWN,
            "Unknown failure. Review stdout/stderr and consider retrying with adjusted parameters.",
            None,
        )
