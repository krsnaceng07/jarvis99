# 04_EVENT_SCHEMAS_FREEZE.md

## Purpose
This document freeze-locks the asynchronous event schemas, Redis Stream topic definitions, payload structures, and message broker routing parameters for JARVIS OS.

## Scope
Applies to all PubSub brokers, event publishers, consumer groups, and monitoring workers.

## Immutability Policy
This freeze document is strictly immutable. Future changes require:
```
Architecture Decision Record (ADR) → Impact Analysis → Human Approval → Version Increment
```

## Event Topics & JSON Schemas (Frozen)

### 1. Active Event Topics
- `agent.task.started`: Triggered when an agent picks a task.
- `agent.task.completed`: Triggered on successful verification and reflection.
- `browser.page.loaded`: Triggered when custom viewport navigations complete.
- `system.error.raised`: Triggered when a component triggers an exception.

### 2. Task Started Event Payload Schema (`agent.task.started`)
```json
{
  "type": "object",
  "properties": {
    "event_id": { "type": "string", "format": "uuid" },
    "trace_id": { "type": "string", "format": "uuid" },
    "topic": { "type": "string", "const": "agent.task.started" },
    "payload": {
      "type": "object",
      "properties": {
        "session_id": { "type": "string", "format": "uuid" },
        "task_id": { "type": "string", "format": "uuid" },
        "agent_role": { "type": "string" }
      },
      "required": ["session_id", "task_id", "agent_role"]
    },
    "timestamp": { "type": "string", "format": "date-time" }
  },
  "required": ["event_id", "trace_id", "topic", "payload", "timestamp"]
}
```

### 3. Event Queue Parameters
- **Stream Max Length:** Capped at **10,000 events** (old events are evicted using Redis `MAXLEN ~ 10000`).
- **Ack Timeout:** Unacknowledged events are re-queued after **30 seconds** of lock visibility.

## Responsibilities
- **Global Event Bus Service:** Validates, serializes, and routes payloads to registered listeners.
- **Reviewer Agent:** Rejects code that publishes unregistered event topics.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 8 and Rule 14).

## Interfaces
- Local Broker Client: `jarvis.core.event_bus.client`.

## Examples
- **Correct Event publish:** Publishing `system.error.raised` containing a valid exception class name, traceback summary, and trace ID.
- **Incorrect Event publish:** Publishing an unstructured dictionary containing a custom event name like `"debug_task_click"`. (Violates Event Topics and Schema rules).

## Failure Cases
- **Consumer Deadlock:** A subscriber thread hangs, leaving events unacknowledged. *Mitigation:* The event bus worker daemon enforces a max execution limit on listener callbacks (default: 10s). If exceeded, it terminates the callback and logs errors.

## Security Considerations
- Outbound event data envelopes must filter out variables containing access tokens, decrypted secrets, or private user credentials.

## Future Extension
- Adding new topics requires updating this document via ADR approval.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [36_EVENT_STANDARD.md](file:///e:/jarvis/docs/36_EVENT_STANDARD.md)
- [63_GLOBAL_EVENT_BUS.md](file:///e:/jarvis/docs/63_GLOBAL_EVENT_BUS.md)
