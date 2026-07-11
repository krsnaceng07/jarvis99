"""
PHASE: 39
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/101_PHASE_39_WORKFLOW_GRAPH_ENGINE_SPECIFICATION.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetryPolicy:
    """Configurable retry/backoff policy for workflow step execution.

    Invariant W-3: RetryPolicy is stateless. It decides retry eligibility,
    delay, and attempt limits only. It never modifies workflow state or
    execution metadata.
    """

    max_attempts: int = 3
    backoff_seconds: float = 1.0
    retryable_errors: List[str] = field(default_factory=list)

    def is_retryable(self, exc: Exception) -> bool:
        """Return True if the exception type name is in retryable_errors.

        An empty retryable_errors list means all exceptions are retryable.
        """
        if not self.retryable_errors:
            return True
        exc_name = type(exc).__name__
        return exc_name in self.retryable_errors

    def backoff_delay(self, attempt: int) -> float:
        """Return exponential backoff delay for the given attempt number (0-indexed)."""
        return self.backoff_seconds * (2**attempt)

    async def execute_with_retry(
        self,
        fn: Callable[[], Any],
        context: Optional[str] = None,
    ) -> Any:
        """Run fn with exponential backoff up to max_attempts.

        Args:
            fn:      Zero-argument async or sync callable to execute.
            context: Optional label for log messages.

        Raises:
            The last exception if all attempts are exhausted.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_attempts):
            try:
                result = fn()
                if asyncio.iscoroutine(result):
                    return await result
                return result
            except Exception as exc:
                last_exc = exc
                if not self.is_retryable(exc):
                    logger.warning(
                        "RetryPolicy: non-retryable error on attempt %d/%d [%s]: %s",
                        attempt + 1,
                        self.max_attempts,
                        context or "unknown",
                        exc,
                    )
                    raise

                if attempt + 1 < self.max_attempts:
                    delay = self.backoff_delay(attempt)
                    logger.warning(
                        "RetryPolicy: attempt %d/%d failed [%s]: %s — retrying in %.1fs",
                        attempt + 1,
                        self.max_attempts,
                        context or "unknown",
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "RetryPolicy: all %d attempts exhausted [%s]: %s",
                        self.max_attempts,
                        context or "unknown",
                        exc,
                    )

        assert last_exc is not None
        raise last_exc
