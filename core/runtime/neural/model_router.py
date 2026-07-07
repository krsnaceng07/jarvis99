"""
PHASE: 37
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/PHASE_37_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes cognitive tasks and queries to appropriate LLM providers."""

    def __init__(self, legacy_router: Optional[Any] = None) -> None:
        """Initialize ModelRouter with optional legacy router integration."""
        self.legacy_router = legacy_router
        self._providers: Dict[str, Any] = {}

    def register_provider(self, name: str, provider: Any) -> None:
        """Register a new LLM provider model endpoint."""
        self._providers[name] = provider
        logger.info("Registered provider in ModelRouter: %s", name)

    async def route_query(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        provider_preference: Optional[str] = None,
    ) -> str:
        """Route prompt query to the appropriate LLM provider and return response text."""
        logger.info("Routing query. Preference: %s", provider_preference)

        # If a legacy router is available, delegate execution to leverage existing LLM clients
        if self.legacy_router:
            try:
                res = await self.legacy_router.route_request(prompt, system_instruction)
                return str(res)
            except Exception as e:
                logger.warning(
                    "Legacy router routing failed: %s. Falling back.", str(e)
                )

        # Use registered providers directly
        provider = None
        if provider_preference and provider_preference in self._providers:
            provider = self._providers[provider_preference]
        elif self._providers:
            provider = next(iter(self._providers.values()))

        if provider is not None:
            try:
                result = await provider.generate(prompt, system_instruction)
                return str(result)
            except Exception as e:
                logger.warning("Provider call failed: %s. Using fallback.", str(e))

        # Fallback dummy response for testing and offline environments
        return f"Mocked response for query: {prompt[:30]}..."
