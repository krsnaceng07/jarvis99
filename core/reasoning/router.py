"""JARVIS OS - Model Router.

Selects the correct active model provider based on priority task categories, circuit breaker states, and capability scores.
"""

import asyncio
from typing import List, Optional

from core.config import Settings
from core.exceptions import JarvisSystemError, RateLimitError
from core.reasoning.cost import CostGovernor
from core.reasoning.provider import IModelProvider, ModelHealthStatus
from core.reasoning.rate_limiter import ProviderRateLimiter
from core.reasoning.registry import ModelCapabilityRegistry
from core.reasoning.telemetry import ReasoningTelemetry


class ModelRouter:
    """Resolves task suitability scores and routes to healthy model providers with automatic retry strategies."""

    def __init__(
        self,
        providers: List[IModelProvider],
        registry: ModelCapabilityRegistry,
        rate_limiter: ProviderRateLimiter,
        telemetry: ReasoningTelemetry,
        cost_gov: CostGovernor,
        settings: Settings,
    ) -> None:
        """Initialize ModelRouter."""
        self.providers = {p.name: p for p in providers}
        self.registry = registry
        self.rate_limiter = rate_limiter
        self.telemetry = telemetry
        self.cost_gov = cost_gov
        self.settings = settings

        # Default retry parameters
        self.max_retries = 3
        self.retry_backoffs = [1.0, 2.0, 4.0]

    async def get_provider_for_task(
        self, category: str, estimated_tokens: int = 0
    ) -> IModelProvider:
        """Determine the correct healthy model provider for the specified task category.

        Args:
            category: Target priority category (e.g. 'Planning', 'Coding').
            estimated_tokens: projected request token count.

        Returns:
            An active and healthy IModelProvider.

        Raises:
            JarvisSystemError: If all candidate providers are unhealthy or offline.
        """
        # Retrieve candidate names ranked by capability scores
        candidates = self.registry.get_best_providers_for_task(category)

        # Check if daily budget has already been exhausted
        budget_exhausted = False
        try:
            daily_spending, _ = await self.cost_gov._get_current_spending()
            if daily_spending >= self.cost_gov.daily_budget:
                budget_exhausted = True
        except Exception:
            pass

        # Filter candidates: if budget is exhausted, only allow local model providers (qwen, llama)
        if budget_exhausted:
            candidates = [
                name for name in candidates if name.lower() in ("qwen", "llama")
            ]

        for name in candidates:
            provider = self.providers.get(name.lower())
            if not provider:
                continue

            # Evaluate circuit breaker status
            status = await provider.health_check()
            if status not in (ModelHealthStatus.ONLINE, ModelHealthStatus.DEGRADED):
                await self.telemetry.publish_event(
                    "fallback",
                    provider.name,
                    provider.model_name,
                    {"reason": f"Provider in status: {status}"},
                )
                continue

            # Validate rate limit constraints
            try:
                self.rate_limiter.check_rate_limits(provider.name, estimated_tokens)
                return provider
            except RateLimitError as err:
                await self.telemetry.publish_event(
                    "fallback",
                    provider.name,
                    provider.model_name,
                    {"reason": f"Rate limits hit: {err.message}"},
                )
                continue

        # If all candidates for this category failed, fall back to any online local provider
        for provider in self.providers.values():
            if provider.name.lower() not in ("qwen", "llama"):
                continue
            status = await provider.health_check()
            if status in (ModelHealthStatus.ONLINE, ModelHealthStatus.DEGRADED):
                return provider

        raise JarvisSystemError(
            code="ROUTER_002",
            message="All configured model providers are currently OFFLINE, in COOLDOWN, or rate-limited.",
        )

    async def execute_with_retry(
        self,
        category: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        estimated_tokens: int = 0,
    ) -> str:
        """Dispatch generation requests to model providers under retry loops and circuit breaker guards."""
        attempts = 0
        while attempts <= self.max_retries:
            provider = await self.get_provider_for_task(category, estimated_tokens)

            # Check rate limits again in case of concurrent updates
            try:
                self.rate_limiter.check_rate_limits(provider.name, estimated_tokens)
            except RateLimitError:
                # If rate limits hit, try another provider or failover
                attempts += 1
                continue

            # Increment active concurrency counter
            self.rate_limiter.increment_concurrent(provider.name)
            await self.telemetry.publish_event(
                "started", provider.name, provider.model_name
            )

            start_time = asyncio.get_running_loop().time()
            try:
                response = await provider.generate(prompt, system_prompt)
                duration = asyncio.get_running_loop().time() - start_time

                # Record usage metrics
                out_tokens = provider.count_tokens(response)
                self.rate_limiter.record_request(
                    provider.name, estimated_tokens + out_tokens
                )

                await self.telemetry.publish_event(
                    "completed",
                    provider.name,
                    provider.model_name,
                    {"duration": duration, "output_tokens": out_tokens},
                )
                provider.record_success()
                return response

            except Exception as err:
                duration = asyncio.get_running_loop().time() - start_time
                provider.record_failure()

                action = "timeout" if "timeout" in str(err).lower() else "failed"
                await self.telemetry.publish_event(
                    action,
                    provider.name,
                    provider.model_name,
                    {"error": str(err), "duration": duration},
                )

                if attempts == self.max_retries:
                    raise

                # Retry backoff sleep
                backoff = self.retry_backoffs[
                    min(attempts, len(self.retry_backoffs) - 1)
                ]
                await self.telemetry.publish_event(
                    "retry",
                    provider.name,
                    provider.model_name,
                    {"attempt": attempts + 1, "backoff": backoff},
                )
                await asyncio.sleep(backoff)
                attempts += 1

            finally:
                self.rate_limiter.decrement_concurrent(provider.name)

        raise JarvisSystemError(
            code="ROUTER_RETRY_FAILED",
            message="LLM generation execution failed after max retries.",
        )
