# 11_ERROR_CODE_STANDARD.md

## Purpose
This document defines the Error Code Standard for JARVIS OS. It establishes a unified, machine-readable error code index to simplify debugging, logging, and automated self-healing.

## Scope
Applies to all custom exception classes, log payload outputs, and database error registries.

## Immutability Policy
This freeze document is strictly immutable. Future changes require:
```
Architecture Decision Record (ADR) → Impact Analysis → Human Approval → Version Increment
```

## System Error Code Index (Frozen)

### 1. Memory Subsystem Errors (`MEMORY_XXX`)
- **`MEMORY_001`**: PostgreSQL Connection Pool Exhausted.
- **`MEMORY_002`**: PgVector Search Timeout (exceeded 100ms baseline).
- **`MEMORY_003`**: Knowledge Graph Node Collision (circular references detected).

### 2. Agent Core Errors (`AGENT_XXX`)
- **`AGENT_001`**: Goal Stack Overflow (exceeded max stack depth of 10).
- **`AGENT_002`**: Loop reflection limit hit (exceeded 3 debug attempts).
- **`AGENT_003`**: Swarm protocol message validation failure (schema mismatch).

### 3. Skill & Tool Errors (`SKILL_XXX`)
- **`SKILL_001`**: Missing digital signature in skill manifest.
- **`SKILL_002`**: Sandbox execution timeout.
- **`SKILL_003`**: Unauthorized sandbox resource write attempt.

### 4. System & Security Errors (`SYSTEM_XXX`)
- **`SYSTEM_001`**: Secrets decryption key path invalid.
- **`SYSTEM_002`**: Host resource exhaustion (OOM/CPU limit hit).
- **`SYSTEM_003`**: Heartbeat timeout (daemon offline for 30s).
- **`SYSTEM_999`**: Unhandled fatal kernel exception.

## Responsibilities
- **Developer Agent:** Uses these error codes when throwing custom exceptions in backend code.
- **Debugger Agent:** Scrapes error codes from stack logs to lookup self-healing recovery rules.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Base Exception Class mapping: `jarvis.core.exceptions.ErrorCode`.

## Examples
- **Correct Code Usage:** `raise JarvisMemoryError(code="MEMORY_001", message="Pool full")`.
- **Incorrect Code Usage:** `raise Exception("DB failed")`. (Violates Custom Error Classes and Code rules).

## Failure Cases
- **Missing Error Code mapping:** A developer throws a custom error containing an unregistered code string. *Mitigation:* The Quality Gates run static analysis checks to verify that all exception arguments map to the Error Code Index.

## Security Considerations
- Errors returned to public REST endpoints must mask details while exposing the code (e.g. returning `{"error": {"code": "SYSTEM_001"}}` to client, but saving full details in backend logs).

## Future Extension
- Creating new error codes requires updating this document via approved PR.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [33_ERROR_HANDLING_STANDARD.md](file:///e:/jarvis/docs/33_ERROR_HANDLING_STANDARD.md)
- [38_ERROR_HANDLING_STANDARD.md](file:///e:/jarvis/docs/38_ERROR_HANDLING_STANDARD.md)
