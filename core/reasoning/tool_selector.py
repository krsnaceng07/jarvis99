"""JARVIS OS - Intelligent Tool Selection Engine.

Hybrid LLM + rule-based tool selection with cost optimization,
performance-aware scoring, and automatic fallback support.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.reasoning.decision_engine import DecisionEngine, ToolSelectionResult
from core.reasoning.task import ExecutorType

logger = logging.getLogger(__name__)


class ToolPerformanceRecord(BaseModel):
    """Aggregated performance stats for one executor type."""

    executor: ExecutorType
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    total_latency: float = 0.0
    total_cost: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / self.total_calls if self.total_calls > 0 else 0.5

    @property
    def avg_latency(self) -> float:
        return self.total_latency / self.total_calls if self.total_calls > 0 else 1.0

    @property
    def avg_cost(self) -> float:
        return self.total_cost / self.total_calls if self.total_calls > 0 else 0.05


class ToolPerformanceTracker:
    """Tracks execution performance per executor type for feedback learning."""

    def __init__(self) -> None:
        self._records: Dict[ExecutorType, ToolPerformanceRecord] = {}

    def record_execution(
        self,
        executor: ExecutorType,
        success: bool,
        latency: float,
        cost: float = 0.0,
    ) -> None:
        if executor not in self._records:
            self._records[executor] = ToolPerformanceRecord(executor=executor)
        rec = self._records[executor]
        rec.total_calls += 1
        if success:
            rec.successes += 1
        else:
            rec.failures += 1
        rec.total_latency += latency
        rec.total_cost += cost

    def get_stats(self, executor: ExecutorType) -> ToolPerformanceRecord:
        return self._records.get(
            executor, ToolPerformanceRecord(executor=executor)
        )

    def get_all_stats(self) -> Dict[ExecutorType, ToolPerformanceRecord]:
        return dict(self._records)

    def get_performance_summary(self) -> str:
        lines = []
        for ex, rec in self._records.items():
            lines.append(
                f"{ex.value}: {rec.success_rate:.0%} success, "
                f"{rec.avg_latency:.2f}s avg, ${rec.avg_cost:.3f}/call"
            )
        return "\n".join(lines) if lines else "No performance data yet."


class ToolSelectionEngine:
    """Intelligent tool selection combining rules, LLM, and performance history.

    Selection pipeline:
    1. Rule-based DecisionEngine for fast pattern matching
    2. If confidence < threshold OR complex task → LLM-driven selection
    3. Performance history adjusts confidence scores
    4. Cost optimization: skip LLM for simple/cheap selections
    """

    LLM_CONFIDENCE_THRESHOLD = 0.85

    def __init__(
        self,
        decision_engine: Optional[DecisionEngine] = None,
        llm_runtime: Optional[Any] = None,
        performance_tracker: Optional[ToolPerformanceTracker] = None,
    ) -> None:
        self._decision_engine = decision_engine or DecisionEngine()
        self._llm_runtime = llm_runtime
        self._tracker = performance_tracker or ToolPerformanceTracker()

    @property
    def tracker(self) -> ToolPerformanceTracker:
        return self._tracker

    async def select_tool(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolSelectionResult:
        """Select the best executor for a task description.

        Pipeline:
        1. Check forced executor override in context
        2. Rule-based selection via DecisionEngine
        3. If low confidence → LLM-enhanced selection
        4. Apply performance history adjustments
        """
        context = context or {}

        rule_result = self._decision_engine.select_tool(task_description, context)

        if context.get("forced_executor"):
            return rule_result

        if (
            rule_result.confidence >= self.LLM_CONFIDENCE_THRESHOLD
            or self._llm_runtime is None
        ):
            return self._apply_performance_adjustment(rule_result)

        llm_result = await self._llm_select(task_description, rule_result, context)
        return self._apply_performance_adjustment(llm_result)

    async def select_fallback(
        self,
        failed_executor: ExecutorType,
        task_description: str,
        error: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[ToolSelectionResult]:
        """Select an alternative executor after a failure."""
        context = context or {}

        if self._llm_runtime is not None:
            return await self._llm_select_fallback(
                failed_executor, task_description, error, context
            )

        rule_result = self._decision_engine.select_tool(task_description, context)
        if rule_result.alternative and rule_result.alternative != failed_executor:
            return ToolSelectionResult(
                executor_type=rule_result.alternative,
                confidence=rule_result.confidence * 0.8,
                reasoning=f"Fallback from {failed_executor.value}: {rule_result.reasoning}",
                alternative=None,
            )

        return self._rule_based_fallback(failed_executor)

    def record_result(
        self,
        executor: ExecutorType,
        success: bool,
        latency: float,
        cost: float = 0.0,
    ) -> None:
        self._tracker.record_execution(executor, success, latency, cost)

    async def _llm_select(
        self,
        task_description: str,
        rule_result: ToolSelectionResult,
        context: Dict[str, Any],
    ) -> ToolSelectionResult:
        """Use LLM to select the best tool when rules aren't confident enough."""
        try:
            from core.tools.llm_runtime import LlmRequest

            perf_summary = self._tracker.get_performance_summary()
            memory_hint = ""
            mem_ctx = context.get("memory_context")
            if mem_ctx and isinstance(mem_ctx, list):
                snippets = [
                    str(m.get("content", ""))[:150]
                    for m in mem_ctx[:3]
                    if m.get("content")
                ]
                if snippets:
                    memory_hint = (
                        "\nRelevant past experiences:\n"
                        + "\n".join(f"- {s}" for s in snippets) + "\n"
                    )

            prompt = (
                "Select the best execution tool for this task.\n\n"
                f"Task: {task_description}\n"
                f"Rule-based suggestion: {rule_result.executor_type.value} "
                f"(confidence: {rule_result.confidence:.2f})\n"
                f"\nAvailable tools:\n"
                f"- python: Code execution, data analysis, calculations\n"
                f"- shell: OS commands, system operations, file management\n"
                f"- browser: Web scraping, navigation, UI automation\n"
                f"- api: HTTP/REST calls, external services\n"
                f"- file: Read/write local files\n"
                f"- memory: Search/store in knowledge base\n"
                f"- llm: Text reasoning, summarization, generation\n"
                f"- human: Requires user input/approval\n"
                f"\nTool performance history:\n{perf_summary}"
                f"{memory_hint}\n"
                f"Return ONLY the tool name (one word). No explanation."
            )

            request = LlmRequest(
                prompt=prompt,
                system_prompt=(
                    "You are a tool selection engine. Return ONLY the tool name. "
                    "Choose the most effective tool based on the task and history."
                ),
                category="reasoning",
                max_tokens=20,
                temperature=0.0,
            )
            response = await self._llm_runtime.generate(request)

            if response.text and not response.error:
                chosen = response.text.strip().lower().rstrip(".")
                try:
                    executor = ExecutorType(chosen)
                    return ToolSelectionResult(
                        executor_type=executor,
                        confidence=0.90,
                        reasoning=f"LLM selected {chosen} over rule-based {rule_result.executor_type.value}.",
                        alternative=rule_result.executor_type if executor != rule_result.executor_type else rule_result.alternative,
                    )
                except ValueError:
                    logger.debug("LLM returned unknown executor: %s", chosen)

        except Exception as e:
            logger.debug("LLM tool selection failed: %s", e)

        return rule_result

    async def _llm_select_fallback(
        self,
        failed_executor: ExecutorType,
        task_description: str,
        error: str,
        context: Dict[str, Any],
    ) -> Optional[ToolSelectionResult]:
        """Use LLM to intelligently pick a fallback after failure."""
        try:
            from core.tools.llm_runtime import LlmRequest

            available = [e.value for e in ExecutorType if e != failed_executor]

            prompt = (
                "A tool execution failed. Select the best alternative.\n\n"
                f"Task: {task_description}\n"
                f"Failed tool: {failed_executor.value}\n"
                f"Error: {error[:300]}\n"
                f"Available alternatives: {', '.join(available)}\n\n"
                f"Return ONLY the alternative tool name (one word). "
                f"If no alternative can work, return 'none'."
            )

            request = LlmRequest(
                prompt=prompt,
                system_prompt=(
                    "You are a tool failure recovery engine. "
                    "Pick the best fallback tool. Return ONLY the tool name."
                ),
                category="reasoning",
                max_tokens=20,
                temperature=0.0,
            )
            response = await self._llm_runtime.generate(request)

            if response.text and not response.error:
                chosen = response.text.strip().lower().rstrip(".")
                if chosen == "none":
                    return None
                try:
                    executor = ExecutorType(chosen)
                    return ToolSelectionResult(
                        executor_type=executor,
                        confidence=0.75,
                        reasoning=f"LLM fallback: {chosen} after {failed_executor.value} failed ({error[:100]}).",
                        alternative=None,
                    )
                except ValueError:
                    pass

        except Exception as e:
            logger.debug("LLM fallback selection failed: %s", e)

        return self._rule_based_fallback(failed_executor)

    def _apply_performance_adjustment(
        self, result: ToolSelectionResult
    ) -> ToolSelectionResult:
        """Adjust confidence based on historical performance."""
        stats = self._tracker.get_stats(result.executor_type)
        if stats.total_calls < 3:
            return result

        perf_factor = stats.success_rate
        adjusted_confidence = result.confidence * (0.6 + 0.4 * perf_factor)
        adjusted_confidence = max(0.1, min(1.0, adjusted_confidence))

        if perf_factor < 0.5 and result.alternative:
            alt_stats = self._tracker.get_stats(result.alternative)
            if alt_stats.success_rate > perf_factor:
                logger.info(
                    "Performance swap: %s (%.0f%%) → %s (%.0f%%)",
                    result.executor_type.value, perf_factor * 100,
                    result.alternative.value, alt_stats.success_rate * 100,
                )
                return ToolSelectionResult(
                    executor_type=result.alternative,
                    confidence=adjusted_confidence,
                    reasoning=(
                        f"Swapped to {result.alternative.value} due to poor "
                        f"{result.executor_type.value} performance "
                        f"({perf_factor:.0%} success rate)."
                    ),
                    alternative=result.executor_type,
                )

        return ToolSelectionResult(
            executor_type=result.executor_type,
            confidence=adjusted_confidence,
            reasoning=result.reasoning,
            alternative=result.alternative,
        )

    @staticmethod
    def _rule_based_fallback(
        failed_executor: ExecutorType,
    ) -> Optional[ToolSelectionResult]:
        """Static fallback mapping when LLM is unavailable."""
        fallback_map: Dict[ExecutorType, ExecutorType] = {
            ExecutorType.PYTHON: ExecutorType.SHELL,
            ExecutorType.SHELL: ExecutorType.PYTHON,
            ExecutorType.BROWSER: ExecutorType.API,
            ExecutorType.API: ExecutorType.PYTHON,
            ExecutorType.FILE: ExecutorType.PYTHON,
        }
        alt = fallback_map.get(failed_executor)
        if alt:
            return ToolSelectionResult(
                executor_type=alt,
                confidence=0.6,
                reasoning=f"Rule-based fallback from {failed_executor.value} to {alt.value}.",
                alternative=None,
            )
        return None
