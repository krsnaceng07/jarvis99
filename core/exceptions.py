"""JARVIS OS - Unified Error and Exception Standard.

Defines custom exception classes mapped to the system error code index.
"""

from typing import Any, Dict, Optional


class JarvisError(Exception):
    """Base exception for all errors in JARVIS OS."""

    def __init__(
        self, code: str, message: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Initialize the exception with a standard error code and message.

        Args:
            code: The unified system error code (e.g. 'SYSTEM_999').
            message: Descriptive error message.
            details: Optional dictionary containing additional diagnostic details.
        """
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.details = details or {}


class JarvisSystemError(JarvisError):
    """Exceptions originating from Kernel, Config, and Host environments."""


class JarvisMemoryError(JarvisError):
    """Exceptions originating from Database and Memory subsystems."""


class JarvisAgentError(JarvisError):
    """Exceptions originating from Agent, Planner, and message layers."""


class JarvisSkillError(JarvisError):
    """Exceptions originating from Skill execution and sandbox layers."""


class ModelProviderError(JarvisError):
    """Base exception for all model provider failures."""


class AuthenticationError(ModelProviderError):
    """Raised when API credentials or keys are invalid."""


class RateLimitError(ModelProviderError):
    """Raised when rate limits (RPM/TPM) are exceeded."""


class TimeoutError(ModelProviderError):
    """Raised when requests to a model provider time out."""


class BudgetExceededError(ModelProviderError):
    """Raised when spending limits are breached."""


class TransportError(ModelProviderError):
    """Raised when underlying network/connection issues occur."""


class InvalidResponseError(ModelProviderError):
    """Raised when response payloads are malformed or invalid."""
