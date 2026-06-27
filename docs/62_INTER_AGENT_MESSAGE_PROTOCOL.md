# 62_INTER_AGENT_MESSAGE_PROTOCOL.md

## Purpose
This document defines the Inter-Agent Message Protocol for JARVIS OS. It establishes the detailed JSON serialization envelopes, message routing structures, and payload parser schemas for communication.

## Scope
Applies to all PubSub topics, message queues, and agent connection interfaces inside the Swarm Orchestrator.

## Message Schema Specifications
To prevent communication drift, every message must strictly match the following properties:

### 1. Payload Structure Fields
- `id`: UUIDv4 tracking ID.
- `correlation_id`: Trace ID to link workflow logs.
- `sender`: Name of the originating agent.
- `receiver`: Target agent name.
- `action`: Specific execution verb (e.g. `write_code`, `run_tests`).
- `body`: Nested JSON object containing parameters.
- `checksum`: SHA-256 hash computed over body keys to verify data integrity.

### 2. Message Schema Validation Model
```python
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

class InterAgentMessage(BaseModel):
    id: UUID
    correlation_id: UUID
    sender: str
    receiver: str
    action: str
    body: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

## Responsibilities
- **Swarm Message Bus:** Validates, serializes, and routes messages between agent loops.
- **Security Auditor:** Inspects body contents to filter malicious parameters.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 8, Rule 11, and Rule 14).

## Interfaces
- Broker Channel: Redis stream queue `/jarvis/messages/`.

## Examples
- **Correct Message Envelope:**
```json
{
  "id": "e8a37df4-3d84-4c8d-b94f-7f5e55e81d7f",
  "correlation_id": "a98402db-71bf-4e78-bebf-ea6fb4ea3f8b",
  "sender": "Planner",
  "receiver": "Developer",
  "action": "generate_code",
  "body": {
    "target_file": "core/utils.py",
    "prompt": "Create list merger."
  },
  "timestamp": "2026-06-26T22:30:00Z"
}
```
- **Incorrect Message Envelope:**
A raw text message string or a JSON payload missing the correlation ID or receiver name. (Violates Message Schema rules).

## Failure Cases
- **Message Serialization Error:** An agent attempts to send custom binary assets in the message. *Mitigation:* Binary files must be uploaded to a temp workspace folder first, and the message must only carry the safe local file path.

## Security Considerations
- Unencrypted secrets or database access keys must never be placed inside the body dictionary.

## Future Extension
- Enhancements to communication brokers are logged in ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [13_MULTI_AGENT_PROTOCOL.md](file:///e:/jarvis/docs/13_MULTI_AGENT_PROTOCOL.md)
- [14_SUBAGENT_ORCHESTRATION.md](file:///e:/jarvis/docs/14_SUBAGENT_ORCHESTRATION.md)
- [63_GLOBAL_EVENT_BUS.md](file:///e:/jarvis/docs/63_GLOBAL_EVENT_BUS.md)
