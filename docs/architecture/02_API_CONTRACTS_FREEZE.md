# 02_API_CONTRACTS_FREEZE.md

## Purpose
This document freeze-locks the public API contracts, REST request/response schemas, error envelope shapes, and WebSocket event models for JARVIS OS.

## Scope
Applies to all HTTP and WebSocket endpoints created in the FastAPI backend or consumed by Next.js and Electron clients.

## Immutability Policy
This freeze document is strictly immutable. Future changes require:
```
Architecture Decision Record (ADR) → Impact Analysis → Human Approval → Version Increment
```

## API Contracts & Specifications

### 1. REST Request/Response Envelopes
All successful REST API responses must wrap data outputs inside this schema:
```json
{
  "type": "object",
  "properties": {
    "success": { "type": "boolean", "const": true },
    "data": { "type": "object" },
    "meta": {
      "type": "object",
      "properties": {
        "timestamp": { "type": "string", "format": "date-time" },
        "request_id": { "type": "string", "format": "uuid" }
      },
      "required": ["timestamp", "request_id"]
    }
  },
  "required": ["success", "data", "meta"]
}
```

### 2. Error Response Payload
Unsuccessful REST requests must return this error payload shape:
```json
{
  "type": "object",
  "properties": {
    "success": { "type": "boolean", "const": false },
    "error": {
      "type": "object",
      "properties": {
        "code": { "type": "string" },
        "message": { "type": "string" },
        "details": { "type": "object" }
      },
      "required": ["code", "message"]
    },
    "meta": {
      "type": "object",
      "properties": {
        "timestamp": { "type": "string", "format": "date-time" },
        "request_id": { "type": "string", "format": "uuid" }
      },
      "required": ["timestamp", "request_id"]
    }
  },
  "required": ["success", "error", "meta"]
}
```

### 3. WebSocket Event Envelope
Real-time streams over WebSocket channels use this structured payload:
```json
{
  "type": "object",
  "properties": {
    "event": { "type": "string" },
    "payload": { "type": "object" },
    "timestamp": { "type": "string", "format": "date-time" }
  },
  "required": ["event", "payload", "timestamp"]
}
```

## Responsibilities
- **API Developer:** Must format endpoints to return payloads matching these schemas.
- **Reviewer Agent:** Verifies schema compliance and blocks non-compliant endpoints.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 8, Rule 11, and Rule 13).

## Interfaces
- OpenAPI specification exported to `docs/openapi.json`.

## Examples
- **Correct Response:** A POST `/api/v1/sessions` returns `{ "success": true, "data": { "session_id": "..." }, "meta": { "timestamp": "...", "request_id": "..." } }`.
- **Incorrect Response:** The endpoint returns raw user rows `{ "id": 1, "username": "admin" }` directly. (Violates REST Response envelope rule).

## Failure Cases
- **Schema Drift:** A subagent dynamically updates endpoints with different payload keys. *Mitigation:* The Quality Gates compile the OpenAPI specification file during CI/CD checks and raise validation failures if deviations exist.

## Security Considerations
- Error details objects must never expose file system paths, active database queries, or credentials to the client.

## Future Extension
- Modifications to core envelopes require updating this document via ADR approval.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [34_API_STANDARD.md](file:///e:/jarvis/docs/34_API_STANDARD.md)
- [01_ARCHITECTURE_FREEZE.md](file:///e:/jarvis/docs/architecture/01_ARCHITECTURE_FREEZE.md)
- [08_COMPONENT_INTERFACE_FREEZE.md](file:///e:/jarvis/docs/architecture/08_COMPONENT_INTERFACE_FREEZE.md)
