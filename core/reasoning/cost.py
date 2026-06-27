"""JARVIS OS - Cost Governor.

Tracks token consumption, daily API budgets, and enforces user approval thresholds for expensive requests.
"""

from typing import Dict

from core.config import Settings
from core.exceptions import JarvisSystemError


class CostGovernor:
    """Monitors token usage costs and handles budget exhaustion overrides."""

    def __init__(self, settings: Settings) -> None:
        """Initialize CostGovernor.

        Args:
            settings: Settings configuration instance.
        """
        self.settings = settings
        self.daily_spending = 0.0
        self.monthly_spending = 0.0

        # Budget variables loaded from settings or defaults
        self.daily_budget = 10.00
        self.monthly_budget = 100.00
        self.per_call_budget = 0.50

        # Model pricing weights per 1000 tokens (input, output)
        self.pricing: Dict[str, tuple[float, float]] = {
            "gemini": (0.0015, 0.0075),
            "claude": (0.0015, 0.0075),
            "openai": (0.0015, 0.0075),
            "qwen": (0.0, 0.0),
            "llama": (0.0, 0.0),
        }

    def estimate_cost(self, text: str, provider_name: str) -> float:
        """Calculate the estimated input token cost of a text block.

        Args:
            text: Context statement.
            provider_name: Target model provider name.

        Returns:
            Float estimated cost in USD.
        """
        # Standard token estimation: 1 word ~ 1.3 tokens
        tokens = int(len(text.split()) * 1.3)
        rates = self.pricing.get(provider_name.lower(), (0.0, 0.0))
        input_rate = rates[0]
        return (tokens / 1000.0) * input_rate

    def check_budget_limits(self, estimated_cost: float) -> None:
        """Verify that the estimated execution cost does not breach configured budgets.

        Args:
            estimated_cost: Projected request cost.

        Raises:
            JarvisSystemError: If budget is fully exhausted or the call is paused for approval.
        """
        # 1. Monthly Budget Exhaustion
        if self.monthly_spending + estimated_cost > self.monthly_budget:
            raise JarvisSystemError(
                code="BUDGET_001",
                message="Monthly API budget limits exceeded.",
            )

        # 2. Daily Budget Exhaustion
        if self.daily_spending + estimated_cost > self.daily_budget:
            raise JarvisSystemError(
                code="BUDGET_002",
                message="Daily API budget limits exceeded.",
            )

        # 3. Per-Call Threshold Gating ($0.50 USD limit)
        if estimated_cost > self.per_call_budget:
            raise JarvisSystemError(
                code="BUDGET_003",
                message=f"Request cost ${estimated_cost:.4f} exceeds threshold. Awaiting user approval.",
            )

    def log_usage(
        self, prompt_tokens: int, completion_tokens: int, provider_name: str
    ) -> float:
        """Accumulate token billing parameters to the active spending pools.

        Args:
            prompt_tokens: Input tokens count.
            completion_tokens: Output tokens count.
            provider_name: Target model provider name.

        Returns:
            Calculated cost of this call.
        """
        rates = self.pricing.get(provider_name.lower(), (0.0, 0.0))
        input_cost = (prompt_tokens / 1000.0) * rates[0]
        output_cost = (completion_tokens / 1000.0) * rates[1]
        total_cost = input_cost + output_cost

        self.daily_spending += total_cost
        self.monthly_spending += total_cost
        return total_cost

    def reset_spending(self) -> None:
        """Reset active budget pools (useful for new test runs)."""
        self.daily_spending = 0.0
        self.monthly_spending = 0.0
