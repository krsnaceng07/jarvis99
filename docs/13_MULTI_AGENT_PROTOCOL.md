# 13_MULTI_AGENT_PROTOCOL.md

## Purpose
This document establishes the Multi-Agent Protocol for JARVIS OS. It defines the communication standards, message formatting, and JSON contracts used when agents exchange information or coordinate tasks.

## Scope
Applies to all internal agent communication modules, WebSocket payloads, and queue structures inside the Swarm Orchestrator.

## Communication Standards & JSON Payload Schema
All message exchanges between system subagents must follow a strict JSON schema contract to prevent prompt drift and message corruption:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "InterAgentMessage",
  "type": "OBJECT",
  "properties": {
    "id": { "type": "STRING", "format": "uuid" },
    "sender": { "type": "STRING" },
    "receiver": { "type": "STRING" },
    "priority": { "type": "STRING", "enum": ["critical", "high", "normal", "low"] },
    "goal_id": { "type": "STRING", "format": "uuid" },
    "task_id": { "type": "STRING", "format": "uuid" },
    "message_type": { "type": "STRING", "enum": ["request", "response", "event", "error"] },
    "payload": { "type": "OBJECT" },
    "timestamp": { "type": "STRING", "format": "date-time" }
  },
  "required": ["id", "sender", "receiver", "priority", "message_type", "payload", "timestamp"]
}
```

- **Protocol Execution Standard:** Agents are prohibited from parsing unstructured text messages. All messaging interfaces must serialize and deserialize using this envelope.

## Responsibilities
- **Swarm Orchestrator:** Validates all incoming and outgoing messages against the JSON schema. Blocks invalid payloads.
- **Agent Developer:** Implements API calls matching the message schemas.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 8 and Rule 14).

## Interfaces
- Local Broker: Redis PubSub interface (`jarvis:swarm:channels:*`).
- Remote/UI Gateway: WebSocket connection `/ws/v1/swarm`.

## Examples
- **Correct Message Payload:**
```json
{
  "id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
  "sender": "Planner",
  "receiver": "Developer",
  "priority": "normal",
  "goal_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "task_id": "9c0d1e2f-3a4b-5c6d-7a8b-9c0d1e2f3a4b",
  "message_type": "request",
  "payload": {
    "action": "modify_file",
    "file_path": "src/utils.py",
    "instructions": "Add list merging function."
  },
  "timestamp": "2026-06-26T22:30:00Z"
}
```
- **Incorrect Message Payload:**
"Hey Developer, please edit the utils.py file and add a function." (Violates JSON contract rule).

## Failure Cases
- **Message Drift / Schema Mismatch:** An agent attempts to send an undocumented key in the payload. *Mitigation:* The orchestrator returns a `422 Unprocessable Entity` error block, preventing execution and logging the schema violation.

## Security Considerations
- Payload data must never contain plain vault credentials. Any authorization token must be represented as a temporary session ID.

## Future Extension
- Messages schema extensions require updating this specification and the corresponding validator files.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [08_AI_AGENT_CONSTITUTION.md](file:///e:/jarvis/docs/08_AI_AGENT_CONSTITUTION.md)
- [14_SUBAGENT_ORCHESTRATION.md](file:///e:/jarvis/docs/14_SUBAGENT_ORCHESTRATION.md)
- [62_INTER_AGENT_MESSAGE_PROTOCOL.md](file:///e:/jarvis/docs/62_INTER_AGENT_MESSAGE_PROTOCOL.md)
