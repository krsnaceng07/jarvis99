"""JARVIS OS - Execution Metrics Collector.

Observability component logging duration stats, success rates, retry frequencies,
and wait patterns across tool orchestration sessions.
"""

import asyncio
from typing import Dict


class ExecutionMetricsCollector:
    """Observability collector gathering metrics for tool executions, retries, and errors."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.metrics: Dict[str, float] = {
            "total_runs": 0.0,
            "success_runs": 0.0,
            "failed_runs": 0.0,
            "error_runs": 0.0,
            "retry_runs": 0.0,
            "timeout_runs": 0.0,
            "cancelled_runs": 0.0,
            "approval_wait_time_s": 0.0,
            "total_duration_s": 0.0,
        }

    async def log_run(self, duration_s: float, status: str) -> None:
        """Record the outcome and duration of a completed tool run.

        Args:
            duration_s: The execution duration in seconds.
            status: Outcome status string.
        """
        async with self.lock:
            self.metrics["total_runs"] += 1.0
            self.metrics["total_duration_s"] += duration_s

            if status == "SUCCESS":
                self.metrics["success_runs"] += 1.0
            elif status == "FAILURE":
                self.metrics["failed_runs"] += 1.0
            elif status == "ERROR":
                self.metrics["error_runs"] += 1.0
            elif status == "CANCELLED":
                self.metrics["cancelled_runs"] += 1.0

    async def log_retry(self) -> None:
        """Increment the counter of task retry executions."""
        async with self.lock:
            self.metrics["retry_runs"] += 1.0

    async def log_timeout(self) -> None:
        """Increment the counter of execution timeout occurrences."""
        async with self.lock:
            self.metrics["timeout_runs"] += 1.0

    async def log_approval_wait(self, duration_s: float) -> None:
        """Add time spent waiting for user approval.

        Args:
            duration_s: Time in seconds.
        """
        async with self.lock:
            self.metrics["approval_wait_time_s"] += duration_s

    async def get_report(self) -> Dict[str, float]:
        """Compile and retrieve a summary dashboard of current metrics.

        Returns:
            Dictionary containing metrics averages and ratios.
        """
        async with self.lock:
            total = self.metrics["total_runs"]
            avg_duration = (
                self.metrics["total_duration_s"] / total if total > 0.0 else 0.0
            )
            success_rate = self.metrics["success_runs"] / total if total > 0.0 else 0.0
            failure_rate = (
                (self.metrics["failed_runs"] + self.metrics["error_runs"]) / total
                if total > 0.0
                else 0.0
            )

            report = dict(self.metrics)
            report["avg_duration_s"] = avg_duration
            report["success_rate"] = success_rate
            report["failure_rate"] = failure_rate
            return report
