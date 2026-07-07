"""JARVIS OS - Cost Governor.

Tracks token consumption, daily API budgets, and enforces user approval thresholds using Decimal precision and SQLite/PostgreSQL billing logs.
"""

import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from sqlalchemy import func, select

from core.config import Settings
from core.exceptions import BudgetExceededError, JarvisSystemError
from core.memory.models import APIBillingLog


class CostGovernor:
    """Monitors token usage costs, logs usage to the DB, and checks limits with in-memory caching."""

    def __init__(self, settings: Settings, db_session: Optional[Any] = None) -> None:
        """Initialize CostGovernor.

        Args:
            settings: Settings configuration instance.
            db_session: Optional database session context.
        """
        self.settings = settings
        self.db_session = db_session

        # Cost limits as Decimal values
        self.daily_budget = Decimal("10.00")
        self.monthly_budget = Decimal("100.00")
        self.per_call_budget = Decimal("0.50")
        self.alert_threshold = Decimal("8.00")  # 80% daily budget alert boundary

        self.pricing: Dict[str, Tuple[Decimal, Decimal]] = {
            "gemini": (Decimal("0.0015"), Decimal("0.0075")),
            "claude": (Decimal("0.0015"), Decimal("0.0075")),
            "openai": (Decimal("0.0015"), Decimal("0.0075")),
            "qwen": (Decimal("0.0000"), Decimal("0.0000")),
            "llama": (Decimal("0.0000"), Decimal("0.0000")),
        }

        # In-memory cache for daily/monthly totals to optimize DB roundtrips
        self.last_cache_time = 0.0
        self.cache_ttl = 30.0  # seconds
        self.cached_daily_spending = Decimal("0.0")
        self.cached_monthly_spending = Decimal("0.0")

    def estimate_cost(self, text: str, provider_name: str) -> Decimal:
        """Calculate the estimated input token cost of a text block.

        Args:
            text: Context statement.
            provider_name: Target model provider name.

        Returns:
            Decimal estimated cost in USD.
        """
        # Standard token estimation: 1 word ~ 1.3 tokens
        tokens = int(len(text.split()) * 1.3)
        rates = self.pricing.get(
            provider_name.lower(), (Decimal("0.0"), Decimal("0.0"))
        )
        input_rate = rates[0]
        return (Decimal(tokens) / Decimal("1000.0")) * input_rate

    async def _get_current_spending(self) -> Tuple[Decimal, Decimal]:
        """Fetch daily and monthly spending totals, using cache if fresh."""
        now = time.time()
        if now - self.last_cache_time < self.cache_ttl:
            return self.cached_daily_spending, self.cached_monthly_spending

        if not self.db_session:
            # Fallback to in-memory cache values under mock testing without DB
            return self.cached_daily_spending, self.cached_monthly_spending

        # Compute today's and this month's starts (UTC)
        current_time = datetime.now(timezone.utc)
        today_start = datetime(
            current_time.year,
            current_time.month,
            current_time.day,
            tzinfo=timezone.utc,
        )
        month_start = datetime(
            current_time.year, current_time.month, 1, tzinfo=timezone.utc
        )

        # 1. Query daily total cost
        daily_stmt = select(func.sum(APIBillingLog.cost)).where(
            APIBillingLog.timestamp >= today_start
        )
        daily_res = await self.db_session.execute(daily_stmt)
        daily_sum = daily_res.scalar()
        self.cached_daily_spending = (
            Decimal(str(daily_sum)) if daily_sum is not None else Decimal("0.0")
        )

        # 2. Query monthly total cost
        monthly_stmt = select(func.sum(APIBillingLog.cost)).where(
            APIBillingLog.timestamp >= month_start
        )
        monthly_res = await self.db_session.execute(monthly_stmt)
        monthly_sum = monthly_res.scalar()
        self.cached_monthly_spending = (
            Decimal(str(monthly_sum)) if monthly_sum is not None else Decimal("0.0")
        )

        self.last_cache_time = now
        return self.cached_daily_spending, self.cached_monthly_spending

    async def check_budget_limits(self, estimated_cost: Decimal) -> None:
        """Verify that the estimated execution cost does not breach configured budgets.

        Args:
            estimated_cost: Projected request cost.

        Raises:
            BudgetExceededError: If budget is fully exhausted.
            JarvisSystemError: If the call is paused for approval.
        """
        daily, monthly = await self._get_current_spending()

        # 1. Monthly Budget Exhaustion
        if monthly + estimated_cost > self.monthly_budget:
            raise BudgetExceededError(
                code="BUDGET_MONTHLY_EXHAUSTED",
                message="Monthly API budget limits exceeded.",
            )

        # 2. Daily Budget Exhaustion
        if daily + estimated_cost > self.daily_budget:
            raise BudgetExceededError(
                code="BUDGET_DAILY_EXHAUSTED",
                message="Daily API budget limits exceeded.",
            )

        # 3. Per-Call Threshold Gating
        if estimated_cost > self.per_call_budget:
            raise JarvisSystemError(
                code="BUDGET_PER_CALL_EXCEEDED",
                message=f"Request cost ${estimated_cost:.4f} exceeds threshold. Awaiting user approval.",
            )

    async def log_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        provider_name: str,
        model_name: str = "",
    ) -> Decimal:
        """Accumulate token billing parameters to the active spending pools and persist to DB.

        Args:
            prompt_tokens: Input tokens count.
            completion_tokens: Output tokens count.
            provider_name: Target model provider name.
            model_name: Loaded model identifier.

        Returns:
            Calculated cost of this call.
        """
        rates = self.pricing.get(
            provider_name.lower(), (Decimal("0.0"), Decimal("0.0"))
        )
        input_cost = (Decimal(prompt_tokens) / Decimal("1000.0")) * rates[0]
        output_cost = (Decimal(completion_tokens) / Decimal("1000.0")) * rates[1]
        total_cost = input_cost + output_cost

        # Write APIBillingLog database entry
        if self.db_session:
            log_entry = APIBillingLog(
                id=uuid4(),
                timestamp=datetime.now(timezone.utc),
                provider_name=provider_name,
                model_name=model_name or provider_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=total_cost,
            )
            self.db_session.add(log_entry)
            await self.db_session.flush()

        # Update in-memory caches directly
        self.cached_daily_spending += total_cost
        self.cached_monthly_spending += total_cost

        return total_cost

    def reset_spending(self) -> None:
        """Reset active budget pools (useful for new test runs)."""
        self.cached_daily_spending = Decimal("0.0")
        self.cached_monthly_spending = Decimal("0.0")
        self.last_cache_time = 0.0
