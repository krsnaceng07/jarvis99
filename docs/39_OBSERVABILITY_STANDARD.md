# 39_OBSERVABILITY_STANDARD.md

## Purpose
This document defines the Observability Standard for JARVIS OS. It establishes requirements for logging integrations, tracer spans, heartbeats, and performance metrics gauges.

## Scope
Applies to all system processes, model API runners, database pools, browser adapters, and UI dashboard elements.

## Observability Standards & Telemetry Gauges
1. **Heartbeat Signal Policy:**
   - Every active agent service, daemon task, and supervisor must emit a heartbeat ping to Redis at a frequency of **every 10 seconds**.
   - If a heartbeat is missing for 30 seconds, the supervisor marks the component as offline and initiates self-healing (see `23_SELF_HEALING_POLICY.md`).
2. **Metrics Collection Targets:**
   - **System Metrics:** CPU usage, RAM footprint, disk I/O, database connection pool status.
   - **Agent Metrics:** Goal queue depth, task execution durations, token costs, active subagents.
   - **Errors Metrics:** Crash frequencies, HTTP error distributions, retry occurrences.
3. **Trace Spanning:** Every task lifecycle must be instrumented with spans tracking start, execution, validation, and completion.

## Responsibilities
- **Observability Daemon:** Gathers Redis metrics, formats payloads, and streams data to the UI dashboard.
- **System Supervisor:** Monitors daemon heartbeats and coordinates status changes.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- WebSocket API: `/ws/v1/telemetry/observability`.
- Metric endpoint: `/metrics` (Prometheus-compatible format).

## Examples
- **Correct Observability:** A worker agent finishes a tool call, updates its execution speed gauge, and updates its active heartbeat token in Redis.
- **Incorrect Observability:** A background process runs for hours, blocking execution threads, without logging telemetry, writing metrics, or emitting heartbeat signals. (Violates Modularity and Observability rules).

## Failure Cases
- **Metric Stream Congestion:** Monitoring payloads flood the WebSocket queue, causing UI latency. *Mitigation:* Observability metrics are aggregated on the backend and sent to the client at a throttled interval of every 2 seconds.

## Security Considerations
- Telemetry payloads must never include workspace code contents, file diffs, or database data values. Spans only track metadata keys and execution performance.

## Future Extension
- Modifications to monitoring dashboards or metric schemas require ADR entry updates.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [36_OBSERVABILITY_STANDARD.md](file:///e:/jarvis/docs/36_OBSERVABILITY_STANDARD.md)
- [37_LOGGING_STANDARD.md](file:///e:/jarvis/docs/37_LOGGING_STANDARD.md)
- [73_HEALTH_MONITORING.md](file:///e:/jarvis/docs/73_HEALTH_MONITORING.md)
