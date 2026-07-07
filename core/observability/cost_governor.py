"""
PHASE: 27
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/89_PHASE_27_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

CostGovernor — enforces daily LLM API budget constraints per docs/65_COST_GOVERNOR.md.

Architect constraints incorporated:
- C2: Never blocks the EventBus — budget evaluation is fire-and-forget (non-blocking).
  If the governor is unavailable: log, continue. Execution must never stall.
- C7: BudgetSummary includes both daily AND monthly totals.

Integration: ObservabilityService subscribes to 'llm.response' events (Option C approved)
and calls record_usage(). No frozen LlmRuntime is modified.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from core.observability.budget_repository import BudgetRepository
from core.observability.dto import BudgetSummary, CostDecision

logger = logging.getLogger("jarvis.core.observability.cost_governor")

# ---------------------------------------------------------------------------
# Model pricing configuration (Architect constraint — stored in configurable map)
# ---------------------------------------------------------------------------

#: USD cost per 1,000 tokens. Configurable; never fetched from a live API.
MODEL_PRICING_USD_PER_1K_TOKENS: Dict[str, Dict[str, float]] = {
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4-turbo": {"input": 0.010, "output": 0.030},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
    "local": {"input": 0.0, "output": 0.0},  # Ollama / vLLM
}

#: Default model pricing when model is unknown
_FALLBACK_PRICING: Dict[str, float] = {"input": 0.005, "output": 0.015}

# Default budget limits (overridden by settings)
_DEFAULT_DAILY_LIMIT_USD: float = 10.0
_DEFAULT_WARN_THRESHOLD_USD: float = 8.0
_DEFAULT_PER_CALL_BLOCK_USD: float = 0.50


class CostGovernor:
    """Enforces daily LLM API budget constraints per docs/65_COST_GOVERNOR.md.

    Budget tiers (Architect-approved):
      - ALLOW    : daily cost < 80% of limit — proceed normally
      - WARN     : 80–100% of limit — alert raised, proceed
      - BLOCK    : single call estimated cost > $0.50 — log, proceed
      - FAILOVER : daily limit exhausted — callers should route to local model

    Architect constraint C2: record_usage() and estimate_cost() are non-blocking.
    All DB writes are dispatched as fire-and-forget background tasks.
    If the governor errors, callers MUST log and continue — never stall.
    """

    def __init__(
        self,
        budget_repository: BudgetRepository,
        daily_limit_usd: float = _DEFAULT_DAILY_LIMIT_USD,
        warn_threshold_usd: float = _DEFAULT_WARN_THRESHOLD_USD,
        per_call_block_usd: float = _DEFAULT_PER_CALL_BLOCK_USD,
    ) -> None:
        self._repo = budget_repository
        self._daily_limit = daily_limit_usd
        self._warn_threshold = warn_threshold_usd
        self._per_call_block = per_call_block_usd

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> CostDecision:
        """Accumulate token usage for today and return current CostDecision tier.

        Architect constraint C2: DB write is fire-and-forget. Returns decision
        immediately without waiting for persistence to complete.
        """
        cost = self._calculate_cost(model, input_tokens, output_tokens)
        today = _today()

        # Pre-call single-request BLOCK check
        if cost > self._per_call_block:
            logger.warning(
                "Single-call cost $%.4f exceeds per-call limit $%.2f (model=%s)",
                cost,
                self._per_call_block,
                model,
            )
            # Still persist, but return BLOCK decision
            self._fire_and_forget_upsert(
                today, model, input_tokens, output_tokens, cost
            )
            return CostDecision.BLOCK

        self._fire_and_forget_upsert(today, model, input_tokens, output_tokens, cost)

        # Evaluate daily tier (using latest DB totals)
        try:
            daily_total = await self._repo.get_daily_total(today)
            return self._evaluate_tier(daily_total + cost)
        except Exception as exc:
            # Architect constraint C2: never stall — log and continue
            logger.warning("CostGovernor tier evaluation failed (non-fatal): %s", exc)
            return CostDecision.ALLOW

    async def estimate_cost(self, model: str, estimated_tokens: int) -> float:
        """Pre-call cost estimation in USD for a given token count.

        Assumes 50/50 input/output split for estimation purposes.
        """
        half = estimated_tokens // 2
        return self._calculate_cost(model, half, half)

    async def get_daily_summary(self) -> BudgetSummary:
        """Return current daily+monthly cost summary with tier classification.

        Architect constraint C7: returns both daily and monthly totals.
        """
        return await self._repo.get_summary(
            date=_today(),
            daily_limit_usd=self._daily_limit,
            warn_threshold_usd=self._warn_threshold,
        )

    # ------------------------------------------------------------------
    # Event bus handler (called by ObservabilityService)
    # ------------------------------------------------------------------

    async def on_llm_response_event(self, event_body: Dict[str, Any]) -> None:
        """Handle an llm.response event from the event bus.

        Extracts model, input_tokens, output_tokens from the event payload
        and calls record_usage(). Errors are logged-and-dropped per C2.
        """
        try:
            model = str(event_body.get("model", "unknown"))
            input_tokens = int(event_body.get("input_tokens", 0))
            output_tokens = int(event_body.get("output_tokens", 0))
            decision = await self.record_usage(model, input_tokens, output_tokens)
            if decision in (CostDecision.WARN, CostDecision.FAILOVER):
                logger.warning(
                    "Budget tier elevated: %s (model=%s in=%d out=%d)",
                    decision.value,
                    model,
                    input_tokens,
                    output_tokens,
                )
        except Exception as exc:
            # Architect constraint C2: must never stall EventBus
            logger.warning(
                "CostGovernor.on_llm_response_event error (ignored): %s", exc
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate USD cost for a model call."""
        pricing = MODEL_PRICING_USD_PER_1K_TOKENS.get(model, _FALLBACK_PRICING)
        input_cost = (input_tokens / 1000.0) * pricing.get("input", 0.0)
        output_cost = (output_tokens / 1000.0) * pricing.get("output", 0.0)
        return input_cost + output_cost

    def _evaluate_tier(self, cumulative_cost: float) -> CostDecision:
        """Determine budget tier from cumulative daily cost."""
        if cumulative_cost >= self._daily_limit:
            return CostDecision.FAILOVER
        if cumulative_cost >= self._warn_threshold:
            return CostDecision.WARN
        return CostDecision.ALLOW

    def _fire_and_forget_upsert(
        self,
        date: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost: float,
    ) -> None:
        """Dispatch DB upsert as a non-blocking background task.

        Architect constraint C2: caller is never blocked by persistence.
        """

        async def _persist() -> None:
            try:
                await self._repo.upsert_ledger(date, model, tokens_in, tokens_out, cost)
            except Exception as exc:
                logger.warning("Budget ledger upsert failed (non-fatal): %s", exc)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_persist())
        except RuntimeError:
            logger.warning("No running event loop — budget record not persisted")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today() -> str:
    """Return current UTC date string as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
