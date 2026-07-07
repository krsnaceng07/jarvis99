"""JARVIS OS - Token Counter.

Decouples token counting logic from the Cost Governor, allowing for custom multipliers or exact tokenizer extensions.
"""

from typing import Dict


class TokenCounter:
    """Estimates and counts token counts for given text blocks based on provider-specific weights."""

    def __init__(self) -> None:
        """Initialize TokenCounter."""
        # Standard token multipliers: 1 word ~ X tokens
        self.multipliers: Dict[str, float] = {
            "gemini": 1.3,
            "claude": 1.3,
            "openai": 1.4,
            "qwen": 1.4,
            "llama": 1.4,
        }

    def count_tokens(self, text: str, provider_name: str) -> int:
        """Return the estimated length of tokens for the given text.

        Args:
            text: Plain text content.
            provider_name: Target provider vendor name.

        Returns:
            Integer estimated token count.
        """
        multiplier = self.multipliers.get(provider_name.lower(), 1.3)
        # Handle empty/whitespace text safely
        words = text.split()
        if not words:
            return 0
        return int(len(words) * multiplier)
