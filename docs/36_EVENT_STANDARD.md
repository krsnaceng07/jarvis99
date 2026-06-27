# 36_EVENT_STANDARD.md

## Purpose
This document defines the Event Standard for JARVIS OS. It establishes topic naming rules, message payload formats, and event broker structures to support an asynchronous event-driven system.

## Scope
Applies to all event bus publishers, subscribers, background worker tasks, and broker handlers.

## Event Bus Standards & Topic Hierarchy
1. **Unified Event Broker:** The system must use a unified event bus powered by Redis Streams or PubSub for low-latency routing and event persistence.
2. **Standard Event Payload:** Every event dispatched to the bus must use a standard JSON envelope:
```json
{
  "event_id": "uuid-string",
  "topic": "agent.state.changed",
  "payload": {},
  "timestamp": "2026-06-26T22:30:00Z"
}
```
3. **Structured Topic Hierarchy:** Event topics must follow a dot-separated namespace pattern:
   - `[component].[resource].[action]`
   - Examples: `agent.task.started`, `browser.page.loaded`, `memory.node.created`.

## Responsibilities
- **Global Event Bus Service:** Manages event listener registrations, handles stream routing, and records transaction logs (see `63_GLOBAL_EVENT_BUS.md`).
- **Developer Agent:** Registers event listeners when integrating new components.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Event APIs: `EventBus.publish(topic: str, payload: dict)` and `EventBus.subscribe(topic: str, handler: Callable)`.

## Examples
- **Correct Event Dispatch:** Agent starts a tool, triggers `EventBus.publish("agent.tool.started", {"tool_name": "file_write"})` which is parsed by loggers.
- **Incorrect Event Dispatch:** An agent creates a direct function call to the logger module when a tool starts. (Violates Decoupled Event architecture).

## Failure Cases
- **Broker Crash / Connection Drop:** Redis goes offline, dropping active events. *Mitigation:* The Event Bus Client uses a memory buffer queue. If Redis goes offline, events are buffered in memory and flushed when the connection is restored.

## Security Considerations
- Events containing sensitive credential strings or encryption keys are strictly prohibited from being published to the global event bus.

## Future Extension
- Transitioning to heavy brokers (e.g. RabbitMQ/Kafka) requires updating this standard and writing an ADR entry.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [31_EVENT_STANDARD.md](file:///e:/jarvis/docs/31_EVENT_STANDARD.md)
- [63_GLOBAL_EVENT_BUS.md](file:///e:/jarvis/docs/63_GLOBAL_EVENT_BUS.md)
