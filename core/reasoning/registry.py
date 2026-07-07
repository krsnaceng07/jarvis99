"""JARVIS OS - Model Capability Registry.

Maintains model configuration DTOs, task suitability scores, and capability details for routing decisions.
"""

from typing import Dict, List, Optional

from core.reasoning.provider import ProviderConfig


class ModelCapabilityRegistry:
    """Registry maintaining metadata and capability rankings for all model providers."""

    def __init__(self) -> None:
        """Initialize ModelCapabilityRegistry."""
        # Maps provider name to its ProviderConfig
        self.configs: Dict[str, ProviderConfig] = {}

        # Capability scores: task_category -> Dict[provider_name, score]
        # Scoring scale: 0 (completely incapable) to 100 (excellent suitability)
        self.capability_scores: Dict[str, Dict[str, int]] = {
            "Planning": {
                "claude": 95,
                "gemini": 90,
                "openai": 88,
                "qwen": 60,
                "llama": 50,
            },
            "Coding": {
                "claude": 96,
                "openai": 92,
                "qwen": 85,
                "gemini": 82,
                "llama": 70,
            },
            "Vision": {
                "claude": 95,
                "gemini": 90,
                "openai": 88,
                "qwen": 0,
                "llama": 0,
            },
            "Summarization": {
                "gemini": 95,
                "llama": 85,
                "openai": 80,
                "claude": 80,
                "qwen": 78,
            },
            "Tool Calling": {
                "llama": 90,
                "gemini": 85,
                "openai": 85,
                "claude": 85,
                "qwen": 80,
            },
        }

    def register_provider_config(self, config: ProviderConfig) -> None:
        """Register a provider config DTO into the registry."""
        self.configs[config.provider_name.lower()] = config

    def get_provider_config(self, provider_name: str) -> Optional[ProviderConfig]:
        """Retrieve config DTO for target provider."""
        return self.configs.get(provider_name.lower())

    def get_best_providers_for_task(
        self, task_category: str, require_vision: bool = False
    ) -> List[str]:
        """Rank and return candidate provider names for a task based on suitability scores.

        Args:
            task_category: The target task (e.g. 'Planning', 'Coding').
            require_vision: Whether vision support is strictly required.

        Returns:
            Sorted list of provider names from highest score to lowest.
        """
        category_scores = self.capability_scores.get(task_category, {})
        if not category_scores:
            return list(self.configs.keys())

        # Sort candidate names by score descending
        sorted_candidates = sorted(
            category_scores.keys(), key=lambda k: category_scores[k], reverse=True
        )

        # Filter candidates based on vision requirements and registration existence
        filtered = []
        for name in sorted_candidates:
            config = self.configs.get(name.lower())
            if not config:
                continue
            if require_vision and not config.supports_vision:
                continue
            filtered.append(name)

        return filtered
