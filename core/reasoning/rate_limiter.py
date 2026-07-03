"""JARVIS OS - Model Provider Rate Limiter.

Tracks Requests Per Minute (RPM), Tokens Per Minute (TPM), and concurrent requests for model providers.
"""

import time
from typing import Dict, List, Optional

from core.exceptions import RateLimitError


class ProviderRateLimiter:
    """Manages sliding window rate limits for each model provider."""

    def __init__(
        self,
        default_rpm: int = 60,
        default_tpm: int = 50000,
        default_max_concurrent: int = 5,
    ) -> None:
        """Initialize ProviderRateLimiter."""
        self.default_rpm = default_rpm
        self.default_tpm = default_tpm
        self.default_max_concurrent = default_max_concurrent

        # Provider configurations: provider_name -> {rpm, tpm, max_concurrent}
        self.configs: Dict[str, Dict[str, int]] = {}

        # In-memory sliding window timestamps: provider_name -> List[timestamp]
        self.request_timestamps: Dict[str, List[float]] = {}
        # In-memory sliding window tokens: provider_name -> List[(timestamp, token_count)]
        self.token_history: Dict[str, List[tuple[float, int]]] = {}
        # Active concurrent requests count: provider_name -> count
        self.concurrent_requests: Dict[str, int] = {}

    def configure_provider(
        self, provider_name: str, rpm: int, tpm: int, max_concurrent: int
    ) -> None:
        """Set specific rate limits for a model provider."""
        self.configs[provider_name.lower()] = {
            "rpm": rpm,
            "tpm": tpm,
            "max_concurrent": max_concurrent,
        }

    def _get_config(self, provider_name: str) -> Dict[str, int]:
        """Retrieve rate limits for the specified provider."""
        return self.configs.get(
            provider_name.lower(),
            {
                "rpm": self.default_rpm,
                "tpm": self.default_tpm,
                "max_concurrent": self.default_max_concurrent,
            },
        )

    def check_rate_limits(self, provider_name: str, estimated_tokens: int) -> None:
        """Verify provider does not exceed RPM, TPM, or concurrency limits.

        Args:
            provider_name: The name of the LLM provider.
            estimated_tokens: projected request token count.

        Raises:
            RateLimitError: If any of the limits are violated.
        """
        name = provider_name.lower()
        now = time.time()
        config = self._get_config(name)

        # 1. Check Concurrency Limit
        current_concurrent = self.concurrent_requests.get(name, 0)
        if current_concurrent >= config["max_concurrent"]:
            raise RateLimitError(
                code="RATE_LIMIT_CONCURRENT",
                message=f"Concurrency limit ({config['max_concurrent']}) exceeded for provider '{provider_name}'.",
            )

        # 2. Check RPM Limit (Requests in the last 60 seconds)
        timestamps = self.request_timestamps.get(name, [])
        # Prune older than 60 seconds
        timestamps = [ts for ts in timestamps if now - ts < 60]
        self.request_timestamps[name] = timestamps

        if len(timestamps) >= config["rpm"]:
            raise RateLimitError(
                code="RATE_LIMIT_RPM",
                message=f"RPM limit ({config['rpm']}) exceeded for provider '{provider_name}'.",
            )

        # 3. Check TPM Limit (Tokens in the last 60 seconds)
        tokens_log = self.token_history.get(name, [])
        # Prune older than 60 seconds
        tokens_log = [entry for entry in tokens_log if now - entry[0] < 60]
        self.token_history[name] = tokens_log

        total_tokens_last_min = sum(entry[1] for entry in tokens_log)
        if total_tokens_last_min + estimated_tokens > config["tpm"]:
            raise RateLimitError(
                code="RATE_LIMIT_TPM",
                message=f"TPM limit ({config['tpm']}) exceeded for provider '{provider_name}'. Current usage is {total_tokens_last_min} tokens.",
            )

    def record_request(self, provider_name: str, token_count: int) -> None:
        """Record a successful request initiation and token count in the sliding windows.

        Args:
            provider_name: Target provider name.
            token_count: Absolute consumed tokens.
        """
        name = provider_name.lower()
        now = time.time()

        if name not in self.request_timestamps:
            self.request_timestamps[name] = []
        self.request_timestamps[name].append(now)

        if name not in self.token_history:
            self.token_history[name] = []
        self.token_history[name].append((now, token_count))

    def increment_concurrent(self, provider_name: str) -> None:
        """Increment concurrency counter for provider."""
        name = provider_name.lower()
        self.concurrent_requests[name] = self.concurrent_requests.get(name, 0) + 1

    def decrement_concurrent(self, provider_name: str) -> None:
        """Decrement concurrency counter for provider."""
        name = provider_name.lower()
        current = self.concurrent_requests.get(name, 0)
        if current > 0:
            self.concurrent_requests[name] = current - 1

    def reset(self, provider_name: Optional[str] = None) -> None:
        """Reset limits (useful for testing and window expirations)."""
        if provider_name:
            name = provider_name.lower()
            self.request_timestamps[name] = []
            self.token_history[name] = []
            self.concurrent_requests[name] = 0
        else:
            self.request_timestamps.clear()
            self.token_history.clear()
            self.concurrent_requests.clear()
