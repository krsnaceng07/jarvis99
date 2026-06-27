"""JARVIS OS - Model Router.

Selects the correct active model provider based on priority task categories and circuit breaker states.
"""

from typing import Dict, List

from core.config import Settings
from core.exceptions import JarvisSystemError
from core.reasoning.provider import IModelProvider, ModelHealthStatus


class ModelRouter:
    """Resolves task priority mappings and routes to healthy model providers with automatic cooldown failover."""

    def __init__(self, providers: List[IModelProvider], settings: Settings) -> None:
        """Initialize ModelRouter.

        Args:
            providers: List of instantiated model providers.
            settings: Settings configuration instance.
        """
        self.providers = {p.name: p for p in providers}
        self.settings = settings

        # Priority matrix mapping categories to list of fallback provider names
        self.priority_matrix: Dict[str, List[str]] = {
            "Vision": ["gemini", "claude", "openai"],
            "Coding": ["claude", "openai", "qwen"],
            "Planning": ["claude", "gemini", "openai"],
            "Reasoning": ["claude", "gemini", "openai"],
            "Tool Calling": ["llama", "gemini", "openai"],
            "Summarization": ["gemini", "llama", "openai"],
            "Chat": ["llama", "openai"],
        }

    async def get_provider_for_task(self, category: str) -> IModelProvider:
        """Determine the correct healthy model provider for the specified task category.

        Args:
            category: Target priority category.

        Returns:
            An active and healthy IModelProvider.

        Raises:
            JarvisSystemError: If all candidate providers are unhealthy or offline.
        """
        candidates = self.priority_matrix.get(category)
        if not candidates:
            # Fallback to first available provider
            if self.providers:
                return next(iter(self.providers.values()))
            raise JarvisSystemError(
                code="ROUTER_001",
                message="No model providers configured in system.",
            )

        for provider_name in candidates:
            provider = self.providers.get(provider_name)
            if not provider:
                continue

            # Evaluate circuit breaker health status
            status = await provider.health_check()
            if status in (ModelHealthStatus.ONLINE, ModelHealthStatus.DEGRADED):
                return provider

        # If all candidates for this category failed, fall back to any online provider
        for provider in self.providers.values():
            status = await provider.health_check()
            if status in (ModelHealthStatus.ONLINE, ModelHealthStatus.DEGRADED):
                return provider

        raise JarvisSystemError(
            code="ROUTER_002",
            message="All configured model providers are currently OFFLINE or in COOLDOWN.",
        )
