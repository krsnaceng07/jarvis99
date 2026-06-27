# 40_PERFORMANCE_STANDARD.md

## Purpose
This document defines the Performance Standard for JARVIS OS. It establishes limits for latency thresholds, memory footprints, API connection timeouts, and execution budgets.

## Scope
Applies to all API endpoints, database queries, agent planning loops, browser render times, and CLI command execution tasks.

## Performance Standards & Timeouts
1. **API Latency Baselines:**
   - Database queries must execute within **100ms** (or contain optimized indices, see `35_DATABASE_STANDARD.md`).
   - Relational REST API routes (non-LLM calls) must return JSON payloads within **200ms**.
2. **LLM & Tool Timeout Bounds:**
   - Model API calls: Max timeout is **60 seconds** before connection drop.
   - Built-in tools: Max execution timeout is **120 seconds** before task deactivation.
   - Dynamic skills: Max sandbox run timeout is **180 seconds** (see `18_TOOL_EXECUTION_POLICY.md`).
3. **Core Memory Limits:**
   - The FastAPI backend process must maintain a resident memory footprint below **1GB RAM** under normal load conditions.

## Responsibilities
- **Resource Manager:** Allocates sandbox container limits and flags timeout terminations.
- **Developer Agent:** Optimizes database queries, routes, and memory structures to fit these baselines.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 7 and Rule 15).

## Interfaces
- Local execution monitors tracking performance metrics in Prometheus format.

## Examples
- **Correct Performance:** A search tool executes, queries a local vector database in 30ms, gets the top 3 nodes, and returns the payload in 45ms.
- **Incorrect Performance:** A search tool runs a deep recursive loop over the raw local filesystem, blocking the async event loop for 10 minutes. (Violates Async Heuristic, Latency, and Timeout limits).

## Failure Cases
- **API Call Timeout:** Cloud LLMs experience a network slow-down, dropping connection after 60 seconds. *Mitigation:* The system catches the timeout error, logs a warning, and switches the route to the local fallback model (see `19_MODEL_ROUTING_POLICY.md`).

## Security Considerations
- High execution timeout parameters pose a Denial-of-Service (DoS) risk. Timeout constraints must be strictly enforced on the network proxy layer.

## Future Extension
- Modifications to latency targets or timeouts must be approved via ADR revisions.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [18_TOOL_EXECUTION_POLICY.md](file:///e:/jarvis/docs/18_TOOL_EXECUTION_POLICY.md)
- [19_MODEL_ROUTING_POLICY.md](file:///e:/jarvis/docs/19_MODEL_ROUTING_POLICY.md)
- [35_DATABASE_STANDARD.md](file:///e:/jarvis/docs/35_DATABASE_STANDARD.md)
- [39_OBSERVABILITY_STANDARD.md](file:///e:/jarvis/docs/39_OBSERVABILITY_STANDARD.md)
