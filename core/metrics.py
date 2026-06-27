"""JARVIS OS - Performance and Execution Metrics.

Independent module for tracking system-wide counters, gauges, and performance telemetry.
"""

from typing import Any, Dict, List, Optional


class MetricsRegistry:
    """Registry maintaining active runtime performance indicators, counters, and execution metrics."""

    def __init__(self) -> None:
        """Initialize empty metrics storage maps."""
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}

    def increment(
        self, name: str, value: int = 1, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Increment a counter metric.

        Args:
            name: The metric name.
            value: Increment offset step.
            labels: Optional dimensional labels.
        """
        metric_key = self._format_key(name, labels)
        self._counters[metric_key] = self._counters.get(metric_key, 0) + value

    def set_gauge(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Set a gauge metric value.

        Args:
            name: The metric name.
            value: The direct value.
            labels: Optional dimensional labels.
        """
        metric_key = self._format_key(name, labels)
        self._gauges[metric_key] = value

    def observe(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Observe a value in a histogram/distribution (e.g. latency duration).

        Args:
            name: The metric name.
            value: The observed numeric quantity.
            labels: Optional dimensional labels.
        """
        metric_key = self._format_key(name, labels)
        if metric_key not in self._histograms:
            self._histograms[metric_key] = []
        self._histograms[metric_key].append(value)

    def get_metrics(self) -> Dict[str, Any]:
        """Compile a snapshot copy of all recorded metrics.

        Returns:
            Dict containing counters, gauges, and summary histograms.
        """
        histograms_summary = {}
        for k, values in self._histograms.items():
            if not values:
                continue
            histograms_summary[k] = {
                "count": len(values),
                "sum": sum(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
            }

        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": histograms_summary,
        }

    def reset(self) -> None:
        """Reset all metric records to initial empty state."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()

    def _format_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Format metric name and labels into unique trace key string."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
