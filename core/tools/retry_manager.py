"""JARVIS OS - Task Retry Manager.

Implements execution retries with configurable exponential backoff delays,
retryable error matching, and telemetry publishing.
"""

import asyncio
from typing import Awaitable, Callable, Optional

from core.tools.dto import RetryPolicy, ToolExecutionResult
from core.tools.metrics_collector import ExecutionMetricsCollector


class RetryManager:
    """Wrapper executor applying exponential backoff retry policies to tool invocations."""

    async def execute_with_retry(
        self,
        task_fn: Callable[[], Awaitable[ToolExecutionResult]],
        policy: Optional[RetryPolicy],
        metrics_collector: Optional[ExecutionMetricsCollector] = None,
        event_publisher_fn: Optional[
            Callable[[str, ToolExecutionResult], Awaitable[None]]
        ] = None,
    ) -> ToolExecutionResult:
        """Run the provided execution callable, applying retries if configured and matchable.

        Args:
            task_fn: Async callable that runs the tool execution.
            policy: RetryPolicy DTO.
            metrics_collector: Metrics collector instance.
            event_publisher_fn: Async callback to publish events to event bus.

        Returns:
            The final ToolExecutionResult.
        """
        # Default policy fallback
        p = policy or RetryPolicy(max_retries=0)
        attempts = 0
        current_delay = p.delay

        while True:
            try:
                res: ToolExecutionResult = await task_fn()

                # Success status requires no retries
                if res.status == "SUCCESS":
                    return res

                # Check if retryable failure based on attempts and status code/error signature
                if attempts >= p.max_retries:
                    return res

                # Determine if error is retryable
                is_retryable = True
                if p.retryable_errors and res.error:
                    is_retryable = any(err in res.error for err in p.retryable_errors)

                if not is_retryable:
                    return res

            except Exception as err:
                if attempts >= p.max_retries:
                    raise err

                is_retryable = True
                if p.retryable_errors:
                    is_retryable = any(err in str(err) for err in p.retryable_errors)

                if not is_retryable:
                    raise err

                res = ToolExecutionResult(
                    status="ERROR",
                    stdout="",
                    stderr=str(err),
                    exit_code=-1,
                    error=str(err),
                )

            # Apply delay and retry
            attempts += 1
            if metrics_collector:
                await metrics_collector.log_retry()

            if event_publisher_fn:
                # Trigger tool.retry event notification
                await event_publisher_fn("tool.retry", res)

            await asyncio.sleep(current_delay)
            current_delay *= p.backoff_multiplier
