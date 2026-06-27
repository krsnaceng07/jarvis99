"""JARVIS OS - Runtime Foundation and Observability Unit Tests.

Verifies JSON logs formatting, ContextVars injection, Metrics registry, and Health monitoring.
"""

import asyncio
import io
import json
import sys

import pytest

from core.health import HealthMonitor
from core.logger import configure_logging, get_logger, request_id_var, trace_id_var
from core.metrics import MetricsRegistry
from core.version import VERSION


def test_version_meta() -> None:
    """Verify version details map correctly."""
    assert VERSION == "0.1.0"


def test_structured_json_logging() -> None:
    """Verify logs are outputted as structured JSON containing trace correlation variables."""
    # Capture standard output
    captured_output = io.StringIO()
    sys.stdout = captured_output

    try:
        configure_logging(level="DEBUG")
        logger = get_logger("test.json_logger")

        # Set trace context
        trace_id_var.set("trace-123-abc")
        request_id_var.set("req-456-def")

        logger.info("Test message log output.")

    finally:
        sys.stdout = sys.__stdout__

    output_lines = captured_output.getvalue().strip().split("\n")
    assert len(output_lines) >= 1

    # Verify JSON structure
    log_json = json.loads(output_lines[-1])
    assert log_json["level"] == "INFO"
    assert log_json["message"] == "Test message log output."
    assert log_json["trace_id"] == "trace-123-abc"
    assert log_json["request_id"] == "req-456-def"
    assert "timestamp" in log_json


def test_metrics_registry() -> None:
    """Verify counters, gauges, and histograms are correctly cataloged."""
    registry = MetricsRegistry()

    # Counter
    registry.increment("api_requests_total")
    registry.increment("api_requests_total", 5, labels={"status": "success"})
    metrics = registry.get_metrics()
    assert metrics["counters"]["api_requests_total"] == 1
    assert metrics["counters"]["api_requests_total{status=success}"] == 5

    # Gauge
    registry.set_gauge("active_connections", 42.0)
    metrics = registry.get_metrics()
    assert metrics["gauges"]["active_connections"] == 42.0

    # Histogram
    registry.observe("query_latency_seconds", 0.045)
    registry.observe("query_latency_seconds", 0.055)
    metrics = registry.get_metrics()
    assert metrics["histograms"]["query_latency_seconds"]["count"] == 2
    assert metrics["histograms"]["query_latency_seconds"]["avg"] == 0.050

    # Reset
    registry.reset()
    metrics = registry.get_metrics()
    assert not metrics["counters"]
    assert not metrics["gauges"]
    assert not metrics["histograms"]


@pytest.mark.asyncio
async def test_health_monitor_lifecycle() -> None:
    """Verify health monitor updates heartbeat counters and tracks resources."""
    monitor = HealthMonitor(check_interval=0.01)
    await monitor.initialize()
    await monitor.start()

    # Allow polling task to execute at least once
    await asyncio.sleep(0.03)

    health_data = await monitor.check_health()
    assert health_data["heartbeats"] >= 1
    assert health_data["connectivity"]["database"] == "OK"
    assert health_data["resources"]["disk_percent"] >= 0.0

    # Verify status degrade when connectivity fails
    monitor.set_connectivity_status(db_ok=False, redis_ok=True)
    degraded_data = await monitor.check_health()
    assert degraded_data["status"] == "degraded"
    assert degraded_data["connectivity"]["database"] == "ERROR"

    await monitor.stop()
    await monitor.shutdown()
