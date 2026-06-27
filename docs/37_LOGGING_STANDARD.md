# 37_LOGGING_STANDARD.md

## Purpose
This document defines the Logging Standard for JARVIS OS. It establishes the log levels, JSON payload formats, correlation tracing IDs, and metadata rules for the system.

## Scope
Applies to all backend services, sandbox executors, custom plugins, CLI wrappers, and UI clients.

## Logging Standards & Log Levels
1. **Structured JSON Logging:** All log outputs must be written as single-line JSON structures to support easy indexing and analysis by self-healing engines:
```json
{
  "timestamp": "2026-06-26T22:30:00Z",
  "level": "INFO",
  "trace_id": "uuid-string",
  "span_id": "uuid-string",
  "module": "core.brain.planner",
  "message": "Planning completed.",
  "context": {}
}
```
2. **Log Levels:**
   - `DEBUG`: Verbose developer logs (only active in development profile).
   - `INFO`: Normal system occurrences (state changes, task updates).
   - `WARNING`: Handled exceptions, configuration anomalies, slow responses.
   - `ERROR`: Unhandled exceptions, failed subtasks, execution drops.
   - `CRITICAL`: Security boundary escapes, vault key failures, resource exhaustion.
3. **Correlation ID Standard:** Every request, task execution, and agent workflow must generate a unique `trace_id`. This ID must propagate across all sub-agents and database entries to compile clean stack traces.

## Responsibilities
- **Logging Engine Manager:** Writes logs to standard output, saves historical logs to PostgreSQL, and aggregates telemetry.
- **Developer Agent:** Injects log statements containing relevant context variables inside all written modules.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 10 and Rule 13).

## Interfaces
- Logging Wrapper API: `jarvis.core.logger.get_logger()`.

## Examples
- **Correct Log Entry:** Outputting a JSON string containing the level, a correlation ID, and an execution duration variable.
- **Incorrect Log Entry:** Printing a raw text string `print("Database connected")` to the console without context, timestamp, or logging levels. (Violates Structured JSON Logging).

## Failure Cases
- **Disk Space Exhaustion:** Heavy subtask loops generate massive log payloads. *Mitigation:* Log files are rotated automatically when they reach 50MB, and logs older than 7 days are archived and compressed.

## Security Considerations
- Logs must never contain credentials, decrypted secrets, passwords, or personal user tokens. The Logging Engine dynamically filters out sensitive keys before outputting JSON blocks.

## Future Extension
- Enhancements to log routing systems (e.g. OpenTelemetry integration) are managed through ADR updates.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [32_LOGGING_STANDARD.md](file:///e:/jarvis/docs/32_LOGGING_STANDARD.md)
- [39_OBSERVABILITY_STANDARD.md](file:///e:/jarvis/docs/39_OBSERVABILITY_STANDARD.md)
