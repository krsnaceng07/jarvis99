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

import time
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from core.reasoning.cost import CostGovernor
from core.reasoning.provider import IModelProvider
from core.reasoning.task import AgentTerminationReason


class LlmRequest(BaseModel):
    """Provider-agnostic LLM generation request DTO."""

    prompt: str = Field(..., description="User prompt or instruction.")
    system_prompt: Optional[str] = Field(
        default=None, description="System context instructions."
    )
    category: str = Field(
        default="reasoning",
        description="Task category for model routing (e.g. 'reasoning', 'coding').",
    )
    max_tokens: int = Field(default=1000, description="Maximum output tokens requested.")
    temperature: float = Field(default=0.0, description="Sampling temperature (0=deterministic).")


class LlmResponse(BaseModel):
    """Provider-agnostic LLM generation response DTO."""

    text: str = Field(default="", description="Generated text output.")
    provider_name: str = Field(default="", description="Name of the provider used.")
    model_name: str = Field(default="", description="Model identifier used.")
    prompt_tokens: int = Field(default=0, description="Estimated input token count.")
    completion_tokens: int = Field(default=0, description="Estimated output token count.")
    cost: Decimal = Field(default=Decimal("0.0"), description="Estimated cost in USD.")
    duration: float = Field(default=0.0, description="Wall-clock time in seconds.")
    termination_reason: Optional[AgentTerminationReason] = Field(
        default=None,
        description="Set when the call was blocked (e.g. BUDGET_EXCEEDED).",
    )
    error: Optional[str] = Field(default=None, description="Error message if call failed.")


class LlmRuntime:
    """Provider-agnostic LLM execution adapter.

    Architecture:
        Request → CostGovernor budget check → ModelRouter → IModelProvider → Response

    Constraints (Architect-mandated):
        - NEVER exposes provider-specific logic to callers.
        - ALL calls MUST pass through CostGovernor.check_budget_limits().
        - Interface is `generate(request: LlmRequest) -> LlmResponse` only.
    """

    def __init__(
        self,
        provider: IModelProvider,
        cost_governor: CostGovernor,
    ) -> None:
        """Initialise LlmRuntime.

        Args:
            provider: Any concrete IModelProvider (OpenAI, Claude, Gemini, etc.).
            cost_governor: CostGovernor instance for budget enforcement.
        """
        self.provider = provider
        self.cost_governor = cost_governor

    async def generate(self, request: LlmRequest) -> LlmResponse:
        """Execute a single LLM generation with budget gating.

        Flow:
            1. Estimate cost via CostGovernor.
            2. Check budget limits — raises BudgetExceededError if exceeded.
            3. Delegate to provider.generate().
            4. Log actual usage back to CostGovernor.
            5. Return unified LlmResponse.

        Args:
            request: LlmRequest DTO with prompt, category, and token limits.

        Returns:
            LlmResponse DTO — always returned; check .termination_reason for failures.
        """
        start_time = time.perf_counter()

        # 1. Estimate cost
        estimated_cost = self.cost_governor.estimate_cost(
            request.prompt, self.provider.name
        )

        # 2. CostGovernor budget gate (Architect Constraint 6)
        try:
            await self.cost_governor.check_budget_limits(estimated_cost)
        except Exception as budget_err:
            return LlmResponse(
                text="",
                provider_name=self.provider.name,
                model_name=self.provider.model_name,
                termination_reason=AgentTerminationReason.BUDGET_EXCEEDED,
                error=str(budget_err),
                duration=time.perf_counter() - start_time,
            )

        # 3. Delegate to provider (provider-specific details stay inside provider.py)
        try:
            text = await self.provider.generate(
                request.prompt, request.system_prompt
            )
        except Exception as provider_err:
            return LlmResponse(
                text="",
                provider_name=self.provider.name,
                model_name=self.provider.model_name,
                termination_reason=AgentTerminationReason.FAILED,
                error=str(provider_err),
                duration=time.perf_counter() - start_time,
            )

        duration = time.perf_counter() - start_time

        # 4. Estimate token counts
        prompt_tokens = self.provider.count_tokens(request.prompt)
        completion_tokens = self.provider.count_tokens(text)

        # 5. Log actual usage
        actual_cost = await self.cost_governor.log_usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            provider_name=self.provider.name,
            model_name=self.provider.model_name,
        )

        return LlmResponse(
            text=text,
            provider_name=self.provider.name,
            model_name=self.provider.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=actual_cost,
            duration=duration,
        )

    @property
    def provider_name(self) -> str:
        """Return the active provider name (read-only, no internal leak)."""
        return self.provider.name
