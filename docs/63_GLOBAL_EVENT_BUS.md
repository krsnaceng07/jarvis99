# 63_GLOBAL_EVENT_BUS.md

## Purpose
This document defines the Global Event Bus specifications for JARVIS OS. It establishes event routing logic, topic registration policies, listener parameters, and telemetry streaming hooks.

## Scope
Applies to all async publishers, event streams, monitoring workers, and database brokers.

## Event Bus Topology & Topics
The global event bus is built on an event-driven architecture, enabling decoupled modules to respond asynchronously:

```
[Publisher Service]
        ↓ (Event Event)
[Topic Exchange (Redis Streams)]
    ├─ [Topic: agent.task.*] ──> [Task Monitor Listener]
    ├─ [Topic: browser.page.*] ──> [OCR / DOM Viewer Listener]
    ├─ [Topic: memory.node.*] ──> [Graph Indexer Listener]
    └─ [Topic: system.error.*] ──> [Supervisor / Failsafe Daemon]
```

### Event Topic Rules
1. **Explicit Topic Registration:** Only events matching registered topics can be published to the bus.
2. **Wildcard Listeners:** Subscribers can listen to wildcard patterns (e.g. `agent.*` or `*.error`).
3. **Structured Payload Schema:**
   - Every event must contain a `trace_id` for distributed tracing.
   - Payload dictionary keys must align to schemas documented in the API standards.

## Responsibilities
- **Global Event Bus Service:** Subscribes/Publishes stream messages, and logs metrics.
- **System Supervisor:** Monitors event traffic to identify latency bottlenecks.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Broker API: Redis Stream commands (`XADD`, `XREAD`, `XGROUP`).

## Examples
- **Correct Event Dispatch:** Scraper publishes `browser.page.loaded` containing target URL and performance duration.
- **Incorrect Event Dispatch:** Code directly updates dashboard UI components without triggering event messages on the bus. (Violates Decoupled Event architecture).

## Failure Cases
- **Consumer Lag:** Worker daemons process events slower than they are published, causing Redis stream buffers to grow. *Mitigation:* The event bus limits stream length to a maximum of 10,000 events, dropping older messages once the limit is reached.

## Security Considerations
- Outbound event streams are validated to prevent accidental data leaks. Sensitive code logs or configurations must never enter public topics.

## Future Extension
- Enhancements to the broker setup must be approved via ADR records.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [36_EVENT_STANDARD.md](file:///e:/jarvis/docs/36_EVENT_STANDARD.md)
- [62_INTER_AGENT_MESSAGE_PROTOCOL.md](file:///e:/jarvis/docs/62_INTER_AGENT_MESSAGE_PROTOCOL.md)
