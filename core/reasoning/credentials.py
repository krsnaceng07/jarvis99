"""JARVIS OS - Credentials Manager.

Manages credentials and keys for various LLM API providers.
"""

import os
from typing import Any, Optional


class CredentialManager:
    """Manages API keys and credential tokens retrieved from config or env variables."""

    def __init__(self, settings: Optional[Any] = None) -> None:
        """Initialize CredentialManager with optional Settings configuration."""
        self.settings = settings

    def get_api_key(self, provider_name: str) -> str:
        """Retrieve the API key for the specified provider name.

        Args:
            provider_name: Case-insensitive name of the model provider (e.g. 'gemini', 'claude', 'openai').

        Returns:
            The configured key string.
        """
        name = provider_name.upper()
        if name == "GEMINI":
            return (
                os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
                or "mock-gemini-key"
            )
        if name == "CLAUDE" or name == "ANTHROPIC":
            return (
                os.getenv("ANTHROPIC_API_KEY")
                or os.getenv("CLAUDE_API_KEY")
                or "mock-claude-key"
            )
        if name == "OPENAI":
            return os.getenv("OPENAI_API_KEY") or "mock-openai-key"

        # Local model providers like Qwen, Llama do not require key authorization by default
        return os.getenv(f"{name}_API_KEY") or ""
