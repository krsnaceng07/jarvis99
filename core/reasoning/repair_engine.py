"""
PHASE: 40
STATUS: IMPLEMENTATION
SPECIFICATION:
    Goal #4 — Autonomous Repair

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Architecture:
    RepairEngine orchestrates: classify → diagnose → plan → retry → learn → update.
    It delegates classification to ReflectionEngine, fallback selection to
    ToolSelectionEngine, and ambiguous reasoning to LlmRuntime.
    It MUST NOT bypass ToolDispatcher — it receives executors as a dict
    and dispatches through them directly for repair attempts only.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.reasoning.reflection import (
    FailureCategory,
    ReflectionEngine,
    ReflectionOutput,
    RepairStrategy,
)
from core.reasoning.task import ExecutorType, Task
from core.tools.dto import ToolExecutionResult

logger = logging.getLogger(__name__)


# ── DTOs ────────────────────────────────────────────────────────────────────


class RepairRecord(BaseModel):
    """Single repair attempt record for failure learning."""

    failure_category: FailureCategory
    error_signature: str = Field(
        ..., description="Normalised error pattern for cache lookup.",
    )
    original_executor: str
    repair_executor: str
    strategy_used: str
    success: bool
    timestamp: float = Field(default_factory=time.time)


class RepairPlan(BaseModel):
    """Ranked multi-strategy repair plan."""

    root_cause: str = Field(
        ..., description="Human-readable root cause diagnosis.",
    )
    is_recoverable: bool = Field(
        default=True, description="False when failure is unrecoverable.",
    )
    strategies: List[RepairStrategy] = Field(
        default_factory=list,
        description="Repair strategies ranked by confidence (highest first).",
    )


class RepairOutcome(BaseModel):
    """Result of a full repair cycle."""

    result: ToolExecutionResult
    strategy_used: Optional[RepairStrategy] = None
    attempts: int = 0
    learned: bool = Field(
        default=False, description="Whether a new repair pattern was learned.",
    )


# ── Repair Engine ───────────────────────────────────────────────────────────


class RepairEngine:
    """Autonomous repair orchestrator.

    Pipeline per failure:
        1. Classify failure  (ReflectionEngine.analyze)
        2. Diagnose root cause  (LLM-enhanced for UNKNOWN)
        3. Plan repair  (multi-strategy, ranked by confidence)
        4. Multi-stage retry  (same tool → different tool → different strategy)
        5. Learn from success  (store repair pattern for future recall)
        6. Update confidence  (ToolSelectionEngine performance tracking)

    Uses existing components — no duplication:
        ReflectionEngine → failure analysis
        ToolSelectionEngine → fallback tool selection + confidence updates
        LlmRuntime → ambiguous repair reasoning
    """

    MAX_REPAIR_STAGES = 3

    def __init__(
        self,
        reflection_engine: ReflectionEngine,
        tool_selector: Optional[Any] = None,
        llm_runtime: Optional[Any] = None,
    ) -> None:
        self._reflection = reflection_engine
        self._tool_selector = tool_selector
        self._llm_runtime = llm_runtime
        self._repair_history: List[RepairRecord] = []
        self._pattern_cache: Dict[str, RepairStrategy] = {}

    # ── Public API ──────────────────────────────────────────────────────────

    async def attempt_repair(
        self,
        task: Task,
        failed_result: ToolExecutionResult,
        executors: Dict[ExecutorType, Any],
        context: Dict[str, Any],
    ) -> RepairOutcome:
        """Full autonomous repair pipeline.

        Args:
            task: The task that failed.
            failed_result: The ToolExecutionResult from the failed execution.
            executors: Dict of ExecutorType → BaseExecutor instances.
            context: Shared execution context.

        Returns:
            RepairOutcome with the best result achieved and learning flag.
        """
        reflection = self._reflection.analyze(failed_result)

        if reflection.success:
            return RepairOutcome(result=failed_result, attempts=0)

        if reflection.should_abort:
            logger.info(
                "Repair aborted for task %s: unrecoverable %s",
                task.id, reflection.failure_category,
            )
            return RepairOutcome(result=failed_result, attempts=0)

        root_cause = await self._diagnose(failed_result, reflection)

        plan = await self._plan_repair(
            task, failed_result, reflection, root_cause, context,
        )

        if not plan.is_recoverable or not plan.strategies:
            return RepairOutcome(result=failed_result, attempts=0)

        return await self._execute_repair(
            task, plan, executors, context, reflection,
        )

    # ── Stage 2: Root Cause Diagnosis ───────────────────────────────────────

    async def _diagnose(
        self,
        result: ToolExecutionResult,
        reflection: ReflectionOutput,
    ) -> str:
        """Deep root cause analysis, LLM-enhanced for ambiguous failures."""
        if reflection.failure_category != FailureCategory.UNKNOWN:
            return reflection.failure_summary

        if self._llm_runtime is None:
            return reflection.failure_summary or "Unknown failure"

        try:
            from core.tools.llm_runtime import LlmRequest

            combined = " ".join(
                filter(None, [result.stderr or "", result.error or ""])
            )[:500]

            request = LlmRequest(
                prompt=(
                    "Diagnose the root cause of this execution failure.\n\n"
                    f"Exit code: {result.exit_code}\n"
                    f"Error output: {combined}\n\n"
                    "Return ONE sentence describing the root cause. "
                    "Be specific about what went wrong and why."
                ),
                system_prompt="You are a failure diagnosis engine. Be precise and concise.",
                category="reasoning",
                max_tokens=100,
                temperature=0.0,
            )
            response = await self._llm_runtime.generate(request)
            if response.text and not response.error:
                return response.text.strip()
        except Exception as e:
            logger.debug("LLM diagnosis failed: %s", e)

        return reflection.failure_summary or "Unknown failure"

    # ── Stage 3: Repair Planning ────────────────────────────────────────────

    async def _plan_repair(
        self,
        task: Task,
        result: ToolExecutionResult,
        reflection: ReflectionOutput,
        root_cause: str,
        context: Dict[str, Any],
    ) -> RepairPlan:
        """Generate ranked repair strategies from multiple sources."""
        if reflection.should_abort:
            return RepairPlan(
                root_cause=root_cause, is_recoverable=False,
            )

        strategies: List[RepairStrategy] = []

        error_sig = self._error_signature(result)
        cached = self._pattern_cache.get(error_sig)
        if cached is not None:
            boosted = cached.model_copy(
                update={"confidence": min(1.0, cached.confidence + 0.1)},
            )
            strategies.append(boosted)

        if reflection.repair_strategy is not None:
            strategies.append(reflection.repair_strategy)

        fallback_strategy = await self._fallback_strategy(task, result, context)
        if fallback_strategy is not None:
            strategies.append(fallback_strategy)

        if self._llm_runtime is not None and len(strategies) < 2:
            llm_strategy = await self._llm_plan_repair(
                task, result, root_cause, context,
            )
            if llm_strategy is not None:
                strategies.append(llm_strategy)

        if not strategies:
            strategies.append(
                RepairStrategy(
                    strategy="Retry with same executor and parameters.",
                    suggested_executor=task.executor.value,
                    confidence=0.20,
                ),
            )

        strategies.sort(key=lambda s: s.confidence, reverse=True)

        seen: set[str] = set()
        deduped: List[RepairStrategy] = []
        for s in strategies:
            key = (s.suggested_executor or "", s.strategy[:50])
            if key not in seen:
                seen.add(key)
                deduped.append(s)

        return RepairPlan(
            root_cause=root_cause,
            is_recoverable=True,
            strategies=deduped[:self.MAX_REPAIR_STAGES],
        )

    async def _fallback_strategy(
        self,
        task: Task,
        result: ToolExecutionResult,
        context: Dict[str, Any],
    ) -> Optional[RepairStrategy]:
        """Ask ToolSelectionEngine for a fallback executor."""
        if self._tool_selector is None:
            return None

        description = (
            task.payload.get("instruction")
            or task.payload.get("command")
            or task.payload.get("query")
            or task.payload.get("prompt")
            or str(task.payload)
        )

        try:
            fallback = await self._tool_selector.select_fallback(
                failed_executor=task.executor,
                task_description=description,
                error=result.error or result.stderr or "Unknown error",
                context=context,
            )
            if fallback is not None and fallback.executor_type != task.executor:
                return RepairStrategy(
                    strategy=f"Switch to {fallback.executor_type.value}: {fallback.reasoning}",
                    suggested_executor=fallback.executor_type.value,
                    confidence=fallback.confidence * 0.9,
                )
        except Exception as e:
            logger.debug("Fallback selection failed: %s", e)

        return None

    async def _llm_plan_repair(
        self,
        task: Task,
        result: ToolExecutionResult,
        root_cause: str,
        context: Dict[str, Any],
    ) -> Optional[RepairStrategy]:
        """Use LLM to generate a repair strategy for complex failures."""
        if self._llm_runtime is None:
            return None

        try:
            from core.tools.llm_runtime import LlmRequest

            combined = " ".join(
                filter(None, [result.stderr or "", result.error or ""])
            )[:300]

            executors = ", ".join(e.value for e in ExecutorType)

            request = LlmRequest(
                prompt=(
                    "Suggest a repair strategy for this failed task.\n\n"
                    f"Task executor: {task.executor.value}\n"
                    f"Root cause: {root_cause}\n"
                    f"Error: {combined}\n"
                    f"Available executors: {executors}\n\n"
                    "Return a JSON object with:\n"
                    '- "strategy": one-sentence repair instruction\n'
                    '- "suggested_executor": executor name to use (or null for same)\n'
                    '- "confidence": float 0.0-1.0\n'
                    "Return ONLY valid JSON."
                ),
                system_prompt="You are a repair planning engine. Output ONLY valid JSON.",
                category="reasoning",
                max_tokens=150,
                temperature=0.0,
            )
            response = await self._llm_runtime.generate(request)
            if response.text and not response.error:
                import json

                text = response.text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                parsed = json.loads(text)
                return RepairStrategy(
                    strategy=parsed.get("strategy", "LLM-suggested repair"),
                    suggested_executor=parsed.get("suggested_executor"),
                    confidence=float(parsed.get("confidence", 0.5)),
                )
        except Exception as e:
            logger.debug("LLM repair planning failed: %s", e)

        return None

    # ── Stage 4: Multi-stage Retry with Escalation ──────────────────────────

    async def _execute_repair(
        self,
        task: Task,
        plan: RepairPlan,
        executors: Dict[ExecutorType, Any],
        context: Dict[str, Any],
        reflection: ReflectionOutput,
    ) -> RepairOutcome:
        """Execute repair strategies with escalation."""
        last_result: Optional[ToolExecutionResult] = None
        tried_executors: set[str] = {task.executor.value}
        attempts = 0

        for strategy in plan.strategies:
            attempts += 1

            target_executor_name = strategy.suggested_executor or task.executor.value
            try:
                target_executor_type = ExecutorType(target_executor_name)
            except ValueError:
                target_executor_type = task.executor

            executor = executors.get(target_executor_type)
            if executor is None:
                continue

            repair_task = self._build_repair_task(task, strategy, target_executor_type)

            logger.info(
                "Repair stage %d/%d for task %s: %s → %s (%s)",
                attempts, len(plan.strategies), task.id,
                task.executor.value, target_executor_type.value,
                strategy.strategy[:80],
            )

            start = time.perf_counter()
            try:
                result = await executor.execute(repair_task, context)
            except Exception as e:
                result = ToolExecutionResult(
                    task_id=task.id,
                    status="ERROR",
                    error=str(e),
                )
            latency = time.perf_counter() - start

            if self._tool_selector is not None:
                self._tool_selector.record_result(
                    target_executor_type,
                    result.status == "SUCCESS",
                    latency,
                )

            if result.status == "SUCCESS":
                self._learn_success(
                    task, reflection, strategy, target_executor_type,
                )
                return RepairOutcome(
                    result=result,
                    strategy_used=strategy,
                    attempts=attempts,
                    learned=True,
                )

            tried_executors.add(target_executor_type.value)
            last_result = result

        if last_result is None:
            last_result = ToolExecutionResult(
                task_id=task.id,
                status="ERROR",
                error="All repair strategies exhausted.",
            )

        return RepairOutcome(
            result=last_result,
            strategy_used=None,
            attempts=attempts,
            learned=False,
        )

    @staticmethod
    def _build_repair_task(
        original: Task,
        strategy: RepairStrategy,
        executor_type: ExecutorType,
    ) -> Task:
        """Create a modified task applying the repair strategy."""
        patched_payload = dict(original.payload)
        patched_payload.update(strategy.suggested_payload_patch)

        return original.model_copy(
            update={
                "executor": executor_type,
                "payload": patched_payload,
            },
        )

    # ── Stage 5: Learn From Failures ────────────────────────────────────────

    def _learn_success(
        self,
        task: Task,
        reflection: ReflectionOutput,
        strategy: RepairStrategy,
        repair_executor: ExecutorType,
    ) -> None:
        """Store a successful repair pattern for future recall."""
        category = reflection.failure_category or FailureCategory.UNKNOWN
        error_sig = reflection.failure_summary[:100] if reflection.failure_summary else ""

        record = RepairRecord(
            failure_category=category,
            error_signature=error_sig,
            original_executor=task.executor.value,
            repair_executor=repair_executor.value,
            strategy_used=strategy.strategy,
            success=True,
        )
        self._repair_history.append(record)

        if error_sig:
            self._pattern_cache[error_sig] = strategy

        logger.info(
            "Learned repair: %s → %s via %s (confidence %.2f)",
            task.executor.value, repair_executor.value,
            strategy.strategy[:60], strategy.confidence,
        )

    # ── Stage 6: Confidence / Performance Queries ───────────────────────────

    def get_repair_history(self) -> List[RepairRecord]:
        """Return all repair records for inspection/persistence."""
        return list(self._repair_history)

    def get_success_rate(self) -> float:
        """Overall repair success rate."""
        if not self._repair_history:
            return 0.0
        successes = sum(1 for r in self._repair_history if r.success)
        return successes / len(self._repair_history)

    def get_category_stats(self) -> Dict[str, Dict[str, int]]:
        """Per-category repair stats."""
        stats: Dict[str, Dict[str, int]] = {}
        for record in self._repair_history:
            cat = record.failure_category.value
            if cat not in stats:
                stats[cat] = {"attempts": 0, "successes": 0}
            stats[cat]["attempts"] += 1
            if record.success:
                stats[cat]["successes"] += 1
        return stats

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _error_signature(result: ToolExecutionResult) -> str:
        """Normalise error text into a stable cache key."""
        combined = " ".join(
            filter(None, [result.stderr or "", result.error or ""])
        )
        return combined[:100].strip()
